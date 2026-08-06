import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEMINI_VOICE_PROFILE_DIR = ROOT / "gemini_voice_profile"
VOICE_PROVIDER_GEMINI = "gemini"
VOICE_PROVIDER_ELEVENLABS = "elevenlabs"
VOICE_PROVIDER_OPTIONS = [
    ("Gemini (gemini-3.1-flash-tts-preview)", VOICE_PROVIDER_GEMINI),
    ("ElevenLabs (eleven_v3)", VOICE_PROVIDER_ELEVENLABS),
]
DEFAULT_PROJECT_VOICE_CONFIG = {
    "voice_provider": VOICE_PROVIDER_GEMINI,
}
DEFAULT_SCENE_VOICE_KEY = "yetty"
SCENE_VOICE_OPTIONS = [
    ("Yetty (narasi)", "yetty"),
    ("Nilasari (media sosial)", "nilasari"),
    ("Dany Saputra (narasi)", "dany_saputra"),
    ("Dakocan (media sosial)", "dakocan"),
    ("Candy (anak perempuan bersemangat)", "candy"),
    ("Lily (anak perempuan kalem)", "lily"),
    ("Lily - Ngaji", "lily_ngaji"),
    ("Finn (anak laki-laki bersemangat)", "finn"),
    ("Kevin (anak laki-laki kalem)", "kevin"),
]
VOICE_CHARACTER_MAP = {
    "yetty": {
        "display_name": "Yetty",
        "profile_file": "Yetty.txt",
        "elevenlabs_voice_id": "Lpe7uP03WRpCk9XkpFnf",
        "gemini_profile_text": "Super Smooth Indonesian Voice, Young Adult Friendly Smart Fun Deep for Narration",
    },
    "nilasari": {
        "display_name": "Nilasari",
        "profile_file": "Nilasari.txt",
        "elevenlabs_voice_id": "NPDHDOOQCSyifTJZOe6J",
        "gemini_profile_text": "Indonesian voice over with clear articulation and natural tone.",
    },
    "dany_saputra": {
        "display_name": "Dany Saputra",
        "profile_file": "Dany Saputra.txt",
        "elevenlabs_voice_id": "x5tvfc5X0Qh4cqmLpgrs",
        "gemini_profile_text": "Indonesian voice with warm energy and strong narrative for storytelling and historical stories.",
    },
    "dakocan": {
        "display_name": "Dakocan",
        "profile_file": "Dakocan.txt",
        "elevenlabs_voice_id": "plgKUYgnlZ1DCNh54DwJ",
        "gemini_profile_text": "An Indonesian young adult male voice with casual tone. Applicable for podcast, casual voice over and storytelling.",
    },
    "candy": {
        "display_name": "Candy",
        "profile_file": "Candy.txt",
        "elevenlabs_voice_id": "Nggzl2QAXh3OijoXD116",
        "gemini_profile_text": "7 years old Indonesian youthful, cute, sassy, energetic, bubbly, expressive, high pitched, excited, happy, sparkly, giggly, whimsical, bright, cheerful, playful, cartoony, fun, lighthearted, kawaii",
    },
    "lily": {
        "display_name": "Lily",
        "profile_file": "Lily.txt",
        "elevenlabs_voice_id": "Pt5YrLNyu6d2s3s4CVMg",
        "gemini_profile_text": "7 years old Indonesian youthful female voice with a soft and cute tone. Perfect for animated characters and storytelling. Ideal for bringing warmth and sweetness to playful or gentle characters.",
    },
    "lily_ngaji": {
        "display_name": "Lily - Ngaji",
        "profile_file": "Lily - Ngaji.txt",
        "elevenlabs_voice_id": "Pt5YrLNyu6d2s3s4CVMg",
        "gemini_profile_text": "Soft, clear, youthful female Quran reciter with a gentle and beautiful tone. Melodious Quranic tilawah with a gentle murattal style and light Maqam Bayati-inspired melodic contour. Use clear makhraj, tajwid-aware pronunciation, smooth connected phrasing, tasteful melodic rises and falls, and very short natural pauses between ayahs. Keep the recitation flowing and devotional, not like ordinary speech or a pop song. Do not add instruments, background music, harmony, chorus, echo, or sound effects. Recite exactly the Arabic text provided.",
    },
    "finn": {
        "display_name": "Finn",
        "profile_file": "Finn.txt",
        "elevenlabs_voice_id": "vBKc2FfBKJfcZNyEt1n6",
        "gemini_profile_text": "7 years old Indonesian youthful, a well-connected, young conversational male that's perfect for podcasting or casual conversations.",
    },
    "kevin": {
        "display_name": "Kevin",
        "profile_file": "Kevin.txt",
        "elevenlabs_voice_id": "aVwphcJSEW1eYLC622Ru",
        "gemini_profile_text": "7 years old Indonesian youthful, a deep, slightly husky voice with a groggy quality, as if it's just been woken up. The tone is rich and gravelly, carrying a warm and relaxed undertone that hints at the early morning hours.",
    },
}


def normalize_provider(value: str) -> str:
    provider = str(value or "").strip().lower()
    if provider in {VOICE_PROVIDER_GEMINI, VOICE_PROVIDER_ELEVENLABS}:
        return provider
    return VOICE_PROVIDER_GEMINI


def normalize_voice_key(value: str) -> str:
    key = str(value or "").strip().lower()
    if key in VOICE_CHARACTER_MAP:
        return key
    return DEFAULT_SCENE_VOICE_KEY


def resolve_scene_voice_key(scene_meta: dict) -> str:
    if not isinstance(scene_meta, dict):
        return DEFAULT_SCENE_VOICE_KEY
    raw = str(scene_meta.get("voice_character", "")).strip().lower()
    if raw in VOICE_CHARACTER_MAP:
        return raw
    legacy_profile = str(scene_meta.get("gemini_tts_profile", "")).strip().lower()
    legacy_map = {
        "male_adult": "yetty",
        "female_adult": "nilasari",
        "male_child": "finn",
        "female_child": "candy",
    }
    if legacy_profile in legacy_map:
        return legacy_map[legacy_profile]
    return DEFAULT_SCENE_VOICE_KEY


def get_voice_character(voice_key: str) -> dict:
    key = normalize_voice_key(voice_key)
    voice = copy.deepcopy(VOICE_CHARACTER_MAP[key])
    profile_file = str(voice.get("profile_file", "")).strip()
    if profile_file:
        profile_path = GEMINI_VOICE_PROFILE_DIR / profile_file
        try:
            if profile_path.exists():
                profile_text = profile_path.read_text(encoding="utf-8").strip()
                if profile_text:
                    voice["gemini_profile_text"] = profile_text
        except OSError:
            pass
    return voice
