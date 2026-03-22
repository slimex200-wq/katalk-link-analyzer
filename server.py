import csv
import io
import json
import logging
import threading
from pathlib import Path

from fastapi import FastAPI, Query, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from chat_parser import parse_katalk_export
from crawler import crawl_url
from analyzer import analyze_content
from db import Database

logger = logging.getLogger(__name__)

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

    # 분석 진행 상태
    upload_status = {"running": False, "total": 0, "done": 0, "message": ""}

    def _run_pipeline(text: str):
        """백그라운드에서 파싱 → 크롤링 → 분석 실행"""
        try:
            upload_status["running"] = True
            upload_status["done"] = 0
            upload_status["message"] = "URL 추출 중..."

            parsed = parse_katalk_export(text)
            db = get_db()
            new_links = [p for p in parsed if not db.url_exists(p["url"])]
            upload_status["total"] = len(new_links)

            if not new_links:
                upload_status["message"] = "새로운 링크가 없습니다."
                upload_status["running"] = False
                db.close()
                return

            cats = [c["name"] for c in db.get_used_categories()]
            for i, link_data in enumerate(new_links):
                url = link_data["url"]
                upload_status["message"] = f"({i+1}/{len(new_links)}) 크롤링: {url[:50]}..."

                crawled = crawl_url(url, delay=1.0)
                if not crawled or not crawled.get("text", "").strip():
                    db.insert_link(url=url, source_date=link_data.get("date"))
                    upload_status["done"] = i + 1
                    continue

                upload_status["message"] = f"({i+1}/{len(new_links)}) 분석: {url[:50]}..."
                analysis = analyze_content(crawled["text"], cats)

                if analysis:
                    db.insert_link(
                        url=url,
                        title=crawled.get("title"),
                        summary=analysis.summary,
                        category=analysis.category,
                        tags=analysis.tags,
                        source_date=link_data.get("date"),
                        raw_content=crawled["text"][:5000],
                    )
                    if analysis.category and analysis.category not in cats:
                        cats.append(analysis.category)
                else:
                    db.insert_link(
                        url=url,
                        title=crawled.get("title"),
                        summary="분석 실패",
                        source_date=link_data.get("date"),
                        raw_content=crawled["text"][:5000],
                    )

                upload_status["done"] = i + 1

            db.close()
            upload_status["message"] = f"완료! {len(new_links)}개 링크 처리"
        except Exception as e:
            logger.error("파이프라인 에러: %s", e)
            upload_status["message"] = f"에러: {e}"
        finally:
            upload_status["running"] = False

    @app.post("/api/upload")
    async def api_upload(file: UploadFile = File(...)):
        if upload_status["running"]:
            return JSONResponse(status_code=409, content={"error": "이미 분석이 진행 중입니다."})

        content = await file.read()
        # 여러 인코딩 시도
        text = None
        for enc in ["utf-8", "cp949", "euc-kr", "utf-16"]:
            try:
                text = content.decode(enc)
                break
            except (UnicodeDecodeError, UnicodeError):
                continue

        if text is None:
            return JSONResponse(status_code=400, content={"error": "파일 인코딩을 인식할 수 없습니다."})

        parsed = parse_katalk_export(text)
        if not parsed:
            return JSONResponse(status_code=400, content={"error": "링크를 찾을 수 없습니다. 카카오톡 대화 내보내기 파일인지 확인해주세요."})

        db = get_db()
        new_count = sum(1 for p in parsed if not db.url_exists(p["url"]))
        db.close()

        thread = threading.Thread(target=_run_pipeline, args=(text,), daemon=True)
        thread.start()

        return {"ok": True, "total_links": len(parsed), "new_links": new_count}

    @app.get("/api/upload/status")
    async def api_upload_status():
        return upload_status

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
