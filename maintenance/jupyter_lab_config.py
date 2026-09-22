"""Course browser: retain generated files on disk, hide them in the file list."""

from pathlib import Path

c = get_config()
c.ServerApp.root_dir = str(Path(__file__).resolve().parents[1])
c.ServerApp.ip = "127.0.0.1"
c.ServerApp.open_browser = False
c.LabApp.default_url = "/lab/tree/doris-course"
c.ContentsManager.hide_globs = [
    "__pycache__", "*.pyc", "*.pyo", ".DS_Store", "*~",
    "*.egg-info", ".venv", ".ipynb_checkpoints", ".runtime",
]
