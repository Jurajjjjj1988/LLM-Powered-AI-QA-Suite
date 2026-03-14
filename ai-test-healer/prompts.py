"""
Prompt templates for ai-test-healer.

The healer asks Claude to return ONLY a single CSS selector (or the literal
string "NONE" if no suitable selector can be found).  This minimal response
format makes parsing trivial and eliminates injection surface area.

System prompt is STATIC.  The broken selector, element description, and HTML
snippet all go into the user turn.
"""

SYSTEM_PROMPT = """\
You are an expert front-end engineer specialising in CSS selector repair for
automated test suites.

Given a broken CSS selector and an HTML snippet, you find the best replacement
selector that:
  1. Uniquely identifies the described element within the provided HTML.
  2. Is as stable as possible (prefer data-testid, aria-*, id, name attributes
     over positional or visual class names).
  3. Is valid CSS selector syntax.

Output rules (STRICT):
- Return ONLY the CSS selector string. No explanation, no prose, no markdown.
- If you cannot find a matching element, return exactly: NONE
- Do NOT wrap the selector in quotes or backticks.
- Do NOT add any surrounding text.

Examples of valid responses:
  button[data-testid="submit"]
  input[name="email"]
  .login-container > button.btn-submit
  NONE
"""


def build_heal_user_message(
    description: str,
    old_selector: str,
    html_snippet: str,
) -> str:
    """
    Build the user-turn message for a selector healing request.

    All three parameters are user-supplied and therefore placed here (user
    turn), never in the system prompt.
    """
    return (
        f"Element description: {description}\n"
        f"Broken selector: {old_selector}\n\n"
        "HTML snippet:\n"
        f"{html_snippet}\n\n"
        "Return ONLY the replacement CSS selector (or NONE if not found)."
    )
