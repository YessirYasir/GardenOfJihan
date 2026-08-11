from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class AnalysisMode(StrEnum):
    AUTO = "auto"
    GENERAL = "general"
    SOMALI = "somali"
    ARABIC = "arabic"
    QURAN = "quran"


class CaptionStyle(StrEnum):
    GARDEN = "garden"
    HIGH_CONTRAST = "high-contrast"
    MINIMAL = "minimal"


class CaptionPosition(StrEnum):
    BOTTOM = "bottom"
    MIDDLE = "middle"
    TOP = "top"


class SourceInspectRequest(BaseModel):
    url: HttpUrl


class AnalyzeRequest(BaseModel):
    url: HttpUrl | None = None
    upload_id: str | None = None
    mode: AnalysisMode = AnalysisMode.AUTO
    min_clip_seconds: int = Field(default=20, ge=10, le=120)
    max_clip_seconds: int = Field(default=75, ge=15, le=180)
    max_clips: int = Field(default=10, ge=1, le=30)
    project_name: str | None = Field(default=None, max_length=80)


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
    semantic_model: str | None = None


class ClipBoundaryOverride(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_order(self):
        if self.end <= self.start:
            raise ValueError("Clip end must be after start")
        if self.end - self.start > 180:
            raise ValueError("Adjusted clip exceeds three minutes")
        return self


class ProjectReview(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(default="Untitled project", min_length=1, max_length=80)
    selected_ids: list[str] = Field(default_factory=list, max_length=30)
    boundaries: dict[str, ClipBoundaryOverride] = Field(default_factory=dict)
    aspect: str = Field(default="9:16", pattern=r"^(9:16|16:9|1:1)$")
    framing: str = Field(default="auto", pattern=r"^(auto|center|left|right|split-stack)$")
    captions: bool = False
    caption_style: CaptionStyle = CaptionStyle.GARDEN
    caption_position: CaptionPosition = CaptionPosition.BOTTOM


class ProjectReviewRequest(ProjectReview):
    pass


class JobPublic(BaseModel):
    id: str
    status: str
    progress: int = Field(ge=0, le=100)
    message: str
    error: str | None = None
    ranking_method: str = "base"
    ranking_message: str = "Base ranking"
    candidates: list[ClipCandidate] = Field(default_factory=list)
    project: ProjectReview = Field(default_factory=ProjectReview)
    source_available: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ExportRequest(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=30)
    aspect: str = Field(default="9:16", pattern=r"^(9:16|16:9|1:1)$")
    framing: str = Field(default="auto", pattern=r"^(auto|center|left|right|split-stack)$")
    captions: bool = False
    caption_style: CaptionStyle = CaptionStyle.GARDEN
    caption_position: CaptionPosition = CaptionPosition.BOTTOM
    boundaries: dict[str, ClipBoundaryOverride] = Field(default_factory=dict)
