"""Application enums shared by models and future services."""

from enum import StrEnum


class UserRole(StrEnum):
    ADMINISTRATOR = "ADMINISTRATOR"
    DOCUMENT_OWNER = "DOCUMENT_OWNER"
    VIEWER = "VIEWER"


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class PermissionLevel(StrEnum):
    READ = "READ"
    EDIT = "EDIT"


class DocumentAccessLevel(StrEnum):
    """Effective access resolved for a user on a specific document."""

    OWNER = "OWNER"
    EDIT = "EDIT"
    READ = "READ"
    ADMINISTRATOR = "ADMINISTRATOR"


class AuditOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    DENIED = "DENIED"
    FAILURE = "FAILURE"


class AuditAction(StrEnum):
    """Known audit actions. The database column stays extensible for later phases."""

    USER_REGISTERED = "USER_REGISTERED"
    USER_LOGIN = "USER_LOGIN"
    USER_LOGIN_FAILED = "USER_LOGIN_FAILED"
    DOCUMENT_UPLOAD = "DOCUMENT_UPLOAD"
    DOCUMENT_DOWNLOAD = "DOCUMENT_DOWNLOAD"
    DOCUMENT_VIEW = "DOCUMENT_VIEW"
    DOCUMENT_EDIT = "DOCUMENT_EDIT"
    DOCUMENT_DELETE = "DOCUMENT_DELETE"
    PERMISSION_GRANTED = "PERMISSION_GRANTED"
    PERMISSION_UPDATED = "PERMISSION_UPDATED"
    PERMISSION_REVOKED = "PERMISSION_REVOKED"
    ACCESS_DENIED = "ACCESS_DENIED"
