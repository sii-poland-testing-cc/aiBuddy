"""Reusable SQLAlchemy query helpers."""

from sqlalchemy import or_

from app.db.models import ProjectFile


def audit_file_filter(project_id: str):
    """
    SQLAlchemy WHERE conditions for auto-selecting files in an audit.

    Policy (single source of truth — mirrored as a Python predicate in files.py):
      - source_type != 'file'  →  URL/Jira/Confluence live sources, always include
      - last_used_in_audit_id IS NULL  →  never audited, include

    Used by:
      app/api/routes/chat.py  — SQL query for auto-load on chat request
      app/api/routes/files.py — Python predicate _is_audit_selected() for the
                                audit-selection endpoint (operates on loaded rows)
    """
    return [
        ProjectFile.project_id == project_id,
        or_(
            ProjectFile.last_used_in_audit_id.is_(None),
            ProjectFile.source_type != "file",
        ),
    ]
