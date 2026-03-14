import hashlib
import logging
import re

from common.exceptions import SanitizationError

logger = logging.getLogger(__name__)

# Only allow printable ASCII + common unicode for requirements
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]")

# CSS selector allowlist
_CSS_SELECTOR_RE = re.compile(r"^[a-zA-Z0-9\s\[\]#.:!\-_=^$*~|>\"'()+,@]+$")


def sanitize_requirement(text: str, max_length: int = 5000) -> str:
    text = text.strip()
    if len(text) < 10:
        raise SanitizationError("Requirement too short (minimum 10 characters)")
    if len(text) > max_length:
        raise SanitizationError(f"Requirement exceeds {max_length} characters")
    text = _CONTROL_CHARS_RE.sub("", text)
    return text


def sanitize_html_snippet(html: str, max_length: int = 8000) -> str:
    if len(html) > max_length:
        logger.warning(
            "HTML snippet truncated",
            extra={"original_len": len(html), "truncated_to": max_length},
        )
        html = html[:max_length]
    return html


def sanitize_selector(selector: str) -> str:
    selector = selector.strip()
    if not selector:
        raise SanitizationError("Selector is empty")
    if len(selector) > 500:
        raise SanitizationError("Selector exceeds 500 characters")
    if not _CSS_SELECTOR_RE.match(selector):
        raise SanitizationError(
            f"Selector contains disallowed characters: {selector!r}"
        )
    return selector


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
