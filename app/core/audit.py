from contextvars import ContextVar
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional, Dict, Any, List
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

# Context variable tracking current request's actor info
_audit_actor_ctx: ContextVar[Optional[Dict[str, Any]]] = ContextVar("audit_actor_ctx", default=None)

SENSITIVE_ATTRS = {"password_hash", "otp_hash", "secret_key", "jwt_secret_key"}
IGNORED_ATTRS = {"created_at", "updated_at"}
IGNORED_TABLES = {"audit_logs", "alembic_version", "otp_verifications"}


def set_audit_actor(
    user_id: Optional[int] = None,
    email: Optional[str] = None,
    role: Optional[str] = None,
    ip_address: Optional[str] = None
) -> None:
    _audit_actor_ctx.set({
        "actor_id": user_id,
        "actor_email": email,
        "actor_role": role,
        "ip_address": ip_address
    })


def get_audit_actor() -> Dict[str, Any]:
    actor = _audit_actor_ctx.get()
    return actor or {
        "actor_id": None,
        "actor_email": "system",
        "actor_role": "system",
        "ip_address": None
    }


def clear_audit_actor() -> None:
    _audit_actor_ctx.set(None)


def serialize_val(val: Any) -> Any:
    if val is None or isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (list, tuple)):
        return [serialize_val(v) for v in val]
    if isinstance(val, dict):
        return {str(k): serialize_val(v) for k, v in val.items()}
    return str(val)


def get_record_name(obj: Any) -> Optional[str]:
    for attr in ("title", "name", "city_name", "path", "email"):
        if hasattr(obj, attr):
            val = getattr(obj, attr)
            if val is not None:
                return str(val)[:255]
    table = getattr(obj, "__tablename__", "record")
    obj_id = getattr(obj, "id", "")
    return f"{table} #{obj_id}"


def setup_audit_logging(session_factory):
    """Hooks SQLAlchemy session flush events to automatically generate audit logs."""
    from app.db.models.audit_log import AuditLog

    @event.listens_for(session_factory, "before_flush")
    def handle_before_flush(session: Session, flush_context, instances):
        if getattr(session, "_audit_disabled", False):
            return

        actor = get_audit_actor()

        # 1. Track objects being newly created (to record after flush when ID is assigned)
        pending_creates = session.info.setdefault("_pending_audit_creates", [])
        for obj in session.new:
            if isinstance(obj, AuditLog) or getattr(obj, "__tablename__", "") in IGNORED_TABLES:
                continue
            pending_creates.append(obj)

        # 2. Track updates and soft deletes on dirty objects
        for obj in list(session.dirty):
            if isinstance(obj, AuditLog):
                continue
            table_name = getattr(obj, "__tablename__", None)
            if not table_name or table_name in IGNORED_TABLES:
                continue

            insp = inspect(obj)
            changes = {}
            action = "UPDATE"

            # Check column attributes
            for attr in insp.attrs:
                if attr.key in IGNORED_ATTRS or attr.key == "id":
                    continue
                # Only check column attributes, skip relationship collections
                if attr.key not in [c.key for c in insp.mapper.column_attrs]:
                    continue

                hist = attr.load_history()
                if hist.has_changes():
                    old_raw = hist.deleted[0] if hist.deleted else None
                    new_raw = hist.added[0] if hist.added else None

                    # Redact sensitive data
                    if attr.key in SENSITIVE_ATTRS:
                        old_val = "[REDACTED]" if old_raw is not None else None
                        new_val = "[REDACTED]" if new_raw is not None else None
                    else:
                        old_val = serialize_val(old_raw)
                        new_val = serialize_val(new_raw)

                    changes[attr.key] = {"old": old_val, "new": new_val}

                    if attr.key == "is_deleted":
                        if new_raw is True and not old_raw:
                            action = "SOFT_DELETE"
                        elif new_raw is False and old_raw:
                            action = "RESTORE"

            if changes:
                log_entry = AuditLog(
                    table_name=table_name,
                    record_id=obj.id if hasattr(obj, "id") and obj.id is not None else 0,
                    record_name=get_record_name(obj),
                    action=action,
                    changes=changes,
                    actor_id=actor.get("actor_id"),
                    actor_email=actor.get("actor_email"),
                    actor_role=actor.get("actor_role"),
                    ip_address=actor.get("ip_address"),
                    created_at=datetime.now(timezone.utc)
                )
                session.add(log_entry)

    @event.listens_for(session_factory, "after_flush")
    def handle_after_flush(session: Session, flush_context):
        if getattr(session, "_audit_disabled", False):
            return

        pending_creates = session.info.pop("_pending_audit_creates", [])
        if not pending_creates:
            return

        actor = get_audit_actor()
        for obj in pending_creates:
            table_name = getattr(obj, "__tablename__", None)
            if not table_name or table_name in IGNORED_TABLES:
                continue

            insp = inspect(obj)
            initial_values = {}
            for attr in insp.attrs:
                if attr.key in IGNORED_ATTRS or attr.key == "id":
                    continue
                if attr.key not in [c.key for c in insp.mapper.column_attrs]:
                    continue

                raw_val = getattr(obj, attr.key, None)
                if attr.key in SENSITIVE_ATTRS:
                    val = "[REDACTED]" if raw_val is not None else None
                else:
                    val = serialize_val(raw_val)

                if val is not None:
                    initial_values[attr.key] = {"old": None, "new": val}

            log_entry = AuditLog(
                table_name=table_name,
                record_id=obj.id if hasattr(obj, "id") and obj.id is not None else 0,
                record_name=get_record_name(obj),
                action="CREATE",
                changes=initial_values,
                actor_id=actor.get("actor_id"),
                actor_email=actor.get("actor_email"),
                actor_role=actor.get("actor_role"),
                ip_address=actor.get("ip_address"),
                created_at=datetime.now(timezone.utc)
            )
            session.add(log_entry)

