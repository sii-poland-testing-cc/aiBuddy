"""
Shared test-case file parser for audit and mapping workflows.

Supported formats: .xlsx, .csv, .json, .feature (Gherkin)
Returns a uniform list of dicts per test case.
"""

import json
from typing import Dict, List, Optional


async def parse_test_file(path: str) -> List[Dict]:
    """Parse a test-case file into a uniform list of dicts."""
    ext = path.rsplit(".", 1)[-1].lower()
    if ext in ("xlsx", "csv"):
        return await _parse_spreadsheet(path)
    elif ext == "json":
        return await _parse_json(path)
    elif ext == "feature":
        return await _parse_gherkin(path)
    return []


async def _parse_spreadsheet(path: str) -> List[Dict]:
    import pandas as pd
    df = pd.read_excel(path) if path.endswith(".xlsx") else pd.read_csv(path)
    return df.to_dict(orient="records")


async def _parse_json(path: str) -> List[Dict]:
    with open(path) as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


async def _parse_gherkin(path: str) -> List[Dict]:
    """Minimal Gherkin parser — replace with `gherkin` package in production."""
    cases = []
    with open(path) as f:
        scenario, steps = None, []
        for line in f:
            line = line.strip()
            if line.startswith("Scenario"):
                if scenario:
                    cases.append({"name": scenario, "steps": steps, "tags": []})
                scenario, steps = line.split(":", 1)[1].strip(), []
            elif line.startswith(("Given", "When", "Then", "And")):
                steps.append(line)
        if scenario:
            cases.append({"name": scenario, "steps": steps, "tags": []})
    return cases


def build_tc_text(case: Dict) -> Optional[str]:
    """Concatenate key fields for embedding; title weighted 2× for similarity."""
    title    = str(case.get("title")           or case.get("name")       or "").strip()
    steps    = str(case.get("steps")           or case.get("test_steps") or "").strip()
    expected = str(case.get("expected_result") or case.get("assertions") or "").strip()
    if not title and not steps and not expected:
        return None
    return f"{title}. {title}. {steps}. {expected}"
