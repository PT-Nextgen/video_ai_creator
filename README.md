## Overview

Proyek ini menjalankan pipeline pembuatan konten video per scene dari folder `api_production/scene_*`.

## Virtual Environment

Virtual environment proyek memakai `.venv` di root repo.

Membuat dan install dependency:
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Aktivasi:
```powershell
.\.venv\Scripts\Activate.ps1
```

```cmd
.\.venv\Scripts\activate.bat
```

```bash
source ./.venv/bin/activate
```

## Scene Structure

Folder scene berada di `api_production/scene_<n>/`.

File utama:
- `scene_meta.json`
- `z_image_prompt.json`
- `wan22_i2v_prompt.json`
- `wan22_s2v_prompt.json`

Field utama:
- `scene_meta.json`
  - `scene_title`
  - `scene_type`
  - `duration_seconds`
  - `voice_text`
  - `voice_provider`
  - `elevenlabs_voice_id`
  - `elevenlabs_model_id`
  - `generate_caption`
  - `edgetts_voice_id`
  - `sound_prompt`
  - `sound_volume`
- `z_image_prompt.json`
  - `image_model`
  - `positive_prompt`
  - `negative_prompt`
  - `width`
  - `height`
  - `use_random_seed`
  - `seed`
  - `use_lora`
  - `lora_name`
  - `strength_model`
  - `json_api`
- `wan22_i2v_prompt.json`
  - `positive_prompt_one` sampai `positive_prompt_five`
  - `negative_prompt_one` sampai `negative_prompt_five`
  - `width`
  - `height`
  - `use_lora`
  - `lora_high_name`
  - `lora_high_strength`
  - `lora_low_name`
  - `lora_low_strength`
  - `json_api`
- `wan22_s2v_prompt.json`
  - `positive_prompt`
  - `negative_prompt`
  - `width`
  - `height`
  - `cfg`
  - `json_api`

Kebutuhan per `scene_type`:
- `default`
  - membutuhkan `scene_meta.json`, `z_image_prompt.json`, dan `wan22_i2v_prompt.json`
- `wan22_i2v`
  - membutuhkan `scene_meta.json`, `wan22_i2v_prompt.json`, dan minimal satu gambar di root folder scene
- `wan22_s2v`
  - membutuhkan `scene_meta.json`, `wan22_s2v_prompt.json`, minimal satu gambar di root folder scene, dan minimal satu file audio speech berawalan `speech_` di root folder scene
  - `voice_provider` wajib dipilih
  - `voice_text` wajib diisi
- `i2v`
  - membutuhkan `scene_meta.json` dan minimal satu gambar di root folder scene

Catatan sumber image:
- `default`
  - image dibuat dari `z_image_prompt.json`, lalu hasilnya dipakai untuk WAN
- `wan22_i2v`
  - memakai satu gambar terbaru dari root folder scene
- `wan22_s2v`
  - memakai satu gambar terbaru dan satu file audio speech terbaru dari root folder scene
  - file speech harus berawalan `speech_`
  - durasi speech harus kurang dari `19.2` detik
  - hasil video dipotong mengikuti durasi speech dengan tambahan maksimal `4 frame`
- `i2v`
  - memakai semua gambar dari root folder scene

Catatan voice dan caption:
- `voice_text`
  - dipakai sebagai sumber TTS
  - dipakai juga sebagai sumber caption
- `elevenlabs_model_id`
  - model ElevenLabs per scene
  - nilai yang didukung:
    - `eleven_v3`
    - `eleven_multilingual_v2`
    - `eleven_flash_v2_5`
- `generate_caption`
  - boolean
  - default `true`
  - jika aktif, video yang selesai dibuat akan langsung diburn caption otomatis
  - caption tidak membuat file `__captioned` tambahan pada alur otomatis; video final ditimpa dengan versi yang sudah bercaption

Catatan trimming video:
- pemotongan video mengikuti durasi speech hanya berlaku untuk `scene_type=wan22_s2v`
- scene type lain tidak dipotong otomatis mengikuti speech

## Server Config

Konfigurasi server disimpan di `server_config.json`.

Struktur:
```json
{
  "comfyui": {
    "host": "127.0.0.1",
    "port": 8188
  },
  "audio": {
    "host": "127.0.0.1",
    "port": 7777
  }
}
```

Pemakaian:
- `comfyui`
  - dipakai oleh `main.py`, `scripts/generate_initial_image.py`, `scripts/generate_voice.py`, dan `scene_manager_ui.py`
- `audio`
  - dipakai oleh `scripts/generate_sound.py`

Di UI, konfigurasi ini diubah melalui dialog `Konfigurasi Server`.

## Main Runner

Script utama: `main.py`

Fungsi:
- `scene_type=default`
  - generate image dari `z_image_prompt.json`
  - download image
  - upload image ke ComfyUI
  - generate video dari `wan22_i2v_prompt.json`
  - jika `generate_caption=true`, burn caption ke video hasil
- `scene_type=wan22_i2v`
  - ambil satu gambar terbaru dari root folder scene
  - upload image ke ComfyUI
  - generate video dari `wan22_i2v_prompt.json`
  - jika `generate_caption=true`, burn caption ke video hasil
- `scene_type=wan22_s2v`
  - ambil satu gambar terbaru dari root folder scene
  - ambil satu file audio speech terbaru dari root folder scene
  - upload image dan audio ke ComfyUI
  - generate video dari `wan22_s2v_prompt.json`
  - potong hasil video sesuai durasi speech dengan tambahan maksimal `4 frame`
  - jika `generate_caption=true`, burn caption ke video hasil setelah trim
- `scene_type=i2v`
  - ambil semua gambar dari root folder scene
  - compose gambar menjadi video sederhana
  - jika `generate_caption=true`, burn caption ke video hasil

Argumen:
- `--server`, `-s`
  - ComfyUI server `host:port`
- `--scene`, `-S`
  - nama scene, repeatable
- `--loop`, `-L`
  - jumlah loop, minimal `1`

Contoh:
```powershell
.\.venv\Scripts\python.exe main.py --server 127.0.0.1:8188
.\.venv\Scripts\python.exe main.py --server 127.0.0.1:8188 --scene scene_1
.\.venv\Scripts\python.exe main.py --server 127.0.0.1:8188 --scene scene_1 --scene scene_2
```

## Scene Manager UI

Script: `scene_manager_ui.py`

Fungsi utama:
- menampilkan daftar scene di `api_production/`
- drag-and-drop untuk reorder scene
- tambah, sisipkan, dan hapus scene
- edit metadata scene
- edit prompt image
- edit prompt WAN
- edit prompt WAN22 S2V
- pilih model ElevenLabs:
  - `Eleven v3`
  - `Eleven Multilingual v2`
  - `Eleven Flash v2.5`
- aktif/nonaktif caption otomatis per scene lewat checkbox `Generate Caption`
- edit ukuran image dan WAN
- edit ukuran WAN22 S2V
- edit `CFG` untuk WAN22 S2V
- edit pengaturan seed image
- edit Lora image
- edit Lora WAN High dan Low
- pilih langkah WAN `4 langkah` atau `20 langkah`
- pilih model image:
  - `Z-Image Turbo`
  - `Flux.2`
  - `Flux.2 Klein 9B`
- menampilkan aset media per scene
- buka aset ke viewer dengan klik ganda
- hapus aset dari menu klik kanan
- jalankan proses image, scene, voice, sound, dan compose
- menampilkan log proses
- mengubah konfigurasi server lewat dialog

Perilaku UI:
- `Status Adegan` menampilkan masalah validasi scene aktif
- `Jalankan Adegan` dan `Jalankan Semua Adegan` diblok jika masih ada scene bermasalah
- `voice` dan `sound` bersifat opsional
- `voice` hanya wajib jika `voice_provider` dipilih
- `sound_prompt` tidak wajib
- `Generate Caption` default aktif untuk scene baru
- caption tidak lagi dibuat lewat tombol terpisah; caption berjalan otomatis setelah video selesai dibentuk jika `Generate Caption` aktif
- untuk `wan22_s2v`, tab `WAN22 S2V` menyediakan:
  - `Ukuran`
  - `CFG`
  - `Prompt Positif`
  - `Prompt Negatif`
- setelah proses selesai dari UI, akan muncul popup:
  - informasi keberhasilan beserta file output yang terdeteksi
  - atau ringkasan error jika proses gagal

Menjalankan UI:
```powershell
.\.venv\Scripts\python.exe scene_manager_ui.py
```

## Image Models

Implementasi domain image:
- `z_image/z_image.py`
- `flux2/flux2.py`

Model yang tersedia:
- `Z-Image Turbo`
  - template normal: `api_template/z_image_api.json`
  - template Lora: `api_template/z_image_lora_api.json`
  - punya positive dan negative prompt
- `Flux.2`
  - template normal: `api_template/flux2_api.json`
  - template Lora: `api_template/flux2_lora_api.json`
  - tidak memakai negative prompt
- `Flux.2 Klein 9B`
  - template normal: `api_template/flux2_k9_api.json`
  - template Lora: `api_template/flux2_k9_lora_api.json`
  - memakai positive dan negative prompt

Resolusi image yang tersedia:
- `368x640`
- `480x848`
- `720x1280`
- `640x368`
- `848x480`
- `1280x720`

## WAN Workflow

Implementasi domain WAN:
- `wan22_i2v/wan22_i2v.py`
- `wan22_s2v/wan22_s2v.py`

Template WAN:
- normal `4 langkah`
  - `api_template/wan22_i2v_4steps_api.json`
- normal `20 langkah`
  - `api_template/wan22_i2v_api.json`
- Lora `4 langkah`
  - `api_template/wan22_i2v_4steps_lora_api.json`
- Lora `20 langkah`
  - `api_template/wan22_i2v_lora_api.json`

Resolusi WAN yang tersedia:
- `368x640`
- `480x848`
- `720x1280`
- `640x368`
- `848x480`
- `1280x720`

Lora WAN:
- `Lora High`
  - nama file dan kekuatan bisa diatur dari UI
- `Lora Low`
  - nama file dan kekuatan bisa diatur dari UI

## WAN22 S2V Workflow

Implementasi domain WAN22 S2V:
- `wan22_s2v/wan22_s2v.py`

Template WAN22 S2V dipilih otomatis dari durasi speech:
- `< 4.8 detik`
  - `api_template/wan22_s2v_b1_api.json`
- `4.8 detik` sampai kurang dari `9.6 detik`
  - `api_template/wan22_s2v_b2_api.json`
- `9.6 detik` sampai kurang dari `14.4 detik`
  - `api_template/wan22_s2v_b3_api.json`
- `14.4 detik` sampai kurang dari `19.2 detik`
  - `api_template/wan22_s2v_b4_api.json`

Resolusi WAN22 S2V yang tersedia:
- `480x848`
- `720x1280`
- `848x480`
- `1280x720`

Pengaturan WAN22 S2V:
- `negative prompt` didukung
- `cfg` tersedia dari `1.0` sampai `6.0`
  - default `2.0`
- node penting:
  - image input di node `52`
  - audio input di node `58`
  - ukuran di node `93`
  - `cfg` di node `105`

## Generate Initial Image

Script: `scripts/generate_initial_image.py`

Fungsi:
- membaca `z_image_prompt.json`
- membangun workflow image sesuai model yang dipilih
- mengirim workflow ke ComfyUI
- mendownload image hasil ke folder scene

Contoh:
```powershell
.\.venv\Scripts\python.exe scripts\generate_initial_image.py --server 127.0.0.1:8188 --scene scene_1
```

## Voice dan Sound

### Generate Voice

Script: `scripts/generate_voice.py`

Fungsi:
- membaca `scene_meta.json`
- memilih engine voice otomatis dari `voice_provider`
- `edgetts` memakai ComfyUI
- `elevenlabs` memakai API ElevenLabs
- model ElevenLabs dibaca dari `elevenlabs_model_id`
- file output voice selalu memakai awalan `speech_`

Contoh:
```powershell
.\.venv\Scripts\python.exe scripts\generate_voice.py --server 127.0.0.1:8188 --scene scene_1
```

Konfigurasi key:
- `ELEVENLABSKEY` dibaca dari `keys.cfg` di root project

Contoh `keys.cfg`:
```ini
ELEVENLABSKEY=isi_api_key_elevenlabs
AUDIOCRAFTKEY=isi_api_key_audiocraft
```

### Generate Sound

Script: `scripts/generate_sound.py`

Fungsi:
- membaca `sound_prompt` dan `duration_seconds` dari `scene_meta.json`
- request audio ke audio server
- menyimpan hasil WAV ke folder scene

Catatan:
- membaca `keys.cfg` di root project untuk `AUDIOCRAFTKEY`

Contoh:
```powershell
.\.venv\Scripts\python.exe scripts\generate_sound.py --server 127.0.0.1:7777 --scene scene_1
```

## Caption Otomatis

Script pendukung: `scripts/generate_caption.py`

Fungsi:
- membaca `voice_text` dari `scene_meta.json`
- membersihkan audio tags seperti `[warmly]` agar tidak ikut tampil di subtitle
- memakai `faster-whisper` di CPU untuk membantu timing caption
- membagi caption menjadi beberapa potongan pendek
- burn subtitle langsung ke video final

Perilaku:
- caption berjalan otomatis setelah video scene selesai dibuat jika `generate_caption=true`
- caption juga diterapkan pada output `Compose Adegan`
- sumber teks caption selalu dari `voice_text`
- file `.caption.srt` disimpan di samping video yang dicaption

Catatan:
- `faster-whisper` akan mengunduh model saat pertama kali dipakai
- model default caption saat ini adalah `base`

## Compose Video

Script: `scripts/generate_compose.py`

Fungsi:
- mencari file video dan audio dalam scene
- merge video dan audio dengan `ffmpeg` / `ffprobe`
- menulis output MP4 final ke folder `api_production/combined`
- jika `generate_caption=true`, output scene di `combined` langsung diburn caption otomatis

Di UI:
- tersedia tombol `Compose Adegan`
- tersedia tombol `Compose Semua Adegan`

Contoh:
```powershell
.\.venv\Scripts\python.exe scripts\generate_compose.py --scene scene_1
.\.venv\Scripts\python.exe scripts\generate_compose.py --scene scene_1 --scene scene_2
```

Catatan:
- `ffmpeg` dan `ffprobe` harus tersedia di `PATH`

## Logging

File logging utama:
- `logging_config.py`

Log runtime default:
- `content_creation.log`
