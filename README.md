# Sekeron Stage 3 — Artist Intelligence & Recommendation Pipeline

Evidence-led system building per-artist capability intelligence from profile claims
and portfolio media, producing explainable recommendations for sparse hirer briefs,
and re-ranking on updated requirements. Deterministic — no LLM or heavy inference.

## Setup & CLI

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt  # python-docx==1.2.0, Pillow==9.0.1, PyYAML==5.4.1

# Run full pipeline or individual stages (--dataset must precede subcommand):
python3 run.py --dataset "/path/to/Sekeron/Data set" full
python3 run.py --dataset "/path/to/Sekeron/Data set" ingest        # outputs/ingestion.json
python3 run.py --dataset "/path/to/Sekeron/Data set" evidence       # outputs/evidence.json
python3 run.py --dataset "/path/to/Sekeron/Data set" intelligence   # outputs/artist_intelligence.jsonl
python3 run.py --dataset "/path/to/Sekeron/Data set" recommend      # outputs/recommendations.json
python3 run.py --dataset "/path/to/Sekeron/Data set" update         # outputs/updated_recommendation.json
python3 run.py --dataset "/path/to/Sekeron/Data set" validate       # validates outputs
```

## Workflow

1. **Ingestion** — parses `.docx` profiles, extracts MIME/metadata via Pillow+ffprobe, hashes assets (SHA-256) for duplicate detection, flags quality anomalies.
2. **Evidence** — compiles technical/content observations (filename cues capped at MEDIUM confidence, EXIF) and assessments (`DEMONSTRATED`, `CLAIMED_ONLY`, `UNKNOWN`); stock media never counts as demonstrated.
3. **Intelligence** — emits `artist_intelligence.jsonl` (capabilities, evidence, claims, unknowns, confidence).
4. **Recommendations** — parses 4 briefs into structured intent, scores candidates (demonstrated > claimed > unknown; location breaks close ties only), returns top-2 per brief with trade-offs, assumptions, uncertainty, and ≤2 questions.
5. **Follow-up Update** — parses update, re-scores affected brief, outputs revised/stable ranking with explicit change explanation.

## Required Outputs

| Output File | Content |
|---|---|
| `outputs/artist_intelligence.jsonl` | One record/artist: capabilities, evidence, claims, unknowns, confidence |
| `outputs/recommendations.json` | Top-2 per brief, reasons, trade-offs, assumptions, uncertainty, ≤2 questions |
| `outputs/updated_recommendation.json` | Revised/stable ranking after follow-up, with change explanation |

All outputs are generated exclusively by the pipeline — never hand-edited.

## Media Selection & Kaggle Decision

Metadata extraction (image EXIF, audio/video stream info) is lightweight and sufficient. No frame decoding, speech transcription, or VLM analysis is performed, so **no Kaggle offload is required**. See `MEDIA_SELECTION_POLICY.md`.

## Timebox & Effort (Rule 22)

Timeboxed to 6 hours maximum. Active work (~6 hours total) spanned 24–28 Aug 2026, reconstructed from commit/file timestamps. Prioritised evidence integrity, deterministic ranking, and pipeline architecture over unnecessary model complexity or Kaggle integration.

## Model & Processing Rationale (Rule 23)

Dataset processing relies on parsing, metadata, provenance, and deterministic rules. This ensures reproducible, explainable rankings without overstating capability. LLM/VLM/embeddings would only be warranted if semantic interpretation beyond available evidence were required.

## Paid API Usage (Rule 24)

No paid API was used; total spend was ₹0.

## Tests & Documentation

```bash
python3 -m unittest discover -s tests -v
```
Covers ingestion, evidence rules, brief parsing, intelligence JSONL, ranking logic, and follow-up updates (`SEKERON_DATASET` env override supported).
Docs: `decision_note.md` (scope/dimensions), `AI_USAGE.md` (AI disclosure), `MEDIA_SELECTION_POLICY.md`.
