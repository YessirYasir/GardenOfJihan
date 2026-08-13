from pathlib import Path

ROOT = Path(__file__).parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_macos_build_covers_both_architectures_and_pinned_media_tools():
    build = read("scripts/build-macos.sh")
    workflow = read(".github/workflows/macos-build.yml")

    assert 'arm64)' in build
    assert 'x86_64)' in build
    assert "b6.1.1" in build
    assert "FFMPEG-LICENSE.txt" in build
    assert "eugeneware/ffmpeg-static" in build
    assert "FFMPEG_SHA256=" in build
    assert "FFPROBE_SHA256=" in build
    assert "shasum -a 256" in build
    assert "prepare-offline-models.py" in build
    assert "prepare-quran-reference.py" in build
    assert "macos-15" in workflow
    assert "macos-15-intel" in workflow


def test_macos_handoff_is_self_contained_and_plain_language():
    build = read("scripts/build-macos.sh")
    guide = read("scripts/macos/START-HERE.txt")

    assert '--name "Garden of Jihan"' in build
    assert '--add-binary "$MEDIA_ROOT/ffmpeg:bin"' in build
    assert '--add-binary "$MEDIA_ROOT/ffprobe:bin"' in build
    assert '--add-data "$MODEL_ROOT:models"' in build
    assert "Nothing else needs to be installed" in guide
    assert "No account, subscription, credits, or payment" in guide
    assert "Python" not in guide
    assert "API" not in guide
    assert "AI" not in guide


def test_public_macos_release_requires_developer_id_and_notarization():
    workflow = read(".github/workflows/macos-build.yml")
    signer = read("scripts/sign-notarize-macos.sh")
    verifier = read("scripts/verify-macos-package.py")

    assert "GOJ_APPLE_CERTIFICATE_BASE64" in workflow
    assert "GOJ_APPLE_TEAM_ID" in workflow
    assert "notarytool submit" in signer
    assert "stapler staple" in signer
    assert "--options runtime" in signer
    assert "--require-notarized" in workflow
    assert "Authority=Developer ID Application:" in verifier
    assert '"stapler", "validate"' in verifier
    assert '"/usr/sbin/spctl", "--assess"' in verifier
    assert 'package / "FFMPEG-LICENSE.txt"' in verifier


def test_private_macos_artifacts_are_short_lived_and_not_published():
    workflow = read(".github/workflows/macos-build.yml")

    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert "retention-days: 2" in workflow
    assert "startsWith(github.ref, 'refs/tags/v')" in workflow


def test_macos_smoke_compares_health_values_not_object_identity():
    smoke = read("scripts/smoke-macos-package.py")

    assert "health.get(key) != expected" in smoke
    assert "health.get(key) is not expected" not in smoke
