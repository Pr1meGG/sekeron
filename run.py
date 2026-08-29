#!/usr/bin/env python3
"""
Sekeron Stage 3 - Artist Intelligence & Recommendation Pipeline

CLI commands:
  python3 run.py ingest --dataset <path>
  python3 run.py evidence --dataset <path>
  python3 run.py intelligence --dataset <path>
  python3 run.py recommend --dataset <path>
  python3 run.py update --dataset <path>
  python3 run.py validate --dataset <path>
  python3 run.py full --dataset <path>
"""

import sys
import json
import argparse
from pathlib import Path

from src.config import Config
from src.ingest import run_ingestion
from src.output import write_ingestion_outputs
from src.validate import validate_ingestion_outputs
from src.intelligence import build_artist_intelligence
from src.recommend import generate_recommendations, generate_updated_recommendations
from src.evidence import compile_evidence_layer


def cmd_ingest(args):
    """Run dataset ingestion pipeline."""
    config = Config.create(args.dataset)
    artists, media, claims, issues = run_ingestion(config)
    write_ingestion_outputs(config, artists, media, claims, issues)
    print(f"Ingestion complete. {len(artists)} artists, {len(media)} media files, {len(claims)} claims.")
    return config


def _baseline_capability_dict(capability) -> dict:
    """
    Serialize a CapabilityAssessment in the baseline evidence.json schema
    (keys: capability, status, confidence, evidence, claims, limitations).
    """
    d = capability.to_dict()
    d["evidence"] = d.pop("supporting_evidence", [])
    d["claims"] = d.pop("supporting_claims", [])
    d.pop("artist_key", None)
    return d


def cmd_evidence(args):
    """Run evidence extraction pipeline."""
    config = Config.create(args.dataset)

    # Load ingestion data
    ingestion_path = config.output_dir / "ingestion.json"
    with open(ingestion_path, 'r', encoding='utf-8') as f:
        ingestion_data = json.load(f)

    # Compile evidence (technical observations, content observations, assessments, quality)
    tech_obs, content_obs, assessments, quality_summary = compile_evidence_layer(ingestion_data)

    # Write evidence output preserving the baseline schema:
    #   top-level: artists, observations, evidence_quality
    #   capability keys: capability, status, confidence, evidence, claims, limitations
    evidence_path = config.output_dir / "evidence.json"
    evidence_data = {
        "artists": [
            {
                "artist_key": a["artist_key"],
                "capabilities": [
                    _baseline_capability_dict(c)
                    for c in assessments if c.artist_key == a["artist_key"]
                ]
            }
            for a in ingestion_data["artists"]
        ],
        "observations": [o.to_dict() for o in content_obs],
        "evidence_quality": quality_summary,
    }

    with open(evidence_path, 'w', encoding='utf-8') as f:
        json.dump(evidence_data, f, indent=2)

    print(f"Evidence layer compiled. {len(assessments)} capability assessments, "
          f"{len(content_obs)} observations.")
    return config


def cmd_intelligence(args):
    """Build artist intelligence JSONL."""
    config = Config.create(args.dataset)
    path = build_artist_intelligence(config.output_dir)
    print(f"Artist intelligence built at {path}")
    return config


def cmd_recommend(args):
    """Generate recommendations."""
    config = Config.create(args.dataset)
    path = generate_recommendations(config.output_dir, config.dataset_root)
    print(f"Recommendations generated at {path}")
    return config


def cmd_update(args):
    """Process follow-up and generate updated recommendations."""
    config = Config.create(args.dataset)
    path = generate_updated_recommendations(config.output_dir, config.dataset_root)
    print(f"Updated recommendations generated at {path}")
    return config


def cmd_validate(args):
    """Validate all outputs."""
    config = Config.create(args.dataset)

    all_valid = True
    errors = []

    # Validate ingestion outputs
    valid, errs = validate_ingestion_outputs(config.output_dir)
    if not valid:
        all_valid = False
        errors.extend(errs)

    # Validate artist_intelligence.jsonl
    intelligence_path = config.output_dir / "artist_intelligence.jsonl"
    if intelligence_path.exists():
        try:
            with open(intelligence_path, 'r', encoding='utf-8') as f:
                records = [json.loads(line) for line in f if line.strip()]
            keys = [r.get("artist_key") for r in records]
            if len(records) != 15 or len(set(keys)) != 15:
                all_valid = False
                errors.append(f"Expected 15 unique artist records, got {len(records)}")
            required_intelligence_keys = {"artist_key", "category", "display_name", "capabilities", "supporting_claims_summary", "unknowns", "overall_confidence"}
            for record in records:
                missing = required_intelligence_keys - set(record)
                if missing:
                    all_valid = False
                    errors.append(f"Artist record missing keys: {sorted(missing)}")
        except (json.JSONDecodeError, OSError) as exc:
            all_valid = False
            errors.append(f"Invalid artist_intelligence.jsonl: {exc}")
    else:
        all_valid = False
        errors.append("Missing artist_intelligence.jsonl")

    # Validate recommendations.json
    rec_path = config.output_dir / "recommendations.json"
    if rec_path.exists():
        with open(rec_path, 'r', encoding='utf-8') as f:
            rec_data = json.load(f)
        recs = rec_data.get("recommendations", [])
        if len(recs) != 4:
            all_valid = False
            errors.append(f"Expected 4 brief recommendations, got {len(recs)}")
        for r in recs:
            questions = r.get("improve_your_matches", [])
            if len(questions) > 2:
                all_valid = False
                errors.append(f"Brief {r['brief_id']} has {len(questions)} refinement questions (max 2)")
    else:
        all_valid = False
        errors.append("Missing recommendations.json")

    if all_valid:
        print("All validations passed.")
    else:
        print("Validation errors:")
        for e in errors:
            print(f"  - {e}")

    return all_valid


def cmd_full(args):
    """Run the full pipeline."""
    print("=" * 60)
    print("SEKERON STAGE 3 - FULL PIPELINE")
    print("=" * 60)

    # Step 1: Ingest
    print("\n[1/5] Running ingestion...")
    config = cmd_ingest(args)

    # Step 2: Evidence
    print("\n[2/5] Running evidence layer...")
    cmd_evidence(args)

    # Step 3: Intelligence
    print("\n[3/5] Building artist intelligence...")
    cmd_intelligence(args)

    # Step 4: Recommendations
    print("\n[4/5] Generating recommendations...")
    cmd_recommend(args)

    # Step 5: Follow-up update
    print("\n[5/5] Processing follow-up updates...")
    cmd_update(args)

    # Validate
    print("\n" + "=" * 60)
    print("VALIDATION")
    print("=" * 60)
    cmd_validate(args)

    print("\nPipeline complete.")
    return config


def main():
    parser = argparse.ArgumentParser(
        description="Sekeron Stage 3 Artist Intelligence & Recommendation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  ingest     Run dataset ingestion pipeline
  evidence   Run evidence extraction layer
  intelligence  Build artist_intelligence.jsonl
  recommend  Generate recommendations.json
  update     Process follow-up and generate updated_recommendation.json
  validate   Validate all outputs
  full       Run complete pipeline

Examples:
  python3 run.py --dataset /path/to/Sekeron/Data\\ set full
  python3 run.py --dataset /path/to/Sekeron/Data\\ set intelligence
        """
    )

    parser.add_argument("--dataset", required=True, help="Path to the dataset directory")

    subparsers = parser.add_subparsers(dest="command", required=True, help="Command to run")

    # Ingest
    ingest_parser = subparsers.add_parser("ingest", help="Run dataset ingestion pipeline")

    # Evidence
    evidence_parser = subparsers.add_parser("evidence", help="Run evidence extraction pipeline")

    # Intelligence
    intelligence_parser = subparsers.add_parser("intelligence", help="Build artist_intelligence.jsonl")

    # Recommend
    recommend_parser = subparsers.add_parser("recommend", help="Generate recommendations.json")

    # Update
    update_parser = subparsers.add_parser("update", help="Process follow-up and generate updated_recommendation.json")

    # Validate
    validate_parser = subparsers.add_parser("validate", help="Validate all outputs")

    # Full pipeline
    full_parser = subparsers.add_parser("full", help="Run complete pipeline")

    args = parser.parse_args()

    # Route to command handler
    commands = {
        "ingest": cmd_ingest,
        "evidence": cmd_evidence,
        "intelligence": cmd_intelligence,
        "recommend": cmd_recommend,
        "update": cmd_update,
        "validate": cmd_validate,
        "full": cmd_full
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
