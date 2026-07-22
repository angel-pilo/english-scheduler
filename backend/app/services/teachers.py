from __future__ import annotations

from datetime import time

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.enums import TeacherStatus, UserRole
from app.models.level import AcademicLevel
from app.models.teacher import (
    TeacherAvailabilityBlock,
    TeacherAvailabilityException,
    TeacherBranchAssignment,
    TeacherLevelAssignment,
    TeacherProfile,
)
from app.models.user import User
from app.repositories.teachers import TeacherRepository
from app.services.invitations import CreatedInvitation, InvitationService


class TeacherError(Exception):
    pass


class TeacherNotFoundError(TeacherError):
    pass


class TeacherConflictError(TeacherError):
    pass


class LevelService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, actor: User, *, include_inactive: bool = False) -> list[AcademicLevel]:
        statement = select(AcademicLevel).where(
            AcademicLevel.organization_id == self._tenant_id(actor)
        )
        if not include_inactive:
            statement = statement.where(AcademicLevel.active.is_(True))
        return list(self.db.scalars(statement.order_by(AcademicLevel.sort_order)))

    def create(self, actor: User, data: dict[str, object]) -> AcademicLevel:
        name = str(data["name"]).strip()
        if not name:
            raise TeacherError("El nombre del nivel es obligatorio")
        level = AcademicLevel(
            organization_id=self._tenant_id(actor),
            name=name,
            description=self._clean(data.get("description")),
            sort_order=int(data["sort_order"]),
            default_capacity=data.get("default_capacity"),
            active=True,
        )
        self.db.add(level)
        self._commit()
        self.db.refresh(level)
        return level

    def update(
        self, actor: User, level_id: int, changes: dict[str, object]
    ) -> AcademicLevel:
        level = self.db.scalar(
            select(AcademicLevel).where(
                AcademicLevel.id == level_id,
                AcademicLevel.organization_id == self._tenant_id(actor),
            )
        )
        if level is None:
            raise TeacherNotFoundError("Nivel no encontrado")
        required = {"name", "sort_order", "active"}
        if any(changes.get(key) is None for key in required if key in changes):
            raise TeacherError("Los campos obligatorios no pueden quedar vacÃ­os")
        if "name" in changes:
            changes["name"] = str(changes["name"]).strip()
            if not changes["name"]:
                raise TeacherError("El nombre del nivel es obligatorio")
        if "description" in changes:
            changes["description"] = self._clean(changes["description"])
        for field, value in changes.items():
            setattr(level, field, value)
        self._commit()
        self.db.refresh(level)
        return level

    def _commit(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise TeacherConflictError("Ya existe un nivel con ese nombre u orden") from error

    @staticmethod
    def _tenant_id(actor: User) -> int:
        if actor.organization_id is None:
            raise TeacherError("Esta operaciÃ³n requiere contexto de organizaciÃ³n")
        return actor.organization_id

    @staticmethod
    def _clean(value: object) -> str | None:
        if value is None:
            return None
        result = str(value).strip()
        return result or None


class TeacherService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.teachers = TeacherRepository(db)

    def list(
        self,
        actor: User,
        *,
        status: str | None = None,
        branch_id: int | None = None,
        search: str | None = None,
    ) -> list[TeacherProfile]:
        return self.teachers.list(
            self._tenant_id(actor), status=status, branch_id=branch_id, search=search
        )

    def get(self, actor: User, teacher_id: int) -> TeacherProfile:
        teacher = self.teachers.get(self._tenant_id(actor), teacher_id)
        if teacher is None:
            raise TeacherNotFoundError("Profesor no encontrado")
        return teacher

    def get_self(self, user: User) -> TeacherProfile:
        if user.organization_id is None:
            raise TeacherNotFoundError("Perfil de profesor no encontrado")
        teacher = self.teachers.get_by_user(user.id, user.organization_id)
        if teacher is None:
            raise TeacherNotFoundError("Perfil de profesor no encontrado")
        return teacher

    def create(
        self, actor: User, data: dict[str, object]
    ) -> tuple[TeacherProfile, CreatedInvitation]:
        organization_id = self._tenant_id(actor)
        branch_ids = self._ids(data["branch_ids"], "Debe asignarse al menos una sucursal")
        level_ids = self._ids(data.get("level_ids", []), None)
        self._validate_branches(organization_id, branch_ids)
        self._validate_levels(organization_id, level_ids)
        email = str(data["email"]).strip().lower()
        if self.db.scalar(select(User).where(func.lower(User.email) == email)) is not None:
            raise TeacherConflictError("El correo ya estÃ¡ registrado")
        first_name = self._required_text(data["first_name"], "El nombre es obligatorio")
        last_name = self._required_text(data["last_name"], "Los apellidos son obligatorios")
        user = User(
            organization_id=organization_id,
            branch_id=branch_ids[0],
            role=UserRole.TEACHER.value,
            name=f"{first_name} {last_name}".strip(),
            email=email,
            hashed_password=None,
            active=False,
        )
        teacher = TeacherProfile(
            organization_id=organization_id,
            user=user,
            employee_number=self._required_text(
                data["employee_number"], "El nÃºmero de empleado es obligatorio"
            ).upper(),
            first_name=first_name,
            last_name=last_name,
            phone=self._clean(data.get("phone")),
            hire_date=data["hire_date"],
            status=self._status_value(data.get("status", TeacherStatus.ACTIVE)),
            administrative_notes=self._clean(data.get("administrative_notes")),
        )
        self.db.add(teacher)
        try:
            self.db.flush()
            self._replace_assignments(teacher, branch_ids, level_ids)
            self.db.flush()
            invitation = InvitationService(self.db).create_for_existing_user(
                admin=actor, user=user
            )
        except IntegrityError as error:
            self.db.rollback()
            raise TeacherConflictError(
                "El nÃºmero de empleado o correo ya estÃ¡ registrado"
            ) from error
        return teacher, invitation

    def update(
        self, actor: User, teacher_id: int, changes: dict[str, object]
    ) -> TeacherProfile:
        teacher = self.get(actor, teacher_id)
        required = {
            "employee_number", "first_name", "last_name", "email", "hire_date", "status"
        }
        if any(changes.get(key) is None for key in required if key in changes):
            raise TeacherError("Los campos obligatorios no pueden quedar vacÃ­os")
        branch_ids = None
        level_ids = None
        if "branch_ids" in changes:
            branch_ids = self._ids(changes.pop("branch_ids"), "Debe asignarse al menos una sucursal")
            self._validate_branches(teacher.organization_id, branch_ids)
            teacher.user.branch_id = branch_ids[0]
        if "level_ids" in changes:
            level_ids = self._ids(changes.pop("level_ids"), None)
            self._validate_levels(teacher.organization_id, level_ids)
        if "email" in changes:
            email = str(changes.pop("email")).strip().lower()
            if self.db.scalar(
                select(User).where(func.lower(User.email) == email, User.id != teacher.user_id)
            ) is not None:
                raise TeacherConflictError("El correo ya estÃ¡ registrado")
            teacher.user.email = email
        if "employee_number" in changes:
            changes["employee_number"] = self._required_text(
                changes["employee_number"], "El nÃºmero de empleado es obligatorio"
            ).upper()
        if "status" in changes:
            changes["status"] = self._status_value(changes["status"])
        for field in {"first_name", "last_name"}:
            if field in changes:
                changes[field] = self._required_text(
                    changes[field], "El nombre y los apellidos son obligatorios"
                )
        for field in {"phone", "administrative_notes"}:
            if field in changes:
                changes[field] = self._clean(changes[field])
        for field, value in changes.items():
            setattr(teacher, field, value)
        if "first_name" in changes or "last_name" in changes:
            teacher.user.name = f"{teacher.first_name} {teacher.last_name}".strip()
        if "status" in changes:
            if teacher.status == TeacherStatus.ACTIVE.value and teacher.user.hashed_password:
                teacher.user.active = True
            elif teacher.status != TeacherStatus.ACTIVE.value:
                teacher.user.active = False
        if branch_ids is not None or level_ids is not None:
            self._replace_assignments(
                teacher,
                branch_ids if branch_ids is not None else [a.branch_id for a in teacher.branch_assignments],
                level_ids if level_ids is not None else [a.level_id for a in teacher.level_assignments],
            )
        self._commit_or_conflict()
        return self.get(actor, teacher_id)

    def update_self(self, user: User, changes: dict[str, object]) -> TeacherProfile:
        teacher = self.get_self(user)
        for field, value in changes.items():
            if field in {"first_name", "last_name"}:
                value = self._required_text(
                    value, "El nombre y los apellidos son obligatorios"
                )
            else:
                value = self._clean(value)
            setattr(teacher, field, value)
        if "first_name" in changes or "last_name" in changes:
            teacher.user.name = f"{teacher.first_name} {teacher.last_name}".strip()
        self.db.commit()
        return self.get_self(user)

    def deactivate(self, actor: User, teacher_id: int) -> None:
        teacher = self.get(actor, teacher_id)
        teacher.status = TeacherStatus.TERMINATED.value
        teacher.user.active = False
        self.db.commit()

    def replace_availability(
        self,
        teacher: TeacherProfile,
        recurring: list[dict[str, object]],
        exceptions: list[dict[str, object]],
    ) -> TeacherProfile:
        self._validate_availability(recurring, exceptions)
        self.db.execute(
            delete(TeacherAvailabilityBlock).where(
                TeacherAvailabilityBlock.teacher_id == teacher.id
            )
        )
        self.db.execute(
            delete(TeacherAvailabilityException).where(
                TeacherAvailabilityException.teacher_id == teacher.id
            )
        )
        for block in recurring:
            self.db.add(
                TeacherAvailabilityBlock(
                    organization_id=teacher.organization_id,
                    teacher_id=teacher.id,
                    weekday=int(block["weekday"]),
                    start_time=block["start_time"],
                    end_time=block["end_time"],
                )
            )
        for item in exceptions:
            self.db.add(
                TeacherAvailabilityException(
                    organization_id=teacher.organization_id,
                    teacher_id=teacher.id,
                    exception_date=item["exception_date"],
                    is_available=bool(item["is_available"]),
                    start_time=item.get("start_time"),
                    end_time=item.get("end_time"),
                )
            )
        self._commit_or_conflict("La disponibilidad contiene bloques duplicados")
        return self.teachers.get(teacher.organization_id, teacher.id)

    def _replace_assignments(
        self, teacher: TeacherProfile, branch_ids: list[int], level_ids: list[int]
    ) -> None:
        teacher.branch_assignments = [
            TeacherBranchAssignment(
                organization_id=teacher.organization_id, branch_id=branch_id
            )
            for branch_id in branch_ids
        ]
        teacher.level_assignments = [
            TeacherLevelAssignment(
                organization_id=teacher.organization_id, level_id=level_id
            )
            for level_id in level_ids
        ]

    def _validate_branches(self, organization_id: int, ids: list[int]) -> None:
        found = set(
            self.db.scalars(
                select(Branch.id).where(
                    Branch.organization_id == organization_id,
                    Branch.id.in_(ids),
                    Branch.active.is_(True),
                )
            )
        )
        if found != set(ids):
            raise TeacherError("Una o mÃ¡s sucursales no son vÃ¡lidas")

    def _validate_levels(self, organization_id: int, ids: list[int]) -> None:
        if not ids:
            return
        found = set(
            self.db.scalars(
                select(AcademicLevel.id).where(
                    AcademicLevel.organization_id == organization_id,
                    AcademicLevel.id.in_(ids),
                    AcademicLevel.active.is_(True),
                )
            )
        )
        if found != set(ids):
            raise TeacherError("Uno o mÃ¡s niveles no son vÃ¡lidos")

    @staticmethod
    def _validate_availability(
        recurring: list[dict[str, object]], exceptions: list[dict[str, object]]
    ) -> None:
        by_day: dict[int, list[tuple[time, time]]] = {}
        for block in recurring:
            weekday = int(block["weekday"])
            start = block["start_time"]
            end = block["end_time"]
            if not isinstance(start, time) or not isinstance(end, time) or end <= start:
                raise TeacherError("Cada bloque debe tener una hora final posterior a la inicial")
            intervals = by_day.setdefault(weekday, [])
            if any(start < existing_end and end > existing_start for existing_start, existing_end in intervals):
                raise TeacherConflictError("Los bloques recurrentes no pueden traslaparse")
            intervals.append((start, end))
        seen_dates = set()
        for item in exceptions:
            exception_date = item["exception_date"]
            if exception_date in seen_dates:
                raise TeacherConflictError("Solo puede existir una excepciÃ³n por fecha")
            seen_dates.add(exception_date)
            start = item.get("start_time")
            end = item.get("end_time")
            if bool(item["is_available"]):
                if not isinstance(start, time) or not isinstance(end, time) or end <= start:
                    raise TeacherError("Una excepciÃ³n disponible requiere un horario vÃ¡lido")
            elif start is not None or end is not None:
                raise TeacherError("Una excepciÃ³n no disponible no debe incluir horario")

    def _commit_or_conflict(self, message: str | None = None) -> None:
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise TeacherConflictError(
                message or "El nÃºmero de empleado o correo ya estÃ¡ registrado"
            ) from error

    @staticmethod
    def _ids(value: object, empty_message: str | None) -> list[int]:
        ids = list(dict.fromkeys(int(item) for item in value))
        if not ids and empty_message:
            raise TeacherError(empty_message)
        return ids

    @staticmethod
    def _tenant_id(actor: User) -> int:
        if actor.organization_id is None:
            raise TeacherError("Esta operaciÃ³n requiere contexto de organizaciÃ³n")
        return actor.organization_id

    @staticmethod
    def _status_value(value: object) -> str:
        return value.value if isinstance(value, TeacherStatus) else str(value)

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
            raise TeacherError(message)
        return result
