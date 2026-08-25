import os
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional
from PIL import Image
from PIL.ExifTags import TAGS

from .models import MediaAsset, DataQualityIssue

def calculate_sha256(path: Path) -> str:
    """Compute the SHA-256 hash of a file."""
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        raise RuntimeError(f"Failed to calculate SHA-256 for {path.name}: {str(e)}")

def run_ffprobe(path: Path) -> Dict[str, Any]:
    """Execute ffprobe on the file and return parsed JSON results."""
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        str(path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if res.returncode != 0:
            return {}
        return json.loads(res.stdout)
    except Exception:
        return {}

def detect_mime_type_from_content(path: Path) -> str:
    """
    Detect MIME type strictly from file content.
    Precedence: Pillow (Image) -> ffprobe (Audio/Video) -> ZIP/DOCX -> Text -> Unknown.
    """
    # 1. Pillow for recognized images
    try:
        with Image.open(path) as img:
            fmt = img.format.lower()
            if fmt == 'jpeg':
                return 'image/jpeg'
            elif fmt == 'png':
                return 'image/png'
            elif fmt == 'webp':
                return 'image/webp'
            elif fmt == 'gif':
                return 'image/gif'
            elif fmt == 'mpo':
                return 'image/jpeg'
            return f"image/{fmt}"
    except Exception:
        pass

    # 2. ffprobe for recognized audio/video
    ff = run_ffprobe(path)
    if ff and 'format' in ff and 'streams' in ff:
        fmt_name = ff['format'].get('format_name', '').lower()
        streams = ff.get('streams', [])
        has_video = any(s.get('codec_type') == 'video' for s in streams)
        has_audio = any(s.get('codec_type') == 'audio' for s in streams)
        
        if 'mp4' in fmt_name or 'mov' in fmt_name or 'quicktime' in fmt_name:
            if has_video:
                return 'video/mp4' if 'mp4' in fmt_name else 'video/quicktime'
            elif has_audio:
                return 'audio/mp4'
        elif 'wav' in fmt_name or 'pcm' in fmt_name:
            return 'audio/wav'
        elif 'mp3' in fmt_name:
            return 'audio/mpeg'
        
        # Generic fallback based on stream presence
        if has_video:
            # e.g., video/matroska
            first_fmt = fmt_name.split(',')[0].strip()
            return f"video/{first_fmt}"
        elif has_audio:
            first_fmt = fmt_name.split(',')[0].strip()
            return f"audio/{first_fmt}"

    # 3. ZIP/DOCX inspection
    if zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path) as z:
                if 'word/document.xml' in z.namelist():
                    return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                return 'application/zip'
        except Exception:
            pass

    # 4. UTF-8 / Text inspection
    try:
        with open(path, 'r', encoding='utf-8') as f:
            f.read(1024)
            return 'text/plain'
    except Exception:
        pass

    return 'application/octet-stream'

def get_expected_mimes_for_ext(ext: str) -> List[str]:
    """Get accepted MIME types for a given file extension suffix."""
    mapping = {
        '.png': ['image/png'],
        '.jpg': ['image/jpeg'],
        '.jpeg': ['image/jpeg'],
        '.webp': ['image/webp'],
        '.mpo': ['image/jpeg', 'image/mpo'],
        '.mp4': ['video/mp4'],
        '.mov': ['video/quicktime'],
        '.wav': ['audio/wav', 'audio/x-wav'],
        '.mp3': ['audio/mpeg', 'audio/mp3'],
        '.docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
        '.txt': ['text/plain']
    }
    return mapping.get(ext.lower(), [])

def get_media_type_from_mime(mime: str) -> str:
    """Categorize media class by MIME type prefix."""
    if mime.startswith('image/'):
        return 'image'
    elif mime.startswith('video/'):
        return 'video'
    elif mime.startswith('audio/'):
        return 'audio'
    elif mime.startswith('text/'):
        return 'text'
    elif 'wordprocessingml' in mime:
        return 'document'
    return 'unknown'

def extract_image_metadata(path: Path) -> Dict[str, Any]:
    """Extract width, height, format, mode, and EXIF tags from images."""
    meta = {}
    try:
        with Image.open(path) as img:
            meta['width'] = img.width
            meta['height'] = img.height
            meta['format'] = img.format
            meta['mode'] = img.mode
            
            # Extract EXIF tags
            exif_data = {}
            if hasattr(img, '_getexif') and img._getexif() is not None:
                for tag, value in img._getexif().items():
                    tag_name = TAGS.get(tag, tag)
                    if isinstance(value, bytes):
                        try:
                            value = value.decode('utf-8', errors='replace')
                        except Exception:
                            value = repr(value)
                    elif not isinstance(value, (str, int, float, bool, list, dict, type(None))):
                        value = str(value)
                    exif_data[str(tag_name)] = value
            meta['exif'] = exif_data
    except Exception as e:
        meta['error'] = f"Failed to extract image metadata: {str(e)}"
    return meta

def extract_av_metadata(path: Path, ff: Dict[str, Any]) -> Dict[str, Any]:
    """Extract format, duration, audio channels, video streams, and codecs from audio/video."""
    meta = {}
    try:
        fmt_info = ff.get('format', {})
        meta['duration'] = float(fmt_info.get('duration', 0.0))
        meta['bitrate'] = int(fmt_info.get('bit_rate', 0)) if fmt_info.get('bit_rate') else None
        meta['format_name'] = fmt_info.get('format_name', '')
        
        # Collect stream metadata
        video_streams = []
        audio_streams = []
        for s in ff.get('streams', []):
            codec_type = s.get('codec_type')
            codec = s.get('codec_name')
            if codec_type == 'video':
                video_streams.append({
                    "codec": codec,
                    "width": s.get('width'),
                    "height": s.get('height'),
                    "frame_rate": s.get('r_frame_rate')
                })
            elif codec_type == 'audio':
                audio_streams.append({
                    "codec": codec,
                    "channels": s.get('channels'),
                    "sample_rate": int(s.get('sample_rate', 0)) if s.get('sample_rate') else None
                })
                
        meta['video_streams'] = video_streams
        meta['audio_streams'] = audio_streams
        meta['has_video'] = len(video_streams) > 0
        meta['has_audio'] = len(audio_streams) > 0
        
        # Keep raw tags if present
        meta['tags'] = fmt_info.get('tags', {})
    except Exception as e:
        meta['error'] = f"Failed to extract A/V metadata: {str(e)}"
    return meta

def process_media_file(
    path: Path, 
    artist_key: str
) -> Tuple[MediaAsset, List[DataQualityIssue]]:
    """
    Process a single media asset file: read content, extract metadata,
    and detect anomalies. Hashing is performed.
    """
    filename = path.name
    declared_extension = path.suffix
    size_bytes = path.stat().st_size
    
    anomalies = []
    issues = []
    
    # 1. Hashing
    try:
        sha256 = calculate_sha256(path)
        readable = True
    except Exception as e:
        # File is unreadable
        sha256 = ""
        readable = False
        anomalies.append("unreadable_file")
        issues.append(DataQualityIssue(
            severity="ERROR",
            issue_type="unreadable_file",
            artist_key=artist_key,
            asset_key=None,
            description=f"File '{filename}' is unreadable or corrupted on disk.",
            evidence=str(e)
        ))
        
        asset = MediaAsset(
            asset_key=str(path.name),
            artist_key=artist_key,
            path=str(path),
            filename=filename,
            declared_extension=declared_extension,
            detected_mime="application/octet-stream",
            media_type="unknown",
            size_bytes=size_bytes,
            sha256=sha256,
            readable=False,
            anomalies=anomalies
        )
        return asset, issues

    # 2. Content-based MIME detection
    detected_mime = detect_mime_type_from_content(path)
    media_type = get_media_type_from_mime(detected_mime)
    
    # 3. Anomaly check: Empty File
    if size_bytes == 0:
        anomalies.append("empty_file")
        issues.append(DataQualityIssue(
            severity="ERROR",
            issue_type="empty_file",
            artist_key=artist_key,
            asset_key=filename,
            description=f"File '{filename}' is empty (0 bytes).",
            evidence="Size on disk is 0 bytes."
        ))

    # 4. Anomaly check: Extension Mismatch
    expected_mimes = get_expected_mimes_for_ext(declared_extension)
    if expected_mimes and detected_mime not in expected_mimes:
        anomalies.append("extension_mismatch")
        issues.append(DataQualityIssue(
            severity="WARNING",
            issue_type="extension_mismatch",
            artist_key=artist_key,
            asset_key=filename,
            description=f"File extension '{declared_extension}' does not match detected content MIME '{detected_mime}'.",
            evidence=f"Declared ext: {declared_extension}, Content MIME: {detected_mime}"
        ))

    # 5. Metadata extraction
    metadata = {}
    if media_type == 'image':
        metadata = extract_image_metadata(path)
    elif media_type in ['video', 'audio']:
        ff = run_ffprobe(path)
        if ff:
            metadata = extract_av_metadata(path, ff)
            
            # Anomaly check: Silent Video (video has no audio streams)
            if media_type == 'video' and not metadata.get('has_audio', False):
                anomalies.append("silent_video")
                issues.append(DataQualityIssue(
                    severity="WARNING",
                    issue_type="silent_video",
                    artist_key=artist_key,
                    asset_key=filename,
                    description=f"Video asset '{filename}' does not contain an audio stream.",
                    evidence=f"Codec type list has no audio codecs."
                ))
        else:
            anomalies.append("missing_media_metadata")
            issues.append(DataQualityIssue(
                severity="WARNING",
                issue_type="missing_media_metadata",
                artist_key=artist_key,
                asset_key=filename,
                description=f"Audio/video asset '{filename}' metadata could not be parsed by ffprobe.",
                evidence="ffprobe returned empty stream information."
            ))

    asset = MediaAsset(
        asset_key=filename,  # relative filename is used as asset key inside artist scope
        artist_key=artist_key,
        path=str(path),
        filename=filename,
        declared_extension=declared_extension,
        detected_mime=detected_mime,
        media_type=media_type,
        size_bytes=size_bytes,
        sha256=sha256,
        metadata=metadata,
        readable=readable,
        anomalies=anomalies
    )
    
    return asset, issues
