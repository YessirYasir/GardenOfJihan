from garden_jihan.analysis.scoring import build_candidates, score_text
from garden_jihan.analysis.transcription import TranscriptSegment
from garden_jihan.models import AnalysisMode


def test_somali_hook_scores_and_explains():
    score, reasons = score_text(
        "Bal ogow runta arrintan. Maxaa sabab u ah dhibkan? Tani waa muhiim.",
        AnalysisMode.SOMALI,
        25,
    )
    assert score >= 60
    assert any("opening" in reason.lower() or "curiosity" in reason.lower() for reason in reasons)


def test_arabic_hook_scores():
    score, reasons = score_text(
        "اسمع، لماذا حدث هذا؟ لكن الحقيقة مهمة جدا.", AnalysisMode.ARABIC, 22
    )
    assert score >= 60
    assert reasons


def test_candidates_do_not_overlap():
    segments = [
        TranscriptSegment(i * 10, (i + 1) * 10, f"Why this matters segment {i}.")
        for i in range(12)
    ]
    candidates = build_candidates(segments, AnalysisMode.GENERAL, 20, 40, 5)
    for i, a in enumerate(candidates):
        for b in candidates[i + 1 :]:
            assert a.end <= b.start or a.start >= b.end
