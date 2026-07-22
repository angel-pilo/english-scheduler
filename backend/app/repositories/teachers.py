from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.teacher import TeacherBranchAssignment, TeacherProfile


class TeacherRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _options():
        return (
            selectinload(TeacherProfile.user),
            selectinload(TeacherProfile.branch_assignments),
            selectinload(TeacherProfile.level_assignments),
            selectinload(TeacherProfile.recurring_availability),
            selectinload(TeacherProfile.availability_exceptions),
        )

    def list(
        self,
        organization_id: int,
        *,
        status: str | None = None,
        branch_id: int | None = None,
        search: str | None = None,
    ) -> list[TeacherProfile]:
        statement = select(TeacherProfile).options(*self._options()).where(
            TeacherProfile.organization_id == organization_id
        )
        if status:
            statement = statement.where(TeacherProfile.status == status)
        if branch_id is not None:
            statement = statement.where(
                TeacherProfile.branch_assignments.any(
                    TeacherBranchAssignment.branch_id == branch_id
                )
            )
        if search:
            term = f"%{search.strip().lower()}%"
            statement = statement.where(
                or_(
                    func.lower(TeacherProfile.employee_number).like(term),
                    func.lower(TeacherProfile.first_name).like(term),
                    func.lower(TeacherProfile.last_name).like(term),
                )
            )
        return list(
            self.db.scalars(
                statement.order_by(TeacherProfile.last_name, TeacherProfile.first_name)
            )
        )

    def get(self, organization_id: int, teacher_id: int) -> TeacherProfile | None:
        return self.db.scalar(
            select(TeacherProfile)
            .options(*self._options())
            .where(
                TeacherProfile.id == teacher_id,
                TeacherProfile.organization_id == organization_id,
            )
        )

    def get_by_user(self, user_id: int, organization_id: int) -> TeacherProfile | None:
        return self.db.scalar(
            select(TeacherProfile)
            .options(*self._options())
            .where(
                TeacherProfile.user_id == user_id,
                TeacherProfile.organization_id == organization_id,
            )
        )
