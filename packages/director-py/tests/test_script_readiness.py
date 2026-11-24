"""Pre-VO script visualizability and breath-pause readiness audit tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from vedit.cli import app
from vedit.director.script_readiness import audit_script_readiness
from vedit.director.storyboard import idioms_path, load_directing_idioms


def _make_transcript(clauses: list[tuple[list[str], float, float]], gap_s: float = 0.35) -> dict:
    """Build a word-level transcript from (words, word_dur_s, word_step_s) tuples."""
    words: list[dict] = []
    t = 0.0
    for tokens, word_dur, word_step in clauses:
        for idx, tok in enumerate(tokens):
            words.append(
                {
                    "text": tok,
                    "start_s": round(t, 3),
                    "end_s": round(t + word_dur, 3),
                }
            )
            if idx < len(tokens) - 1:
                t += word_step
            else:
                t += word_dur + gap_s
    text = " ".join(w["text"] for w in words)
    return {
        "source_hash": "12345678abcdef",
        "provider": "test",
        "language": "en",
        "duration_s": round(words[-1]["end_s"] if words else 0.0, 3),
        "text": text,
        "words": words,
    }


def test_concrete_geoverum_transcript_passes_readiness() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    transcript = _make_transcript(
        [
            (["In", "1998,", "27", "km", "in", "Chile."], 0.35, 0.42),
            (["Rebels", "arrested", "him", "in", "Panama."], 0.35, 0.42),
            (["Then", "he", "walked", "north", "to", "Alaska."], 0.35, 0.42),
            (["No", "country", "denied", "500", "people."], 0.35, 0.42),
        ]
    )
    report = audit_script_readiness(transcript, idioms)
    assert report.ready is True
    assert report.fallback_share <= 0.35
    assert not any(f.severity == "error" for f in report.findings)


def test_dry_abstract_streak_flags_rewrite_and_high_fallback_share() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    transcript = _make_transcript(
        [
            (["actually", "matters", "deeply", "here."], 0.35, 0.42),
            (["people", "often", "consider", "things."], 0.35, 0.42),
            (["something", "feels", "different", "today."], 0.35, 0.42),
            (["another", "perspective", "emerges", "slowly."], 0.35, 0.42),
            (["overall", "context", "remains", "unclear."], 0.35, 0.42),
        ]
    )
    report = audit_script_readiness(transcript, idioms)
    assert report.ready is False
    codes = {f.code for f in report.findings}
    assert "dry_clause_streak" in codes
    assert "high_fallback_share" in codes
    streak_finding = next(f for f in report.findings if f.code == "dry_clause_streak")
    assert len(streak_finding.beat_ids) >= 3


def test_compressed_reading_clause_recommends_breath_pause() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    transcript = _make_transcript(
        [
            (["In", "1998", "Chile."], 0.3, 0.35),
            (["Only", "27", "days."], 0.05, 0.15),  # spoken span = 0.15 + 0.15 + 0.05 = 0.35s
            (["He", "walked", "north", "to", "Alaska."], 0.35, 0.42),
        ]
    )
    report = audit_script_readiness(transcript, idioms)
    pause_findings = [f for f in report.findings if f.code == "needs_breath_pause"]
    assert pause_findings
    assert pause_findings[0].recommended_pause_ms is not None
    assert pause_findings[0].recommended_pause_ms >= 250


def test_cli_storyboard_readiness_json_output(tmp_path: Path) -> None:
    runner = CliRunner()

    ready_path = tmp_path / "ready.json"
    ready_path.write_text(
        json.dumps(
            _make_transcript(
                [
                    (["In", "1998,", "27", "km", "in", "Chile."], 0.35, 0.42),
                    (["Rebels", "arrested", "him", "in", "Panama."], 0.35, 0.42),
                    (["Then", "he", "walked", "north", "to", "Alaska."], 0.35, 0.42),
                ]
            )
        ),
        encoding="utf-8",
    )
    res_ok = runner.invoke(
        app,
        ["storyboard", "readiness", str(ready_path), "--brand", "geoverum"],
    )
    assert res_ok.exit_code == 0, res_ok.output
    payload_ok = json.loads(res_ok.output)
    assert payload_ok["ready"] is True

    dry_path = tmp_path / "dry.json"
    dry_path.write_text(
        json.dumps(
            _make_transcript(
                [
                    (["actually", "matters", "deeply", "here."], 0.35, 0.42),
                    (["people", "often", "consider", "things."], 0.35, 0.42),
                    (["something", "feels", "different", "today."], 0.35, 0.42),
                    (["another", "perspective", "emerges", "slowly."], 0.35, 0.42),
                ]
            )
        ),
        encoding="utf-8",
    )
    res_fail = runner.invoke(
        app,
        ["storyboard", "readiness", str(dry_path), "--brand", "geoverum", "--strict"],
    )
    assert res_fail.exit_code == 1, res_fail.output
    payload_fail = json.loads(res_fail.output)
    assert payload_fail["ready"] is False
