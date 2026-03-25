"""
Shared helpers for Faza 5+6 mapping tests.
Imported by test_mapping.py and test_mapping_extended.py.
"""
import json
from pathlib import Path
from unittest.mock import patch

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_CSV = FIXTURES_DIR / "sample_tests.csv"


def create_project(app_client, name: str = "mapping-test") -> str:
    r = app_client.post("/api/projects/", json={"name": name})
    assert r.status_code in (200, 201)
    return r.json()["project_id"]


def upload_csv(app_client, project_id: str, name: str = "sample_tests.csv") -> str:
    """Upload sample_tests.csv and return the stored file path."""
    with SAMPLE_CSV.open("rb") as fh:
        r = app_client.post(
            f"/api/files/{project_id}/upload?source_type=file",
            files={"files": (name, fh, "text/csv")},
        )
    assert r.status_code == 200, f"Upload failed: {r.text}"
    uploaded = r.json()
    if isinstance(uploaded, list) and uploaded:
        return uploaded[0].get("file_path", "")
    return ""


def run_mapping(app_client, project_id: str, file_path: str = "") -> dict:
    """Run mapping workflow (no LLM — embedding-only mode) and return result data."""
    with patch("app.api.routes.mapping.get_llm", return_value=None):
        r = app_client.post(
            f"/api/mapping/{project_id}/run",
            json={"file_paths": [file_path] if file_path else [], "message": ""},
        )
    assert r.status_code == 200, f"Mapping run failed: {r.text}"
    for line in r.text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            break
        try:
            ev = json.loads(payload)
            if ev.get("type") == "result":
                return ev["data"]
        except (json.JSONDecodeError, KeyError):
            continue
    return {}
