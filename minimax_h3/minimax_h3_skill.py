"""Build self-contained MiniMax H3 guidance for LLM text payloads.

The source skill is stored as a small directory containing a SKILL.md file and
two reference documents.  LLM calls in this application receive one text
payload and cannot resolve the relative paths mentioned by SKILL.md.  This
module keeps the source documents unchanged while converting their file-based
references into explicit, in-payload section references.
"""

from __future__ import annotations

from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
MINIMAX_H3_SKILL_DIR = _PROJECT_ROOT / "api_production" / "AGENT-SKILLS" / "MINIMAX-H3"

_SKILL_PATH = MINIMAX_H3_SKILL_DIR / "SKILL.md"
_BASE_GUIDE_PATH = MINIMAX_H3_SKILL_DIR / "references" / "base-en.txt"
_FULL_REFERENCE_GUIDE_PATH = MINIMAX_H3_SKILL_DIR / "references" / "ref-en.txt"

COMMON_SECTION_OPERATIONAL = "MINIMAX H3 OPERATIONAL RULES"
COMMON_SECTION_BASE = "MINIMAX H3 BASE-MODE GUIDE"
COMMON_SECTION_FULL_REFERENCE = "MINIMAX H3 FULL-REFERENCE GUIDE"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _normalize_skill_text(text: str) -> str:
    """Make SKILL.md self-contained when embedded in a single text payload."""
    text = text.replace(
        "Portable to any agent that can read local files; no external API calls, MiniMax Hub tools, or proprietary runtime are required.",
        "These instructions are self-contained in this payload. No local file access, external API call, MiniMax Hub tool, or proprietary runtime is required.",
    )
    text = text.replace(
        "The optional `agents/openai.yaml` only provides UI metadata.",
        "Optional UI metadata is not part of these prompt-writing rules and is omitted from this payload.",
    )
    text = text.replace(
        "For base text/keyframe modes, read `references/base-en.txt` and follow its final prompt structure.",
        f"For base text/keyframe modes, apply the `{COMMON_SECTION_BASE}` section included below and follow its final prompt structure.",
    )
    text = text.replace(
        "For full-reference mode, read `references/ref-en.txt` and follow its six-section rewrite format.",
        f"For full-reference mode, apply the `{COMMON_SECTION_FULL_REFERENCE}` section included below and follow its six-section rewrite format.",
    )
    text = text.replace(
        "Use `integrated_multimodal_description`, `overall_soundscape`, and `non_diegetic_music` in the order shown in `references/base-en.txt`.",
        f"Use `integrated_multimodal_description`, `overall_soundscape`, and `non_diegetic_music` in the order defined by the `{COMMON_SECTION_BASE}` section included below.",
    )
    text = text.replace(
        "Read `references/ref-en.txt` for label rules, retention analysis, and complete examples.",
        f"Apply the `{COMMON_SECTION_FULL_REFERENCE}` section included below for label rules, retention analysis, and complete examples.",
    )
    return text


def _normalize_base_guide_text(text: str) -> str:
    """Mark the base guide as an explicit payload section."""
    return text.replace(
        "# Video Prompt Writing Guide (T2VA / I2VA / FL2VA / L2VA)",
        "# MiniMax H3 Base-Mode Guide (T2VA / I2VA / FL2VA / L2VA)",
        1,
    )


def _normalize_full_reference_guide_text(text: str) -> str:
    """Replace cross-file references in the full-reference guide."""
    text = text.replace(
        "The basic formats for shots, camera movement, speakers, dialogue, and ordinary sound are shared with the Video Prompt Writing Guide (T2VA / I2VA / FL2VA / L2VA). This guide focuses on the reference labels, analysis sections, and format differences specific to full-reference mode.",
        f"The basic formats for shots, camera movement, speakers, dialogue, and ordinary sound follow the `{COMMON_SECTION_BASE}` section included in this payload. This guide focuses on the reference labels, analysis sections, and format differences specific to full-reference mode.",
    )
    text = text.replace(
        "The basic format follows the Video Prompt Writing Guide (T2VA / I2VA / FL2VA / L2VA):",
        f"The basic format follows the `{COMMON_SECTION_BASE}` section included in this payload:",
    )
    text = text.replace(
        "For complete rules and examples covering camera vocabulary, group speech, voice-over, dialogue across cuts, and visible text, see the Video Prompt Writing Guide (T2VA / I2VA / FL2VA / L2VA).",
        f"For complete rules and examples covering camera vocabulary, group speech, voice-over, dialogue across cuts, and visible text, apply the `{COMMON_SECTION_BASE}` section included above.",
    )
    text = text.replace(
        "The definitions of these two sound categories follow the Video Prompt Writing Guide (T2VA / I2VA / FL2VA / L2VA).",
        f"The definitions of these two sound categories follow the sound rules in the `{COMMON_SECTION_BASE}` section included above.",
    )
    return text


def load_minimax_h3_common_sections() -> dict[str, str]:
    """Load and normalize the three common MiniMax H3 guidance documents."""
    return {
        COMMON_SECTION_OPERATIONAL: _normalize_skill_text(_read_text(_SKILL_PATH)),
        COMMON_SECTION_BASE: _normalize_base_guide_text(_read_text(_BASE_GUIDE_PATH)),
        COMMON_SECTION_FULL_REFERENCE: _normalize_full_reference_guide_text(
            _read_text(_FULL_REFERENCE_GUIDE_PATH)
        ),
    }


def build_minimax_h3_common_guidance() -> str:
    """Return all common MiniMax H3 guidance as one self-contained block."""
    sections = load_minimax_h3_common_sections()
    lines = []
    for title in (
        COMMON_SECTION_OPERATIONAL,
        COMMON_SECTION_BASE,
        COMMON_SECTION_FULL_REFERENCE,
    ):
        lines.extend([
            f"=== {title} ===",
            sections[title].strip(),
            f"=== END {title} ===",
            "",
        ])
    return "\n".join(lines).strip()


def is_minimax_h3_scene_type(scene_type: str) -> bool:
    """Return whether a scene uses the MiniMax H3 prompt architecture."""
    return str(scene_type or "").strip().lower().startswith("minimax-h3_")

