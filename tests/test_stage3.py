import json
import os
import tempfile
import unittest
from pathlib import Path

from src.hirer import parse_hirer_briefs, parse_follow_up_update
from src.intelligence import build_artist_intelligence
from src.recommend import (
    generate_recommendations,
    generate_updated_recommendations,
    _score_artist_against_brief,
    reset_scoring_config,
)

# ---------------------------------------------------------------------------
# Dataset location is resolved dynamically so the suite runs on any machine.
# Resolution order:
#   1. $SEKERON_DATASET environment variable (explicit override)
#   2. <repo-parent>/Sekeron/Data set (standard layout next to the repo)
# The test asserts a clear error if the dataset cannot be located.
# ---------------------------------------------------------------------------
def _dataset_root() -> Path:
    env = os.environ.get("SEKERON_DATASET")
    if env:
        return Path(env)
    candidate = Path(__file__).resolve().parents[2] / "Sekeron" / "Data set"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(
        "Stage 3 dataset not found. Set SEKERON_DATASET=/path/to/'Data set' "
        "or place the repository next to the 'Sekeron/Data set' directory."
    )


DATASET = _dataset_root()
OUTPUTS = Path(__file__).resolve().parents[1] / "outputs"


class TestStage3Outputs(unittest.TestCase):
    def setUp(self):
        # Ensure scoring uses defaults (or the shipped scoring.yaml) consistently
        reset_scoring_config()

    def test_four_briefs_and_structured_intent(self):
        briefs = parse_hirer_briefs(DATASET)
        self.assertEqual(len(briefs), 4)
        for brief in briefs:
            for key in ('brief_id', 'explicit_constraints', 'reasonable_assumptions',
                        'contradictions', 'important_unknowns',
                        'required_capabilities', 'preferred_capabilities', 'disqualifiers'):
                self.assertIn(key, brief)
        cafe = next(b for b in briefs if b['brief_id'].startswith('01_cafe_music'))
        self.assertIn('acoustic_music', cafe['required_capabilities'])
        self.assertTrue(cafe['contradictions'])
        self.assertTrue(cafe['important_unknowns'])

    def test_constraint_extraction_no_noise(self):
        briefs = parse_hirer_briefs(DATASET)
        cafe = next(b for b in briefs if b['brief_id'].startswith('01_cafe_music'))
        # Timestamp-derived duplicate dates must not appear
        self.assertEqual(sum(1 for c in cafe['explicit_constraints'] if c.startswith('Date:')), 0)
        # No false budget of "11"
        self.assertNotIn('Budget: 11', cafe['explicit_constraints'])
        skincare = next(b for b in briefs if b['brief_id'].startswith('02_skincare'))
        self.assertNotIn('Budget: 11', skincare['explicit_constraints'])
        self.assertTrue(any('18k' in c for c in skincare['explicit_constraints']))
        # No mis-parsed times from "3-4 customer reactions"
        video = next(b for b in briefs if b['brief_id'].startswith('03_vertical_video'))
        self.assertFalse(any('Time: 3-4' in c for c in video['explicit_constraints']))
        # Leadership must NOT inherit the massive-stage disqualifier
        leadership = next(b for b in briefs if b['brief_id'].startswith('04_leadership'))
        self.assertNotIn('Massive setups or large stage requirements', leadership['disqualifiers'])
        self.assertIn('Stiff traditional conference style photography', leadership['disqualifiers'])

    def test_intelligence_is_valid_unique_jsonl(self):
        path = build_artist_intelligence(OUTPUTS)
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(len(records), 15)
        self.assertEqual(len({r['artist_key'] for r in records}), 15)
        for record in records:
            self.assertTrue(record['capabilities'])
            self.assertIn('unknowns', record)
            for cap in record['capabilities']:
                self.assertIn(cap['status'], ('DEMONSTRATED', 'CLAIMED_ONLY', 'UNKNOWN'))
                self.assertIn(cap['confidence'], ('HIGH', 'MEDIUM', 'LOW'))

    def test_demonstrated_beats_claim_and_unknown_is_not_false(self):
        brief = {'required_capabilities': ['acoustic_music'], 'preferred_capabilities': [],
                 'explicit_constraints': [], 'disqualifiers': []}
        demonstrated = {'capabilities': [{'capability': 'acoustic_music', 'status': 'DEMONSTRATED',
                                          'confidence': 'LOW', 'limitations': []}],
                        'supporting_claims_summary': []}
        claimed = {'capabilities': [{'capability': 'acoustic_music', 'status': 'CLAIMED_ONLY',
                                     'confidence': 'MEDIUM', 'limitations': []}],
                   'supporting_claims_summary': []}
        unknown = {'capabilities': [{'capability': 'acoustic_music', 'status': 'UNKNOWN',
                                     'confidence': 'LOW', 'limitations': []}],
                   'supporting_claims_summary': []}
        self.assertGreater(_score_artist_against_brief(demonstrated, brief)['score'],
                           _score_artist_against_brief(claimed, brief)['score'])
        self.assertLess(_score_artist_against_brief(unknown, brief)['score'], 0)

    def test_location_bonus_cannot_overturn_capability_gap(self):
        # Regression for the audit finding: Aanya (UNKNOWN product) must NOT rank
        # above Frames (CLAIMED product) merely because of a location bonus.
        brief = {'required_capabilities': ['product_photography'], 'preferred_capabilities': [],
                 'explicit_constraints': ['Gurgaon ideal, Delhi acceptable'],
                 'disqualifiers': []}
        unknown_with_location = {
            'capabilities': [{'capability': 'product_photography', 'status': 'UNKNOWN',
                              'confidence': 'LOW', 'limitations': []}],
            'supporting_claims_summary': ['Delhi / NCR'],
        }
        claimed_no_location = {
            'capabilities': [{'capability': 'product_photography', 'status': 'CLAIMED_ONLY',
                              'confidence': 'MEDIUM', 'limitations': []}],
            'supporting_claims_summary': ['Kolkata'],
        }
        unknown_score = _score_artist_against_brief(unknown_with_location, brief)['score']
        claimed_score = _score_artist_against_brief(claimed_no_location, brief)['score']
        self.assertGreater(claimed_score, unknown_score)

    def test_recommendations_and_questions(self):
        path = generate_recommendations(OUTPUTS, DATASET)
        data = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(len(data['recommendations']), 4)
        for brief in data['recommendations']:
            self.assertEqual(len(brief['top_recommendations']), 2)
            self.assertLessEqual(len(brief['improve_your_matches']), 2)
            for question in brief['improve_your_matches']:
                self.assertTrue(question['missing_info'])
                self.assertTrue(question['why_it_matters'])
                self.assertTrue(question['ranking_impact'])
                for rec in brief['top_recommendations']:
                    self.assertTrue(rec['match_reasons'] or rec['uncertainties'])

    def test_assumptions_populated_from_brief(self):
        path = generate_recommendations(OUTPUTS, DATASET)
        data = json.loads(path.read_text(encoding='utf-8'))
        for brief in data['recommendations']:
            for rec in brief['top_recommendations']:
                self.assertTrue(rec['assumptions'],
                                f"assumptions empty for {brief['brief_id']} {rec['display_name']}")

    def test_no_generic_label_capability_inflation(self):
        # A generic "Photographer" category label must not produce event_photography.
        # Verify the evidence logic directly against ingestion claims, so the test
        # does not depend on a stale regenerated evidence.json.
        from src.evidence import compile_evidence_layer
        with open(OUTPUTS / 'ingestion.json', 'r', encoding='utf-8') as f:
            ingestion = json.load(f)
        _, _, assessments, _ = compile_evidence_layer(ingestion)

        def status_for(artist_key, capability):
            for a in assessments:
                if a.artist_key == artist_key and a.capability == capability:
                    return a.status
            return None

        # Kabir's bio is product/food/fashion/portrait — no event claim.
        self.assertEqual(
            status_for('artist_profiles/photographers/P02_Kabir_Mehta', 'event_photography'),
            'UNKNOWN'
        )
        # Aanya genuinely mentions events in her bio, so she keeps a claim.
        self.assertEqual(
            status_for('artist_profiles/photographers/P01_Aanya_Rao', 'event_photography'),
            'CLAIMED_ONLY'
        )

    def test_follow_up_parsing_and_reranking(self):
        update = parse_follow_up_update(DATASET)
        self.assertEqual(update['affected_brief_family'], '01_cafe_music')
        self.assertTrue(update['updates'])
        path = generate_updated_recommendations(OUTPUTS, DATASET)
        data = json.loads(path.read_text(encoding='utf-8'))
        self.assertIn('01_cafe_music_whatsapp', data['metadata']['changed_briefs'])
        changed = next(r for r in data['recommendations'] if r.get('follow_up_applied'))
        self.assertTrue(changed['previous_ranking'])
        self.assertTrue(changed['updated_ranking'])
        self.assertTrue(changed['changes_detected']['changed_constraints'])

    def test_follow_up_stability_explanation(self):
        path = generate_updated_recommendations(OUTPUTS, DATASET)
        data = json.loads(path.read_text(encoding='utf-8'))
        changed = next(r for r in data['recommendations'] if r.get('follow_up_applied'))
        if changed['previous_ranking'] == changed['updated_ranking']:
            text = changed['ranking_change_explanation']
            for phrase in ('changed', 're-scored', 'remained stable', 'unavailable'):
                self.assertIn(phrase, text)
            self.assertIn('rate', text)


if __name__ == '__main__':
    unittest.main()
