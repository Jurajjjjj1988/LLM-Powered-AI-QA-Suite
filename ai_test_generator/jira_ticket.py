"""
Parse a pasted / fetched ticket into a structured ``JiraTicket`` — offline, deterministic.

The tool's real job is to generate tests FROM a work item's acceptance criteria, not
from a vague one-liner. This module turns the messy markdown of a real ticket (a Jira
export, or a ``gh issue view`` GitHub issue) into a structured ticket so the generator
can produce one traceable test per criterion.

Deliberately lenient about how a human wrote the ticket, but careful not to mis-parse:
- Section headings match several spellings (``## Acceptance Criteria``, ``**AC**``,
  ``Definition of Done``, ``DoD`` …). A ``#``/``**bold**`` line is always a heading; a
  plain colon-terminated line is a heading ONLY when it names a known section (so a
  criterion that ends with ``:`` is not mistaken for one).
- List items may be ``-`` / ``*`` / ``+`` bullets, ``1.`` / ``1)`` numbers, or GitHub
  task-list checkboxes ``- [ ]`` / ``- [x]`` (the checkbox marker is stripped). Wrapped
  continuation lines and indented sub-bullets fold into their parent criterion.
- Lines inside fenced code blocks (``` ``` ``` / ``~~~``) are ignored, so a documentation
  checkbox in an example block does not leak in as a criterion.
- A project key is taken only from the LEADING/bracketed title position and never from a
  standards token like ``ISO-8601`` / ``UTF-8`` / ``SHA-256``.

Raises :class:`TicketParseError` when nothing test-worthy can be extracted — per the
project rule *never proceed without complete information*.
"""

from __future__ import annotations

import re

from common.exceptions import TicketParseError
from common.schemas import JiraTicket

# A leading (optionally bracketed) Jira-style key: "PROJ-123" / "[PROJ-123]".
_JIRA_KEY_LEADING = re.compile(r"^\[?([A-Z][A-Z0-9]+)-(\d+)\]?")
# A GitHub issue number like #42 (fallback key when no Jira key is present).
_GH_NUMBER = re.compile(r"#(\d+)\b")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]")
_FENCE = re.compile(r"^\s*(?:```|~~~)")

# Uppercase tokens that look like a key (LETTERS-digits) but are standards/abbreviations.
_STD_TOKENS = frozenset(
    {
        "ISO",
        "UTF",
        "SHA",
        "MD",
        "RFC",
        "COVID",
        "HTTP",
        "HTTPS",
        "IP",
        "IPV",
        "OAUTH",
        "SSL",
        "TLS",
        "API",
        "CVE",
        "AES",
        "RSA",
        "UTC",
        "GB",
        "MB",
        "KB",
    }
)

_AC_HEADINGS = ("acceptance criteria", "acceptance", "ac", "criteria", "requirements", "scenarios")
_DOD_HEADINGS = ("definition of done", "dod", "done when")
_DESC_HEADINGS = ("description", "summary", "context", "story", "background", "overview")

_MAX_CRITERIA = 100
_MAX_ITEM_CHARS = 2000
_MAX_DESC_CHARS = 20000
_MAX_KEY_CHARS = 64
_MAX_SUMMARY_CHARS = 500


def _clean(text: str) -> str:
    """Strip control characters (terminal-escape safety) and collapse whitespace."""
    return re.sub(r"\s+", " ", _CONTROL_CHARS.sub("", text)).strip()


def _as_list_item(line: str) -> str | None:
    """Return the item text if *line* is a bullet / number / checkbox item, else None."""
    m = re.match(r"^(?:[-*+]|\d+[.)])\s+(.*)$", line.strip())
    if not m:
        return None
    item = re.sub(r"^\[[ xX]\]\s*", "", m.group(1)).strip()
    return item or None


def _is_checkbox(line: str) -> bool:
    return bool(re.match(r"^\s*[-*+]\s*\[[ xX]\]", line))


def _classify(heading: str) -> str | None:
    """Map a lowercased heading to a section kind, or None if it is not a known section."""
    for kind, names in (("ac", _AC_HEADINGS), ("dod", _DOD_HEADINGS), ("desc", _DESC_HEADINGS)):
        if any(heading == n or heading.startswith(n + " ") for n in names):
            return kind
    return None


def _heading_text(line: str) -> str | None:
    """Return the lowercased heading text if *line* is a section heading, else None.

    ``#`` and ``**bold**`` lines are always headings (they delimit a section). A plain
    colon-terminated line is only a heading when it names a known section — a trailing
    ``:`` alone is too weak a signal (a criterion frequently ends with a colon).
    """
    stripped = line.strip()
    if not stripped:
        return None
    is_hash = stripped.startswith("#")
    is_bold = stripped.startswith("**") and stripped.endswith("**")
    if is_hash or is_bold:
        text = stripped.lstrip("#").strip().strip("*").rstrip(":").strip()
        return re.sub(r"^\d+[.)]\s*", "", text).lower()  # '### 1. Acceptance Criteria'
    if stripped.endswith(":"):
        text = re.sub(r"^\d+[.)]\s*", "", stripped.rstrip(":").strip().strip("*")).lower()
        if _classify(text) is not None:
            return text
    return None


def _collect_entries(section_lines: list[str]) -> list[str]:
    """Turn the lines of a section into criteria, folding continuations into their parent.

    A base-level list item starts a new criterion; an indented sub-bullet or a wrapped
    prose line appends to the current one. A section with no list items at all yields its
    prose as a single criterion (so a Gherkin/prose 'Acceptance Criteria' still produces
    something rather than raising).
    """
    entries: list[str] = []
    for line in section_lines:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        item = _as_list_item(line)
        if item is not None and indent < 2:
            entries.append(item)
        elif item is not None:  # indented sub-bullet → continuation of the parent
            _append_continuation(entries, item)
        else:  # wrapped prose line
            _append_continuation(entries, line.strip())
    return entries


def _append_continuation(entries: list[str], text: str) -> None:
    if entries:
        entries[-1] = f"{entries[-1]} {text}"
    else:
        entries.append(text)


def _slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-").upper()
    return (slug[:60].strip("-")) or "TICKET"


def _extract_key_and_summary(lines: list[str]) -> tuple[str, str]:
    first = next((ln for ln in lines if ln.strip()), "")
    title = first.strip().lstrip("#").strip()
    if title.startswith("**") and title.endswith("**"):
        title = title.strip("*").strip()
    body = "\n".join(lines)

    key: str | None = None
    summary = title
    m = _JIRA_KEY_LEADING.match(title)
    if m and m.group(1) not in _STD_TOKENS:
        key = f"{m.group(1)}-{m.group(2)}"
        summary = title[m.end() :]
    else:
        gh = _GH_NUMBER.search(first) or _GH_NUMBER.search(body)
        if gh:
            key = f"GH-{gh.group(1)}"
        # else: leave summary as the title — never delete an ambiguous token from it.

    summary = _clean(_GH_NUMBER.sub("", summary).strip(" :#-[]"))
    # A bare section name ("Acceptance Criteria") is not a real title.
    cleaned_summary: str | None = (
        summary if summary and _classify(summary.lower()) is None else None
    )
    if key is None:
        key = _slug(cleaned_summary or title)
    summary = cleaned_summary or key
    return key[:_MAX_KEY_CHARS], summary[:_MAX_SUMMARY_CHARS]


def _bucket_line(
    buckets: dict[str, list[str]], section: str | None, raw: str, item: str | None
) -> None:
    """Append a non-heading line to its section bucket (ignores stray list items)."""
    if section in ("ac", "dod"):
        buckets[section].append(raw)
    elif item is None and raw.strip() and section in (None, "desc"):
        # Prose only — list items outside AC/DOD (nav, stray checklists) are ignored.
        buckets["desc"].append(raw.strip())


def _scan_sections(lines: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
    """Walk the ticket once, bucketing lines into (ac, dod, description, checkboxes).

    Tracks fenced code blocks (their lines are ignored) and the current section, and
    captures every task-list checkbox separately so a heading-less checklist can still
    supply the criteria.
    """
    buckets: dict[str, list[str]] = {"ac": [], "dod": [], "desc": []}
    checkboxes: list[str] = []
    section: str | None = None
    in_code = False

    for raw in lines:
        if _FENCE.match(raw):
            in_code = not in_code
            continue
        if in_code:
            continue

        item = _as_list_item(raw)
        if item is not None and _is_checkbox(raw):
            checkboxes.append(item)

        heading = None if item is not None else _heading_text(raw)
        if heading is not None:
            section = _classify(heading)
            continue

        _bucket_line(buckets, section, raw, item)

    return buckets["ac"], buckets["dod"], buckets["desc"], checkboxes


def parse_ticket(text: str) -> JiraTicket:
    """Parse raw ticket *text* (markdown / plain) into a structured :class:`JiraTicket`.

    Raises :class:`TicketParseError` if no acceptance criteria can be extracted.
    """
    if not text or not text.strip():
        raise TicketParseError("Ticket is empty — nothing to generate tests from.")

    lines = text.splitlines()
    key, summary = _extract_key_and_summary(lines)
    ac_lines, dod_lines, desc_lines, checkboxes = _scan_sections(lines)

    acceptance = _collect_entries(ac_lines)
    dod = _collect_entries(dod_lines)
    # Heading-less GitHub checklist → the checkboxes ARE the criteria.
    if not acceptance and checkboxes:
        acceptance = checkboxes

    acceptance = [c for c in (_clean(x)[:_MAX_ITEM_CHARS] for x in acceptance) if c][:_MAX_CRITERIA]
    dod = [d for d in (_clean(x)[:_MAX_ITEM_CHARS] for x in dod) if d][:_MAX_CRITERIA]

    if not acceptance:
        raise TicketParseError(
            f"Ticket {key!r} has no acceptance criteria. Add an 'Acceptance Criteria' "
            "section (bullets or checkboxes) so each criterion becomes a test."
        )

    description = _clean(" ".join(desc_lines))[:_MAX_DESC_CHARS]
    return JiraTicket(
        key=key,
        summary=summary,
        description=description,
        acceptance_criteria=acceptance,
        definition_of_done=dod,
    )
