import unittest
import tempfile
import shutil
import json
from pathlib import Path

from src.validate import validate_ingestion_outputs

class TestValidation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def write_json(self, filename: str, data: dict):
        with open(self.temp_path / filename, 'w', encoding='utf-8') as f:
            json.dump(data, f)

    def test_validation_success(self):
        # Write valid ingestion.json
        self.write_json("ingestion.json", {
            "dataset": {
                "root_path": "/path/to/dataset",
                "total_artists": 2,
                "total_profile_files": 2,
                "total_media_files": 2,
                "ingestion_timestamp": "2026-08-24T16:00:00Z"
            },
            "artists": [],
            "media": [],
            "profile_claims": [],
            "quality_issues": []
        })
        
        # Write valid ingestion_summary.json
        self.write_json("ingestion_summary.json", {
            "number_of_artists": 2,
            "number_by_category": {"photographers": 1, "video_editors": 1},
            "profile_count": 2,
            "image_count": 1,
            "audio_count": 0,
            "video_count": 1,
            "duplicate_count": 0,
            "unreadable_count": 0,
            "anomaly_count": 0,
            "extension_mismatch_count": 0
        })
        
        is_valid, errors = validate_ingestion_outputs(self.temp_path)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

    def test_validation_missing_key(self):
        # missing quality_issues key in ingestion.json
        self.write_json("ingestion.json", {
            "dataset": {
                "root_path": "/path/to/dataset",
                "total_artists": 2,
                "total_profile_files": 2,
                "total_media_files": 2,
                "ingestion_timestamp": "2026-08-24T16:00:00Z"
            },
            "artists": [],
            "media": [],
            "profile_claims": []
        })
        
        self.write_json("ingestion_summary.json", {
            "number_of_artists": 2,
            "number_by_category": {"photographers": 1},
            "profile_count": 2,
            "image_count": 1,
            "audio_count": 0,
            "video_count": 1,
            "duplicate_count": 0,
            "unreadable_count": 0,
            "anomaly_count": 0,
            "extension_mismatch_count": 0
        })
        
        is_valid, errors = validate_ingestion_outputs(self.temp_path)
        self.assertFalse(is_valid)
        self.assertTrue(any("missing top-level keys" in err for err in errors))

    def test_validation_type_mismatch(self):
        self.write_json("ingestion.json", {
            "dataset": {
                "root_path": "/path/to/dataset",
                "total_artists": 2,
                "total_profile_files": 2,
                "total_media_files": 2,
                "ingestion_timestamp": "2026-08-24T16:00:00Z"
            },
            "artists": "not-a-list", # Type Mismatch
            "media": [],
            "profile_claims": [],
            "quality_issues": []
        })
        
        self.write_json("ingestion_summary.json", {
            "number_of_artists": 2,
            "number_by_category": {"photographers": 1},
            "profile_count": 2,
            "image_count": 1,
            "audio_count": 0,
            "video_count": 1,
            "duplicate_count": 0,
            "unreadable_count": 0,
            "anomaly_count": 0,
            "extension_mismatch_count": 0
        })
        
        is_valid, errors = validate_ingestion_outputs(self.temp_path)
        self.assertFalse(is_valid)
        self.assertTrue(any("must be a list" in err for err in errors))

if __name__ == "__main__":
    unittest.main()
