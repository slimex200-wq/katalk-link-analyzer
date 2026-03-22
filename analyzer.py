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
