# Sekeron Artist Intelligence & Recommendation Pipeline

This project implements the Sekeron Stage 3 Practical Assessment: **Artist Intelligence & Recommendation Challenge**.

The system parses unstructured artist profiles, walks portfolio directories recursively to extract media metadata, runs duplicate asset hash checks, and flags structural and data-quality anomalies deterministically. It then compiles evidence-based capability assessments for each artist.

---

## 1. Codebase Structure

```text
sekeron/
├── src/
│   ├── __init__.py
│   ├── config.py       # Configuration and CLI path validation
│   ├── models.py       # Data transfer objects / domain models
│   ├── ingest.py       # Main scanner and ingestion logic
│   ├── profiles.py     # Profile document (.docx) extractor
│   ├── media.py        # Content-based media metadata extractor
│   ├── evidence.py     # Phase 2 evidence intelligence layer
│   ├── output.py       # JSON database serializer
│   └── validate.py     # Output schema validator
│
├── config/
│   ├── scoring.yaml          # Downstream score configurations (Placeholder)
│   └── evidence_rules.yaml   # Dataset-agnostic evidence rules (stock, content cues)
│
├── outputs/            # Pipeline output database dumps
│
├── tests/              # Unit tests using mock fixtures
│   ├── test_ingest.py
│   ├── test_profiles.py
│   ├── test_media.py
│   ├── test_evidence.py
│   └── test_validation.py
│
├── run.py              # CLI entry point script
├── requirements.txt    # Pinned dependencies
├── README.md           # Main documentation
├── decision_note.md    # Architecture and scope notes
└── AI_USAGE.md         # AI disclosure log
```

---

## 2. CLI Usage

### Phase 1: Ingestion

```bash
python3 run.py ingest --dataset /path/to/dataset_root
```

Outputs:
* `outputs/ingestion.json`
* `outputs/ingestion_summary.json`

### Phase 2: Evidence Intelligence

```bash
python3 run.py evidence --dataset /path/to/dataset_root
```

Inputs: `outputs/ingestion.json`
Output: `outputs/evidence.json`

---

## 3. Core Design Principles

1. **Deterministic Ingestion**: Canonical artist keys are derived from normalized relative directory paths (e.g. `artist_profiles/photographers/P01_Aanya_Rao`) to prevent ID collisions. Internal profile-claimed IDs are stored strictly as metadata.
2. **Content-Based MIME Verification**: Media file types are detected using file headers (via `Pillow` and `ffprobe` streams) rather than relying on filename extensions. Mismatches generate `extension_mismatch` data quality warnings.
3. **Graceful Error Handling**: Individual corrupt or unreadable files create quality warnings but do not fail the overall scanner.
4. **Authenticity Checking**: Duplicate assets are tracked via SHA-256 hashes, setting the `duplicate_of` field to trace provenance.

---

## 4. Phase 2: Evidence Intelligence

The evidence layer compiles a two-layer evidence model from ingestion data:

1. **TechnicalObservation** — Objective file-level facts (resolution, codecs, MIME types). Technical metadata never automatically proves semantic capability.
2. **ContentObservation** — Semantic observations derived from trustworthy signals: filename cues and embedded EXIF metadata. Filename-based observations are capped at `MEDIUM` confidence.

### Capability Assessment

Each artist × capability combination is assessed into one of three states:
* `DEMONSTRATED` — supported by content evidence
* `CLAIMED_ONLY` — claimed in profile but not demonstrated
* `UNKNOWN` — neither claimed nor demonstrated

### Dataset-Agnostic Configuration

Evidence rules (stock-media detection, filename content cues) are externalised in `config/evidence_rules.yaml`. No artist names, filenames, or dataset-specific logic appears in Python source code. A new dataset requires editing only this YAML file.

### Limitations Tracked
* `LIMITED_BY_PROVENANCE` — stock/third-party media detected
* `SYNTHETIC_SAMPLE` — synthetic assessment metadata detected
* Identity anomalies (`ID_CONFLICT`, `NAME_MISMATCH`, `UNUSUAL_DIRECTORY_LAYOUT`) surfaced from ingestion
