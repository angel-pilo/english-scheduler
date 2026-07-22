from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.booking import Booking
from app.models.enums import (
    BookingStatus,
    ClassSessionStatus,
    NotificationType,
    WaitlistStatus,
)
from app.models.schedule import ClassSession
from app.models.user import User
from app.models.waitlist import BookingWaitlist, Notification
from app.services.bookings import (
    BookingError,
    BookingNotFoundError,
    BookingPolicyService,
    BookingService,
)


class WaitlistError(BookingError):
    pass


class WaitlistNotFoundError(WaitlistError):
    pass


class WaitlistConflictError(WaitlistError):
    pass


class WaitlistService:
    ACTIVE_STATUSES = {WaitlistStatus.WAITING.value, WaitlistStatus.OFFERED.value}

    def __init__(self, db: Session) -> None:
        self.db = db

    def join(
        self, user: User, session_id: int, *, now: datetime | None = None
    ) -> BookingWaitlist:
        current = self._now(now)
        booking_service = BookingService(self.db)
        student = booking_service._student_for_user(user)
        session = self.db.scalar(
            booking_service._session_query()
            .where(
                ClassSession.id == session_id,
                ClassSession.organization_id == student.organization_id,
            )
            .with_for_update()
        )
        if session is None:
            raise BookingNotFoundError("Sesión no encontrada")
        self.offer_next_for_session(session_id=session.id, now=current, commit=False)
        existing = self.db.scalar(
            select(BookingWaitlist).where(
                BookingWaitlist.organization_id == student.organization_id,
                BookingWaitlist.session_id == session.id,
                BookingWaitlist.student_id == student.id,
                BookingWaitlist.status.in_(self.ACTIVE_STATUSES),
            )
        )
        if existing is not None:
            raise WaitlistConflictError("El alumno ya está en la lista de espera")
        availability = booking_service._availability(
            student,
            session,
            now=current,
            raise_error=False,
        )
        if availability.unavailable_reason != "La sesión no tiene lugares disponibles":
            raise WaitlistConflictError(
                availability.unavailable_reason
                or "La sesión todavía tiene lugares; puede reservar directamente"
            )
        entry = BookingWaitlist(
            organization_id=student.organization_id,
            session_id=session.id,
            student_id=student.id,
            status=WaitlistStatus.WAITING.value,
            updated_by_user_id=user.id,
        )
        self.db.add(entry)
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise WaitlistConflictError("No fue posible unirse a la lista de espera") from error
        return self.get_for_self(user, entry.id, now=current)

    def list_for_self(
        self, user: User, *, now: datetime | None = None
    ) -> list[BookingWaitlist]:
        current = self._now(now)
        student = BookingService(self.db)._student_for_user(user)
        entries = list(
            self.db.scalars(
                self._base_query()
                .where(
                    BookingWaitlist.organization_id == student.organization_id,
                    BookingWaitlist.student_id == student.id,
                )
                .order_by(BookingWaitlist.created_at.desc(), BookingWaitlist.id.desc())
            )
        )
        for session_id in {item.session_id for item in entries if item.status in self.ACTIVE_STATUSES}:
            self.offer_next_for_session(session_id=session_id, now=current, commit=False)
        self.db.commit()
        return list(
            self.db.scalars(
                self._base_query()
                .where(
                    BookingWaitlist.organization_id == student.organization_id,
                    BookingWaitlist.student_id == student.id,
                )
                .order_by(BookingWaitlist.created_at.desc(), BookingWaitlist.id.desc())
            )
        )

    def get_for_self(
        self, user: User, entry_id: int, *, now: datetime | None = None
    ) -> BookingWaitlist:
        student = BookingService(self.db)._student_for_user(user)
        entry = self.db.scalar(
            self._base_query().where(
                BookingWaitlist.id == entry_id,
                BookingWaitlist.organization_id == student.organization_id,
                BookingWaitlist.student_id == student.id,
            )
        )
        if entry is None:
            raise WaitlistNotFoundError("Entrada de lista de espera no encontrada")
        if entry.status in self.ACTIVE_STATUSES:
            self.offer_next_for_session(
                session_id=entry.session_id,
                now=self._now(now),
                commit=True,
            )
            self.db.refresh(entry)
        return entry

    def leave(
        self, user: User, entry_id: int, *, now: datetime | None = None
    ) -> BookingWaitlist:
        current = self._now(now)
        entry = self.get_for_self(user, entry_id, now=current)
        if entry.status not in self.ACTIVE_STATUSES:
            raise WaitlistConflictError("La entrada ya no está activa")
        was_offered = entry.status == WaitlistStatus.OFFERED.value
        entry.status = WaitlistStatus.LEFT.value
        entry.updated_by_user_id = user.id
        if was_offered:
            self.db.flush()
            self.offer_next_for_session(
                session_id=entry.session_id,
                now=current,
                commit=False,
            )
        self.db.commit()
        return self.get_for_self(user, entry.id, now=current)

    def accept(
        self, user: User, entry_id: int, *, now: datetime | None = None
    ) -> tuple[BookingWaitlist, Booking]:
        current = self._now(now)
        booking_service = BookingService(self.db)
        student = booking_service._student_for_user(user)
        entry = self.db.scalar(
            self._base_query()
            .where(
                BookingWaitlist.id == entry_id,
                BookingWaitlist.organization_id == student.organization_id,
                BookingWaitlist.student_id == student.id,
            )
            .with_for_update()
        )
        if entry is None:
            raise WaitlistNotFoundError("Entrada de lista de espera no encontrada")
        self.offer_next_for_session(
            session_id=entry.session_id,
            now=current,
            commit=False,
        )
        if entry.status != WaitlistStatus.OFFERED.value:
            raise WaitlistConflictError("No existe una oferta activa para aceptar")
        if self._as_utc(entry.offer_expires_at) <= current:
            raise WaitlistConflictError("La oferta ya expiró")
        booking = booking_service._create(
            actor=user,
            student=student,
            session_id=entry.session_id,
            override_rules=False,
            reason="Lugar aceptado desde lista de espera",
            now=current,
            held_waitlist_entry_id=entry.id,
            commit=False,
        )
        entry.status = WaitlistStatus.ACCEPTED.value
        entry.booking_id = booking.id
        entry.updated_by_user_id = user.id
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise WaitlistConflictError("El lugar cambió; intenta nuevamente") from error
        return self.get_for_self(user, entry.id, now=current), booking_service._get(
            user, booking.id, student_id=student.id
        )

    def offer_next_for_session(
        self,
        *,
        session_id: int,
        now: datetime,
        commit: bool,
    ) -> list[BookingWaitlist]:
        session = self.db.scalar(
            select(ClassSession)
            .options(joinedload(ClassSession.branch))
            .where(ClassSession.id == session_id)
            .with_for_update()
        )
        if session is None:
            return []
        organization_id = session.organization_id
        expired = list(
            self.db.scalars(
                self._base_query().where(
                    BookingWaitlist.organization_id == organization_id,
                    BookingWaitlist.session_id == session_id,
                    BookingWaitlist.status == WaitlistStatus.OFFERED.value,
                    BookingWaitlist.offer_expires_at <= now,
                )
            )
        )
        for entry in expired:
            entry.status = WaitlistStatus.EXPIRED.value
            entry.updated_by_user_id = entry.student.user_id
            self._notify_expired(entry)
        self.db.flush()

        session_start = BookingService._session_start(session)
        if (
            session.status != ClassSessionStatus.PUBLISHED.value
            or session_start <= now
        ):
            remaining = list(
                self.db.scalars(
                    self._base_query().where(
                        BookingWaitlist.organization_id == organization_id,
                        BookingWaitlist.session_id == session_id,
                        BookingWaitlist.status.in_(self.ACTIVE_STATUSES),
                    )
                )
            )
            for entry in remaining:
                entry.status = WaitlistStatus.EXPIRED.value
                entry.updated_by_user_id = entry.student.user_id
                if entry.offer_expires_at is not None:
                    self._notify_expired(entry)
            if commit:
                self.db.commit()
            return []

        active_bookings = int(
            self.db.scalar(
                select(func.count(Booking.id)).where(
                    Booking.organization_id == organization_id,
                    Booking.session_id == session_id,
                    Booking.status.in_(
                        {
                            BookingStatus.CONFIRMED.value,
                            BookingStatus.CANCELLATION_PENDING.value,
                        }
                    ),
                )
            )
            or 0
        )
        active_offers = int(
            self.db.scalar(
                select(func.count(BookingWaitlist.id)).where(
                    BookingWaitlist.organization_id == organization_id,
                    BookingWaitlist.session_id == session_id,
                    BookingWaitlist.status == WaitlistStatus.OFFERED.value,
                    BookingWaitlist.offer_expires_at > now,
                )
            )
            or 0
        )
        places = max(session.effective_capacity - active_bookings - active_offers, 0)
        offered: list[BookingWaitlist] = []
        policy = BookingPolicyService(self.db).effective(
            organization_id, session.branch_id
        )
        while places > 0:
            entry = self.db.scalar(
                self._base_query()
                .where(
                    BookingWaitlist.organization_id == organization_id,
                    BookingWaitlist.session_id == session_id,
                    BookingWaitlist.status == WaitlistStatus.WAITING.value,
                )
                .order_by(BookingWaitlist.created_at, BookingWaitlist.id)
                .limit(1)
            )
            if entry is None:
                break
            entry.status = WaitlistStatus.OFFERED.value
            entry.offer_expires_at = min(
                now + timedelta(minutes=policy.waitlist_offer_minutes),
                session_start,
            )
            entry.updated_by_user_id = entry.student.user_id
            self._notify_offer(entry, session)
            offered.append(entry)
            places -= 1
            self.db.flush()
        if commit:
            self.db.commit()
        return offered

    def process_expired(self, actor: User, *, now: datetime | None = None) -> int:
        current = self._now(now)
        organization_id = self._tenant_id(actor)
        session_ids = list(
            self.db.scalars(
                select(BookingWaitlist.session_id)
                .where(
                    BookingWaitlist.organization_id == organization_id,
                    BookingWaitlist.status.in_(self.ACTIVE_STATUSES),
                )
                .distinct()
            )
        )
        for session_id in session_ids:
            self.offer_next_for_session(
                session_id=session_id,
                now=current,
                commit=False,
            )
        self.db.commit()
        return len(session_ids)

    def list_for_admin(
        self,
        actor: User,
        *,
        session_id: int | None = None,
        status: str | None = None,
        now: datetime | None = None,
    ) -> list[BookingWaitlist]:
        organization_id = self._tenant_id(actor)
        self.process_expired(actor, now=now)
        statement = self._base_query().where(
            BookingWaitlist.organization_id == organization_id
        )
        if session_id is not None:
            statement = statement.where(BookingWaitlist.session_id == session_id)
        if status is not None:
            statement = statement.where(BookingWaitlist.status == status)
        return list(
            self.db.scalars(
                statement.order_by(
                    BookingWaitlist.session_id,
                    BookingWaitlist.created_at,
                    BookingWaitlist.id,
                )
            )
        )

    def position(self, entry: BookingWaitlist) -> int | None:
        if entry.status not in self.ACTIVE_STATUSES:
            return None
        ids = list(
            self.db.scalars(
                select(BookingWaitlist.id)
                .where(
                    BookingWaitlist.organization_id == entry.organization_id,
                    BookingWaitlist.session_id == entry.session_id,
                    BookingWaitlist.status.in_(self.ACTIVE_STATUSES),
                )
                .order_by(BookingWaitlist.created_at, BookingWaitlist.id)
            )
        )
        return ids.index(entry.id) + 1 if entry.id in ids else None

    def _notify_offer(self, entry: BookingWaitlist, session: ClassSession) -> None:
        self.db.add(
            Notification(
                organization_id=entry.organization_id,
                user_id=entry.student.user_id,
                notification_type=NotificationType.WAITLIST_PLACE_AVAILABLE.value,
                title="Lugar disponible",
                message=f"Hay un lugar disponible para {session.title}. Confírmalo antes de que venza la oferta.",
                entity_type="booking_waitlist",
                entity_id=entry.id,
            )
        )

    def _notify_expired(self, entry: BookingWaitlist) -> None:
        self.db.add(
            Notification(
                organization_id=entry.organization_id,
                user_id=entry.student.user_id,
                notification_type=NotificationType.WAITLIST_OFFER_EXPIRED.value,
                title="Oferta vencida",
                message="La oferta de la lista de espera venció sin confirmación.",
                entity_type="booking_waitlist",
                entity_id=entry.id,
            )
        )

    @staticmethod
    def _base_query():
        return select(BookingWaitlist).options(
            joinedload(BookingWaitlist.session).joinedload(ClassSession.branch),
            joinedload(BookingWaitlist.student),
        )

    @staticmethod
    def _now(value: datetime | None) -> datetime:
        current = value or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise WaitlistError("La fecha actual debe incluir zona horaria")
        return current.astimezone(timezone.utc)

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime:
        if value is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _tenant_id(actor: User) -> int:
        if actor.organization_id is None:
            raise WaitlistError("Esta operación requiere contexto de organización")
        return actor.organization_id


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, user: User, *, unread_only: bool = False) -> list[Notification]:
        statement = select(Notification).where(
            Notification.organization_id == self._tenant_id(user),
            Notification.user_id == user.id,
        )
        if unread_only:
            statement = statement.where(Notification.read_at.is_(None))
        return list(
            self.db.scalars(
                statement.order_by(Notification.created_at.desc(), Notification.id.desc())
            )
        )

    def mark_read(
        self, user: User, notification_id: int, *, now: datetime | None = None
    ) -> Notification:
        notification = self.db.scalar(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.organization_id == self._tenant_id(user),
                Notification.user_id == user.id,
            )
        )
        if notification is None:
            raise WaitlistNotFoundError("Notificación no encontrada")
        notification.read_at = WaitlistService._now(now)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    @staticmethod
    def _tenant_id(user: User) -> int:
        if user.organization_id is None:
            raise WaitlistError("Esta operación requiere contexto de organización")
        return user.organization_id
