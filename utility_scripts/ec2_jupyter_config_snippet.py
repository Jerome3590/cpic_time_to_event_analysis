# Jupyter post-save hook - auto-push notebook outputs to S3 on save.
# Append this to ~/.jupyter/jupyter_notebook_config.py on EC2.

import os
from pathlib import Path
import subprocess
import sys

from notebook.services.contents.filemanager import FileContentsManager

_original_save = FileContentsManager.save
_PROJECT_ROOT = Path(
    os.environ.get("CPIC_PROJECT_ROOT", "/home/pgx3874/cpic_time_to_event_analysis")
).expanduser()
_CURSOR_SETUP = _PROJECT_ROOT / "cursor_setup.py"


def _patched_save(self, model, path=""):
    result = _original_save(self, model, path)
    if path.endswith(".ipynb"):
        nb_abs_path = str(Path(self.root_dir) / path)
        if _CURSOR_SETUP.exists():
            subprocess.Popen(
                [
                    sys.executable,
                    str(_CURSOR_SETUP),
                    "push-outputs",
                    nb_abs_path,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    return result


FileContentsManager.save = _patched_save
