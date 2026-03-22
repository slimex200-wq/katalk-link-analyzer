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
    """카톡 링크 분석기 - 나에게 보내기 링크를 분석하고 정리합니다."""
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
