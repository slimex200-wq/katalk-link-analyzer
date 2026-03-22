# KaTalk Link Analyzer - Design Spec

## Overview

카카오톡 "나에게 보내기" 대화 내보내기 파일(.txt)에서 링크를 추출하고, 웹 크롤링 후 Claude CLI로 요약/분류하여 로컬 웹 UI로 결과를 확인하는 CLI 도구.

## Architecture

```
카톡 .txt → Parser → Crawler → Analyzer (claude -p) → SQLite → Web UI (FastAPI)
```

### Components

| 컴포넌트 | 역할 | 기술 |
|----------|------|------|
| Parser | 카톡 .txt에서 URL 추출 | Python regex |
| Crawler | 링크별 본문/메타데이터 수집 | requests + BeautifulSoup (JS 렌더링 필요 시 playwright fallback) |
| Analyzer | 요약 + 카테고리/태그 생성 | claude -p (CLI) |
| Storage | 분석 결과 저장 | SQLite |
| Web UI | 검색/필터/카테고리별 보기 | FastAPI + Jinja2 |
| CLI | 메인 진입점, 파이프라인 실행 | click or argparse |

## Data Model

### links 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| url | TEXT UNIQUE | 원본 URL |
| title | TEXT | 페이지 제목 |
| summary | TEXT | AI 요약 |
| category | TEXT | 카테고리 |
| tags | TEXT (JSON) | 태그 목록 |
| source_date | TEXT | 카톡 메시지 날짜 |
| created_at | TIMESTAMP | 저장 시각 |
| raw_content | TEXT | 크롤링 원문 (선택) |

### categories 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| name | TEXT UNIQUE | 카테고리명 |
| is_default | BOOLEAN | 기본 카테고리 여부 |

기본 카테고리: 기술, 뉴스, 쇼핑, 참고자료, 엔터테인먼트

## Category Strategy

- 기본 카테고리 5개 사전 정의
- AI가 내용 분석 후 기본 카테고리에 매칭
- 맞는 게 없으면 AI가 새 카테고리 자동 생성
- 태그는 항상 AI 자동 생성 (3-5개)

## CLI Interface

```bash
# 링크 추출 + 크롤링 + AI 분석
python main.py parse <chat.txt>

# 웹 UI 실행
python main.py serve [--port 8080]

# 저장된 링크 목록 (터미널)
python main.py list [--category <name>]
```

## KakaoTalk Export Format

PC 카카오톡 대화 내보내기 형식 (예시):
```
2026년 3월 22일 오후 4:27, 나 : https://example.com/article
2026년 3월 22일 오후 4:30, 나 : 이거 나중에 봐야겠다 https://another.com
```

- 날짜/시간 + 발신자 + 메시지 패턴
- URL은 메시지 본문에서 regex로 추출
- 한 메시지에 여러 URL 가능

## Analyzer Prompt

Claude CLI에 전달할 프롬프트:
```
다음 웹 페이지 내용을 분석해서 JSON으로 응답해줘:
- summary: 2-3문장 한글 요약
- category: 기존 카테고리 [기술, 뉴스, 쇼핑, 참고자료, 엔터테인먼트] 중 하나, 없으면 새 카테고리명
- tags: 관련 태그 3-5개 (한글)

내용:
{crawled_content}
```

## Web UI

- 메인 페이지: 전체 링크 목록 (최신순)
- 카테고리 사이드바 필터
- 태그 클릭 필터
- 검색 (제목/요약/태그)
- 각 링크 카드: 제목, 요약, 카테고리 뱃지, 태그, 날짜, 원본 링크

## Crawling Policy

- User-Agent 헤더 설정 (브라우저 UA)
- 요청 간 1-2초 delay (rate limiting)
- JS 렌더링 페이지 (Medium, Velog, Notion 등): requests 실패 시 playwright fallback
- 콘텐츠 길이 제한: 본문 텍스트 최대 5,000자로 truncate (claude -p 토큰 한도 대응)

## Analyzer Reliability

- `claude -p` 병렬 처리: `concurrent.futures.ThreadPoolExecutor(max_workers=3)`
- `--max-links` 옵션으로 한번에 처리할 링크 수 제한 가능
- 진행률 표시 (tqdm)
- JSON 파싱 실패 시: 마크다운 코드블록 제거 후 재파싱 → 실패 시 재시도 1회 → 최종 실패 시 "분석 실패"로 저장
- 응답 검증: Pydantic 모델로 summary/category/tags 구조 확인

## Error Handling

- 크롤링 실패 시: URL과 에러 로깅, 건너뛰기
- claude -p 실패 시: 위 Analyzer Reliability 참조
- 중복 URL: 기존 데이터 유지 (skip), `--force`로 재분석 가능
- 잘못된 URL: 파싱 단계에서 필터링
- 증분 처리: 같은 .txt 재파싱 시 새 URL만 추가 처리

## Project Structure

```
katalk-link-analyzer/
  main.py              # CLI 진입점
  parser.py            # 카톡 .txt 파서
  crawler.py           # 웹 크롤러
  analyzer.py          # Claude CLI 분석기
  db.py                # SQLite 관리
  server.py            # FastAPI 웹 서버
  templates/
    index.html         # 메인 페이지
    components/
      link_card.html   # 링크 카드
  static/
    style.css
  tests/
    test_parser.py
    test_crawler.py
    test_analyzer.py
    test_db.py
  docs/
