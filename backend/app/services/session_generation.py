from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta, time
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.enums import ClassSessionStatus, TeacherStatus
from app.models.room import Room
from app.models.schedule import ClassSession, ScheduleTemplate
from app.models.teacher import TeacherProfile
from app.models.user import User
from app.services.schedules import ScheduleService


class SessionGenerationError(Exception):
    pass


class ClassSessionNotFoundError(SessionGenerationError):
    pass


class ClassSessionConflictError(SessionGenerationError):
    pass


@dataclass(frozen=True)
class GenerationIssue:
    template_id: int
    session_date: date
    reason: str


@dataclass(frozen=True)
class GenerationResult:
    batch_id: str
    week_start: date
    week_end: date
    sessions: list[ClassSession]
    issues: list[GenerationIssue]
    existing_count: int
    blocked_count: int


class ClassSessionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def generate_week(
        self, actor: User, *, week_start: date, branch_id: int | None = None
    ) -> GenerationResult:
        if week_start.weekday() != 0:
            raise SessionGenerationError("week_start debe ser lunes")
        organization_id = self._tenant_id(actor)
        week_end = week_start + timedelta(days=6)
        template_statement = (
            select(ScheduleTemplate)
            .options(
                joinedload(ScheduleTemplate.room),
                joinedload(ScheduleTemplate.level),
            )
            .where(
                ScheduleTemplate.organization_id == organization_id,
                ScheduleTemplate.active.is_(True),
                ScheduleTemplate.effective_from <= week_end,
                (
                    ScheduleTemplate.effective_until.is_(None)
                    | (ScheduleTemplate.effective_until >= week_start)
                ),
            )
            .order_by(ScheduleTemplate.weekday, ScheduleTemplate.start_time)
        )
        if branch_id is not None:
            template_statement = template_statement.where(
                ScheduleTemplate.branch_id == branch_id
            )
        templates = list(self.db.scalars(template_statement))
        sessions_in_week = self._sessions_between(
            organization_id, week_start, week_end, include_cancelled=False
        )
        history_start = week_start - timedelta(days=28)
        recent_sessions = self._sessions_between(
            organization_id, history_start, week_start - timedelta(days=1),
            include_cancelled=False,
        )
        teachers = self._teachers(organization_id)
        batch_id = str(uuid4())
        created: list[ClassSession] = []
        issues: list[GenerationIssue] = []
        existing_count = 0
        blocked_count = 0

        for template in templates:
            session_date = week_start + timedelta(days=template.weekday)
            if session_date < template.effective_from or (
                template.effective_until is not None
                and session_date > template.effective_until
            ):
                continue
            if any(
                item.source_template_id == template.id
                and item.session_date == session_date
                for item in sessions_in_week
            ):
                existing_count += 1
                continue
            if ScheduleService(self.db).matching_exceptions(
                actor,
                target_date=session_date,
                branch_id=template.branch_id,
                room_id=template.room_id,
                teacher_id=None,
                start_time=template.start_time,
                end_time=template.end_time,
            ):
                blocked_count += 1
                issues.append(
                    GenerationIssue(template.id, session_date, "Bloqueada por excepción de calendario")
                )
                continue
            if self._has_room_conflict(
                sessions_in_week,
                session_date,
                template.room_id,
                template.start_time,
                template.end_time,
            ):
                blocked_count += 1
                issues.append(
                    GenerationIssue(template.id, session_date, "Conflicto de salón")
                )
                continue
            teacher = self._select_teacher(
                actor,
                teachers,
                sessions_in_week,
                recent_sessions,
                template,
                session_date,
                week_start,
                week_end,
            )
            configured = (
                template.configured_capacity
                or template.level.default_capacity
                or template.room.capacity
            )
            effective = min(configured, template.room.capacity)
            session = ClassSession(
                organization_id=organization_id,
                source_template_id=template.id,
                generation_batch_id=batch_id,
                branch_id=template.branch_id,
                room_id=template.room_id,
                level_id=template.level_id,
                teacher_id=teacher.id if teacher else None,
                title=template.name,
                session_date=session_date,
                start_time=template.start_time,
                end_time=template.end_time,
                configured_capacity=configured,
                effective_capacity=effective,
                status=ClassSessionStatus.DRAFT.value,
                notes=template.notes,
                created_by_user_id=actor.id,
                updated_by_user_id=actor.id,
            )
            self.db.add(session)
            sessions_in_week.append(session)
            created.append(session)
            if teacher is None:
                issues.append(
                    GenerationIssue(template.id, session_date, "Sin profesor disponible")
                )
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise ClassSessionConflictError(
                "La semana cambió durante la generación; intenta nuevamente"
            ) from error
        return GenerationResult(
            batch_id=batch_id,
            week_start=week_start,
            week_end=week_end,
            sessions=[self.get(actor, item.id) for item in created],
            issues=issues,
            existing_count=existing_count,
            blocked_count=blocked_count,
        )

    def list(
        self,
        actor: User,
        *,
        date_from: date,
        date_to: date,
        branch_id: int | None = None,
        teacher_id: int | None = None,
        status: str | None = None,
    ) -> list[ClassSession]:
        if date_to < date_from:
            raise SessionGenerationError("La fecha final no puede ser anterior a la inicial")
        statement = self._base_query().where(
            ClassSession.organization_id == self._tenant_id(actor),
            ClassSession.session_date >= date_from,
            ClassSession.session_date <= date_to,
        )
        if branch_id is not None:
            statement = statement.where(ClassSession.branch_id == branch_id)
        if teacher_id is not None:
            statement = statement.where(ClassSession.teacher_id == teacher_id)
        if status is not None:
            statement = statement.where(ClassSession.status == status)
        return list(
            self.db.scalars(
                statement.order_by(ClassSession.session_date, ClassSession.start_time)
            )
        )

    def get(self, actor: User, session_id: int) -> ClassSession:
        item = self.db.scalar(
            self._base_query().where(
                ClassSession.id == session_id,
                ClassSession.organization_id == self._tenant_id(actor),
            )
        )
        if item is None:
            raise ClassSessionNotFoundError("Sesión no encontrada")
        return item

    def update(
        self, actor: User, session_id: int, changes: dict[str, object]
    ) -> ClassSession:
        item = self.get(actor, session_id)
        if item.status == ClassSessionStatus.CANCELLED.value:
            raise SessionGenerationError("Una sesión cancelada no puede modificarse")
        teacher_id = changes.get("teacher_id", item.teacher_id)
        room_id = changes.get("room_id", item.room_id)
        configured = changes.get("configured_capacity", item.configured_capacity)
        status = changes.get("status", item.status)
        if room_id is None:
            raise SessionGenerationError("El salón es obligatorio")
        if configured is None:
            raise SessionGenerationError("El cupo configurado es obligatorio")
        if status is None:
            raise SessionGenerationError("El estado es obligatorio")
        status = status.value if isinstance(status, ClassSessionStatus) else str(status)
        if status not in {item.value for item in ClassSessionStatus}:
            raise SessionGenerationError("Estado de sesión no válido")
        room = self.db.scalar(
            select(Room).where(
                Room.id == room_id,
                Room.branch_id == item.branch_id,
                Room.organization_id == item.organization_id,
                Room.active.is_(True),
            )
        )
        if room is None:
            raise SessionGenerationError("Salón activo no válido para la sucursal")
        peers = self._sessions_between(
            item.organization_id, item.session_date, item.session_date,
            include_cancelled=False,
        )
        if self._has_room_conflict(
            peers,
            item.session_date,
            room.id,
            item.start_time,
            item.end_time,
            exclude_id=item.id,
        ):
            raise ClassSessionConflictError("El salón ya está ocupado")
        if teacher_id is not None:
            teacher = self.db.scalar(
                select(TeacherProfile)
                .options(
                    selectinload(TeacherProfile.branch_assignments),
                    selectinload(TeacherProfile.level_assignments),
                    selectinload(TeacherProfile.recurring_availability),
                    selectinload(TeacherProfile.availability_exceptions),
                )
                .where(
                    TeacherProfile.id == teacher_id,
                    TeacherProfile.organization_id == item.organization_id,
                )
            )
            if teacher is None or not self._teacher_is_eligible(
                actor, teacher, item, peers
            ):
                raise SessionGenerationError("Profesor no disponible o no autorizado")
        if status == ClassSessionStatus.PUBLISHED.value and teacher_id is None:
            raise SessionGenerationError("Una sesión publicada requiere profesor")
        if "title" in changes:
            changes["title"] = self._required(changes["title"], "El título es obligatorio")
        if "notes" in changes:
            changes["notes"] = self._clean(changes["notes"])
        item.teacher_id = teacher_id
        item.room_id = room.id
        item.configured_capacity = int(configured)
        item.effective_capacity = min(int(configured), room.capacity)
        item.status = status
        for field in ("title", "notes"):
            if field in changes:
                setattr(item, field, changes[field])
        item.updated_by_user_id = actor.id
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise ClassSessionConflictError("No fue posible actualizar la sesión") from error
        return self.get(actor, item.id)

    def _select_teacher(
        self,
        actor: User,
        teachers: list[TeacherProfile],
        week_sessions: list[ClassSession],
        recent_sessions: list[ClassSession],
        template: ScheduleTemplate,
        session_date: date,
        week_start: date,
        week_end: date,
    ) -> TeacherProfile | None:
        eligible = []
        proxy = _SessionSlot(
            branch_id=template.branch_id,
            level_id=template.level_id,
            session_date=session_date,
            start_time=template.start_time,
            end_time=template.end_time,
            room_id=template.room_id,
        )
        for teacher in teachers:
            if not self._teacher_is_eligible(actor, teacher, proxy, week_sessions):
                continue
            weekly_minutes = sum(
                self._duration_minutes(item.start_time, item.end_time)
                for item in week_sessions
                if item.teacher_id == teacher.id
                and week_start <= item.session_date <= week_end
            )
            repeated_level = sum(
                1
                for item in recent_sessions
                if item.teacher_id == teacher.id and item.level_id == template.level_id
            )
            total_recent = sum(
                1 for item in recent_sessions if item.teacher_id == teacher.id
            )
            eligible.append(
                ((weekly_minutes, repeated_level, total_recent, teacher.id), teacher)
            )
        return min(eligible, key=lambda item: item[0])[1] if eligible else None

    def _teacher_is_eligible(
        self,
        actor: User,
        teacher: TeacherProfile,
        slot: ClassSession | _SessionSlot,
        sessions: list[ClassSession],
    ) -> bool:
        if teacher.status != TeacherStatus.ACTIVE.value:
            return False
        if slot.branch_id not in {item.branch_id for item in teacher.branch_assignments}:
            return False
        if slot.level_id not in {item.level_id for item in teacher.level_assignments}:
            return False
        exception = next(
            (
                item
                for item in teacher.availability_exceptions
                if item.exception_date == slot.session_date
            ),
            None,
        )
        if exception is not None:
            if not exception.is_available:
                return False
            available = (
                exception.start_time <= slot.start_time
                and exception.end_time >= slot.end_time
            )
        else:
            available = any(
                block.weekday == slot.session_date.weekday()
                and block.start_time <= slot.start_time
                and block.end_time >= slot.end_time
                for block in teacher.recurring_availability
            )
        if not available:
            return False
        if any(
            item.teacher_id == teacher.id
            and item.session_date == slot.session_date
            and self._times_overlap(
                item.start_time, item.end_time, slot.start_time, slot.end_time
            )
            and (
                getattr(slot, "id", None) is None
                or getattr(slot, "id", None) != item.id
            )
            for item in sessions
        ):
            return False
        if ScheduleService(self.db).matching_exceptions(
            actor,
            target_date=slot.session_date,
            branch_id=slot.branch_id,
            room_id=slot.room_id,
            teacher_id=teacher.id,
            start_time=slot.start_time,
            end_time=slot.end_time,
        ):
            return False
        return True

    def _teachers(self, organization_id: int) -> list[TeacherProfile]:
        return list(
            self.db.scalars(
                select(TeacherProfile)
                .options(
                    selectinload(TeacherProfile.branch_assignments),
                    selectinload(TeacherProfile.level_assignments),
                    selectinload(TeacherProfile.recurring_availability),
                    selectinload(TeacherProfile.availability_exceptions),
                )
                .where(
                    TeacherProfile.organization_id == organization_id,
                    TeacherProfile.status == TeacherStatus.ACTIVE.value,
                )
                .order_by(TeacherProfile.id)
            )
        )

    def _sessions_between(
        self,
        organization_id: int,
        date_from: date,
        date_to: date,
        *,
        include_cancelled: bool,
    ) -> list[ClassSession]:
        statement = self._base_query().where(
            ClassSession.organization_id == organization_id,
            ClassSession.session_date >= date_from,
            ClassSession.session_date <= date_to,
        )
        if not include_cancelled:
            statement = statement.where(
                ClassSession.status != ClassSessionStatus.CANCELLED.value
            )
        return list(self.db.scalars(statement))

    @staticmethod
    def _has_room_conflict(
        sessions: list[ClassSession],
        session_date: date,
        room_id: int,
        start_time: time,
        end_time: time,
        *,
        exclude_id: int | None = None,
    ) -> bool:
        return any(
            (exclude_id is None or item.id != exclude_id)
            and item.room_id == room_id
            and item.session_date == session_date
            and item.status != ClassSessionStatus.CANCELLED.value
            and ClassSessionService._times_overlap(
                item.start_time, item.end_time, start_time, end_time
            )
            for item in sessions
        )

    @staticmethod
    def _times_overlap(
        start_a: time, end_a: time, start_b: time, end_b: time
    ) -> bool:
        return start_a < end_b and end_a > start_b

    @staticmethod
    def _duration_minutes(start: time, end: time) -> int:
        return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)

    @staticmethod
    def _base_query():
        return select(ClassSession).options(
            joinedload(ClassSession.room),
            joinedload(ClassSession.level),
            joinedload(ClassSession.teacher),
        )

    @staticmethod
    def _tenant_id(actor: User) -> int:
        if actor.organization_id is None:
            raise SessionGenerationError("Esta operación requiere contexto de organización")
        return actor.organization_id

    @staticmethod
    def _clean(value: object) -> str | None:
        if value is None:
            return None
        result = str(value).strip()
        return result or None

    @staticmethod
    def _required(value: object, message: str) -> str:
        if value is None:
            raise SessionGenerationError(message)
        result = str(value).strip()
        if not result:
            raise SessionGenerationError(message)
        return result


@dataclass(frozen=True)
class _SessionSlot:
    branch_id: int
    room_id: int
    level_id: int
    session_date: date
    start_time: time
    end_time: time
