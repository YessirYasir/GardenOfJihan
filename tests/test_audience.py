from garden_jihan.analysis.audience import normalize_heatmap


def test_heatmap_normalization_uses_relative_peak():
    values = normalize_heatmap(
        [
            {"start_time": 0, "end_time": 10, "value": 2},
            {"start_time": 10, "end_time": 20, "value": 8},
        ]
    )
    assert len(values) == 2
    assert values[0].value == 0.25
    assert values[1].value == 1.0


def test_heatmap_ignores_broken_bins():
    values = normalize_heatmap(
        [
            {"start_time": 3, "end_time": 3, "value": 9},
            {"start_time": "bad", "end_time": 7, "value": 1},
        ]
    )
    assert values == []
