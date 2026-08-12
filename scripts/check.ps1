$ErrorActionPreference = "Stop"
pytest
ruff check .
bandit -q -r src -ll
pip-audit
