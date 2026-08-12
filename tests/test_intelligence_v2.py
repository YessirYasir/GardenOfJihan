from garden_jihan.analysis import signals as signals_module
from garden_jihan.analysis.scoring import build_candidates, score_text_detailed
from garden_jihan.analysis.signals import MediaSignals, TimedValue
from garden_jihan.analysis.transcription import TranscriptSegment
from garden_jihan.models import AnalysisMode


def test_complete_payoff_beats_repetitive_filler():
    strong = (
        "Why does this keep happening? The problem looks impossible, but here is the truth. "
        "We changed one thing, and therefore the result was completely different."
    )
    filler = "you know like basically basically basically we were there and then like you know basically"
    strong_score, reasons, breakdown = score_text_detailed(strong, AnalysisMode.GENERAL, 28)
    weak_score, _, weak_breakdown = score_text_detailed(filler, AnalysisMode.GENERAL, 28)
    assert strong_score > weak_score
    assert breakdown["payoff"] > weak_breakdown["payoff"]
    assert reasons


def test_media_signals_can_lift_an_already_viable_moment():
    text = "Listen, this is important. Here is why it matters, and this is the result."
    baseline, _, _ = score_text_detailed(text, AnalysisMode.GENERAL, 24)
    boosted, reasons, _ = score_text_detailed(
        text,
        AnalysisMode.GENERAL,
        24,
        audio_signal=0.9,
        scene_signal=0.8,
        replay_signal=0.95,
    )
    assert boosted > baseline
    assert any("replay" in reason.lower() for reason in reasons)


def test_duplicate_candidates_are_suppressed_even_without_overlap():
    segments = [
        TranscriptSegment(0, 10, "Why this matters is simple."),
        TranscriptSegment(10, 20, "Here is the truth and the answer."),
        TranscriptSegment(30, 40, "Why this matters is simple."),
        TranscriptSegment(40, 50, "Here is the truth and the answer."),
        TranscriptSegment(60, 70, "A different story begins here."),
        TranscriptSegment(70, 80, "The result teaches a separate lesson."),
    ]
    candidates = build_candidates(segments, AnalysisMode.GENERAL, 20, 30, 5)
    assert len(candidates) == 2


def test_signal_profile_averages_window_values():
    profile = MediaSignals(
        audio_energy=[TimedValue(0, 10, 0.2), TimedValue(10, 20, 0.8)],
        replay=[TimedValue(0, 20, 0.75)],
        scene_times=[3, 8, 15],
    )
    assert profile.audio_for(0, 20) == 0.5
    assert profile.replay_for(2, 12) == 0.75
    assert profile.scene_density_for(0, 20) is not None


def test_media_signal_surveys_are_combined(monkeypatch, tmp_path):
    monkeypatch.setattr(
        signals_module,
        "extract_audio_energy",
        lambda _path: [TimedValue(0, 2, 0.8)],
    )
    monkeypatch.setattr(signals_module, "extract_scene_times", lambda _path: [1.0, 3.0])

    result = signals_module.build_media_signals(tmp_path / "video.mp4")

    assert result.audio_energy[0].value == 0.8
    assert result.scene_times == [1.0, 3.0]


def test_somali_story_phrases_raise_story_signal_and_create_verbatim_titles():
    story = (
        "Tusaale ahaan, maalin ayaa nin safar galay. Markii uu soo noqday wuxuu ogaaday "
        "xaqiiqda, ugu dambaynna casharka waa in sabirku muhiim yahay."
    )
    filler = "Wax kale ayaa jira oo hadalka ku jira waana arrin caadi ah oo la sheegayo."

    story_score, story_reasons, breakdown = score_text_detailed(
        story,
        AnalysisMode.SOMALI,
        30,
    )
    filler_score, _, _ = score_text_detailed(filler, AnalysisMode.SOMALI, 30)
    candidates = build_candidates(
        [TranscriptSegment(0, 30, story)],
        AnalysisMode.SOMALI,
        20,
        60,
        1,
    )

    assert story_score > filler_score
    assert breakdown["story"] >= 62
    assert any("story or example" in reason for reason in story_reasons)
    assert candidates[0].title != "Strong moment"
    assert candidates[0].title.rstrip("…") in story


def test_somali_title_fails_cleanly_when_speech_is_mislabeled_as_arabic():
    candidates = build_candidates(
        [TranscriptSegment(125, 150, "هذا نص عربي غير موثوق للعنوان")],
        AnalysisMode.SOMALI,
        20,
        60,
        1,
    )

    assert candidates[0].title == "Moment at 2:05"
