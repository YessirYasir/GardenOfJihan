$ErrorActionPreference = "Stop"
if (-not (Test-Path ".venv")) { python -m venv .venv }
. .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,ai]"
garden-of-jihan
