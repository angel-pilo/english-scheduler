from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.student import StudentProfile


class StudentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        organization_id: int,
        *,
        status: str | None = None,
        branch_id: int | None = None,
        search: str | None = None,
    ) -> list[StudentProfile]:
        statement = (
            select(StudentProfile)
            .options(joinedload(StudentProfile.user))
            .where(StudentProfile.organization_id == organization_id)
        )
        if status is not None:
            statement = statement.where(StudentProfile.status == status)
        if branch_id is not None:
            statement = statement.where(StudentProfile.primary_branch_id == branch_id)
        if search:
            term = f"%{search.strip().lower()}%"
            statement = statement.where(
                or_(
                    func.lower(StudentProfile.student_number).like(term),
                    func.lower(StudentProfile.first_name).like(term),
                    func.lower(StudentProfile.last_name).like(term),
                )
            )
        return list(self.db.scalars(statement.order_by(StudentProfile.last_name, StudentProfile.first_name)))

    def get(self, organization_id: int, student_id: int) -> StudentProfile | None:
        return self.db.scalar(
            select(StudentProfile)
            .options(joinedload(StudentProfile.user))
            .where(
                StudentProfile.id == student_id,
                StudentProfile.organization_id == organization_id,
            )
        )

    def get_by_user(self, user_id: int, organization_id: int) -> StudentProfile | None:
        return self.db.scalar(
            select(StudentProfile)
            .options(joinedload(StudentProfile.user))
            .where(
                StudentProfile.user_id == user_id,
                StudentProfile.organization_id == organization_id,
            )
        )
