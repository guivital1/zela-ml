"""Checks locais para código, artefato e integração HTTP."""

import subprocess
import sys

for arguments in (
    ["ruff", "check", "src", "scripts", "tests"],
    ["ruff", "format", "--check", "src", "scripts", "tests"],
    ["pytest", "-q"],
):
    subprocess.run([sys.executable, "-m", *arguments], check=True)
