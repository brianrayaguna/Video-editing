"""Deterministic advisory retrieval from editorial_playbook.json and external brand memory."""

from __future__ import annotations

import copy
import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from vedit.contracts import find_repo_root, validate_against_contract

PLAYBOOK_SCHEMA = "editorial_playbook.schema.json"

HintKind = Literal["exemplar", "grammar_trigger", "winning_beat", "failure_pattern"]

_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "over",
        "under",
        "when",
        "where",
        "which",
        "while",
        "about",
        "are",
        "was",
        "were",
        "have",
        "has",
        "had",
        "not",
        "but",
        "can",
        "will",
        "does",
        "did",
        "its",
        "their",
        "yang",
        "dan",
        "dari",
        "untuk",
        "dengan",
        "pada",
        "ini",
        "itu",
    }
)

_ROLE_ALIASES: dict[str, set[str]] = {
    "obstacle": {"proof", "data_callout"},
    "hinge": {"proof", "setup"},
    "recap": {"outro", "climax"},
}


@dataclass(slots=True)
class RetrievedHint:
    """Single advisory directing hint retrieved from playbook or brand memory."""

    kind: HintKind
    item_id: str
    score: float
    summary: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DirectingContext:
    """Advisory directing context keyed by beat ID plus global triggers and warnings."""

    brand_id: str
    story_shape: str
    global_triggers: list[RetrievedHint] = field(default_factory=list)
    beat_hints: dict[str, list[RetrievedHint]] = field(default_factory=dict)
    failure_warnings: list[RetrievedHint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "brand_id": self.brand_id,
            "story_shape": self.story_shape,
            "global_triggers": [h.to_dict() for h in self.global_triggers],
            "beat_hints": {
                bid: [h.to_dict() for h in hints] for bid, hints in self.beat_hints.items()
            },
            "failure_warnings": [h.to_dict() for h in self.failure_warnings],
        }


def playbook_path(brand_id: str, repo_root: Path | None = None) -> Path:
    """Return the repository path to a brand's editorial_playbook.json."""
    root = repo_root or find_repo_root()
    return root / "profiles" / "brands" / brand_id / "editorial_playbook.json"


def load_editorial_playbook(path: Path) -> dict[str, Any]:
    """Load and validate an editorial_playbook.json file against its Draft 2020-12 schema."""
    data = json.loads(path.expanduser().read_text(encoding="utf-8"))
    errors = validate_against_contract(data, PLAYBOOK_SCHEMA)
    if errors:
        raise ValueError(f"{path.name} failed contract check: {errors}")
    return data


def _tokenize(text: str) -> list[str]:
    normalized = text.lower().replace("_", " ").replace("-", " ")
    return [tok for tok in _TOKEN_RE.findall(normalized) if tok not in _STOPWORDS]


def _bm25_idf(docs: list[list[str]]) -> dict[str, float]:
    n_docs = max(len(docs), 1)
    df: Counter[str] = Counter()
    for doc in docs:
        for tok in set(doc):
            df[tok] += 1
    return {
        tok: math.log((n_docs - freq + 0.5) / (freq + 0.5) + 1.0)
        for tok, freq in df.items()
    }


def _bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    idf: dict[str, float],
    avg_len: float,
) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    k1 = 1.2
    b = 0.75
    counts = Counter(doc_tokens)
    dl = len(doc_tokens)
    denom_norm = k1 * (1.0 - b + b * (dl / max(avg_len, 1.0)))
    total = 0.0
    for q in set(query_tokens):
        tf = counts.get(q, 0)
        if tf <= 0:
            continue
        q_idf = idf.get(q, 0.5)
        total += q_idf * (tf * (k1 + 1.0)) / (tf + denom_norm)
    return total


def _beat_query_tokens(beat: dict[str, Any], story_shape: str) -> list[str]:
    parts = [
        str(beat.get("clause") or ""),
        str(beat.get("story_need") or ""),
        str(beat.get("device") or ""),
        str(beat.get("function") or ""),
        str(beat.get("treatment") or ""),
        story_shape,
    ]
    return _tokenize(" ".join(parts))


def retrieve_directing_context(
    storyboard: dict[str, Any],
    playbook: dict[str, Any],
    *,
    memory: dict[str, Any] | None = None,
    top_k_per_beat: int = 2,
    top_k_triggers: int = 5,
) -> DirectingContext:
    """Retrieve advisory playbook triggers, exemplars, and optional brand memory hints.

    Strictly read-only and advisory; never mutates `storyboard` or executes trigger strings.
    """
    brand_id = str(storyboard.get("brand_id") or playbook.get("brand_id") or "")
    story_shape = str((storyboard.get("story") or {}).get("shape") or "free_form")
    beats = list(storyboard.get("beats") or [])

    triggers = list(playbook.get("grammar_triggers") or [])
    exemplars = list(playbook.get("exemplar_bank") or [])
    winning_beats = list((memory or {}).get("winning_beats") or [])
    failure_patterns = list((memory or {}).get("failure_patterns") or [])

    trig_docs = [
        _tokenize(
            " ".join(
                [
                    str(t.get("trigger_id") or ""),
                    str(t.get("condition") or ""),
                    str(t.get("action") or ""),
                    str(t.get("rationale") or ""),
                ]
            )
        )
        for t in triggers
    ]
    trig_idf = _bm25_idf(trig_docs)
    trig_avg = sum(len(d) for d in trig_docs) / max(len(trig_docs), 1)

    ex_docs = [
        _tokenize(
            " ".join(
                [
                    str(e.get("exemplar_id") or ""),
                    str(e.get("role") or ""),
                    str(e.get("hyperframes_pattern") or ""),
                    str(e.get("notes") or ""),
                ]
            )
        )
        for e in exemplars
    ]
    ex_idf = _bm25_idf(ex_docs)
    ex_avg = sum(len(d) for d in ex_docs) / max(len(ex_docs), 1)

    story_tokens = _tokenize(
        " ".join(
            [
                story_shape,
                str((storyboard.get("story") or {}).get("logline") or ""),
                *(str(b.get("clause") or "") for b in beats),
                *(str(b.get("story_need") or "") for b in beats),
            ]
        )
    )

    global_scored: list[RetrievedHint] = []
    for trig, doc_toks in zip(triggers, trig_docs, strict=False):
        lex = _bm25_score(story_tokens, doc_toks, trig_idf, trig_avg)
        weight = float(trig.get("weight", 0.5))
        score = round((lex + 0.25) * (0.5 + weight), 4)
        global_scored.append(
            RetrievedHint(
                kind="grammar_trigger",
                item_id=str(trig["trigger_id"]),
                score=score,
                summary=str(trig.get("rationale") or trig.get("action") or trig["trigger_id"]),
                payload=copy.deepcopy(trig),
            )
        )
    global_scored.sort(key=lambda h: (-h.score, h.item_id))
    global_triggers = global_scored[: max(0, top_k_triggers)]

    beat_devices = {str(b.get("device") or "") for b in beats}
    failure_warnings: list[RetrievedHint] = []
    for fp in failure_patterns:
        fp_dev = fp.get("device")
        occ = int(fp.get("occurrences", 1))
        if (fp_dev and fp_dev in beat_devices) or occ >= 2:
            failure_warnings.append(
                RetrievedHint(
                    kind="failure_pattern",
                    item_id=str(fp.get("pattern_id") or "failure"),
                    score=round(1.0 + 0.2 * occ, 4),
                    summary=str(fp.get("description") or ""),
                    payload=copy.deepcopy(fp),
                )
            )
    failure_warnings.sort(key=lambda h: (-h.score, h.item_id))

    beat_hints: dict[str, list[RetrievedHint]] = {}
    for beat in beats:
        bid = str(beat["beat_id"])
        fn = str(beat.get("function") or "")
        dev = str(beat.get("device") or "")
        beat_dur = max(0.25, float(beat.get("end_s", 0.0)) - float(beat.get("start_s", 0.0)))
        q_tokens = _beat_query_tokens(beat, story_shape)
        q_set = set(q_tokens)

        candidates: list[RetrievedHint] = []
        raw_ex_scores: list[tuple[dict[str, Any], float, float, float]] = []
        max_lex = 0.0
        for ex, doc_toks in zip(exemplars, ex_docs, strict=False):
            ex_role = str(ex.get("role") or "")
            role_boost = 0.0
            if ex_role == fn:
                role_boost = 2.0
            elif ex_role in _ROLE_ALIASES.get(fn, set()):
                role_boost = 0.8

            ex_dur = max(0.25, float(ex.get("end_s", 0.0)) - float(ex.get("start_s", 0.0)))
            dur_prox = max(0.0, 1.0 - abs(beat_dur - ex_dur) / max(beat_dur, ex_dur, 1.0))
            lex = _bm25_score(q_tokens, doc_toks, ex_idf, ex_avg)
            max_lex = max(max_lex, lex)
            raw_ex_scores.append((ex, role_boost, lex, dur_prox))

        for ex, role_boost, lex, dur_prox in raw_ex_scores:
            norm_lex = (2.0 * lex / max_lex) if max_lex > 0.0 else 0.0
            score = round(role_boost + norm_lex + 0.2 * dur_prox, 4)
            candidates.append(
                RetrievedHint(
                    kind="exemplar",
                    item_id=str(ex["exemplar_id"]),
                    score=score,
                    summary=str(ex.get("notes") or ex.get("hyperframes_pattern") or ""),
                    payload=copy.deepcopy(ex),
                )
            )

        for wb in winning_beats:
            wb_tokens = set(
                _tokenize(
                    f"{wb.get('clause', '')} {wb.get('story_need', '')} {wb.get('device', '')}"
                )
            )
            overlap = len(q_set & wb_tokens)
            fn_match = 1.6 if wb.get("function") == fn else 0.0
            dev_match = 1.0 if wb.get("device") == dev else 0.0
            if fn_match > 0.0 or dev_match > 0.0 or overlap > 0:
                wb_score = round(
                    fn_match
                    + dev_match
                    + min(2.0, 0.5 * overlap)
                    + float(wb.get("rubric_score", 0.85)),
                    4,
                )
                candidates.append(
                    RetrievedHint(
                        kind="winning_beat",
                        item_id=f"{wb.get('project_id', 'ep')}:{wb.get('beat_id', 'beat')}",
                        score=wb_score,
                        summary=str(wb.get("story_need") or wb.get("clause") or ""),
                        payload=copy.deepcopy(wb),
                    )
                )

        for fp in failure_patterns:
            fp_dev = fp.get("device")
            if fp_dev and fp_dev == dev:
                occ = int(fp.get("occurrences", 1))
                fp_score = round(3.8 + 0.25 * occ, 4)
                candidates.append(
                    RetrievedHint(
                        kind="failure_pattern",
                        item_id=str(fp.get("pattern_id") or "failure"),
                        score=fp_score,
                        summary=str(fp.get("description") or ""),
                        payload=copy.deepcopy(fp),
                    )
                )

        candidates.sort(key=lambda h: (-h.score, h.item_id))
        beat_hints[bid] = candidates[: max(0, top_k_per_beat)]

    return DirectingContext(
        brand_id=brand_id,
        story_shape=story_shape,
        global_triggers=global_triggers,
        beat_hints=beat_hints,
        failure_warnings=failure_warnings,
    )
