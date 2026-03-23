from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# 트래킹/마케팅 파라미터 — 제거 대상
TRACKING_PARAMS = {
    # UTM
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    # Facebook / Meta
    "fbclid", "fb_action_ids", "fb_action_types", "fb_ref", "fb_source",
    # Google
    "gclid", "gclsrc", "dclid", "gbraid", "wbraid",
    # Microsoft
    "msclkid",
    # Twitter / X
    "twclid",
    # HubSpot
    "hsa_cam", "hsa_grp", "hsa_mt", "hsa_src", "hsa_ad", "hsa_acc",
    "hsa_net", "hsa_ver", "hsa_la", "hsa_ol", "hsa_kw",
    # 기타
    "ref", "ref_src", "ref_url", "referrer",
    "mc_cid", "mc_eid",  # Mailchimp
    "oly_enc_id", "oly_anon_id",  # Omeda
    "_hsenc", "_hsmi",  # HubSpot tracking
    "mkt_tok",  # Marketo
    "igshid",  # Instagram
    "s", "si",  # Spotify, YouTube share
}

# m. → www. 로 통합할 도메인 패턴
MOBILE_SUBDOMAIN_DOMAINS = {
    "naver.com", "daum.net", "tistory.com", "youtube.com",
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "reddit.com", "wikipedia.org",
}


def normalize_url(url: str) -> str:
    """URL을 정규화하여 동일 페이지의 변형을 통일합니다.

    - scheme/host 소문자
    - trailing slash 제거
    - 트래킹 파라미터 제거
    - m. 서브도메인 → www 또는 bare domain 통일
    - query param 정렬
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return url

    scheme = parsed.scheme.lower()
    host = parsed.hostname or ""
    host = host.lower()
    port = parsed.port
    path = parsed.path
    fragment = ""  # fragment 제거

    # m. 서브도메인 통일
    if host.startswith("m."):
        bare = host[2:]
        if bare in MOBILE_SUBDOMAIN_DOMAINS or any(bare.endswith("." + d) for d in MOBILE_SUBDOMAIN_DOMAINS):
            host = bare

    # www. 제거하여 bare domain으로 통일
    if host.startswith("www."):
        host = host[4:]

    # trailing slash 제거 (루트 "/" 제외)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # 트래킹 파라미터 제거 + 정렬
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {
        k: v for k, v in query_params.items()
        if k.lower() not in TRACKING_PARAMS
    }
    sorted_query = urlencode(
        [(k, v[0] if len(v) == 1 else v) for k, v in sorted(filtered.items())],
        doseq=True,
    )

    netloc = host
    if port and port not in (80, 443):
        netloc = f"{host}:{port}"

    return urlunparse((scheme, netloc, path, "", sorted_query, fragment))
