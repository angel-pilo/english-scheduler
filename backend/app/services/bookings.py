from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.booking import Booking, BookingEvent, BookingPolicy, BookingPolicyTimeBlock
from app.models.branch import Branch
from app.models.curriculum import StudentLevelHistory
from app.models.enums import (
    BookingEventType,
    BookingStatus,
    ClassSessionStatus,
    StudentStatus,
)
from app.models.schedule import ClassSession
from app.models.student import StudentProfile
from app.models.user import User
from app.models.waitlist import BookingWaitlist


class BookingError(Exception):
    pass


class BookingNotFoundError(BookingError):
    pass


class BookingConflictError(BookingError):
    pass


@dataclass(frozen=True)
class EffectiveBookingPolicy:
    minimum_booking_notice_hours: int = 24
    minimum_cancellation_notice_hours: int = 24
    earliest_booking_week_offset: int = 1
    latest_booking_week_offset: int = 1
    waitlist_offer_minutes: int = 120
    time_blocks: tuple[BookingPolicyTimeBlock, ...] = ()


@dataclass(frozen=True)
class SessionAvailability:
    session: ClassSession
    confirmed_count: int
    held_count: int
    own_booking_id: int | None
    unavailable_reason: str | None

    @property
    def available_places(self) -> int:
        return max(
            self.session.effective_capacity - self.confirmed_count - self.held_count,
            0,
        )


@dataclass(frozen=True)
class WeeklyUsage:
    week_start: date
    week_end: date
    allowed_minutes: int
    reserved_minutes: int

    @property
    def available_minutes(self) -> int:
        return max(self.allowed_minutes - self.reserved_minutes, 0)


class BookingPolicyService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, actor: User) -> list[BookingPolicy]:
        return list(
            self.db.scalars(
                self._base_query()
                .where(BookingPolicy.organization_id == self._tenant_id(actor))
                .order_by(BookingPolicy.branch_id)
            )
        )

    def upsert(
        self, actor: User, *, branch_id: int | None, data: dict[str, object]
    ) -> BookingPolicy:
        organization_id = self._tenant_id(actor)
        if branch_id is not None:
            branch = self.db.scalar(
                select(Branch).where(
                    Branch.id == branch_id,
                    Branch.organization_id == organization_id,
                    Branch.active.is_(True),
                )
            )
            if branch is None:
                raise BookingError("Sucursal activa no encontrada")
        blocks = list(data.pop("time_blocks", []))
        self._validate_blocks(blocks)
        policy = self.db.scalar(
            self._base_query().where(
                BookingPolicy.organization_id == organization_id,
                BookingPolicy.branch_id == branch_id,
            )
        )
        if policy is None:
            policy = BookingPolicy(
                organization_id=organization_id,
                branch_id=branch_id,
                created_by_user_id=actor.id,
                updated_by_user_id=actor.id,
            )
            self.db.add(policy)
        for field in (
            "minimum_booking_notice_hours",
            "minimum_cancellation_notice_hours",
            "earliest_booking_week_offset",
            "latest_booking_week_offset",
            "waitlist_offer_minutes",
        ):
            value = data.get(field)
            if value is None and field == "waitlist_offer_minutes":
                value = 120
            setattr(policy, field, int(value))
        policy.updated_by_user_id = actor.id
        policy.time_blocks.clear()
        policy.time_blocks.extend(
            BookingPolicyTimeBlock(
                organization_id=organization_id,
                weekday=int(item["weekday"]),
                start_time=item["start_time"],
                end_time=item["end_time"],
            )
            for item in blocks
        )
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise BookingConflictError("No fue posible guardar la política") from error
        return self.get(actor, policy.id)

    def get(self, actor: User, policy_id: int) -> BookingPolicy:
        policy = self.db.scalar(
            self._base_query().where(
                BookingPolicy.id == policy_id,
                BookingPolicy.organization_id == self._tenant_id(actor),
            )
        )
        if policy is None:
            raise BookingNotFoundError("Política de reservación no encontrada")
        return policy

    def effective(self, organization_id: int, branch_id: int) -> EffectiveBookingPolicy:
        policy = self.db.scalar(
            self._base_query()
            .where(
                BookingPolicy.organization_id == organization_id,
                BookingPolicy.branch_id == branch_id,
            )
        )
        if policy is None:
            policy = self.db.scalar(
                self._base_query().where(
                    BookingPolicy.organization_id == organization_id,
                    BookingPolicy.branch_id.is_(None),
                )
            )
        if policy is None:
            return EffectiveBookingPolicy()
        return EffectiveBookingPolicy(
            minimum_booking_notice_hours=policy.minimum_booking_notice_hours,
            minimum_cancellation_notice_hours=policy.minimum_cancellation_notice_hours,
            earliest_booking_week_offset=policy.earliest_booking_week_offset,
            latest_booking_week_offset=policy.latest_booking_week_offset,
            waitlist_offer_minutes=policy.waitlist_offer_minutes,
            time_blocks=tuple(policy.time_blocks),
        )

    @staticmethod
    def _validate_blocks(blocks: list[dict[str, object]]) -> None:
        ordered = sorted(
            blocks, key=lambda item: (int(item["weekday"]), item["start_time"])
        )
        for current, following in zip(ordered, ordered[1:]):
            if (
                current["weekday"] == following["weekday"]
                and current["end_time"] > following["start_time"]
            ):
                raise BookingConflictError("Las ventanas de reservación no pueden traslaparse")

    @staticmethod
    def _base_query():
        return select(BookingPolicy).options(selectinload(BookingPolicy.time_blocks))

    @staticmethod
    def _tenant_id(actor: User) -> int:
        if actor.organization_id is None:
            raise BookingError("Esta operación requiere contexto de organización")
        return actor.organization_id


class BookingService:
    ACTIVE_STATUSES = {
        BookingStatus.CONFIRMED.value,
        BookingStatus.CANCELLATION_PENDING.value,
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    def available_sessions(
        self,
        user: User,
        *,
        date_from: date,
        date_to: date,
        now: datetime | None = None,
    ) -> list[SessionAvailability]:
        if date_to < date_from:
            raise BookingError("La fecha final no puede ser anterior a la inicial")
        student = self._student_for_user(user)
        level_id = self._current_level_id(student)
        if level_id is None:
            return []
        statement = self._session_query().where(
            ClassSession.organization_id == student.organization_id,
            ClassSession.level_id == level_id,
            ClassSession.session_date >= date_from,
            ClassSession.session_date <= date_to,
            ClassSession.status == ClassSessionStatus.PUBLISHED.value,
        )
        if not student.can_book_other_branches:
            statement = statement.where(ClassSession.branch_id == student.primary_branch_id)
        sessions = list(
            self.db.scalars(
                statement.order_by(ClassSession.session_date, ClassSession.start_time)
            )
        )
        return [
            self._availability(student, item, now=self._now(now), raise_error=False)
            for item in sessions
        ]

    def create_for_self(
        self, user: User, session_id: int, *, now: datetime | None = None
    ) -> Booking:
        return self._create(
            actor=user,
            student=self._student_for_user(user),
            session_id=session_id,
            override_rules=False,
            reason=None,
            now=self._now(now),
        )

    def create_for_admin(
        self,
        actor: User,
        *,
        student_id: int,
        session_id: int,
        override_rules: bool,
        reason: str | None,
        now: datetime | None = None,
    ) -> Booking:
        if override_rules and not self._clean(reason):
            raise BookingError("El motivo es obligatorio al ignorar reglas")
        student = self._student(actor, student_id)
        return self._create(
            actor=actor,
            student=student,
            session_id=session_id,
            override_rules=override_rules,
            reason=reason,
            now=self._now(now),
        )

    def list_for_self(self, user: User, *, date_from: date, date_to: date) -> list[Booking]:
        student = self._student_for_user(user)
        return self._list(
            student.organization_id,
            date_from=date_from,
            date_to=date_to,
            student_id=student.id,
        )

    def list_for_admin(
        self,
        actor: User,
        *,
        date_from: date,
        date_to: date,
        student_id: int | None = None,
        session_id: int | None = None,
        status: str | None = None,
    ) -> list[Booking]:
        if date_to < date_from:
            raise BookingError("La fecha final no puede ser anterior a la inicial")
        statement = self._booking_query().where(
            Booking.organization_id == self._tenant_id(actor),
            ClassSession.session_date >= date_from,
            ClassSession.session_date <= date_to,
        )
        if student_id is not None:
            statement = statement.where(Booking.student_id == student_id)
        if session_id is not None:
            statement = statement.where(Booking.session_id == session_id)
        if status is not None:
            statement = statement.where(Booking.status == status)
        return list(
            self.db.scalars(
                statement.order_by(ClassSession.session_date, ClassSession.start_time)
            )
        )

    def cancel_for_self(
        self,
        user: User,
        booking_id: int,
        *,
        reason: str | None,
        now: datetime | None = None,
    ) -> Booking:
        student = self._student_for_user(user)
        booking = self._get(user, booking_id, student_id=student.id)
        if booking.status == BookingStatus.CANCELLATION_PENDING.value:
            raise BookingConflictError("La cancelación tardía ya está pendiente")
        if booking.status != BookingStatus.CONFIRMED.value:
            raise BookingConflictError("La reservación ya está cancelada")
        current = self._now(now)
        policy = BookingPolicyService(self.db).effective(
            student.organization_id, booking.session.branch_id
        )
        cutoff = self._session_start(booking.session) - timedelta(
            hours=policy.minimum_cancellation_notice_hours
        )
        if current <= cutoff:
            self._transition(
                booking,
                actor=user,
                new_status=BookingStatus.CANCELLED,
                event_type=BookingEventType.CANCELLED,
                reason=reason,
                quota_released=True,
                now=current,
            )
            self._offer_waitlist_place(booking.session_id, current)
        else:
            self._transition(
                booking,
                actor=user,
                new_status=BookingStatus.CANCELLATION_PENDING,
                event_type=BookingEventType.LATE_CANCELLATION_REQUESTED,
                reason=reason,
                quota_released=False,
                now=current,
            )
        self.db.commit()
        return self._get(user, booking.id, student_id=student.id)

    def review_late_cancellation(
        self,
        actor: User,
        booking_id: int,
        *,
        approve: bool,
        reason: str,
        release_quota: bool,
        now: datetime | None = None,
    ) -> Booking:
        booking = self._get(actor, booking_id)
        if booking.status != BookingStatus.CANCELLATION_PENDING.value:
            raise BookingConflictError("La reservación no tiene una solicitud pendiente")
        if approve:
            self._transition(
                booking,
                actor=actor,
                new_status=BookingStatus.CANCELLED,
                event_type=BookingEventType.LATE_CANCELLATION_APPROVED,
                reason=reason,
                quota_released=release_quota,
                now=self._now(now),
            )
            self._offer_waitlist_place(booking.session_id, self._now(now))
        else:
            self._transition(
                booking,
                actor=actor,
                new_status=BookingStatus.CONFIRMED,
                event_type=BookingEventType.LATE_CANCELLATION_REJECTED,
                reason=reason,
                quota_released=False,
                now=self._now(now),
            )
        self.db.commit()
        return self._get(actor, booking.id)

    def cancel_for_admin(
        self,
        actor: User,
        booking_id: int,
        *,
        reason: str,
        release_quota: bool,
        now: datetime | None = None,
    ) -> Booking:
        booking = self._get(actor, booking_id)
        if booking.status == BookingStatus.CANCELLED.value:
            raise BookingConflictError("La reservación ya está cancelada")
        self._transition(
            booking,
            actor=actor,
            new_status=BookingStatus.CANCELLED,
            event_type=BookingEventType.ADMIN_CANCELLED,
            reason=reason,
            quota_released=release_quota,
            now=self._now(now),
        )
        self._offer_waitlist_place(booking.session_id, self._now(now))
        self.db.commit()
        return self._get(actor, booking.id)

    def history(self, actor: User, booking_id: int, *, own: bool = False) -> list[BookingEvent]:
        student_id = self._student_for_user(actor).id if own else None
        return list(self._get(actor, booking_id, student_id=student_id).events)

    def weekly_usage(
        self, user: User, *, week_start: date
    ) -> WeeklyUsage:
        if week_start.weekday() != 0:
            raise BookingError("week_start debe ser lunes")
        student = self._student_for_user(user)
        return self._weekly_usage(student, week_start)

    def _create(
        self,
        *,
        actor: User,
        student: StudentProfile,
        session_id: int,
        override_rules: bool,
        reason: str | None,
        now: datetime,
        held_waitlist_entry_id: int | None = None,
        commit: bool = True,
    ) -> Booking:
        session = self.db.scalar(
            self._session_query()
            .where(
                ClassSession.id == session_id,
                ClassSession.organization_id == student.organization_id,
            )
            .with_for_update()
        )
        if session is None:
            raise BookingNotFoundError("Sesión no encontrada")
        if held_waitlist_entry_id is None:
            self._offer_waitlist_place(session.id, now)
        availability = self._availability(
            student,
            session,
            now=now,
            raise_error=not override_rules,
            ignore_policy_rules=override_rules,
            exclude_waitlist_entry_id=held_waitlist_entry_id,
            ignore_booking_timing_rules=held_waitlist_entry_id is not None,
        )
        if availability.own_booking_id is not None:
            raise BookingConflictError("El alumno ya reservó esta sesión")
        if availability.available_places <= 0:
            raise BookingConflictError("La sesión no tiene lugares disponibles")
        booking = Booking(
            organization_id=student.organization_id,
            session_id=session.id,
            student_id=student.id,
            status=BookingStatus.CONFIRMED.value,
            reserved_minutes=self._duration_minutes(session.start_time, session.end_time),
            quota_released=False,
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
        )
        self.db.add(booking)
        self.db.flush()
        self._event(
            booking,
            actor=actor,
            event_type=(
                BookingEventType.ADMIN_CREATED
                if actor.id != student.user_id
                else BookingEventType.CREATED
            ),
            previous_status=None,
            new_status=BookingStatus.CONFIRMED.value,
            reason=reason,
            override_rules=override_rules,
        )
        if not commit:
            return booking
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise BookingConflictError(
                "El cupo o las reservaciones cambiaron; intenta de nuevo"
            ) from error
        return self._get(actor, booking.id)

    def _availability(
        self,
        student: StudentProfile,
        session: ClassSession,
        *,
        now: datetime,
        raise_error: bool,
        ignore_policy_rules: bool = False,
        exclude_waitlist_entry_id: int | None = None,
        ignore_booking_timing_rules: bool = False,
    ) -> SessionAvailability:
        bookings = self._bookings_for_session(session.organization_id, session.id)
        active = [item for item in bookings if item.status in self.ACTIVE_STATUSES]
        offers = self._active_waitlist_offers(
            session.organization_id,
            session.id,
            now,
            exclude_id=exclude_waitlist_entry_id,
        )
        own = next((item for item in active if item.student_id == student.id), None)
        reason = self._unavailable_reason(
            student,
            session,
            active,
            offers,
            now=now,
            ignore_policy_rules=ignore_policy_rules,
            ignore_booking_timing_rules=ignore_booking_timing_rules,
        )
        if raise_error and reason is not None:
            raise BookingConflictError(reason)
        return SessionAvailability(
            session, len(active), len(offers), own.id if own else None, reason
        )

    def _unavailable_reason(
        self,
        student: StudentProfile,
        session: ClassSession,
        active_session_bookings: list[Booking],
        active_offers: list[BookingWaitlist],
        *,
        now: datetime,
        ignore_policy_rules: bool,
        ignore_booking_timing_rules: bool,
    ) -> str | None:
        if student.status != StudentStatus.ACTIVE.value:
            return "El alumno no está activo"
        if session.status != ClassSessionStatus.PUBLISHED.value:
            return "La sesión no está publicada"
        if any(item.student_id == student.id for item in active_session_bookings):
            return "El alumno ya reservó esta sesión"
        if any(item.student_id == student.id for item in active_offers):
            return "El alumno ya tiene una oferta activa para esta sesión"
        if self._has_time_conflict(student, session):
            return "El alumno ya tiene otra clase en ese horario"
        if ignore_policy_rules:
            return (
                "La sesión no tiene lugares disponibles"
                if len(active_session_bookings) + len(active_offers)
                >= session.effective_capacity
                else None
            )
        if student.course_start_date and session.session_date < student.course_start_date:
            return "La sesión es anterior al inicio del curso"
        if student.course_end_date and session.session_date > student.course_end_date:
            return "La sesión es posterior a la vigencia del curso"
        if not student.can_book_other_branches and session.branch_id != student.primary_branch_id:
            return "El alumno solo puede reservar en su sucursal"
        if self._current_level_id(student) != session.level_id:
            return "La sesión no corresponde al nivel actual del alumno"
        policy = BookingPolicyService(self.db).effective(
            student.organization_id, session.branch_id
        )
        local_now = self._local_now(now, session.branch.timezone)
        current_week = local_now.date() - timedelta(days=local_now.weekday())
        session_week = session.session_date - timedelta(days=session.session_date.weekday())
        if not ignore_booking_timing_rules:
            session_start = self._session_start(session)
            if session_start - now < timedelta(hours=policy.minimum_booking_notice_hours):
                return "No se cumple el aviso mínimo para reservar"
            earliest = current_week + timedelta(weeks=policy.earliest_booking_week_offset)
            latest = current_week + timedelta(weeks=policy.latest_booking_week_offset)
            if session_week < earliest or session_week > latest:
                return "La sesión está fuera de las semanas permitidas para reservar"
            if policy.time_blocks and not any(
                block.weekday == local_now.weekday()
                and block.start_time <= local_now.time().replace(tzinfo=None)
                and block.end_time > local_now.time().replace(tzinfo=None)
                for block in policy.time_blocks
            ):
                return "La ventana de reservación está cerrada"
        duration = self._duration_minutes(session.start_time, session.end_time)
        usage = self._weekly_usage(student, session_week)
        if usage.reserved_minutes + duration > usage.allowed_minutes:
            return "La reservación excede el límite semanal de horas"
        if (
            len(active_session_bookings) + len(active_offers)
            >= session.effective_capacity
        ):
            return "La sesión no tiene lugares disponibles"
        return None

    def _weekly_usage(self, student: StudentProfile, week_start: date) -> WeeklyUsage:
        week_end = week_start + timedelta(days=6)
        reserved = self.db.scalar(
            select(func.coalesce(func.sum(Booking.reserved_minutes), 0))
            .join(ClassSession, ClassSession.id == Booking.session_id)
            .where(
                Booking.organization_id == student.organization_id,
                Booking.student_id == student.id,
                ClassSession.session_date >= week_start,
                ClassSession.session_date <= week_end,
                or_(
                    Booking.status.in_(self.ACTIVE_STATUSES),
                    (Booking.status == BookingStatus.CANCELLED.value)
                    & Booking.quota_released.is_(False),
                ),
            )
        )
        allowed = int(Decimal(student.weekly_hours_limit) * 60)
        return WeeklyUsage(week_start, week_end, allowed, int(reserved or 0))

    def _has_time_conflict(self, student: StudentProfile, session: ClassSession) -> bool:
        return bool(
            self.db.scalar(
                select(Booking.id)
                .join(ClassSession, ClassSession.id == Booking.session_id)
                .where(
                    Booking.organization_id == student.organization_id,
                    Booking.student_id == student.id,
                    Booking.status.in_(self.ACTIVE_STATUSES),
                    ClassSession.session_date == session.session_date,
                    ClassSession.start_time < session.end_time,
                    ClassSession.end_time > session.start_time,
                    ClassSession.id != session.id,
                )
                .limit(1)
            )
        )

    def _get(
        self, actor: User, booking_id: int, *, student_id: int | None = None
    ) -> Booking:
        statement = self._booking_query().where(
            Booking.id == booking_id,
            Booking.organization_id == self._tenant_id(actor),
        )
        if student_id is not None:
            statement = statement.where(Booking.student_id == student_id)
        booking = self.db.scalar(statement)
        if booking is None:
            raise BookingNotFoundError("Reservación no encontrada")
        return booking

    def _list(
        self,
        organization_id: int,
        *,
        date_from: date,
        date_to: date,
        student_id: int,
    ) -> list[Booking]:
        if date_to < date_from:
            raise BookingError("La fecha final no puede ser anterior a la inicial")
        return list(
            self.db.scalars(
                self._booking_query()
                .where(
                    Booking.organization_id == organization_id,
                    Booking.student_id == student_id,
                    ClassSession.session_date >= date_from,
                    ClassSession.session_date <= date_to,
                )
                .order_by(ClassSession.session_date, ClassSession.start_time)
            )
        )

    def _bookings_for_session(self, organization_id: int, session_id: int) -> list[Booking]:
        return list(
            self.db.scalars(
                select(Booking).where(
                    Booking.organization_id == organization_id,
                    Booking.session_id == session_id,
                )
            )
        )

    def _active_waitlist_offers(
        self,
        organization_id: int,
        session_id: int,
        now: datetime,
        *,
        exclude_id: int | None = None,
    ) -> list[BookingWaitlist]:
        statement = select(BookingWaitlist).where(
            BookingWaitlist.organization_id == organization_id,
            BookingWaitlist.session_id == session_id,
            BookingWaitlist.status == "OFFERED",
            BookingWaitlist.offer_expires_at > now,
        )
        if exclude_id is not None:
            statement = statement.where(BookingWaitlist.id != exclude_id)
        return list(self.db.scalars(statement))

    def _offer_waitlist_place(self, session_id: int, now: datetime) -> None:
        from app.services.waitlists import WaitlistService

        WaitlistService(self.db).offer_next_for_session(
            session_id=session_id,
            now=now,
            commit=False,
        )

    def _transition(
        self,
        booking: Booking,
        *,
        actor: User,
        new_status: BookingStatus,
        event_type: BookingEventType,
        reason: str | None,
        quota_released: bool,
        now: datetime,
    ) -> None:
        previous = booking.status
        booking.status = new_status.value
        booking.quota_released = quota_released
        booking.cancelled_at = now if new_status == BookingStatus.CANCELLED else None
        booking.updated_by_user_id = actor.id
        self._event(
            booking,
            actor=actor,
            event_type=event_type,
            previous_status=previous,
            new_status=new_status.value,
            reason=reason,
            override_rules=actor.id != booking.student.user_id,
        )

    def _event(
        self,
        booking: Booking,
        *,
        actor: User,
        event_type: BookingEventType,
        previous_status: str | None,
        new_status: str,
        reason: str | None,
        override_rules: bool,
    ) -> None:
        booking.events.append(
            BookingEvent(
                organization_id=booking.organization_id,
                actor_user_id=actor.id,
                event_type=event_type.value,
                previous_status=previous_status,
                new_status=new_status,
                reason=self._clean(reason),
                override_rules=override_rules,
            )
        )

    def _student_for_user(self, user: User) -> StudentProfile:
        if user.organization_id is None:
            raise BookingNotFoundError("Perfil de alumno no encontrado")
        student = self.db.scalar(
            select(StudentProfile).where(
                StudentProfile.user_id == user.id,
                StudentProfile.organization_id == user.organization_id,
            )
        )
        if student is None:
            raise BookingNotFoundError("Perfil de alumno no encontrado")
        return student

    def _student(self, actor: User, student_id: int) -> StudentProfile:
        student = self.db.scalar(
            select(StudentProfile).where(
                StudentProfile.id == student_id,
                StudentProfile.organization_id == self._tenant_id(actor),
            )
        )
        if student is None:
            raise BookingNotFoundError("Alumno no encontrado")
        return student

    def _current_level_id(self, student: StudentProfile) -> int | None:
        return self.db.scalar(
            select(StudentLevelHistory.level_id).where(
                StudentLevelHistory.organization_id == student.organization_id,
                StudentLevelHistory.student_id == student.id,
                StudentLevelHistory.is_current.is_(True),
            )
        )

    @staticmethod
    def _duration_minutes(start: time, end: time) -> int:
        return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)

    @classmethod
    def _session_start(cls, session: ClassSession) -> datetime:
        try:
            zone = ZoneInfo(session.branch.timezone)
        except ZoneInfoNotFoundError as error:
            raise BookingError("Zona horaria de sucursal no válida") from error
        return datetime.combine(session.session_date, session.start_time, tzinfo=zone).astimezone(
            timezone.utc
        )

    @staticmethod
    def _local_now(value: datetime, timezone_name: str) -> datetime:
        try:
            return value.astimezone(ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError as error:
            raise BookingError("Zona horaria de sucursal no válida") from error

    @staticmethod
    def _now(value: datetime | None) -> datetime:
        current = value or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise BookingError("La fecha actual debe incluir zona horaria")
        return current.astimezone(timezone.utc)

    @staticmethod
    def _session_query():
        return select(ClassSession).options(joinedload(ClassSession.branch))

    @staticmethod
    def _booking_query():
        return (
            select(Booking)
            .join(ClassSession, ClassSession.id == Booking.session_id)
            .options(
                joinedload(Booking.session).joinedload(ClassSession.branch),
                joinedload(Booking.student),
                selectinload(Booking.events),
            )
        )

    @staticmethod
    def _tenant_id(actor: User) -> int:
        if actor.organization_id is None:
            raise BookingError("Esta operación requiere contexto de organización")
        return actor.organization_id

    @staticmethod
    def _clean(value: object) -> str | None:
        if value is None:
            return None
        result = str(value).strip()
        return result or None
