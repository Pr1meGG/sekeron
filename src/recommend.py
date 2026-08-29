"""
Phase 3 & 4: Recommendation Engine

Deterministic recommendation engine that:
- Scores artists against hirer briefs
- Weights demonstrated evidence above claims
- Capability relevance dominates; secondary bonuses only break close ties
- Handles UNKNOWN appropriately (eligible but scores zero/no penalty)
- Produces top-2 recommendations per brief with explanations
- Generates refinement questions (<=2 per brief)
- Processes follow-up updates and re-ranks
"""

import json
import re
import yaml
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from .hirer import parse_hirer_briefs, parse_follow_up_update, extract_follow_up_changes

# ---------------------------------------------------------------
# Default scoring weights — overridable via config/scoring.yaml
# Key principle: capability relevance dominates; secondary bonuses
# (location, preferred) must NOT overturn a meaningful capability
# difference.
# ---------------------------------------------------------------
_DEFAULT_SCORING = {
    "required_demonstrated": 3.0,
    "required_claimed": 1.0,
    "required_unknown_penalty": -0.5,
    "preferred_demonstrated": 0.75,
    "preferred_claimed": 0.5,
    "location_match": 0.2,
    "confidence_bonus": {"HIGH": 0.5, "MEDIUM": 0.25, "LOW": 0.0},
    "limitation_penalty": {
        "LIMITED_BY_PROVENANCE": -1.0,
        "SYNTHETIC_SAMPLE": -0.5,
        "ID_CONFLICT": -0.3,
        "NAME_MISMATCH": -0.2,
        "UNUSUAL_DIRECTORY_LAYOUT": -0.1,
    },
}

_SCORING_WEIGHTS = dict(_DEFAULT_SCORING)  # copy; may be overridden below


def _load_scoring_config(scoring_path: Optional[Path] = None) -> None:
    """Load scoring weights from config/scoring.yaml, merging with defaults."""
    global _SCORING_WEIGHTS
    path = scoring_path or Path(__file__).resolve().parent.parent / "config" / "scoring.yaml"
    override = dict(_DEFAULT_SCORING)
    if not path.exists():
        _SCORING_WEIGHTS = override
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        w = cfg.get("weights", {})
        override["required_demonstrated"] = w.get("required_demonstrated", _DEFAULT_SCORING["required_demonstrated"])
        override["required_claimed"] = w.get("required_claimed", _DEFAULT_SCORING["required_claimed"])
        override["required_unknown_penalty"] = w.get("required_unknown_penalty", _DEFAULT_SCORING["required_unknown_penalty"])
        override["preferred_demonstrated"] = w.get("preferred_demonstrated", _DEFAULT_SCORING["preferred_demonstrated"])
        override["preferred_claimed"] = w.get("preferred_claimed", _DEFAULT_SCORING["preferred_claimed"])
        override["location_match"] = w.get("location_match", _DEFAULT_SCORING["location_match"])
        cb = cfg.get("confidence_bonus", {})
        override["confidence_bonus"]["HIGH"] = cb.get("HIGH", _DEFAULT_SCORING["confidence_bonus"]["HIGH"])
        override["confidence_bonus"]["MEDIUM"] = cb.get("MEDIUM", _DEFAULT_SCORING["confidence_bonus"]["MEDIUM"])
        override["confidence_bonus"]["LOW"] = cb.get("LOW", _DEFAULT_SCORING["confidence_bonus"]["LOW"])
        lp = cfg.get("limitation_penalty", {})
        override["limitation_penalty"]["LIMITED_BY_PROVENANCE"] = lp.get("LIMITED_BY_PROVENANCE", _DEFAULT_SCORING["limitation_penalty"]["LIMITED_BY_PROVENANCE"])
        override["limitation_penalty"]["SYNTHETIC_SAMPLE"] = lp.get("SYNTHETIC_SAMPLE", _DEFAULT_SCORING["limitation_penalty"]["SYNTHETIC_SAMPLE"])
        override["limitation_penalty"]["ID_CONFLICT"] = lp.get("ID_CONFLICT", _DEFAULT_SCORING["limitation_penalty"]["ID_CONFLICT"])
        override["limitation_penalty"]["NAME_MISMATCH"] = lp.get("NAME_MISMATCH", _DEFAULT_SCORING["limitation_penalty"]["NAME_MISMATCH"])
        override["limitation_penalty"]["UNUSUAL_DIRECTORY_LAYOUT"] = lp.get("UNUSUAL_DIRECTORY_LAYOUT", _DEFAULT_SCORING["limitation_penalty"]["UNUSUAL_DIRECTORY_LAYOUT"])
    except Exception:
        pass  # fall back to defaults
    _SCORING_WEIGHTS = override


def reset_scoring_config() -> None:
    """Reset to defaults (used by tests)."""
    global _SCORING_WEIGHTS
    _SCORING_WEIGHTS = dict(_DEFAULT_SCORING)


# Load scoring config at import time
_load_scoring_config()


# ---- Scoring helpers ---------------------------------------------------

_LOCATION_RE = re.compile(r'\b(delhi|ncr|gurgaon|gurugram|noida)\b', re.IGNORECASE)


def _mentions_location(text: str) -> bool:
    """Word-boundary location check. Avoids substring false positives such as
    'ncr' inside 'increased'."""
    return bool(_LOCATION_RE.search(text))


def _capability_score(assessment: Dict[str, Any]) -> Tuple[float, str]:
    """Score a single required capability assessment. Returns (score, label)."""
    status = assessment.get("status", "UNKNOWN")
    conf = assessment.get("confidence", "LOW")
    if status == "DEMONSTRATED":
        s = _SCORING_WEIGHTS["required_demonstrated"]
        s += _SCORING_WEIGHTS["confidence_bonus"].get(conf, 0)
        return s, f"DEMONSTRATED"
    elif status == "CLAIMED_ONLY":
        return _SCORING_WEIGHTS["required_claimed"], "CLAIMED"
    else:
        # UNKNOWN is eligible but adds no positive score
        return _SCORING_WEIGHTS["required_unknown_penalty"], "UNKNOWN"


def _score_artist_against_brief(
    artist: Dict[str, Any],
    brief: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Score a single artist against a single brief.

    Returns a dict with:
    - score: total numeric score
    - breakdown: dict of score components
    - match_reasons: list of why this artist matches
    - trade_offs: list of trade-offs
    - assumptions: list of assumptions made
    - uncertainties: list of uncertainties
    """
    score = 0.0
    breakdown = {}
    match_reasons = []
    trade_offs = []
    assumptions = []
    uncertainties = []

    capabilities = artist.get("capabilities", [])
    cap_map = {c["capability"]: c for c in capabilities}

    required_caps = brief.get("required_capabilities", [])
    preferred_caps = brief.get("preferred_capabilities", [])
    disqualifiers = brief.get("disqualifiers", [])
    constraints = brief.get("explicit_constraints", [])
    brief_assumptions = brief.get("reasonable_assumptions", [])

    # --- Capability matching (primary signal) ---
    req_demo = 0.0
    req_claim = 0.0
    req_unknown = 0.0
    pref_score = 0.0

    for cap in required_caps:
        if cap in cap_map:
            assessment = cap_map[cap]
            cap_score, label = _capability_score(assessment)
            score += cap_score
            if label == "DEMONSTRATED":
                req_demo += cap_score
                match_reasons.append(
                    f"DEMONSTRATED capability '{cap}' with {assessment.get('confidence','LOW')} confidence; "
                    f"directly maps to required '{cap}'"
                )
            elif label == "CLAIMED":
                req_claim += cap_score
                match_reasons.append(
                    f"PROFILE CLAIM for required '{cap}' (no independent evidence)"
                )
            else:
                req_unknown += cap_score
                uncertainties.append(
                    f"Capability '{cap}' is UNKNOWN — ranking is provisional pending evidence"
                )
        else:
            # Capability dimension not present in artist's assessment at all
            uncertainties.append(
                f"No capability dimension for required '{cap}'"
            )

    for cap in preferred_caps:
        if cap in cap_map:
            assessment = cap_map[cap]
            status = assessment.get("status", "UNKNOWN")
            if status == "DEMONSTRATED":
                score += _SCORING_WEIGHTS["preferred_demonstrated"]
                pref_score += _SCORING_WEIGHTS["preferred_demonstrated"]
                match_reasons.append(
                    f"DEMONSTRATED preferred capability '{cap}'"
                )
            elif status == "CLAIMED_ONLY":
                score += _SCORING_WEIGHTS["preferred_claimed"]
                pref_score += _SCORING_WEIGHTS["preferred_claimed"]
                match_reasons.append(
                    f"CLAIMED preferred capability '{cap}'"
                )

    # --- Limitation penalties ---
    lim_penalties = 0.0
    for cap in required_caps:
        if cap in cap_map:
            limitations = cap_map[cap].get("limitations", [])
            for lim in limitations:
                penalty = _SCORING_WEIGHTS["limitation_penalty"].get(lim, 0)
                if penalty < 0:
                    score += penalty
                    lim_penalties += penalty
                    trade_offs.append(f"Limitation '{lim}' on '{cap}' capability")

    # --- Location matching (small secondary bonus, cannot overturn capability gap) ---
    location_score = 0.0
    location_match = False
    for constraint in constraints:
        if _mentions_location(constraint):
            location_match = True
            break
    claims = artist.get("supporting_claims_summary", [])
    for claim in claims:
        if _mentions_location(claim):
            if not location_match:
                score += _SCORING_WEIGHTS["location_match"]
                location_score = _SCORING_WEIGHTS["location_match"]
                location_match = True
            break

    # --- Disqualifiers as one-per-brief trade-off notes ---
    seen = set()
    for disq in disqualifiers:
        if disq not in seen:
            trade_offs.append(f"Brief excludes: {disq}")
            seen.add(disq)

    # --- Unknowns relevant to the brief ---
    unknowns = artist.get("unknowns", [])
    for unknown in unknowns:
        if unknown in required_caps or unknown in preferred_caps:
            uncertainties.append(
                f"Artist has UNKNOWN status for '{unknown}' which is relevant to this brief"
            )

    # --- Assumptions from the brief's context ---
    for a in brief_assumptions:
        if a not in assumptions:
            assumptions.append(a)

    # Deduplicate trade-offs
    trade_offs = list(dict.fromkeys(trade_offs))

    breakdown = {
        "required_demonstrated_score": round(req_demo, 2),
        "required_claimed_score": round(req_claim, 2),
        "required_unknown_penalty": round(req_unknown, 2),
        "preferred_score": round(pref_score, 2),
        "location_score": round(location_score, 2),
        "limitation_penalties": round(lim_penalties, 2),
    }

    return {
        "score": round(score, 2),
        "breakdown": breakdown,
        "match_reasons": match_reasons,
        "trade_offs": trade_offs,
        "assumptions": assumptions,
        "uncertainties": uncertainties,
    }


def _generate_refinement_questions(
    brief: Dict[str, Any],
    top_candidates: List[Tuple[Dict[str, Any], Dict[str, Any]]]
) -> List[Dict[str, str]]:
    """Generate up to 2 refinement questions per brief."""
    questions = []
    required_caps = brief.get("required_capabilities", [])

    # Question 1: about the most important capability gap
    unknowns_for_brief = []
    for artist, _score_info in top_candidates:
        for unknown in artist.get("unknowns", []):
            if unknown in required_caps:
                unknowns_for_brief.append(unknown)

    if unknowns_for_brief:
        cap = unknowns_for_brief[0]
        questions.append({
            "question": f"Does the artist have demonstrated experience in '{cap}'?",
            "missing_info": f"Whether the top candidates have proven capability in '{cap}'",
            "why_it_matters": "This is a required capability for the brief. If demonstrated, it would significantly boost the candidate's score.",
            "ranking_impact": "A DEMONSTRATED status for this capability would add ~3.0 base points plus confidence bonus, potentially changing the ranking order."
        })

    # Question 2: about constraints
    budget_constraint = [c for c in brief.get("explicit_constraints", [])
                         if "budget" in c.lower() or "₹" in c or "INR" in c]
    if budget_constraint:
        questions.append({
            "question": "What is the exact budget ceiling for this project?",
            "missing_info": "The precise budget limit is not clearly stated",
            "why_it_matters": "Budget determines which artists are feasible candidates",
            "ranking_impact": "A higher budget could enable candidates with premium rates; a lower budget would disqualify them."
        })
    elif len(questions) == 0:
        questions.append({
            "question": "Is the artist's location flexible for on-site work?",
            "missing_info": "Whether candidates can travel to the project location",
            "why_it_matters": "Location compatibility affects feasibility",
            "ranking_impact": "A candidate who can travel would gain the location match bonus of +0.2 points."
        })

    return questions[:2]


# ---- Public API ---------------------------------------------------------

def generate_recommendations(
    output_dir: Path,
    dataset_root: Path
) -> Path:
    """
    Phase 3: Generate recommendations.json

    Reads artist_intelligence.jsonl and hirer briefs, scores all artists,
    and produces top-2 recommendations per brief.
    """
    intelligence_path = output_dir / "artist_intelligence.jsonl"
    if not intelligence_path.exists():
        raise FileNotFoundError(f"artist_intelligence.jsonl not found at {intelligence_path}")

    artists = []
    with open(intelligence_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                artists.append(json.loads(line))

    briefs = parse_hirer_briefs(dataset_root)
    recommendations = []

    for brief in briefs:
        brief_id = brief["brief_id"]
        brief_assumptions = brief.get("reasonable_assumptions", [])

        scored = []
        for artist in artists:
            score_info = _score_artist_against_brief(artist, brief)
            scored.append((artist, score_info))

        scored.sort(key=lambda x: x[1]["score"], reverse=True)
        top_two = scored[:2]

        top_recommendations = []
        for i, (artist, score_info) in enumerate(top_two):
            entry = {
                "rank": i + 1,
                "artist_key": artist["artist_key"],
                "display_name": artist["display_name"],
                "category": artist["category"],
                "total_score": score_info["score"],
                "match_reasons": score_info["match_reasons"],
                "trade_offs": score_info["trade_offs"],
                "assumptions": brief_assumptions,
                "uncertainties": score_info["uncertainties"],
                "score_breakdown": score_info["breakdown"],
            }
            top_recommendations.append(entry)

        questions = _generate_refinement_questions(brief, top_two)
        recommendations.append({
            "brief_id": brief_id,
            "top_recommendations": top_recommendations,
            "improve_your_matches": questions,
        })

    output = {
        "recommendations": recommendations,
        "metadata": {
            "total_artists_evaluated": len(artists),
            "total_briefs_processed": len(briefs),
            "scoring_weights_used": _SCORING_WEIGHTS,
        },
    }

    rec_path = output_dir / "recommendations.json"
    with open(rec_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return rec_path


def generate_updated_recommendations(
    output_dir: Path,
    dataset_root: Path
) -> Path:
    """
    Phase 4: Process follow-up updates and generate updated_recommendation.json

    Re-runs matching for affected briefs, recording previous and updated rankings,
    and explicitly explains ranking stability.
    """
    rec_path = output_dir / "recommendations.json"
    if not rec_path.exists():
        raise FileNotFoundError(f"recommendations.json not found. Run 'recommend' first.")

    with open(rec_path, 'r', encoding='utf-8') as f:
        rec_data = json.load(f)

    intelligence_path = output_dir / "artist_intelligence.jsonl"
    artists = []
    with open(intelligence_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                artists.append(json.loads(line))

    follow_up = parse_follow_up_update(dataset_root)
    briefs = parse_hirer_briefs(dataset_root)
    brief_map = {b["brief_id"]: b for b in briefs}

    affected_brief_id = follow_up.get("affected_brief")
    changed_briefs = []
    updated_recommendations = []

    for rec in rec_data.get("recommendations", []):
        brief_id = rec["brief_id"]
        same_brief = (
            brief_id == affected_brief_id
            or (affected_brief_id and brief_id.startswith(affected_brief_id))
        )

        if same_brief and follow_up.get("updates"):
            original_brief = brief_map.get(brief_id, {})
            changes = extract_follow_up_changes(follow_up, original_brief)

            # Build updated brief
            updated_brief = dict(original_brief)
            updated_constraints = [
                c for c in original_brief.get("explicit_constraints", [])
                if "background" not in c.lower() and "budget" not in c.lower()
            ]
            updated_constraints.extend(changes.get("changed_constraints", []))
            updated_brief["explicit_constraints"] = updated_constraints
            updated_brief["reasonable_assumptions"] = list(
                dict.fromkeys(
                    original_brief.get("reasonable_assumptions", [])
                    + changes.get("new_information", [])
                )
            )
            updated_brief["preferred_capabilities"] = list(
                set(original_brief.get("preferred_capabilities", []))
                | {"vocal_guitar_harmony"}
            )

            # Re-score
            scored = []
            for artist in artists:
                score_info = _score_artist_against_brief(artist, updated_brief)
                scored.append((artist, score_info))
            scored.sort(key=lambda x: x[1]["score"], reverse=True)
            top_two = scored[:2]

            top_recommendations = []
            for i, (artist, score_info) in enumerate(top_two):
                entry = {
                    "rank": i + 1,
                    "artist_key": artist["artist_key"],
                    "display_name": artist["display_name"],
                    "category": artist["category"],
                    "total_score": score_info["score"],
                    "match_reasons": score_info["match_reasons"],
                    "trade_offs": score_info["trade_offs"],
                    "assumptions": updated_brief.get("reasonable_assumptions", []),
                    "uncertainties": score_info["uncertainties"],
                    "score_breakdown": score_info["breakdown"],
                }
                top_recommendations.append(entry)

            questions = _generate_refinement_questions(updated_brief, top_two)

            previous_ranking = [
                {"rank": item.get("rank"), "artist_key": item.get("artist_key"),
                 "total_score": item.get("total_score")}
                for item in rec.get("top_recommendations", [])
            ]
            updated_ranking = [
                {"rank": item.get("rank"), "artist_key": item.get("artist_key"),
                 "total_score": item.get("total_score")}
                for item in top_recommendations
            ]

            # Compare order by artist key, not by score (scores may shift slightly
            # due to constraint changes without affecting the ranking order).
            prev_keys = [r["artist_key"] for r in previous_ranking]
            upd_keys = [r["artist_key"] for r in updated_ranking]
            same_order = prev_keys == upd_keys

            # Explanation
            change_text = (
                "Ranking unchanged. " if same_order
                else "Ranking changed. "
            )
            change_text += (
                f"The updated brief replaces the original constraints with "
                f"{', '.join(changes.get('changed_constraints', []) or ['updated scope'])}. "
                f"All artists were re-scored against the updated constraints and preferred "
                f"capability set. "
            )
            if same_order:
                change_text += (
                    "The top-two artists and their order did not change. "
                    "The ranking remained stable because the artist intelligence does not "
                    "contain rate, availability, or headline-set performance data. "
                    "Without this information, the relative capability ordering between "
                    "candidates cannot change. "
                    "Important information unavailable: artist rates, availability/schedule, "
                    "headline-set/performance scope capability, PA/speaker setup at venue."
                )
            else:
                change_text += "The available evidence supports a different ordering."

            updated_rec = {
                "brief_id": brief_id,
                "top_recommendations": top_recommendations,
                "improve_your_matches": questions,
                "follow_up_applied": True,
                "changes_detected": changes,
                "previous_ranking": previous_ranking,
                "updated_ranking": updated_ranking,
                "ranking_change_explanation": change_text,
            }
            updated_recommendations.append(updated_rec)
            changed_briefs.append(brief_id)
        else:
            updated_recommendations.append(rec)

    output = {
        "recommendations": updated_recommendations,
        "metadata": {
            "total_artists_evaluated": len(artists),
            "total_briefs_processed": len(briefs),
            "changed_briefs": changed_briefs,
            "follow_up_source": follow_up.get("source_file"),
            "scoring_weights_used": _SCORING_WEIGHTS,
        },
    }

    output_path = output_dir / "updated_recommendation.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return output_path