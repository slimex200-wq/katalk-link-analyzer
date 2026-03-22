# KaTalk Link Analyzer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 카카오톡 대화 내보내기에서 링크를 추출, 크롤링, Claude CLI로 요약/분류하고 웹 UI로 결과를 확인하는 CLI 도구 구현

**Architecture:** Python CLI 파이프라인 (Parser → Crawler → Analyzer → SQLite) + FastAPI 웹 UI. 크롤링은 requests/BeautifulSoup 기본, playwright fallback. 분석은 `claude -p` CLI 호출, ThreadPoolExecutor 병렬 처리.

**Tech Stack:** Python 3.11+, click, requests, beautifulsoup4, playwright, pydantic, sqlite3, FastAPI, uvicorn, jinja2, tqdm

**Spec:** `docs/superpowers/specs/2026-03-22-katalk-link-analyzer-design.md`

---

## File Structure

```
katalk-link-analyzer/
  main.py              # CLI 진입점 (click)
  chat_parser.py       # 카톡 .txt 파서 — URL + 날짜 추출
  crawler.py           # 웹 크롤러 — requests + playwright fallback
  analyzer.py          # Claude CLI 분석기 — subprocess + JSON 파싱
  models.py            # Pydantic 모델 — AnalysisResult, LinkRecord
  db.py                # SQLite CRUD — links, categories 테이블
  server.py            # FastAPI 웹 서버 + API 엔드포인트
  templates/
    index.html         # 메인 페이지 (카드 목록, 사이드바, 검색)
  static/
    style.css          # 스타일시트
  tests/
    __init__.py
    test_chat_parser.py
    test_crawler.py
    test_analyzer.py
    test_db.py
    test_server.py
  requirements.txt
```

---

### Task 1: 프로젝트 초기화 + DB 스키마

**Files:**
- Create: `requirements.txt`
- Create: `models.py`
- Create: `db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: 프로젝트 초기화**

```bash
cd ~/claude-projects/katalk-link-analyzer
python -m venv venv
source venv/Scripts/activate
```

- [ ] **Step 2: requirements.txt 작성**

```
click>=8.1
requests>=2.31
beautifulsoup4>=4.12
playwright>=1.40
pydantic>=2.5
fastapi>=0.109
uvicorn>=0.27
jinja2>=3.1
tqdm>=4.66
pytest>=8.0
httpx>=0.27
```

```bash
pip install -r requirements.txt
```

- [ ] **Step 2.5: .gitignore 작성**

```
venv/
__pycache__/
*.db
*.pyc
.env
.pytest_cache/
```

- [ ] **Step 3: Pydantic 모델 작성 (models.py)**

```python
from pydantic import BaseModel


class AnalysisResult(BaseModel):
    summary: str
    category: str
    tags: list[str]


class LinkRecord(BaseModel):
    id: int | None = None
    url: str
    title: str | None = None
    summary: str | None = None
    category: str | None = None
    tags: list[str] = []
    source_date: str | None = None
    raw_content: str | None = None
```

- [ ] **Step 4: DB 테스트 작성 (tests/test_db.py)**

```python
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
```

- [ ] **Step 5: 테스트 실행 — 실패 확인**

```bash
pytest tests/test_db.py -v
```

Expected: FAIL — `db` 모듈 없음

- [ ] **Step 6: db.py 구현**

```python
import json
import sqlite3
from datetime import datetime, timezone

DEFAULT_CATEGORIES = ["기술", "뉴스", "쇼핑", "참고자료", "엔터테인먼트"]


class Database:
    def __init__(self, db_path: str = "links.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                is_default BOOLEAN DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT,
                summary TEXT,
                category TEXT,
                tags TEXT DEFAULT '[]',
                source_date TEXT,
                created_at TEXT,
                raw_content TEXT
            );
        """)
        for cat in DEFAULT_CATEGORIES:
            self.conn.execute(
                "INSERT OR IGNORE INTO categories (name, is_default) VALUES (?, 1)",
                (cat,),
            )
        self.conn.commit()

    def execute(self, sql, params=()):
        return self.conn.execute(sql, params)

    def insert_link(self, url, title=None, summary=None, category=None, tags=None, source_date=None, raw_content=None):
        try:
            self.conn.execute(
                """INSERT INTO links (url, title, summary, category, tags, source_date, created_at, raw_content)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (url, title, summary, category, json.dumps(tags or [], ensure_ascii=False),
                 source_date, datetime.now(timezone.utc).isoformat(), raw_content),
            )
            if category:
                self.ensure_category(category)
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def upsert_link(self, url, **kwargs):
        fields = {k: v for k, v in kwargs.items() if v is not None}
        if "tags" in fields:
            fields["tags"] = json.dumps(fields["tags"], ensure_ascii=False)
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [url]
        self.conn.execute(f"UPDATE links SET {set_clause} WHERE url = ?", values)
        if "category" in fields:
            self.ensure_category(kwargs["category"])
        self.conn.commit()

    def get_link_by_url(self, url):
        row = self.conn.execute("SELECT * FROM links WHERE url = ?", (url,)).fetchone()
        if row:
            result = dict(row)
            result["tags"] = json.loads(result["tags"]) if result["tags"] else []
            return result
        return None

    def get_links(self, category=None, search=None):
        query = "SELECT * FROM links"
        params = []
        conditions = []
        if category:
            conditions.append("category = ?")
            params.append(category)
        if search:
            conditions.append("(title LIKE ? OR summary LIKE ? OR tags LIKE ?)")
            params.extend([f"%{search}%"] * 3)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC"
        rows = self.conn.execute(query, params).fetchall()
        results = []
        for row in rows:
            r = dict(row)
            r["tags"] = json.loads(r["tags"]) if r["tags"] else []
            results.append(r)
        return results

    def search_links(self, query):
        return self.get_links(search=query)

    def get_categories(self):
        rows = self.conn.execute("SELECT * FROM categories ORDER BY is_default DESC, name").fetchall()
        return [dict(r) for r in rows]

    def ensure_category(self, name):
        self.conn.execute("INSERT OR IGNORE INTO categories (name, is_default) VALUES (?, 0)", (name,))
        self.conn.commit()

    def url_exists(self, url):
        return self.conn.execute("SELECT 1 FROM links WHERE url = ?", (url,)).fetchone() is not None

    def close(self):
        self.conn.close()
```

- [ ] **Step 7: 테스트 실행 — 통과 확인**

```bash
pytest tests/test_db.py -v
```

Expected: ALL PASS

- [ ] **Step 8: 커밋**

```bash
git init
git add .gitignore requirements.txt models.py db.py tests/__init__.py tests/test_db.py docs/
git commit -m "feat: 프로젝트 초기화, DB 스키마 + CRUD 구현"
```

---

### Task 2: 카톡 파서

**Files:**
- Create: `chat_parser.py`
- Create: `tests/test_chat_parser.py`

- [ ] **Step 1: 테스트 작성 (tests/test_chat_parser.py)**

```python
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
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/test_chat_parser.py -v
```

Expected: FAIL

- [ ] **Step 3: chat_parser.py 구현**

```python
import re
from urllib.parse import urlparse

URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')

# PC 형식: "2026년 3월 22일 오후 4:27, 나 : ..."
PC_DATE_PATTERN = re.compile(r'(\d{4}년 \d{1,2}월 \d{1,2}일 [오전후]+ \d{1,2}:\d{2})')

# 모바일 형식: "[나] [오후 4:27] ..."
MOBILE_DATE_PATTERN = re.compile(r'\[.*?\]\s*\[([오전후]+ \d{1,2}:\d{2})\]')


def parse_katalk_export(text: str) -> list[dict]:
    if not text.strip():
        return []

    seen_urls: set[str] = set()
    results: list[dict] = []
    current_date = None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        pc_match = PC_DATE_PATTERN.search(line)
        if pc_match:
            current_date = pc_match.group(1)

        mobile_match = MOBILE_DATE_PATTERN.search(line)
        if mobile_match:
            current_date = mobile_match.group(1)

        urls = URL_PATTERN.findall(line)
        for url in urls:
            url = url.rstrip(".,;:!?)")
            if url not in seen_urls and _is_valid_url(url):
                seen_urls.add(url)
                results.append({
                    "url": url,
                    "date": current_date,
                })

    return results


def _is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return bool(parsed.scheme and parsed.netloc)
    except Exception:
        return False
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
pytest tests/test_chat_parser.py -v
```

Expected: ALL PASS

- [ ] **Step 5: 커밋**

```bash
git add chat_parser.py tests/test_chat_parser.py
git commit -m "feat: 카톡 대화 내보내기 파서 구현 (PC/모바일 형식)"
```

---

### Task 3: 웹 크롤러

**Files:**
- Create: `crawler.py`
- Create: `tests/test_crawler.py`

- [ ] **Step 1: 테스트 작성 (tests/test_crawler.py)**

```python
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
    result = crawl_url("https://this-domain-does-not-exist-12345.com")
    assert result is None


def test_empty_html():
    result = extract_text_content("")
    assert result["title"] is None
    assert result["text"] == ""
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/test_crawler.py -v
```

Expected: FAIL

- [ ] **Step 3: crawler.py 구현**

```python
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
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
pytest tests/test_crawler.py -v
```

Expected: ALL PASS

- [ ] **Step 5: 커밋**

```bash
git add crawler.py tests/test_crawler.py
git commit -m "feat: 웹 크롤러 구현 (requests + playwright fallback)"
```

---

### Task 4: Claude CLI 분석기

**Files:**
- Create: `analyzer.py`
- Create: `tests/test_analyzer.py`

- [ ] **Step 1: 테스트 작성 (tests/test_analyzer.py)**

```python
import json
import pytest
from analyzer import parse_claude_response, build_prompt, analyze_content
from models import AnalysisResult


def test_parse_valid_json():
    response = '{"summary": "요약입니다", "category": "기술", "tags": ["python", "AI"]}'
    result = parse_claude_response(response)
    assert isinstance(result, AnalysisResult)
    assert result.summary == "요약입니다"
    assert result.category == "기술"
    assert result.tags == ["python", "AI"]


def test_parse_json_in_code_block():
    response = '```json\n{"summary": "요약", "category": "뉴스", "tags": ["test"]}\n```'
    result = parse_claude_response(response)
    assert result.summary == "요약"


def test_parse_json_with_extra_text():
    response = '여기 결과입니다:\n{"summary": "요약", "category": "기술", "tags": ["a"]}'
    result = parse_claude_response(response)
    assert result.summary == "요약"


def test_parse_invalid_json():
    response = "이건 JSON이 아닙니다"
    result = parse_claude_response(response)
    assert result is None


def test_parse_missing_fields():
    response = '{"summary": "요약"}'
    result = parse_claude_response(response)
    assert result is None


def test_build_prompt():
    prompt = build_prompt("테스트 콘텐츠", ["기술", "뉴스"])
    assert "테스트 콘텐츠" in prompt
    assert "기술" in prompt
    assert "JSON" in prompt


def test_build_prompt_with_existing_categories():
    prompt = build_prompt("내용", ["기술", "뉴스", "커스텀"])
    assert "커스텀" in prompt
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/test_analyzer.py -v
```

Expected: FAIL

- [ ] **Step 3: analyzer.py 구현**

```python
import json
import logging
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from models import AnalysisResult
from pydantic import ValidationError

logger = logging.getLogger(__name__)

MAX_WORKERS = 3
CODE_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)
JSON_OBJECT_PATTERN = re.compile(r"\{[^{}]*(?:\[[^\[\]]*\][^{}]*)?\}", re.DOTALL)


def build_prompt(content: str, existing_categories: list[str] | None = None) -> str:
    cats = existing_categories or ["기술", "뉴스", "쇼핑", "참고자료", "엔터테인먼트"]
    cat_list = ", ".join(cats)
    return f"""다음 웹 페이지 내용을 분석해서 JSON만 응답해줘 (다른 텍스트 없이):
- summary: 2-3문장 한글 요약
- category: 기존 카테고리 [{cat_list}] 중 하나, 없으면 새 카테고리명
- tags: 관련 태그 3-5개 (한글)

내용:
{content}"""


def parse_claude_response(response: str) -> AnalysisResult | None:
    json_str = None

    code_match = CODE_BLOCK_PATTERN.search(response)
    if code_match:
        json_str = code_match.group(1).strip()

    if json_str is None:
        obj_match = JSON_OBJECT_PATTERN.search(response)
        if obj_match:
            json_str = obj_match.group(0)

    if json_str is None:
        return None

    try:
        data = json.loads(json_str)
        return AnalysisResult(**data)
    except (json.JSONDecodeError, ValidationError):
        return None


def analyze_content(content: str, existing_categories: list[str] | None = None) -> AnalysisResult | None:
    prompt = build_prompt(content, existing_categories)

    for attempt in range(2):
        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                parsed = parse_claude_response(result.stdout)
                if parsed:
                    return parsed
                logger.warning("JSON 파싱 실패 (시도 %d): %s", attempt + 1, result.stdout[:200])
            else:
                logger.warning("claude -p 실패 (시도 %d): %s", attempt + 1, result.stderr[:200])
        except subprocess.TimeoutExpired:
            logger.warning("claude -p 타임아웃 (시도 %d)", attempt + 1)
        except Exception as e:
            logger.warning("claude -p 에러 (시도 %d): %s", attempt + 1, e)

    return None


def analyze_batch(items: list[dict], existing_categories: list[str] | None = None, max_workers: int = MAX_WORKERS) -> list[dict]:
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(analyze_content, item["content"], existing_categories): item
            for item in items
        }
        for future in as_completed(futures):
            item = futures[future]
            try:
                analysis = future.result()
                results.append({**item, "analysis": analysis})
            except Exception as e:
                logger.warning("분석 실패 %s: %s", item.get("url", "?"), e)
                results.append({**item, "analysis": None})

    return results
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
pytest tests/test_analyzer.py -v
```

Expected: ALL PASS (subprocess 호출 테스트는 제외, 파싱 로직만 테스트)

- [ ] **Step 5: 커밋**

```bash
git add analyzer.py tests/test_analyzer.py
git commit -m "feat: Claude CLI 분석기 구현 (JSON 파싱 + 병렬 처리)"
```

---

### Task 5: CLI 메인 파이프라인

**Files:**
- Create: `main.py`

- [ ] **Step 1: main.py 구현**

```python
import logging
import sys

import click
from tqdm import tqdm

from analyzer import analyze_content
from crawler import crawl_url
from db import Database
from chat_parser import parse_katalk_export

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@click.group()
def cli():
    """카톡 링크 분석기 — 나에게 보내기 링크를 분석하고 정리합니다."""
    pass


@cli.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--max-links", type=int, default=None, help="최대 처리 링크 수")
@click.option("--force", is_flag=True, help="기존 링크도 재분석")
@click.option("--db-path", default="links.db", help="DB 파일 경로")
def parse(file_path: str, max_links: int | None, force: bool, db_path: str):
    """카톡 대화 내보내기 파일에서 링크를 추출하고 분석합니다."""
    db = Database(db_path)

    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    links = parse_katalk_export(text)
    click.echo(f"추출된 링크: {len(links)}개")

    if not force:
        links = [l for l in links if not db.url_exists(l["url"])]
        click.echo(f"새 링크: {len(links)}개")

    if max_links:
        links = links[:max_links]

    if not links:
        click.echo("처리할 링크가 없습니다.")
        return

    categories = [c["name"] for c in db.get_categories()]

    for link in tqdm(links, desc="분석 중"):
        url = link["url"]
        crawled = crawl_url(url)

        if crawled is None:
            logger.warning("크롤링 실패: %s", url)
            db.insert_link(url=url, source_date=link["date"], summary="크롤링 실패")
            continue

        title = crawled["title"]
        content = crawled["text"]

        if not content.strip():
            logger.warning("빈 콘텐츠: %s", url)
            db.insert_link(url=url, title=title, source_date=link["date"], summary="콘텐츠 없음")
            continue

        analysis = analyze_content(content, categories)

        if analysis:
            if force and db.url_exists(url):
                db.upsert_link(
                    url=url, title=title, summary=analysis.summary,
                    category=analysis.category, tags=analysis.tags,
                    source_date=link["date"], raw_content=content[:5000],
                )
            else:
                db.insert_link(
                    url=url, title=title, summary=analysis.summary,
                    category=analysis.category, tags=analysis.tags,
                    source_date=link["date"], raw_content=content[:5000],
                )
            if analysis.category not in categories:
                categories.append(analysis.category)
        else:
            db.insert_link(url=url, title=title, source_date=link["date"], summary="분석 실패")

    total = len(db.get_links())
    click.echo(f"완료! 총 {total}개 링크 저장됨.")
    db.close()


@cli.command(name="list")
@click.option("--category", default=None, help="카테고리 필터")
@click.option("--search", default=None, help="검색어")
@click.option("--db-path", default="links.db", help="DB 파일 경로")
def list_links(category: str | None, search: str | None, db_path: str):
    """저장된 링크 목록을 표시합니다."""
    db = Database(db_path)
    links = db.get_links(category=category, search=search)

    if not links:
        click.echo("저장된 링크가 없습니다.")
        return

    for link in links:
        cat = f"[{link['category']}]" if link["category"] else ""
        tags = " ".join(f"#{t}" for t in link["tags"]) if link["tags"] else ""
        click.echo(f"\n{cat} {link['title'] or link['url']}")
        if link["summary"]:
            click.echo(f"  {link['summary']}")
        if tags:
            click.echo(f"  {tags}")
        click.echo(f"  {link['url']}")

    db.close()


@cli.command()
@click.option("--port", default=8080, help="서버 포트")
@click.option("--db-path", default="links.db", help="DB 파일 경로")
def serve(port: int, db_path: str):
    """웹 UI 서버를 실행합니다."""
    import uvicorn
    from server import create_app

    app = create_app(db_path)
    click.echo(f"서버 시작: http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    cli()
```

- [ ] **Step 2: CLI 도움말 확인**

```bash
python main.py --help
python main.py parse --help
```

Expected: 도움말 출력

- [ ] **Step 3: 커밋**

```bash
git add main.py
git commit -m "feat: CLI 메인 파이프라인 구현 (parse, list, serve)"
```

---

### Task 6: FastAPI 웹 UI

**Files:**
- Create: `server.py`
- Create: `templates/index.html`
- Create: `static/style.css`
- Create: `tests/test_server.py`

- [ ] **Step 1: 테스트 작성 (tests/test_server.py)**

```python
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
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/test_server.py -v
```

Expected: FAIL

- [ ] **Step 3: server.py 구현**

```python
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import Database

BASE_DIR = Path(__file__).parent


def create_app(db_path: str = "links.db") -> FastAPI:
    app = FastAPI(title="카톡 링크 분석기")
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=BASE_DIR / "templates")

    def get_db():
        return Database(db_path)

    @app.get("/", response_class=HTMLResponse)
    async def index(
        request: Request,
        category: str | None = Query(None),
        q: str | None = Query(None),
    ):
        db = get_db()
        links = db.get_links(category=category, search=q)
        categories = db.get_categories()
        db.close()
        return templates.TemplateResponse("index.html", {
            "request": request,
            "links": links,
            "categories": categories,
            "current_category": category,
            "search_query": q or "",
        })

    @app.get("/api/links")
    async def api_links(
        category: str | None = Query(None),
        q: str | None = Query(None),
    ):
        db = get_db()
        links = db.get_links(category=category, search=q)
        db.close()
        return links

    return app
```

- [ ] **Step 4: templates/index.html 작성**

```html
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>카톡 링크 분석기</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="container">
        <header>
            <h1>카톡 링크 분석기</h1>
            <form class="search-bar" method="get" action="/">
                <input type="text" name="q" value="{{ search_query }}" placeholder="검색어 입력...">
                <button type="submit">검색</button>
            </form>
        </header>

        <div class="layout">
            <aside class="sidebar">
                <h3>카테고리</h3>
                <ul>
                    <li><a href="/" class="{{ 'active' if not current_category else '' }}">전체</a></li>
                    {% for cat in categories %}
                    <li>
                        <a href="/?category={{ cat.name }}"
                           class="{{ 'active' if current_category == cat.name else '' }}">
                            {{ cat.name }}
                        </a>
                    </li>
                    {% endfor %}
                </ul>
            </aside>

            <main class="content">
                {% if links %}
                <p class="count">{{ links|length }}개 링크</p>
                {% for link in links %}
                <div class="card">
                    <div class="card-header">
                        <a href="{{ link.url }}" target="_blank" class="card-title">
                            {{ link.title or link.url }}
                        </a>
                        {% if link.category %}
                        <span class="badge">{{ link.category }}</span>
                        {% endif %}
                    </div>
                    {% if link.summary %}
                    <p class="card-summary">{{ link.summary }}</p>
                    {% endif %}
                    <div class="card-footer">
                        <div class="tags">
                            {% for tag in link.tags %}
                            <a href="/?q={{ tag }}" class="tag">#{{ tag }}</a>
                            {% endfor %}
                        </div>
                        {% if link.source_date %}
                        <span class="date">{{ link.source_date }}</span>
                        {% endif %}
                    </div>
                </div>
                {% endfor %}
                {% else %}
                <p class="empty">저장된 링크가 없습니다.</p>
                {% endif %}
            </main>
        </div>
    </div>
</body>
</html>
```

- [ ] **Step 5: static/style.css 작성**

```css
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #0a0a0a;
    color: #e0e0e0;
    line-height: 1.6;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}

header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid #222;
}

h1 { font-size: 1.4rem; color: #fff; }

.search-bar { display: flex; gap: 8px; }

.search-bar input {
    background: #1a1a1a;
    border: 1px solid #333;
    color: #e0e0e0;
    padding: 8px 12px;
    border-radius: 6px;
    width: 240px;
}

.search-bar button {
    background: #2563eb;
    color: #fff;
    border: none;
    padding: 8px 16px;
    border-radius: 6px;
    cursor: pointer;
}

.layout {
    display: grid;
    grid-template-columns: 200px 1fr;
    gap: 24px;
}

.sidebar h3 {
    font-size: 0.85rem;
    color: #888;
    margin-bottom: 12px;
    text-transform: uppercase;
}

.sidebar ul { list-style: none; }

.sidebar li a {
    display: block;
    padding: 6px 10px;
    color: #aaa;
    text-decoration: none;
    border-radius: 4px;
    font-size: 0.9rem;
}

.sidebar li a:hover, .sidebar li a.active {
    background: #1a1a1a;
    color: #fff;
}

.count {
    font-size: 0.85rem;
    color: #666;
    margin-bottom: 16px;
}

.card {
    background: #141414;
    border: 1px solid #222;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
}

.card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}

.card-title {
    color: #60a5fa;
    text-decoration: none;
    font-weight: 500;
}

.card-title:hover { text-decoration: underline; }

.badge {
    background: #1e3a5f;
    color: #93c5fd;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
}

.card-summary {
    color: #bbb;
    font-size: 0.9rem;
    margin-bottom: 8px;
}

.card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.tags { display: flex; gap: 6px; flex-wrap: wrap; }

.tag {
    color: #888;
    text-decoration: none;
    font-size: 0.8rem;
}

.tag:hover { color: #60a5fa; }

.date { color: #555; font-size: 0.8rem; }

.empty { color: #666; text-align: center; padding: 40px; }
```

- [ ] **Step 6: 테스트 실행 — 통과 확인**

```bash
pytest tests/test_server.py -v
```

Expected: ALL PASS

- [ ] **Step 7: 커밋**

```bash
git add server.py templates/ static/ tests/test_server.py
git commit -m "feat: FastAPI 웹 UI 구현 (카드 목록, 카테고리 필터, 검색)"
```

---

### Task 7: 통합 테스트 + 마무리

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_integration.py`

- [ ] **Step 1: conftest.py 작성**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
```

- [ ] **Step 2: 통합 테스트 작성 (tests/test_integration.py)**

```python
import pytest
from click.testing import CliRunner
from main import cli


@pytest.fixture
def sample_chat(tmp_path):
    chat = tmp_path / "chat.txt"
    chat.write_text(
        "2026년 3월 22일 오후 4:27, 나 : https://www.python.org\n"
        "2026년 3월 22일 오후 4:30, 나 : 파이썬 공식 사이트\n",
        encoding="utf-8",
    )
    return str(chat)


def test_parse_extracts_links(sample_chat, tmp_path):
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    result = runner.invoke(cli, ["parse", sample_chat, "--db-path", db_path, "--max-links", "1"])
    assert result.exit_code == 0
    assert "추출된 링크: 1개" in result.output


def test_list_empty(tmp_path):
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    result = runner.invoke(cli, ["list", "--db-path", db_path])
    assert "저장된 링크가 없습니다" in result.output


def test_parse_then_list(sample_chat, tmp_path):
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["parse", sample_chat, "--db-path", db_path, "--max-links", "1"])
    result = runner.invoke(cli, ["list", "--db-path", db_path])
    assert "python.org" in result.output
```

- [ ] **Step 3: 전체 테스트 실행**

```bash
pytest tests/ -v --tb=short
```

Expected: ALL PASS

- [ ] **Step 4: 커밋**

```bash
git add tests/conftest.py tests/test_integration.py
git commit -m "test: 통합 테스트 추가"
```

- [ ] **Step 5: playwright 설치**

```bash
playwright install chromium
```

- [ ] **Step 6: 최종 커밋**

```bash
git add -A
git commit -m "chore: 프로젝트 초기 설정 완료"
```
