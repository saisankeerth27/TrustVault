from app.db.base import Base
from app.models import (  # noqa: F401
    AuditEvent,
    Document,
    DocumentPermission,
    RefreshToken,
    User,
)


def test_all_core_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "users",
        "documents",
        "document_permissions",
        "document_versions",
        "audit_events",
        "refresh_tokens",
    }


def test_users_columns_and_uniqueness() -> None:
    table = Base.metadata.tables["users"]

    assert set(table.columns.keys()) == {
        "id",
        "name",
        "email",
        "password_hash",
        "role",
        "status",
        "last_login_at",
        "created_at",
        "updated_at",
    }
    assert any(
        constraint.name == "uq_users_email"
        for constraint in table.constraints
    )
    role_constraint = next(
        constraint
        for constraint in table.constraints
        if constraint.name == "ck_users_role"
    )
    assert "ADMINISTRATOR" in str(role_constraint.sqltext)
    assert "USER" in str(role_constraint.sqltext)
    assert "VIEWER" not in str(role_constraint.sqltext)


def test_documents_columns_and_constraints() -> None:
    table = Base.metadata.tables["documents"]

    assert {
        "owner_id",
        "storage_key",
        "checksum",
        "next_version_number",
        "deleted_at",
    } <= set(table.columns.keys())
    constraint_names = {constraint.name for constraint in table.constraints}
    assert "ck_documents_file_size_nonnegative" in constraint_names
    assert "ck_documents_next_version_number_minimum" in constraint_names
    assert "ck_documents_storage_key_not_url" in constraint_names

    index_names = {index.name for index in table.indexes}
    assert {
        "ix_documents_owner_id",
        "ix_documents_category",
        "ix_documents_created_at",
        "ix_documents_name_trgm",
        "ix_documents_owner_active",
    } <= index_names


def test_document_versions_track_immutable_content_history() -> None:
    table = Base.metadata.tables["document_versions"]

    assert {
        "document_id",
        "version_number",
        "storage_key",
        "original_filename",
        "mime_type",
        "file_size",
        "checksum",
        "uploaded_by",
        "change_summary",
        "is_current",
        "created_at",
    } <= set(table.columns.keys())

    foreign_keys = {
        fk.parent.name: fk.ondelete
        for fk in table.foreign_key_constraints
        for fk in fk.elements
    }
    assert foreign_keys["document_id"] == "CASCADE"
    assert foreign_keys["uploaded_by"] == "SET NULL"

    constraint_names = {constraint.name for constraint in table.constraints}
    assert {
        "ck_document_versions_file_size_nonnegative",
        "ck_document_versions_storage_key_not_url",
        "ck_document_versions_checksum_sha256",
        "uq_document_versions_document_number",
        "uq_document_versions_storage_key",
    } <= constraint_names

    index_names = {index.name for index in table.indexes}
    assert {
        "ix_document_versions_document_id",
        "ix_document_versions_uploaded_by",
        "ix_document_versions_created_at",
        "uq_document_versions_current",
    } <= index_names


def test_permissions_prevent_duplicate_active_grants() -> None:
    table = Base.metadata.tables["document_permissions"]
    unique_indexes = {index.name for index in table.indexes if index.unique}

    assert "uq_document_permissions_active" in unique_indexes


def test_audit_events_use_set_null_foreign_keys() -> None:
    table = Base.metadata.tables["audit_events"]
    foreign_keys = {
        fk.parent.name: fk.ondelete for fk in table.foreign_key_constraints for fk in fk.elements
    }

    assert foreign_keys["actor_id"] == "SET NULL"
    assert foreign_keys["document_id"] == "SET NULL"


def test_refresh_tokens_store_hashes_and_cascade_with_users() -> None:
    table = Base.metadata.tables["refresh_tokens"]

    assert {
        "id",
        "user_id",
        "family_id",
        "token_hash",
        "expires_at",
        "created_at",
        "revoked_at",
        "replaced_by_id",
    } == set(table.columns.keys())

    foreign_keys = {
        fk.parent.name: fk.ondelete for fk in table.foreign_key_constraints for fk in fk.elements
    }
    assert foreign_keys["user_id"] == "CASCADE"
    assert foreign_keys["replaced_by_id"] == "SET NULL"

    index_names = {index.name for index in table.indexes}
    assert {
        "ix_refresh_tokens_user_id",
        "ix_refresh_tokens_family_id",
        "ix_refresh_tokens_expires_at",
        "ix_refresh_tokens_active_family",
    } <= index_names
