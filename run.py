#!/usr/bin/env python3
import sys
import json
import argparse
from pathlib import Path

from src.config import Config
from src.ingest import run_ingestion
from src.output import write_ingestion_outputs
from src.validate import validate_ingestion_outputs

def main():
    parser = argparse.ArgumentParser(description="Sekeron Stage 3 Artist Intelligence & Recommendation Pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Ingest subcommand
    ingest_parser = subparsers.add_parser("ingest", help="Run dataset ingestion pipeline")
    ingest_parser.add_argument("--dataset", required=True, help="Path to the dataset directory")
    ingest_parser.add_argument("--output", help="Optional override path for output directory")
    
    # Evidence subcommand
    evidence_parser = subparsers.add_parser("evidence", help="Run evidence extraction pipeline")
    evidence_parser.add_argument("--dataset", required=True, help="Path to the dataset directory")
    evidence_parser.add_argument("--output", help="Optional override path for output directory")
    
    args = parser.parse_args()
    
    if args.command == "ingest":
        dataset_path = Path(args.dataset)
        if not dataset_path.exists():
            print(f"Error: Dataset path '{dataset_path}' does not exist.", file=sys.stderr)
            sys.exit(1)
            
        print(f"Initializing Ingestion Configuration...")
        config = Config.create(str(dataset_path), args.output)
        print(f"Dataset Root: {config.dataset_root}")
        print(f"Output Directory: {config.output_dir}")
        
        print("\nScanning dataset and processing profiles & media...")
        try:
            artists, media, claims, issues = run_ingestion(config)
        except Exception as e:
            print(f"Fatal error during dataset ingestion: {str(e)}", file=sys.stderr)
            sys.exit(1)
            
        print(f"\nIngestion Complete:")
        print(f"  Discovered Artists: {len(artists)}")
        print(f"  Processed Profiles: {sum(1 for a in artists if a.profile_files)}")
        print(f"  Processed Media Assets: {len(media)}")
        print(f"  Extracted Profile Claims: {len(claims)}")
        print(f"  Quality/Anomaly Issues Raised: {len(issues)}")
        
        # Check expected vs actual assessment artists
        photographers = sum(1 for a in artists if a.category == "photographer")
        musicians = sum(1 for a in artists if a.category == "musician")
        editors = sum(1 for a in artists if a.category == "video_editor")
        
        print(f"\nBreakdown by Category:")
        print(f"  Photographers: {photographers} (Expected: 5)")
        print(f"  Musicians: {musicians} (Expected: 5)")
        print(f"  Video Editors: {editors} (Expected: 5)")
        
        # Soft warnings if actuals do not match expected assessment parameters
        if len(artists) != 15 or photographers != 5 or musicians != 5 or editors != 5:
            print("\n[WARNING] Discovered artist counts differ from the expected Sekeron stage assessment targets (15 total, 5/5/5 split).")
            
        print("\nWriting JSON output databases...")
        ingestion_path, summary_path = write_ingestion_outputs(config, artists, media, claims, issues)
        print(f"Wrote Ingestion Database to: {ingestion_path}")
        print(f"Wrote Summary to: {summary_path}")
        
        print("\nValidating outputs...")
        is_valid, validation_errors = validate_ingestion_outputs(config.output_dir)
        if is_valid:
            print("Validation successful: JSON files match the expected schema!")
        else:
            print("Validation errors detected in JSON output files:", file=sys.stderr)
            for err in validation_errors:
                print(f"  - {err}", file=sys.stderr)
            sys.exit(2)
            
        print("\nPhase 1 Ingestion Pipeline executed successfully!")

    elif args.command == "evidence":
        config = Config.create(args.dataset, args.output)
        ingestion_path = config.output_dir / "ingestion.json"
        if not ingestion_path.exists():
            print(f"Error: Ingestion database '{ingestion_path}' not found. Please run 'ingest' command first.", file=sys.stderr)
            sys.exit(1)
            
        print(f"Loading Ingestion Database from {ingestion_path}...")
        with open(ingestion_path, 'r', encoding='utf-8') as f:
            ingestion_data = json.load(f)
            
        print("Compiling evidence observations and capability assessments...")
        from src.evidence import compile_evidence_layer
        tech_obs, content_obs, assessments, quality_summary = compile_evidence_layer(ingestion_data)
        
        # Group capability assessments by artist key
        grouped_assessments = {}
        for a in assessments:
            grouped_assessments.setdefault(a.artist_key, []).append({
                "capability": a.capability,
                "status": a.status,
                "confidence": a.confidence,
                "evidence": a.supporting_evidence,
                "claims": a.supporting_claims,
                "limitations": a.limitations
            })
            
        artists_output = []
        for key, caps in sorted(grouped_assessments.items()):
            artists_output.append({
                "artist_key": key,
                "capabilities": caps
            })
            
        evidence_data = {
            "artists": artists_output,
            "observations": [c.to_dict() for c in content_obs],
            "evidence_quality": quality_summary
        }
        
        evidence_path = config.output_dir / "evidence.json"
        print(f"Writing evidence data to {evidence_path}...")
        with open(evidence_path, 'w', encoding='utf-8') as f:
            json.dump(evidence_data, f, indent=2)
            
        # Summary statistics
        demo_count = sum(1 for a in assessments if a.status == "DEMONSTRATED")
        claim_count = sum(1 for a in assessments if a.status == "CLAIMED_ONLY")
        unk_count = sum(1 for a in assessments if a.status == "UNKNOWN")
        prov_count = sum(1 for a in assessments if "LIMITED_BY_PROVENANCE" in a.limitations)
        
        print("\nEvidence Analysis Summary:")
        print(f"  Total Capability Assessments: {len(assessments)}")
        print(f"  Demonstrated: {demo_count}")
        print(f"  Claimed Only: {claim_count}")
        print(f"  Unknown: {unk_count}")
        print(f"  Provenance Limited: {prov_count}")
        
        print("\nPhase 2 Evidence Intelligence executed successfully!")

if __name__ == "__main__":
    main()
