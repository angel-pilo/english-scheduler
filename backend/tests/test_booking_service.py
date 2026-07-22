from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.branch import Branch
from app.models.curriculum import StudentLevelHistory
from app.models.enums import (
    BookingStatus,
    ClassSessionStatus,
    StudentStatus,
    UserRole,
    WaitlistStatus,
)
from app.models.level import AcademicLevel
from app.models.org import Organization
from app.models.rbac import Role
from app.models.room import Room
from app.models.schedule import ClassSession, ScheduleTemplate
from app.models.student import StudentProfile
from app.models.teacher import TeacherProfile
from app.models.user import User
from app.services.bookings import (
    BookingConflictError,
    BookingError,
    BookingNotFoundError,
    BookingPolicyService,
    BookingService,
)
from app.services.waitlists import (
    NotificationService,
    WaitlistConflictError,
    WaitlistNotFoundError,
    WaitlistService,
)


NOW = datetime(2026, 8, 3, 10, tzinfo=timezone.utc)


@dataclass
class TenantData:
    admin: User
    branch: Branch
    room: Room
    level: AcademicLevel
    teacher: TeacherProfile


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(
            [
                Role(code=UserRole.ADMIN.value, name="Admin", description="Admin"),
                Role(code=UserRole.TEACHER.value, name="Teacher", description="Teacher"),
                Role(code=UserRole.STUDENT.value, name="Student", description="Student"),
            ]
        )
        db.commit()
        yield db


def _tenant(db: Session, suffix: str = "one") -> TenantData:
    organization = Organization(name=f"Academia {suffix}", slug=f"academia-{suffix}")
    branch = Branch(
        organization=organization,
        name="Matriz",
        code=f"M-{suffix}",
        timezone="UTC",
    )
    admin = User(
        organization=organization,
        branch=branch,
        name="Admin",
        email=f"admin-{suffix}@test.local",
        hashed_password="hash",
        role=UserRole.ADMIN.value,
    )
    teacher_user = User(
        organization=organization,
        branch=branch,
        name="Teacher",
        email=f"teacher-{suffix}@test.local",
        hashed_password="hash",
        role=UserRole.TEACHER.value,
    )
    db.add_all([admin, teacher_user])
    db.flush()
    room = Room(
        organization_id=organization.id,
        branch_id=branch.id,
        name="Salón 1",
        code="S1",
        capacity=2,
    )
    level = AcademicLevel(
        organization_id=organization.id,
        name="A1",
        sort_order=1,
        default_capacity=2,
    )
    teacher = TeacherProfile(
        organization_id=organization.id,
        user_id=teacher_user.id,
        employee_number="T-1",
        first_name="Teacher",
        last_name="One",
        hire_date=date(2026, 1, 1),
    )
    db.add_all([room, level, teacher])
    db.commit()
    return TenantData(admin, branch, room, level, teacher)


def _student(
    db: Session,
    tenant: TenantData,
    number: int,
    *,
    weekly_hours: str = "2",
    level: AcademicLevel | None = None,
) -> tuple[User, StudentProfile]:
    user = User(
        organization_id=tenant.admin.organization_id,
        branch_id=tenant.branch.id,
        name=f"Student {number}",
        email=f"student-{tenant.admin.organization_id}-{number}@test.local",
        hashed_password="hash",
        role=UserRole.STUDENT.value,
        active=True,
    )
    profile = StudentProfile(
        organization_id=tenant.admin.organization_id,
        user=user,
        primary_branch_id=tenant.branch.id,
        student_number=f"ST-{number}",
        first_name="Student",
        last_name=str(number),
        admission_date=date(2026, 1, 1),
        weekly_hours_limit=Decimal(weekly_hours),
        status=StudentStatus.ACTIVE.value,
        can_book_other_branches=False,
    )
    db.add(profile)
    db.flush()
    selected_level = level or tenant.level
    db.add(
        StudentLevelHistory(
            organization_id=tenant.admin.organization_id,
            student_id=profile.id,
            level_id=selected_level.id,
            start_date=date(2026, 1, 1),
            end_date=None,
            is_current=True,
        )
    )
    db.commit()
    return user, profile


def _class_session(
    db: Session,
    tenant: TenantData,
    *,
    session_date: date = date(2026, 8, 10),
    start_time: time = time(7),
    capacity: int = 2,
    level: AcademicLevel | None = None,
) -> ClassSession:
    selected_level = level or tenant.level
    end_time = time(start_time.hour + 1, start_time.minute)
    template = ScheduleTemplate(
        organization_id=tenant.admin.organization_id,
        branch_id=tenant.branch.id,
        room_id=tenant.room.id,
        level_id=selected_level.id,
        name=f"Clase {session_date}-{start_time}",
        weekday=session_date.weekday(),
        start_time=start_time,
        end_time=end_time,
        configured_capacity=capacity,
        effective_from=date(2026, 1, 1),
        active=True,
        created_by_user_id=tenant.admin.id,
        updated_by_user_id=tenant.admin.id,
    )
    db.add(template)
    db.flush()
    item = ClassSession(
        organization_id=tenant.admin.organization_id,
        source_template_id=template.id,
        generation_batch_id=f"batch-{template.id}",
        branch_id=tenant.branch.id,
        room_id=tenant.room.id,
        level_id=selected_level.id,
        teacher_id=tenant.teacher.id,
        title=template.name,
        session_date=session_date,
        start_time=start_time,
        end_time=end_time,
        configured_capacity=capacity,
        effective_capacity=capacity,
        status=ClassSessionStatus.PUBLISHED.value,
        created_by_user_id=tenant.admin.id,
        updated_by_user_id=tenant.admin.id,
    )
    db.add(item)
    db.commit()
    return item


def test_student_books_and_weekly_usage_is_reported(session: Session) -> None:
    tenant = _tenant(session)
    user, _ = _student(session, tenant, 1)
    class_session = _class_session(session, tenant)

    booking = BookingService(session).create_for_self(user, class_session.id, now=NOW)

    assert booking.status == BookingStatus.CONFIRMED.value
    assert booking.reserved_minutes == 60
    assert booking.events[0].event_type == "CREATED"
    usage = BookingService(session).weekly_usage(user, week_start=date(2026, 8, 10))
    assert usage.allowed_minutes == 120
    assert usage.reserved_minutes == 60
    assert usage.available_minutes == 60


def test_duplicate_and_capacity_are_enforced(session: Session) -> None:
    tenant = _tenant(session)
    first_user, _ = _student(session, tenant, 1)
    second_user, _ = _student(session, tenant, 2)
    class_session = _class_session(session, tenant, capacity=1)
    service = BookingService(session)
    service.create_for_self(first_user, class_session.id, now=NOW)

    with pytest.raises(BookingConflictError, match="ya reservó"):
        service.create_for_self(first_user, class_session.id, now=NOW)
    with pytest.raises(BookingConflictError, match="lugares"):
        service.create_for_self(second_user, class_session.id, now=NOW)


def test_weekly_limit_and_time_conflicts_are_enforced(session: Session) -> None:
    tenant = _tenant(session)
    user, _ = _student(session, tenant, 1, weekly_hours="1")
    first = _class_session(session, tenant, start_time=time(7))
    second = _class_session(session, tenant, start_time=time(8))
    overlap = _class_session(session, tenant, start_time=time(7, 30))
    service = BookingService(session)
    service.create_for_self(user, first.id, now=NOW)

    with pytest.raises(BookingConflictError, match="límite semanal"):
        service.create_for_self(user, second.id, now=NOW)
    with pytest.raises(BookingConflictError, match="otra clase"):
        service.create_for_self(user, overlap.id, now=NOW)


def test_normal_cancellation_releases_seat_and_quota(session: Session) -> None:
    tenant = _tenant(session)
    user, _ = _student(session, tenant, 1, weekly_hours="1")
    class_session = _class_session(session, tenant, capacity=1)
    service = BookingService(session)
    booking = service.create_for_self(user, class_session.id, now=NOW)

    cancelled = service.cancel_for_self(
        user, booking.id, reason="Cambio de horario", now=NOW
    )

    assert cancelled.status == BookingStatus.CANCELLED.value
    assert cancelled.quota_released is True
    assert [item.event_type for item in cancelled.events] == ["CREATED", "CANCELLED"]
    assert service.weekly_usage(user, week_start=date(2026, 8, 10)).reserved_minutes == 0


def test_late_cancellation_requires_admin_review(session: Session) -> None:
    tenant = _tenant(session)
    user, _ = _student(session, tenant, 1, weekly_hours="1")
    class_session = _class_session(session, tenant)
    service = BookingService(session)
    booking = service.create_for_self(user, class_session.id, now=NOW)
    late_now = datetime(2026, 8, 10, 6, 30, tzinfo=timezone.utc)

    pending = service.cancel_for_self(
        user, booking.id, reason="Emergencia", now=late_now
    )
    assert pending.status == BookingStatus.CANCELLATION_PENDING.value

    reviewed = service.review_late_cancellation(
        tenant.admin,
        booking.id,
        approve=True,
        reason="Aprobada sin devolver hora",
        release_quota=False,
        now=late_now,
    )
    assert reviewed.status == BookingStatus.CANCELLED.value
    assert reviewed.quota_released is False
    assert service.weekly_usage(user, week_start=date(2026, 8, 10)).reserved_minutes == 60


def test_policy_windows_and_week_offsets_are_configurable(session: Session) -> None:
    tenant = _tenant(session)
    user, _ = _student(session, tenant, 1)
    class_session = _class_session(session, tenant)
    BookingPolicyService(session).upsert(
        tenant.admin,
        branch_id=tenant.branch.id,
        data={
            "minimum_booking_notice_hours": 24,
            "minimum_cancellation_notice_hours": 24,
            "earliest_booking_week_offset": 1,
            "latest_booking_week_offset": 1,
            "time_blocks": [
                {"weekday": 0, "start_time": time(11), "end_time": time(12)}
            ],
        },
    )

    with pytest.raises(BookingConflictError, match="ventana"):
        BookingService(session).create_for_self(user, class_session.id, now=NOW)


def test_admin_override_requires_reason_but_never_overbooks(session: Session) -> None:
    tenant = _tenant(session)
    first_user, first_student = _student(session, tenant, 1)
    _, second_student = _student(session, tenant, 2)
    class_session = _class_session(session, tenant, capacity=1)
    service = BookingService(session)
    service.create_for_self(first_user, class_session.id, now=NOW)

    with pytest.raises(BookingConflictError, match="lugares"):
        service.create_for_admin(
            tenant.admin,
            student_id=second_student.id,
            session_id=class_session.id,
            override_rules=True,
            reason="Excepción autorizada",
            now=NOW,
        )
    with pytest.raises(BookingError, match="motivo"):
        service.create_for_admin(
            tenant.admin,
            student_id=first_student.id,
            session_id=class_session.id,
            override_rules=True,
            reason=None,
            now=NOW,
        )

    late_session = _class_session(
        session,
        tenant,
        session_date=date(2026, 8, 3),
        start_time=time(12),
        capacity=2,
    )
    extraordinary = service.create_for_admin(
        tenant.admin,
        student_id=second_student.id,
        session_id=late_session.id,
        override_rules=True,
        reason="Alta extraordinaria autorizada",
        now=NOW,
    )
    assert extraordinary.status == BookingStatus.CONFIRMED.value
    assert extraordinary.events[0].event_type == "ADMIN_CREATED"
    assert extraordinary.events[0].override_rules is True


def test_tenant_cannot_access_another_organizations_session(session: Session) -> None:
    first_tenant = _tenant(session, "one")
    second_tenant = _tenant(session, "two")
    user, _ = _student(session, first_tenant, 1)
    foreign_session = _class_session(session, second_tenant)

    with pytest.raises(BookingNotFoundError, match="Sesión no encontrada"):
        BookingService(session).create_for_self(user, foreign_session.id, now=NOW)


def test_waitlist_requires_a_full_session_and_preserves_fifo(session: Session) -> None:
    tenant = _tenant(session)
    first_user, _ = _student(session, tenant, 1)
    second_user, _ = _student(session, tenant, 2)
    third_user, _ = _student(session, tenant, 3)
    class_session = _class_session(session, tenant, capacity=1)
    booking_service = BookingService(session)
    waitlist_service = WaitlistService(session)

    with pytest.raises(WaitlistConflictError, match="reservar directamente"):
        waitlist_service.join(second_user, class_session.id, now=NOW)

    booking_service.create_for_self(first_user, class_session.id, now=NOW)
    second = waitlist_service.join(second_user, class_session.id, now=NOW)
    third = waitlist_service.join(third_user, class_session.id, now=NOW)

    assert waitlist_service.position(second) == 1
    assert waitlist_service.position(third) == 2


def test_cancellation_offers_place_and_holds_capacity(session: Session) -> None:
    tenant = _tenant(session)
    booked_user, _ = _student(session, tenant, 1)
    waiting_user, _ = _student(session, tenant, 2)
    other_user, _ = _student(session, tenant, 3)
    class_session = _class_session(session, tenant, capacity=1)
    booking_service = BookingService(session)
    waitlist_service = WaitlistService(session)
    booking = booking_service.create_for_self(booked_user, class_session.id, now=NOW)
    entry = waitlist_service.join(waiting_user, class_session.id, now=NOW)

    booking_service.cancel_for_self(booked_user, booking.id, reason=None, now=NOW)
    offered = waitlist_service.get_for_self(waiting_user, entry.id, now=NOW)

    assert offered.status == WaitlistStatus.OFFERED.value
    assert offered.offer_expires_at is not None
    notifications = NotificationService(session).list(waiting_user)
    assert notifications[0].notification_type == "WAITLIST_PLACE_AVAILABLE"
    with pytest.raises(BookingConflictError, match="lugares"):
        booking_service.create_for_self(other_user, class_session.id, now=NOW)


def test_student_explicitly_accepts_waitlist_offer(session: Session) -> None:
    tenant = _tenant(session)
    booked_user, _ = _student(session, tenant, 1)
    waiting_user, _ = _student(session, tenant, 2)
    class_session = _class_session(session, tenant, capacity=1)
    booking_service = BookingService(session)
    waitlist_service = WaitlistService(session)
    original = booking_service.create_for_self(booked_user, class_session.id, now=NOW)
    entry = waitlist_service.join(waiting_user, class_session.id, now=NOW)
    booking_service.cancel_for_self(booked_user, original.id, reason=None, now=NOW)

    accepted, booking = waitlist_service.accept(waiting_user, entry.id, now=NOW)

    assert accepted.status == WaitlistStatus.ACCEPTED.value
    assert accepted.booking_id == booking.id
    assert booking.status == BookingStatus.CONFIRMED.value
    assert booking.student_id == accepted.student_id


def test_expired_offer_notifies_and_advances_queue(session: Session) -> None:
    tenant = _tenant(session)
    booked_user, _ = _student(session, tenant, 1)
    first_waiting_user, _ = _student(session, tenant, 2)
    second_waiting_user, _ = _student(session, tenant, 3)
    class_session = _class_session(session, tenant, capacity=1)
    booking_service = BookingService(session)
    waitlist_service = WaitlistService(session)
    booking = booking_service.create_for_self(booked_user, class_session.id, now=NOW)
    first = waitlist_service.join(first_waiting_user, class_session.id, now=NOW)
    second = waitlist_service.join(second_waiting_user, class_session.id, now=NOW)
    booking_service.cancel_for_self(booked_user, booking.id, reason=None, now=NOW)

    after_expiration = NOW + timedelta(minutes=121)
    processed = waitlist_service.process_expired(tenant.admin, now=after_expiration)
    first = waitlist_service.get_for_self(
        first_waiting_user, first.id, now=after_expiration
    )
    second = waitlist_service.get_for_self(
        second_waiting_user, second.id, now=after_expiration
    )

    assert processed == 1
    assert first.status == WaitlistStatus.EXPIRED.value
    assert second.status == WaitlistStatus.OFFERED.value
    assert {
        item.notification_type
        for item in NotificationService(session).list(first_waiting_user)
    } == {"WAITLIST_PLACE_AVAILABLE", "WAITLIST_OFFER_EXPIRED"}


def test_leaving_an_offer_promotes_next_student(session: Session) -> None:
    tenant = _tenant(session)
    booked_user, _ = _student(session, tenant, 1)
    first_waiting_user, _ = _student(session, tenant, 2)
    second_waiting_user, _ = _student(session, tenant, 3)
    class_session = _class_session(session, tenant, capacity=1)
    booking_service = BookingService(session)
    waitlist_service = WaitlistService(session)
    booking = booking_service.create_for_self(booked_user, class_session.id, now=NOW)
    first = waitlist_service.join(first_waiting_user, class_session.id, now=NOW)
    second = waitlist_service.join(second_waiting_user, class_session.id, now=NOW)
    booking_service.cancel_for_self(booked_user, booking.id, reason=None, now=NOW)

    left = waitlist_service.leave(first_waiting_user, first.id, now=NOW)
    promoted = waitlist_service.get_for_self(second_waiting_user, second.id, now=NOW)

    assert left.status == WaitlistStatus.LEFT.value
    assert promoted.status == WaitlistStatus.OFFERED.value


def test_notification_can_only_be_read_by_its_owner(session: Session) -> None:
    tenant = _tenant(session)
    booked_user, _ = _student(session, tenant, 1)
    waiting_user, _ = _student(session, tenant, 2)
    other_user, _ = _student(session, tenant, 3)
    class_session = _class_session(session, tenant, capacity=1)
    booking_service = BookingService(session)
    waitlist_service = WaitlistService(session)
    booking = booking_service.create_for_self(booked_user, class_session.id, now=NOW)
    waitlist_service.join(waiting_user, class_session.id, now=NOW)
    booking_service.cancel_for_self(booked_user, booking.id, reason=None, now=NOW)
    notification = NotificationService(session).list(waiting_user)[0]

    with pytest.raises(WaitlistNotFoundError, match="Notificación no encontrada"):
        NotificationService(session).mark_read(other_user, notification.id, now=NOW)
    read = NotificationService(session).mark_read(waiting_user, notification.id, now=NOW)
    assert read.read_at is not None
