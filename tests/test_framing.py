from garden_jihan.media.framing import FaceObservation, choose_auto_framing


def _face(
    time: float,
    track_id: int,
    center_x: float,
    motion: float,
    audio: float | None = 0.8,
) -> FaceObservation:
    return FaceObservation(
        time=time,
        track_id=track_id,
        center_x=center_x,
        area=0.08,
        mouth_motion=motion,
        audio_energy=audio,
    )


def test_auto_framing_tracks_one_stable_subject_without_speaker_claim():
    observations = [_face(float(index), 1, 0.25 + index * 0.01, 0.0) for index in range(8)]

    decision = choose_auto_framing(observations, clip_start=0.0, expected_samples=10)

    assert decision.applied == "auto-subject"
    assert decision.confidence > 0.8
    assert len(decision.points) == 8
    assert "not speaker identity" in decision.message


def test_auto_framing_follows_separated_audio_visual_activity_between_faces():
    observations = []
    for index in range(10):
        left_is_active = index < 5
        observations.extend(
            [
                _face(float(index), 1, 0.22, 0.055 if left_is_active else 0.002),
                _face(float(index), 2, 0.78, 0.002 if left_is_active else 0.055),
            ]
        )

    decision = choose_auto_framing(observations, clip_start=0.0, expected_samples=10)

    assert decision.applied == "auto-speaking-face"
    assert decision.confidence >= 0.8
    assert decision.points[0].center_x < 0.3
    assert decision.points[-1].center_x > 0.65
    assert "does not identify" in decision.message


def test_auto_framing_fails_to_center_when_multiple_faces_are_ambiguous():
    observations = []
    for index in range(10):
        observations.extend(
            [
                _face(float(index), 1, 0.25, 0.03),
                _face(float(index), 2, 0.75, 0.029),
            ]
        )

    decision = choose_auto_framing(observations, clip_start=0.0, expected_samples=10)

    assert decision.applied == "center"
    assert decision.confidence == 0.0
    assert not decision.points
    assert "ambiguous" in decision.message


def test_auto_framing_fails_to_center_with_sparse_detections():
    decision = choose_auto_framing(
        [_face(0.0, 1, 0.2, 0.1), _face(1.0, 1, 0.2, 0.1)],
        clip_start=0.0,
        expected_samples=10,
    )

    assert decision.applied == "center"
    assert "consistently" in decision.message
