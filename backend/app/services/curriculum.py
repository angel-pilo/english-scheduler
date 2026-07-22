from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.curriculum import (
    CurriculumChapter,
    CurriculumTopic,
    StudentLevelHistory,
    StudentTopicProgress,
)
from app.models.enums import (
    TeacherStatus,
    TopicProgressStatus,
    TopicStatus,
    UserRole,
)
from app.models.level import AcademicLevel
from app.models.student import StudentProfile
from app.models.teacher import TeacherProfile
from app.models.user import User
from app.services.students import StudentError, StudentNotFoundError, StudentService


class CurriculumError(Exception):
    pass


class CurriculumNotFoundError(CurriculumError):
    pass


class CurriculumConflictError(CurriculumError):
    pass


class CurriculumAccessError(CurriculumError):
    pass


class CurriculumService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_curriculum(
        self, actor: User, *, include_inactive: bool = False
    ) -> list[AcademicLevel]:
        statement = (
            select(AcademicLevel)
            .options(
                selectinload(AcademicLevel.chapters).selectinload(
                    CurriculumChapter.topics
                )
            )
            .where(AcademicLevel.organization_id == self._tenant_id(actor))
        )
        if not include_inactive:
            statement = statement.where(AcademicLevel.active.is_(True))
        return list(self.db.scalars(statement.order_by(AcademicLevel.sort_order)))

    def get_chapter(self, actor: User, chapter_id: int) -> CurriculumChapter:
        chapter = self.db.scalar(
            select(CurriculumChapter)
            .options(selectinload(CurriculumChapter.topics))
            .where(
                CurriculumChapter.id == chapter_id,
                CurriculumChapter.organization_id == self._tenant_id(actor),
            )
        )
        if chapter is None:
            raise CurriculumNotFoundError("Capítulo no encontrado")
        return chapter

    def get_topic(self, actor: User, topic_id: int) -> CurriculumTopic:
        topic = self.db.scalar(
            select(CurriculumTopic)
            .options(selectinload(CurriculumTopic.chapter))
            .where(
                CurriculumTopic.id == topic_id,
                CurriculumTopic.organization_id == self._tenant_id(actor),
            )
        )
        if topic is None:
            raise CurriculumNotFoundError("Tema no encontrado")
        return topic

    def create_chapter(
        self, actor: User, level_id: int, data: dict[str, object]
    ) -> CurriculumChapter:
        organization_id = self._tenant_id(actor)
        level = self.db.scalar(
            select(AcademicLevel).where(
                AcademicLevel.id == level_id,
                AcademicLevel.organization_id == organization_id,
            )
        )
        if level is None:
            raise CurriculumNotFoundError("Nivel no encontrado")
        chapter = CurriculumChapter(
            organization_id=organization_id,
            level_id=level.id,
            name=self._required_text(data["name"], "El nombre del capítulo es obligatorio"),
            description=self._clean(data.get("description")),
            sort_order=int(data["sort_order"]),
            active=True,
        )
        self.db.add(chapter)
        self._commit("Ya existe un capítulo con ese nombre u orden")
        self.db.refresh(chapter)
        return chapter

    def update_chapter(
        self, actor: User, chapter_id: int, changes: dict[str, object]
    ) -> CurriculumChapter:
        chapter = self.get_chapter(actor, chapter_id)
        if any(
            changes.get(field) is None
            for field in {"name", "sort_order", "active"}
            if field in changes
        ):
            raise CurriculumError("Los campos obligatorios no pueden quedar vacíos")
        if "name" in changes:
            changes["name"] = self._required_text(
                changes["name"], "El nombre del capítulo es obligatorio"
            )
        if "description" in changes:
            changes["description"] = self._clean(changes["description"])
        for field, value in changes.items():
            setattr(chapter, field, value)
        if changes.get("active") is False:
            for topic in chapter.topics:
                topic.status = TopicStatus.INACTIVE.value
        self._commit("Ya existe un capítulo con ese nombre u orden")
        return self.get_chapter(actor, chapter_id)

    def create_topic(
        self, actor: User, chapter_id: int, data: dict[str, object]
    ) -> CurriculumTopic:
        chapter = self.get_chapter(actor, chapter_id)
        topic = CurriculumTopic(
            organization_id=chapter.organization_id,
            chapter_id=chapter.id,
            name=self._required_text(data["name"], "El nombre del tema es obligatorio"),
            description=self._clean(data.get("description")),
            sort_order=int(data["sort_order"]),
            status=self._enum_value(data.get("status", TopicStatus.ACTIVE)),
        )
        self.db.add(topic)
        self._commit("Ya existe un tema con ese nombre u orden")
        self.db.refresh(topic)
        return topic

    def update_topic(
        self, actor: User, topic_id: int, changes: dict[str, object]
    ) -> CurriculumTopic:
        topic = self.get_topic(actor, topic_id)
        if any(
            changes.get(field) is None
            for field in {"name", "sort_order", "status"}
            if field in changes
        ):
            raise CurriculumError("Los campos obligatorios no pueden quedar vacíos")
        if "name" in changes:
            changes["name"] = self._required_text(
                changes["name"], "El nombre del tema es obligatorio"
            )
        if "description" in changes:
            changes["description"] = self._clean(changes["description"])
        if "status" in changes:
            changes["status"] = self._enum_value(changes["status"])
        for field, value in changes.items():
            setattr(topic, field, value)
        self._commit("Ya existe un tema con ese nombre u orden")
        return self.get_topic(actor, topic_id)

    def deactivate_chapter(self, actor: User, chapter_id: int) -> None:
        self.update_chapter(actor, chapter_id, {"active": False})

    def archive_topic(self, actor: User, topic_id: int) -> None:
        self.update_topic(actor, topic_id, {"status": TopicStatus.ARCHIVED})

    def _commit(self, message: str) -> None:
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise CurriculumConflictError(message) from error

    @staticmethod
    def _tenant_id(actor: User) -> int:
        if actor.organization_id is None:
            raise CurriculumError("Esta operación requiere contexto de organización")
        return actor.organization_id

    @staticmethod
    def _enum_value(value: object) -> str:
        return value.value if hasattr(value, "value") else str(value)

    @staticmethod
    def _clean(value: object) -> str | None:
        if value is None:
            return None
        result = str(value).strip()
        return result or None

    @staticmethod
    def _required_text(value: object, message: str) -> str:
        result = str(value).strip()
        if not result:
            raise CurriculumError(message)
        return result


class AcademicProgressService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def assign_level(
        self, actor: User, student_id: int, *, level_id: int, start_date: date
    ) -> StudentLevelHistory:
        student = self._student(actor, student_id)
        level = self.db.scalar(
            select(AcademicLevel).where(
                AcademicLevel.id == level_id,
                AcademicLevel.organization_id == student.organization_id,
                AcademicLevel.active.is_(True),
            )
        )
        if level is None:
            raise CurriculumNotFoundError("Nivel activo no encontrado")
        history = self.get_history_for_student(student)
        current = next((item for item in history if item.is_current), None)
        if current is not None:
            if current.level_id == level_id:
                raise CurriculumConflictError("El alumno ya se encuentra en este nivel")
            if start_date <= current.start_date:
                raise CurriculumError(
                    "El nuevo nivel debe iniciar después del nivel actual"
                )
            current.is_current = False
            current.end_date = start_date - timedelta(days=1)
        elif history:
            latest_end = max(item.end_date for item in history if item.end_date is not None)
            if start_date <= latest_end:
                raise CurriculumError("La fecha se traslapa con el historial existente")
        enrollment = StudentLevelHistory(
            organization_id=student.organization_id,
            student_id=student.id,
            level_id=level.id,
            start_date=start_date,
            end_date=None,
            is_current=True,
        )
        self.db.add(enrollment)
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise CurriculumConflictError("No fue posible asignar el nivel") from error
        return self._history_by_id(student.organization_id, enrollment.id)

    def get_history(self, actor: User, student_id: int) -> list[StudentLevelHistory]:
        student = self._student(actor, student_id)
        return self.get_history_for_student(student)

    def get_history_for_student(
        self, student: StudentProfile
    ) -> list[StudentLevelHistory]:
        return list(
            self.db.scalars(
                select(StudentLevelHistory)
                .options(selectinload(StudentLevelHistory.level))
                .where(
                    StudentLevelHistory.organization_id == student.organization_id,
                    StudentLevelHistory.student_id == student.id,
                )
                .order_by(StudentLevelHistory.start_date)
            )
        )

    def get_academic_progress(
        self, actor: User, student_id: int
    ) -> tuple[StudentProfile, list[StudentLevelHistory], list[StudentTopicProgress]]:
        student = self._student(actor, student_id)
        self._authorize_progress_actor(actor, student)
        return student, self.get_history_for_student(student), self._progress(student)

    def get_own_academic_progress(
        self, user: User
    ) -> tuple[StudentProfile, list[StudentLevelHistory], list[StudentTopicProgress]]:
        try:
            student = StudentService(self.db).get_self(user)
        except StudentNotFoundError as error:
            raise CurriculumNotFoundError(str(error)) from error
        except StudentError as error:
            raise CurriculumError(str(error)) from error
        return student, self.get_history_for_student(student), self._progress(student)

    def update_topic_progress(
        self,
        actor: User,
        student_id: int,
        topic_id: int,
        *,
        status: TopicProgressStatus,
        observations: str | None,
    ) -> StudentTopicProgress:
        student = self._student(actor, student_id)
        current = self._current_level(student)
        self._authorize_progress_actor(actor, student, current=current)
        topic = self.db.scalar(
            select(CurriculumTopic)
            .options(selectinload(CurriculumTopic.chapter))
            .where(
                CurriculumTopic.id == topic_id,
                CurriculumTopic.organization_id == student.organization_id,
                CurriculumTopic.status == TopicStatus.ACTIVE.value,
            )
        )
        if topic is None:
            raise CurriculumNotFoundError("Tema activo no encontrado")
        if current is None or topic.chapter.level_id != current.level_id:
            raise CurriculumAccessError("El tema no pertenece al nivel actual del alumno")
        progress = self.db.scalar(
            select(StudentTopicProgress).where(
                StudentTopicProgress.student_id == student.id,
                StudentTopicProgress.topic_id == topic.id,
            )
        )
        if progress is None:
            progress = StudentTopicProgress(
                organization_id=student.organization_id,
                student_id=student.id,
                topic_id=topic.id,
                updated_by_user_id=actor.id,
            )
            self.db.add(progress)
        value = status.value
        now = datetime.now(timezone.utc)
        progress.status = value
        progress.observations = CurriculumService._clean(observations)
        progress.updated_by_user_id = actor.id
        progress.last_taught_at = (
            None if value == TopicProgressStatus.NOT_STARTED.value else now
        )
        progress.completed_at = (
            now if value == TopicProgressStatus.COMPLETED.value else None
        )
        self.db.commit()
        return self._progress_by_id(student.organization_id, progress.id)

    def _authorize_progress_actor(
        self,
        actor: User,
        student: StudentProfile,
        *,
        current: StudentLevelHistory | None = None,
    ) -> None:
        if actor.role == UserRole.ADMIN.value:
            return
        if actor.role != UserRole.TEACHER.value:
            raise CurriculumAccessError("No autorizado para consultar este progreso")
        teacher = self.db.scalar(
            select(TeacherProfile)
            .options(
                selectinload(TeacherProfile.branch_assignments),
                selectinload(TeacherProfile.level_assignments),
            )
            .where(
                TeacherProfile.user_id == actor.id,
                TeacherProfile.organization_id == student.organization_id,
                TeacherProfile.status == TeacherStatus.ACTIVE.value,
            )
        )
        current = current or self._current_level(student)
        if (
            teacher is None
            or current is None
            or student.primary_branch_id
            not in {item.branch_id for item in teacher.branch_assignments}
            or current.level_id
            not in {item.level_id for item in teacher.level_assignments}
        ):
            raise CurriculumAccessError(
                "El profesor no está relacionado con la sucursal y nivel del alumno"
            )

    def _current_level(self, student: StudentProfile) -> StudentLevelHistory | None:
        return self.db.scalar(
            select(StudentLevelHistory)
            .options(selectinload(StudentLevelHistory.level))
            .where(
                StudentLevelHistory.organization_id == student.organization_id,
                StudentLevelHistory.student_id == student.id,
                StudentLevelHistory.is_current.is_(True),
            )
        )

    def _student(self, actor: User, student_id: int) -> StudentProfile:
        try:
            return StudentService(self.db).get(actor, student_id)
        except StudentNotFoundError as error:
            raise CurriculumNotFoundError(str(error)) from error
        except StudentError as error:
            raise CurriculumError(str(error)) from error

    def _progress(self, student: StudentProfile) -> list[StudentTopicProgress]:
        return list(
            self.db.scalars(
                select(StudentTopicProgress)
                .options(
                    selectinload(StudentTopicProgress.topic).selectinload(
                        CurriculumTopic.chapter
                    )
                )
                .where(
                    StudentTopicProgress.organization_id == student.organization_id,
                    StudentTopicProgress.student_id == student.id,
                )
                .order_by(StudentTopicProgress.topic_id)
            )
        )

    def _history_by_id(
        self, organization_id: int, history_id: int
    ) -> StudentLevelHistory:
        return self.db.scalar(
            select(StudentLevelHistory)
            .options(selectinload(StudentLevelHistory.level))
            .where(
                StudentLevelHistory.id == history_id,
                StudentLevelHistory.organization_id == organization_id,
            )
        )

    def _progress_by_id(
        self, organization_id: int, progress_id: int
    ) -> StudentTopicProgress:
        return self.db.scalar(
            select(StudentTopicProgress)
            .options(
                selectinload(StudentTopicProgress.topic).selectinload(
                    CurriculumTopic.chapter
                )
            )
            .where(
                StudentTopicProgress.id == progress_id,
                StudentTopicProgress.organization_id == organization_id,
            )
        )
