from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.curriculum import (
    CurriculumChapter,
    CurriculumTopic,
    StudentLevelHistory,
    StudentTopicProgress,
)
from app.models.enums import PermissionCode, UserRole
from app.models.user import User
from app.schemas.curriculum import (
    AcademicProgressOut,
    ChapterCreateIn,
    ChapterOut,
    ChapterUpdateIn,
    CurriculumChapterOut,
    CurriculumLevelOut,
    LevelAssignmentIn,
    StudentLevelHistoryOut,
    TopicCreateIn,
    TopicOut,
    TopicProgressOut,
    TopicProgressUpdateIn,
    TopicUpdateIn,
)
from app.services.curriculum import (
    AcademicProgressService,
    CurriculumAccessError,
    CurriculumConflictError,
    CurriculumError,
    CurriculumNotFoundError,
    CurriculumService,
)


router = APIRouter(tags=["curriculum"])


@router.get("/curriculum", response_model=list[CurriculumLevelOut])
def get_curriculum(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CurriculumLevelOut]:
    show_inactive = include_inactive and user.role == UserRole.ADMIN.value
    levels = CurriculumService(db).list_curriculum(
        user,
        include_inactive=show_inactive,
    )
    return [
        CurriculumLevelOut(
            id=level.id,
            name=level.name,
            description=level.description,
            sort_order=level.sort_order,
            default_capacity=level.default_capacity,
            active=level.active,
            chapters=[
                CurriculumChapterOut(
                    **ChapterOut.model_validate(chapter).model_dump(),
                    topics=[
                        TopicOut.model_validate(topic)
                        for topic in sorted(
                            chapter.topics, key=lambda item: item.sort_order
                        )
                        if show_inactive
                        or topic.status == "ACTIVE"
                    ],
                )
                for chapter in sorted(
                    level.chapters, key=lambda item: item.sort_order
                )
                if show_inactive or chapter.active
            ],
        )
        for level in levels
    ]


@router.post(
    "/admin/levels/{level_id}/chapters",
    response_model=ChapterOut,
    status_code=status.HTTP_201_CREATED,
)
def create_chapter(
    level_id: int,
    payload: ChapterCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.CURRICULUM_MANAGE)),
) -> ChapterOut:
    try:
        return ChapterOut.model_validate(
            CurriculumService(db).create_chapter(actor, level_id, payload.model_dump())
        )
    except CurriculumError as error:
        _raise_curriculum(error)


@router.patch("/admin/chapters/{chapter_id}", response_model=ChapterOut)
def update_chapter(
    chapter_id: int,
    payload: ChapterUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.CURRICULUM_MANAGE)),
) -> ChapterOut:
    try:
        return ChapterOut.model_validate(
            CurriculumService(db).update_chapter(
                actor, chapter_id, payload.model_dump(exclude_unset=True)
            )
        )
    except CurriculumError as error:
        _raise_curriculum(error)


@router.delete("/admin/chapters/{chapter_id}", status_code=204)
def deactivate_chapter(
    chapter_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.CURRICULUM_MANAGE)),
) -> Response:
    try:
        CurriculumService(db).deactivate_chapter(actor, chapter_id)
    except CurriculumError as error:
        _raise_curriculum(error)
    return Response(status_code=204)


@router.post(
    "/admin/chapters/{chapter_id}/topics",
    response_model=TopicOut,
    status_code=status.HTTP_201_CREATED,
)
def create_topic(
    chapter_id: int,
    payload: TopicCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.CURRICULUM_MANAGE)),
) -> TopicOut:
    try:
        return TopicOut.model_validate(
            CurriculumService(db).create_topic(actor, chapter_id, payload.model_dump())
        )
    except CurriculumError as error:
        _raise_curriculum(error)


@router.patch("/admin/topics/{topic_id}", response_model=TopicOut)
def update_topic(
    topic_id: int,
    payload: TopicUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.CURRICULUM_MANAGE)),
) -> TopicOut:
    try:
        return TopicOut.model_validate(
            CurriculumService(db).update_topic(
                actor, topic_id, payload.model_dump(exclude_unset=True)
            )
        )
    except CurriculumError as error:
        _raise_curriculum(error)


@router.delete("/admin/topics/{topic_id}", status_code=204)
def archive_topic(
    topic_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.CURRICULUM_MANAGE)),
) -> Response:
    try:
        CurriculumService(db).archive_topic(actor, topic_id)
    except CurriculumError as error:
        _raise_curriculum(error)
    return Response(status_code=204)


@router.get(
    "/admin/students/{student_id}/level-history",
    response_model=list[StudentLevelHistoryOut],
)
def get_student_level_history(
    student_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.STUDENTS_MANAGE)),
) -> list[StudentLevelHistoryOut]:
    try:
        return [
            _history_out(item)
            for item in AcademicProgressService(db).get_history(actor, student_id)
        ]
    except CurriculumError as error:
        _raise_curriculum(error)


@router.post(
    "/admin/students/{student_id}/levels",
    response_model=StudentLevelHistoryOut,
    status_code=status.HTTP_201_CREATED,
)
def assign_student_level(
    student_id: int,
    payload: LevelAssignmentIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.STUDENTS_MANAGE)),
) -> StudentLevelHistoryOut:
    try:
        item = AcademicProgressService(db).assign_level(
            actor,
            student_id,
            level_id=payload.level_id,
            start_date=payload.start_date,
        )
        return _history_out(item)
    except CurriculumError as error:
        _raise_curriculum(error)


@router.get("/students/me/academic-progress", response_model=AcademicProgressOut)
def get_my_academic_progress(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(PermissionCode.OWN_PROFILE_VIEW)),
) -> AcademicProgressOut:
    try:
        return _academic_progress_out(
            AcademicProgressService(db).get_own_academic_progress(user)
        )
    except CurriculumError as error:
        _raise_curriculum(error)


@router.get(
    "/students/{student_id}/academic-progress",
    response_model=AcademicProgressOut,
)
def get_student_academic_progress(
    student_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(
        require_permission(PermissionCode.STUDENT_PROGRESS_MANAGE)
    ),
) -> AcademicProgressOut:
    try:
        return _academic_progress_out(
            AcademicProgressService(db).get_academic_progress(actor, student_id)
        )
    except CurriculumError as error:
        _raise_curriculum(error)


@router.put(
    "/students/{student_id}/topics/{topic_id}/progress",
    response_model=TopicProgressOut,
)
def update_student_topic_progress(
    student_id: int,
    topic_id: int,
    payload: TopicProgressUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(
        require_permission(PermissionCode.STUDENT_PROGRESS_MANAGE)
    ),
) -> TopicProgressOut:
    try:
        item = AcademicProgressService(db).update_topic_progress(
            actor,
            student_id,
            topic_id,
            status=payload.status,
            observations=payload.observations,
        )
        return _progress_out(item)
    except CurriculumError as error:
        _raise_curriculum(error)


def _history_out(item: StudentLevelHistory) -> StudentLevelHistoryOut:
    return StudentLevelHistoryOut(
        id=item.id,
        student_id=item.student_id,
        level_id=item.level_id,
        level_name=item.level.name,
        start_date=item.start_date,
        end_date=item.end_date,
        is_current=item.is_current,
        created_at=item.created_at,
    )


def _progress_out(item: StudentTopicProgress) -> TopicProgressOut:
    return TopicProgressOut(
        id=item.id,
        student_id=item.student_id,
        topic_id=item.topic_id,
        topic_name=item.topic.name,
        chapter_id=item.topic.chapter_id,
        chapter_name=item.topic.chapter.name,
        level_id=item.topic.chapter.level_id,
        status=item.status,
        observations=item.observations,
        last_taught_at=item.last_taught_at,
        completed_at=item.completed_at,
        updated_by_user_id=item.updated_by_user_id,
        updated_at=item.updated_at,
    )


def _academic_progress_out(data) -> AcademicProgressOut:
    student, history, progress = data
    current = next((item for item in history if item.is_current), None)
    return AcademicProgressOut(
        student_id=student.id,
        current_level_id=current.level_id if current else None,
        level_history=[_history_out(item) for item in history],
        topic_progress=[_progress_out(item) for item in progress],
    )


def _raise_curriculum(error: CurriculumError) -> NoReturn:
    if isinstance(error, CurriculumNotFoundError):
        raise HTTPException(status_code=404, detail=str(error))
    if isinstance(error, CurriculumConflictError):
        raise HTTPException(status_code=409, detail=str(error))
    if isinstance(error, CurriculumAccessError):
        raise HTTPException(status_code=403, detail=str(error))
    raise HTTPException(status_code=400, detail=str(error))
