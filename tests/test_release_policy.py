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
    assert "Never distribute an unsigned GardenOfJihan.exe as a public release." in build_script
