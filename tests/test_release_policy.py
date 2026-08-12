from pathlib import Path

ROOT = Path(__file__).parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_every_public_windows_workflow_verifies_the_exact_release_zip():
    tag_workflow = _read(".github/workflows/windows-build.yml")
    beta_workflow = _read(".github/workflows/publish-beta.yml")

    gate_command = (
        '.\\scripts\\assert-signed-release.ps1 -PackageRoot "dist\\GardenOfJihan" '
        '-ArchivePath "dist\\GardenOfJihan-Windows-x64.zip"'
    )
    assert gate_command in tag_workflow
    assert gate_command in beta_workflow
    assert tag_workflow.index(gate_command) < tag_workflow.index("actions/upload-artifact@v4")
    assert beta_workflow.index(gate_command) < beta_workflow.index("Publish GitHub prerelease")
    assert "if: startsWith(github.ref, 'refs/tags/v')" in tag_workflow


def test_release_gate_checks_signature_inside_archive_and_exact_executable_identity():
    script = _read("scripts/assert-signed-release.ps1")

    assert "Expand-Archive" in script
    assert 'Get-AuthenticodeSignature -LiteralPath $Executable' in script
    assert '$signature.Status -ne "Valid"' in script
    assert '$productName -ne "Garden of Jihan"' in script
    assert "$looseHash -ne $archiveHash" in script
    assert "SignerCertificate.Thumbprint" in script


def test_packaged_instructions_never_recommend_unsigned_distribution():
    build_script = _read("scripts/build-windows.ps1")

    assert "Windows Public Beta" not in build_script
    assert (
        "Never distribute GardenOfJihan.exe publicly unless Windows identifies its trusted publisher."
        in build_script
    )


def test_windows_package_collects_local_semantic_runtime():
    build_script = _read("scripts/build-windows.ps1")

    assert "--collect-all fastembed" in build_script
    assert "--collect-all onnxruntime" in build_script
    assert "prepare-offline-models.py" in build_script
    assert "prepare-quran-reference.py" in build_script


def test_windows_package_pins_and_verifies_ffmpeg_without_admin_package_manager():
    build_script = _read("scripts/build-windows.ps1")

    assert '$ffmpegVersion = "8.1"' in build_script
    assert (
        '$ffmpegArchiveSha256 = "587B1C37DE29C5003D01CF65DA10001BAC43A58B88E61AF0FC77C61DAFF04761"'
        in build_script
    )
    assert "Get-FileHash -LiteralPath $downloadPath -Algorithm SHA256" in build_script
    assert "Downloaded FFmpeg archive failed the pinned SHA256 check" in build_script
    assert "curl.exe --fail --location --retry 3" in build_script
    assert "choco install" not in build_script
    assert "Get-Command ffmpeg" not in build_script
    assert '$PythonExecutable = "python"' in build_script
    assert "[switch]$SkipDependencyInstall" in build_script


def test_windows_package_carries_ffmpeg_license_and_source_notice():
    build_script = _read("scripts/build-windows.ps1")
    notices = _read("THIRD-PARTY-NOTICES.md")

    assert "FFMPEG-LICENSE.txt" in build_script
    assert "FFMPEG-BUILD-INFO.txt" in build_script
    assert "THIRD-PARTY-NOTICES.md" in build_script
    assert "GNU General Public License" in notices
    assert "9047fa1b08" in notices
    assert "587B1C37DE29C5003D01CF65DA10001BAC43A58B88E61AF0FC77C61DAFF04761" in notices


def test_packaged_smoke_exercises_clean_shutdown_without_opening_a_window():
    smoke_script = _read("scripts/smoke-windows-package.ps1")

    assert "-WindowStyle Hidden" in smoke_script
    assert '"$origin/api/app/quit"' in smoke_script
    assert "$process.WaitForExit(15000)" in smoke_script
    assert 'Stop-Process -Id $process.Id -Force' in smoke_script
    assert "$homeMarkup" in smoke_script
    assert "$home =" not in smoke_script
    assert 'id="progressClock"' in smoke_script
    assert '"$origin/api/quran/reference"' in smoke_script
    assert "[int]$quran.verses -ne 6236" in smoke_script


def test_caption_smoke_accepts_current_ffmpeg_filter_flags_and_renders_video():
    smoke_script = _read("scripts/smoke-captions.ps1")

    assert "[A-Z.]+" in smoke_script
    assert '"subtitles=filename=' in smoke_script
    assert "-c:v libx264" in smoke_script


def test_release_workflows_preserve_exact_arabic_branding():
    beta_workflow = _read(".github/workflows/publish-beta.yml")

    assert "جيهان" in beta_workflow
    assert "Ø¬" not in beta_workflow
