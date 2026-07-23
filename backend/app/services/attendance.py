from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.attendance import AttendanceEvent, AttendanceRecord
from app.models.booking import Booking
from app.models.enums import (
    AttendanceStatus,
    BookingStatus,
    ClassSessionStatus,
    UserRole,
)
from app.models.schedule import ClassSession
from app.models.teacher import TeacherProfile
from app.models.user import User
from app.services.bookings import BookingService


class AttendanceError(Exception):
    pass


class AttendanceNotFoundError(AttendanceError):
    pass


class AttendanceAccessError(AttendanceError):
    pass


class AttendanceConflictError(AttendanceError):
    pass


@dataclass(frozen=True)
class AttendanceRosterItem:
    booking: Booking
    attendance: AttendanceRecord | None


class AttendanceService:
    ACTIVE_BOOKING_STATUSES = {
        BookingStatus.CONFIRMED.value,
        BookingStatus.CANCELLATION_PENDING.value,
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    def roster(self, actor: User, session_id: int) -> list[AttendanceRosterItem]:
        class_session = self._session(actor, session_id)
        self._authorize(actor, class_session)
        bookings = list(
            self.db.scalars(
                select(Booking)
                .options(joinedload(Booking.student))
                .where(
                    Booking.organization_id == class_session.organization_id,
                    Booking.session_id == class_session.id,
                )
                .order_by(Booking.id)
            )
        )
        records = {
            item.booking_id: item
            for item in self.db.scalars(
                select(AttendanceRecord)
                .options(selectinload(AttendanceRecord.events))
                .where(
                    AttendanceRecord.organization_id == class_session.organization_id,
                    AttendanceRecord.booking_id.in_([item.id for item in bookings]),
                )
            )
        } if bookings else {}
        return [
            AttendanceRosterItem(item, records.get(item.id))
            for item in bookings
            if item.status in self.ACTIVE_BOOKING_STATUSES or item.id in records
        ]

    def save(
        self,
        actor: User,
        session_id: int,
        records: list[dict[str, object]],
        *,
        correction_reason: str | None,
        now: datetime | None = None,
    ) -> list[AttendanceRosterItem]:
        class_session = self.db.scalar(
            self._session_query(actor, session_id).with_for_update()
        )
        if class_session is None:
            raise AttendanceNotFoundError("Sesión no encontrada")
        self._authorize(actor, class_session)
        if class_session.status != ClassSessionStatus.PUBLISHED.value:
            raise AttendanceConflictError("La asistencia requiere una sesión publicada")
        current = self._now(now)
        if BookingService._session_start(class_session) > current:
            raise AttendanceConflictError("La asistencia no puede registrarse antes de iniciar")
        booking_ids = [int(item["booking_id"]) for item in records]
        if len(booking_ids) != len(set(booking_ids)):
            raise AttendanceConflictError("La lista contiene reservaciones duplicadas")
        bookings = {
            item.id: item
            for item in self.db.scalars(
                select(Booking).where(
                    Booking.organization_id == class_session.organization_id,
                    Booking.session_id == class_session.id,
                    Booking.id.in_(booking_ids),
                )
            )
        }
        if set(bookings) != set(booking_ids):
            raise AttendanceNotFoundError("Reservación no encontrada en esta sesión")
        existing = {
            item.booking_id: item
            for item in self.db.scalars(
                select(AttendanceRecord).where(
                    AttendanceRecord.organization_id == class_session.organization_id,
                    AttendanceRecord.booking_id.in_(booking_ids),
                )
            )
        }
        clean_reason = self._clean(correction_reason)
        prepared: list[
            tuple[
                int,
                AttendanceRecord | None,
                dict[str, object],
                dict[str, object] | None,
            ]
        ] = []
        for data in records:
            booking_id = int(data["booking_id"])
            booking = bookings[booking_id]
            record = existing.get(booking_id)
            if record is None and booking.status not in self.ACTIVE_BOOKING_STATUSES:
                raise AttendanceConflictError(
                    "No puede registrarse asistencia para una reservación cancelada"
                )
            values = self._validated_values(data)
            previous = self._snapshot(record) if record is not None else None
            if previous == values:
                continue
            if (
                record is not None
                and record.status != AttendanceStatus.PENDING.value
                and clean_reason is None
            ):
                raise AttendanceConflictError("El motivo de corrección es obligatorio")
            prepared.append((booking_id, record, values, previous))

        for booking_id, record, values, previous in prepared:
            if record is None:
                record = AttendanceRecord(
                    organization_id=class_session.organization_id,
                    booking_id=booking_id,
                    recorded_by_user_id=actor.id,
                    updated_by_user_id=actor.id,
                    **values,
                )
                self.db.add(record)
                self.db.flush()
                existing[booking_id] = record
            else:
                for field, value in values.items():
                    setattr(record, field, value)
                record.updated_by_user_id = actor.id
            record.events.append(
                AttendanceEvent(
                    organization_id=class_session.organization_id,
                    previous_values=json.dumps(previous, sort_keys=True) if previous else None,
                    new_values=json.dumps(values, sort_keys=True),
                    reason=clean_reason,
                    actor_user_id=actor.id,
                )
            )
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise AttendanceConflictError("No fue posible guardar la asistencia") from error
        return self.roster(actor, session_id)

    def history(self, actor: User, session_id: int) -> list[AttendanceEvent]:
        class_session = self._session(actor, session_id)
        self._authorize(actor, class_session)
        return list(
            self.db.scalars(
                select(AttendanceEvent)
                .join(
                    AttendanceRecord,
                    AttendanceRecord.id == AttendanceEvent.attendance_id,
                )
                .join(Booking, Booking.id == AttendanceRecord.booking_id)
                .where(
                    AttendanceEvent.organization_id == class_session.organization_id,
                    Booking.session_id == class_session.id,
                )
                .order_by(AttendanceEvent.created_at, AttendanceEvent.id)
            )
        )

    def _session(self, actor: User, session_id: int) -> ClassSession:
        item = self.db.scalar(self._session_query(actor, session_id))
        if item is None:
            raise AttendanceNotFoundError("Sesión no encontrada")
        return item

    def _session_query(self, actor: User, session_id: int):
        return (
            select(ClassSession)
            .options(joinedload(ClassSession.branch))
            .where(
                ClassSession.id == session_id,
                ClassSession.organization_id == self._tenant_id(actor),
            )
        )

    def _authorize(self, actor: User, class_session: ClassSession) -> None:
        if actor.role == UserRole.ADMIN.value:
            return
        if actor.role != UserRole.TEACHER.value:
            raise AttendanceAccessError("No autorizado para gestionar asistencia")
        teacher_id = self.db.scalar(
            select(TeacherProfile.id).where(
                TeacherProfile.organization_id == class_session.organization_id,
                TeacherProfile.user_id == actor.id,
            )
        )
        if teacher_id is None or teacher_id != class_session.teacher_id:
            raise AttendanceAccessError("El profesor no está asignado a esta sesión")

    def _validated_values(self, data: dict[str, object]) -> dict[str, object]:
        status = data["status"]
        status = status.value if isinstance(status, AttendanceStatus) else str(status)
        if status not in {item.value for item in AttendanceStatus}:
            raise AttendanceError("Estado de asistencia no válido")
        minutes = data.get("minutes_late")
        justification = self._clean(data.get("justification"))
        observations = self._clean(data.get("observations"))
        if status == AttendanceStatus.LATE.value:
            if minutes is None or int(minutes) <= 0:
                raise AttendanceError("Los minutos de retardo son obligatorios")
            minutes = int(minutes)
        elif minutes is not None:
            raise AttendanceError("Los minutos solo aplican al estado LATE")
        if status == AttendanceStatus.JUSTIFIED.value and justification is None:
            raise AttendanceError("La justificación es obligatoria")
        return {
            "status": status,
            "minutes_late": minutes,
            "justification": justification,
            "observations": observations,
        }

    @staticmethod
    def _snapshot(record: AttendanceRecord | None) -> dict[str, object] | None:
        if record is None:
            return None
        return {
            "status": record.status,
            "minutes_late": record.minutes_late,
            "justification": record.justification,
            "observations": record.observations,
        }

    @staticmethod
    def _now(value: datetime | None) -> datetime:
        current = value or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise AttendanceError("La fecha actual debe incluir zona horaria")
        return current.astimezone(timezone.utc)

    @staticmethod
    def _tenant_id(actor: User) -> int:
        if actor.organization_id is None:
            raise AttendanceAccessError("Esta operación requiere contexto de organización")
        return actor.organization_id

    @staticmethod
    def _clean(value: object) -> str | None:
        if value is None:
            return None
        result = str(value).strip()
        return result or None
