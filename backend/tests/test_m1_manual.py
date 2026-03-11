"""
M1 Context Builder — manual end-to-end test
============================================
Usage (from backend/):
    python tests/test_m1_manual.py
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

BASE = "http://localhost:8000"
PROJECT_ID = "test-m1-manual"
FIXTURE = Path(__file__).parent / "fixtures" / "sample_domain.docx"


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=120) as client:

        # ── 1. POST /api/context/{id}/build ───────────────────────────────────
        print("=" * 60)
        print(f"POST /api/context/{PROJECT_ID}/build")
        print("=" * 60)

        with FIXTURE.open("rb") as fh:
            response = await client.post(
                f"/api/context/{PROJECT_ID}/build",
                files={"files": (FIXTURE.name, fh, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )

        if response.status_code != 200:
            print(f"ERROR {response.status_code}: {response.text}")
            sys.exit(1)

        # Read SSE stream
        final_result = None
        print("\n--- SSE events ---")
        for line in response.text.splitlines():
            if not line.startswith("data: "):
                continue
            payload = line[6:].strip()
            if payload == "[DONE]":
                print("[DONE]")
                break
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue

            etype = event.get("type")
            data = event.get("data", {})

            if etype == "progress":
                bar = "#" * int(data.get("progress", 0) * 20)
                pct = int(data.get("progress", 0) * 100)
                print(f"  [{pct:3d}%] [{bar:<20}] {data.get('stage','?'):8s}  {data.get('message','')}")
            elif etype == "result":
                final_result = data
                print(f"  [RESULT] project_id={data.get('project_id')}  rag_ready={data.get('rag_ready')}")
            elif etype == "error":
                print(f"  [ERROR] {data.get('message')}")
                sys.exit(1)

        # ── 2. GET /api/context/{id}/status ───────────────────────────────────
        print("\n" + "=" * 60)
        print(f"GET /api/context/{PROJECT_ID}/status")
        print("=" * 60)
        r = await client.get(f"/api/context/{PROJECT_ID}/status")
        status = r.json()
        print(json.dumps(status, indent=2))

        # ── 3. GET /api/context/{id}/mindmap ──────────────────────────────────
        print("\n" + "=" * 60)
        print(f"GET /api/context/{PROJECT_ID}/mindmap")
        print("=" * 60)
        r = await client.get(f"/api/context/{PROJECT_ID}/mindmap")
        if r.status_code == 404:
            print("  404 — mindmap not available")
            mindmap = {"nodes": [], "edges": []}
        else:
            mindmap = r.json()
            print(f"  nodes ({len(mindmap.get('nodes', []))}):")
            for n in mindmap.get("nodes", [])[:5]:
                print(f"    • [{n.get('type','?'):10s}] {n.get('label','')}")
            if len(mindmap.get("nodes", [])) > 5:
                print(f"    … and {len(mindmap['nodes']) - 5} more")
            print(f"  edges ({len(mindmap.get('edges', []))}):")
            for e in mindmap.get("edges", [])[:5]:
                print(f"    • {e.get('source')} --[{e.get('label','')}]--> {e.get('target')}")

        # ── 4. GET /api/context/{id}/glossary ─────────────────────────────────
        print("\n" + "=" * 60)
        print(f"GET /api/context/{PROJECT_ID}/glossary")
        print("=" * 60)
        r = await client.get(f"/api/context/{PROJECT_ID}/glossary")
        if r.status_code == 404:
            print("  404 — glossary not available")
            glossary = []
        else:
            glossary = r.json()
            for term in glossary[:5]:
                print(f"  • {term.get('term','?')}: {term.get('definition','')[:80]}")
            if len(glossary) > 5:
                print(f"  … and {len(glossary) - 5} more terms")

        # ── Summary ───────────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  rag_ready:       {status.get('rag_ready')}")
        print(f"  artefacts_ready: {status.get('artefacts_ready')}")
        stats = status.get("stats") or (final_result or {}).get("stats") or {}
        print(f"  entities:        {stats.get('entity_count', '?')}")
        print(f"  relations:       {stats.get('relation_count', '?')}")
        print(f"  glossary terms:  {len(glossary)}")
        print(f"  mind map nodes:  {len(mindmap.get('nodes', []))}")
        print(f"  mind map edges:  {len(mindmap.get('edges', []))}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
