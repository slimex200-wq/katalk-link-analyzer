import pytest
from url_normalize import normalize_url


class TestTrackingParamRemoval:
    def test_removes_utm_params(self):
        url = "https://example.com/article?utm_source=kakao&utm_medium=social&id=123"
        assert normalize_url(url) == "https://example.com/article?id=123"

    def test_removes_fbclid(self):
        url = "https://example.com/page?fbclid=abc123"
        assert normalize_url(url) == "https://example.com/page"

    def test_removes_gclid(self):
        url = "https://example.com/?gclid=xyz"
        assert normalize_url(url) == "https://example.com/"

    def test_removes_multiple_tracking_params(self):
        url = "https://example.com/post?utm_source=tw&fbclid=abc&ref=home&title=hello"
        assert normalize_url(url) == "https://example.com/post?title=hello"

    def test_keeps_non_tracking_params(self):
        url = "https://example.com/search?q=python&page=2"
        assert normalize_url(url) == "https://example.com/search?page=2&q=python"

    def test_removes_youtube_si(self):
        url = "https://youtube.com/watch?v=abc123&si=trackingid"
        assert normalize_url(url) == "https://youtube.com/watch?v=abc123"


class TestSubdomainNormalization:
    def test_removes_www(self):
        url = "https://www.example.com/page"
        assert normalize_url(url) == "https://example.com/page"

    def test_mobile_naver(self):
        url = "https://m.naver.com/article/123"
        assert normalize_url(url) == "https://naver.com/article/123"

    def test_mobile_youtube(self):
        url = "https://m.youtube.com/watch?v=abc"
        assert normalize_url(url) == "https://youtube.com/watch?v=abc"

    def test_mobile_tistory(self):
        url = "https://m.blog.tistory.com/post/1"
        assert normalize_url(url) == "https://blog.tistory.com/post/1"

    def test_non_mobile_m_domain_unchanged(self):
        """m.으로 시작하지만 알려진 도메인이 아닌 경우 유지"""
        url = "https://m.custom-site.io/page"
        assert normalize_url(url) == "https://m.custom-site.io/page"


class TestTrailingSlash:
    def test_removes_trailing_slash(self):
        url = "https://example.com/page/"
        assert normalize_url(url) == "https://example.com/page"

    def test_keeps_root_slash(self):
        url = "https://example.com/"
        assert normalize_url(url) == "https://example.com/"

    def test_no_trailing_slash_unchanged(self):
        url = "https://example.com/page"
        assert normalize_url(url) == "https://example.com/page"


class TestCaseNormalization:
    def test_lowercases_host(self):
        url = "https://EXAMPLE.COM/Page"
        assert normalize_url(url) == "https://example.com/Page"

    def test_lowercases_scheme(self):
        url = "HTTPS://example.com/page"
        assert normalize_url(url) == "https://example.com/page"


class TestQuerySorting:
    def test_sorts_params(self):
        url = "https://example.com/search?z=1&a=2&m=3"
        assert normalize_url(url) == "https://example.com/search?a=2&m=3&z=1"


class TestFragmentRemoval:
    def test_removes_fragment(self):
        url = "https://example.com/page#section1"
        assert normalize_url(url) == "https://example.com/page"


class TestEdgeCases:
    def test_no_query_string(self):
        url = "https://example.com/simple"
        assert normalize_url(url) == "https://example.com/simple"

    def test_empty_query_after_filter(self):
        url = "https://example.com/page?utm_source=kakao"
        assert normalize_url(url) == "https://example.com/page"

    def test_invalid_url_returns_as_is(self):
        url = "not-a-url"
        assert normalize_url(url) == "not-a-url"

    def test_same_url_different_tracking_normalizes_same(self):
        url1 = "https://example.com/article?utm_source=kakao&id=42"
        url2 = "https://www.example.com/article/?fbclid=xyz&id=42"
        assert normalize_url(url1) == normalize_url(url2)

    def test_mobile_vs_desktop_normalizes_same(self):
        url1 = "https://m.naver.com/news/123"
        url2 = "https://www.naver.com/news/123"
        assert normalize_url(url1) == normalize_url(url2)
