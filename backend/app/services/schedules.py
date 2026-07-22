from __future__ import annotations

from datetime import date, time

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.branch import Branch
from app.models.enums import ScheduleExceptionScope, TeacherStatus
from app.models.level import AcademicLevel
from app.models.room import Room
from app.models.schedule import ScheduleException, ScheduleTemplate
from app.models.teacher import TeacherProfile
from app.models.user import User


class ScheduleError(Exception):
    pass


class ScheduleNotFoundError(ScheduleError):
    pass


class ScheduleConflictError(ScheduleError):
    pass


class ScheduleService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_templates(
        self,
        actor: User,
        *,
        branch_id: int | None = None,
        level_id: int | None = None,
        include_inactive: bool = False,
    ) -> list[ScheduleTemplate]:
        statement = (
            select(ScheduleTemplate)
            .options(joinedload(ScheduleTemplate.room), joinedload(ScheduleTemplate.level))
            .where(ScheduleTemplate.organization_id == self._tenant_id(actor))
        )
        if branch_id is not None:
            statement = statement.where(ScheduleTemplate.branch_id == branch_id)
        if level_id is not None:
            statement = statement.where(ScheduleTemplate.level_id == level_id)
        if not include_inactive:
            statement = statement.where(ScheduleTemplate.active.is_(True))
        return list(
            self.db.scalars(
                statement.order_by(
                    ScheduleTemplate.weekday, ScheduleTemplate.start_time
                )
            )
        )

    def get_template(self, actor: User, template_id: int) -> ScheduleTemplate:
        template = self.db.scalar(
            select(ScheduleTemplate)
            .options(joinedload(ScheduleTemplate.room), joinedload(ScheduleTemplate.level))
            .where(
                ScheduleTemplate.id == template_id,
                ScheduleTemplate.organization_id == self._tenant_id(actor),
            )
        )
        if template is None:
            raise ScheduleNotFoundError("Plantilla de horario no encontrada")
        return template

    def create_template(
        self, actor: User, data: dict[str, object]
    ) -> ScheduleTemplate:
        organization_id = self._tenant_id(actor)
        values = dict(data)
        values["name"] = self._required(values["name"], "El nombre es obligatorio")
        values["notes"] = self._clean(values.get("notes"))
        self._validate_template_values(organization_id, values)
        self._assert_no_template_conflict(organization_id, values)
        template = ScheduleTemplate(
            organization_id=organization_id,
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
            active=True,
            **values,
        )
        self.db.add(template)
        self._commit("No fue posible crear la plantilla")
        return self.get_template(actor, template.id)

    def update_template(
        self, actor: User, template_id: int, changes: dict[str, object]
    ) -> ScheduleTemplate:
        template = self.get_template(actor, template_id)
        required = {
            "name", "branch_id", "room_id", "level_id", "weekday",
            "start_time", "end_time", "effective_from", "active",
        }
        if any(changes.get(field) is None for field in required if field in changes):
            raise ScheduleError("Los campos obligatorios no pueden quedar vacíos")
        values = {
            "name": template.name,
            "branch_id": template.branch_id,
            "room_id": template.room_id,
            "level_id": template.level_id,
            "weekday": template.weekday,
            "start_time": template.start_time,
            "end_time": template.end_time,
            "configured_capacity": template.configured_capacity,
            "effective_from": template.effective_from,
            "effective_until": template.effective_until,
            "notes": template.notes,
            "active": template.active,
        }
        values.update(changes)
        values["name"] = self._required(values["name"], "El nombre es obligatorio")
        values["notes"] = self._clean(values.get("notes"))
        self._validate_template_values(template.organization_id, values)
        if values["active"]:
            self._assert_no_template_conflict(
                template.organization_id, values, exclude_id=template.id
            )
        for field, value in values.items():
            setattr(template, field, value)
        template.updated_by_user_id = actor.id
        self._commit("No fue posible actualizar la plantilla")
        return self.get_template(actor, template.id)

    def deactivate_template(self, actor: User, template_id: int) -> None:
        self.update_template(actor, template_id, {"active": False})

    def list_exceptions(
        self,
        actor: User,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        include_inactive: bool = False,
    ) -> list[ScheduleException]:
        if date_from is not None and date_to is not None and date_to < date_from:
            raise ScheduleError("La fecha final no puede ser anterior a la inicial")
        statement = select(ScheduleException).where(
            ScheduleException.organization_id == self._tenant_id(actor)
        )
        if date_from is not None:
            statement = statement.where(ScheduleException.exception_date >= date_from)
        if date_to is not None:
            statement = statement.where(ScheduleException.exception_date <= date_to)
        if not include_inactive:
            statement = statement.where(ScheduleException.active.is_(True))
        return list(
            self.db.scalars(
                statement.order_by(
                    ScheduleException.exception_date, ScheduleException.start_time
                )
            )
        )

    def get_exception(self, actor: User, exception_id: int) -> ScheduleException:
        item = self.db.scalar(
            select(ScheduleException).where(
                ScheduleException.id == exception_id,
                ScheduleException.organization_id == self._tenant_id(actor),
            )
        )
        if item is None:
            raise ScheduleNotFoundError("Excepción de calendario no encontrada")
        return item

    def matching_exceptions(
        self,
        actor: User,
        *,
        target_date: date,
        branch_id: int,
        room_id: int,
        teacher_id: int | None,
        start_time: time,
        end_time: time,
    ) -> list[ScheduleException]:
        if end_time <= start_time:
            raise ScheduleError("La hora final debe ser posterior a la inicial")
        candidates = self.db.scalars(
            select(ScheduleException).where(
                ScheduleException.organization_id == self._tenant_id(actor),
                ScheduleException.exception_date == target_date,
                ScheduleException.active.is_(True),
            )
        )
        matches = []
        for item in candidates:
            scope_matches = (
                item.scope == ScheduleExceptionScope.ORGANIZATION.value
                or (
                    item.scope == ScheduleExceptionScope.BRANCH.value
                    and item.branch_id == branch_id
                )
                or (
                    item.scope == ScheduleExceptionScope.ROOM.value
                    and item.branch_id == branch_id
                    and item.room_id == room_id
                )
                or (
                    item.scope == ScheduleExceptionScope.TEACHER.value
                    and teacher_id is not None
                    and item.teacher_id == teacher_id
                )
            )
            if scope_matches and self._times_overlap(
                item.start_time,
                item.end_time,
                start_time,
                end_time,
            ):
                matches.append(item)
        return sorted(matches, key=lambda item: (item.scope, item.id))

    def create_exception(
        self, actor: User, data: dict[str, object]
    ) -> ScheduleException:
        values = dict(data)
        values["scope"] = self._scope_value(values["scope"])
        values["reason"] = self._required(values["reason"], "El motivo es obligatorio")
        organization_id = self._tenant_id(actor)
        self._validate_exception_values(organization_id, values)
        self._assert_no_exception_conflict(organization_id, values)
        item = ScheduleException(
            organization_id=organization_id,
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
            active=True,
            **values,
        )
        self.db.add(item)
        self._commit("No fue posible crear la excepción")
        self.db.refresh(item)
        return item

    def update_exception(
        self, actor: User, exception_id: int, changes: dict[str, object]
    ) -> ScheduleException:
        item = self.get_exception(actor, exception_id)
        required = {"exception_date", "scope", "reason", "active"}
        if any(changes.get(field) is None for field in required if field in changes):
            raise ScheduleError("Los campos obligatorios no pueden quedar vacíos")
        values = {
            "exception_date": item.exception_date,
            "scope": item.scope,
            "branch_id": item.branch_id,
            "room_id": item.room_id,
            "teacher_id": item.teacher_id,
            "start_time": item.start_time,
            "end_time": item.end_time,
            "reason": item.reason,
            "active": item.active,
        }
        values.update(changes)
        values["scope"] = self._scope_value(values["scope"])
        values["reason"] = self._required(values["reason"], "El motivo es obligatorio")
        self._normalize_scope(values)
        self._validate_exception_values(item.organization_id, values)
        if values["active"]:
            self._assert_no_exception_conflict(
                item.organization_id, values, exclude_id=item.id
            )
        for field, value in values.items():
            setattr(item, field, value)
        item.updated_by_user_id = actor.id
        self._commit("No fue posible actualizar la excepción")
        self.db.refresh(item)
        return item

    def deactivate_exception(self, actor: User, exception_id: int) -> None:
        self.update_exception(actor, exception_id, {"active": False})

    @staticmethod
    def effective_capacity(template: ScheduleTemplate) -> int:
        candidates = [template.room.capacity]
        if template.level.default_capacity is not None:
            candidates.append(template.level.default_capacity)
        if template.configured_capacity is not None:
            candidates.append(template.configured_capacity)
        return min(candidates)

    def _validate_template_values(
        self, organization_id: int, values: dict[str, object]
    ) -> None:
        start = values["start_time"]
        end = values["end_time"]
        if not isinstance(start, time) or not isinstance(end, time) or end <= start:
            raise ScheduleError("La hora final debe ser posterior a la inicial")
        effective_from = values["effective_from"]
        effective_until = values.get("effective_until")
        if effective_until is not None and effective_until < effective_from:
            raise ScheduleError("La vigencia final no puede ser anterior a la inicial")
        branch_id = int(values["branch_id"])
        room = self.db.scalar(
            select(Room).where(
                Room.id == int(values["room_id"]),
                Room.branch_id == branch_id,
                Room.organization_id == organization_id,
                Room.active.is_(True),
            )
        )
        branch = self.db.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.organization_id == organization_id,
                Branch.active.is_(True),
            )
        )
        level = self.db.scalar(
            select(AcademicLevel).where(
                AcademicLevel.id == int(values["level_id"]),
                AcademicLevel.organization_id == organization_id,
                AcademicLevel.active.is_(True),
            )
        )
        if branch is None or room is None or level is None:
            raise ScheduleError("Sucursal, salón o nivel activo no válido")

    def _assert_no_template_conflict(
        self,
        organization_id: int,
        values: dict[str, object],
        *,
        exclude_id: int | None = None,
    ) -> None:
        statement = select(ScheduleTemplate).where(
            ScheduleTemplate.organization_id == organization_id,
            ScheduleTemplate.room_id == int(values["room_id"]),
            ScheduleTemplate.weekday == int(values["weekday"]),
            ScheduleTemplate.active.is_(True),
            ScheduleTemplate.start_time < values["end_time"],
            ScheduleTemplate.end_time > values["start_time"],
        )
        if exclude_id is not None:
            statement = statement.where(ScheduleTemplate.id != exclude_id)
        for existing in self.db.scalars(statement):
            if self._date_ranges_overlap(
                existing.effective_from,
                existing.effective_until,
                values["effective_from"],
                values.get("effective_until"),
            ):
                raise ScheduleConflictError(
                    "El salón ya tiene una plantilla en ese horario y vigencia"
                )

    def _validate_exception_values(
        self, organization_id: int, values: dict[str, object]
    ) -> None:
        self._normalize_scope(values)
        start = values.get("start_time")
        end = values.get("end_time")
        if (start is None) != (end is None) or (
            start is not None and end is not None and end <= start
        ):
            raise ScheduleError("El rango horario de la excepción no es válido")
        scope = values["scope"]
        if scope in {ScheduleExceptionScope.BRANCH.value, ScheduleExceptionScope.ROOM.value}:
            branch = self.db.scalar(
                select(Branch).where(
                    Branch.id == values["branch_id"],
                    Branch.organization_id == organization_id,
                )
            )
            if branch is None:
                raise ScheduleError("Sucursal no válida")
        if scope == ScheduleExceptionScope.ROOM.value:
            room = self.db.scalar(
                select(Room).where(
                    Room.id == values["room_id"],
                    Room.branch_id == values["branch_id"],
                    Room.organization_id == organization_id,
                )
            )
            if room is None:
                raise ScheduleError("Salón no válido para la sucursal")
        if scope == ScheduleExceptionScope.TEACHER.value:
            teacher = self.db.scalar(
                select(TeacherProfile).where(
                    TeacherProfile.id == values["teacher_id"],
                    TeacherProfile.organization_id == organization_id,
                    TeacherProfile.status == TeacherStatus.ACTIVE.value,
                )
            )
            if teacher is None:
                raise ScheduleError("Profesor activo no válido")

    def _assert_no_exception_conflict(
        self,
        organization_id: int,
        values: dict[str, object],
        *,
        exclude_id: int | None = None,
    ) -> None:
        statement = select(ScheduleException).where(
            ScheduleException.organization_id == organization_id,
            ScheduleException.exception_date == values["exception_date"],
            ScheduleException.scope == values["scope"],
            ScheduleException.active.is_(True),
        )
        if exclude_id is not None:
            statement = statement.where(ScheduleException.id != exclude_id)
        target = self._exception_target(values)
        for existing in self.db.scalars(statement):
            if self._exception_target(existing) == target and self._times_overlap(
                existing.start_time,
                existing.end_time,
                values.get("start_time"),
                values.get("end_time"),
            ):
                raise ScheduleConflictError(
                    "Ya existe una excepción superpuesta para el mismo alcance"
                )

    @staticmethod
    def _normalize_scope(values: dict[str, object]) -> None:
        scope = values["scope"]
        if scope == ScheduleExceptionScope.ORGANIZATION.value:
            values.update(branch_id=None, room_id=None, teacher_id=None)
        elif scope == ScheduleExceptionScope.BRANCH.value:
            values.update(room_id=None, teacher_id=None)
            if values.get("branch_id") is None:
                raise ScheduleError("La excepción de sucursal requiere branch_id")
        elif scope == ScheduleExceptionScope.ROOM.value:
            values["teacher_id"] = None
            if values.get("branch_id") is None or values.get("room_id") is None:
                raise ScheduleError("La excepción de salón requiere branch_id y room_id")
        elif scope == ScheduleExceptionScope.TEACHER.value:
            values.update(branch_id=None, room_id=None)
            if values.get("teacher_id") is None:
                raise ScheduleError("La excepción de profesor requiere teacher_id")
        else:
            raise ScheduleError("Alcance de excepción no válido")

    @staticmethod
    def _exception_target(value: object) -> tuple[object, object, object]:
        if isinstance(value, dict):
            return value.get("branch_id"), value.get("room_id"), value.get("teacher_id")
        return value.branch_id, value.room_id, value.teacher_id

    @staticmethod
    def _times_overlap(
        start_a: time | None,
        end_a: time | None,
        start_b: time | None,
        end_b: time | None,
    ) -> bool:
        if start_a is None or start_b is None:
            return True
        return start_a < end_b and end_a > start_b

    @staticmethod
    def _date_ranges_overlap(
        start_a: date,
        end_a: date | None,
        start_b: date,
        end_b: date | None,
    ) -> bool:
        return (end_a is None or end_a >= start_b) and (
            end_b is None or end_b >= start_a
        )

    def _commit(self, message: str) -> None:
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise ScheduleConflictError(message) from error

    @staticmethod
    def _tenant_id(actor: User) -> int:
        if actor.organization_id is None:
            raise ScheduleError("Esta operación requiere contexto de organización")
        return actor.organization_id

    @staticmethod
    def _scope_value(value: object) -> str:
        return value.value if isinstance(value, ScheduleExceptionScope) else str(value)

    @staticmethod
    def _clean(value: object) -> str | None:
        if value is None:
            return None
        result = str(value).strip()
        return result or None

    @staticmethod
    def _required(value: object, message: str) -> str:
        result = str(value).strip()
        if not result:
            raise ScheduleError(message)
        return result
