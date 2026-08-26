import os
from pathlib import Path
from typing import List, Dict, Any, Tuple, Set
from .config import Config
from .models import ArtistRecord, ProfileClaim, MediaAsset, DataQualityIssue
from .profiles import extract_claims_and_issues
from .media import process_media_file

def run_ingestion(config: Config) -> Tuple[List[ArtistRecord], List[MediaAsset], List[ProfileClaim], List[DataQualityIssue]]:
    """
    Run the ingestion pipeline on the dataset root.
    Exits gracefully on missing directories or individual file reading errors.
    """
    dataset_root = config.dataset_root
    artist_profiles_dir = dataset_root / "artist_profiles"
    
    artists: List[ArtistRecord] = []
    all_media: List[MediaAsset] = []
    all_claims: List[ProfileClaim] = []
    all_issues: List[DataQualityIssue] = []

    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root path does not exist: {dataset_root}")
        
    if not artist_profiles_dir.exists():
        raise FileNotFoundError(f"artist_profiles directory not found under dataset root: {artist_profiles_dir}")

    # Track overall duplicate detection maps
    sha256_map: Dict[str, MediaAsset] = {}  # sha256 -> MediaAsset
    claimed_ids_map: Dict[str, List[str]] = {}  # claimed_id -> list of artist_keys
    
    # 1. Discover Artists
    # Iterate through subdirectories under artist_profiles/
    for category_dir in sorted(artist_profiles_dir.iterdir()):
        if not category_dir.is_dir() or category_dir.name.startswith('.'):
            continue
            
        category_name = category_dir.name  # e.g., photographers, musicians, video_editors
        
        for artist_dir in sorted(category_dir.iterdir()):
            if not artist_dir.is_dir() or artist_dir.name.startswith('.'):
                continue
                
            folder_name = artist_dir.name
            
            # Canonical key is the normalized relative folder path
            # e.g., 'artist_profiles/photographers/P01_Jane_Doe'
            relative_folder_path = artist_dir.relative_to(dataset_root)
            artist_key = str(relative_folder_path).replace(os.path.sep, '/')
            
            # Find files recursively under this artist directory
            profile_paths: List[Path] = []
            media_paths: List[Path] = []
            
            for p in artist_dir.rglob('*'):
                if not p.is_file() or p.name.startswith('.'):
                    continue
                ext = p.suffix.lower()
                if ext == '.docx':
                    profile_paths.append(p)
                elif ext in ['.jpg', '.jpeg', '.png', '.webp', '.mpo', '.mp4', '.mov', '.wav', '.mp3']:
                    media_paths.append(p)
            
            # 2. Parse Profile Document(s)
            profile_ids = []
            display_name = folder_name.split('_', 1)[1].replace('_', ' ') if '_' in folder_name else folder_name
            identity_anomalies = []
            
            # Process profile claims
            if not profile_paths:
                # Anomaly: missing profile
                issue = DataQualityIssue(
                    severity="ERROR",
                    issue_type="missing_profile",
                    artist_key=artist_key,
                    asset_key=None,
                    description=f"Artist directory '{folder_name}' is missing a profile docx file.",
                    evidence=f"Checked path: {artist_dir}"
                )
                all_issues.append(issue)
                identity_anomalies.append("missing_profile")
            else:
                for doc_path in sorted(profile_paths):
                    try:
                        claims, issues, details = extract_claims_and_issues(doc_path, artist_key, folder_name)
                        all_claims.extend(claims)
                        all_issues.extend(issues)
                        
                        if details["claimed_id"]:
                            profile_ids.append(details["claimed_id"])
                            # Track for duplicate claimed IDs later
                            claimed_ids_map.setdefault(details["claimed_id"], []).append(artist_key)
                            
                        # Use the extracted display name if found
                        display_name = details["display_name"]
                        
                        # Add profile issues to identity anomalies list
                        for issue in issues:
                            identity_anomalies.append(issue.issue_type)
                    except Exception as e:
                        all_issues.append(DataQualityIssue(
                            severity="ERROR",
                            issue_type="corrupt_profile",
                            artist_key=artist_key,
                            asset_key=doc_path.name,
                            description=f"Failed to parse profile docx: {str(e)}",
                            evidence=str(doc_path)
                        ))
                        identity_anomalies.append("corrupt_profile")

            # 3. Process Media Assets
            artist_media_assets: List[MediaAsset] = []
            has_unusual_layout = False
            
            for m_path in sorted(media_paths):
                try:
                    asset, issues = process_media_file(m_path, artist_key)
                    all_issues.extend(issues)
                    
                    # Detect unusual directory layout
                    # Expect direct parent folder name of media files to be 'media'
                    parent_dir_name = m_path.parent.name
                    if parent_dir_name != 'media':
                        has_unusual_layout = True
                        
                    # Handle duplicate assets using SHA-256 mapping
                    if asset.readable and asset.sha256:
                        if asset.sha256 in sha256_map:
                            original_asset = sha256_map[asset.sha256]
                            asset.duplicate_of = original_asset.path
                            asset.anomalies.append("duplicate_media")
                            
                            all_issues.append(DataQualityIssue(
                                severity="WARNING",
                                issue_type="duplicate_media",
                                artist_key=artist_key,
                                asset_key=asset.filename,
                                description=f"Media file '{asset.filename}' is a duplicate of '{original_asset.filename}' (Artist: {original_asset.artist_key}).",
                                evidence=f"SHA-256 hash match: {asset.sha256}"
                            ))
                        else:
                            sha256_map[asset.sha256] = asset
                            
                    artist_media_assets.append(asset)
                    all_media.append(asset)
                except Exception as e:
                    # Log file processing errors but continue gracefully
                    all_issues.append(DataQualityIssue(
                        severity="ERROR",
                        issue_type="unreadable_file",
                        artist_key=artist_key,
                        asset_key=m_path.name,
                        description=f"Failed to process media file: {str(e)}",
                        evidence=str(m_path)
                    ))

            # 4. Unusual directory layout check
            if has_unusual_layout:
                identity_anomalies.append("unusual_directory_layout")
                all_issues.append(DataQualityIssue(
                    severity="WARNING",
                    issue_type="unusual_directory_layout",
                    artist_key=artist_key,
                    asset_key=None,
                    description=f"Artist directory '{folder_name}' has an unusual media directory layout.",
                    evidence=f"Media files detected outside standard 'media/' subfolder."
                ))

            # 5. Suspicious Category/Media mismatch check
            media_types = {a.media_type for a in artist_media_assets if a.readable}
            if artist_media_assets:
                if category_name == "photographers":
                    # Photographers must have images
                    if "image" not in media_types:
                        identity_anomalies.append("media_category_mismatch")
                        all_issues.append(DataQualityIssue(
                            severity="WARNING",
                            issue_type="media_category_mismatch",
                            artist_key=artist_key,
                            asset_key=None,
                            description=f"Photographer '{folder_name}' has no verified image assets in their portfolio.",
                            evidence=f"Media types present: {list(media_types)}"
                        ))
                elif category_name == "musicians":
                    # Musicians must have audio or video
                    if "audio" not in media_types and "video" not in media_types:
                        identity_anomalies.append("media_category_mismatch")
                        all_issues.append(DataQualityIssue(
                            severity="WARNING",
                            issue_type="media_category_mismatch",
                            artist_key=artist_key,
                            asset_key=None,
                            description=f"Musician '{folder_name}' has no verified audio or video assets in their portfolio.",
                            evidence=f"Media types present: {list(media_types)}"
                        ))
                elif category_name == "video_editors":
                    # Video editors must have video
                    if "video" not in media_types:
                        identity_anomalies.append("media_category_mismatch")
                        all_issues.append(DataQualityIssue(
                            severity="WARNING",
                            issue_type="media_category_mismatch",
                            artist_key=artist_key,
                            asset_key=None,
                            description=f"Video editor '{folder_name}' has no verified video assets in their portfolio.",
                            evidence=f"Media types present: {list(media_types)}"
                        ))

            # Build and append Artist Record
            artist_rec = ArtistRecord(
                artist_key=artist_key,
                folder_path=str(artist_dir),
                display_name=display_name,
                category=category_name.rstrip('s'),  # photographer, musician, video_editor
                profile_files=[str(p) for p in profile_paths],
                media_files=[str(p) for p in media_paths],
                profile_ids=profile_ids,
                identity_anomalies=identity_anomalies
            )
            artists.append(artist_rec)
            
    # 6. Post-scan: Check for duplicate claimed profile IDs
    for claimed_id, keys in claimed_ids_map.items():
        if len(keys) > 1:
            for key in keys:
                # Add anomaly issue to the list
                all_issues.append(DataQualityIssue(
                    severity="ERROR",
                    issue_type="duplicate_profile_id",
                    artist_key=key,
                    asset_key=None,
                    description=f"Claimed profile ID '{claimed_id}' is claimed by multiple folders.",
                    evidence=f"ID '{claimed_id}' claimed by: {keys}"
                ))
                # Update the matching artist records
                for artist in artists:
                    if artist.artist_key == key:
                        if "duplicate_profile_id" not in artist.identity_anomalies:
                            artist.identity_anomalies.append("duplicate_profile_id")
                            
    return artists, all_media, all_claims, all_issues
