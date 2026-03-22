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
