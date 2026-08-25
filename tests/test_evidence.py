import unittest
from src.evidence import compile_evidence_layer, is_stock_media

class TestEvidence(unittest.TestCase):

    def setUp(self):
        # Create a mock ingestion database structure
        self.mock_ingestion = {
            "artists": [
                {
                    "artist_key": "artist_profiles/photographers/P01_Aanya_Rao",
                    "folder_path": "/path/to/P01_Aanya_Rao",
                    "display_name": "Aanya Rao",
                    "category": "photographer",
                    "profile_files": ["profile.docx"],
                    "media_files": ["photo.jpg"],
                    "profile_ids": ["P01"],
                    "identity_anomalies": []
                },
                {
                    "artist_key": "artist_profiles/musicians/M02_Neon_Junction",
                    "folder_path": "/path/to/M02_Neon_Junction",
                    "display_name": "Neon Junction",
                    "category": "musician",
                    "profile_files": ["profile.docx"],
                    "media_files": ["stock.mp3"],
                    "profile_ids": ["M02"],
                    "identity_anomalies": []
                }
            ],
            "media": [
                # Normal image file (P01)
                {
                    "asset_key": "photo.jpg",
                    "artist_key": "artist_profiles/photographers/P01_Aanya_Rao",
                    "path": "/path/to/P01/photo.jpg",
                    "filename": "photo.jpg",
                    "declared_extension": ".jpg",
                    "detected_mime": "image/jpeg",
                    "media_type": "image",
                    "size_bytes": 1024,
                    "sha256": "hash_123",
                    "metadata": {
                        "width": 1920,
                        "height": 1080
                    },
                    "readable": True,
                    "duplicate_of": None,
                    "anomalies": []
                },
                # Duplicate image file (P01) - same SHA-256
                {
                    "asset_key": "photo_copy.jpg",
                    "artist_key": "artist_profiles/photographers/P01_Aanya_Rao",
                    "path": "/path/to/P01/photo_copy.jpg",
                    "filename": "photo_copy.jpg",
                    "declared_extension": ".jpg",
                    "detected_mime": "image/jpeg",
                    "media_type": "image",
                    "size_bytes": 1024,
                    "sha256": "hash_123", # Duplicate hash
                    "metadata": {
                        "width": 1920,
                        "height": 1080
                    },
                    "readable": True,
                    "duplicate_of": "/path/to/P01/photo.jpg",
                    "anomalies": ["duplicate_media"]
                },
                # Stock media track (M02)
                {
                    "asset_key": "ahsleysnow-feel-like-home-523056.mp3",
                    "artist_key": "artist_profiles/musicians/M02_Neon_Junction",
                    "path": "/path/to/M02/ahsleysnow-feel-like-home-523056.mp3",
                    "filename": "ahsleysnow-feel-like-home-523056.mp3",
                    "declared_extension": ".mp3",
                    "detected_mime": "audio/mpeg",
                    "media_type": "audio",
                    "size_bytes": 2048,
                    "sha256": "hash_stock",
                    "metadata": {},
                    "readable": True,
                    "duplicate_of": None,
                    "anomalies": []
                },
                # Synthetic comment WAV file (M02)
                {
                    "asset_key": "synth.wav",
                    "artist_key": "artist_profiles/musicians/M02_Neon_Junction",
                    "path": "/path/to/M02/synth.wav",
                    "filename": "synth.wav",
                    "declared_extension": ".wav",
                    "detected_mime": "audio/wav",
                    "media_type": "audio",
                    "size_bytes": 4096,
                    "sha256": "hash_synth",
                    "metadata": {
                        "tags": {
                            "comment": "Synthetic assessment sample"
                        }
                    },
                    "readable": True,
                    "duplicate_of": None,
                    "anomalies": []
                },
                # Mismatch file extension (P01)
                {
                    "asset_key": "mismatch.png",
                    "artist_key": "artist_profiles/photographers/P01_Aanya_Rao",
                    "path": "/path/to/P01/mismatch.png",
                    "filename": "mismatch.png",
                    "declared_extension": ".png",
                    "detected_mime": "image/jpeg", # anomalous MIME but technically valid image
                    "media_type": "image",
                    "size_bytes": 500,
                    "sha256": "hash_mismatch",
                    "metadata": {
                        "width": 100,
                        "height": 100
                    },
                    "readable": True,
                    "duplicate_of": None,
                    "anomalies": ["extension_mismatch"]
                }
            ],
            "profile_claims": [
                # Claimed capabilities
                {
                    "artist_key": "artist_profiles/photographers/P01_Aanya_Rao",
                    "claim": "candid event photography",
                    "source_file": "profile.docx",
                    "section_or_locator": "Bio",
                    "claim_type": "experience",
                    "confidence": 1.0,
                    "notes": ""
                },
                {
                    "artist_key": "artist_profiles/musicians/M02_Neon_Junction",
                    "claim": "electronic music producer",
                    "source_file": "profile.docx",
                    "section_or_locator": "Bio",
                    "claim_type": "experience",
                    "confidence": 1.0,
                    "notes": ""
                }
            ],
            "quality_issues": [
                {
                    "severity": "WARNING",
                    "issue_type": "duplicate_media",
                    "artist_key": "artist_profiles/photographers/P01_Aanya_Rao",
                    "asset_key": "photo_copy.jpg",
                    "description": "Duplicate media file.",
                    "evidence": ""
                }
            ]
        }

    def test_technical_metadata_does_not_create_semantic_capability(self):
        # Even though photo.jpg has 1920x1080 resolution technical metadata,
        # it does not have a filename or EXIF content cue for 'portrait_photography'.
        # Therefore, 'portrait_photography' should not be DEMONSTRATED.
        tech_obs, content_obs, assessments, _ = compile_evidence_layer(self.mock_ingestion)
        
        # Check that photo.jpg has a technical observation
        t_obs = next(t for t in tech_obs if t.asset_key == "photo.jpg")
        self.assertEqual(t_obs.metadata["width"], 1920)
        
        # Check portrait_photography capability assessment for P01 is not DEMONSTRATED
        portrait_assessment = next(a for a in assessments if a.artist_key == "artist_profiles/photographers/P01_Aanya_Rao" and a.capability == "portrait_photography")
        self.assertNotEqual(portrait_assessment.status, "DEMONSTRATED")

    def test_profile_claim_without_content_evidence_is_claimed_only(self):
        # P01 claims 'event_photography' but the supplied file 'photo.jpg' has no semantic filename cue for events.
        # Thus, 'event_photography' should be CLAIMED_ONLY.
        _, _, assessments, _ = compile_evidence_layer(self.mock_ingestion)
        
        event_assessment = next(a for a in assessments if a.artist_key == "artist_profiles/photographers/P01_Aanya_Rao" and a.capability == "event_photography")
        self.assertEqual(event_assessment.status, "CLAIMED_ONLY")
        self.assertEqual(event_assessment.confidence, "MEDIUM")

    def test_stock_media_triggers_provenance_limitation_and_claimed_only(self):
        # M02 claims 'electronic_music' but only supplies a stock track 'ahsleysnow-feel-like-home-523056.mp3'.
        # This must flag LIMITED_BY_PROVENANCE and degrade the assessment to CLAIMED_ONLY.
        _, _, assessments, _ = compile_evidence_layer(self.mock_ingestion)
        
        elec_assessment = next(a for a in assessments if a.artist_key == "artist_profiles/musicians/M02_Neon_Junction" and a.capability == "electronic_music")
        self.assertIn("LIMITED_BY_PROVENANCE", elec_assessment.limitations)
        self.assertEqual(elec_assessment.status, "CLAIMED_ONLY")
        # Stock limits confidence to LOW
        self.assertEqual(elec_assessment.confidence, "LOW")

    def test_synthetic_comment_metadata_triggers_synthetic_sample_limitation(self):
        # synth.wav has 'Synthetic assessment sample' in its tags.
        # This should append SYNTHETIC_SAMPLE to M02 assessments.
        _, _, assessments, _ = compile_evidence_layer(self.mock_ingestion)
        
        for assess in assessments:
            if assess.artist_key == "artist_profiles/musicians/M02_Neon_Junction":
                self.assertIn("SYNTHETIC_SAMPLE", assess.limitations)

    def test_duplicate_content_does_not_double_evidence_count(self):
        # photo.jpg and photo_copy.jpg have the same hash.
        # One is duplicate_of the other.
        # In evidence compilation, only the original photo.jpg (non-duplicate) must be included.
        # If we map a capability to this asset (e.g. if we add nature_photography claim),
        # the supporting evidence count for it must be 1.
        self.mock_ingestion["profile_claims"].append({
            "artist_key": "artist_profiles/photographers/P01_Aanya_Rao",
            "claim": "nature snapshots",
            "source_file": "profile.docx",
            "section_or_locator": "Bio",
            "claim_type": "experience",
            "confidence": 1.0,
            "notes": ""
        })
        # Add filename keywords to trigger content observation for both
        self.mock_ingestion["media"][0]["filename"] = "sunflower_macro.jpg"
        self.mock_ingestion["media"][1]["filename"] = "sunflower_macro_copy.jpg"
        
        _, _, assessments, _ = compile_evidence_layer(self.mock_ingestion)
        
        nature_assessment = next(a for a in assessments if a.artist_key == "artist_profiles/photographers/P01_Aanya_Rao" and a.capability == "nature_photography")
        # Should be DEMONSTRATED with exactly 1 supporting asset (the duplicate is filtered out)
        self.assertEqual(nature_assessment.status, "DEMONSTRATED")
        self.assertEqual(len(nature_assessment.supporting_evidence), 1)

    def test_anomalous_extension_file_produces_valid_technical_observation(self):
        # mismatch.png has mime image/jpeg but declared .png.
        # It is still parsed as a valid TechnicalObservation.
        tech_obs, _, _, _ = compile_evidence_layer(self.mock_ingestion)
        
        m_obs = next(t for t in tech_obs if t.asset_key == "mismatch.png")
        self.assertTrue(m_obs.readable)
        self.assertIn("extension_mismatch", m_obs.anomalies)

    def test_missing_semantic_evidence_is_unknown(self):
        # M02 has no claims and no evidence for 'acoustic_music'.
        # Thus, its status for 'acoustic_music' must be UNKNOWN.
        _, _, assessments, _ = compile_evidence_layer(self.mock_ingestion)
        
        ac_assessment = next(a for a in assessments if a.artist_key == "artist_profiles/musicians/M02_Neon_Junction" and a.capability == "acoustic_music")
        self.assertEqual(ac_assessment.status, "UNKNOWN")

if __name__ == "__main__":
    unittest.main()
