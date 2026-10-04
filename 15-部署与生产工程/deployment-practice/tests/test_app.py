from fastapi.testclient import TestClient

from deploy_lab.app import LocalStore, create_app


def test_smoke_and_trace_correlation_without_model(tmp_path):
    with TestClient(create_app(LocalStore(tmp_path / "state.sqlite"))) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200
        response = client.post("/demo", json={"question": "工具调用是什么？"}, headers={"X-Trace-Id": "untrusted"})
        assert response.status_code == 200
        assert response.json()["mode"] == "offline"
        assert response.headers["X-Trace-Id"] == response.json()["trace_id"] != "untrusted"


def test_missing_database_is_not_ready_but_process_alive(tmp_path):
    store = LocalStore(tmp_path / "state.sqlite")
    with TestClient(create_app(store)) as client:
        store.path.unlink()
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        assert client.post("/demo", json={"question": "hello"}).status_code == 503
        assert not store.path.exists()


def test_extra_fields_and_oversized_question_rejected(tmp_path):
    with TestClient(create_app(LocalStore(tmp_path / "state.sqlite"))) as client:
        for payload in ({"question": "x", "api_key": "never-log-me"}, {"question": "x" * 501}, {"question": ""}):
            assert client.post("/demo", json=payload).status_code == 422
