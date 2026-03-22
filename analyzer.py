import json
import logging
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from models import AnalysisResult
from pydantic import ValidationError

logger = logging.getLogger(__name__)

MAX_WORKERS = 3
CODE_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)
JSON_OBJECT_PATTERN = re.compile(r"\{[^{}]*(?:\[[^\[\]]*\][^{}]*)?\}", re.DOTALL)


def _detect_backend() -> str:
    """사용 가능한 AI 백엔드 자동 감지. 환경변수 ANALYZER_BACKEND으로 강제 지정 가능."""
    forced = os.environ.get("ANALYZER_BACKEND", "").lower()
    if forced in ("claude", "openai"):
        return forced

    # Claude CLI 우선
    try:
        r = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=10, shell=True,
        )
        if r.returncode == 0:
            return "claude"
    except Exception:
        pass

    # OpenAI API key 확인
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"

    raise RuntimeError(
        "AI 백엔드를 찾을 수 없습니다.\n"
        "- Claude Code CLI 설치: https://docs.anthropic.com/en/docs/claude-code\n"
        "- 또는 OPENAI_API_KEY 환경변수 설정"
    )


def build_prompt(content: str, existing_categories: list[str] | None = None) -> str:
    cats = existing_categories or ["기술", "뉴스", "쇼핑", "참고자료", "엔터테인먼트"]
    cat_list = ", ".join(cats)
    return f"""다음 웹 페이지 내용을 분석해서 JSON만 응답해줘 (다른 텍스트 없이):
- summary: 2-3문장 한글 요약
- category: 기존 카테고리 [{cat_list}] 중 하나, 없으면 새 카테고리명
- tags: 관련 태그 3-5개 (한글)

내용:
{content}"""


def parse_response(response: str) -> AnalysisResult | None:
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


def _call_claude(prompt: str) -> str | None:
    try:
        result = subprocess.run(
            ["claude", "-p"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
            shell=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            return result.stdout
        logger.warning("claude -p 실패: %s", result.stderr[:200])
    except subprocess.TimeoutExpired:
        logger.warning("claude -p 타임아웃")
    except Exception as e:
        logger.warning("claude -p 에러: %s", e)
    return None


def _call_openai(prompt: str) -> str | None:
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai 패키지가 필요합니다: pip install openai")
        return None

    try:
        client = OpenAI()
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning("OpenAI API 에러: %s", e)
        return None


_backend = None


def _get_backend():
    global _backend
    if _backend is None:
        _backend = _detect_backend()
        logger.info("AI 백엔드: %s", _backend)
    return _backend


def analyze_content(content: str, existing_categories: list[str] | None = None) -> AnalysisResult | None:
    prompt = build_prompt(content, existing_categories)
    backend = _get_backend()
    call_fn = _call_claude if backend == "claude" else _call_openai

    for attempt in range(2):
        response = call_fn(prompt)
        if response:
            parsed = parse_response(response)
            if parsed:
                return parsed
            logger.warning("JSON 파싱 실패 (시도 %d): %s", attempt + 1, (response or "")[:200])

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
