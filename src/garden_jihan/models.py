from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class AnalysisMode(StrEnum):
    AUTO = "auto"
    GENERAL = "general"
    SOMALI = "somali"
    ARABIC = "arabic"
    QURAN = "quran"


class SourceInspectRequest(BaseModel):
    url: HttpUrl


class AnalyzeRequest(BaseModel):
    url: HttpUrl | None = None
    upload_id: str | None = None
    mode: AnalysisMode = AnalysisMode.AUTO
    min_clip_seconds: int = Field(default=20, ge=10, le=120)
    max_clip_seconds: int = Field(default=75, ge=15, le=180)
    max_clips: int = Field(default=10, ge=1, le=30)


class ClipCandidate(BaseModel):
    id: str
    start: float
    end: float
    score: float = Field(ge=0, le=100)
    title: str
    reasons: list[str]
    transcript: str
    mode: AnalysisMode
    quran_match: dict | None = None
    score_breakdown: dict[str, float] = Field(default_factory=dict)


class JobPublic(BaseModel):
    id: str
    status: str
    progress: int = Field(ge=0, le=100)
    message: str
    error: str | None = None
    candidates: list[ClipCandidate] = Field(default_factory=list)


class ExportRequest(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=30)
    aspect: str = Field(default="9:16", pattern=r"^(9:16|16:9|1:1)$")
