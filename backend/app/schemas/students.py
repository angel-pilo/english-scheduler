from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import StudentStatus


class StudentCreateIn(BaseModel):
    student_number: str = Field(min_length=1, max_length=40)
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    primary_branch_id: int
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=2000)
    company: str | None = Field(default=None, max_length=160)
    emergency_contact_name: str | None = Field(default=None, max_length=160)
    emergency_contact_phone: str | None = Field(default=None, max_length=30)
    admission_date: date
    weekly_hours_limit: Decimal = Field(gt=0, le=168, decimal_places=2)
    status: StudentStatus = StudentStatus.ACTIVE
    course_start_date: date | None = None
    course_end_date: date | None = None
    can_book_other_branches: bool = False
    administrative_notes: str | None = Field(default=None, max_length=4000)


class StudentUpdateIn(BaseModel):
    student_number: str | None = Field(default=None, min_length=1, max_length=40)
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    primary_branch_id: int | None = None
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=2000)
    company: str | None = Field(default=None, max_length=160)
    emergency_contact_name: str | None = Field(default=None, max_length=160)
    emergency_contact_phone: str | None = Field(default=None, max_length=30)
    admission_date: date | None = None
    weekly_hours_limit: Decimal | None = Field(default=None, gt=0, le=168, decimal_places=2)
    status: StudentStatus | None = None
    course_start_date: date | None = None
    course_end_date: date | None = None
    can_book_other_branches: bool | None = None
    administrative_notes: str | None = Field(default=None, max_length=4000)


class StudentSelfUpdateIn(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=2000)
    emergency_contact_name: str | None = Field(default=None, max_length=160)
    emergency_contact_phone: str | None = Field(default=None, max_length=30)


class StudentOut(BaseModel):
    id: int
    user_id: int
    organization_id: int
    primary_branch_id: int
    student_number: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: str | None
    address: str | None
    company: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    admission_date: date
    weekly_hours_limit: Decimal
    status: str
    course_start_date: date | None
    course_end_date: date | None
    can_book_other_branches: bool
    administrative_notes: str | None
    photo_storage_key: str | None
    account_active: bool
    created_at: datetime
    updated_at: datetime


class StudentCreatedOut(StudentOut):
    activation_url: str | None = None
