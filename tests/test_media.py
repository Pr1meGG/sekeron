import unittest
import tempfile
import shutil
from pathlib import Path
from PIL import Image

from src.media import calculate_sha256, detect_mime_type_from_content, process_media_file

class TestMedia(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_calculate_sha256(self):
        # Write simple text file
        test_file = self.temp_path / "test.txt"
        with open(test_file, 'w') as f:
            f.write("sekeron")
            
        expected_hash = "95693653f9173dbd97b542f7ba6fbfc23322283ac1ce5c110ea2970e35a39be1"
        self.assertEqual(calculate_sha256(test_file), expected_hash)

    def test_content_based_mime_image(self):
        # Create a mock JPEG image
        img_path = self.temp_path / "mock.jpg"
        img = Image.new('RGB', (50, 50), color='blue')
        img.save(str(img_path), format='JPEG')
        
        mime = detect_mime_type_from_content(img_path)
        self.assertEqual(mime, "image/jpeg")

    def test_extension_mismatch_detection(self):
        # Create a JPEG image but save it with a .png suffix
        mismatch_path = self.temp_path / "mismatch.png"
        img = Image.new('RGB', (50, 50), color='green')
        img.save(str(mismatch_path), format='JPEG')
        
        asset, issues = process_media_file(mismatch_path, "photographers/PO4_Drift")
        
        self.assertEqual(asset.declared_extension, ".png")
        self.assertEqual(asset.detected_mime, "image/jpeg")
        self.assertIn("extension_mismatch", asset.anomalies)
        
        issue_types = [i.issue_type for i in issues]
        self.assertIn("extension_mismatch", issue_types)

    def test_empty_file_anomaly(self):
        # Create an empty file
        empty_path = self.temp_path / "empty.jpg"
        with open(empty_path, 'wb') as f:
            pass
            
        asset, issues = process_media_file(empty_path, "photographers/P01_Aanya_Rao")
        self.assertIn("empty_file", asset.anomalies)
        
        issue_types = [i.issue_type for i in issues]
        self.assertIn("empty_file", issue_types)

if __name__ == "__main__":
    unittest.main()
