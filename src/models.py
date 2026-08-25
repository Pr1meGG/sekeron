from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

@dataclass
class ArtistRecord:
    artist_key: str
    folder_path: str
    display_name: str
    category: str
    profile_files: List[str] = field(default_factory=list)
    media_files: List[str] = field(default_factory=list)
    profile_ids: List[str] = field(default_factory=list)
    identity_anomalies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class ProfileClaim:
    artist_key: str
    claim: str
    source_file: str
    section_or_locator: str
    claim_type: str
    confidence: float
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class MediaAsset:
    asset_key: str
    artist_key: str
    path: str
    filename: str
    declared_extension: str
    detected_mime: str
    media_type: str
    size_bytes: int
    sha256: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    readable: bool = True
    duplicate_of: Optional[str] = None
    anomalies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class TechnicalObservation:
    asset_key: str
    artist_key: str
    path: str
    filename: str
    declared_extension: str
    detected_mime: str
    media_type: str
    size_bytes: int
    sha256: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    readable: bool = True
    duplicate_of: Optional[str] = None
    anomalies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class ContentObservation:
    asset_key: str
    artist_key: str
    subject: str            # e.g., "product", "candid event", "nature", "instrumental"
    format_style: str       # e.g., "tabletop cosmetic", "group circle", "vertical short-form"
    audio_content: str      # e.g., "acoustic guitar and vocals", "silent", "electronic beat"
    confidence: str         # HIGH, MEDIUM, LOW
    source_locator: str     # filename or filename + timestamp
    source_type: str        # direct_content, filename_context, embedded_metadata, profile_claim

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class CapabilityAssessment:
    artist_key: str
    capability: str
    status: str             # DEMONSTRATED, CLAIMED_ONLY, UNKNOWN
    confidence: str         # HIGH, MEDIUM, LOW
    supporting_evidence: List[str]  # list of asset_keys
    supporting_claims: List[str]    # list of claimed texts
    limitations: List[str]          # e.g., LIMITED_BY_PROVENANCE, SYNTHETIC_SAMPLE

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class DataQualityIssue:
    severity: str  # e.g., ERROR, WARNING, INFO
    issue_type: str  # e.g., extension_mismatch, duplicate_id, silent_video
    artist_key: Optional[str]
    asset_key: Optional[str]
    description: str
    evidence: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
