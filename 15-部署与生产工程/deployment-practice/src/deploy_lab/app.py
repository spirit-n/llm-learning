from __future__ import annotations

from learning_db import Database, DatabaseError
from sqlalchemy import text
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=500)


class PersistentStore:
    def __init__(self, url: str | Path | None = None):
        self.db = Database(url)
        self.path = Path(url) if url is not None and '://' not in str(url) else None
        self.db.create_tables(["CREATE TABLE IF NOT EXISTS requests (trace_id VARCHAR(32) PRIMARY KEY)"])

    def ready(self) -> bool:
        if self.path is not None and not self.path.exists():
            return False
        try:
            with self.db.connection() as db:
                db.execute(text('SELECT trace_id FROM requests LIMIT 1')).fetchall()
            return True
        except DatabaseError:
            return False

    def record(self, trace_id: str) -> None:
        with self.db.transaction() as db:
            db.execute(text('INSERT INTO requests VALUES (:trace)'), {'trace': trace_id})


LocalStore = PersistentStore


def create_app(store: PersistentStore | None = None) -> FastAPI:
    app = FastAPI(title="Offline deployment lab")
    app.state.store = store if store is not None else PersistentStore()

    @app.middleware("http")
    async def correlation(request: Request, call_next):
        # Do not trust caller-provided trace IDs as log strings or identities.
        request.state.trace_id = uuid4().hex
        response = await call_next(request)
        response.headers["X-Trace-Id"] = request.state.trace_id
        return response

    @app.get("/health")
    def health():
        return {"status": "alive", "mode": "offline"}

    @app.get("/ready")
    def ready():
        if not app.state.store.ready():
            raise HTTPException(status_code=503, detail="storage_not_ready")
        return {"status": "ready"}

    @app.post("/demo")
    def demo(question: Question, request: Request):
        if not app.state.store.ready():
            raise HTTPException(status_code=503, detail="storage_not_ready")
        try:
            app.state.store.record(request.state.trace_id)
        except DatabaseError:
            raise HTTPException(status_code=503, detail="storage_unavailable") from None
        # Deliberately fixed answer: this validates serving, not intelligence.
        return {"answer": "离线演示：模型提出调用意图，应用程序校验并执行工具。",
                "mode": "offline", "trace_id": request.state.trace_id}

    return app
