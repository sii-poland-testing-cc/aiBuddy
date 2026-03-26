"""
Jira REST API client with depth-aware context fetching.

Depth model:
  0 — the linked item itself
  1 — parent (epic/feature/initiative), children (subtasks), linked issues
  2 — bugs that are linked to depth-1 issues (bug chains only)
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger("ai_buddy.jira")


# ── Public API ────────────────────────────────────────────────────────────────

class JiraClient:
    def __init__(self, jira_url: str, user_email: str, api_key: str):
        self.base_url = jira_url.rstrip("/")
        self._auth = (user_email, api_key) if user_email else None
        self._headers: dict = {} if self._auth else {"Authorization": f"Bearer {api_key}"}

    async def test_connection(self) -> dict:
        """Test connectivity to Jira. Returns {ok, status_code, detail}."""
        if not self.base_url.startswith(("http://", "https://")):
            return {"ok": False, "status_code": None, "detail": "Nieprawidłowy adres — URL musi zaczynać się od http:// lub https://"}

        url = f"{self.base_url}/rest/api/2/project?maxResults=1"
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(url, auth=self._auth, headers=self._headers)

            if resp.status_code == 401:
                return {"ok": False, "status_code": resp.status_code, "detail": "Nieautoryzowany. Sprawdź dane dostępowe i scope (wymagany: read:jira-work)."}
            if resp.status_code == 403:
                return {"ok": False, "status_code": resp.status_code, "detail": "Brak uprawnień. Sprawdź czy token ma scope read:jira-work."}
            if resp.status_code == 404:
                return {"ok": False, "status_code": resp.status_code, "detail": "Nie znaleziono endpointu. Sprawdź adres serwera Jira."}
            if not resp.is_success:
                return {"ok": False, "status_code": resp.status_code, "detail": f"Błąd serwera Jira: {resp.status_code}"}

            projects = resp.json()
            count = len(projects) if isinstance(projects, list) else 0
            return {"ok": True, "status_code": resp.status_code, "detail": f"Połączono. Dostępne projekty: {count}"}

        except httpx.ConnectError:
            return {"ok": False, "status_code": None, "detail": "Nie można nawiązać połączenia. Sprawdź adres serwera."}
        except httpx.TimeoutException:
            return {"ok": False, "status_code": None, "detail": "Przekroczono czas połączenia (8s)."}
        except httpx.InvalidURL as exc:
            return {"ok": False, "status_code": None, "detail": f"Nieprawidłowy adres URL: {exc}. Sprawdzany URL: {url!r}"}
        except Exception as exc:
            return {"ok": False, "status_code": None, "detail": str(exc)}

    async def get_issue(self, key: str) -> Optional[dict]:
        """Fetch a single issue. Returns None on 404 or any HTTP error."""
        url = f"{self.base_url}/rest/api/2/issue/{key}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, auth=self._auth, headers=self._headers)
        except httpx.HTTPError as exc:
            logger.warning("HTTP error fetching issue %s: %s", key, exc)
            return None
        if not resp.is_success:
            if resp.status_code != 404:
                logger.warning("Unexpected status %s fetching issue %s", resp.status_code, key)
            return None
        return resp.json()

    async def search_issues(self, jql: str, max_results: int = 50) -> list[dict]:
        """Run a JQL search via POST (GET /search is deprecated/gone on Atlassian Cloud)."""
        url = f"{self.base_url}/rest/api/3/issue/search"
        payload = {"jql": jql, "maxResults": max_results}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                auth=self._auth,
                headers={**self._headers, "Content-Type": "application/json"},
                json=payload,
            )
        if not resp.is_success:
            logger.warning("Jira search failed (jql=%r): %s", jql, resp.status_code)
            return []
        return resp.json().get("issues", [])

    async def get_epic_issues(self, epic_key: str, max_results: int = 50) -> list[dict]:
        """Fetch issues belonging to an Epic via the Agile API (classic projects)."""
        url = f"{self.base_url}/rest/agile/1.0/epic/{epic_key}/issue"
        params = {"maxResults": max_results}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, auth=self._auth, headers=self._headers, params=params)
        if not resp.is_success:
            logger.warning("Agile epic issues failed (%s): %s", epic_key, resp.status_code)
            return []
        return resp.json().get("issues", [])

    async def fetch_with_context(self, root_key: str) -> Optional[dict]:
        """
        Fetch root issue + depth-1 relations + depth-2 bug chains.
        Returns None if root issue does not exist.
        """
        raw = await self.get_issue(root_key)
        if raw is None:
            return None

        root = _extract_issue(raw)
        result: dict = {"root": root, "parent": None, "children": [], "linked": []}
        seen: set[str] = {root_key}
        fields = raw.get("fields", {})

        # ── Depth 1: parent ───────────────────────────────────────────────────
        if parent_ref := fields.get("parent"):
            parent_raw = await self.get_issue(parent_ref["key"])
            if parent_raw:
                result["parent"] = _extract_issue(parent_raw)
                seen.add(parent_ref["key"])

        # ── Depth 1: children ─────────────────────────────────────────────────
        # Strategy (first that yields results wins):
        #   1. JQL `parent = KEY`              — next-gen / company-managed hierarchy
        #   2. Agile API epic/{key}/issue      — classic projects, Epic→Story
        #   3. fields.subtasks                 — subtask-type children (Story→Subtask)
        # Search results carry limited fields; each child is re-fetched via
        # get_issue to get full field data (description, links, etc.).
        child_keys: list[str] = []

        hits = await self.search_issues(f'parent = "{root_key}"')
        child_keys = [h["key"] for h in hits if h["key"] not in seen]

        if not child_keys and root["type"].lower() == "epic":
            hits = await self.get_epic_issues(root_key)
            child_keys = [h["key"] for h in hits if h["key"] not in seen]

        # subtasks fallback (Jira Server / Story→Subtask)
        for s in fields.get("subtasks", []):
            if s["key"] not in seen and s["key"] not in child_keys:
                child_keys.append(s["key"])

        for child_key in child_keys:
            if child_key in seen:
                continue
            seen.add(child_key)
            child_raw = await self.get_issue(child_key)
            if child_raw:
                result["children"].append(_extract_issue(child_raw))

        # ── Depth 1: linked issues ────────────────────────────────────────────
        depth1_bugs: list[tuple[str, dict]] = []  # (key, raw) for depth-2 traversal
        for link in fields.get("issuelinks", []):
            ref = link.get("inwardIssue") or link.get("outwardIssue")
            if not ref or ref["key"] in seen:
                continue
            seen.add(ref["key"])
            linked_raw = await self.get_issue(ref["key"])
            if linked_raw is None:
                continue
            info = _extract_issue(linked_raw)
            direction = "inward" if "inwardIssue" in link else "outward"
            info["link_type"] = link.get("type", {}).get(direction, "")
            result["linked"].append(info)
            if info["type"].lower() == "bug":
                depth1_bugs.append((ref["key"], linked_raw))

        # ── Depth 2: bugs linked to depth-1 bugs ─────────────────────────────
        for _bug_key, bug_raw in depth1_bugs:
            for link in bug_raw.get("fields", {}).get("issuelinks", []):
                ref = link.get("inwardIssue") or link.get("outwardIssue")
                if not ref or ref["key"] in seen:
                    continue
                nested_raw = await self.get_issue(ref["key"])
                if nested_raw is None:
                    continue
                nested = _extract_issue(nested_raw)
                seen.add(ref["key"])
                if nested["type"].lower() != "bug":
                    continue
                direction = "inward" if "inwardIssue" in link else "outward"
                nested["link_type"] = link.get("type", {}).get(direction, "")
                result["linked"].append(nested)

        return result


# ── Markdown formatter ────────────────────────────────────────────────────────

def to_markdown(data: dict) -> str:
    lines: list[str] = []

    def _issue_block(issue: dict, heading: str) -> None:
        lines.append(heading)
        lines.append("")
        meta = [f"**Type**: {issue['type']}", f"**Status**: {issue['status']}"]
        if issue["priority"]:
            meta.append(f"**Priority**: {issue['priority']}")
        if issue["labels"]:
            meta.append(f"**Labels**: {', '.join(issue['labels'])}")
        lines.append(" | ".join(meta))
        lines.append("")
        if issue["description"]:
            lines.append(issue["description"])
            lines.append("")

    root = data["root"]
    _issue_block(root, f"# {root['key']}: {root['summary']}")

    if data["parent"]:
        p = data["parent"]
        lines.append("---")
        lines.append("")
        lines.append("## Parent Context")
        lines.append("")
        _issue_block(p, f"### {p['key']}: {p['summary']}")

    if data["children"]:
        lines.append("---")
        lines.append("")
        lines.append("## Child Items")
        lines.append("")
        for c in data["children"]:
            _issue_block(c, f"### {c['key']}: {c['summary']}")

    if data["linked"]:
        lines.append("---")
        lines.append("")
        lines.append("## Linked Issues")
        lines.append("")
        for li in data["linked"]:
            tag = f"[{li['link_type']}] " if li.get("link_type") else ""
            _issue_block(li, f"### {tag}{li['key']}: {li['summary']}")

    return "\n".join(lines)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_issue(raw: dict) -> dict:
    fields = raw.get("fields", {})
    return {
        "key": raw.get("key", ""),
        "summary": fields.get("summary", ""),
        "description": _text(fields.get("description")),
        "status": (fields.get("status") or {}).get("name", ""),
        "type": (fields.get("issuetype") or {}).get("name", ""),
        "priority": (fields.get("priority") or {}).get("name", ""),
        "labels": fields.get("labels", []),
    }


def _text(value) -> str:
    """Extract plain text from a Jira field (plain string or Atlassian Document Format)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and value.get("type") == "doc":
        return _adf_to_text(value).strip()
    return str(value)


def _adf_to_text(node: dict) -> str:
    """Recursively flatten Atlassian Document Format to plain text."""
    block_types = {
        "paragraph", "heading", "bulletList", "orderedList",
        "listItem", "blockquote", "codeBlock", "rule",
    }
    parts: list[str] = []
    if text := node.get("text"):
        parts.append(text)
    for child in node.get("content", []):
        parts.append(_adf_to_text(child))
    joined = "".join(filter(None, parts))
    return ("\n" + joined) if (node.get("type") in block_types and joined) else joined
