# Contributing

Contributions are welcome.

1. Create a feature branch.
2. Keep media-processing subprocesses argument-based; never use `shell=True`.
3. Do not add telemetry, hidden network calls, bundled credentials, or copyrighted test media.
4. Add tests for new parsing/security boundaries.
5. Run `pytest`, `ruff check .`, and `bandit -r src` before opening a PR.

For Qur'an and Somali language data, include source, license, annotation methodology, and reviewer information. Accuracy claims should be backed by an evaluation set, not examples chosen after the fact.
