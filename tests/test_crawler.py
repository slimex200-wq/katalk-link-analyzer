import pytest
from crawler import crawl_url, extract_text_content


def test_extract_text_from_html():
    html = "<html><head><title>Test</title></head><body><p>Hello World</p></body></html>"
    result = extract_text_content(html)
    assert result["title"] == "Test"
    assert "Hello World" in result["text"]


def test_extract_title_from_og_tag():
    html = '<html><head><meta property="og:title" content="OG Title"></head><body></body></html>'
    result = extract_text_content(html)
    assert result["title"] == "OG Title"


def test_text_truncation():
    html = "<html><body><p>" + "가" * 10000 + "</p></body></html>"
    result = extract_text_content(html, max_length=5000)
    assert len(result["text"]) <= 5000


def test_strip_script_and_style():
    html = "<html><body><script>alert(1)</script><style>.x{}</style><p>Content</p></body></html>"
    result = extract_text_content(html)
    assert "alert" not in result["text"]
    assert "Content" in result["text"]


def test_crawl_invalid_url():
    result = crawl_url("https://this-domain-does-not-exist-12345.com", delay=0)
    assert result is None


def test_empty_html():
    result = extract_text_content("")
    assert result["title"] is None
    assert result["text"] == ""
