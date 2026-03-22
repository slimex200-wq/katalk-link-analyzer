import json
import sqlite3
from datetime import datetime, timezone

DEFAULT_CATEGORIES = ["기술", "뉴스", "쇼핑", "참고자료", "엔터테인먼트"]


class Database:
    def __init__(self, db_path: str = "links.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                is_default BOOLEAN DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT,
                summary TEXT,
                category TEXT,
                tags TEXT DEFAULT '[]',
                source_date TEXT,
                created_at TEXT,
                raw_content TEXT
            );
        """)
        for cat in DEFAULT_CATEGORIES:
            self.conn.execute(
                "INSERT OR IGNORE INTO categories (name, is_default) VALUES (?, 1)",
                (cat,),
            )
        self.conn.commit()

    def execute(self, sql, params=()):
        return self.conn.execute(sql, params)

    def insert_link(self, url, title=None, summary=None, category=None, tags=None, source_date=None, raw_content=None):
        try:
            self.conn.execute(
                """INSERT INTO links (url, title, summary, category, tags, source_date, created_at, raw_content)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (url, title, summary, category, json.dumps(tags or [], ensure_ascii=False),
                 source_date, datetime.now(timezone.utc).isoformat(), raw_content),
            )
            if category:
                self.ensure_category(category)
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def upsert_link(self, url, **kwargs):
        fields = {k: v for k, v in kwargs.items() if v is not None}
        if "tags" in fields:
            fields["tags"] = json.dumps(fields["tags"], ensure_ascii=False)
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [url]
        self.conn.execute(f"UPDATE links SET {set_clause} WHERE url = ?", values)
        if "category" in fields:
            self.ensure_category(kwargs["category"])
        self.conn.commit()

    def get_link_by_url(self, url):
        row = self.conn.execute("SELECT * FROM links WHERE url = ?", (url,)).fetchone()
        if row:
            result = dict(row)
            result["tags"] = json.loads(result["tags"]) if result["tags"] else []
            return result
        return None

    def get_links(self, category=None, search=None):
        query = "SELECT * FROM links"
        params = []
        conditions = []
        if category:
            conditions.append("category = ?")
            params.append(category)
        if search:
            conditions.append("(title LIKE ? OR summary LIKE ? OR tags LIKE ?)")
            params.extend([f"%{search}%"] * 3)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC"
        rows = self.conn.execute(query, params).fetchall()
        results = []
        for row in rows:
            r = dict(row)
            r["tags"] = json.loads(r["tags"]) if r["tags"] else []
            results.append(r)
        return results

    def search_links(self, query):
        return self.get_links(search=query)

    def get_categories(self):
        rows = self.conn.execute("SELECT * FROM categories ORDER BY is_default DESC, name").fetchall()
        return [dict(r) for r in rows]

    def get_used_categories(self):
        """링크가 실제로 존재하는 카테고리만 반환"""
        rows = self.conn.execute(
            "SELECT DISTINCT category FROM links WHERE category IS NOT NULL ORDER BY category"
        ).fetchall()
        return [{"name": r["category"]} for r in rows]

    def ensure_category(self, name):
        self.conn.execute("INSERT OR IGNORE INTO categories (name, is_default) VALUES (?, 0)", (name,))
        self.conn.commit()

    def url_exists(self, url):
        return self.conn.execute("SELECT 1 FROM links WHERE url = ?", (url,)).fetchone() is not None

    def close(self):
        self.conn.close()
