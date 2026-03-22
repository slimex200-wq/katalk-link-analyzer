import os
import pytest
from db import Database


@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test.db"
    db = Database(str(db_path))
    yield db
    db.close()


def test_init_creates_tables(test_db):
    tables = test_db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = [t[0] for t in tables]
    assert "links" in names
    assert "categories" in names


def test_default_categories_created(test_db):
    cats = test_db.get_categories()
    names = [c["name"] for c in cats]
    assert "기술" in names
    assert "뉴스" in names
    assert "쇼핑" in names
    assert "참고자료" in names
    assert "엔터테인먼트" in names


def test_insert_link(test_db):
    test_db.insert_link(
        url="https://example.com",
        title="Test",
        summary="요약",
        category="기술",
        tags=["python", "test"],
        source_date="2026-03-22",
    )
    link = test_db.get_link_by_url("https://example.com")
    assert link is not None
    assert link["title"] == "Test"
    assert link["category"] == "기술"


def test_duplicate_url_skipped(test_db):
    test_db.insert_link(url="https://example.com", title="First")
    result = test_db.insert_link(url="https://example.com", title="Second")
    assert result is False
    link = test_db.get_link_by_url("https://example.com")
    assert link["title"] == "First"


def test_get_links_by_category(test_db):
    test_db.insert_link(url="https://a.com", title="A", category="기술")
    test_db.insert_link(url="https://b.com", title="B", category="뉴스")
    links = test_db.get_links(category="기술")
    assert len(links) == 1
    assert links[0]["url"] == "https://a.com"


def test_search_links(test_db):
    test_db.insert_link(url="https://a.com", title="Python 튜토리얼", summary="파이썬 기초")
    test_db.insert_link(url="https://b.com", title="맛집 추천", summary="강남 맛집")
    results = test_db.search_links("파이썬")
    assert len(results) == 1


def test_upsert_link_with_force(test_db):
    test_db.insert_link(url="https://example.com", title="Old")
    test_db.upsert_link(url="https://example.com", title="New", summary="Updated")
    link = test_db.get_link_by_url("https://example.com")
    assert link["title"] == "New"


def test_ensure_category_creates_new(test_db):
    test_db.ensure_category("새카테고리")
    cats = test_db.get_categories()
    names = [c["name"] for c in cats]
    assert "새카테고리" in names
