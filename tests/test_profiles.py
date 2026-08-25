import unittest
import tempfile
import shutil
from pathlib import Path
import docx

from src.profiles import extract_claims_and_issues, extract_profile_details

class TestProfiles(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def create_mock_docx(self, filename: str, paragraphs: list) -> Path:
        doc_path = self.temp_path / filename
        doc = docx.Document()
        for p in paragraphs:
            doc.add_paragraph(p)
        doc.save(str(doc_path))
        return doc_path

    def test_extract_details_standard(self):
        text = (
            "P01 / Aanya Rao\n"
            "Category: Photographer Location: Delhi / NCR Work preference: Travel available\n"
            "Bio: Photographer working in events, cafés, and workshops.\n"
        )
        claimed_id, claimed_name, category, location, work_pref, bio = extract_profile_details(text, "P01_Aanya_Rao")
        self.assertEqual(claimed_id, "P01")
        self.assertEqual(claimed_name, "Aanya Rao")
        self.assertEqual(category, "Photographer")
        self.assertEqual(location, "Delhi / NCR")
        self.assertEqual(work_pref, "Travel available")
        self.assertEqual(bio, "Photographer working in events, cafés, and workshops.")

    def test_extract_details_missing_name(self):
        # Case Rehman Ali (missing name in profile)
        text = (
            "Category: Video Editor Location: Gurugram Work preference: Remote\n"
            "Bio: Video editor working on explainers.\n"
        )
        claimed_id, claimed_name, category, location, work_pref, bio = extract_profile_details(text, "V02_Rehman_Ali")
        self.assertIsNone(claimed_id)
        self.assertIsNone(claimed_name)
        self.assertEqual(category, "Video Editor")
        self.assertEqual(location, "Gurugram")
        self.assertEqual(work_pref, "Remote")
        self.assertEqual(bio, "Video editor working on explainers.")

    def test_mismatched_id_and_name_anomalies(self):
        # Create a mock docx with mismatched ID and Name (e.g. folder PO4_Drift vs claimed ID V05)
        doc_path = self.create_mock_docx("profile.docx", [
            "V05 / Drift",
            "Category: Photographer Location: Ghaziabad",
            "Bio: Natural photography snaps."
        ])
        
        claims, issues, details = extract_claims_and_issues(doc_path, "photographers/PO4_Drift", "PO4_Drift")
        
        # Check issues detected:
        issue_types = [i.issue_type for i in issues]
        self.assertIn("id_conflict", issue_types)
        
        # Another test for Name Mismatch (Rahul Gupta folder vs claimed Tara D'Souza name)
        doc_path_2 = self.create_mock_docx("profile_2.docx", [
            "V03 / Tara D'Souza",
            "Category: Video Editor Location: Mumbai",
            "Bio: Cinematic travel cuts."
        ])
        claims_2, issues_2, details_2 = extract_claims_and_issues(doc_path_2, "video_editors/V03_Rahul_Gupta", "V03_Rahul_Gupta")
        
        issue_types_2 = [i.issue_type for i in issues_2]
        self.assertIn("name_mismatch", issue_types_2)

    def test_missing_profile_name_warning(self):
        # Rehman Ali case
        doc_path = self.create_mock_docx("profile.docx", [
            "Category: Video Editor Location: Gurugram Work preference: Remote",
            "Bio: Explainer edits."
        ])
        claims, issues, details = extract_claims_and_issues(doc_path, "video_editors/V02_Rehman_Ali", "V02_Rehman_Ali")
        
        issue_types = [i.issue_type for i in issues]
        self.assertIn("missing_profile_name", issue_types)

if __name__ == "__main__":
    unittest.main()
