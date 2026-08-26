# Decision Note: Sekeron Artist Intelligence & Recommendation System

## Phase 1: Ingestion Pipeline
- Content-based MIME detection.
- Recursive dataset ingestion without hardcoded absolute paths.
- Extraction of raw Profile Claims and metadata.
- SHA-256 duplicate asset verification.
- Audit for data anomalies (claimed ID collisions, layout issues, unreadable files).

---

## Phase 2: Evidence Intelligence (Implemented)

The Phase 2 Evidence Intelligence layer has been successfully designed and implemented. It evaluates claims and observations separately, avoiding semantic leap assumptions.

### 1. Two-Layer Evidence Model
* **Technical Observation**: Objective physical characteristics of the file container (resolution, codecs, channels, metadata tags, EXIF parameters). Technical observations alone *never* automatically prove semantic capabilities (e.g. `4032x3024 JPEG` does not prove `portrait_photography`).
* **Content Observation**: Artistic content traits (subjects, genres, instrumentation) derived strictly from trustworthy semantic signals (explicit filename keywords, embedded metadata tags). The source type is preserved as `direct_content` or `filename_context` (which is capped at `MEDIUM` confidence).

### 2. Capability Assessment Statuses
Every capability for an artist is evaluated into one of three states:
* `DEMONSTRATED`: The artist profile claims it (or it is expected) AND there is clear, verified content evidence proving it (excluding stock files).
* `CLAIMED_ONLY`: The artist claims the capability, but no supplied evidence demonstrates it (or the evidence is stock/invalid).
* `UNKNOWN`: The capability is neither claimed in the profile nor demonstrated in the media portfolio.

### 3. Categorical Confidence Mappings
No arbitrary numerical confidence probabilities are used in the evidence layer. Confidence is mapped to:
* `HIGH`: High-quality, direct embedded metadata or direct content validation.
* `MEDIUM`: Trustworthy filename-cues, or standard profile claims with normal metadata.
* `LOW`: Stock files, missing content signals, or significant metadata limitations.

### 4. Stock & Synthetic Provenance Checks
* **Stock Media Tracks**: Files are flagged via dataset-agnostic, configuration-driven provenance rules (`config/evidence_rules.yaml`) — by default a structural filename pattern for royalty-free library tracks (`<publisher>-<slug...>-<catalog-id>.<ext>`). Matched files trigger a `LIMITED_BY_PROVENANCE` limitation, are skipped for content observations, and do *not* count as demonstrated capabilities. No artist folder names or track titles appear in the code.
* **Synthetic Metadata**: Comments matching `"Synthetic assessment sample"` trigger a `SYNTHETIC_SAMPLE` limitation but do not automatically invalidate the evidence.
