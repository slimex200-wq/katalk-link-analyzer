import pytest
from fastapi.testclient import TestClient
from server import create_app


@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    app = create_app(db_path)
    return TestClient(app)


@pytest.fixture
def client_with_data(tmp_path):
    from db import Database
    db_path = str(tmp_path / "test.db")
    db = Database(db_path)
    db.insert_link(url="https://example.com", title="테스트", summary="요약", category="기술", tags=["python"])
    db.insert_link(url="https://news.com", title="뉴스", summary="뉴스 요약", category="뉴스", tags=["시사"])
    db.close()
    app = create_app(db_path)
    return TestClient(app)


def test_index_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "카톡 링크 분석기" in resp.text


def test_index_with_data(client_with_data):
    resp = client_with_data.get("/")
    assert resp.status_code == 200
    assert "테스트" in resp.text
    assert "뉴스" in resp.text


def test_filter_by_category(client_with_data):
    resp = client_with_data.get("/?category=기술")
    assert resp.status_code == 200
    assert "테스트" in resp.text
    assert "뉴스" not in resp.text


def test_search(client_with_data):
    resp = client_with_data.get("/?q=파이썬")
    assert resp.status_code == 200


def test_api_links(client_with_data):
    resp = client_with_data.get("/api/links")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
