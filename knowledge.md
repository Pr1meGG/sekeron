# Sekeron — Engineering Constitution

This file is the permanent engineering constitution for the Sekeron project. All code changes and design decisions must conform to it.

---

## Project

**Sekeron Applied AI Internship Practical Assessment**

## Mission

Build an **evidence-first Artist Intelligence and Recommendation pipeline**.

## Current Dataset

- Approximately 1 GB.
- 15 artists:
  - 5 photographers
  - 5 musicians
  - 5 video editors

---

## Architecture

### Phase 1: Ingestion

- **Input:** raw artist dataset
- **Output:**
  - `outputs/ingestion.json`
  - `outputs/ingestion_summary.json`

**Responsibilities:**
- Discover artists
- Canonical filesystem identity
- Parse `profile.docx`
- Discover media
- Content-based MIME detection
- Technical metadata
- SHA-256 hashing
- Duplicate detection
- Anomalies
- Provenance

### Phase 2: Evidence Intelligence

- **Input:** `outputs/ingestion.json`
- **Output:** `outputs/evidence.json`

Two distinct evidence layers:

1. **TechnicalObservation** — Objective technical facts only.
2. **ContentObservation** — Semantic/content-level observations.

---

## Evidence Integrity Rules (IMPORTANT)

Technical metadata MUST NOT be treated as semantic evidence.

Examples:
- JPEG resolution does not prove portrait photography.
- MP4 resolution does not prove video editing.
- Codec does not prove artistic capability.
- EXIF does not prove subject matter.

### Capability States

Every capability assessment must use exactly one of:

- `DEMONSTRATED`
- `CLAIMED_ONLY`
- `UNKNOWN`

**Never** use `FALSE` for missing evidence.

Definitions:
- **Profile claim:** The artist says they can do something.
- **Demonstrated capability:** Actual supplied evidence supports the capability.
- **Unknown:** Insufficient evidence.

### Filename / Context Cues

- Allowed only as **weak semantic cues**.
- `source_type`: `filename_context`
- Filename/context alone must NEVER produce HIGH confidence.
- Filename/context must NOT become definitive content evidence.
- Direct content evidence may produce stronger confidence.

### Confidence

Confidence is categorical only:

- `HIGH`
- `MEDIUM`
- `LOW`

Do NOT invent numerical probabilities.

### Stock Media

Stock media is a provenance limitation. Use:

- `LIMITED_BY_PROVENANCE`

Never infer that the artist lacks the capability.

Synthetic assessment metadata is also a provenance limitation:

- `SYNTHETIC_SAMPLE`

It does not prove the artist is fake or incapable.

### Duplicates

Identical SHA-256 content is **one** independent evidence item.

Do not double-weight duplicate content.

---

## Dataset-Specific Logic: FORBIDDEN

Never hardcode:

- artist IDs
- artist names
- specific filenames
- specific capability outcomes
- dataset-specific lookup tables

The pipeline must generalize to another dataset.

---

## Current Phase

Phase 2 must be fully audited before Phase 3.

Future roadmap (do NOT implement early):

- **Phase 3:** hirer intent
- **Phase 4:** matching/ranking
- **Phase 5:** reranking/follow-up

Do not implement future phases early.

---

## Compute Policy

The local machine is an orchestration/development environment.

### Locally ALLOWED

- `ls` / `find`
- `git`
- `grep` / `ripgrep`
- JSON parsing
- Schema validation
- Unit tests
- Lightweight Python
- Targeted metadata inspection
- Targeted `ffprobe`
- Small fixtures
- Source code analysis

### Locally FORBIDDEN for large data

- Batch ffmpeg frame extraction
- OpenCV processing over the dataset
- Whisper/transcription over all media
- Image embeddings over all media
- Video embeddings
- Large VLM inference
- Batch OCR
- Large audio feature extraction
- Model training
- GPU workloads
- Repeatedly scanning the 1 GB dataset unnecessarily

---

## Heavy Media Analysis: Designed for Kaggle

Heavy media analysis MUST be designed for Kaggle, following this workflow:

1. Design the job locally.
2. Create a reproducible Kaggle notebook/script.
3. Run the expensive processing in Kaggle.
4. Export structured JSON/Parquet results.
5. Bring only the results back into this repository.
6. Integrate the results locally.

Do not silently perform expensive computation locally.

---

## Operating Mode

Before changing code:

1. Inspect the existing implementation.
2. Identify the smallest relevant files.
3. Explain the intended change.
4. Implement narrowly.
5. Run relevant tests.
6. Report what changed.

Additional rules:

- Never silently redesign the architecture.
- When uncertain: STOP and report the ambiguity.
- Never claim content understanding that the available evidence cannot support.

**This project values evidence integrity over inflated capability counts.**
