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
        db.close()
        return templates.TemplateResponse(request, "index.html", {
            "links": links,
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

    @app.get("/api/categories")
    async def api_categories():
        db = get_db()
        categories = db.get_used_categories()
        db.close()
        return categories

    return app
