import csv
import io
import json
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from db import Database

BASE_DIR = Path(__file__).parent


class CategoryUpdate(BaseModel):
    category: str


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
        date_from: str | None = Query(None),
        date_to: str | None = Query(None),
        pinned: bool = Query(False),
    ):
        db = get_db()
        links = db.get_links(category=category, search=q, date_from=date_from, date_to=date_to, pinned_only=pinned)
        db.close()
        return templates.TemplateResponse(request, "index.html", {
            "links": links,
            "current_category": category,
            "search_query": q or "",
            "date_from": date_from or "",
            "date_to": date_to or "",
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

    @app.delete("/api/links/{link_id}")
    async def api_delete_link(link_id: int):
        db = get_db()
        deleted = db.delete_link(link_id)
        db.close()
        if deleted:
            return {"ok": True}
        return JSONResponse(status_code=404, content={"error": "not found"})

    @app.patch("/api/links/{link_id}/category")
    async def api_update_category(link_id: int, body: CategoryUpdate):
        db = get_db()
        updated = db.update_category(link_id, body.category)
        db.close()
        if updated:
            return {"ok": True, "category": body.category}
        return JSONResponse(status_code=404, content={"error": "not found"})

    @app.post("/api/links/{link_id}/pin")
    async def api_toggle_pin(link_id: int):
        db = get_db()
        result = db.toggle_pin(link_id)
        db.close()
        if result["ok"]:
            return result
        return JSONResponse(status_code=404, content={"error": "not found"})

    @app.get("/api/categories")
    async def api_categories():
        db = get_db()
        categories = db.get_used_categories()
        db.close()
        return categories

    @app.get("/api/export/json")
    async def api_export_json():
        db = get_db()
        links = db.get_links()
        db.close()
        content = json.dumps(links, ensure_ascii=False, indent=2)
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=links.json"},
        )

    @app.get("/api/export/csv")
    async def api_export_csv():
        db = get_db()
        links = db.get_links()
        db.close()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["url", "title", "summary", "category", "tags", "source_date"])
        for link in links:
            tags = ", ".join(link.get("tags", [])) if isinstance(link.get("tags"), list) else link.get("tags", "")
            writer.writerow([link["url"], link.get("title", ""), link.get("summary", ""), link.get("category", ""), tags, link.get("source_date", "")])
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8-sig")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=links.csv"},
        )

    return app
