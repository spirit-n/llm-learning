from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=500)


class LocalStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS requests (trace_id TEXT PRIMARY KEY)")

    def connect(self):
        # mode=rw prevents a removed database silently being recreated as 'healthy'.
        return sqlite3.connect(self.path.resolve().as_uri() + "?mode=rw", uri=True, timeout=1)

    def ready(self) -> bool:
        try:
            with closing(self.connect()) as db:
                db.execute("SELECT trace_id FROM requests LIMIT 1").fetchall()
            return True
        except sqlite3.Error:
            return False

    def record(self, trace_id: str) -> None:
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO requests VALUES (?)", (trace_id,))


def create_app(store: LocalStore | None = None) -> FastAPI:
    app = FastAPI(title="Offline deployment lab")
    app.state.store = store if store is not None else LocalStore(Path("data/state.sqlite"))

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
        except sqlite3.Error:
            raise HTTPException(status_code=503, detail="storage_unavailable") from None
        # Deliberately fixed answer: this validates serving, not intelligence.
        return {"answer": "离线演示：模型提出调用意图，应用程序校验并执行工具。",
                "mode": "offline", "trace_id": request.state.trace_id}

    return app
