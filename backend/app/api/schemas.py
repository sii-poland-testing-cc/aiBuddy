"""Shared Pydantic schemas used across multiple API routes."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ─── Jira ─────────────────────────────────────────────────────────────────────

class JiraIssueIn(BaseModel):
    issue_key: str


class JiraTestIn(BaseModel):
    jira_url: str
    jira_user_email: str = ""
    jira_api_key: str


# ─── Projects ─────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = ""


class ProjectOut(BaseModel):
    project_id: str
    name: str
    description: str
    created_at: str
    file_count: int = 0


# ─── Files ────────────────────────────────────────────────────────────────────

class UploadedFile(BaseModel):
    filename: str
    file_path: str
    size_bytes: int
    project_id: str
    indexed: bool


class FileOut(BaseModel):
    filename: str
    file_path: str
    size_bytes: int
    indexed: bool
    uploaded_at: str


class AuditSelectionItem(BaseModel):
    id: str
    filename: str
    file_path: str
    source_type: str
    size_bytes: int
    uploaded_at: str
    last_used_in_audit_id: str | None
    last_used_in_audit_at: str | None
    selected: bool


# ─── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    project_id: str
    message: str
    file_paths: list[str] = []
    tier: str = "audit"                        # "audit" | "optimize" | "regenerate"
    audit_report: Optional[Dict[str, Any]] = None  # required for tier="optimize"


# ─── Requirements ─────────────────────────────────────────────────────────────

class ExtractRequest(BaseModel):
    message: str = ""  # optional user hint (e.g. "focus on payment module")


class RequirementUpdate(BaseModel):
    """Payload for human review / manual correction."""
    title: Optional[str] = None
    description: Optional[str] = None
    external_id: Optional[str] = None
    level: Optional[str] = None
    source_type: Optional[str] = None
    taxonomy: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    human_reviewed: Optional[bool] = None
    needs_review: Optional[bool] = None
    review_reason: Optional[str] = None


# ─── Mapping ──────────────────────────────────────────────────────────────────

class RunMappingRequest(BaseModel):
    file_paths: List[str] = []   # explicit TC file paths; empty = auto-load from DB
    message: str = ""            # optional user hint


class MappingVerification(BaseModel):
    human_verified: bool = True
    mapping_confidence: Optional[float] = None
    coverage_aspects: Optional[List[str]] = None
