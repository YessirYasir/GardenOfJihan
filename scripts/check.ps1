$ErrorActionPreference = "Stop"
pytest
ruff check .
bandit -q -r src
pip-audit
