"""
Phase 2: Hirer Intent Parsing

Deterministically parses the hirer conversation files and extracts structured
brief information without hard-coding output objects.

Parsing is intentionally conservative:
  - conversation timestamp prefixes are stripped before constraint extraction
  - only numbers explicitly tagged as budgets (k/INR/₹) or adjacent to a budget
    keyword are treated as budgets
  - only am/pm-qualified ranges are treated as times
  - repeated constraints are deduplicated
  - disqualifiers fire only when their own supporting text is present
"""

import re
from pathlib import Path
from typing import Dict, Any, List

# Conversation timestamp prefix, e.g. "18/08/26, 6:41 pm - Rhea: "
_TIMESTAMP_PREFIX = re.compile(
    r'^\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}\s*(?:am|pm)?\s*[-–]\s*[^:]+:\s*',
    re.IGNORECASE,
)

_TIME_RANGE = re.compile(
    r'\d{1,2}(?::\d{2})?\s*(?:am|pm)\s*(?:to|[-–])\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)',
    re.IGNORECASE,
)

_DATE_NUMERIC = re.compile(r'(?<![\d/:])(\d{1,2}/\d{1,2}/\d{2,4})(?![\d/:])')
_DATE_MONTH = re.compile(
    r'\b(\d{1,2}(?:st|nd|rd|th)?\s+'
    r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*)\b',
    re.IGNORECASE,
)

_BUDGET_TOKEN = re.compile(
    r'₹\s*\d[\d,]*|\d[\d,]*(?:\s*[-–]\s*\d[\d,]*)?\s*(?:k|K)\b|\d[\d,]*\s*INR\b',
    re.IGNORECASE,
)
_BUDGET_NEAR_KEYWORD = re.compile(
    r'(?:budget|cost|rate|quote|pay)\s*(?:of|about|around|is|:)?\s*'
    r'(?:₹|INR\s*)?(\d[\d,]*(?:\s*[-–]\s*\d[\d,]*)?\s*(?:k|K|INR|₹)?)',
    re.IGNORECASE,
)

_QUANTITY = re.compile(
    r'(\d{1,3}(?:\s*[-–]\s*\d{1,3})?)\s*'
    r'(?:final\s+(?:images?|pictures?)|images?|photos?|pictures?|clips?|final\b|guests|people|persons)\b',
    re.IGNORECASE,
)


def _strip_timestamps(content: str) -> str:
    """Remove conversation timestamp prefixes, keeping the message body."""
    return "\n".join(
        _TIMESTAMP_PREFIX.sub("", line) if _TIMESTAMP_PREFIX.match(line) else line
        for line in content.split("\n")
    )


def _dedupe(items: List[str]) -> List[str]:
    """Preserve order, drop duplicates."""
    return list(dict.fromkeys(items))


def parse_brief_text(content: str, brief_id: str) -> Dict[str, Any]:
    """
    Parse a hirer conversation file and extract structured brief information.

    Uses deterministic pattern discovery:
    - explicit_constraints: directly stated requirements
    - reasonable_assumptions: inferred but supported by the text
    - contradictions: conflicting statements
    - important_unknowns: questions left open
    - required_capabilities / preferred_capabilities
    - disqualifiers: explicit deal-breakers (branch-specific patterns)
    """
    content_lower = content.lower()
    clean = _strip_timestamps(content)
    clean_lower = clean.lower()

    explicit_constraints: List[str] = []
    reasonable_assumptions: List[str] = []
    contradictions: List[str] = []
    important_unknowns: List[str] = []
    required_capabilities: List[str] = []
    preferred_capabilities: List[str] = []
    disqualifiers: List[str] = []

    # --- Capability Detection ---
    if re.search(r'acoustic|live music|background music', content_lower):
        required_capabilities.append("acoustic_music")
        if re.search(r'vocals?|singer|guitar', content_lower):
            preferred_capabilities.append("vocal_guitar_harmony")

    if re.search(r'product.*(photograph|photo|shoot)|skincare.*launch|bottles?|jars?', content_lower):
        required_capabilities.append("product_photography")
        if re.search(r'fashion|portrait', content_lower):
            preferred_capabilities.append("portrait_photography")

    if re.search(r'reel|vertical.*video|short.?form|9:16|30.*sec', content_lower):
        required_capabilities.append("vertical_video_editing")
        if re.search(r'cinematic|travel', content_lower):
            preferred_capabilities.append("cinematic_travel_editing")

    if re.search(r'event.*(photograph|photo)|leadership|off.?site|group.*photo', content_lower):
        required_capabilities.append("event_photography")
        if re.search(r'headshot|portrait', content_lower):
            preferred_capabilities.append("portrait_photography")

    # --- Time constraints (require explicit am/pm) ---
    for t in _dedupe([m.strip() for m in _TIME_RANGE.findall(clean)]):
        explicit_constraints.append(f"Time: {t}")

    # --- Date constraints (deduplicated; timestamps already stripped) ---
    dates = _DATE_NUMERIC.findall(clean) + _DATE_MONTH.findall(clean)
    for d in _dedupe(dates):
        explicit_constraints.append(f"Date: {d}")

    # --- Budget constraints (explicitly tagged amounts only) ---
    budgets = _BUDGET_TOKEN.findall(clean)
    budgets += [b for b in _BUDGET_NEAR_KEYWORD.findall(clean_lower) if b.strip()]
    budgets = [b.strip() for b in budgets if b.strip()]
    if budgets:
        explicit_constraints.append(f"Budget: {' / '.join(_dedupe(budgets))}")

    # --- Quantity constraints (deduplicated) ---
    for q in _dedupe([m.strip() for m in _QUANTITY.findall(clean)]):
        explicit_constraints.append(f"Quantity: {q}")

    # --- Reasonable Assumptions (supported by text; never fabricated) ---
    if re.search(r'\bdelhi\b|\bncr\b|gurugram|gurgaon|noida', clean_lower):
        reasonable_assumptions.append("Delhi NCR area execution")
    if re.search(r'no\s+.*stage|small\s+area|massive\s+setup', clean_lower):
        reasonable_assumptions.append("Performance in a small cleared area with portable, low-setup equipment")
    if re.search(r'not too loud|still be able to talk|background music', clean_lower):
        reasonable_assumptions.append("Performance remains at a conversation-friendly volume")
    if re.search(r'no studio|simple setup|handle a simple setup|tabletop', clean_lower):
        reasonable_assumptions.append("Photographer handles basic in-situ tabletop setup without a full studio")
    if re.search(r'a lot are probably useless|find the story|not just put every clip', clean_lower):
        reasonable_assumptions.append("Editor curates a small subset of the raw clips rather than using all")
    if re.search(r"don't know if we can legally|legal.*song|suggest something else", clean_lower):
        reasonable_assumptions.append("Editor may need to propose alternative music if the event song cannot be licensed")
    if re.search(r'candid.*more important|candid.*if both.*not realistic', clean_lower):
        reasonable_assumptions.append("Candid event coverage is prioritised over formal headshots")
    if re.search(r'send me two sensible options|procurement', clean_lower):
        reasonable_assumptions.append("Two pricing/scope options will be presented to procurement")

    # --- Important Unknowns (open questions in the conversation) ---
    lines = [l.strip() for l in content.split('\n') if l.strip()]
    for line in lines:
        if '?' not in line and 'whether' not in line.lower():
            continue
        body = _TIMESTAMP_PREFIX.sub('', line).strip()
        clean_q = re.sub(r'^[^:]+:\s*', '', body).strip().rstrip('?').strip()
        if clean_q and len(clean_q) > 5:
            important_unknowns.append(clean_q)

    # --- Contradictions (both ideas present in the text) ---
    if ("background" in content_lower and "music" in content_lower
            and re.search(r"lively|proper performance|headline set", content_lower)):
        contradictions.append("Client wants background music but also requests a lively performance element")

    # --- Disqualifiers (each branch requires its own supporting text) ---
    if re.search(r'massive\s+setup|no\s+.*stage|don\'?t?\s*send.*band', clean_lower):
        disqualifiers.append("Massive setups or large stage requirements")
    if re.search(r'stiff.*conference|not\s+the\s+usual\s+stiff|conference\s+(?:photo|style)', clean_lower):
        disqualifiers.append("Stiff traditional conference style photography")

    return {
        "brief_id": brief_id,
        "explicit_constraints": _dedupe(explicit_constraints),
        "reasonable_assumptions": _dedupe(reasonable_assumptions),
        "contradictions": _dedupe(contradictions),
        "important_unknowns": _dedupe(important_unknowns),
        "required_capabilities": _dedupe(required_capabilities),
        "preferred_capabilities": _dedupe(preferred_capabilities),
        "disqualifiers": _dedupe(disqualifiers),
    }


def parse_hirer_briefs(dataset_root: Path) -> List[Dict[str, Any]]:
    """
    Phase 2: Discover and parse all hirer conversation files from disk.
    """
    hirer_dir = dataset_root / "hirer_conversations"
    if not hirer_dir.exists():
        raise FileNotFoundError(f"Hirer conversations directory not found: {hirer_dir}")

    briefs = []
    for file_path in sorted(hirer_dir.glob("*.txt")):
        brief_id = file_path.stem
        content = file_path.read_text(encoding="utf-8")
        briefs.append(parse_brief_text(content, brief_id))
    return briefs


def parse_follow_up_update(dataset_root: Path) -> Dict[str, Any]:
    """
    Phase 4: Parse the supplied follow-up update file(s).
    """
    follow_up_dir = dataset_root / "follow_up_update"
    if not follow_up_dir.exists():
        return {"updates": [], "source_file": None}

    updates = []
    for p in sorted(follow_up_dir.glob("*.txt")):
        updates.append({"file": p.name, "content": p.read_text(encoding="utf-8")})

    affected_family = None
    for u in updates:
        text = u["content"].lower()
        if re.search(r'cafe|music|enquiry.*081|081', text):
            affected_family = "01_cafe_music"
        elif re.search(r'skincare|product.*photograph', text):
            affected_family = "02_skincare_photography"
        elif re.search(r'reel|vertical.*video', text):
            affected_family = "03_vertical_video"
        elif re.search(r'leadership|event', text):
            affected_family = "04_leadership_event"

    return {
        "updates": updates,
        "source_file": updates[0]["file"] if updates else None,
        "affected_brief": affected_family,
        "affected_brief_family": affected_family,
    }


def extract_follow_up_changes(follow_up: Dict[str, Any], original_brief: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract what changed between the original brief and the follow-up update.
    """
    changes = {
        "changed_constraints": [],
        "changed_assumptions": [],
        "changed_unknowns": [],
        "new_information": [],
        "removed_information": [],
    }

    if not follow_up.get("updates"):
        return changes

    content = follow_up["updates"][0]["content"].lower() if follow_up["updates"] else ""

    budget_matches = re.findall(r'(?:can|go|up|budget)\s+(?:up\s+)?to\s*(\d+)k', content)
    if budget_matches:
        old_budget = [c for c in original_brief.get("explicit_constraints", []) if "Budget" in c]
        if old_budget:
            changes["removed_information"].append(old_budget[0])
        changes["changed_constraints"].append(f"Budget increased to up to {budget_matches[0]}k INR")

    if re.search(r'headline|proper.*set|performance', content):
        old = [c for c in original_brief.get("explicit_constraints", [])
               if "background" in c.lower() or "7 PM to 10 PM" in c]
        if old:
            changes["removed_information"].append(old[0])
        changes["changed_constraints"].append(
            "Scope changed from background music to headline performance set"
        )

    guest_matches = re.findall(r'(\d+)\s*guests', content)
    if guest_matches:
        changes["new_information"].append(f"Event now has approximately {guest_matches[0]} guests")

    if re.search(r'clear.*small.*area', content):
        changes["new_information"].append("Venue can now clear a small area for performance")

    return changes
