from pathlib import Path

ROOT = Path(__file__).parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_portable_build_uses_pinned_official_runtime_and_hash_locked_dependencies():
    script = _read("scripts/build-portable-browser.ps1")

    assert '$pythonVersion = "3.12.10"' in script
    assert (
        '$pythonArchiveSha256 = '
        '"4ACBED6DD1C744B0376E3B1CF57CE906F9DC9E95E68824584C8099A63025A3C3"'
        in script
    )
    assert "https://www.python.org/ftp/python/$pythonVersion/$pythonArchiveName" in script
    assert "Get-AuthenticodeSignature" in script
    assert "Python Software Foundation" in script
    assert "--require-hashes" in script
    assert "--only-binary=:all:" in script
    assert "requirements-portable-windows.txt" in script
    assert "PACKAGE-FILES.sha256" in script
    assert "prepare-offline-models.py" in script
    assert 'speech_model_revision = "536b0662742c02347bc0e980a01041f333bce120"' in script
    assert 'meaning_model_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"' in script
    assert "prepare-quran-reference.py" in script
    assert (
        'quran_reference_sha256 = '
        '"d25401b9235ea0c77a2511b1edc5b5d28df1b3bcd0259d6657ec6e303dd8eee9"'
        in script
    )


def test_portable_launcher_is_offline_one_click_and_has_no_custom_executable():
    launcher = _read("scripts/portable/START GARDEN OF JIHAN.cmd")
    starter = _read("scripts/portable/portable_start.pyw")
    verifier = _read("scripts/verify-portable-bundle.ps1")

    assert "runtime\\pythonw.exe" in launcher
    assert "app\\portable_start.pyw" in launcher
    assert "GOJ_DISTRIBUTION=portable-browser" in launcher
    assert r"GOJ_SPEECH_MODEL_PATH=%~dp0models\speech" in launcher
    assert r"GOJ_MEANING_MODEL_PATH=%~dp0models\meaning" in launcher
    assert r"GOJ_QURAN_REFERENCE_PATH=%~dp0models\quran_reference.json" in launcher
    assert all(term not in launcher.lower() for term in ("http://", "https://", "curl.exe", "powershell"))
    assert "GardenOfJihan.exe" not in launcher
    assert "from garden_jihan.launcher import main as launch" in starter
    assert "portable folder is incomplete or" in starter
    assert "must not contain an unsigned custom GardenOfJihan.exe" in verifier
    assert r"models\quran_reference.json" in verifier
    assert "Portable Qur'an guide integrity check failed" in verifier


def test_portable_handoff_is_private_and_cannot_publish_a_release():
    workflow = _read(".github/workflows/portable-browser.yml")
    guide = _read("scripts/portable/START-HERE.txt")

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" in workflow
    assert "push:" not in workflow
    assert "gh release" not in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert "retention-days: 2" in workflow
    assert "Everything needed to understand your videos is already included" in guide
    assert "No account, administrator access, subscription" in guide
    assert "AI" not in guide
    assert "API" not in guide
    assert "Python" not in guide


def test_portable_smoke_covers_first_run_ui_and_clean_shutdown():
    smoke = _read("scripts/smoke-portable-browser.ps1")

    assert '"$origin/api/health"' in smoke
    assert '"$origin/api/onboarding/complete"' in smoke
    assert '"$origin/api/app/quit"' in smoke
    assert '$health.distribution -ne "portable-browser"' in smoke
    assert "$health.first_run -ne $true" in smoke
    assert "$afterWelcome.first_run -ne $false" in smoke
    assert "did not close cleanly" in smoke
    assert 'id="progressClock"' in smoke
    assert '"$origin/api/quran/reference"' in smoke
    assert "[int]$quran.verses -ne 6236" in smoke
