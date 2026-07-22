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
