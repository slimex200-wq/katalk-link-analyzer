import logging
import time

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_MAX_LENGTH = 5000
REQUEST_TIMEOUT = 15


def crawl_url(url: str, delay: float = 1.0) -> dict | None:
    time.sleep(delay)

    result = _crawl_with_requests(url)
    if result is None:
        result = _crawl_with_playwright(url)
    elif result.get("_skip_fallback"):
        result.pop("_skip_fallback", None)

    return result


def _crawl_with_requests(url: str) -> dict | None:
    try:
        resp = requests.get(url, headers={"User-Agent": DEFAULT_UA}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        result = extract_text_content(resp.text)
        if result["text"].strip():
            return result
        return None  # 빈 콘텐츠 → playwright fallback
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code in (403, 404, 410):
            logger.warning("HTTP %d for %s, skipping", e.response.status_code, url)
            return {"title": None, "text": "", "_skip_fallback": True}
        logger.warning("requests failed for %s: %s", url, e)
        return None
    except Exception as e:
        logger.warning("requests failed for %s: %s", url, e)
        return None


def _crawl_with_playwright(url: str) -> dict | None:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=DEFAULT_UA)
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=10000)
            html = page.content()
            browser.close()
            return extract_text_content(html)
    except Exception as e:
        logger.warning("playwright failed for %s: %s", url, e)
        return None


def extract_text_content(html: str, max_length: int = DEFAULT_MAX_LENGTH) -> dict:
    if not html:
        return {"title": None, "text": ""}

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    og_title = soup.find("meta", property="og:title")
    title_tag = soup.find("title")
    title = None
    if og_title and og_title.get("content"):
        title = og_title["content"]
    elif title_tag:
        title = title_tag.get_text(strip=True)

    text = soup.get_text(separator="\n", strip=True)
    text = "\n".join(line for line in text.splitlines() if line.strip())

    if len(text) > max_length:
        text = text[:max_length]

    return {"title": title, "text": text}
