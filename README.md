# Sekeron Artist Intelligence Ingestion Pipeline (Phase 1)

This project contains the Phase 1 Ingestion Pipeline for the Sekeron Stage 3 Practical Assessment: **Artist Intelligence & Recommendation Challenge**.

The system parses unstructured artist profiles, walks portfolio directories recursively to extract media metadata, runs duplicate asset hash checks, and flags structural and data-quality anomalies deterministically.

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
│   ├── output.py       # JSON database serializer
│   └── validate.py     # Output schema validator
│
├── config/
│   └── scoring.yaml    # Downstream score configurations (Placeholder)
│
├── outputs/            # Ingestion output database dumps
│
├── tests/              # Ingestion unit tests using mock fixtures
│   ├── test_ingest.py
│   ├── test_profiles.py
│   ├── test_media.py
│   └── test_validation.py
│
├── run.py              # CLI entry point script
├── requirements.txt    # Pinned dependencies
├── README.md           # Main documentation
├── decision_note.md    # Architecture and scope notes (Placeholder)
└── AI_USAGE.md         # AI disclosure log
```

---

## 2. Ingestion CLI Usage

The ingestion CLI runs without hardcoded absolute paths:

```bash
python3 run.py ingest --dataset /path/to/dataset_root
```

* **Example (Standard Workstation)**:
  ```bash
  python3 run.py ingest --dataset "/media/projects/playground/Sekeron/Data set"
  ```

Outputs are written to:
* `sekeron/outputs/ingestion.json`
* `sekeron/outputs/ingestion_summary.json`

---

## 3. Core Design Principles

1. **Deterministic Ingestion**: Canonical artist keys are derived from normalized relative directory paths (e.g. `artist_profiles/photographers/P01_Aanya_Rao`) to prevent ID collisions. Internal profile-claimed IDs are stored strictly as metadata.
2. **Content-Based MIME Verification**: Media file types are detected using file headers (via `Pillow` and `ffprobe` streams) rather than relying on filename extensions. Mismatches generate `extension_mismatch` data quality warnings.
3. **Graceful Error Handling**: Individual corrupt or unreadable files create quality warnings but do not fail the overall scanner.
4. **Authenticity Checking**: Duplicate assets are tracked via SHA-256 hashes, setting the `duplicate_of` field to trace provenance.
