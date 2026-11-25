"""Tests for executable curiosity loops, tension arc, direction continuity, and readiness checks."""

from __future__ import annotations

from vedit.director.script_readiness import audit_script_readiness
from vedit.director.storyboard import check_storyboard, idioms_path, load_directing_idioms


def _make_transcript(clauses: list[tuple[list[str], float, float]], gap_s: float = 0.35) -> dict:
    words: list[dict] = []
    t = 0.0
    for tokens, word_dur, word_step in clauses:
        for idx, tok in enumerate(tokens):
            words.append({"text": tok, "start_s": round(t, 3), "end_s": round(t + word_dur, 3)})
            t += word_step if idx < len(tokens) - 1 else (word_dur + gap_s)
    return {
        "source_hash": "12345678abcdef",
        "provider": "test",
        "language": "en",
        "duration_s": round(words[-1]["end_s"] if words else 0.0, 3),
        "text": " ".join(w["text"] for w in words),
        "words": words,
    }


def _base_storyboard() -> dict:
    return {
        "schema_version": "1.0",
        "project_id": "story_test",
        "brand_id": "geoverum",
        "duration_s": 24.0,
        "directing_source": "user",
        "pacing": "default",
        "story": {
            "shape": "mystery_answered_late",
            "narrative_framework": "three_act",
            "signature_image": "border_line",
            "curiosity_loops": [
                {
                    "loop_id": "main_mystery",
                    "question": "Why does this enclave loop around two rivers?",
                    "opened_beat_id": "b1",
                    "promise_hinge_beat_id": "b2",
                    "payoff_beat_id": "b4",
                }
            ],
        },
        "beats": [
            {
                "beat_id": "b1",
                "start_s": 0.0,
                "end_s": 2.0,
                "clause": "A border bends twice here",
                "function": "hook",
                "story_need": "show the odd bend",
                "device": "fill",
                "tension_level": 0.72,
                "uses_signature_image": True,
                "shot": {"scale": "ws", "motion_direction": "left_to_right"},
            },
            {
                "beat_id": "b2",
                "start_s": 2.0,
                "end_s": 8.0,
                "clause": "Why did surveyors draw it?",
                "function": "hinge",
                "story_need": "signal the mystery hinge",
                "device": "mood_dip",
                "hold_reason": "pause for question",
                "tension_level": 0.45,
                "shot": {"scale": "ms", "motion_direction": "left_to_right"},
            },
            {
                "beat_id": "b3",
                "start_s": 8.0,
                "end_s": 16.0,
                "clause": "In 1890 the river shifted",
                "function": "proof",
                "story_need": "animate old channel",
                "device": "era_marker",
                "hold_reason": "historical explanation",
                "tension_level": 0.65,
                "split_edit": {"kind": "j_cut", "offset_s": 0.5},
            },
            {
                "beat_id": "b4",
                "start_s": 16.0,
                "end_s": 24.0,
                "clause": "Leaving the town stranded",
                "function": "outro",
                "story_need": "reveal stranded town",
                "device": "pin_and_label",
                "hold_reason": "consequence hold",
                "tension_level": 0.90,
                "uses_signature_image": True,
            },
        ],
    }


def test_storytelling_idioms_pass_and_catch_violations() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    good = _base_storyboard()
    rep_good = check_storyboard(good, idioms)
    assert rep_good.passed, rep_good.to_dict()

    bad = _base_storyboard()
    del bad["story"]["curiosity_loops"][0]["payoff_beat_id"]
    for b in bad["beats"]:
        b["tension_level"] = 0.5
    bad["beats"][1]["shot"]["motion_direction"] = "right_to_left"
    bad["beats"][0]["split_edit"] = {"kind": "j_cut", "offset_s": 0.5}
    rep_bad = check_storyboard(bad, idioms)
    codes = {i.idiom_id for i in rep_bad.issues}
    assert "curiosity_loops_closed" in codes
    assert "tension_arc_dynamic" in codes
    assert "shot_direction_continuity" in codes
    assert "split_edit_bounds" in codes
    assert not rep_bad.passed


def test_script_readiness_detects_throat_clearing_flat_pacing_and_telling() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    tr = _make_transcript(
        [
            (["Hey", "guys", "welcome", "back."], 0.25, 0.30),
            (["Basically", "things", "matter", "now."], 0.25, 0.30),
            (["Simply", "put", "ideas", "change."], 0.25, 0.30),
            (["People", "often", "wonder", "why."], 0.25, 0.30),
            (["In", "other", "words", "yes."], 0.25, 0.30),
            (["Another", "thought", "appears", "here."], 0.25, 0.30),
            (["Context", "always", "shapes", "mind."], 0.25, 0.30),
            (["Overall", "meaning", "stays", "quiet."], 0.25, 0.30),
        ]
    )
    rep = audit_script_readiness(tr, idioms)
    codes = {f.code for f in rep.findings}
    assert "throat_clearing_opening" in codes
    assert "flat_pacing_variance" in codes
    assert "low_show_dont_tell_ratio" in codes
    assert "show_dont_tell_score" in rep.summary
    assert "pacing_std_s" in rep.summary
