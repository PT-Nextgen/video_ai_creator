import copy
import json
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QProcess, Qt, QUrl, QTimer, Signal
from PySide6.QtGui import QAction, QDesktopServices, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QInputDialog,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QPlainTextEdit, QSpinBox, QSplitter, QStackedWidget, QTabWidget, QTextEdit, QToolButton,
    QToolBar, QVBoxLayout, QWidget, QStyle, QSizePolicy,
)
from scripts.server_config import load_server_config, save_server_config
from wan22_i2v.wan22_i2v import DEFAULT_PROMPT as DEFAULT_WAN_PROMPT
from wan22_i2v.wan22_i2v import SIZE_OPTIONS as WAN_SIZE_OPTIONS
from wan22_i2v.wan22_i2v import STEP_OPTIONS as WAN_STEP_OPTIONS
from wan22_i2v.wan22_i2v import WAN_DURATION_OPTIONS
from wan22_i2v.wan22_i2v import get_step_template_name as get_wan_step_template_name
from wan22_i2v.wan22_i2v import get_template_name as get_wan_template_name
from wan22_s2v.wan22_s2v import DEFAULT_PROMPT as DEFAULT_WAN22_S2V_PROMPT
from wan22_s2v.wan22_s2v import MAX_AUDIO_DURATION as WAN22_S2V_MAX_AUDIO_DURATION
from wan22_s2v.wan22_s2v import SIZE_OPTIONS as WAN22_S2V_SIZE_OPTIONS
from wan22_s2v.wan22_s2v import get_audio_duration as get_wan22_s2v_audio_duration
from flux2.flux2 import MODEL_FLUX2
from z_image.z_image import IMAGE_MODEL_OPTIONS, MODEL_Z_IMAGE_TURBO
from z_image.z_image import DEFAULT_PROMPT as DEFAULT_Z_IMAGE_PROMPT
from z_image.z_image import SIZE_OPTIONS as Z_IMAGE_SIZES
from z_image.z_image import get_model_key as get_z_image_model_key
from z_image.z_image import supports_negative_prompt as z_image_supports_negative_prompt
from z_image.z_image import get_template_name as get_z_image_template_name
from gemini.gemini_image import MODEL_GEMINI_IMAGE, MODEL_GEMINI_FLASH_05K, list_gemini_image_models
from prompt_localization import convert_prompt_payload_for_ui, prepare_prompt_payload_for_save, read_json_for_runtime

ROOT = Path(__file__).resolve().parent
API_PRODUCTION = ROOT / "api_production"
MUSIC_DIR = ROOT / "music"
MAIN_SCRIPT = ROOT / "main.py"
INITIAL_IMAGE_SCRIPT = ROOT / "scripts" / "generate_initial_image.py"
IMAGE_EDIT_SCRIPT = ROOT / "scripts" / "generate_image_edit.py"
COVER_IMAGE_SCRIPT = ROOT / "scripts" / "generate_cover_image.py"
VOICE_SCRIPT = ROOT / "scripts" / "generate_voice.py"
SOUND_SCRIPT = ROOT / "scripts" / "generate_sound.py"
CAPTION_SCRIPT = ROOT / "scripts" / "generate_caption.py"
COMPOSE_SCRIPT = ROOT / "scripts" / "generate_compose.py"
BACKUP_SCRIPT = ROOT / "backup_production.py"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".avi", ".mkv"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
ARCHIVE_EXTS = {".zip"}
ELEVENLABS_VOICES = [
    ("Yetty Indonesia", "Lpe7uP03WRpCk9XkpFnf"),
    ("Iwan Indonesia", "1kNciG1jHVSuFBPoxdRZ"),
    ("Kira", "gmnazjXOFoOcWA59sd5m"),
    ("Livna", "GdyFAZdMpKMBHw5pc1Bu"),
    ("Zan", "zmqLb9Ysr8fUvDD7hXK8"),
]
ELEVENLABS_MODEL_ID = "eleven_v3"
ELEVENLABS_MODEL_OPTIONS = [
    ("Eleven v3", "eleven_v3"),
    ("Eleven Multilingual v2", "eleven_multilingual_v2"),
    ("Eleven Flash v2.5", "eleven_flash_v2_5"),
]
EDGETTS_VOICES = [
    ("[Indonesian] id-ID Ardi", "[Indonesian] id-ID Ardi"),
    ("[Indonesian] id-ID Gadis", "[Indonesian] id-ID Gadis"),
]

DEFAULT_SCENE_META = {
    "scene_title": "", "duration_seconds": 10, "voice_text": "",
    "voice_provider": "elevenlabs", "elevenlabs_voice_id": "",
    "elevenlabs_model_id": ELEVENLABS_MODEL_ID,
    "generate_caption": True,
    "edgetts_voice_id": "", "sound_prompt": "", "sound_volume": "",
    "scene_type": "default",
}
DEFAULT_WEB_SCROLL_PROMPT = {
    "url": "",
    "width": 368,
    "height": 640,
    "duration_seconds": 5.0,
    "speed": 1,
    "capture_mode": "live_capture",
}
DEFAULT_IMAGE_PAN_PROMPT = {
    "width": 480,
    "height": 848,
    "direction": "from_right",
    "capture_mode": "live_capture",
}
DEFAULT_IMAGE_EDIT_PROMPT = {
    "image_model": MODEL_FLUX2,
    "gemini_model_id": MODEL_GEMINI_FLASH_05K,
    "groups": [
        {"source_image": "", "prompt": ""},
        {"source_image": "", "prompt": ""},
        {"source_image": "", "prompt": ""},
    ],
}
DEFAULT_Z_IMAGE_EXTRA_PROMPTS = {
    "groups": [
        {"positive_prompt": "", "negative_prompt": ""},
        {"positive_prompt": "", "negative_prompt": ""},
        {"positive_prompt": "", "negative_prompt": ""},
    ],
}


def load_json(path: Path, default: dict):
    if not path.exists():
        return copy.deepcopy(default)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    merged = copy.deepcopy(default)
    merged.update(data)
    return convert_prompt_payload_for_ui(path.name, merged)


def write_json(path: Path, data: dict):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_prompt_json(path: Path, data: dict):
    existing_data = None
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception:
            existing_data = None
    payload = prepare_prompt_payload_for_save(path.name, data, existing_data=existing_data)
    write_json(path, payload)


def scene_dir_name(index: int) -> str:
    return f"scene_{index}"


def list_scene_dirs_in_project(project_dir: Path | None):
    if project_dir is None:
        return []
    if not project_dir.exists() or not project_dir.is_dir():
        return []
    scenes = []
    for child in project_dir.iterdir():
        if child.is_dir() and child.name.startswith("scene_"):
            try:
                scenes.append((int(child.name.split("_", 1)[1]), child))
            except ValueError:
                pass
    scenes.sort(key=lambda item: item[0])
    return [path for _, path in scenes]


def list_output_files(directory: Path):
    if not directory.exists():
        return {}
    outputs = {}
    for child in directory.iterdir():
        if child.is_file() and child.suffix.lower() in (IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS | ARCHIVE_EXTS):
            try:
                outputs[str(child.resolve())] = child.stat().st_mtime
            except OSError:
                continue
    return outputs


def build_scene_templates(title: str, scene_type: str, duration: int):
    meta = copy.deepcopy(DEFAULT_SCENE_META)
    meta["scene_title"] = title
    meta["scene_type"] = scene_type
    meta["duration_seconds"] = duration
    return (
        meta,
        copy.deepcopy(DEFAULT_Z_IMAGE_PROMPT),
        copy.deepcopy(DEFAULT_WAN_PROMPT),
        copy.deepcopy(DEFAULT_WAN22_S2V_PROMPT),
        copy.deepcopy(DEFAULT_WEB_SCROLL_PROMPT),
        copy.deepcopy(DEFAULT_IMAGE_PAN_PROMPT),
    )


def create_scene_files(
    scene_dir: Path,
    meta=None,
    z_prompt=None,
    wan_prompt=None,
    wan22_s2v_prompt=None,
    web_scroll_prompt=None,
    image_pan_prompt=None,
    image_edit_prompt=None,
    z_image_extra_prompts=None,
):
    scene_dir.mkdir(parents=True, exist_ok=True)
    resolved_meta = copy.deepcopy(DEFAULT_SCENE_META)
    if isinstance(meta, dict):
        resolved_meta.update(meta)
    scene_type = str(resolved_meta.get("scene_type", "default")).strip()
    write_prompt_json(scene_dir / "scene_meta.json", resolved_meta)
    sync_scene_prompt_files(
        scene_dir,
        scene_type=scene_type,
        z_prompt=z_prompt or DEFAULT_Z_IMAGE_PROMPT,
        wan_prompt=wan_prompt or DEFAULT_WAN_PROMPT,
        s2v_prompt=wan22_s2v_prompt or DEFAULT_WAN22_S2V_PROMPT,
        web_prompt=web_scroll_prompt or DEFAULT_WEB_SCROLL_PROMPT,
        image_pan_prompt=image_pan_prompt or DEFAULT_IMAGE_PAN_PROMPT,
        image_edit_prompt=image_edit_prompt or DEFAULT_IMAGE_EDIT_PROMPT,
        z_image_extra_prompts=z_image_extra_prompts or DEFAULT_Z_IMAGE_EXTRA_PROMPTS,
    )


def sync_scene_prompt_files(
    scene_dir: Path,
    scene_type: str,
    z_prompt: dict,
    wan_prompt: dict,
    s2v_prompt: dict,
    web_prompt: dict,
    image_pan_prompt: dict,
    image_edit_prompt: dict | None = None,
    z_image_extra_prompts: dict | None = None,
):
    """Ensure prompt JSON files exist according to selected scene type.

    Rules:
    - z_image_prompt.json: always present
    - wan22_i2v_prompt.json: only for default/wan22/wan22_i2v
    - wan22_s2v_prompt.json: always present (used when switching to s2v later)
    """
    write_prompt_json(scene_dir / "z_image_prompt.json", z_prompt or DEFAULT_Z_IMAGE_PROMPT)
    write_prompt_json(scene_dir / "wan22_s2v_prompt.json", s2v_prompt or DEFAULT_WAN22_S2V_PROMPT)
    write_prompt_json(scene_dir / "web_scroll_prompt.json", web_prompt or DEFAULT_WEB_SCROLL_PROMPT)
    write_prompt_json(scene_dir / "image_pan_prompt.json", image_pan_prompt or DEFAULT_IMAGE_PAN_PROMPT)
    write_prompt_json(scene_dir / "image_edit_prompt.json", image_edit_prompt or DEFAULT_IMAGE_EDIT_PROMPT)
    write_prompt_json(scene_dir / "z_image_extra_prompts.json", z_image_extra_prompts or DEFAULT_Z_IMAGE_EXTRA_PROMPTS)

    wan_required_types = {"default", "wan22", "wan22_i2v"}
    wan_path = scene_dir / "wan22_i2v_prompt.json"
    if scene_type in wan_required_types:
        write_prompt_json(wan_path, wan_prompt or DEFAULT_WAN_PROMPT)
    elif wan_path.exists():
        wan_path.unlink()


def duplicate_directory(src: Path, dst: Path):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def find_latest_asset(scene_dir: Path, exts: set[str]):
    if not scene_dir.exists():
        return None
    items = [p for p in scene_dir.iterdir() if p.is_file() and p.suffix.lower() in exts]
    if not items:
        return None
    items.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return items[0]


def find_latest_speech_asset(scene_dir: Path):
    audio_exts = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
    if not scene_dir.exists():
        return None
    items = [
        p for p in scene_dir.iterdir()
        if p.is_file() and p.suffix.lower() in audio_exts and p.name.startswith("speech_")
    ]
    if not items:
        return None
    items.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return items[0]


def _is_valid_web_url(value: str):
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_one_decimal_step(value: float):
    return abs((value * 10.0) - round(value * 10.0)) < 1e-9


def validate_scene_data(
    meta: dict,
    z_prompt: dict,
    wan_prompt: dict,
    s2v_prompt: dict | None = None,
    web_prompt: dict | None = None,
    image_pan_prompt: dict | None = None,
    scene_dir: Path | None = None,
):
    issues = []
    scene_type = str(meta.get("scene_type", "default")).strip()
    s2v_prompt = s2v_prompt or DEFAULT_WAN22_S2V_PROMPT
    web_prompt = web_prompt or DEFAULT_WEB_SCROLL_PROMPT
    image_pan_prompt = image_pan_prompt or DEFAULT_IMAGE_PAN_PROMPT
    image_model_key = get_z_image_model_key(z_prompt)
    is_gemini_image = image_model_key == MODEL_GEMINI_IMAGE
    if not str(meta.get("scene_title", "")).strip():
        issues.append("Judul adegan wajib diisi.")
    try:
        if scene_type not in {"wan22_s2v", "web_scroll"} and int(meta.get("duration_seconds", 0)) <= 0:
            issues.append("Durasi harus lebih besar dari 0.")
    except Exception:
        if scene_type not in {"wan22_s2v", "web_scroll"}:
            issues.append("Durasi harus berupa angka.")
    if scene_type == "default":
        if not str(z_prompt.get("positive_prompt", "")).strip():
            issues.append("Prompt positif gambar awal wajib diisi.")
        if not is_gemini_image and not z_prompt.get("use_random_seed", True):
            try:
                if int(z_prompt.get("seed", 0)) <= 0:
                    issues.append("Seed statik harus berupa bilangan bulat positif.")
            except Exception:
                issues.append("Seed statik harus berupa bilangan bulat positif.")
        if not is_gemini_image and z_prompt.get("use_lora"):
            if not str(z_prompt.get("lora_name", "")).strip():
                issues.append("Nama Lora wajib diisi saat Lora digunakan.")
            try:
                if float(z_prompt.get("strength_model", 0)) <= 0:
                    issues.append("Kekuatan Lora harus berupa bilangan desimal positif.")
            except Exception:
                issues.append("Kekuatan Lora harus berupa bilangan desimal positif.")
        if not str(wan_prompt.get("positive_prompt_one", "")).strip():
            issues.append("Prompt positif WAN pertama wajib diisi.")
        if wan_prompt.get("use_lora"):
            if not str(wan_prompt.get("lora_high_name", "")).strip():
                issues.append("Nama Lora High WAN wajib diisi saat Lora digunakan.")
            if not str(wan_prompt.get("lora_low_name", "")).strip():
                issues.append("Nama Lora Low WAN wajib diisi saat Lora digunakan.")
            try:
                if float(wan_prompt.get("lora_high_strength", 0)) <= 0:
                    issues.append("Kekuatan Lora High WAN harus berupa bilangan desimal positif.")
            except Exception:
                issues.append("Kekuatan Lora High WAN harus berupa bilangan desimal positif.")
            try:
                if float(wan_prompt.get("lora_low_strength", 0)) <= 0:
                    issues.append("Kekuatan Lora Low WAN harus berupa bilangan desimal positif.")
            except Exception:
                issues.append("Kekuatan Lora Low WAN harus berupa bilangan desimal positif.")
    if scene_type in {"wan22", "wan22_i2v"}:
        if not str(wan_prompt.get("positive_prompt_one", "")).strip():
            issues.append("Prompt positif WAN pertama wajib diisi.")
        if scene_dir and not find_latest_asset(scene_dir, IMAGE_EXTS):
            issues.append("Adegan WAN membutuhkan minimal satu gambar lokal di folder scene.")
    if scene_type == "wan22_s2v":
        if scene_dir and not find_latest_asset(scene_dir, IMAGE_EXTS):
            issues.append("Adegan WAN22 S2V membutuhkan minimal satu gambar di root folder scene.")
        if not str(meta.get("voice_provider", "")).strip():
            issues.append("Penyedia suara wajib dipilih untuk WAN22 S2V.")
        if not str(meta.get("voice_text", "")).strip():
            issues.append("Teks suara wajib diisi untuk WAN22 S2V.")
        speech_asset = find_latest_speech_asset(scene_dir) if scene_dir else None
        if scene_dir and not speech_asset:
            issues.append("Adegan WAN22 S2V membutuhkan minimal satu file audio speech yang berawalan `speech_` di root folder scene.")
        elif speech_asset:
            try:
                duration = get_wan22_s2v_audio_duration(str(speech_asset))
            except Exception:
                issues.append("Durasi audio speech WAN22 S2V tidak dapat dibaca. Pastikan `ffprobe` tersedia dan file audionya valid.")
            else:
                if duration >= WAN22_S2V_MAX_AUDIO_DURATION:
                    issues.append(f"Durasi audio speech WAN22 S2V harus kurang dari {WAN22_S2V_MAX_AUDIO_DURATION} detik.")
    if scene_type == "web_scroll":
        url = str(web_prompt.get("url", "")).strip()
        if not url:
            issues.append("URL website wajib diisi untuk adegan web_scroll.")
        elif not _is_valid_web_url(url):
            issues.append("Format URL website tidak valid. Gunakan URL dengan http:// atau https://")
        try:
            duration_value = float(web_prompt.get("duration_seconds", -1))
        except Exception:
            issues.append("Durasi web_scroll harus berupa angka desimal 0.0 sampai 20.0 dengan 1 angka di belakang koma.")
        else:
            if duration_value < 0 or duration_value > 20:
                issues.append("Durasi web_scroll harus di antara 0.0 sampai 20.0 detik.")
            elif not _is_one_decimal_step(duration_value):
                issues.append("Durasi web_scroll harus kelipatan 0.1 detik (1 angka di belakang koma).")
        try:
            speed_value = int(web_prompt.get("speed", 0))
        except Exception:
            issues.append("Speed web_scroll harus berupa bilangan bulat positif dari 1 sampai 5.")
        else:
            if speed_value < 1 or speed_value > 5:
                issues.append("Speed web_scroll harus di antara 1 sampai 5.")
        capture_mode = str(web_prompt.get("capture_mode", "live_capture")).strip()
        if capture_mode not in {"stable_pan", "live_capture"}:
            issues.append("Mode web_scroll tidak valid. Pilih `stable_pan` atau `live_capture`.")
    if scene_type == "image_pan":
        if scene_dir and not find_latest_asset(scene_dir, IMAGE_EXTS):
            issues.append("Adegan image_pan membutuhkan satu gambar awal di folder scene.")
        try:
            pan_width = int(image_pan_prompt.get("width", DEFAULT_IMAGE_PAN_PROMPT["width"]))
            pan_height = int(image_pan_prompt.get("height", DEFAULT_IMAGE_PAN_PROMPT["height"]))
        except Exception:
            pan_width = 0
            pan_height = 0
        if pan_width <= 0 or pan_height <= 0:
            issues.append("Ukuran image_pan tidak valid.")
        elif pan_height <= pan_width:
            issues.append("Ukuran image_pan harus portrait (tinggi lebih besar dari lebar).")
        pan_direction = str(image_pan_prompt.get("direction", "from_right")).strip()
        if pan_direction not in {"from_right", "from_left"}:
            issues.append("Arah image_pan tidak valid. Pilih `from_right` atau `from_left`.")
        pan_mode = str(image_pan_prompt.get("capture_mode", "live_capture")).strip()
        if pan_mode not in {"stable_pan", "live_capture"}:
            issues.append("Mode image_pan tidak valid. Pilih `stable_pan` atau `live_capture`.")
    if scene_type == "i2v" and scene_dir and not find_latest_asset(scene_dir, IMAGE_EXTS):
        issues.append("Adegan i2v membutuhkan minimal satu gambar lokal di folder scene.")
    provider = str(meta.get("voice_provider", "")).strip()
    if provider == "elevenlabs":
        if not str(meta.get("voice_text", "")).strip():
            issues.append("Teks suara wajib diisi untuk ElevenLabs.")
        if not str(meta.get("elevenlabs_voice_id", "")).strip():
            issues.append("ID suara ElevenLabs wajib diisi.")
    if provider == "edgetts":
        if not str(meta.get("voice_text", "")).strip():
            issues.append("Teks suara wajib diisi untuk EdgeTTS.")
        if not str(meta.get("edgetts_voice_id", "")).strip():
            issues.append("ID suara EdgeTTS wajib diisi.")
    return issues


class SceneListWidget(QListWidget):
    orderChanged = Signal()

    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)

    def dropEvent(self, event):
        super().dropEvent(event)
        self.orderChanged.emit()


class SceneTemplateDialog(QDialog):
    def __init__(self, parent=None, title="Tambah Adegan"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.title_input = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems(["default", "wan22_i2v", "wan22_s2v", "i2v", "web_scroll", "image_pan"])
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 3600)
        self.duration_spin.setValue(10)
        form = QFormLayout(self)
        form.addRow("Judul Adegan", self.title_input)
        form.addRow("Tipe Adegan", self.type_combo)
        form.addRow("Durasi (detik)", self.duration_spin)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.type_combo.currentTextChanged.connect(self.update_fields_for_scene_type)
        self.update_fields_for_scene_type(self.type_combo.currentText())

    def update_fields_for_scene_type(self, scene_type: str):
        self.duration_spin.setEnabled(scene_type not in {"wan22_s2v", "web_scroll"})

    def get_data(self):
        return {
            "scene_title": self.title_input.text().strip(),
            "scene_type": self.type_combo.currentText(),
            "duration_seconds": self.duration_spin.value(),
        }


class ServerConfigDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Konfigurasi Server")
        self.comfyui_host_input = QLineEdit(str(config.get("comfyui", {}).get("host", "")))
        self.comfyui_port_input = QLineEdit(str(config.get("comfyui", {}).get("port", "")))
        self.audio_host_input = QLineEdit(str(config.get("audio", {}).get("host", "")))
        self.audio_port_input = QLineEdit(str(config.get("audio", {}).get("port", "")))

        form = QFormLayout(self)
        form.addRow("Host / IP ComfyUI", self.comfyui_host_input)
        form.addRow("Port ComfyUI", self.comfyui_port_input)
        form.addRow("Host / IP Audio", self.audio_host_input)
        form.addRow("Port Audio", self.audio_port_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def get_config(self):
        comfyui_host = self.comfyui_host_input.text().strip()
        audio_host = self.audio_host_input.text().strip()
        if not comfyui_host:
            raise ValueError("Host / IP ComfyUI wajib diisi.")
        if not audio_host:
            raise ValueError("Host / IP audio wajib diisi.")
        try:
            comfyui_port = int(self.comfyui_port_input.text().strip())
            audio_port = int(self.audio_port_input.text().strip())
        except ValueError as e:
            raise ValueError("Port server harus berupa angka.") from e
        if comfyui_port <= 0 or audio_port <= 0:
            raise ValueError("Port server harus lebih besar dari 0.")
        return {
            "comfyui": {"host": comfyui_host, "port": comfyui_port},
            "audio": {"host": audio_host, "port": audio_port},
        }


class ProcessDialog(QDialog):
    def __init__(self, log_widget, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Proses")
        self.resize(760, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Log Proses"))
        layout.addWidget(log_widget)


class ComposeMusicDialog(QDialog):
    def __init__(self, music_files: list[Path], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Music Compose")
        self.music_combo = QComboBox(self)
        self.music_combo.addItem("(Tanpa music)", "")
        for path in music_files:
            self.music_combo.addItem(path.name, str(path))

        self.volume_input = QDoubleSpinBox(self)
        self.volume_input.setRange(0.0, 2.0)
        self.volume_input.setDecimals(2)
        self.volume_input.setSingleStep(0.05)
        self.volume_input.setValue(1.00)

        layout = QFormLayout(self)
        layout.addRow("File Music", self.music_combo)
        layout.addRow("Volume (0.00 - 2.00)", self.volume_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self):
        return str(self.music_combo.currentData() or "").strip(), float(self.volume_input.value())


class CoverPromptDialog(QDialog):
    def __init__(self, prompt_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Cover")
        self.resize(760, 760)

        self.model_input = QComboBox(self)
        for model_key, label in IMAGE_MODEL_OPTIONS:
            self.model_input.addItem(label, model_key)
        self.gemini_model_input = QComboBox(self)
        self.gemini_models = list_gemini_image_models()
        for model_id in self.gemini_models:
            self.gemini_model_input.addItem(model_id, model_id)

        self.size_input = QComboBox(self)
        for label, width, height in Z_IMAGE_SIZES:
            self.size_input.addItem(label, (width, height))

        self.use_random_seed_input = QCheckBox("Random Seed", self)
        self.seed_input = QLineEdit(self)
        self.use_lora_input = QCheckBox("Pakai Lora", self)
        self.lora_name_input = QLineEdit(self)
        self.lora_strength_input = QLineEdit(self)
        self.positive_input = QTextEdit(self)
        self.negative_input = QTextEdit(self)

        form = QFormLayout(self)
        form.addRow("Model", self.model_input)
        form.addRow("Model Gemini", self.gemini_model_input)
        form.addRow("Ukuran", self.size_input)
        form.addRow("", self.use_random_seed_input)
        form.addRow("Seed Statik", self.seed_input)
        form.addRow("", self.use_lora_input)
        form.addRow("Nama Lora", self.lora_name_input)
        form.addRow("Kekuatan Lora", self.lora_strength_input)
        form.addRow("Prompt Positif", self.positive_input)
        form.addRow("Prompt Negatif", self.negative_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self.use_random_seed_input.toggled.connect(self._update_seed_enabled)
        self.use_lora_input.toggled.connect(self._update_lora_enabled)
        self.model_input.currentIndexChanged.connect(self._update_model_fields)

        self._load_data(prompt_data or {})
        self._update_seed_enabled()
        self._update_lora_enabled()
        self._update_model_fields()

    def _load_data(self, data: dict):
        model_key = get_z_image_model_key(data)
        idx = self.model_input.findData(model_key)
        self.model_input.setCurrentIndex(max(idx, 0))

        width = int(data.get("width", DEFAULT_Z_IMAGE_PROMPT["width"]))
        height = int(data.get("height", DEFAULT_Z_IMAGE_PROMPT["height"]))
        size_idx = -1
        for i in range(self.size_input.count()):
            val = self.size_input.itemData(i)
            if isinstance(val, tuple) and val == (width, height):
                size_idx = i
                break
        self.size_input.setCurrentIndex(max(size_idx, 0))

        self.use_random_seed_input.setChecked(bool(data.get("use_random_seed", True)))
        self.seed_input.setText(str(data.get("seed", 1)))
        self.use_lora_input.setChecked(bool(data.get("use_lora", False)))
        self.lora_name_input.setText(str(data.get("lora_name", "")))
        self.lora_strength_input.setText(str(data.get("strength_model", 1.0)))
        self.positive_input.setPlainText(str(data.get("positive_prompt", "")))
        self.negative_input.setPlainText(str(data.get("negative_prompt", "")))
        selected_gemini_model = str(data.get("gemini_model_id", MODEL_GEMINI_FLASH_05K)).strip()
        idx = self.gemini_model_input.findData(selected_gemini_model)
        if idx < 0 and selected_gemini_model:
            self.gemini_model_input.addItem(selected_gemini_model, selected_gemini_model)
            idx = self.gemini_model_input.findData(selected_gemini_model)
        self.gemini_model_input.setCurrentIndex(max(idx, 0))

    def _update_seed_enabled(self):
        self.seed_input.setEnabled(not self.use_random_seed_input.isChecked())

    def _update_lora_enabled(self):
        enabled = self.use_lora_input.isChecked()
        self.lora_name_input.setEnabled(enabled)
        self.lora_strength_input.setEnabled(enabled)

    def _update_model_fields(self):
        model_key = str(self.model_input.currentData() or MODEL_Z_IMAGE_TURBO)
        can_use_negative = z_image_supports_negative_prompt({"image_model": model_key})
        self.negative_input.setEnabled(can_use_negative)
        if not can_use_negative:
            self.negative_input.setPlainText("")

        is_gemini = model_key == MODEL_GEMINI_IMAGE
        self.gemini_model_input.setVisible(is_gemini)
        label = self.layout().labelForField(self.gemini_model_input)
        if label is not None:
            label.setVisible(is_gemini)
        self.use_lora_input.setEnabled(not is_gemini)
        self.use_random_seed_input.setEnabled(not is_gemini)
        if is_gemini:
            self.use_lora_input.setChecked(False)
            self.use_random_seed_input.setChecked(True)
            self.seed_input.setText("1")
        self._update_seed_enabled()
        self._update_lora_enabled()

    def get_data(self):
        model_key = str(self.model_input.currentData() or MODEL_Z_IMAGE_TURBO)
        use_lora = self.use_lora_input.isChecked()
        use_random_seed = self.use_random_seed_input.isChecked()

        seed_val = 1
        if not use_random_seed:
            try:
                seed_val = int(self.seed_input.text().strip() or "1")
            except ValueError:
                raise ValueError("Seed statik harus berupa bilangan bulat positif.")
            if seed_val <= 0:
                raise ValueError("Seed statik harus berupa bilangan bulat positif.")

        lora_strength = 1.0
        if use_lora:
            try:
                lora_strength = float(self.lora_strength_input.text().strip() or "1.0")
            except ValueError:
                raise ValueError("Kekuatan Lora harus berupa bilangan desimal positif.")
            if lora_strength <= 0:
                raise ValueError("Kekuatan Lora harus berupa bilangan desimal positif.")

        data = {
            "image_model": model_key,
            "gemini_model_id": (
                str(self.gemini_model_input.currentData() or MODEL_GEMINI_FLASH_05K).strip()
                if model_key == MODEL_GEMINI_IMAGE
                else ""
            ),
            "positive_prompt": self.positive_input.toPlainText().strip(),
            "negative_prompt": (
                self.negative_input.toPlainText().strip()
                if z_image_supports_negative_prompt({"image_model": model_key})
                else ""
            ),
            "width": int((self.size_input.currentData() or (368, 640))[0]),
            "height": int((self.size_input.currentData() or (368, 640))[1]),
            "use_random_seed": use_random_seed,
            "seed": seed_val,
            "use_lora": use_lora,
            "lora_name": self.lora_name_input.text().strip() if use_lora else "",
            "strength_model": lora_strength,
        }
        data["json_api"] = get_z_image_template_name(data)
        if not data["positive_prompt"]:
            raise ValueError("Prompt positif cover wajib diisi.")
        if use_lora and not data["lora_name"]:
            raise ValueError("Nama Lora wajib diisi saat Lora digunakan.")
        return data


class MediaPreviewLabel(QLabel):
    activated = Signal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._source_pixmap = QPixmap()
        self._source_path = None
        self._suppress_release = False
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(220)
        self._click_timer.timeout.connect(self.activated.emit)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("border: 1px solid #d1d5db; background: #fafafa;")

    def set_preview_pixmap(self, pixmap: QPixmap):
        self._source_pixmap = pixmap
        self._refresh_scaled_pixmap()

    def clear_preview(self, text=""):
        self._source_pixmap = QPixmap()
        self._source_path = None
        self._suppress_release = False
        self._click_timer.stop()
        self.clear()
        if text:
            self.setText(text)

    def set_source_path(self, path):
        self._source_path = Path(path) if path else None

    def source_path(self):
        return self._source_path

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._suppress_release:
                self._suppress_release = False
                event.accept()
                return
            self._click_timer.start()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._click_timer.isActive():
                self._click_timer.stop()
            self._suppress_release = True
            self.activated.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_scaled_pixmap()

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(360, 240)

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(360, 240)

    def _refresh_scaled_pixmap(self):
        if self._source_pixmap.isNull():
            return
        target_size = self.contentsRect().size()
        if target_size.width() <= 1 or target_size.height() <= 1:
            return
        scaled = self._source_pixmap.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled)


class SceneEditorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pengelola Adegan")
        self.resize(1700, 980)
        self.current_project_name = ""
        self.current_scene_dir = None
        self.process = None
        self.process_context = None
        self.loading_scene = False
        self.editor_tabs = None
        self.meta_tab = None
        self.z_tab = None
        self.wan_tab = None
        self.s2v_tab = None
        self.web_tab = None
        self.image_edit_tab = None
        self.assets_tab = None
        self.generate_initial_image_button = None
        self.duration_label = None
        self.s2v_negative_label = None
        self.scene_list = SceneListWidget()
        self.scene_list.currentItemChanged.connect(self.on_scene_changed)
        self.scene_list.orderChanged.connect(self.on_scene_reordered)
        self.server_config = load_server_config()
        self.toolbar = None

        self.scene_title_input = QLineEdit()
        self.duration_input = QComboBox()
        for value in [5, 10, 15, 20, 25]:
            self.duration_input.addItem(str(value), value)
        self.scene_type_combo = QComboBox()
        self.scene_type_combo.addItems(["default", "wan22_i2v", "wan22_s2v", "i2v", "web_scroll", "image_pan"])
        self.voice_provider_combo = QComboBox()
        self.voice_provider_combo.addItems(["", "elevenlabs", "edgetts"])
        self.elevenlabs_voice_input = QComboBox()
        self.elevenlabs_voice_input.addItem("", "")
        for voice_name, voice_id in ELEVENLABS_VOICES:
            self.elevenlabs_voice_input.addItem(voice_name, voice_id)
        self.elevenlabs_model_input = QComboBox()
        for model_label, model_id in ELEVENLABS_MODEL_OPTIONS:
            self.elevenlabs_model_input.addItem(model_label, model_id)
        self.edgetts_voice_input = QComboBox()
        self.edgetts_voice_input.addItem("", "")
        for voice_name, voice_id in EDGETTS_VOICES:
            self.edgetts_voice_input.addItem(voice_name, voice_id)
        self.generate_caption_input = QCheckBox("Generate Caption")
        self.generate_caption_input.setChecked(True)
        self.voice_text_input = QTextEdit()
        self.sound_prompt_input = QTextEdit()
        self.sound_volume_input = QLineEdit()
        self.z_positive_input = QTextEdit()
        self.z_model_input = QComboBox()
        for model_key, label in IMAGE_MODEL_OPTIONS:
            self.z_model_input.addItem(label, model_key)
        self.z_gemini_model_input = QComboBox()
        self.z_gemini_model_ids = list_gemini_image_models()
        for model_id in self.z_gemini_model_ids:
            self.z_gemini_model_input.addItem(model_id, model_id)
        self.z_negative_input = QTextEdit()
        self.z_clipboard_button = QToolButton()
        self.z_clipboard_button.setText("Image Gen Prompt")
        self.z_clipboard_button.clicked.connect(self.copy_z_image_skill_prompt_to_clipboard)
        self.z_extra_positive_inputs = []
        self.z_extra_negative_inputs = []
        self.z_extra_clipboard_buttons = []
        self.z_extra_buttons = []
        self.z_size_input = QComboBox()
        for label, width, height in Z_IMAGE_SIZES:
            self.z_size_input.addItem(label, (width, height))
        self.z_use_random_seed_input = QCheckBox("Random Seed")
        self.z_use_random_seed_input.setChecked(True)
        self.z_seed_input = QLineEdit()
        self.z_use_lora_input = QCheckBox("Pakai Lora")
        self.z_lora_name_input = QLineEdit()
        self.z_lora_strength_input = QLineEdit()
        for slot_index in range(3):
            positive_input = QTextEdit()
            negative_input = QTextEdit()
            clipboard_button = QToolButton()
            clipboard_button.setText("Image Gen Prompt")
            clipboard_button.clicked.connect(
                lambda _checked=False, idx=slot_index: self.copy_extra_image_skill_prompt_to_clipboard(idx)
            )
            button = QToolButton()
            button.setText("Buat Image")
            button.clicked.connect(lambda _checked=False, idx=slot_index: self.run_extra_image_slot(idx))
            self.z_extra_positive_inputs.append(positive_input)
            self.z_extra_negative_inputs.append(negative_input)
            self.z_extra_clipboard_buttons.append(clipboard_button)
            self.z_extra_buttons.append(button)
        self.wan_step_combo = QComboBox()
        for label, template_name in WAN_STEP_OPTIONS:
            self.wan_step_combo.addItem(label, template_name)
        self.wan_duration_input = QComboBox()
        for label, duration_value in WAN_DURATION_OPTIONS:
            self.wan_duration_input.addItem(label, duration_value)
        self.wan_size_input = QComboBox()
        for label, width, height in WAN_SIZE_OPTIONS:
            self.wan_size_input.addItem(label, (width, height))
        self.wan_use_lora_input = QCheckBox("Pakai Lora")
        self.wan_lora_high_name_input = QLineEdit()
        self.wan_lora_high_strength_input = QLineEdit()
        self.wan_lora_low_name_input = QLineEdit()
        self.wan_lora_low_strength_input = QLineEdit()
        self.wan_prompt_inputs = {}
        for key in [
            "positive_prompt_one", "negative_prompt_one", "positive_prompt_two", "negative_prompt_two",
            "positive_prompt_three", "negative_prompt_three",
        ]:
            self.wan_prompt_inputs[key] = QTextEdit()
        self.s2v_positive_input = QTextEdit()
        self.s2v_negative_input = QTextEdit()
        self.s2v_size_input = QComboBox()
        for label, width, height in WAN22_S2V_SIZE_OPTIONS:
            self.s2v_size_input.addItem(label, (width, height))
        self.s2v_cfg_input = QDoubleSpinBox()
        self.s2v_cfg_input.setRange(1.0, 6.0)
        self.s2v_cfg_input.setSingleStep(0.1)
        self.s2v_cfg_input.setDecimals(1)
        self.s2v_cfg_input.setValue(float(DEFAULT_WAN22_S2V_PROMPT.get("cfg", 2.0)))
        self.web_url_input = QLineEdit()
        self.web_size_input = QComboBox()
        for label, width, height in Z_IMAGE_SIZES:
            self.web_size_input.addItem(label, (width, height))
        self.web_duration_input = QDoubleSpinBox()
        self.web_duration_input.setRange(0.0, 20.0)
        self.web_duration_input.setSingleStep(0.1)
        self.web_duration_input.setDecimals(1)
        self.web_duration_input.setValue(float(DEFAULT_WEB_SCROLL_PROMPT.get("duration_seconds", 5.0)))
        self.web_speed_input = QSpinBox()
        self.web_speed_input.setRange(1, 5)
        self.web_speed_input.setValue(int(DEFAULT_WEB_SCROLL_PROMPT.get("speed", 1)))
        self.web_capture_mode_input = QComboBox()
        self.web_capture_mode_input.addItem("Live Capture (Default)", "live_capture")
        self.web_capture_mode_input.addItem("Stable Pan", "stable_pan")
        self.image_pan_size_input = QComboBox()
        for label, width, height in Z_IMAGE_SIZES:
            if int(height) > int(width):
                self.image_pan_size_input.addItem(label, (width, height))
        self.image_pan_direction_input = QComboBox()
        self.image_pan_direction_input.addItem("Dari Kanan", "from_right")
        self.image_pan_direction_input.addItem("Dari Kiri", "from_left")
        self.image_pan_capture_mode_input = QComboBox()
        self.image_pan_capture_mode_input.addItem("Live Capture (Default)", "live_capture")
        self.image_pan_capture_mode_input.addItem("Stable Pan", "stable_pan")
        self.image_edit_model_input = QComboBox()
        self.image_edit_model_input.addItem("Flux.2", MODEL_FLUX2)
        self.image_edit_model_input.addItem("Gemini", MODEL_GEMINI_IMAGE)
        self.image_edit_gemini_model_input = QComboBox()
        for model_id in self.z_gemini_model_ids:
            self.image_edit_gemini_model_input.addItem(model_id, model_id)
        self.image_edit_image_inputs = []
        self.image_edit_prompt_inputs = []
        self.image_edit_clipboard_buttons = []
        self.image_edit_buttons = []
        for slot_index in range(3):
            image_input = QComboBox()
            prompt_input = QTextEdit()
            clipboard_button = QToolButton()
            clipboard_button.setText("Image Gen Prompt")
            clipboard_button.clicked.connect(
                lambda _checked=False, idx=slot_index: self.copy_image_edit_prompt_to_clipboard(idx)
            )
            button = QToolButton()
            button.setText("Edit Gambar")
            button.clicked.connect(lambda _checked=False, idx=slot_index: self.run_image_edit_slot(idx))
            self.image_edit_image_inputs.append(image_input)
            self.image_edit_prompt_inputs.append(prompt_input)
            self.image_edit_clipboard_buttons.append(clipboard_button)
            self.image_edit_buttons.append(button)

        self.status_label = QPlainTextEdit()
        self.status_label.setReadOnly(True)
        self.status_label.setPlainText("Belum ada adegan yang dipilih.")
        self.status_label.setFixedHeight(96)
        self.image_preview = MediaPreviewLabel("Klik ganda file pada tab Aset untuk melihat media.")
        self.video_preview = MediaPreviewLabel("Klik ganda file video pada tab Aset untuk melihat media.")
        self.audio_preview = MediaPreviewLabel()
        speaker_icon = self.style().standardIcon(QStyle.SP_MediaVolume)
        self.audio_preview.set_preview_pixmap(speaker_icon.pixmap(128, 128))
        self.image_preview.activated.connect(lambda: self.open_preview_in_default_app(self.image_preview))
        self.video_preview.activated.connect(lambda: self.open_preview_in_default_app(self.video_preview))
        self.audio_preview.activated.connect(lambda: self.open_preview_in_default_app(self.audio_preview))
        self.viewer_stack = QStackedWidget()
        self.viewer_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.viewer_stack.addWidget(self.image_preview)
        self.viewer_stack.addWidget(self.video_preview)
        self.viewer_stack.addWidget(self.audio_preview)
        self.viewer_title_label = QLabel("Tampilan")
        self.viewer_info_label = QLabel("Klik ganda file pada tab Aset untuk melihat media.")

        self.asset_list = QListWidget()
        self.asset_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.asset_list.currentItemChanged.connect(self.on_asset_selected)
        self.asset_list.itemClicked.connect(self.on_asset_clicked)
        self.asset_list.itemDoubleClicked.connect(self.on_asset_double_clicked)
        self.asset_list.customContextMenuRequested.connect(self.open_asset_context_menu)
        self.asset_info_label = QLabel("Belum ada aset yang dipilih.")
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.process_dialog = None

        self.video_player = QMediaPlayer(self)
        self.video_audio_output = QAudioOutput(self)
        self.video_sink = QVideoSink(self)
        self.video_player.setAudioOutput(self.video_audio_output)
        self.video_player.setVideoOutput(self.video_sink)
        self.video_sink.videoFrameChanged.connect(self.on_video_frame_changed)
        self.audio_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_player.setAudioOutput(self.audio_output)

        self.install_field_watchers()
        self.build_ui()
        self.update_seed_fields_enabled()
        self.update_lora_fields_enabled()
        self.update_wan_lora_fields_enabled()
        self.update_image_edit_model_fields_enabled()
        self.update_scene_type_tabs()
        self.update_scene_type_specific_fields()
        self.update_run_action_buttons_state()
        self.reload_scene_list()
        self.refresh_project_state()

    def install_field_watchers(self):
        for signal in [
            self.scene_title_input.textChanged, self.duration_input.currentTextChanged,
            self.scene_type_combo.currentTextChanged, self.voice_provider_combo.currentTextChanged,
            self.elevenlabs_voice_input.currentTextChanged, self.elevenlabs_model_input.currentTextChanged,
            self.edgetts_voice_input.currentTextChanged,
            self.sound_volume_input.textChanged, self.z_model_input.currentIndexChanged,
            self.z_gemini_model_input.currentIndexChanged,
            self.z_size_input.currentTextChanged, self.wan_step_combo.currentIndexChanged, self.wan_size_input.currentTextChanged,
            self.wan_duration_input.currentTextChanged,
            self.s2v_size_input.currentTextChanged, self.s2v_cfg_input.valueChanged, self.web_url_input.textChanged,
            self.web_size_input.currentTextChanged, self.web_duration_input.valueChanged, self.web_speed_input.valueChanged,
            self.web_capture_mode_input.currentIndexChanged,
            self.image_pan_size_input.currentTextChanged,
            self.image_pan_direction_input.currentIndexChanged,
            self.image_pan_capture_mode_input.currentIndexChanged,
            self.image_edit_model_input.currentIndexChanged,
            self.image_edit_gemini_model_input.currentIndexChanged,
            self.z_use_random_seed_input.checkStateChanged, self.z_use_lora_input.checkStateChanged,
            self.generate_caption_input.checkStateChanged,
            self.wan_use_lora_input.checkStateChanged,
        ]:
            signal.connect(self.refresh_scene_status)
        for widget in [
            self.voice_text_input, self.sound_prompt_input, self.z_positive_input,
            self.z_negative_input, self.z_seed_input, self.z_lora_name_input, self.z_lora_strength_input,
            self.wan_lora_high_name_input, self.wan_lora_high_strength_input,
            self.wan_lora_low_name_input, self.wan_lora_low_strength_input,
            self.s2v_positive_input, self.s2v_negative_input,
            *self.wan_prompt_inputs.values(),
            *self.z_extra_positive_inputs, *self.z_extra_negative_inputs,
        ]:
            widget.textChanged.connect(self.refresh_scene_status)
        self.z_use_lora_input.toggled.connect(self.update_lora_fields_enabled)
        self.z_use_random_seed_input.toggled.connect(self.update_seed_fields_enabled)
        self.z_model_input.currentIndexChanged.connect(self.update_image_model_fields_enabled)
        self.image_edit_model_input.currentIndexChanged.connect(self.update_image_edit_model_fields_enabled)
        self.wan_use_lora_input.toggled.connect(self.update_wan_lora_fields_enabled)
        self.scene_type_combo.currentTextChanged.connect(self.update_scene_type_tabs)
        self.scene_type_combo.currentTextChanged.connect(self.update_scene_type_specific_fields)
        self.scene_type_combo.currentTextChanged.connect(self.update_run_action_buttons_state)

    def build_ui(self):
        self.toolbar = QToolBar("Aksi")
        self.toolbar.setMovable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        self.build_toolbar_actions()

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Daftar Adegan"))
        left_layout.addWidget(self.scene_list)
        splitter.addWidget(left)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.addWidget(self.build_editor_tabs())
        splitter.addWidget(center)

        right = QWidget()
        right.setMinimumSize(0, 0)
        right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout = QVBoxLayout(right)
        self.viewer_group = self.build_viewer_group()
        self.status_group = self.build_status_group()
        right_layout.addWidget(self.viewer_group, 3)
        right_layout.addWidget(self.status_group, 1)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 3)

    def build_editor_tabs(self):
        tabs = QTabWidget()
        self.editor_tabs = tabs
        self.meta_tab = QWidget()
        meta_layout = QFormLayout(self.meta_tab)
        self.duration_label = QLabel("Durasi (detik)")
        meta_layout.addRow("Judul Adegan", self.scene_title_input)
        meta_layout.addRow(self.duration_label, self.duration_input)
        for label, widget in [
            ("Tipe Adegan", self.scene_type_combo), ("Penyedia Suara", self.voice_provider_combo),
            ("Suara ElevenLabs", self.elevenlabs_voice_input), ("Model ElevenLabs", self.elevenlabs_model_input),
            ("ID Suara EdgeTTS", self.edgetts_voice_input), ("Generate Caption", self.generate_caption_input),
            ("Teks Suara", self.voice_text_input), ("Prompt Suara Latar", self.sound_prompt_input),
            ("Volume Suara Latar", self.sound_volume_input),
        ]:
            meta_layout.addRow(label, widget)
        tabs.addTab(self.meta_tab, "Metadata")

        self.z_tab = QWidget()
        z_layout = QFormLayout(self.z_tab)
        z_layout.addRow("Model", self.z_model_input)
        z_layout.addRow("Model Gemini", self.z_gemini_model_input)
        z_layout.addRow("Ukuran", self.z_size_input)
        z_layout.addRow("", self.z_use_random_seed_input)
        z_layout.addRow("Seed Statik", self.z_seed_input)
        z_layout.addRow("", self.z_use_lora_input)
        z_layout.addRow("Nama Lora", self.z_lora_name_input)
        z_layout.addRow("Kekuatan Lora", self.z_lora_strength_input)
        z_layout.addRow("Prompt Positif", self.z_positive_input)
        z_layout.addRow("", self.z_clipboard_button)
        z_layout.addRow("Prompt Negatif", self.z_negative_input)
        tabs.addTab(self.z_tab, "Gambar Awal")

        self.z_extra_tab = QWidget()
        z_extra_layout = QVBoxLayout(self.z_extra_tab)
        for idx in range(3):
            group = QGroupBox(f"Prompt Tambahan {idx + 1}")
            group_layout = QFormLayout(group)
            group_layout.addRow("Prompt Positif", self.z_extra_positive_inputs[idx])
            group_layout.addRow("", self.z_extra_clipboard_buttons[idx])
            group_layout.addRow("Prompt Negatif", self.z_extra_negative_inputs[idx])
            group_layout.addRow("", self.z_extra_buttons[idx])
            z_extra_layout.addWidget(group)
        z_extra_layout.addStretch(1)
        tabs.addTab(self.z_extra_tab, "Prompt Tambahan")

        self.wan_tab = QWidget()
        wan_layout = QGridLayout(self.wan_tab)
        wan_layout.addWidget(QLabel("Langkah WAN"), 0, 0)
        wan_layout.addWidget(self.wan_step_combo, 0, 1)
        wan_layout.addWidget(QLabel("Durasi WAN"), 1, 0)
        wan_layout.addWidget(self.wan_duration_input, 1, 1)
        wan_layout.addWidget(QLabel("Ukuran"), 2, 0)
        wan_layout.addWidget(self.wan_size_input, 2, 1)
        wan_layout.addWidget(self.wan_use_lora_input, 3, 0, 1, 2)
        wan_layout.addWidget(QLabel("Nama Lora High"), 4, 0)
        wan_layout.addWidget(self.wan_lora_high_name_input, 4, 1)
        wan_layout.addWidget(QLabel("Kekuatan Lora High"), 5, 0)
        wan_layout.addWidget(self.wan_lora_high_strength_input, 5, 1)
        wan_layout.addWidget(QLabel("Nama Lora Low"), 6, 0)
        wan_layout.addWidget(self.wan_lora_low_name_input, 6, 1)
        wan_layout.addWidget(QLabel("Kekuatan Lora Low"), 7, 0)
        wan_layout.addWidget(self.wan_lora_low_strength_input, 7, 1)
        row = 8
        for key, widget in self.wan_prompt_inputs.items():
            wan_layout.addWidget(QLabel(key.replace("_", " ").title()), row, 0)
            wan_layout.addWidget(widget, row, 1)
            row += 1
        tabs.addTab(self.wan_tab, "WAN22_I2V")

        self.s2v_tab = QWidget()
        s2v_layout = QFormLayout(self.s2v_tab)
        s2v_layout.addRow("Ukuran", self.s2v_size_input)
        s2v_layout.addRow("CFG", self.s2v_cfg_input)
        s2v_layout.addRow("Prompt Positif", self.s2v_positive_input)
        self.s2v_negative_label = QLabel("Prompt Negatif")
        s2v_layout.addRow(self.s2v_negative_label, self.s2v_negative_input)
        tabs.addTab(self.s2v_tab, "WAN22 S2V")

        self.web_tab = QWidget()
        web_layout = QFormLayout(self.web_tab)
        web_layout.addRow("URL Website", self.web_url_input)
        web_layout.addRow("Ukuran", self.web_size_input)
        web_layout.addRow("Durasi (detik)", self.web_duration_input)
        web_layout.addRow("Speed", self.web_speed_input)
        web_layout.addRow("Mode", self.web_capture_mode_input)
        tabs.addTab(self.web_tab, "Web Scroll")

        self.image_pan_tab = QWidget()
        image_pan_layout = QFormLayout(self.image_pan_tab)
        image_pan_layout.addRow("Ukuran (Portrait)", self.image_pan_size_input)
        image_pan_layout.addRow("Arah", self.image_pan_direction_input)
        image_pan_layout.addRow("Mode", self.image_pan_capture_mode_input)
        tabs.addTab(self.image_pan_tab, "Image Pan")

        self.image_edit_tab = QWidget()
        image_edit_layout = QVBoxLayout(self.image_edit_tab)
        image_edit_form = QFormLayout()
        image_edit_form.addRow("Model", self.image_edit_model_input)
        image_edit_form.addRow("Model Gemini", self.image_edit_gemini_model_input)
        image_edit_layout.addLayout(image_edit_form)
        for idx in range(3):
            group = QGroupBox(f"Edit Gambar {idx + 1}")
            group_layout = QFormLayout(group)
            group_layout.addRow("Gambar Awal", self.image_edit_image_inputs[idx])
            group_layout.addRow("Prompt", self.image_edit_prompt_inputs[idx])
            group_layout.addRow("", self.image_edit_clipboard_buttons[idx])
            group_layout.addRow("", self.image_edit_buttons[idx])
            image_edit_layout.addWidget(group)
        image_edit_layout.addStretch(1)
        tabs.addTab(self.image_edit_tab, "Image Edit")

        self.assets_tab = QWidget()
        assets_layout = QVBoxLayout(self.assets_tab)
        assets_layout.addWidget(QLabel("Aset media dalam adegan. Klik ganda untuk membuka tampilan."))
        assets_layout.addWidget(self.asset_list)
        assets_layout.addWidget(self.asset_info_label)
        tabs.addTab(self.assets_tab, "Aset")
        return tabs

    def update_scene_type_tabs(self):
        if self.editor_tabs is None:
            return
        scene_type = self.scene_type_combo.currentText().strip()
        visible_map = {
            self.meta_tab: True,
            self.z_tab: scene_type != "web_scroll",
            self.wan_tab: scene_type in {"default", "wan22", "wan22_i2v"},
            self.s2v_tab: scene_type == "wan22_s2v",
            self.web_tab: scene_type == "web_scroll",
            self.image_pan_tab: scene_type == "image_pan",
            self.image_edit_tab: True,
            self.assets_tab: True,
        }
        current_widget = self.editor_tabs.currentWidget()
        for widget, visible in visible_map.items():
            if widget is None:
                continue
            index = self.editor_tabs.indexOf(widget)
            if index >= 0:
                self.editor_tabs.setTabVisible(index, visible)
        if current_widget and not visible_map.get(current_widget, True):
            self.editor_tabs.setCurrentWidget(self.meta_tab)

    def update_scene_type_specific_fields(self):
        scene_type = self.scene_type_combo.currentText().strip()
        hide_meta_duration = scene_type in {"wan22_s2v", "web_scroll"}
        self.duration_input.setEnabled(not hide_meta_duration)
        if self.duration_label is not None:
            self.duration_label.setEnabled(not hide_meta_duration)
            self.duration_label.setVisible(not hide_meta_duration)
        self.duration_input.setVisible(not hide_meta_duration)
        is_wan22_s2v = scene_type == "wan22_s2v"
        if self.s2v_negative_label is not None:
            self.s2v_negative_label.setVisible(is_wan22_s2v)
        self.s2v_negative_input.setVisible(is_wan22_s2v)

    def build_viewer_group(self):
        group = QGroupBox("Tampilan")
        group.setMinimumSize(0, 0)
        group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(group)
        layout.addWidget(self.viewer_title_label)
        layout.addWidget(self.viewer_stack)
        layout.addWidget(self.viewer_info_label)
        return group

    def build_status_group(self):
        group = QGroupBox("Status Adegan")
        layout = QVBoxLayout(group)
        self.status_label.setStyleSheet("padding: 6px; background: #f3f4f6; border: 1px solid #d1d5db;")
        layout.addWidget(self.status_label)
        return group

    def build_toolbar_actions(self):
        if self.toolbar is None:
            return
        self.toolbar.clear()

        def add_action(text, tooltip, icon_kind, handler):
            action = QAction(self.style().standardIcon(icon_kind), text, self)
            action.setToolTip(tooltip)
            action.setStatusTip(tooltip)
            action.triggered.connect(handler)
            self.toolbar.addAction(action)
            return action

        add_action("Project Baru", "Buat project baru.", QStyle.SP_FileDialogNewFolder, self.new_project)
        add_action("Buka Project", "Buka project yang sudah ada.", QStyle.SP_DirOpenIcon, self.open_project)
        add_action("Tutup Project", "Tutup project aktif.", QStyle.SP_DialogCloseButton, self.close_project)
        self.toolbar.addSeparator()
        add_action("Tambah Adegan", "Tambahkan adegan baru di akhir daftar.", QStyle.SP_FileDialogNewFolder, self.add_scene)
        add_action("Sisipkan Adegan", "Sisipkan adegan baru sebelum adegan yang sedang dipilih.", QStyle.SP_ArrowDown, self.insert_scene)
        add_action("Hapus Adegan", "Hapus adegan yang sedang dipilih.", QStyle.SP_TrashIcon, self.delete_scene)
        self.toolbar.addSeparator()
        add_action("Simpan Adegan", "Simpan perubahan adegan yang sedang dibuka.", QStyle.SP_DialogSaveButton, self.save_current_scene)
        add_action("Tambah Aset", "Tambahkan file aset ke folder adegan yang sedang dipilih.", QStyle.SP_FileIcon, self.add_asset_to_scene)
        add_action("Konfigurasi Server", "Buka dialog konfigurasi host/IP dan port server.", QStyle.SP_DriveNetIcon, self.open_server_config_dialog)
        add_action("Proses", "Buka atau tutup dialog status dan log proses.", QStyle.SP_FileDialogDetailedView, self.toggle_process_dialog)
        add_action("Muat Ulang", "Muat ulang daftar adegan dan statusnya.", QStyle.SP_BrowserReload, self.reload_scene_list)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.build_run_action_group())
        self.toolbar.addWidget(self.build_cover_action_group())
        self.toolbar.addWidget(self.build_audio_action_group())
        self.toolbar.addWidget(self.build_backup_action_group())
        self.toolbar.addWidget(self.build_compose_action_group())

    def project_dir(self) -> Path | None:
        name = str(self.current_project_name or "").strip()
        if not name:
            return None
        return API_PRODUCTION / name

    def list_projects(self):
        API_PRODUCTION.mkdir(parents=True, exist_ok=True)
        items = []
        reserved = {"combined", "cover"}
        for child in API_PRODUCTION.iterdir():
            if (
                child.is_dir()
                and child.name not in reserved
                and not child.name.startswith("scene_")
                and not child.name.startswith("__")
            ):
                items.append(child.name)
        items.sort(key=lambda s: s.lower())
        return items

    def list_scene_dirs_current(self):
        return list_scene_dirs_in_project(self.project_dir())

    def refresh_project_state(self):
        project_label = self.current_project_name if self.current_project_name else "(tidak ada project)"
        self.setWindowTitle(f"Pengelola Adegan - {project_label}")
        if not self.current_project_name:
            self.current_scene_dir = None
            self.scene_list.clear()
            self.refresh_image_edit_source_options()
            self.status_label.setPlainText("Belum ada project yang dibuka.")
            self.viewer_info_label.setText("Buka project terlebih dahulu.")
        self.update_run_action_buttons_state()

    def ensure_project_selected(self, notify=True):
        if self.project_dir() is not None:
            return True
        if notify:
            QMessageBox.information(self, "Belum Ada Project", "Buka atau buat project terlebih dahulu.")
        return False

    def new_project(self):
        if self.current_scene_dir:
            self.save_current_scene(silent=True, reload_list=False)
        name, ok = QInputDialog.getText(self, "Project Baru", "Masukkan nama project:")
        if not ok:
            return
        project_name = (name or "").strip()
        if not project_name:
            QMessageBox.warning(self, "Nama Tidak Valid", "Nama project tidak boleh kosong.")
            return
        if any(ch in project_name for ch in '\\/:*?"<>|'):
            QMessageBox.warning(self, "Nama Tidak Valid", "Nama project mengandung karakter yang tidak valid.")
            return
        API_PRODUCTION.mkdir(parents=True, exist_ok=True)
        pdir = API_PRODUCTION / project_name
        if pdir.exists():
            QMessageBox.warning(self, "Project Sudah Ada", f"Project `{project_name}` sudah ada.")
            return
        pdir.mkdir(parents=True, exist_ok=False)
        write_prompt_json(pdir / "cover_prompt.json", copy.deepcopy(DEFAULT_Z_IMAGE_PROMPT))
        default_scene = pdir / scene_dir_name(1)
        meta, z_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt = build_scene_templates("", "default", 10)
        create_scene_files(default_scene, meta, z_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt)
        self.current_project_name = project_name
        self.reload_scene_list()
        self.select_scene_by_name(default_scene.name)
        self.refresh_project_state()
        self.statusBar().showMessage(f"Project {project_name} dibuat.", 3000)

    def open_project(self):
        if self.current_scene_dir:
            self.save_current_scene(silent=True, reload_list=False)
        projects = self.list_projects()
        if not projects:
            QMessageBox.information(self, "Project Kosong", "Belum ada project di api_production.")
            return
        selected, ok = QInputDialog.getItem(self, "Buka Project", "Pilih project:", projects, 0, False)
        if not ok:
            return
        self.current_project_name = str(selected).strip()
        self.reload_scene_list()
        self.refresh_project_state()
        self.statusBar().showMessage(f"Project {self.current_project_name} dibuka.", 3000)

    def close_project(self):
        if self.current_scene_dir:
            self.save_current_scene(silent=True, reload_list=False)
        self.release_media_locks()
        self.current_project_name = ""
        self.current_scene_dir = None
        self.refresh_project_state()

    def build_run_action_group(self):
        frame = QFrame(self)
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame { background: #eef6ff; border: 1px solid #93c5fd; border-radius: 6px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        title = QLabel("Proses", frame)
        title.setStyleSheet("font-weight: 600; color: #1d4ed8;")
        layout.addWidget(title)

        def add_button(text, tooltip, icon_kind, handler):
            button = QToolButton(frame)
            button.setIcon(self.style().standardIcon(icon_kind))
            button.setToolTip(tooltip)
            button.setStatusTip(tooltip)
            button.clicked.connect(handler)
            layout.addWidget(button)
            return button

        self.generate_initial_image_button = add_button(
            "Buat Gambar Awal",
            "Buat gambar awal untuk adegan yang dipilih.",
            QStyle.SP_ComputerIcon,
            self.generate_initial_image_only,
        )
        add_button("Jalankan Adegan", "Jalankan alur untuk adegan yang dipilih.", QStyle.SP_MediaPlay, self.run_current_scene)
        add_button("Jalankan Semua", "Jalankan semua adegan secara berurutan.", QStyle.SP_MediaSkipForward, self.run_all_scenes)
        return frame

    def update_run_action_buttons_state(self):
        if self.generate_initial_image_button is None:
            return
        scene_type = self.scene_type_combo.currentText().strip()
        self.generate_initial_image_button.setEnabled(scene_type != "web_scroll")

    def build_audio_action_group(self):
        frame = QFrame(self)
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame { background: #effaf5; border: 1px solid #86efac; border-radius: 6px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        title = QLabel("Audio", frame)
        title.setStyleSheet("font-weight: 600; color: #166534;")
        layout.addWidget(title)

        def add_button(tooltip, icon_kind, handler):
            button = QToolButton(frame)
            button.setIcon(self.style().standardIcon(icon_kind))
            button.setToolTip(tooltip)
            button.setStatusTip(tooltip)
            button.clicked.connect(handler)
            layout.addWidget(button)

        add_button("Buat voice untuk adegan yang dipilih.", QStyle.SP_MediaVolume, self.generate_voice_current_scene)
        add_button("Buat voice untuk semua adegan.", QStyle.SP_MediaSeekForward, self.generate_voice_all_scenes)
        add_button("Buat sound untuk adegan yang dipilih.", QStyle.SP_DialogOpenButton, self.generate_sound_current_scene)
        add_button("Buat sound untuk semua adegan.", QStyle.SP_DialogApplyButton, self.generate_sound_all_scenes)
        return frame

    def build_cover_action_group(self):
        frame = QFrame(self)
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame { background: #ecfeff; border: 1px solid #67e8f9; border-radius: 6px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        title = QLabel("Cover", frame)
        title.setStyleSheet("font-weight: 600; color: #0e7490;")
        layout.addWidget(title)

        button = QToolButton(frame)
        button.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        button.setToolTip("Buka dialog konfigurasi dan generate cover project.")
        button.setStatusTip("Buka dialog konfigurasi dan generate cover project.")
        button.clicked.connect(self.open_cover_dialog)
        layout.addWidget(button)
        return frame

    def build_backup_action_group(self):
        frame = QFrame(self)
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame { background: #f5f3ff; border: 1px solid #c4b5fd; border-radius: 6px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        title = QLabel("Backup", frame)
        title.setStyleSheet("font-weight: 600; color: #5b21b6;")
        layout.addWidget(title)

        button = QToolButton(frame)
        button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        button.setToolTip("Simpan backup ZIP project aktif.")
        button.setStatusTip("Simpan backup ZIP project aktif.")
        button.clicked.connect(self.save_backup_zip)
        layout.addWidget(button)
        return frame

    def build_compose_action_group(self):
        frame = QFrame(self)
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame { background: #fff7ed; border: 1px solid #fdba74; border-radius: 6px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        title = QLabel("Compose", frame)
        title.setStyleSheet("font-weight: 600; color: #9a3412;")
        layout.addWidget(title)

        def add_button(tooltip, icon_kind, handler):
            button = QToolButton(frame)
            button.setIcon(self.style().standardIcon(icon_kind))
            button.setToolTip(tooltip)
            button.setStatusTip(tooltip)
            button.clicked.connect(handler)
            layout.addWidget(button)

        add_button("Gabungkan video dan audio untuk semua adegan.", QStyle.SP_DialogYesButton, self.compose_all_scenes)
        return frame

    def append_log(self, text: str):
        self.log_output.appendPlainText(text.rstrip())

    def ensure_process_dialog(self):
        if self.process_dialog is None:
            self.process_dialog = ProcessDialog(self.log_output, self)
        return self.process_dialog

    def toggle_process_dialog(self):
        dialog = self.ensure_process_dialog()
        if dialog.isVisible():
            dialog.hide()
        else:
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

    def open_server_config_dialog(self):
        self.server_config = load_server_config()
        dialog = ServerConfigDialog(self.server_config, self)
        while True:
            if dialog.exec() != QDialog.Accepted:
                return False
            try:
                self.server_config = save_server_config(dialog.get_config())
            except ValueError as e:
                QMessageBox.warning(self, "Konfigurasi Server Tidak Valid", str(e))
                continue
            break
        self.statusBar().showMessage("Konfigurasi server disimpan.", 3000)
        return True

    def ensure_server_config_loaded(self):
        try:
            self.server_config = load_server_config()
        except Exception:
            self.server_config = load_server_config()
        return True

    def comfyui_server_address(self):
        config = self.server_config or load_server_config()
        comfyui = config.get("comfyui", {})
        return f"{comfyui.get('host')}:{comfyui.get('port')}"

    def audio_server_address(self):
        config = self.server_config or load_server_config()
        audio = config.get("audio", {})
        return f"{audio.get('host')}:{audio.get('port')}"

    def release_media_locks(self):
        self.video_player.stop()
        self.video_player.setSource(QUrl())
        self.audio_player.stop()
        self.audio_player.setSource(QUrl())

    def clear_viewer(self):
        self.release_media_locks()
        self.viewer_stack.setCurrentWidget(self.image_preview)
        self.image_preview.clear_preview("Klik ganda file pada tab Aset untuk melihat media.")
        self.video_preview.clear_preview("Klik ganda file video pada tab Aset untuk melihat media.")
        self.audio_preview.clear_preview()
        self.viewer_title_label.setText("Tampilan")
        self.viewer_info_label.setText("Klik ganda file pada tab Aset untuk melihat media.")

    def open_preview_in_default_app(self, preview_widget):
        asset_path = getattr(preview_widget, "source_path", lambda: None)()
        if not asset_path:
            return
        asset_path = Path(asset_path)
        if not asset_path.exists():
            QMessageBox.information(self, "File Tidak Ditemukan", f"File tidak ditemukan:\n{asset_path}")
            return
        if asset_path.suffix.lower() not in (IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS):
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(asset_path)))

    def open_asset_preview_only(self, asset_path: Path):
        suffix = asset_path.suffix.lower()
        if suffix in IMAGE_EXTS:
            pixmap = QPixmap(str(asset_path))
            if pixmap.isNull():
                self.clear_viewer()
                self.viewer_info_label.setText(f"Gagal memuat gambar: {asset_path.name}")
                return
            self.release_media_locks()
            self.image_preview.clear_preview()
            self.image_preview.set_source_path(asset_path)
            self.image_preview.set_preview_pixmap(pixmap)
            self.viewer_stack.setCurrentWidget(self.image_preview)
            self.viewer_title_label.setText("Tampilan")
            self.viewer_info_label.setText(asset_path.name)
            return
        if suffix in VIDEO_EXTS:
            self.release_media_locks()
            self.video_preview.clear_preview("Memuat video...")
            self.video_preview.set_source_path(asset_path)
            self.video_player.setSource(QUrl.fromLocalFile(str(asset_path)))
            self.viewer_stack.setCurrentWidget(self.video_preview)
            self.viewer_title_label.setText("Tampilan")
            self.viewer_info_label.setText(asset_path.name)
            self.video_player.play()
            QTimer.singleShot(0, self.video_player.pause)
            return
        if suffix in AUDIO_EXTS:
            self.release_media_locks()
            self.audio_preview.clear_preview()
            self.audio_preview.set_source_path(asset_path)
            self.audio_preview.set_preview_pixmap(self.style().standardIcon(QStyle.SP_MediaVolume).pixmap(128, 128))
            self.viewer_stack.setCurrentWidget(self.audio_preview)
            self.viewer_title_label.setText("Tampilan")
            self.viewer_info_label.setText(asset_path.name)
            return
        self.clear_viewer()

    def update_lora_fields_enabled(self):
        enabled = self.z_use_lora_input.isChecked()
        self.z_lora_name_input.setEnabled(enabled)
        self.z_lora_strength_input.setEnabled(enabled)

    def update_seed_fields_enabled(self):
        self.z_seed_input.setEnabled(not self.z_use_random_seed_input.isChecked())

    def update_image_model_fields_enabled(self):
        model_key = str(self.z_model_input.currentData() or MODEL_Z_IMAGE_TURBO)
        is_gemini = model_key == MODEL_GEMINI_IMAGE
        can_use_negative = z_image_supports_negative_prompt({"image_model": model_key})
        self.z_gemini_model_input.setVisible(is_gemini)
        if self.z_tab is not None:
            layout = self.z_tab.layout()
            if isinstance(layout, QFormLayout):
                label = layout.labelForField(self.z_gemini_model_input)
                if label is not None:
                    label.setVisible(is_gemini)
        self.z_negative_input.setEnabled(can_use_negative)
        if not can_use_negative:
            self.z_negative_input.setPlainText("")
        for negative_input in self.z_extra_negative_inputs:
            negative_input.setEnabled(can_use_negative)
            if not can_use_negative:
                negative_input.setPlainText("")
        self.z_use_lora_input.setEnabled(not is_gemini)
        if is_gemini and self.z_use_lora_input.isChecked():
            self.z_use_lora_input.setChecked(False)
        self.z_use_random_seed_input.setEnabled(not is_gemini)
        if is_gemini:
            self.z_use_random_seed_input.setChecked(True)
            self.z_seed_input.setText("1")
        self.update_seed_fields_enabled()
        self.update_lora_fields_enabled()

    def update_wan_lora_fields_enabled(self):
        enabled = self.wan_use_lora_input.isChecked()
        self.wan_lora_high_name_input.setEnabled(enabled)
        self.wan_lora_high_strength_input.setEnabled(enabled)
        self.wan_lora_low_name_input.setEnabled(enabled)
        self.wan_lora_low_strength_input.setEnabled(enabled)

    def update_image_edit_model_fields_enabled(self):
        model_key = str(self.image_edit_model_input.currentData() or MODEL_FLUX2)
        is_gemini = model_key == MODEL_GEMINI_IMAGE
        self.image_edit_gemini_model_input.setVisible(is_gemini)
        if self.image_edit_tab is not None:
            layout = self.image_edit_tab.layout()
            if isinstance(layout, QVBoxLayout) and layout.count() > 0:
                form_item = layout.itemAt(0)
                form_layout = form_item.layout() if form_item else None
                if isinstance(form_layout, QFormLayout):
                    label = form_layout.labelForField(self.image_edit_gemini_model_input)
                    if label is not None:
                        label.setVisible(is_gemini)

    def open_asset_in_viewer(self, asset_path: Path):
        suffix = asset_path.suffix.lower()
        if suffix in IMAGE_EXTS:
            self.open_asset_preview_only(asset_path)
            return
        if suffix in VIDEO_EXTS:
            self.release_media_locks()
            self.video_preview.clear_preview("Memuat video...")
            self.video_preview.set_source_path(asset_path)
            self.video_player.setSource(QUrl.fromLocalFile(str(asset_path)))
            self.viewer_stack.setCurrentWidget(self.video_preview)
            self.viewer_title_label.setText("Tampilan")
            self.viewer_info_label.setText(asset_path.name)
            self.video_player.play()
            return
        if suffix in AUDIO_EXTS:
            self.release_media_locks()
            self.audio_preview.clear_preview()
            self.audio_preview.set_source_path(asset_path)
            self.audio_preview.set_preview_pixmap(self.style().standardIcon(QStyle.SP_MediaVolume).pixmap(128, 128))
            self.viewer_stack.setCurrentWidget(self.audio_preview)
            self.viewer_title_label.setText("Tampilan")
            self.viewer_info_label.setText(asset_path.name)
            self.audio_player.setSource(QUrl.fromLocalFile(str(asset_path)))
            self.audio_player.play()
            return
        self.clear_viewer()

    def on_video_frame_changed(self, frame):
        if not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        self.video_preview.set_preview_pixmap(QPixmap.fromImage(image))

    def item_scene_path(self, item):
        if item is None:
            return None
        try:
            value = item.data(Qt.UserRole)
        except RuntimeError:
            return None
        return Path(value) if value else None

    def reload_scene_list(self):
        if not self.ensure_project_selected(notify=False):
            self.scene_list.clear()
            self.current_scene_dir = None
            return
        current_name = self.current_scene_dir.name if self.current_scene_dir else None
        was_loading = self.loading_scene
        self.loading_scene = True
        self.scene_list.clear()
        for scene_dir in self.list_scene_dirs_current():
            meta = load_json(scene_dir / "scene_meta.json", DEFAULT_SCENE_META)
            z_prompt = load_json(scene_dir / "z_image_prompt.json", DEFAULT_Z_IMAGE_PROMPT)
            wan_prompt = load_json(scene_dir / "wan22_i2v_prompt.json", DEFAULT_WAN_PROMPT)
            s2v_prompt = load_json(scene_dir / "wan22_s2v_prompt.json", DEFAULT_WAN22_S2V_PROMPT)
            web_prompt = load_json(scene_dir / "web_scroll_prompt.json", DEFAULT_WEB_SCROLL_PROMPT)
            image_pan_prompt = load_json(scene_dir / "image_pan_prompt.json", DEFAULT_IMAGE_PAN_PROMPT)
            issues = validate_scene_data(meta, z_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt, scene_dir)
            label = scene_dir.name if not issues else f"{scene_dir.name} ({len(issues)} masalah)"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, str(scene_dir))
            item.setToolTip("\n".join(issues) if issues else "Siap")
            self.scene_list.addItem(item)
            if scene_dir.name == current_name:
                self.scene_list.setCurrentItem(item)
        if self.scene_list.count() and self.scene_list.currentRow() < 0:
            self.scene_list.setCurrentRow(0)
        self.loading_scene = was_loading
        selected = self.current_scene_path_from_ui()
        self.current_scene_dir = selected
        if selected and not self.loading_scene:
            self.load_scene(selected)
        elif not selected:
            self.refresh_image_edit_source_options()

    def current_scene_path_from_ui(self):
        item = self.scene_list.currentItem()
        return self.item_scene_path(item)

    def on_scene_changed(self, current, previous):
        if self.loading_scene:
            return
        if previous and self.current_scene_dir:
            self.save_current_scene(silent=True, reload_list=False)
        self.release_media_locks()
        self.current_scene_dir = self.item_scene_path(current)
        if self.current_scene_dir:
            self.load_scene(self.current_scene_dir)

    def on_scene_reordered(self):
        if self.loading_scene:
            return
        project_dir = self.project_dir()
        if project_dir is None:
            return
        self.release_media_locks()
        if self.current_scene_dir:
            self.save_current_scene(silent=True, reload_list=False)
        ordered_paths = [Path(self.scene_list.item(i).data(Qt.UserRole)) for i in range(self.scene_list.count())]
        if not ordered_paths:
            return
        temp_paths = []
        for idx, old_path in enumerate(ordered_paths, start=1):
            temp_path = project_dir / f"__reorder_tmp_{idx}"
            if temp_path.exists():
                shutil.rmtree(temp_path)
            old_path.rename(temp_path)
            temp_paths.append(temp_path)
        for idx, temp_path in enumerate(temp_paths, start=1):
            temp_path.rename(project_dir / scene_dir_name(idx))
        current_row = self.scene_list.currentRow()
        self.reload_scene_list()
        if 0 <= current_row < self.scene_list.count():
            self.scene_list.setCurrentRow(current_row)

    def load_scene(self, scene_dir: Path):
        self.loading_scene = True
        try:
            meta = load_json(scene_dir / "scene_meta.json", DEFAULT_SCENE_META)
            z_prompt = load_json(scene_dir / "z_image_prompt.json", DEFAULT_Z_IMAGE_PROMPT)
            wan_prompt = load_json(scene_dir / "wan22_i2v_prompt.json", DEFAULT_WAN_PROMPT)
            s2v_prompt = load_json(scene_dir / "wan22_s2v_prompt.json", DEFAULT_WAN22_S2V_PROMPT)
            web_prompt = load_json(scene_dir / "web_scroll_prompt.json", DEFAULT_WEB_SCROLL_PROMPT)
            image_pan_prompt = load_json(scene_dir / "image_pan_prompt.json", DEFAULT_IMAGE_PAN_PROMPT)
            self.scene_title_input.setText(str(meta.get("scene_title", "")))
            duration_value = str(meta.get("duration_seconds", ""))
            index = self.duration_input.findData(int(float(duration_value))) if duration_value else -1
            if index < 0:
                index = self.duration_input.findText(duration_value)
            self.duration_input.setCurrentIndex(max(index, 0))
            self.scene_type_combo.setCurrentText(str(meta.get("scene_type", "default")))
            self.update_scene_type_tabs()
            self.update_scene_type_specific_fields()
            self.voice_provider_combo.setCurrentText(str(meta.get("voice_provider", "")))
            elevenlabs_voice_id = str(meta.get("elevenlabs_voice_id", ""))
            index = self.elevenlabs_voice_input.findData(elevenlabs_voice_id)
            if index < 0 and elevenlabs_voice_id:
                label = f"Suara Khusus ({elevenlabs_voice_id})"
                self.elevenlabs_voice_input.addItem(label, elevenlabs_voice_id)
                index = self.elevenlabs_voice_input.findData(elevenlabs_voice_id)
            self.elevenlabs_voice_input.setCurrentIndex(max(index, 0))
            elevenlabs_model_id = str(meta.get("elevenlabs_model_id", ELEVENLABS_MODEL_ID))
            index = self.elevenlabs_model_input.findData(elevenlabs_model_id)
            self.elevenlabs_model_input.setCurrentIndex(max(index, 0))
            edgetts_voice_id = str(meta.get("edgetts_voice_id", ""))
            index = self.edgetts_voice_input.findData(edgetts_voice_id)
            if index < 0 and edgetts_voice_id:
                label = f"Suara Khusus ({edgetts_voice_id})"
                self.edgetts_voice_input.addItem(label, edgetts_voice_id)
                index = self.edgetts_voice_input.findData(edgetts_voice_id)
            self.edgetts_voice_input.setCurrentIndex(max(index, 0))
            self.generate_caption_input.setChecked(bool(meta.get("generate_caption", True)))
            self.voice_text_input.setPlainText(str(meta.get("voice_text", "")))
            self.sound_prompt_input.setPlainText(str(meta.get("sound_prompt", "")))
            self.sound_volume_input.setText(str(meta.get("sound_volume", "")))
            z_width = int(z_prompt.get("width", DEFAULT_Z_IMAGE_PROMPT["width"]))
            z_height = int(z_prompt.get("height", DEFAULT_Z_IMAGE_PROMPT["height"]))
            model_key = get_z_image_model_key(z_prompt)
            index = self.z_model_input.findData(model_key)
            self.z_model_input.setCurrentIndex(max(index, 0))
            selected_gemini_model = str(z_prompt.get("gemini_model_id", MODEL_GEMINI_FLASH_05K)).strip()
            index = self.z_gemini_model_input.findData(selected_gemini_model)
            if index < 0 and selected_gemini_model:
                self.z_gemini_model_input.addItem(selected_gemini_model, selected_gemini_model)
                index = self.z_gemini_model_input.findData(selected_gemini_model)
            self.z_gemini_model_input.setCurrentIndex(max(index, 0))
            index = -1
            for i in range(self.z_size_input.count()):
                size_value = self.z_size_input.itemData(i)
                if isinstance(size_value, tuple) and size_value == (z_width, z_height):
                    index = i
                    break
            self.z_size_input.setCurrentIndex(max(index, 0))
            self.z_use_random_seed_input.setChecked(bool(z_prompt.get("use_random_seed", True)))
            self.z_seed_input.setText(str(z_prompt.get("seed", 1)))
            self.z_use_lora_input.setChecked(bool(z_prompt.get("use_lora", False)))
            self.z_lora_name_input.setText(str(z_prompt.get("lora_name", "")))
            self.z_lora_strength_input.setText(str(z_prompt.get("strength_model", 1.0)))
            self.update_image_model_fields_enabled()
            self.update_seed_fields_enabled()
            self.update_lora_fields_enabled()
            self.z_positive_input.setPlainText(str(z_prompt.get("positive_prompt", "")))
            self.z_negative_input.setPlainText(str(z_prompt.get("negative_prompt", "")))
            index = self.wan_step_combo.findData(get_wan_step_template_name(wan_prompt))
            self.wan_step_combo.setCurrentIndex(max(index, 0))
            self.wan_use_lora_input.setChecked(bool(wan_prompt.get("use_lora", False)))
            wan_width = int(wan_prompt.get("width", DEFAULT_WAN_PROMPT["width"]))
            wan_height = int(wan_prompt.get("height", DEFAULT_WAN_PROMPT["height"]))
            wan_duration = int(wan_prompt.get("duration_seconds", DEFAULT_WAN_PROMPT["duration_seconds"]))
            index = self.wan_duration_input.findData(wan_duration)
            self.wan_duration_input.setCurrentIndex(max(index, 0))
            index = -1
            for i in range(self.wan_size_input.count()):
                size_value = self.wan_size_input.itemData(i)
                if isinstance(size_value, tuple) and size_value == (wan_width, wan_height):
                    index = i
                    break
            self.wan_size_input.setCurrentIndex(max(index, 0))
            self.wan_lora_high_name_input.setText(str(wan_prompt.get("lora_high_name", DEFAULT_WAN_PROMPT["lora_high_name"])))
            self.wan_lora_high_strength_input.setText(str(wan_prompt.get("lora_high_strength", DEFAULT_WAN_PROMPT["lora_high_strength"])))
            self.wan_lora_low_name_input.setText(str(wan_prompt.get("lora_low_name", DEFAULT_WAN_PROMPT["lora_low_name"])))
            self.wan_lora_low_strength_input.setText(str(wan_prompt.get("lora_low_strength", DEFAULT_WAN_PROMPT["lora_low_strength"])))
            self.update_wan_lora_fields_enabled()
            for key, widget in self.wan_prompt_inputs.items():
                widget.setPlainText(str(wan_prompt.get(key, "")))
            s2v_width = int(s2v_prompt.get("width", DEFAULT_WAN22_S2V_PROMPT["width"]))
            s2v_height = int(s2v_prompt.get("height", DEFAULT_WAN22_S2V_PROMPT["height"]))
            index = -1
            for i in range(self.s2v_size_input.count()):
                size_value = self.s2v_size_input.itemData(i)
                if isinstance(size_value, tuple) and size_value == (s2v_width, s2v_height):
                    index = i
                    break
            self.s2v_size_input.setCurrentIndex(max(index, 0))
            self.s2v_cfg_input.setValue(float(s2v_prompt.get("cfg", DEFAULT_WAN22_S2V_PROMPT["cfg"])))
            self.s2v_positive_input.setPlainText(str(s2v_prompt.get("positive_prompt", DEFAULT_WAN22_S2V_PROMPT["positive_prompt"])))
            self.s2v_negative_input.setPlainText(str(s2v_prompt.get("negative_prompt", DEFAULT_WAN22_S2V_PROMPT["negative_prompt"])))
            self.web_url_input.setText(str(web_prompt.get("url", DEFAULT_WEB_SCROLL_PROMPT["url"])))
            try:
                web_width = int(web_prompt.get("width", DEFAULT_WEB_SCROLL_PROMPT["width"]))
            except (TypeError, ValueError):
                web_width = int(DEFAULT_WEB_SCROLL_PROMPT["width"])
            try:
                web_height = int(web_prompt.get("height", DEFAULT_WEB_SCROLL_PROMPT["height"]))
            except (TypeError, ValueError):
                web_height = int(DEFAULT_WEB_SCROLL_PROMPT["height"])
            index = -1
            for i in range(self.web_size_input.count()):
                size_value = self.web_size_input.itemData(i)
                if isinstance(size_value, tuple) and size_value == (web_width, web_height):
                    index = i
                    break
            self.web_size_input.setCurrentIndex(max(index, 0))
            try:
                web_duration = float(web_prompt.get("duration_seconds", DEFAULT_WEB_SCROLL_PROMPT["duration_seconds"]))
            except (TypeError, ValueError):
                web_duration = float(DEFAULT_WEB_SCROLL_PROMPT["duration_seconds"])
            try:
                web_speed = int(web_prompt.get("speed", DEFAULT_WEB_SCROLL_PROMPT["speed"]))
            except (TypeError, ValueError):
                web_speed = int(DEFAULT_WEB_SCROLL_PROMPT["speed"])
            web_duration = round(max(0.0, min(20.0, web_duration)), 1)
            self.web_duration_input.setValue(web_duration)
            self.web_speed_input.setValue(max(1, min(5, web_speed)))
            capture_mode = str(web_prompt.get("capture_mode", DEFAULT_WEB_SCROLL_PROMPT["capture_mode"])).strip()
            index = self.web_capture_mode_input.findData(capture_mode)
            self.web_capture_mode_input.setCurrentIndex(max(index, 0))
            try:
                pan_width = int(image_pan_prompt.get("width", DEFAULT_IMAGE_PAN_PROMPT["width"]))
            except (TypeError, ValueError):
                pan_width = int(DEFAULT_IMAGE_PAN_PROMPT["width"])
            try:
                pan_height = int(image_pan_prompt.get("height", DEFAULT_IMAGE_PAN_PROMPT["height"]))
            except (TypeError, ValueError):
                pan_height = int(DEFAULT_IMAGE_PAN_PROMPT["height"])
            index = -1
            for i in range(self.image_pan_size_input.count()):
                size_value = self.image_pan_size_input.itemData(i)
                if isinstance(size_value, tuple) and size_value == (pan_width, pan_height):
                    index = i
                    break
            self.image_pan_size_input.setCurrentIndex(max(index, 0))
            pan_direction = str(image_pan_prompt.get("direction", DEFAULT_IMAGE_PAN_PROMPT["direction"])).strip()
            index = self.image_pan_direction_input.findData(pan_direction)
            self.image_pan_direction_input.setCurrentIndex(max(index, 0))
            pan_mode = str(image_pan_prompt.get("capture_mode", DEFAULT_IMAGE_PAN_PROMPT["capture_mode"])).strip()
            index = self.image_pan_capture_mode_input.findData(pan_mode)
            self.image_pan_capture_mode_input.setCurrentIndex(max(index, 0))
            self.load_z_image_extra_prompts_into_ui(scene_dir)
            self.load_image_edit_into_ui(scene_dir)
        finally:
            self.loading_scene = False
        self.refresh_scene_status()
        self.refresh_assets_and_previews()

    def gather_scene_data(self):
        meta = {
            "scene_title": self.scene_title_input.text().strip(),
            "duration_seconds": self.parse_duration_value(),
            "voice_text": self.voice_text_input.toPlainText().strip(),
            "voice_provider": self.voice_provider_combo.currentText().strip(),
            "elevenlabs_voice_id": str(self.elevenlabs_voice_input.currentData() or "").strip(),
            "elevenlabs_model_id": str(self.elevenlabs_model_input.currentData() or ELEVENLABS_MODEL_ID).strip(),
            "generate_caption": self.generate_caption_input.isChecked(),
            "edgetts_voice_id": str(self.edgetts_voice_input.currentData() or "").strip(),
            "sound_prompt": self.sound_prompt_input.toPlainText().strip(),
            "sound_volume": self.sound_volume_input.text().strip(),
            "scene_type": self.scene_type_combo.currentText().strip(),
        }
        z_prompt = {
            "image_model": str(self.z_model_input.currentData() or MODEL_Z_IMAGE_TURBO),
            "gemini_model_id": (
                str(self.z_gemini_model_input.currentData() or MODEL_GEMINI_FLASH_05K).strip()
                if str(self.z_model_input.currentData() or MODEL_Z_IMAGE_TURBO) == MODEL_GEMINI_IMAGE
                else ""
            ),
            "positive_prompt": self.z_positive_input.toPlainText().strip(),
            "negative_prompt": (
                self.z_negative_input.toPlainText().strip()
                if z_image_supports_negative_prompt({"image_model": str(self.z_model_input.currentData() or MODEL_Z_IMAGE_TURBO)})
                else ""
            ),
            "width": int((self.z_size_input.currentData() or (368, 640))[0]),
            "height": int((self.z_size_input.currentData() or (368, 640))[1]),
            "use_random_seed": self.z_use_random_seed_input.isChecked(),
            "seed": self.parse_seed_value(),
            "use_lora": self.z_use_lora_input.isChecked(),
            "lora_name": self.z_lora_name_input.text().strip(),
            "strength_model": self.parse_lora_strength_value(),
        }
        z_prompt["json_api"] = get_z_image_template_name(z_prompt)
        wan_prompt = {
            "duration_seconds": int(self.wan_duration_input.currentData() or DEFAULT_WAN_PROMPT["duration_seconds"]),
            "width": int((self.wan_size_input.currentData() or (368, 640))[0]),
            "height": int((self.wan_size_input.currentData() or (368, 640))[1]),
            "use_lora": self.wan_use_lora_input.isChecked(),
            "lora_high_name": self.wan_lora_high_name_input.text().strip(),
            "lora_high_strength": self.parse_wan_lora_strength_value(self.wan_lora_high_strength_input, "High"),
            "lora_low_name": self.wan_lora_low_name_input.text().strip(),
            "lora_low_strength": self.parse_wan_lora_strength_value(self.wan_lora_low_strength_input, "Low"),
            "json_api": get_wan_template_name({
                "json_api": self.wan_step_combo.currentData(),
                "use_lora": self.wan_use_lora_input.isChecked(),
            }),
        }
        for key, widget in self.wan_prompt_inputs.items():
            wan_prompt[key] = widget.toPlainText().strip()
        s2v_prompt = {
            "positive_prompt": self.s2v_positive_input.toPlainText().strip() or DEFAULT_WAN22_S2V_PROMPT["positive_prompt"],
            "negative_prompt": self.s2v_negative_input.toPlainText().strip() or DEFAULT_WAN22_S2V_PROMPT["negative_prompt"],
            "width": int((self.s2v_size_input.currentData() or (480, 848))[0]),
            "height": int((self.s2v_size_input.currentData() or (480, 848))[1]),
            "cfg": float(self.s2v_cfg_input.value()),
            "json_api": "auto_by_speech_duration",
        }
        web_prompt = {
            "url": self.web_url_input.text().strip(),
            "width": int((self.web_size_input.currentData() or (368, 640))[0]),
            "height": int((self.web_size_input.currentData() or (368, 640))[1]),
            "duration_seconds": round(float(self.web_duration_input.value()), 1),
            "speed": int(self.web_speed_input.value()),
            "capture_mode": str(self.web_capture_mode_input.currentData() or "live_capture").strip(),
        }
        image_pan_prompt = {
            "width": int((self.image_pan_size_input.currentData() or (480, 848))[0]),
            "height": int((self.image_pan_size_input.currentData() or (480, 848))[1]),
            "direction": str(self.image_pan_direction_input.currentData() or "from_right").strip(),
            "capture_mode": str(self.image_pan_capture_mode_input.currentData() or "live_capture").strip(),
        }
        return meta, z_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt

    def parse_duration_value(self):
        value = self.duration_input.currentText().strip()
        if not value:
            return 10
        try:
            return int(float(value))
        except ValueError:
            raise ValueError("Durasi harus berupa angka.")

    def parse_lora_strength_value(self):
        if not self.z_use_lora_input.isChecked():
            return 1.0
        value = self.z_lora_strength_input.text().strip()
        if not value:
            return 1.0
        try:
            parsed = float(value)
        except ValueError:
            raise ValueError("Kekuatan Lora harus berupa bilangan desimal positif.")
        if parsed <= 0:
            raise ValueError("Kekuatan Lora harus berupa bilangan desimal positif.")
        return parsed

    def parse_seed_value(self):
        if self.z_use_random_seed_input.isChecked():
            # Ignore any stale value in the static seed input when random mode is enabled.
            return 1
        value = self.z_seed_input.text().strip()
        if not value:
            raise ValueError("Seed statik wajib diisi saat Random Seed dimatikan.")
        try:
            parsed = int(value)
        except ValueError:
            raise ValueError("Seed statik harus berupa bilangan bulat positif.")
        if parsed <= 0:
            raise ValueError("Seed statik harus berupa bilangan bulat positif.")
        return parsed

    def parse_wan_lora_strength_value(self, widget: QLineEdit, label: str):
        if not self.wan_use_lora_input.isChecked():
            return 1.0
        value = widget.text().strip()
        if not value:
            raise ValueError(f"Kekuatan Lora {label} WAN wajib diisi saat Lora digunakan.")
        try:
            parsed = float(value)
        except ValueError:
            raise ValueError(f"Kekuatan Lora {label} WAN harus berupa bilangan desimal positif.")
        if parsed <= 0:
            raise ValueError(f"Kekuatan Lora {label} WAN harus berupa bilangan desimal positif.")
        return parsed

    def load_image_edit_prompt(self, scene_dir: Path):
        data = load_json(scene_dir / "image_edit_prompt.json", DEFAULT_IMAGE_EDIT_PROMPT)
        model_key = str(data.get("image_model", MODEL_FLUX2)).strip().lower()
        if model_key not in {MODEL_FLUX2, MODEL_GEMINI_IMAGE}:
            model_key = MODEL_FLUX2
        gemini_model_id = str(data.get("gemini_model_id", MODEL_GEMINI_FLASH_05K)).strip()
        groups = data.get("groups")
        if not isinstance(groups, list):
            groups = []
        normalized_groups = []
        for index in range(3):
            item = groups[index] if index < len(groups) and isinstance(groups[index], dict) else {}
            normalized_groups.append(
                {
                    "source_image": str(item.get("source_image", "")).strip(),
                    "prompt": str(item.get("prompt", "")).strip(),
                }
            )
        return {"image_model": model_key, "gemini_model_id": gemini_model_id, "groups": normalized_groups}

    def load_z_image_extra_prompts(self, scene_dir: Path):
        data = load_json(scene_dir / "z_image_extra_prompts.json", DEFAULT_Z_IMAGE_EXTRA_PROMPTS)
        groups = data.get("groups")
        if not isinstance(groups, list):
            groups = []
        normalized_groups = []
        for index in range(3):
            item = groups[index] if index < len(groups) and isinstance(groups[index], dict) else {}
            normalized_groups.append(
                {
                    "positive_prompt": str(item.get("positive_prompt", "")).strip(),
                    "negative_prompt": str(item.get("negative_prompt", "")).strip(),
                }
            )
        return {"groups": normalized_groups}

    def gather_z_image_extra_prompts(self):
        groups = []
        model_key = str(self.z_model_input.currentData() or MODEL_Z_IMAGE_TURBO)
        supports_negative = z_image_supports_negative_prompt({"image_model": model_key})
        for positive_input, negative_input in zip(self.z_extra_positive_inputs, self.z_extra_negative_inputs):
            groups.append(
                {
                    "positive_prompt": positive_input.toPlainText().strip(),
                    "negative_prompt": negative_input.toPlainText().strip() if supports_negative else "",
                }
            )
        return {"groups": groups}

    def gather_image_edit_prompt(self):
        groups = []
        for image_input, prompt_input in zip(self.image_edit_image_inputs, self.image_edit_prompt_inputs):
            groups.append(
                {
                    "source_image": str(image_input.currentData() or "").strip(),
                    "prompt": prompt_input.toPlainText().strip(),
                }
            )
        return {
            "image_model": str(self.image_edit_model_input.currentData() or MODEL_FLUX2).strip(),
            "gemini_model_id": str(self.image_edit_gemini_model_input.currentData() or MODEL_GEMINI_FLASH_05K).strip(),
            "groups": groups,
        }

    def refresh_image_edit_source_options(self, preferred_images=None):
        preferred_images = preferred_images or ["", "", ""]
        image_names = []
        if self.current_scene_dir and self.current_scene_dir.exists():
            image_names = sorted(
                [
                    p.name for p in self.current_scene_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in IMAGE_EXTS
                ],
                key=lambda name: name.lower(),
            )

        for index, combo in enumerate(self.image_edit_image_inputs):
            preferred = str(preferred_images[index] if index < len(preferred_images) else "").strip()
            current_value = str(combo.currentData() or "").strip()
            wanted = preferred or current_value
            combo.blockSignals(True)
            combo.clear()
            for image_name in image_names:
                combo.addItem(image_name, image_name)
            if image_names:
                selected_index = combo.findData(wanted)
                combo.setCurrentIndex(selected_index if selected_index >= 0 else 0)
            combo.blockSignals(False)

    def load_image_edit_into_ui(self, scene_dir: Path):
        data = self.load_image_edit_prompt(scene_dir)
        model_index = self.image_edit_model_input.findData(str(data.get("image_model", MODEL_FLUX2)))
        self.image_edit_model_input.setCurrentIndex(model_index if model_index >= 0 else 0)
        selected_gemini_model = str(data.get("gemini_model_id", MODEL_GEMINI_FLASH_05K)).strip()
        gemini_index = self.image_edit_gemini_model_input.findData(selected_gemini_model)
        if gemini_index < 0 and selected_gemini_model:
            self.image_edit_gemini_model_input.addItem(selected_gemini_model, selected_gemini_model)
            gemini_index = self.image_edit_gemini_model_input.findData(selected_gemini_model)
        self.image_edit_gemini_model_input.setCurrentIndex(gemini_index if gemini_index >= 0 else 0)
        self.update_image_edit_model_fields_enabled()
        groups = data.get("groups", [])
        preferred_images = [str(group.get("source_image", "")).strip() for group in groups[:3]]
        self.refresh_image_edit_source_options(preferred_images=preferred_images)
        for index, prompt_input in enumerate(self.image_edit_prompt_inputs):
            group_data = groups[index] if index < len(groups) else {}
            prompt_input.setPlainText(str(group_data.get("prompt", "")))

    def load_z_image_extra_prompts_into_ui(self, scene_dir: Path):
        data = self.load_z_image_extra_prompts(scene_dir)
        groups = data.get("groups", [])
        for index in range(3):
            group_data = groups[index] if index < len(groups) else {}
            self.z_extra_positive_inputs[index].setPlainText(str(group_data.get("positive_prompt", "")))
            self.z_extra_negative_inputs[index].setPlainText(str(group_data.get("negative_prompt", "")))

    def refresh_scene_status(self):
        if not self.current_scene_dir:
            self.status_label.setPlainText("Belum ada adegan yang dipilih.")
            return
        try:
            meta, z_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt = self.gather_scene_data()
            issues = validate_scene_data(meta, z_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt, self.current_scene_dir)
        except ValueError as e:
            issues = [str(e)]
        if issues:
            self.status_label.setPlainText("Masalah:\n- " + "\n- ".join(issues))
            self.status_label.setStyleSheet("padding: 6px; background: #fef2f2; border: 1px solid #ef4444; color: #991b1b;")
        else:
            self.status_label.setPlainText("Status: Siap")
            self.status_label.setStyleSheet("padding: 6px; background: #ecfdf5; border: 1px solid #10b981; color: #065f46;")

    def get_scene_issues(self, scene_dir: Path):
        meta = load_json(scene_dir / "scene_meta.json", DEFAULT_SCENE_META)
        z_prompt = load_json(scene_dir / "z_image_prompt.json", DEFAULT_Z_IMAGE_PROMPT)
        wan_prompt = load_json(scene_dir / "wan22_i2v_prompt.json", DEFAULT_WAN_PROMPT)
        s2v_prompt = load_json(scene_dir / "wan22_s2v_prompt.json", DEFAULT_WAN22_S2V_PROMPT)
        web_prompt = load_json(scene_dir / "web_scroll_prompt.json", DEFAULT_WEB_SCROLL_PROMPT)
        image_pan_prompt = load_json(scene_dir / "image_pan_prompt.json", DEFAULT_IMAGE_PAN_PROMPT)
        return validate_scene_data(meta, z_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt, scene_dir)

    def ensure_scene_is_runnable(self, scene_dir: Path):
        issues = self.get_scene_issues(scene_dir)
        if issues:
            QMessageBox.warning(
                self,
                "Adegan Masih Bermasalah",
                "Adegan tidak bisa dijalankan karena masih ada masalah:\n- " + "\n- ".join(issues),
            )
            return False
        return True

    def ensure_all_scenes_are_runnable(self):
        problem_summaries = []
        for scene_dir in self.list_scene_dirs_current():
            issues = self.get_scene_issues(scene_dir)
            if issues:
                problem_summaries.append(f"{scene_dir.name}: " + "; ".join(issues))
        if problem_summaries:
            QMessageBox.warning(
                self,
                "Masih Ada Adegan Bermasalah",
                "Semua adegan tidak bisa dijalankan karena masih ada masalah:\n- " + "\n- ".join(problem_summaries),
            )
            return False
        return True

    def refresh_assets_and_previews(self):
        if not self.current_scene_dir:
            self.refresh_image_edit_source_options()
            return
        self.clear_viewer()
        assets = sorted(
            [
                p for p in self.current_scene_dir.iterdir()
                if p.is_file() and p.suffix.lower() in (IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS)
            ],
            key=lambda p: p.name.lower(),
        )
        self.asset_list.clear()
        self.asset_info_label.setText("Belum ada aset yang dipilih.")
        for asset in assets:
            item = QListWidgetItem(asset.name)
            item.setData(Qt.UserRole, str(asset))
            self.asset_list.addItem(item)
        self.refresh_image_edit_source_options()
        if not assets:
            self.viewer_info_label.setText("Tidak ada file media di scene ini.")

    def save_current_scene(self, silent=False, reload_list=True):
        if not self.current_scene_dir:
            return False
        try:
            meta, z_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt = self.gather_scene_data()
        except ValueError as e:
            if not silent:
                QMessageBox.warning(self, "Data Tidak Valid", str(e))
            return False
        issues = validate_scene_data(meta, z_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt, self.current_scene_dir)
        if issues and not silent:
            reply = QMessageBox.question(
                self, "Masalah Validasi",
                "Adegan masih memiliki masalah:\n- " + "\n- ".join(issues) + "\n\nTetap simpan?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return False
        scene_type = str(meta.get("scene_type", "default")).strip()
        image_edit_prompt = self.gather_image_edit_prompt()
        z_image_extra_prompts = self.gather_z_image_extra_prompts()
        write_prompt_json(self.current_scene_dir / "scene_meta.json", meta)
        sync_scene_prompt_files(
            self.current_scene_dir,
            scene_type=scene_type,
            z_prompt=z_prompt,
            wan_prompt=wan_prompt,
            s2v_prompt=s2v_prompt,
            web_prompt=web_prompt,
            image_pan_prompt=image_pan_prompt,
            image_edit_prompt=image_edit_prompt,
            z_image_extra_prompts=z_image_extra_prompts,
        )
        self.refresh_scene_status()
        if reload_list:
            self.reload_scene_list()
            self.select_scene_by_name(self.current_scene_dir.name)
        if not silent:
            self.statusBar().showMessage(f"Adegan {self.current_scene_dir.name} disimpan.", 3000)
        return True

    def open_scene_dialog(self, title):
        dialog = SceneTemplateDialog(self, title=title)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.get_data()

    def add_scene(self):
        if not self.ensure_project_selected():
            return
        data = self.open_scene_dialog("Tambah Adegan")
        if data is None:
            return
        project_dir = self.project_dir()
        if project_dir is None:
            QMessageBox.information(self, "Belum Ada Project", "Buka atau buat project terlebih dahulu.")
            return
        new_dir = project_dir / scene_dir_name(len(self.list_scene_dirs_current()) + 1)
        meta, z_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt = build_scene_templates(data["scene_title"], data["scene_type"], data["duration_seconds"])
        create_scene_files(new_dir, meta, z_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt)
        self.reload_scene_list()
        self.select_scene_by_name(new_dir.name)

    def insert_scene(self):
        if not self.ensure_project_selected():
            return
        current = self.current_scene_path_from_ui()
        if current is None:
            self.add_scene()
            return
        self.release_media_locks()
        data = self.open_scene_dialog("Sisipkan Adegan")
        if data is None:
            return
        insert_index = int(current.name.split("_", 1)[1])
        project_dir = self.project_dir()
        if project_dir is None:
            QMessageBox.information(self, "Belum Ada Project", "Buka atau buat project terlebih dahulu.")
            return
        scenes = self.list_scene_dirs_current()
        temp_root = project_dir / "__insert_tmp__"
        if temp_root.exists():
            shutil.rmtree(temp_root)
        temp_root.mkdir(parents=True, exist_ok=True)
        for scene in scenes:
            target_index = int(scene.name.split("_", 1)[1])
            name = scene_dir_name(target_index + 1) if target_index >= insert_index else scene.name
            duplicate_directory(scene, temp_root / name)
        meta, z_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt = build_scene_templates(data["scene_title"], data["scene_type"], data["duration_seconds"])
        create_scene_files(temp_root / scene_dir_name(insert_index), meta, z_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt)
        for scene in scenes:
            shutil.rmtree(scene)
        for child in sorted(temp_root.iterdir(), key=lambda p: p.name):
            child.rename(project_dir / child.name)
        temp_root.rmdir()
        self.reload_scene_list()
        self.select_scene_by_name(scene_dir_name(insert_index))

    def delete_scene(self):
        if not self.ensure_project_selected():
            return
        current = self.current_scene_path_from_ui()
        if current is None:
            return
        self.release_media_locks()
        reply = QMessageBox.question(self, "Hapus Adegan", f"Hapus {current.name}?", QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        shutil.rmtree(current)
        # renumber after delete to keep contiguous scene folder names
        project_dir = self.project_dir()
        if project_dir is None:
            QMessageBox.information(self, "Belum Ada Project", "Buka atau buat project terlebih dahulu.")
            return
        scenes = self.list_scene_dirs_current()
        temp_paths = []
        for idx, path in enumerate(scenes, start=1):
            temp = project_dir / f"__delete_tmp_{idx}"
            if temp.exists():
                shutil.rmtree(temp)
            path.rename(temp)
            temp_paths.append(temp)
        for idx, temp in enumerate(temp_paths, start=1):
            temp.rename(project_dir / scene_dir_name(idx))
        self.reload_scene_list()

    def add_asset_to_scene(self):
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        files, _ = QFileDialog.getOpenFileNames(self, "Pilih Aset")
        for file_path in files:
            src = Path(file_path)
            shutil.copy2(src, self.current_scene_dir / src.name)
        self.refresh_assets_and_previews()
        self.refresh_scene_status()
        self.statusBar().showMessage(f"{len(files)} aset ditambahkan ke {self.current_scene_dir.name}.", 3000)

    def select_scene_by_name(self, scene_name: str):
        for row in range(self.scene_list.count()):
            item = self.scene_list.item(row)
            if Path(item.data(Qt.UserRole)).name == scene_name:
                self.scene_list.setCurrentItem(item)
                return

    def snapshot_outputs(self, watch_dirs):
        snapshot = {}
        for directory in watch_dirs or []:
            snapshot.update(list_output_files(directory))
        return snapshot

    def collect_changed_outputs(self, watch_dirs, before_snapshot):
        changed = []
        before_snapshot = before_snapshot or {}
        for directory in watch_dirs or []:
            for path_str, mtime in list_output_files(directory).items():
                old_mtime = before_snapshot.get(path_str)
                if old_mtime is None or mtime > old_mtime + 1e-6:
                    changed.append(Path(path_str))
        changed.sort(key=lambda p: (str(p.parent).lower(), p.name.lower()))
        return changed

    def format_output_summary(self, outputs):
        if not outputs:
            return "Proses selesai tanpa file output baru yang terdeteksi."
        lines = []
        for path in outputs:
            rel_path = path.relative_to(ROOT) if ROOT in path.parents or path == ROOT else path
            lines.append(str(rel_path))
        return "File output:\n- " + "\n- ".join(lines)

    def build_z_image_skill_clipboard_text(self, positive_prompt: str, image_path: str | None = None):
        if not self.current_project_name:
            return None, "Belum ada project yang dibuka."
        if not self.current_scene_dir:
            return None, "Belum ada scene yang dipilih."

        size_label = self.z_size_input.currentText().strip()
        project_dir = self.project_dir()
        if project_dir is None:
            return None, "Belum ada project yang dibuka."

        if image_path:
            prompt_text = (
                f"Gunakan skill Image Gen untuk mengedit gambar {image_path} dengan prompt :\n"
                f"{positive_prompt}. Ukuran gambar {size_label}.\n\n"
                f"Kemudian kopikan hasil image yang dibuat direktori project {project_dir.resolve()} "
                f"dalam scene {self.current_scene_dir.name}. Jangan lupa scale ke ukuran diminta tanpa strecth."
            )
        else:
            prompt_text = (
                f"[$imagegen](C:\\Users\\brainer94\\.codex\\skills\\.system\\imagegen\\SKILL.md) {positive_prompt}. "
                f"Ukuran gambar {size_label}.\n\n"
                f"Kemudian kopikan hasil image yang dibuat direktori project {project_dir.resolve()} "
                f"dalam scene {self.current_scene_dir.name}. Jangan lupa scale ke ukuran diminta tanpa strecth."
            )
        return prompt_text, None

    def copy_z_image_skill_prompt_to_clipboard(self):
        prompt_text, error = self.build_z_image_skill_clipboard_text(self.z_positive_input.toPlainText().strip())
        if error:
            QMessageBox.information(self, "Belum Siap", error)
            return
        QApplication.clipboard().setText(prompt_text)
        self.statusBar().showMessage("Teks Image Gen disalin ke clipboard.", 3000)

    def copy_extra_image_skill_prompt_to_clipboard(self, slot_index: int):
        if slot_index < 0 or slot_index >= len(self.z_extra_positive_inputs):
            QMessageBox.information(self, "Belum Siap", "Slot prompt tambahan tidak valid.")
            return
        prompt_text, error = self.build_z_image_skill_clipboard_text(
            self.z_extra_positive_inputs[slot_index].toPlainText().strip()
        )
        if error:
            QMessageBox.information(self, "Belum Siap", error)
            return
        QApplication.clipboard().setText(prompt_text)
        self.statusBar().showMessage(f"Teks Image Gen slot {slot_index + 1} disalin ke clipboard.", 3000)

    def copy_image_edit_prompt_to_clipboard(self, slot_index: int):
        if slot_index < 0 or slot_index >= len(self.image_edit_image_inputs):
            QMessageBox.information(self, "Belum Siap", "Slot edit gambar tidak valid.")
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Siap", "Belum ada scene yang dipilih.")
            return
        image_name = str(self.image_edit_image_inputs[slot_index].currentData() or "").strip()
        if not image_name:
            QMessageBox.information(self, "Belum Siap", f"Pilih gambar awal pada Edit Gambar {slot_index + 1}.")
            return
        image_path = str((self.current_scene_dir / image_name).resolve())
        prompt_text, error = self.build_z_image_skill_clipboard_text(
            self.image_edit_prompt_inputs[slot_index].toPlainText().strip(),
            image_path=image_path,
        )
        if error:
            QMessageBox.information(self, "Belum Siap", error)
            return
        QApplication.clipboard().setText(prompt_text)
        self.statusBar().showMessage(f"Teks Image Gen edit slot {slot_index + 1} disalin ke clipboard.", 3000)

    def tail_process_log(self, max_lines=12):
        text = self.log_output.toPlainText().strip()
        if not text:
            return ""
        lines = text.splitlines()
        return "\n".join(lines[-max_lines:])

    def start_process(self, script_path: Path, args, title, watch_dirs=None):
        python_exe = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)
        self.process = QProcess(self)
        self.process_context = {
            "title": title,
            "watch_dirs": list(watch_dirs or []),
            "before_snapshot": self.snapshot_outputs(watch_dirs or []),
        }
        self.process.setProgram(str(python_exe))
        self.process.setArguments([str(script_path), *args])
        self.process.setWorkingDirectory(str(ROOT))
        self.process.readyReadStandardOutput.connect(self.on_process_stdout)
        self.process.readyReadStandardError.connect(self.on_process_stderr)
        self.process.finished.connect(self.on_process_finished)
        self.log_output.clear()
        self.append_log(f"{title} dengan {python_exe}")
        self.process.start()
        if not self.process.waitForStarted(3000):
            self.process_context = None
            QMessageBox.critical(self, "Proses Gagal", "Gagal memulai proses.")

    def confirm_run_action(self, title: str, message: str):
        reply = QMessageBox.question(self, title, message, QMessageBox.Yes | QMessageBox.No)
        return reply == QMessageBox.Yes

    def run_current_scene(self):
        if not self.confirm_run_action("Jalankan Adegan", "Jalankan adegan yang sedang dipilih?"):
            return
        self._run_current_scene()

    def _run_current_scene(self):
        if not self.ensure_project_selected():
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        if not self.ensure_server_config_loaded():
            return
        if not self.save_current_scene():
            return
        if not self.ensure_scene_is_runnable(self.current_scene_dir):
            return
        self.start_process(
            MAIN_SCRIPT,
            ["--server", self.comfyui_server_address(), "--project", self.current_project_name, "--scene", self.current_scene_dir.name],
            f"Menjalankan {self.current_scene_dir.name}",
            watch_dirs=[self.current_scene_dir],
        )

    def run_all_scenes(self):
        if not self.confirm_run_action("Jalankan Semua Adegan", "Jalankan semua adegan?"):
            return
        self._run_all_scenes()

    def _run_all_scenes(self):
        if not self.ensure_project_selected():
            return
        if not self.ensure_server_config_loaded():
            return
        if self.current_scene_dir:
            self.save_current_scene(silent=True)
        if not self.ensure_all_scenes_are_runnable():
            return
        self.start_process(
            MAIN_SCRIPT,
            ["--server", self.comfyui_server_address(), "--project", self.current_project_name],
            "Menjalankan semua adegan",
            watch_dirs=self.list_scene_dirs_current(),
        )

    def generate_initial_image_only(self):
        if not self.confirm_run_action("Buat Gambar Awal", "Buat gambar awal untuk adegan yang sedang dipilih?"):
            return
        self._generate_initial_image_only()

    def _generate_initial_image_only(self):
        if not self.ensure_project_selected():
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        if not self.ensure_server_config_loaded():
            return
        if not self.save_current_scene():
            return
        self.start_process(
            INITIAL_IMAGE_SCRIPT,
            ["--server", self.comfyui_server_address(), "--project", self.current_project_name, "--scene", self.current_scene_dir.name],
            f"Membuat gambar awal untuk {self.current_scene_dir.name}",
            watch_dirs=[self.current_scene_dir],
        )

    def run_extra_image_slot(self, slot_index: int):
        if slot_index < 0 or slot_index >= len(self.z_extra_positive_inputs):
            return
        if not self.ensure_project_selected():
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        if not self.ensure_server_config_loaded():
            return
        if not self.save_current_scene():
            return

        positive_prompt = self.z_extra_positive_inputs[slot_index].toPlainText().strip()
        if not positive_prompt:
            QMessageBox.warning(self, "Data Tidak Valid", f"Prompt Positif pada Prompt Tambahan {slot_index + 1} wajib diisi.")
            return

        self.start_process(
            INITIAL_IMAGE_SCRIPT,
            [
                "--server", self.comfyui_server_address(),
                "--project", self.current_project_name,
                "--scene", self.current_scene_dir.name,
                "--prompt-file", "z_image_extra_prompts.json",
                "--prompt-index", str(slot_index + 1),
            ],
            f"Membuat image tambahan {slot_index + 1} untuk {self.current_scene_dir.name}",
            watch_dirs=[self.current_scene_dir],
        )

    def run_image_edit_slot(self, slot_index: int):
        if slot_index < 0 or slot_index >= len(self.image_edit_image_inputs):
            return
        if not self.ensure_project_selected():
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        if not self.ensure_server_config_loaded():
            return
        if not self.save_current_scene():
            return

        source_image = str(self.image_edit_image_inputs[slot_index].currentData() or "").strip()
        prompt = self.image_edit_prompt_inputs[slot_index].toPlainText().strip()
        if not source_image:
            QMessageBox.warning(self, "Data Tidak Valid", f"Pilih gambar awal pada Edit Gambar {slot_index + 1}.")
            return
        if not prompt:
            QMessageBox.warning(self, "Data Tidak Valid", f"Prompt pada Edit Gambar {slot_index + 1} wajib diisi.")
            return

        prompt_json_path = self.current_scene_dir / "image_edit_prompt.json"
        try:
            runtime_payload = read_json_for_runtime(str(prompt_json_path), required=True)
            runtime_groups = runtime_payload.get("groups") if isinstance(runtime_payload, dict) else None
            if isinstance(runtime_groups, list) and slot_index < len(runtime_groups) and isinstance(runtime_groups[slot_index], dict):
                runtime_prompt = str(runtime_groups[slot_index].get("prompt", "")).strip()
                if runtime_prompt:
                    prompt = runtime_prompt
        except Exception as e:
            self.append_log(f"[warning] Gagal sinkronisasi prompt image edit runtime: {e}")

        model_key = str(self.image_edit_model_input.currentData() or MODEL_FLUX2).strip()
        gemini_model_id = str(self.image_edit_gemini_model_input.currentData() or MODEL_GEMINI_FLASH_05K).strip()
        args = [
            "--server", self.comfyui_server_address(),
            "--project", self.current_project_name,
            "--scene", self.current_scene_dir.name,
            "--model", model_key,
            "--source-image", source_image,
            "--prompt", prompt,
        ]
        if model_key == MODEL_GEMINI_IMAGE and gemini_model_id:
            args.extend(["--gemini-model-id", gemini_model_id])

        self.start_process(
            IMAGE_EDIT_SCRIPT,
            args,
            f"Edit gambar {slot_index + 1} untuk {self.current_scene_dir.name}",
            watch_dirs=[self.current_scene_dir],
        )

    def generate_voice_current_scene(self):
        if not self.ensure_project_selected():
            return
        if not self.confirm_run_action("Buat Voice", "Buat voice untuk adegan yang sedang dipilih?"):
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        if not self.ensure_server_config_loaded():
            return
        if not self.save_current_scene():
            return
        self.start_process(
            VOICE_SCRIPT,
            ["--server", self.comfyui_server_address(), "--project", self.current_project_name, "--scene", self.current_scene_dir.name],
            f"Membuat voice untuk {self.current_scene_dir.name}",
            watch_dirs=[self.current_scene_dir],
        )

    def generate_voice_all_scenes(self):
        if not self.ensure_project_selected():
            return
        if not self.confirm_run_action("Buat Semua Voice", "Buat voice untuk semua adegan?"):
            return
        if not self.ensure_server_config_loaded():
            return
        if self.current_scene_dir:
            self.save_current_scene(silent=True)
        self.start_process(
            VOICE_SCRIPT,
            ["--server", self.comfyui_server_address(), "--project", self.current_project_name],
            "Membuat voice untuk semua adegan",
            watch_dirs=self.list_scene_dirs_current(),
        )

    def generate_sound_current_scene(self):
        if not self.ensure_project_selected():
            return
        if not self.confirm_run_action("Buat Sound", "Buat sound untuk adegan yang sedang dipilih?"):
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        if not self.ensure_server_config_loaded():
            return
        if not self.save_current_scene():
            return
        self.start_process(
            SOUND_SCRIPT,
            ["--server", self.audio_server_address(), "--project", self.current_project_name, "--scene", self.current_scene_dir.name],
            f"Membuat sound untuk {self.current_scene_dir.name}",
            watch_dirs=[self.current_scene_dir],
        )

    def generate_sound_all_scenes(self):
        if not self.ensure_project_selected():
            return
        if not self.confirm_run_action("Buat Semua Sound", "Buat sound untuk semua adegan?"):
            return
        if not self.ensure_server_config_loaded():
            return
        if self.current_scene_dir:
            self.save_current_scene(silent=True)
        self.start_process(
            SOUND_SCRIPT,
            ["--server", self.audio_server_address(), "--project", self.current_project_name],
            "Membuat sound untuk semua adegan",
            watch_dirs=self.list_scene_dirs_current(),
        )

    def compose_current_scene(self):
        if not self.ensure_project_selected():
            return
        if not self.confirm_run_action("Compose Adegan", "Gabungkan video dan audio untuk adegan yang sedang dipilih?"):
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        if not self.save_current_scene():
            return
        self.start_process(
            COMPOSE_SCRIPT,
            ["--project", self.current_project_name, "--scene", self.current_scene_dir.name, "--no-final-merge"],
            f"Menggabungkan video dan audio untuk {self.current_scene_dir.name}",
            watch_dirs=[self.current_scene_dir, (self.project_dir() / "combined") if self.project_dir() else (API_PRODUCTION / "combined")],
        )

    def compose_all_scenes(self):
        if not self.ensure_project_selected():
            return
        if not self.confirm_run_action("Compose Semua Adegan", "Gabungkan video dan audio untuk semua adegan?"):
            return
        if self.current_scene_dir:
            self.save_current_scene(silent=True)

        music_files = []
        if MUSIC_DIR.exists():
            exts = {".m4a", ".mp3", ".wav"}
            music_files = sorted(
                [p for p in MUSIC_DIR.iterdir() if p.is_file() and p.suffix.lower() in exts],
                key=lambda p: p.name.lower(),
            )
        dialog = ComposeMusicDialog(music_files, self)
        if dialog.exec() != QDialog.Accepted:
            return
        music_file, music_volume = dialog.get_values()
        args = []
        args.extend(["--project", self.current_project_name])
        if music_file:
            args.extend(["--music-file", music_file, "--music-volume", f"{music_volume:.2f}"])

        self.start_process(
            COMPOSE_SCRIPT,
            args,
            "Menggabungkan video dan audio untuk semua adegan",
            watch_dirs=[*self.list_scene_dirs_current(), self.project_dir() / "combined" if self.project_dir() else API_PRODUCTION / "combined", MUSIC_DIR],
        )

    def cover_prompt_path(self):
        pdir = self.project_dir()
        if pdir is None:
            return None
        return pdir / "cover_prompt.json"

    def load_cover_prompt(self):
        path = self.cover_prompt_path()
        if path is None:
            return copy.deepcopy(DEFAULT_Z_IMAGE_PROMPT)
        return load_json(path, DEFAULT_Z_IMAGE_PROMPT)

    def open_cover_dialog(self):
        if not self.ensure_project_selected():
            return
        prompt_data = self.load_cover_prompt()
        dialog = CoverPromptDialog(prompt_data, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            cover_prompt = dialog.get_data()
        except ValueError as e:
            QMessageBox.warning(self, "Data Cover Tidak Valid", str(e))
            return
        cover_path = self.cover_prompt_path()
        if cover_path is None:
            QMessageBox.warning(self, "Project Tidak Valid", "Project aktif tidak valid.")
            return
        write_prompt_json(cover_path, cover_prompt)
        if not self.ensure_server_config_loaded():
            return
        if not self.confirm_run_action("Generate Cover", f"Generate `cover.png` untuk project `{self.current_project_name}`?"):
            return
        pdir = self.project_dir()
        watch_dirs = [pdir / "cover"] if pdir else []
        self.start_process(
            COVER_IMAGE_SCRIPT,
            ["--server", self.comfyui_server_address(), "--project", self.current_project_name],
            f"Membuat cover untuk project {self.current_project_name}",
            watch_dirs=watch_dirs,
        )

    def save_backup_zip(self):
        if not self.ensure_project_selected():
            return
        display_name = f"{self.current_project_name}.zip"
        if not self.confirm_run_action("Konfirmasi Save", f"Simpan backup sebagai `{display_name}`?"):
            return
        if self.current_scene_dir:
            self.save_current_scene(silent=True)
        self.start_process(
            BACKUP_SCRIPT,
            ["--project", self.current_project_name],
            f"Menyimpan backup ZIP project {self.current_project_name}",
            watch_dirs=[ROOT / "backup_production"],
        )

    def on_asset_selected(self, current, previous):
        if not current:
            self.asset_info_label.setText("Belum ada aset yang dipilih.")
            return
        asset_path = Path(current.data(Qt.UserRole))
        self.asset_info_label.setText(asset_path.name)

    def on_asset_clicked(self, item):
        if not item:
            return
        self.open_asset_preview_only(Path(item.data(Qt.UserRole)))

    def on_asset_double_clicked(self, item):
        if not item:
            return
        self.open_asset_in_viewer(Path(item.data(Qt.UserRole)))

    def open_asset_context_menu(self, position):
        item = self.asset_list.itemAt(position)
        if not item:
            return
        self.asset_list.setCurrentItem(item)
        menu = QMenu(self.asset_list)
        delete_action = QAction("Hapus", self.asset_list)
        delete_action.triggered.connect(lambda: self.delete_selected_asset(item))
        menu.addAction(delete_action)
        menu.exec(self.asset_list.mapToGlobal(position))

    def delete_selected_asset(self, item):
        if not item or not self.current_scene_dir:
            return
        asset_path = Path(item.data(Qt.UserRole))
        if not asset_path.exists():
            self.refresh_assets_and_previews()
            return
        reply = QMessageBox.question(
            self,
            "Hapus Aset",
            f"Hapus aset `{asset_path.name}`?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            if (
                self.video_player.source().toLocalFile() == str(asset_path)
                or self.audio_player.source().toLocalFile() == str(asset_path)
            ):
                self.clear_viewer()
            asset_path.unlink()
        except Exception as e:
            QMessageBox.critical(self, "Gagal Menghapus", f"Gagal menghapus aset:\n{e}")
            return
        self.refresh_assets_and_previews()
        self.refresh_scene_status()
        self.statusBar().showMessage(f"Aset {asset_path.name} dihapus.", 3000)

    def on_process_stdout(self):
        if self.process:
            self.append_log(bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace"))

    def on_process_stderr(self):
        if self.process:
            self.append_log(bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace"))

    def on_process_finished(self, exit_code, exit_status):
        self.append_log(f"\nProses selesai dengan kode keluar {exit_code}")
        context = self.process_context or {}
        if self.current_scene_dir:
            self.refresh_assets_and_previews()
            self.refresh_scene_status()
        if exit_code == 0:
            outputs = self.collect_changed_outputs(
                context.get("watch_dirs", []),
                context.get("before_snapshot", {}),
            )
            QMessageBox.information(
                self,
                "Proses Berhasil",
                f"{context.get('title', 'Proses')} berhasil.\n\n{self.format_output_summary(outputs)}",
            )
            self.statusBar().showMessage("Proses selesai.", 5000)
        else:
            tail_log = self.tail_process_log()
            message = f"{context.get('title', 'Proses')} gagal dengan kode keluar {exit_code}."
            if tail_log:
                message += f"\n\nRingkasan log terakhir:\n{tail_log}"
            QMessageBox.critical(self, "Proses Gagal", message)
            self.statusBar().showMessage("Proses gagal.", 5000)
        self.process_context = None


def main():
    app = QApplication(sys.argv)
    window = SceneEditorWindow()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
