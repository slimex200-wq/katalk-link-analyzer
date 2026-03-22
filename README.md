# 카톡 링크 분석기

카카오톡 "나에게 보내기"로 저장한 링크들을 AI가 자동으로 크롤링, 요약, 분류해주는 도구.

![Python](https://img.shields.io/badge/python-3.11+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## 기능

- 카카오톡 대화 내보내기(.txt)에서 URL 자동 추출 (PC/모바일 형식 지원)
- 웹 크롤링 (requests + Playwright fallback)
- AI 요약 + 카테고리/태그 자동 분류
- 다크 테마 웹 대시보드
- 즐겨찾기(핀), 카테고리 수정, 검색, 날짜 필터
- JSON/CSV 내보내기

## AI 백엔드

두 가지 중 하나를 사용합니다 (자동 감지):

| 백엔드 | 비용 | 설정 |
|--------|------|------|
| **Claude Code CLI** | 무료 (Pro/Max 구독 시) | [설치](https://docs.anthropic.com/en/docs/claude-code) 후 바로 사용 |
| **OpenAI API** | API 사용량만큼 | `.env`에 `OPENAI_API_KEY` 설정 |

## 설치

```bash
git clone https://github.com/slimex200-wq/katalk-link-analyzer.git
cd katalk-link-analyzer

python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt

# Playwright 브라우저 설치 (JS 렌더링 페이지용)
playwright install chromium
```

### OpenAI 사용 시

```bash
cp .env.example .env
# .env 파일에 OPENAI_API_KEY 설정
```

## 사용법

### 1. 카톡 대화 내보내기

- **PC**: 채팅방 → ☰ → 대화 내보내기 → .txt 저장
- **모바일**: 채팅방 → 설정 → 대화 내보내기

### 2. 링크 분석

```bash
python main.py parse "대화내보내기.txt"

# 옵션
python main.py parse "chat.txt" --max-links 10   # 최대 10개만
python main.py parse "chat.txt" --force           # 기존 링크 재분석
```

### 3. 웹 대시보드

```bash
python main.py serve              # http://localhost:8080
python main.py serve --port 3000  # 포트 변경
```

### 4. 터미널에서 보기

```bash
python main.py list
python main.py list --category 기술
python main.py list --search AI
```

## 웹 대시보드 기능

- 카테고리 필터 (개수 표시)
- 검색 (제목/요약/태그)
- 날짜 범위 필터
- 즐겨찾기 (★) 핀 고정
- 카테고리 클릭 수정
- 링크 삭제
- JSON/CSV 내보내기

## 환경변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `ANALYZER_BACKEND` | AI 백엔드 강제 지정 (`claude` / `openai`) | 자동 감지 |
| `OPENAI_API_KEY` | OpenAI API 키 | - |
| `OPENAI_MODEL` | OpenAI 모델 | `gpt-4o-mini` |

## 기술 스택

- **파서**: Python regex (PC/모바일 카톡 형식)
- **크롤러**: requests + BeautifulSoup, Playwright fallback
- **AI**: Claude Code CLI / OpenAI API
- **DB**: SQLite
- **웹**: FastAPI + Jinja2
- **CLI**: Click

## 라이선스

MIT
