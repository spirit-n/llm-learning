import pytest

from tool_loop import tools


@pytest.fixture(autouse=True)
def offline_analytics(tmp_path, monkeypatch):
    store_class = tools.AnalyticsStore
    monkeypatch.setattr(tools, "AnalyticsStore", lambda: store_class(tmp_path / "analytics.sqlite"))
