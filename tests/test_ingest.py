import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch
import docx
from PIL import Image

from src.config import Config
from src.ingest import run_ingestion

class TestIngest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        
        # Setup mock Sekeron structure
        self.profiles_dir = self.temp_path / "artist_profiles"
        self.photographers_dir = self.profiles_dir / "photographers"
        self.video_editors_dir = self.profiles_dir / "video_editors"
        
        self.photographers_dir.mkdir(parents=True)
        self.video_editors_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def create_mock_docx(self, parent_dir: Path, filename: str, lines: list):
        doc = docx.Document()
        for line in lines:
            doc.add_paragraph(line)
        doc.save(str(parent_dir / filename))

    def create_mock_image(self, parent_dir: Path, filename: str):
        img_path = parent_dir / filename
        img_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new('RGB', (10, 10), color='red')
        img.save(str(img_path), format='JPEG')

    @patch('src.media.run_ffprobe')
    def test_run_ingestion_basic(self, mock_ffprobe):
        # Stub ffprobe response for video files
        mock_ffprobe.return_value = {
            "format": {"duration": "10.0", "format_name": "mov,mp4,m4a"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 720, "height": 1280},
                {"codec_type": "audio", "codec_name": "aac", "channels": 2}
            ]
        }
        
        # 1. Create Artist 1: P01_Aanya_Rao (Photographer, standard layout)
        artist_1_dir = self.photographers_dir / "P01_Aanya_Rao"
        artist_1_dir.mkdir()
        self.create_mock_docx(artist_1_dir, "profile.docx", [
            "P01 / Aanya Rao",
            "Category: Photographer Location: Delhi NCR",
            "Bio: Event and café photography snaps."
        ])
        self.create_mock_image(artist_1_dir / "media", "photo1.jpg")
        
        # 2. Create Artist 2: VO4_Shivam_media (Video Editor, anomalous Work/ folder and missing profile portfolio claim)
        artist_2_dir = self.video_editors_dir / "VO4_Shivam_media"
        artist_2_dir.mkdir()
        self.create_mock_docx(artist_2_dir, "Shivam_Artist_Profile.docx", [
            "V04 / Shivam",
            "Category: Visual Artist Location: Delhi",
            "Bio: Cinematic videographer.",
            "Portfolio: Not provided in the profile."
        ])
        # Create a mock video file under Work/
        video_path = artist_2_dir / "Work" / "reel.mp4"
        video_path.parent.mkdir(exist_ok=True)
        with open(video_path, 'wb') as f:
            f.write(b"mock mp4 data")
            
        # Run ingestion
        config = Config.create(self.temp_dir)
        artists, media, claims, issues = run_ingestion(config)
        
        # Verify discoveries
        self.assertEqual(len(artists), 2)
        artist_keys = [a.artist_key for a in artists]
        self.assertIn("artist_profiles/photographers/P01_Aanya_Rao", artist_keys)
        self.assertIn("artist_profiles/video_editors/VO4_Shivam_media", artist_keys)
        
        # Check standard key generation
        a1 = next(a for a in artists if "P01_Aanya_Rao" in a.artist_key)
        self.assertEqual(a1.display_name, "Aanya Rao")
        self.assertEqual(a1.category, "photographer")
        
        # Check Shivam anomalies (unusual folder layout Work/ instead of media/)
        a2 = next(a for a in artists if "VO4_Shivam_media" in a.artist_key)
        self.assertIn("unusual_directory_layout", a2.identity_anomalies)
        
        # Check total processed assets
        self.assertEqual(len(media), 2)
        
        # Check if issues contain unusual layout warning
        issue_types = [i.issue_type for i in issues]
        self.assertIn("unusual_directory_layout", issue_types)

    def test_duplicate_claimed_ids(self):
        # Create two artists that claim the same profile ID (ID collision)
        # Artist A
        artist_a_dir = self.video_editors_dir / "V03_Rahul_Gupta"
        artist_a_dir.mkdir()
        self.create_mock_docx(artist_a_dir, "profile.docx", [
            "V03 / Tara D'Souza",
            "Category: Video Editor Location: Mumbai"
        ])
        
        # Artist B
        artist_b_dir = self.video_editors_dir / "VO5_Roshan"
        artist_b_dir.mkdir()
        self.create_mock_docx(artist_b_dir, "Roshan_Artist_Profile.docx", [
            "V03 / Roshan",
            "Category: Video Creator Location: Delhi NCR"
        ])
        
        config = Config.create(self.temp_dir)
        artists, media, claims, issues = run_ingestion(config)
        
        # Check duplicate profile ID anomaly triggered
        issue_types = [i.issue_type for i in issues]
        self.assertIn("duplicate_profile_id", issue_types)
        
        # Check both artists have the duplicate_profile_id tag in anomalies
        for a in artists:
            self.assertIn("duplicate_profile_id", a.identity_anomalies)

if __name__ == "__main__":
    unittest.main()
