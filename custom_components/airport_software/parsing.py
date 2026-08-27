"""Pure-function HTML parsing for airport-software pages.

No network I/O lives here — client.py owns the HTTP layer and calls
into these functions with already-fetched response bodies.
"""
import html as html_module
import re

_HIDDEN_FIELD_RE = re.compile(r'<input[^>]*type="hidden"[^>]*>')
_NAME_RE = re.compile(r'name="([^"]+)"')
_VALUE_RE = re.compile(r'value="([^"]*)"')


def extract_hidden_fields(page_html: str) -> dict[str, str]:
    """Return {name: value} for every hidden <input> in an ASP.NET page."""
    fields: dict[str, str] = {}
    for match in _HIDDEN_FIELD_RE.finditer(page_html):
        tag = match.group(0)
        name_match = _NAME_RE.search(tag)
        if not name_match:
            continue
        value_match = _VALUE_RE.search(tag)
        fields[name_match.group(1)] = value_match.group(1) if value_match else ""
    return fields


_ERROR_DIV_RE = re.compile(r'<div id="ctl00_fehlertext" class="meldungen_err">')


def login_failed(response_html: str) -> bool:
    """True if a login POST response is the login page re-rendered with an error."""
    return bool(_ERROR_DIV_RE.search(response_html))
