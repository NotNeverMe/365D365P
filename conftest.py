"""Make each project's modules importable in tests (project dirs start with digits, so they are not packages)."""

import sys
from pathlib import Path

for project in sorted((Path(__file__).parent / "projects").glob("*/")):
    if project.is_dir():
        sys.path.insert(0, str(project))
