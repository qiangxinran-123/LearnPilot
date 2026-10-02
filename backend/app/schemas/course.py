from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CourseInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    category: str | None = Field(default=None, max_length=120)
    learning_goal: str | None = Field(default=None, max_length=1000)
    target_date: date | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Course name must not be blank.")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return value.strip()

    @field_validator("category", "learning_goal", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class CourseCreate(CourseInput):
    pass


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=120)
    learning_goal: str | None = Field(default=None, max_length=1000)
    target_date: date | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Course name must not be null.")
        normalized = value.strip()
        if not normalized:
            raise ValueError("Course name must not be blank.")
        return normalized

    @field_validator("description", "category", "learning_goal", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class Course(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    category: str | None = None
    learning_goal: str | None = None
    target_date: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    material_count: int = 0
    # M1 compatibility alias; new clients should use category.
    semester: str = ""


class CourseListResponse(BaseModel):
    count: int
    courses: list[Course]


class CourseDeleteResponse(BaseModel):
    id: int
    deleted: bool


class MaterialCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    type: str = Field(min_length=1, max_length=50)
    summary: str = Field(default="", max_length=10000)

    @field_validator("title", "type")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Material value must not be blank.")
        return normalized


class Material(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    title: str
    type: str
    summary: str
    filename: str | None = None
    original_filename: str | None = None
    media_type: str | None = None
    extension: str | None = None
    size_bytes: int = 0
    storage_status: str
    text_preview: str = ""
    text_length: int = 0
    extracted: bool = False
    extraction_status: str
    extraction_error_code: str | None = None
    extraction_error_message: str | None = None
    parser_name: str | None = None
    parser_version: str | None = None
    page_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    ai_summary: str | None = None
    summary_generated: bool | None = None
    summary_method: str | None = None
    summary_updated_at: datetime | None = None
    cards: list[StudyCard] | None = None
    cards_generated: bool | None = None
    cards_generated_at: datetime | None = None
    cards_method: str | None = None


class MaterialListResponse(BaseModel):
    course_id: int
    count: int
    materials: list[Material]


class MaterialSearchResult(Material):
    course_id: int


class MaterialSearchResponse(BaseModel):
    query: str
    course_id: int | None = None
    count: int
    materials: list[MaterialSearchResult]


class MaterialContentResponse(BaseModel):
    material_id: int
    text: str
    offset: int
    limit: int
    total_length: int
    has_more: bool
    page_count: int
    parser_name: str
    parser_version: str


class SummaryContent(BaseModel):
    overview: str
    key_concepts: list[str]
    important_points: list[str]
    common_mistakes: list[str]
    review_suggestions: list[str]
    provider: str
    model: str
    prompt_version: str
    generated_at: datetime
    updated_at: datetime


class MaterialSummaryResponse(BaseModel):
    # id is kept for the M1 endpoint contract and equals material_id.
    id: int
    material_id: int
    summary: SummaryContent | None = None
    ai_summary: str | None = None
    summary_generated: bool = False
    summary_method: str | None = None
    summary_updated_at: datetime | None = None


class StudyCard(BaseModel):
    id: int
    question: str
    answer: str
    knowledge_hint: str | None = None
    source_reference: str | None = None
    order_index: int = 0
    source_material_id: int
    card_type: str = "study"
    created_at: datetime


class CardGenerationResponse(BaseModel):
    material_id: int
    count: int
    cards: list[StudyCard]
    cards_generated: bool
    cards_generated_at: datetime | None = None
    cards_method: str | None = None


class MaterialQARequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Question must not be blank.")
        return normalized


class MaterialQAResponse(BaseModel):
    material_id: int
    answer: str
    references: list[str]
    grounded: bool
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
