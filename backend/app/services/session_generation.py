from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta, time
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.assignment import TeacherAssignmentEvent
from app.models.enums import (
    ClassSessionStatus,
    TeacherAssignmentMethod,
    TeacherStatus,
)
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


@dataclass(frozen=True)
class TeacherScoreBreakdown:
    weekly_load_minutes: int
    weekly_load_penalty: int
    recent_total_sessions: int
    recent_total_penalty: int
    recent_same_level_sessions: int
    recent_same_level_penalty: int
    recent_same_template_sessions: int
    recent_same_template_penalty: int
    recent_same_slot_sessions: int
    recent_same_slot_penalty: int

    @property
    def total_penalty(self) -> int:
        return (
            self.weekly_load_penalty
            + self.recent_total_penalty
            + self.recent_same_level_penalty
            + self.recent_same_template_penalty
            + self.recent_same_slot_penalty
        )

    def as_dict(self) -> dict[str, int]:
        return {**self.__dict__, "total_penalty": self.total_penalty}


@dataclass(frozen=True)
class TeacherCandidate:
    teacher: TeacherProfile
    eligible: bool
    ineligibility_reason: str | None
    score: int | None
    breakdown: TeacherScoreBreakdown | None


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
            candidate = self._select_teacher(
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
                teacher_id=candidate.teacher.id if candidate else None,
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
            self.db.flush()
            if candidate is not None:
                self._record_assignment(
                    session=session,
                    actor=actor,
                    previous_teacher_id=None,
                    new_teacher_id=candidate.teacher.id,
                    method=TeacherAssignmentMethod.AUTO_GENERATION,
                    score=candidate.score,
                    breakdown=candidate.breakdown,
                    reason="Asignación automática durante la generación semanal",
                )
            sessions_in_week.append(session)
            created.append(session)
            if candidate is None:
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
        self,
        actor: User,
        session_id: int,
        changes: dict[str, object],
        *,
        assignment_method: TeacherAssignmentMethod = TeacherAssignmentMethod.MANUAL,
        assignment_score: int | None = None,
        assignment_breakdown: TeacherScoreBreakdown | None = None,
    ) -> ClassSession:
        item = self.get(actor, session_id)
        if item.status == ClassSessionStatus.CANCELLED.value:
            raise SessionGenerationError("Una sesión cancelada no puede modificarse")
        assignment_reason = self._clean(changes.pop("assignment_reason", None))
        previous_teacher_id = item.teacher_id
        teacher_id = changes.get("teacher_id", item.teacher_id)
        teacher_changed = "teacher_id" in changes and teacher_id != previous_teacher_id
        if (
            teacher_changed
            and assignment_method == TeacherAssignmentMethod.MANUAL
            and assignment_reason is None
        ):
            raise SessionGenerationError("El motivo de reasignación es obligatorio")
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
        if teacher_changed:
            self._record_assignment(
                session=item,
                actor=actor,
                previous_teacher_id=previous_teacher_id,
                new_teacher_id=teacher_id,
                method=assignment_method,
                score=assignment_score,
                breakdown=assignment_breakdown,
                reason=assignment_reason,
            )
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise ClassSessionConflictError("No fue posible actualizar la sesión") from error
        return self.get(actor, item.id)

    def teacher_candidates(
        self, actor: User, session_id: int
    ) -> list[TeacherCandidate]:
        item = self.get(actor, session_id)
        week_start = item.session_date - timedelta(days=item.session_date.weekday())
        week_end = week_start + timedelta(days=6)
        week_sessions = self._sessions_between(
            item.organization_id, week_start, week_end, include_cancelled=False
        )
        recent_sessions = self._sessions_between(
            item.organization_id,
            week_start - timedelta(days=28),
            week_start - timedelta(days=1),
            include_cancelled=False,
        )
        return self._rank_teacher_candidates(
            actor,
            self._teachers(item.organization_id, active_only=False),
            week_sessions,
            recent_sessions,
            item,
            week_start,
            week_end,
        )

    def assign_best_teacher(
        self, actor: User, session_id: int, *, reason: str | None = None
    ) -> ClassSession:
        candidates = self.teacher_candidates(actor, session_id)
        best = next((item for item in candidates if item.eligible), None)
        if best is None:
            raise SessionGenerationError("No hay profesores elegibles para esta sesión")
        return self.update(
            actor,
            session_id,
            {
                "teacher_id": best.teacher.id,
                "assignment_reason": reason or "Asignación de la mejor recomendación",
            },
            assignment_method=TeacherAssignmentMethod.AUTO_RECOMMENDATION,
            assignment_score=best.score,
            assignment_breakdown=best.breakdown,
        )

    def assignment_history(
        self, actor: User, session_id: int
    ) -> list[TeacherAssignmentEvent]:
        item = self.get(actor, session_id)
        return list(
            self.db.scalars(
                select(TeacherAssignmentEvent)
                .where(
                    TeacherAssignmentEvent.organization_id == item.organization_id,
                    TeacherAssignmentEvent.session_id == item.id,
                )
                .order_by(
                    TeacherAssignmentEvent.created_at,
                    TeacherAssignmentEvent.id,
                )
            )
        )

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
    ) -> TeacherCandidate | None:
        proxy = _SessionSlot(
            branch_id=template.branch_id,
            level_id=template.level_id,
            source_template_id=template.id,
            session_date=session_date,
            start_time=template.start_time,
            end_time=template.end_time,
            room_id=template.room_id,
        )
        candidates = self._rank_teacher_candidates(
            actor,
            teachers,
            week_sessions,
            recent_sessions,
            proxy,
            week_start,
            week_end,
        )
        return next((item for item in candidates if item.eligible), None)

    def _rank_teacher_candidates(
        self,
        actor: User,
        teachers: list[TeacherProfile],
        week_sessions: list[ClassSession],
        recent_sessions: list[ClassSession],
        slot: ClassSession | _SessionSlot,
        week_start: date,
        week_end: date,
    ) -> list[TeacherCandidate]:
        candidates: list[TeacherCandidate] = []
        for teacher in teachers:
            reason = self._teacher_ineligibility_reason(
                actor, teacher, slot, week_sessions
            )
            if reason is not None:
                candidates.append(TeacherCandidate(teacher, False, reason, None, None))
                continue
            weekly_minutes = sum(
                self._duration_minutes(item.start_time, item.end_time)
                for item in week_sessions
                if item.teacher_id == teacher.id
                and week_start <= item.session_date <= week_end
                and getattr(slot, "id", None) != item.id
            )
            recent_total = sum(
                1 for item in recent_sessions if item.teacher_id == teacher.id
            )
            repeated_level = sum(
                1
                for item in recent_sessions
                if item.teacher_id == teacher.id and item.level_id == slot.level_id
            )
            repeated_template = sum(
                1
                for item in recent_sessions
                if item.teacher_id == teacher.id
                and item.source_template_id == slot.source_template_id
            )
            repeated_slot = sum(
                1
                for item in recent_sessions
                if item.teacher_id == teacher.id
                and item.session_date.weekday() == slot.session_date.weekday()
                and item.start_time == slot.start_time
            )
            breakdown = TeacherScoreBreakdown(
                weekly_load_minutes=weekly_minutes,
                weekly_load_penalty=round(weekly_minutes * 20 / 60),
                recent_total_sessions=recent_total,
                recent_total_penalty=recent_total * 4,
                recent_same_level_sessions=repeated_level,
                recent_same_level_penalty=repeated_level * 15,
                recent_same_template_sessions=repeated_template,
                recent_same_template_penalty=repeated_template * 35,
                recent_same_slot_sessions=repeated_slot,
                recent_same_slot_penalty=repeated_slot * 10,
            )
            candidates.append(
                TeacherCandidate(
                    teacher,
                    True,
                    None,
                    1000 - breakdown.total_penalty,
                    breakdown,
                )
            )
        return sorted(
            candidates,
            key=lambda item: (
                not item.eligible,
                -(item.score if item.score is not None else -10_000),
                item.teacher.id,
            ),
        )

    def _teacher_is_eligible(
        self,
        actor: User,
        teacher: TeacherProfile,
        slot: ClassSession | _SessionSlot,
        sessions: list[ClassSession],
    ) -> bool:
        return self._teacher_ineligibility_reason(actor, teacher, slot, sessions) is None

    def _teacher_ineligibility_reason(
        self,
        actor: User,
        teacher: TeacherProfile,
        slot: ClassSession | _SessionSlot,
        sessions: list[ClassSession],
    ) -> str | None:
        if teacher.status != TeacherStatus.ACTIVE.value:
            return "Profesor inactivo"
        if slot.branch_id not in {item.branch_id for item in teacher.branch_assignments}:
            return "Profesor no asignado a la sucursal"
        if slot.level_id not in {item.level_id for item in teacher.level_assignments}:
            return "Profesor no autorizado para el nivel"
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
                return "Excepción de disponibilidad no permite la sesión"
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
            return "Fuera de la disponibilidad del profesor"
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
            return "El profesor ya tiene otra sesión en ese horario"
        if ScheduleService(self.db).matching_exceptions(
            actor,
            target_date=slot.session_date,
            branch_id=slot.branch_id,
            room_id=slot.room_id,
            teacher_id=teacher.id,
            start_time=slot.start_time,
            end_time=slot.end_time,
        ):
            return "El calendario tiene una excepción para el profesor"
        return None

    def _teachers(
        self, organization_id: int, *, active_only: bool = True
    ) -> list[TeacherProfile]:
        statement = (
            select(TeacherProfile)
            .options(
                selectinload(TeacherProfile.branch_assignments),
                selectinload(TeacherProfile.level_assignments),
                selectinload(TeacherProfile.recurring_availability),
                selectinload(TeacherProfile.availability_exceptions),
            )
            .where(TeacherProfile.organization_id == organization_id)
            .order_by(TeacherProfile.id)
        )
        if active_only:
            statement = statement.where(
                TeacherProfile.status == TeacherStatus.ACTIVE.value
            )
        return list(
            self.db.scalars(statement)
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

    def _record_assignment(
        self,
        *,
        session: ClassSession,
        actor: User,
        previous_teacher_id: int | None,
        new_teacher_id: int | None,
        method: TeacherAssignmentMethod,
        score: int | None,
        breakdown: TeacherScoreBreakdown | None,
        reason: str | None,
    ) -> None:
        self.db.add(
            TeacherAssignmentEvent(
                organization_id=session.organization_id,
                session_id=session.id,
                previous_teacher_id=previous_teacher_id,
                new_teacher_id=new_teacher_id,
                method=method.value,
                score=score,
                score_breakdown=(
                    json.dumps(breakdown.as_dict(), sort_keys=True)
                    if breakdown is not None
                    else None
                ),
                reason=self._clean(reason),
                actor_user_id=actor.id,
            )
        )

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
    source_template_id: int
    session_date: date
    start_time: time
    end_time: time
