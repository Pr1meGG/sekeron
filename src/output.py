import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple
from .models import ArtistRecord, MediaAsset, ProfileClaim, DataQualityIssue
from .config import Config

def write_ingestion_outputs(
    config: Config,
    artists: List[ArtistRecord],
    media: List[MediaAsset],
    claims: List[ProfileClaim],
    issues: List[DataQualityIssue]
) -> Tuple[Path, Path]:
    """
    Serialize the ingestion results into JSON output files inside the configured outputs/ directory.
    Creates the outputs/ folder if it doesn't exist.
    """
    output_dir = config.output_dir
    output_dir.mkdir(exist_ok=True, parents=True)
    
    ingestion_json_path = output_dir / "ingestion.json"
    summary_json_path = output_dir / "ingestion_summary.json"
    
    # 1. Prepare main ingestion.json
    now_str = datetime.utcnow().isoformat() + "Z"
    
    # Calculate file counts
    total_files = len(artists) # each folder counts, but let's count actual files processed
    profile_count = sum(len(a.profile_files) for a in artists)
    media_count = sum(len(a.media_files) for a in artists)
    
    main_data = {
        "dataset": {
            "root_path": str(config.dataset_root),
            "total_artists": len(artists),
            "total_profile_files": profile_count,
            "total_media_files": media_count,
            "ingestion_timestamp": now_str
        },
        "artists": [a.to_dict() for a in artists],
        "media": [m.to_dict() for m in media],
        "profile_claims": [c.to_dict() for c in claims],
        "quality_issues": [i.to_dict() for i in issues]
    }
    
    with open(ingestion_json_path, 'w', encoding='utf-8') as f:
        json.dump(main_data, f, indent=2)

    # 2. Prepare ingestion_summary.json
    categories = {}
    for a in artists:
        categories[a.category] = categories.get(a.category, 0) + 1
        
    image_count = sum(1 for m in media if m.media_type == 'image')
    audio_count = sum(1 for m in media if m.media_type == 'audio')
    # video files include videos
    video_count = sum(1 for m in media if m.media_type == 'video')
    
    duplicate_count = sum(1 for m in media if m.duplicate_of is not None)
    unreadable_count = sum(1 for m in media if not m.readable)
    extension_mismatch_count = sum(1 for m in media if "extension_mismatch" in m.anomalies)
    
    summary_data = {
        "number_of_artists": len(artists),
        "number_by_category": categories,
        "profile_count": profile_count,
        "image_count": image_count,
        "audio_count": audio_count,
        "video_count": video_count,
        "duplicate_count": duplicate_count,
        "unreadable_count": unreadable_count,
        "anomaly_count": len(issues),
        "extension_mismatch_count": extension_mismatch_count
    }
    
    with open(summary_json_path, 'w', encoding='utf-8') as f:
        json.dump(summary_data, f, indent=2)
        
    return ingestion_json_path, summary_json_path
