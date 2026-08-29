#!/usr/bin/env python3
"""
Phase 1: Build artist_intelligence.jsonl

Reads existing ingestion.json and evidence.json, then produces exactly one
JSONL record per artist with:
  - artist_key, category, display_name
  - capabilities (list of {capability, status, confidence, evidence, claims, limitations})
  - supporting_claims_summary (list of claim strings)
  - unknowns (sorted list of UNKNOWN capabilities)
  - overall_confidence (HIGH if any DEMONSTRATED, else MEDIUM/LOW)

No hard-coded artist IDs, names, or final capability outcomes.
"""

import json
from pathlib import Path
from typing import Dict, Any, List


def build_artist_intelligence(output_dir: Path) -> Path:
    """
    Build artist_intelligence.jsonl from ingestion.json and evidence.json.

    Returns the path to the generated JSONL file.
    """
    ingestion_path = output_dir / "ingestion.json"
    evidence_path = output_dir / "evidence.json"

    if not ingestion_path.exists():
        raise FileNotFoundError(f"ingestion.json not found at {ingestion_path}")
    if not evidence_path.exists():
        raise FileNotFoundError(f"evidence.json not found at {evidence_path}")

    with open(ingestion_path, 'r', encoding='utf-8') as f:
        ingestion_data = json.load(f)
    with open(evidence_path, 'r', encoding='utf-8') as f:
        evidence_data = json.load(f)

    artists_raw = ingestion_data.get("artists", [])
    evidence_artists = evidence_data.get("artists", [])

    # Map evidence by artist_key -> list of capabilities
    evidence_map: Dict[str, List[Dict[str, Any]]] = {}
    for item in evidence_artists:
        ak = item["artist_key"]
        evidence_map[ak] = item.get("capabilities", [])

    # Retain source paths for evidence locators. Evidence assessments store
    # asset keys; ingestion is the authoritative source for their full paths.
    media_map: Dict[str, Dict[str, Any]] = {
        f"{m.get('artist_key')}::{m.get('asset_key')}" : m
        for m in ingestion_data.get("media", [])
    }

    # Map profile claims by artist_key -> list of claims
    claims_raw = ingestion_data.get("profile_claims", [])
    claims_map: Dict[str, List[Dict[str, Any]]] = {}
    for c in claims_raw:
        claims_map.setdefault(c["artist_key"], []).append(c)

    jsonl_path = output_dir / "artist_intelligence.jsonl"
    records_written = 0

    with open(jsonl_path, 'w', encoding='utf-8') as f:
        for artist in sorted(artists_raw, key=lambda x: x["artist_key"]):
            key = artist["artist_key"]
            caps = evidence_map.get(key, [])

            # Build supporting_claims_summary from profile claims only
            claim_texts = [c["claim"] for c in claims_map.get(key, [])]

            # Collect unknown capabilities
            unknowns = sorted(list(set(
                c["capability"] for c in caps if c.get("status") == "UNKNOWN"
            )))

            # Overall confidence: HIGH if any DEMONSTRATED with MEDIUM+ confidence
            overall = "LOW"
            has_demonstrated = False
            for c in caps:
                if c.get("status") == "DEMONSTRATED":
                    has_demonstrated = True
                    if c.get("confidence") == "HIGH":
                        overall = "HIGH"
                        break
                    elif c.get("confidence") == "MEDIUM" and overall != "HIGH":
                        overall = "MEDIUM"
            if has_demonstrated and overall == "LOW":
                overall = "MEDIUM"
            elif not has_demonstrated:
                # Check if any CLAIMED_ONLY exists
                has_claims = any(c.get("status") == "CLAIMED_ONLY" for c in caps)
                overall = "MEDIUM" if has_claims else "LOW"

            # Keep claim and evidence provenance visible at record level while
            # preserving the richer capability-level structures from evidence.json.
            supporting_evidence = []
            for capability in caps:
                for asset_key in capability.get("evidence", capability.get("supporting_evidence", [])):
                    media = media_map.get(f"{key}::{asset_key}", {})
                    supporting_evidence.append({
                        "asset_key": asset_key,
                        "source_file": media.get("path", asset_key),
                        "locator": "asset filename; semantic content not independently verified"
                    })
            supporting_claims = []
            for claim in claims_map.get(key, []):
                supporting_claims.append({
                    "claim": claim["claim"],
                    "source_file": claim.get("source_file"),
                    "locator": claim.get("section_or_locator")
                })

            record = {
                "artist_key": key,
                "category": artist["category"],
                "display_name": artist["display_name"],
                "capabilities": caps,
                "supporting_evidence": supporting_evidence,
                "supporting_claims": supporting_claims,
                "supporting_claims_summary": claim_texts,
                "unknowns": unknowns,
                "overall_confidence": overall
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            records_written += 1

    return jsonl_path


if __name__ == "__main__":
    import sys
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs")
    path = build_artist_intelligence(output_dir)
    print(f"Intelligence built at {path}")
