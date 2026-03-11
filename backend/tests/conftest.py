"""
conftest.py — shared pytest config and fixtures.
Env vars MUST be set before any app modules are imported.
"""
import os
import tempfile

# ─── Override paths BEFORE any app module is imported ─────────────────────────
_TEST_TMP = tempfile.mkdtemp(prefix="ai_buddy_test_")
os.environ.setdefault("LLM_PROVIDER", "anthropic")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-placeholder")
os.environ["CHROMA_PERSIST_DIR"] = os.path.join(_TEST_TMP, "chroma")
os.environ["UPLOAD_DIR"] = os.path.join(_TEST_TMP, "uploads")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_TMP}/test.db"

import pytest


@pytest.fixture
def sample_docx_path():
    """Path to the existing sample fixture."""
    from pathlib import Path
    p = Path(__file__).parent / "fixtures" / "sample_domain.docx"
    assert p.exists(), f"Fixture not found: {p}"
    return str(p)


def _make_minimal_pdf(text: str = "QA Test Document Content") -> bytes:
    """Build a minimal valid PDF with one line of text (no external deps)."""
    safe = text.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode()

    hdr  = b"%PDF-1.4\n"
    obj1 = b"1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n"
    obj2 = b"2 0 obj\n<</Type/Pages/Kids[3 0 R]/Count 1>>\nendobj\n"
    obj3 = b"3 0 obj\n<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>\nendobj\n"
    obj4 = (b"4 0 obj\n<</Length " + str(len(stream)).encode()
            + b">>\nstream\n" + stream + b"\nendstream\nendobj\n")
    obj5 = b"5 0 obj\n<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>\nendobj\n"

    body = hdr + obj1 + obj2 + obj3 + obj4 + obj5
    o1 = len(hdr)
    o2 = o1 + len(obj1)
    o3 = o2 + len(obj2)
    o4 = o3 + len(obj3)
    o5 = o4 + len(obj4)

    xref_pos = len(body)
    xref = (
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        + f"{o1:010d} 00000 n \n".encode()
        + f"{o2:010d} 00000 n \n".encode()
        + f"{o3:010d} 00000 n \n".encode()
        + f"{o4:010d} 00000 n \n".encode()
        + f"{o5:010d} 00000 n \n".encode()
    )
    trailer = (
        b"trailer\n<</Size 6/Root 1 0 R>>\nstartxref\n"
        + str(xref_pos).encode()
        + b"\n%%EOF\n"
    )
    return body + xref + trailer


@pytest.fixture
def sample_pdf_path(tmp_path):
    """Create a minimal one-page PDF with text and return its path."""
    pdf_bytes = _make_minimal_pdf("QA Test Document: coverage defect regression severity")
    p = tmp_path / "sample_test.pdf"
    p.write_bytes(pdf_bytes)
    return str(p)


@pytest.fixture
def app_client():
    """FastAPI TestClient with app lifespan running."""
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
