import re
from importlib.resources import files


def _ui_text(name: str) -> str:
    return files("garden_jihan").joinpath("ui", name).read_text(encoding="utf-8")


def test_production_brand_and_garden_motion_are_preserved():
    html = _ui_text("index.html")
    app_css = _ui_text("app.css")
    editor_css = _ui_text("editor.css")
    background = files("garden_jihan").joinpath(
        "ui", "assets", "garden-sanctuary-bg.png"
    )

    assert html.count(">جيهان<") >= 2
    assert html.count('class="falling-flower ') == 12
    assert "flowerFall" in editor_css
    assert "flowerSway" in editor_css
    assert ".ff1" in editor_css and "animation-duration:27s" in editor_css
    assert ".ff1 span{animation-duration:6.2s}" in editor_css
    assert background.is_file() and len(background.read_bytes()) > 500_000
    assert 'url("/static/assets/garden-sanctuary-bg.png")' in app_css
    assert 'class="waterfall-motion"' in html
    assert html.count('class="breeze-layer ') == 3
    assert "waterfallFlow" in app_css
    assert "gardenBreezeCanopy" in app_css
    assert "gardenBreezeLeft" in app_css
    assert "gardenBreezeRight" in app_css


def test_first_run_welcome_is_local_honest_and_keyboard_reachable():
    html = _ui_text("index.html")
    app_css = _ui_text("app.css")
    app_js = _ui_text("app.js")

    assert 'id="welcomeGarden"' in html
    assert 'role="dialog" aria-modal="true"' in html
    assert 'id="beginGarden"' in html
    assert "جيهان" in html
    assert "Your private garden is ready as soon as it opens" in html
    assert "opens as a private garden on this computer" in html
    assert "@media(prefers-reduced-motion:reduce)" in app_css
    assert "api('/api/onboarding/complete',{method:'POST'})" in app_js
    assert "document.getElementById('beginGarden').focus()" in app_js


def test_production_ui_claims_match_current_behavior():
    html = _ui_text("index.html")

    assert "All local services ready" not in html
    assert "Ready for your video" in html
    assert "Add Video ✦" in html
    assert "Native-language analysis" not in html
    for label, percent in (
        ("Opening &amp; curiosity", 34),
        ("Meaning &amp; completeness", 30),
        ("Feeling &amp; freshness", 24),
        ("Voice &amp; movement", 12),
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
    assert 'id="progressClock" aria-live="polite"' in html
    assert "data.elapsed_seconds" in app_js
    assert "working normally" in app_js
    assert "about ${clockTime(eta)} left" in app_js
    assert "Stopped after ${clockTime(elapsed)}" in app_js
    assert ".trust-row{justify-content:center;overflow:visible;flex-wrap:wrap" in app_css


def test_desktop_ui_has_an_explicit_safe_quit_control():
    html = _ui_text("index.html")
    app_js = _ui_text("app.js")

    assert 'id="quitApp"' in html
    assert "Your saved work will stay on this computer" in app_js
    assert "api('/api/app/quit',{method:'POST'})" in app_js
    assert "Garden of Jihan is closed" in app_js


def test_caption_controls_offer_honest_word_tracking_without_technical_copy():
    html = _ui_text("index.html")
    app_js = _ui_text("app.js")

    for control in ('id="captions"', 'id="captionStyle"', 'id="captionPosition"'):
        assert control in html
    assert '<option value="words">Word-by-word highlight</option>' in html
    assert "Qur’an word highlights appear only when every spoken word can be matched carefully" in html
    assert "Surah, Ayah, and Qira’at are never guessed" in html
    assert "caption_style:document.getElementById('captionStyle').value" in app_js
    assert "word_tracking:wordTracking" in app_js
    assert "candidate.mode==='quran'" in app_js
    assert "let exportBusy=false;" in app_js
    assert "/api/exports/${exportId}" in app_js
    assert "Rendering clip" not in app_js
    assert "data.progress" in app_js


def test_moment_status_explains_results_without_exposing_implementation_details():
    html = _ui_text("index.html")
    app_js = _ui_text("app.js")

    assert 'id="rankingStatus"' in html
    assert "Meaning and story flow considered" in app_js
    assert "Your moments are ready" in app_js
    assert "Careful Qur’an review" in app_js
    assert "Surah, Ayah, and Qira’at are never guessed" in app_js
    assert "semantic_coherence:'Story flow'" in app_js


def test_auto_framing_is_honest_and_keeps_manual_fallbacks():
    html = _ui_text("index.html")
    app_js = _ui_text("app.js")

    assert '<option value="auto" selected>Follow the speaker</option>' in html
    assert all(
        f'<option value="{value}">' in html
        for value in ("center", "left", "right", "split-stack")
    )
    assert "When the garden is uncertain, it keeps the picture centered" in html
    assert "file.framing?.applied" in app_js
    assert "returns to center whenever uncertain" in app_js


def test_local_project_library_resumes_and_saves_review_state():
    html = _ui_text("index.html")
    app_js = _ui_text("app.js")

    for element in ('id="projectLibrary"', 'id="projectList"', 'id="projectName"'):
        assert element in html
    assert "Everything here remains on this computer" in html
    assert "selected_ids:[...selected]" in app_js
    assert "boundaries,aspect:" in app_js
    assert "resumeProject(project.id)" in app_js
    assert "method:'DELETE'" in app_js
    assert "addEventListener('timeupdate'" in app_js
    assert "setTimeout(()=>{if(video.currentTime>=effective.end)" not in app_js


def test_project_saves_are_snapshotted_serialized_and_flushed_before_quit():
    app_js = _ui_text("app.js")

    assert "let pendingProjectSave = null;" in app_js
    assert "let projectSaveQueue = Promise.resolve(true);" in app_js
    assert "pendingProjectSave={jobId:currentJob,payload:projectPayload()}" in app_js
    assert "projectSaveQueue=projectSaveQueue.then(persist,persist)" in app_js
    assert "pendingProjectSave&&pendingProjectSave.jobId!==data.id" in app_js
    assert "if(!await flushPendingProjectSave())" in app_js
    assert app_js.index("if(!await flushPendingProjectSave())") < app_js.index(
        "api('/api/app/quit',{method:'POST'})"
    )


def test_official_publishing_keeps_required_disclosures_in_plain_language():
    html = _ui_text("index.html")
    app_js = _ui_text("app.js")

    assert "Share on YouTube" in html
    assert "Choose the Google connection file provided for Garden of Jihan" in html
    assert "used only for publishing" in html
    assert 'id="youtubeKids"' in html
    assert 'id="youtubeSynthetic"' in html
    assert "TikTok sharing unavailable" in html
    assert "TikTok has not approved this connection yet" in html
    assert "/api/publish/youtube/connect" in app_js
    assert "made_for_kids:kids==='yes'" in app_js
    assert "contains_synthetic_media:synthetic==='yes'" in app_js


def test_top_moments_shelf_is_persistent_and_never_uses_demo_cards():
    html = _ui_text("index.html")
    app_js = _ui_text("app.js")

    for element in ('id="momentShelf"', 'id="momentShelfGrid"', 'id="emptyMomentShelf"'):
        assert element in html
    assert "Your strongest moments will gather here as you create" in html
    assert "api('/api/moments')" in app_js
    assert "renderTopMoments(data.moments||[])" in app_js
    assert "resumeProject(moment.project_id)" in app_js
    assert "placeholder moment" not in app_js.lower()


def test_visible_dashboard_copy_avoids_technical_product_language():
    html = _ui_text("index.html")
    visible_text = re.sub(r"<[^>]+>", " ", html)

    for forbidden in (
        r"\bAI\b",
        r"\bAPI\b",
        r"OAuth",
        r"FFmpeg",
        r"source code",
        r"Open Source",
        r"telemetry",
        r"checksum",
        r"model-estimated",
    ):
        assert re.search(forbidden, visible_text, flags=re.IGNORECASE) is None


def test_quran_guide_is_included_and_never_sends_user_out_for_setup():
    html = _ui_text("index.html")
    guide = _ui_text("quran-reference.js")

    assert "complete reviewed guide is included" in html
    assert "quranReferenceFile" not in html
    assert "tanzil.net/download" not in html
    assert "6,236 Ayahs are included and verified" in guide
    assert "method: 'POST'" not in guide
