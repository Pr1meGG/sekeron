# Media Selection Policy

The Stage 3 pipeline uses the existing lightweight ingestion/evidence layer.

## Inspected

- File bytes are SHA-256 hashed for duplicate detection.
- Image files are opened with Pillow for content MIME detection, dimensions, and available EXIF fields.
- Audio/video files are inspected with `ffprobe` for container, duration, stream, codec, and audio/video metadata.
- Configured filename/context cues may create content observations, but their confidence is capped at `MEDIUM` and they are never treated as strong visual proof.
- Stock/third-party media is excluded from capability evidence.

## Skipped

- No full video-frame decoding or exhaustive frame sampling is performed.
- No speech transcription, VLM classification, face recognition, reverse image search, or internet lookup is performed.
- No Kaggle integration is used.

## Rationale and limitations

The recruiter outputs can be generated from the supplied profile claims, technical metadata, provenance rules, and weak configured filename cues. The dataset does not require expensive semantic media processing to produce a defensible submission. Filename cues remain limited evidence, and capabilities with no trustworthy claim or content cue remain `UNKNOWN`. If future data requires semantic verification of ambiguous videos or audio, representative frame/audio sampling can be added as a separately reviewed operation; it should not silently upgrade existing evidence.
