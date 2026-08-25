import json
from pathlib import Path
from typing import Dict, Any, Tuple, List

def validate_ingestion_outputs(output_dir: Path) -> Tuple[bool, List[str]]:
    """
    Validate that the generated files in output_dir conform strictly to the expected schemas.
    Returns (is_valid, list_of_error_messages).
    """
    errors = []
    
    ingestion_json_path = output_dir / "ingestion.json"
    summary_json_path = output_dir / "ingestion_summary.json"
    
    # 1. Validate ingestion.json
    if not ingestion_json_path.exists():
        errors.append("Missing ingestion.json file.")
    else:
        try:
            with open(ingestion_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            required_keys = {"dataset", "artists", "media", "profile_claims", "quality_issues"}
            missing_keys = required_keys - set(data.keys())
            if missing_keys:
                errors.append(f"ingestion.json is missing top-level keys: {missing_keys}")
                
            # Basic type checks
            for key in ["artists", "media", "profile_claims", "quality_issues"]:
                if key in data and not isinstance(data[key], list):
                    errors.append(f"ingestion.json key '{key}' must be a list, found {type(data[key]).__name__}.")
                    
            if "dataset" in data:
                if not isinstance(data["dataset"], dict):
                    errors.append(f"ingestion.json key 'dataset' must be a dict.")
                else:
                    dataset_keys = {"root_path", "total_artists", "total_profile_files", "total_media_files", "ingestion_timestamp"}
                    missing_dataset_keys = dataset_keys - set(data["dataset"].keys())
                    if missing_dataset_keys:
                        errors.append(f"ingestion.json dataset metadata is missing keys: {missing_dataset_keys}")
                        
        except json.JSONDecodeError as e:
            errors.append(f"Failed to parse ingestion.json as valid JSON: {str(e)}")
        except Exception as e:
            errors.append(f"Error reading ingestion.json: {str(e)}")

    # 2. Validate ingestion_summary.json
    if not summary_json_path.exists():
        errors.append("Missing ingestion_summary.json file.")
    else:
        try:
            with open(summary_json_path, 'r', encoding='utf-8') as f:
                summary = json.load(f)
                
            required_summary_keys = {
                "number_of_artists", "number_by_category", "profile_count", 
                "image_count", "audio_count", "video_count", 
                "duplicate_count", "unreadable_count", "anomaly_count", 
                "extension_mismatch_count"
            }
            missing_summary_keys = required_summary_keys - set(summary.keys())
            if missing_summary_keys:
                errors.append(f"ingestion_summary.json is missing keys: {missing_summary_keys}")
                
            # Basic value type checks
            for k in required_summary_keys:
                if k in summary:
                    if k == "number_by_category":
                        if not isinstance(summary[k], dict):
                            errors.append(f"Summary key 'number_by_category' must be a dict.")
                    else:
                        if not isinstance(summary[k], int):
                            errors.append(f"Summary key '{k}' must be an integer.")
                            
        except json.JSONDecodeError as e:
            errors.append(f"Failed to parse ingestion_summary.json as valid JSON: {str(e)}")
        except Exception as e:
            errors.append(f"Error reading ingestion_summary.json: {str(e)}")
            
    return len(errors) == 0, errors
