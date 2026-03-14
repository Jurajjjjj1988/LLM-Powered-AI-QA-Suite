"""
Log parser for ai-test-analyzer.

Supports:
  - JSON log files: list of objects with {test, status, duration?, timestamp?, error_message?}
  - JUnit XML files (standard <testsuite><testcase> schema)
  - Plain-text log files (best-effort line parsing — useful for CI stdout dumps)

All entries are normalised to TestLogEntry (from common.schemas), which already
applies the status normalisation mapping (PASSED→PASS, FAILED→FAIL, etc.) via
its field_validator.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree

from common.schemas import TestLogEntry

logger = logging.getLogger(__name__)

# Regex for plain-text lines like:
#   PASS  login_test  2.34s
#   ✓  checkout_test (1500ms)
#   ✗  payment_test  FAILED  4.1s
_PLAIN_LINE_RE = re.compile(
    r"(?P<status>PASS(?:ED)?|FAIL(?:ED|URE)?|ERROR|SKIP(?:PED)?|SUCCESS|OK)"
    r"[\s\-:]+(?P<name>[^\s()\[\]]{3,})"
    r"(?:[\s(]+(?P<duration>[\d.]+)\s*(?:ms|s|sec)?)?",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

def parse_log_file(path: str | Path) -> list[TestLogEntry]:
    """
    Detect file format and return a list of normalised TestLogEntry objects.
    Raises ValueError if the file cannot be parsed in any supported format.
    """
    fpath = Path(path)
    if not fpath.exists():
        raise FileNotFoundError(f"Log file not found: {fpath}")

    raw = fpath.read_text(encoding="utf-8", errors="replace")
    suffix = fpath.suffix.lower()

    if suffix in (".xml",):
        return _parse_junit_xml(raw, source=str(fpath))

    if suffix in (".json",):
        return _parse_json_log(raw, source=str(fpath))

    # Try JSON first (some files are .log but contain JSON)
    stripped = raw.strip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            return _parse_json_log(raw, source=str(fpath))
        except (json.JSONDecodeError, ValueError):
            pass

    # Fall back to XML sniff
    if stripped.startswith("<"):
        try:
            return _parse_junit_xml(raw, source=str(fpath))
        except ElementTree.ParseError:
            pass

    # Last resort: plain-text
    entries = list(_parse_plain_text(raw))
    if not entries:
        raise ValueError(
            f"Could not parse {fpath} as JSON, JUnit XML, or plain text. "
            "Ensure it contains test result data."
        )
    return entries


def parse_log_entries(raw_entries: list[dict]) -> list[TestLogEntry]:
    """
    Normalise a list of raw dicts (already loaded from JSON or passed programmatically)
    into TestLogEntry objects.  Invalid entries are skipped with a warning.
    """
    results: list[TestLogEntry] = []
    for i, entry in enumerate(raw_entries):
        try:
            results.append(TestLogEntry(**entry))
        except Exception as exc:
            logger.warning(
                "Skipping invalid log entry",
                extra={"index": i, "error": str(exc), "entry": entry},
            )
    return results


# ---------------------------------------------------------------------------
# Format-specific parsers
# ---------------------------------------------------------------------------

def _parse_json_log(raw: str, source: str) -> list[TestLogEntry]:
    data = json.loads(raw)
    if isinstance(data, dict):
        # Some runners wrap results: {"results": [...]}  or {"tests": [...]}
        for key in ("results", "tests", "entries", "testResults"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        else:
            raise ValueError(
                f"JSON in {source} is an object but no known list key found"
            )
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array in {source}")

    logger.debug("Parsing JSON log", extra={"source": source, "entries": len(data)})
    return parse_log_entries(data)


def _parse_junit_xml(raw: str, source: str) -> list[TestLogEntry]:
    """
    Parse JUnit XML.  Handles both single <testsuite> and <testsuites> wrapper.
    """
    root = ElementTree.fromstring(raw)  # raises ParseError on bad XML

    # Normalise root: collect all <testcase> elements regardless of nesting
    testcases = list(root.iter("testcase"))
    logger.debug(
        "Parsing JUnit XML", extra={"source": source, "testcases": len(testcases)}
    )

    entries: list[TestLogEntry] = []
    for tc in testcases:
        classname = tc.get("classname", "")
        name = tc.get("name", "unknown")
        full_name = f"{classname}.{name}" if classname else name
        duration = _safe_float(tc.get("time", "0"))

        # Determine status from child elements
        if tc.find("failure") is not None:
            status = "FAIL"
            error_el = tc.find("failure")
        elif tc.find("error") is not None:
            status = "FAIL"
            error_el = tc.find("error")
        elif tc.find("skipped") is not None:
            status = "SKIP"
            error_el = None
        else:
            status = "PASS"
            error_el = None

        error_message: str | None = None
        if error_el is not None:
            error_message = (error_el.get("message") or error_el.text or "").strip() or None

        try:
            entries.append(
                TestLogEntry(
                    test=full_name,
                    status=status,
                    duration=duration,
                    error_message=error_message,
                )
            )
        except Exception as exc:
            logger.warning(
                "Skipping JUnit testcase", extra={"name": full_name, "error": str(exc)}
            )

    return entries


def _parse_plain_text(raw: str) -> Iterable[TestLogEntry]:
    """
    Best-effort extraction of test results from plain-text CI output.
    Yields TestLogEntry objects for lines that match the heuristic pattern.
    """
    for line in raw.splitlines():
        m = _PLAIN_LINE_RE.search(line)
        if m:
            duration_str = m.group("duration") or "0"
            # Convert ms to seconds if the unit hint is present
            duration = _safe_float(duration_str)
            if "ms" in line[m.start():m.end()].lower():
                duration = duration / 1000.0

            try:
                yield TestLogEntry(
                    test=m.group("name").strip(),
                    status=m.group("status").strip(),
                    duration=duration,
                )
            except Exception:
                pass  # Skip lines we cannot fully parse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
