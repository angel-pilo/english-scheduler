from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.enums import StudentStatus, UserRole
from app.models.student import StudentProfile
from app.models.user import User
from app.repositories.students import StudentRepository
from app.services.invitations import CreatedInvitation, InvitationService


class StudentError(Exception):
    pass


class StudentNotFoundError(StudentError):
    pass


class StudentConflictError(StudentError):
    pass


class StudentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.students = StudentRepository(db)

    def list(
        self,
        actor: User,
        *,
        status: str | None = None,
        branch_id: int | None = None,
        search: str | None = None,
    ) -> list[StudentProfile]:
        return self.students.list(
            self._tenant_id(actor), status=status, branch_id=branch_id, search=search
        )

    def get(self, actor: User, student_id: int) -> StudentProfile:
        student = self.students.get(self._tenant_id(actor), student_id)
        if student is None:
            raise StudentNotFoundError("Alumno no encontrado")
        return student

    def get_self(self, user: User) -> StudentProfile:
        if user.organization_id is None:
            raise StudentNotFoundError("Perfil de alumno no encontrado")
        student = self.students.get_by_user(user.id, user.organization_id)
        if student is None:
            raise StudentNotFoundError("Perfil de alumno no encontrado")
        return student

    def create(self, actor: User, data: dict[str, object]) -> tuple[StudentProfile, CreatedInvitation]:
        organization_id = self._tenant_id(actor)
        branch_id = int(data["primary_branch_id"])
        self._active_branch(organization_id, branch_id)
        self._validate_dates(
            data.get("course_start_date"), data.get("course_end_date")
        )
        email = str(data["email"]).strip().lower()
        if self.db.scalar(select(User).where(func.lower(User.email) == email)) is not None:
            raise StudentConflictError("El correo ya está registrado")

        first_name = str(data["first_name"]).strip()
        last_name = str(data["last_name"]).strip()
        user = User(
            organization_id=organization_id,
            branch_id=branch_id,
            role=UserRole.STUDENT.value,
            name=f"{first_name} {last_name}".strip(),
            email=email,
            hashed_password=None,
            active=False,
        )
        profile = StudentProfile(
            organization_id=organization_id,
            user=user,
            primary_branch_id=branch_id,
            student_number=str(data["student_number"]).strip().upper(),
            first_name=first_name,
            last_name=last_name,
            phone=self._clean(data.get("phone")),
            address=self._clean(data.get("address")),
            company=self._clean(data.get("company")),
            emergency_contact_name=self._clean(data.get("emergency_contact_name")),
            emergency_contact_phone=self._clean(data.get("emergency_contact_phone")),
            admission_date=data["admission_date"],
            weekly_hours_limit=Decimal(str(data["weekly_hours_limit"])),
            status=self._status_value(data.get("status", StudentStatus.ACTIVE)),
            course_start_date=data.get("course_start_date"),
            course_end_date=data.get("course_end_date"),
            can_book_other_branches=bool(data.get("can_book_other_branches", False)),
            administrative_notes=self._clean(data.get("administrative_notes")),
        )
        self.db.add(profile)
        try:
            self.db.flush()
            invitation = InvitationService(self.db).create_for_existing_user(
                admin=actor, user=user
            )
        except IntegrityError as error:
            self.db.rollback()
            raise StudentConflictError("La matrícula o el correo ya están registrados") from error
        return profile, invitation

    def update(self, actor: User, student_id: int, changes: dict[str, object]) -> StudentProfile:
        student = self.get(actor, student_id)
        self._apply_changes(student, changes, administrative=True)
        self._commit_or_conflict()
        self.db.refresh(student)
        return student

    def update_self(self, user: User, changes: dict[str, object]) -> StudentProfile:
        student = self.get_self(user)
        self._apply_changes(student, changes, administrative=False)
        self.db.commit()
        self.db.refresh(student)
        return student

    def withdraw(self, actor: User, student_id: int) -> None:
        student = self.get(actor, student_id)
        student.status = StudentStatus.WITHDRAWN.value
        student.user.active = False
        self.db.commit()

    def _apply_changes(
        self, student: StudentProfile, changes: dict[str, object], *, administrative: bool
    ) -> None:
        required_fields = {
            "student_number",
            "first_name",
            "last_name",
            "email",
            "primary_branch_id",
            "admission_date",
            "weekly_hours_limit",
            "status",
        }
        if any(changes.get(field) is None for field in required_fields if field in changes):
            raise StudentError("Los campos obligatorios no pueden quedar vacÃ­os")
        if administrative and "primary_branch_id" in changes:
            branch_id = int(changes["primary_branch_id"])
            self._active_branch(student.organization_id, branch_id)
            student.primary_branch_id = branch_id
            student.user.branch_id = branch_id
        if administrative and "email" in changes:
            email = str(changes.pop("email")).strip().lower()
            existing = self.db.scalar(
                select(User).where(func.lower(User.email) == email, User.id != student.user_id)
            )
            if existing is not None:
                raise StudentConflictError("El correo ya está registrado")
            student.user.email = email
        if administrative and "student_number" in changes:
            changes["student_number"] = str(changes["student_number"]).strip().upper()
        if "status" in changes:
            changes["status"] = self._status_value(changes["status"])
        start = changes.get("course_start_date", student.course_start_date)
        end = changes.get("course_end_date", student.course_end_date)
        self._validate_dates(start, end)

        excluded = {"primary_branch_id", "email"}
        for field, value in changes.items():
            if field in excluded:
                continue
            if field in {
                "first_name",
                "last_name",
                "phone",
                "address",
                "company",
                "emergency_contact_name",
                "emergency_contact_phone",
                "administrative_notes",
            }:
                value = self._clean(value)
            setattr(student, field, value)

        if "first_name" in changes or "last_name" in changes:
            student.user.name = f"{student.first_name} {student.last_name}".strip()
        if administrative and "status" in changes:
            if student.status in {
                StudentStatus.INACTIVE.value,
                StudentStatus.SUSPENDED.value,
                StudentStatus.GRADUATED.value,
                StudentStatus.WITHDRAWN.value,
            }:
                student.user.active = False
            elif student.status == StudentStatus.ACTIVE.value and student.user.hashed_password:
                student.user.active = True

    def _commit_or_conflict(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise StudentConflictError("La matrícula o el correo ya están registrados") from error

    def _active_branch(self, organization_id: int, branch_id: int) -> Branch:
        branch = self.db.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.organization_id == organization_id,
                Branch.active.is_(True),
            )
        )
        if branch is None:
            raise StudentError("Sucursal activa no encontrada")
        return branch

    @staticmethod
    def _tenant_id(actor: User) -> int:
        if actor.organization_id is None:
            raise StudentError("Esta operación requiere contexto de organización")
        return actor.organization_id

    @staticmethod
    def _validate_dates(start: object, end: object) -> None:
        if isinstance(start, date) and isinstance(end, date) and end < start:
            raise StudentError("La fecha final no puede ser anterior a la fecha inicial")

    @staticmethod
    def _status_value(value: object) -> str:
        return value.value if isinstance(value, StudentStatus) else str(value)

    @staticmethod
    def _clean(value: object) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None
