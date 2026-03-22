from pydantic import BaseModel


class AnalysisResult(BaseModel):
    summary: str
    category: str
    tags: list[str]


class LinkRecord(BaseModel):
    id: int | None = None
    url: str
    title: str | None = None
    summary: str | None = None
    category: str | None = None
    tags: list[str] = []
    source_date: str | None = None
    raw_content: str | None = None
