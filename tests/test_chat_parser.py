import pytest
from chat_parser import parse_katalk_export


def test_parse_single_url():
    text = "2026년 3월 22일 오후 4:27, 나 : https://example.com/article"
    results = parse_katalk_export(text)
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com/article"
    assert "2026" in results[0]["date"]


def test_parse_url_with_text():
    text = "2026년 3월 22일 오후 4:30, 나 : 이거 나중에 봐야겠다 https://another.com"
    results = parse_katalk_export(text)
    assert len(results) == 1
    assert results[0]["url"] == "https://another.com"


def test_parse_multiple_urls_in_one_message():
    text = "2026년 3월 22일 오후 4:30, 나 : https://a.com https://b.com"
    results = parse_katalk_export(text)
    assert len(results) == 2


def test_parse_multiple_messages():
    text = """2026년 3월 22일 오후 4:27, 나 : https://a.com
2026년 3월 22일 오후 4:30, 나 : https://b.com"""
    results = parse_katalk_export(text)
    assert len(results) == 2


def test_skip_non_url_messages():
    text = """2026년 3월 22일 오후 4:27, 나 : 안녕하세요
2026년 3월 22일 오후 4:30, 나 : https://example.com"""
    results = parse_katalk_export(text)
    assert len(results) == 1


def test_parse_http_url():
    text = "2026년 3월 22일 오후 4:27, 나 : http://example.com"
    results = parse_katalk_export(text)
    assert len(results) == 1


def test_deduplicate_urls():
    text = """2026년 3월 22일 오후 4:27, 나 : https://example.com
2026년 3월 22일 오후 4:30, 나 : https://example.com"""
    results = parse_katalk_export(text)
    assert len(results) == 1


def test_parse_file(tmp_path):
    chat_file = tmp_path / "chat.txt"
    chat_file.write_text("2026년 3월 22일 오후 4:27, 나 : https://example.com", encoding="utf-8")
    results = parse_katalk_export(chat_file.read_text(encoding="utf-8"))
    assert len(results) == 1


def test_parse_mobile_format():
    text = "[나] [오후 4:27] https://example.com"
    results = parse_katalk_export(text)
    assert len(results) == 1


def test_empty_input():
    results = parse_katalk_export("")
    assert len(results) == 0
