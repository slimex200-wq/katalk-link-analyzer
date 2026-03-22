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


SKIP_DOMAINS = {
    "127.0.0.1", "localhost",
    "docs.google.com", "drive.google.com",
    "mail.google.com", "calendar.google.com",
}

SKIP_PREFIXES = (
    "https://l.threads.com/",  # 리다이렉트 URL
)


def _is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if not (parsed.scheme and parsed.netloc):
            return False
        host = parsed.netloc.split(":")[0]
        if host in SKIP_DOMAINS:
            return False
        if any(url.startswith(p) for p in SKIP_PREFIXES):
            return False
        return True
    except Exception:
        return False
