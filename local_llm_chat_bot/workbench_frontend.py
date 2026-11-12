"""Browser page of the Bosch Assembly Assistant.

The page lives in ``static/`` as three ordinary files so it can be read and
edited with normal tooling:

- ``workbench.html``: the page shell and static markup,
- ``workbench.css``: all styles,
- ``workbench.js``: all browser code.

They are assembled once into the same single self-contained document the
server has always sent from ``/``: no extra HTTP endpoints, no external
requests.  The i18n catalog placeholder inside the script is filled by
``chat_workbench`` afterwards.
"""

from __future__ import annotations

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "static"
SHELL_FILE = "workbench.html"
# Each include marker is a comment that is valid where it stands (inside
# <style> and <script>), so the shell file stays a well-formed page.
INCLUDES = {
    "/*@include workbench.css*/": "workbench.css",
    "/*@include workbench.js*/": "workbench.js",
}


def read_static(name: str) -> str:
    # Universal newlines: a CRLF checkout on Windows yields the same page.
    return (STATIC_DIR / name).read_text(encoding="utf-8")


def load_frontend_html() -> str:
    """Return the page template (catalog placeholder still unfilled)."""
    page = read_static(SHELL_FILE)
    for marker, name in INCLUDES.items():
        if page.count(marker) != 1:
            raise RuntimeError(f"{SHELL_FILE} must contain {marker!r} exactly once")
        before, after = page.split(marker)
        page = before + read_static(name) + after
    return page


def frontend_source() -> str:
    """Shell, styles and script as one text, for source-level checks."""
    return "\n".join(read_static(name) for name in (SHELL_FILE, *INCLUDES.values()))
