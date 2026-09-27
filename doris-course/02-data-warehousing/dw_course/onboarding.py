"""Actionable setup failures without replacing IPython's global error handler."""

import html
import os
from pathlib import Path
from urllib.parse import quote

from IPython.display import HTML, display

COURSE_ROOT = Path(__file__).resolve().parents[1]
LABS = {
    1: "level1/module01-introduction/lab1_connect_and_query.ipynb",
    5: "level1/module05-ingestion/lab5_stream_load.ipynb",
    6: "level1/module06-data-quality/lab6_validate_orders.ipynb",
}


class SetupRequired(RuntimeError):
    """Still stop execution, but show recovery links and folded details in IPython."""

    def __init__(self, message, *, labs=(), detail=""):
        super().__init__(message)
        self.links = [("First-time setup", "GETTING_STARTED.md")]
        self.links.extend((f"Open Lab {number}", LABS[number]) for number in labs)
        self.detail = detail

    def _render_traceback_(self):
        from .ui import install_styles

        install_styles()
        links = " · ".join(
            f'<a href="{html.escape(quote(os.path.relpath(COURSE_ROOT / path, Path.cwd()), safe="/"))}">{html.escape(label)}</a>'
            for label, path in self.links
        )
        details = (
            '<details class="doris-log"><summary>Technical details</summary>'
            f'<pre>{html.escape(self.detail)}</pre></details>' if self.detail else ""
        )
        display(HTML(
            '<div class="doris-status failure"><div class="doris-status-title">'
            'One more setup step is needed</div>'
            f'<p>{html.escape(str(self))}</p><p>{links}</p></div>{details}'
        ))
        return [f"SetupRequired: {self}"]
