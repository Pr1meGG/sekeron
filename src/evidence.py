import os
import re
from pathlib import Path
from functools import lru_cache
from typing import Dict, Any, List, Tuple, Optional, Set
import yaml

from .models import TechnicalObservation, ContentObservation, CapabilityAssessment

# Default location of the dataset-agnostic evidence rule configuration.
EVIDENCE_RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "evidence_rules.yaml"

# Categorical confidence ranking used to enforce the filename-cue ceiling.
_CONFIDENCE_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
_FILENAME_CONTEXT_MAX_CONFIDENCE = "MEDIUM"

@lru_cache(maxsize=None)
def _load_evidence_rules_cached(rules_path: str) -> Dict[str, Any]:
    """Load and cache evidence rules from a YAML file.

    Missing or malformed files degrade gracefully to empty rule sets so the
    evidence layer never crashes on configuration problems; it simply finds
    no stock media and no filename cues.
    """
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = yaml.safe_load(f) or {}
    except OSError:
        rules = {}
    if not isinstance(rules, dict):
        rules = {}
    return {
        "stock_media_rules": rules.get("stock_media_rules") or [],
        "content_cues": rules.get("content_cues") or [],
    }

def load_evidence_rules(rules_path: Optional[Path] = None) -> Dict[str, Any]:
    """Public accessor for evidence rules; reloads when the path changes."""
    path = str(Path(rules_path)) if rules_path else str(EVIDENCE_RULES_PATH)
    return _load_evidence_rules_cached(path)

def reset_evidence_rules() -> None:
    """Drop cached rules so the next access re-reads them (used by tests)."""
    _load_evidence_rules_cached.cache_clear()

def _rule_target(field: str, filename: str, artist_key: str, path: str) -> str:
    """Return the lowercase string a rule's field refers to."""
    targets = {
        "filename": filename,
        "artist_key": artist_key,
        "path": path,
    }
    return str(targets.get(field, filename)).lower()

# Mappings of profile claims to normalized capability names
CAPABILITY_MAPPING = {
    "product": "product_photography",
    "food": "food_photography",
    "fashion": "fashion_photography",
    "portrait": "portrait_photography",
    "event": "event_photography",
    "candid": "event_photography",
    "architecture": "architecture_photography",
    "interior": "architecture_photography",
    "hospitality": "architecture_photography",
    "travel": "travel_photography",
    "nature": "nature_photography",
    
    # Musicians
    "acoustic": "acoustic_music",
    "vocals": "acoustic_music",
    "singer": "acoustic_music",
    "guitar": "acoustic_music",
    "electronic": "electronic_music",
    "live electronic": "electronic_music",
    
    # Video Editors
    "social": "vertical_video_editing",
    "short-form": "vertical_video_editing",
    "reel": "vertical_video_editing",
    "explainer": "corporate_explainer_editing",
    "interview": "corporate_explainer_editing",
    "company": "corporate_explainer_editing",
    "travel film": "cinematic_travel_editing",
    "wedding film": "cinematic_travel_editing",
    "hospitality film": "cinematic_travel_editing",
    "cinematography": "cinematography_production",
    "videography": "cinematography_production"
}

def is_stock_media(filename: str, artist_key: str = "", path: str = "") -> bool:
    """Detect whether an asset is stock/royalty-free media.

    Detection is fully configuration-driven via ``config/evidence_rules.yaml``:
    ordered regex rules matched against asset fields (filename/path/artist_key).
    No artist names, folder names, or dataset-specific filenames appear here.
    """
    for rule in load_evidence_rules().get("stock_media_rules", []):
        if not isinstance(rule, dict):
            continue
        pattern = rule.get("pattern")
        if not pattern:
            continue
        target = _rule_target(rule.get("field", "filename"), filename, artist_key, path)
        try:
            if re.search(pattern, target):
                return True
        except re.error:
            # Invalid patterns must never crash the pipeline; skip the rule.
            continue
    return False

def compile_technical_observations(media_assets: List[Dict[str, Any]]) -> List[TechnicalObservation]:
    """Compile raw ingestion media records into TechnicalObservation objects."""
    obs = []
    for asset in media_assets:
        obs.append(TechnicalObservation(
            asset_key=asset["asset_key"],
            artist_key=asset["artist_key"],
            path=asset["path"],
            filename=asset["filename"],
            declared_extension=asset["declared_extension"],
            detected_mime=asset["detected_mime"],
            media_type=asset["media_type"],
            size_bytes=asset["size_bytes"],
            sha256=asset["sha256"],
            metadata=asset["metadata"],
            readable=asset["readable"],
            duplicate_of=asset["duplicate_of"],
            anomalies=asset["anomalies"]
        ))
    return obs

def detect_content_observation(asset: Dict[str, Any]) -> Optional[Tuple[ContentObservation, str]]:
    """
    Formulate a ContentObservation strictly from trustworthy semantic signals (filenames, tags).
    Imposes a confidence ceiling of MEDIUM for filename/context cues.

    Filename cues come from the configuration-driven table in
    ``config/evidence_rules.yaml`` (ordered regex rules); this module contains
    no dataset-specific filename substrings.
    """
    filename = asset.get("filename", "")
    artist_key = asset.get("artist_key", "")
    
    # Skip stock media as it does not demonstrate original capability
    if is_stock_media(filename, artist_key, asset.get("path", "")):
        return None
        
    subject = "unknown"
    format_style = "unknown"
    audio_content = "unknown"
    confidence = "LOW"
    source_type = "filename_context"
    capability = None
    
    fname_lower = filename.lower()

    # Configuration-driven filename cues (first matching rule wins).
    for cue in load_evidence_rules().get("content_cues", []):
        if not isinstance(cue, dict):
            continue
        pattern = cue.get("pattern")
        if not pattern:
            continue
        try:
            matched = re.search(pattern, fname_lower) is not None
        except re.error:
            continue
        if not matched:
            continue
        subject = str(cue.get("subject", "unknown"))
        format_style = str(cue.get("format_style", "unknown"))
        audio_content = str(cue.get("audio_content", "unknown"))
        capability = cue.get("capability")
        # Enforce the knowledge.md ceiling: filename context is capped at MEDIUM.
        cue_confidence = str(cue.get("confidence", "MEDIUM")).upper()
        if _CONFIDENCE_RANK.get(cue_confidence, 1) > _CONFIDENCE_RANK[_FILENAME_CONTEXT_MAX_CONFIDENCE]:
            cue_confidence = _FILENAME_CONTEXT_MAX_CONFIDENCE
        confidence = cue_confidence
        break

    # 4. EXIF Embedded Metadata
    exif = asset.get("metadata", {}).get("exif", {})
    desc = exif.get("ImageDescription") or exif.get("UserComment")
    if desc and len(str(desc).strip()) > 3:
        subject = str(desc).strip()
        format_style = "embedded description"
        confidence = "HIGH"
        source_type = "embedded_metadata"
        # Check if subject matches key terms for capability
        for kw, cap in CAPABILITY_MAPPING.items():
            if kw in subject.lower():
                capability = cap
                break

    if subject == "unknown" and format_style == "unknown":
        return None
        
    # Default capability based on name matching if not already set
    if not capability:
        for kw, cap in CAPABILITY_MAPPING.items():
            if kw in fname_lower:
                capability = cap
                break
                
    if not capability:
        return None

    return ContentObservation(
        asset_key=asset["asset_key"],
        artist_key=artist_key,
        subject=subject,
        format_style=format_style,
        audio_content=audio_content,
        confidence=confidence,
        source_locator=filename,
        source_type=source_type
    ), capability

def normalize_profile_claims(claims_data: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """Map profile claim text strings into normalized capability IDs."""
    mappings = []
    for claim in claims_data:
        claim_text = claim["claim"].lower()
        artist_key = claim["artist_key"]
        
        # Scan for matching capability terms in the claim string.
        # NOTE: a generic role/category label (e.g. "Photographer", "Video Editor")
        # must NOT be treated as evidence for a specific capability. Only explicit
        # claim keywords (from CAPABILITY_MAPPING) or demonstrated evidence may
        # produce a capability signal.
        matched_caps = set()
        for term, cap in CAPABILITY_MAPPING.items():
            if term in claim_text:
                matched_caps.add(cap)

        for cap in matched_caps:
            mappings.append((artist_key, cap, claim["claim"]))
            
    return mappings

def compile_evidence_layer(ingestion_data: Dict[str, Any]) -> Tuple[List[TechnicalObservation], List[ContentObservation], List[CapabilityAssessment], List[Dict[str, Any]]]:
    """Coordinates Phase 2 mapping, duplicate checks, stock-music filters, and capability assessment."""
    artists_list = ingestion_data.get("artists", [])
    media_list = ingestion_data.get("media", [])
    claims_list = ingestion_data.get("profile_claims", [])
    quality_issues = ingestion_data.get("quality_issues", [])
    
    # 1. Compile Technical Observations
    tech_obs = compile_technical_observations(media_list)
    
    # 2. Compile Content Observations
    content_obs: List[ContentObservation] = []
    media_capability_map: Dict[str, List[Tuple[str, str]]] = {} # artist_key -> list of (asset_key, capability)
    
    for asset in media_list:
        res = detect_content_observation(asset)
        if res:
            obs, cap = res
            content_obs.append(obs)
            media_capability_map.setdefault(asset["artist_key"], []).append((asset["asset_key"], cap))
            
    # 3. Normalize Profile Claims
    normalized_claims = normalize_profile_claims(claims_list)
    # Group claims by artist_key -> capability -> list of original claims
    claims_by_artist_cap: Dict[str, Dict[str, List[str]]] = {}
    for artist_key, cap, orig_claim in normalized_claims:
        claims_by_artist_cap.setdefault(artist_key, {}).setdefault(cap, []).append(orig_claim)
        
    # Group content observations by artist_key -> capability -> list of non-duplicate asset_keys
    evidence_by_artist_cap: Dict[str, Dict[str, List[str]]] = {}
    for asset in media_list:
        artist_key = asset["artist_key"]
        asset_key = asset["asset_key"]
        
        # Check if this asset mapped to a capability in step 2
        for key, cap in media_capability_map.get(artist_key, []):
            if key == asset_key:
                # Deduplicate check: identical SHA-256 counts as one independent evidence item
                # If duplicate_of is present, we skip adding it to the evidence list, or record it differently
                if asset.get("duplicate_of"):
                    # Skipped from adding as independent evidence
                    continue
                evidence_by_artist_cap.setdefault(artist_key, {}).setdefault(cap, []).append(asset_key)

    # 4. Build Capability Assessments
    assessments: List[CapabilityAssessment] = []
    
    # Define the union of all capabilities per artist
    for artist in artists_list:
        artist_key = artist["artist_key"]
        artist_category = artist["category"]
        
        # Capabilities claimed by profile or demonstrated by media
        artist_caps: Set[str] = set()
        if artist_key in claims_by_artist_cap:
            artist_caps.update(claims_by_artist_cap[artist_key].keys())
        if artist_key in evidence_by_artist_cap:
            artist_caps.update(evidence_by_artist_cap[artist_key].keys())
            
        # Ensure we add relevant category-default capabilities if not found
        # (Allows testing for CLAIMED_ONLY vs UNKNOWN on target assessment parameters)
        category_caps = []
        if artist_category == "photographer":
            category_caps = ["product_photography", "portrait_photography", "architecture_photography", "nature_photography", "event_photography"]
        elif artist_category == "musician":
            category_caps = ["acoustic_music", "electronic_music"]
        elif artist_category == "video_editor":
            category_caps = ["vertical_video_editing", "corporate_explainer_editing", "cinematic_travel_editing", "cinematography_production"]
            
        for cap in category_caps:
            artist_caps.add(cap)
            
        for cap in sorted(artist_caps):
            supporting_claims = claims_by_artist_cap.get(artist_key, {}).get(cap, [])
            supporting_evidence = evidence_by_artist_cap.get(artist_key, {}).get(cap, [])
            
            # Limitations detection
            limitations = []
            
            # Check for general artist anomalies from quality issues
            for issue in quality_issues:
                if issue.get("artist_key") == artist_key:
                    if issue["issue_type"] in ["id_conflict", "name_mismatch", "unusual_directory_layout"]:
                        limitations.append(issue["issue_type"].upper())
                        
            # Check for stock media limitation
            # If the artist has stock media portfolio files, flag it
            has_stock = False
            for m in media_list:
                if m["artist_key"] == artist_key and is_stock_media(m["filename"], artist_key, m.get("path", "")):
                    has_stock = True
                    break
            if has_stock:
                limitations.append("LIMITED_BY_PROVENANCE")
                # Stock media does NOT count as demonstrated original capability
                # We override supporting evidence list to be empty so it falls back to CLAIMED_ONLY
                supporting_evidence = []
                
            # Check for synthetic sample tags in assets
            has_synthetic = False
            for m in media_list:
                if m["artist_key"] == artist_key:
                    comment = m.get("metadata", {}).get("tags", {}).get("comment", "")
                    if "synthetic" in str(comment).lower():
                        has_synthetic = True
                        break
            if has_synthetic:
                limitations.append("SYNTHETIC_SAMPLE")

            # Determine status
            status = "UNKNOWN"
            if supporting_evidence:
                status = "DEMONSTRATED"
            elif supporting_claims:
                status = "CLAIMED_ONLY"
                
            # Determine categorical confidence
            confidence = "LOW"
            if status == "DEMONSTRATED":
                # Check supporting evidence content observations
                obs_confidences = [obs.confidence for obs in content_obs if obs.artist_key == artist_key and obs.asset_key in supporting_evidence]
                if "HIGH" in obs_confidences:
                    confidence = "HIGH"
                elif "MEDIUM" in obs_confidences:
                    confidence = "MEDIUM"
                else:
                    confidence = "LOW"
            elif status == "CLAIMED_ONLY":
                # Claims without evidence have medium confidence unless limited by provenance
                if "LIMITED_BY_PROVENANCE" in limitations:
                    confidence = "LOW"
                else:
                    confidence = "MEDIUM"
            else:
                confidence = "LOW"
                
            assessments.append(CapabilityAssessment(
                artist_key=artist_key,
                capability=cap,
                status=status,
                confidence=confidence,
                supporting_evidence=supporting_evidence,
                supporting_claims=supporting_claims,
                limitations=sorted(list(set(limitations)))
            ))
            
    # Gather evidence quality summary logs
    quality_summary = []
    for issue in quality_issues:
        quality_summary.append({
            "issue_type": issue["issue_type"],
            "artist_key": issue["artist_key"],
            "severity": issue["severity"],
            "description": issue["description"]
        })
        
    return tech_obs, content_obs, assessments, quality_summary
