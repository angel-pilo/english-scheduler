from enum import Enum


class UserRole(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"


class PermissionCode(str, Enum):
    ORGANIZATIONS_MANAGE = "organizations.manage"
    BRANCHES_MANAGE = "branches.manage"
    ROOMS_MANAGE = "rooms.manage"
    USERS_INVITE = "users.invite"
    USERS_PERMISSIONS_MANAGE = "users.permissions.manage"
    LEVELS_MANAGE = "levels.manage"
    CURRICULUM_MANAGE = "curriculum.manage"
    SCHEDULE_MANAGE = "schedule.manage"
    BOOKINGS_MANAGE = "bookings.manage"
    PAYMENTS_MANAGE = "payments.manage"
    REPORTS_VIEW = "reports.view"
    ATTENDANCE_MANAGE = "attendance.manage"
    GRADES_MANAGE = "grades.manage"
    TEACHER_AVAILABILITY_MANAGE = "teacher.availability.manage"
    STUDENT_BOOKINGS_MANAGE = "student.bookings.manage"
    OWN_SCHEDULE_VIEW = "own.schedule.view"
    OWN_PROFILE_VIEW = "own.profile.view"
    STUDENTS_MANAGE = "students.manage"
    TEACHERS_MANAGE = "teachers.manage"
    STUDENT_PROGRESS_MANAGE = "student.progress.manage"


class StudentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    GRADUATED = "GRADUATED"
    WITHDRAWN = "WITHDRAWN"


class TeacherStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"


class TopicStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class TopicProgressStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ScheduleExceptionScope(str, Enum):
    ORGANIZATION = "ORGANIZATION"
    BRANCH = "BRANCH"
    ROOM = "ROOM"
    TEACHER = "TEACHER"


class ClassSessionStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CANCELLED = "CANCELLED"


class BookingStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLATION_PENDING = "CANCELLATION_PENDING"
    CANCELLED = "CANCELLED"


class BookingEventType(str, Enum):
    CREATED = "CREATED"
    CANCELLED = "CANCELLED"
    LATE_CANCELLATION_REQUESTED = "LATE_CANCELLATION_REQUESTED"
    LATE_CANCELLATION_APPROVED = "LATE_CANCELLATION_APPROVED"
    LATE_CANCELLATION_REJECTED = "LATE_CANCELLATION_REJECTED"
    ADMIN_CREATED = "ADMIN_CREATED"
    ADMIN_CANCELLED = "ADMIN_CANCELLED"


class WaitlistStatus(str, Enum):
    WAITING = "WAITING"
    OFFERED = "OFFERED"
    ACCEPTED = "ACCEPTED"
    EXPIRED = "EXPIRED"
    LEFT = "LEFT"


class NotificationType(str, Enum):
    WAITLIST_PLACE_AVAILABLE = "WAITLIST_PLACE_AVAILABLE"
    WAITLIST_OFFER_EXPIRED = "WAITLIST_OFFER_EXPIRED"


class TeacherAssignmentMethod(str, Enum):
    AUTO_GENERATION = "AUTO_GENERATION"
    AUTO_RECOMMENDATION = "AUTO_RECOMMENDATION"
    MANUAL = "MANUAL"
