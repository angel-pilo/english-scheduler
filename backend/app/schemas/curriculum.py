from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import TopicProgressStatus, TopicStatus


class ChapterCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int = Field(ge=0)


class ChapterUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int | None = Field(default=None, ge=0)
    active: bool | None = None


class ChapterOut(BaseModel):
    id: int
    organization_id: int
    level_id: int
    name: str
    description: str | None
    sort_order: int
    active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TopicCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int = Field(ge=0)
    status: TopicStatus = TopicStatus.ACTIVE


class TopicUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int | None = Field(default=None, ge=0)
    status: TopicStatus | None = None


class TopicOut(BaseModel):
    id: int
    organization_id: int
    chapter_id: int
    name: str
    description: str | None
    sort_order: int
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CurriculumChapterOut(ChapterOut):
    topics: list[TopicOut]


class CurriculumLevelOut(BaseModel):
    id: int
    name: str
    description: str | None
    sort_order: int
    default_capacity: int | None
    active: bool
    chapters: list[CurriculumChapterOut]


class LevelAssignmentIn(BaseModel):
    level_id: int
    start_date: date


class StudentLevelHistoryOut(BaseModel):
    id: int
    student_id: int
    level_id: int
    level_name: str
    start_date: date
    end_date: date | None
    is_current: bool
    created_at: datetime


class TopicProgressUpdateIn(BaseModel):
    status: TopicProgressStatus
    observations: str | None = Field(default=None, max_length=4000)


class TopicProgressOut(BaseModel):
    id: int
    student_id: int
    topic_id: int
    topic_name: str
    chapter_id: int
    chapter_name: str
    level_id: int
    status: str
    observations: str | None
    last_taught_at: datetime | None
    completed_at: datetime | None
    updated_by_user_id: int
    updated_at: datetime


class AcademicProgressOut(BaseModel):
    student_id: int
    current_level_id: int | None
    level_history: list[StudentLevelHistoryOut]
    topic_progress: list[TopicProgressOut]
