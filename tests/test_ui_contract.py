from importlib.resources import files


def _ui_text(name: str) -> str:
    return files("garden_jihan").joinpath("ui", name).read_text(encoding="utf-8")


def test_production_brand_and_garden_motion_are_preserved():
    html = _ui_text("index.html")
    editor_css = _ui_text("editor.css")

    assert html.count(">جيهان<") == 2
    assert html.count('class="falling-flower ') == 12
    assert "flowerFall" in editor_css
    assert "flowerSway" in editor_css
    assert ".ff1" in editor_css and "animation-duration:27s" in editor_css
    assert ".ff1 span{animation-duration:6.2s}" in editor_css


def test_production_ui_claims_match_current_behavior():
    html = _ui_text("index.html")

    assert "All local services ready" not in html
    assert "Local interface connected" in html
    assert "Check source ✦" in html
    assert "Native-language analysis" not in html
    for label, percent in (
        ("Hook &amp; curiosity", 34),
        ("Payoff &amp; completeness", 30),
        ("Emotion, density &amp; novelty", 24),
        ("Audio, visual &amp; replay", 12),
    ):
        assert f"<span>{label}</span><b>{percent}%</b>" in html


def test_analysis_progress_is_accessible_and_does_not_scroll_on_launch():
    html = _ui_text("index.html")
    app_css = _ui_text("app.css")
    app_js = _ui_text("app.js")

    assert 'role="progressbar"' in html
    assert 'id="startAnalysis" class="primary analyze-hero" aria-busy="false"' in html
    assert all(f'id="growth{number}"' in html for number in range(1, 5))
    assert "showStep(0,{scroll:false});" in app_js
    assert "let analysisBusy=false;" in app_js
    assert "startAnalysisButton.disabled=busy;" in app_js
    assert ".trust-row{justify-content:center;overflow:visible;flex-wrap:wrap" in app_css


def test_caption_controls_are_functional_and_do_not_claim_word_tracking():
    html = _ui_text("index.html")
    app_js = _ui_text("app.js")

    for control in ('id="captions"', 'id="captionStyle"', 'id="captionPosition"'):
        assert control in html
    assert "Uses local transcript segment timing, not word tracking." in html
    assert "Qur’an burn-in stays disabled until verified acoustic timing" in html
    assert "caption_style:document.getElementById('captionStyle').value" in app_js
    assert "candidate.mode==='quran'" in app_js
    assert "let exportBusy=false;" in app_js


def test_ranking_status_reports_embeddings_fallback_and_quran_safe_path():
    html = _ui_text("index.html")
    app_js = _ui_text("app.js")

    assert 'id="rankingStatus"' in html
    assert "Local meaning model active" in app_js
    assert "Base ranking used" in app_js
    assert "no cloud or paid API fallback" in app_js
    assert "Qur’an-safe ranking" in app_js
    assert "does not infer Surah, Ayah, or Qira’at" in app_js
    assert "semantic_coherence:'Topic coherence'" in app_js


def test_auto_framing_is_honest_and_keeps_manual_fallbacks():
    html = _ui_text("index.html")
    app_js = _ui_text("app.js")

    assert '<option value="auto" selected>Auto speaking face (beta)</option>' in html
    assert all(
        f'<option value="{value}">' in html
        for value in ("center", "left", "right", "split-stack")
    )
    assert "never identifies a person" in html
    assert "file.framing?.message" in app_js
