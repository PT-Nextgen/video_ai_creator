# README-PRODUCTION

Dokumen ini adalah panduan operasional dari sisi user saat bekerja langsung di folder `api_production`.

Tujuan dokumen ini:
- menjelaskan struktur project produksi
- menjelaskan file apa yang perlu diisi
- menjelaskan alur kerja scene
- menjelaskan command yang dipakai dari folder `api_production`

Dokumen ini tidak membahas source code internal.

## Konteks Kerja

Asumsi:
- current working directory adalah folder `api_production`
- setiap project ada di `api_production/<project_name>`
- setiap scene ada di `api_production/<project_name>/scene_<n>`

Contoh:

```text
api_production/
  apa_itu_magnet/
    project_settings.json
    scene_1/
    scene_2/
    scene_3/
```

## Struktur Project

Setiap project minimal memiliki:
- `project_settings.json`
- satu atau lebih folder `scene_<n>`

Setiap scene biasanya memiliki file:
- `scene_meta.json`
- `z_image_prompt.json`
- `z_image_extra_prompts.json`
- `image_edit_prompt.json`
- `wan22_i2v_prompt.json`
- `wan22_s2v_prompt.json`
- `web_scroll_prompt.json`
- `image_pan_prompt.json`
- `image_zoom_prompt.json`
- `web_search_prompt.json`

Catatan:
- saat scene baru dibuat dari UI atau CLI, semua file JSON prompt inti langsung dibuat otomatis
- ini memudahkan pergantian `scene_type` tanpa perlu menambah file manual

## Konfigurasi Project

File utama project adalah `project_settings.json`.

Field penting:
- `project_description`
- `comfyui_server`
- `video_size.width`
- `video_size.height`
- `prompt_generation.model`
- `translate.model`
- `voice.voice_provider`
- `caption.generate_caption`
- `cover`

Fungsi masing-masing:
- `project_description`
  - deskripsi video secara keseluruhan
- `comfyui_server`
  - alamat server ComfyUI, format `host:port`
- `video_size`
  - ukuran video project
- `prompt_generation.model`
  - model untuk generate prompt bahasa Inggris
- `translate.model`
  - model untuk translasi prompt ke bahasa Inggris
- `voice.voice_provider`
  - provider voice global project
  - nilai yang didukung: `gemini`, `elevenlabs`
- `caption.generate_caption`
  - jika `true`, caption akan diburn otomatis ke video hasil
- `cover`
  - konfigurasi pembuatan cover project

## Konfigurasi Scene

File utama per scene adalah `scene_meta.json`.

Field penting:
- `scene_title`
- `scene_description`
- `scene_type`
- `duration_seconds`
- `voice_text`
- `voice_character`
- `sound_prompt`
- `sound_volume`

Fungsi masing-masing:
- `scene_title`
  - judul singkat scene
- `scene_description`
  - deskripsi visual dan konteks scene
- `scene_type`
  - tipe alur video scene
- `duration_seconds`
  - durasi target scene
- `voice_text`
  - teks TTS untuk scene
- `voice_character`
  - karakter suara scene
- `sound_prompt`
  - prompt sound effect
- `sound_volume`
  - volume sound effect saat compose

## Aturan Voice Text

Aturan operasional yang dipakai saat ini:
- `voice_text` dipakai sebagai sumber TTS
- `voice_text` dipakai juga sebagai sumber caption
- untuk workflow scene yang sedang dipakai saat ini, usahakan `voice_text` tetap ringkas agar audio tidak melebihi durasi scene

## Format Prompt

Prompt di file JSON disimpan dalam format bilingual:
- `id_old`
- `id_new`
- `en`

Arti field:
- `id_new`
  - versi terbaru dari prompt yang dilihat user di UI
- `id_old`
  - versi lama yang dipakai untuk membandingkan perubahan
- `en`
  - versi runtime bahasa Inggris

Aturan umum:
- prompt yang diedit oleh user tetap dalam Bahasa Indonesia
- saat runtime, sistem akan memakai `en`
- jika `id_old != id_new` atau `en` kosong, sistem dapat menerjemahkan ulang saat runtime

## Tipe Scene

Nilai `scene_type` yang didukung:
- `wan22_i2v`
- `wan22_s2v`
- `i2v`
- `web_scroll`
- `image_pan`
- `image_zoom`

### 1. `wan22_i2v`

Kebutuhan:
- `scene_meta.json`
- `wan22_i2v_prompt.json`
- minimal satu gambar di root folder scene

Cara kerja:
- memakai satu gambar terbaru dari root folder scene
- menghasilkan video gerak WAN dari prompt video

Catatan:
- cocok untuk scene bergaya ilustratif, naratif, dan non-teknis
- tidak ideal untuk visual yang sangat teknis atau butuh akurasi teks tinggi

### 2. `wan22_s2v`

Kebutuhan:
- `scene_meta.json`
- `wan22_s2v_prompt.json`
- minimal satu gambar di root folder scene
- minimal satu file speech berawalan `speech_`

Cara kerja:
- memakai satu gambar terbaru
- memakai satu file speech terbaru
- menghasilkan video yang mengikuti audio speech

Catatan:
- gambar awal sebaiknya menampilkan wajah manusia dengan jelas
- durasi speech harus kurang dari `19.2` detik

### 3. `i2v`

Kebutuhan:
- `scene_meta.json`
- `z_image_prompt.json`
- minimal satu gambar di root folder scene

Cara kerja:
- memakai semua gambar di root folder scene
- menyusunnya menjadi video sederhana

### 4. `web_scroll`

Kebutuhan:
- `scene_meta.json`
- `web_scroll_prompt.json`

Cara kerja:
- membuka URL lalu scroll halaman selama durasi scene

Field penting:
- `url`
- `width`
- `height`
- `duration_seconds`
- `speed`

### 5. `image_pan`

Kebutuhan:
- `scene_meta.json`
- `z_image_prompt.json`
- `image_pan_prompt.json`
- minimal satu gambar di root folder scene

Cara kerja:
- memakai satu gambar awal
- membuat gerakan pan horizontal

Field penting:
- `direction`
  - `from_right`
  - `from_left`

### 6. `image_zoom`

Kebutuhan:
- `scene_meta.json`
- `image_zoom_prompt.json`
- minimal satu gambar di root folder scene

Cara kerja:
- memakai satu gambar awal
- membuat gerakan zoom in atau zoom out

Field penting:
- `zoom_direction`
  - `in`
  - `out`
- `focal_point`
- `zoom_strength`

## File Prompt Utama

### `z_image_prompt.json`

Dipakai untuk membuat gambar awal.

Field utama:
- `image_model`
- `gemini_model_id`
- `positive_prompt`
- `negative_prompt`
- `width`
- `height`
- `use_random_seed`
- `seed`
- `use_lora`
- `lora_name`
- `strength_model`

Model image yang didukung:
- `z-image turbo`
- `flux.2`
- `flux.2 klein 9b`
- `gemini`

### `wan22_i2v_prompt.json`

Dipakai untuk membuat video `wan22_i2v`.

Field utama:
- `duration_seconds`
- `positive_prompt_one`
- `negative_prompt_one`
- `positive_prompt_two`
- `negative_prompt_two`
- `width`
- `height`
- `use_lora`

Catatan:
- untuk durasi `10` detik, umumnya dipakai dua pasang prompt

### `wan22_s2v_prompt.json`

Dipakai untuk membuat video `wan22_s2v`.

Field utama:
- `positive_prompt`
- `negative_prompt`
- `width`
- `height`
- `cfg`

### `image_pan_prompt.json`

Field utama:
- `width`
- `height`
- `direction`

### `image_zoom_prompt.json`

Field utama:
- `width`
- `height`
- `zoom_direction`
- `focal_point`
- `zoom_strength`

### `web_scroll_prompt.json`

Field utama:
- `url`
- `width`
- `height`
- `duration_seconds`
- `speed`

## Alur Kerja Produksi

Urutan kerja yang umum:

1. Buat project
2. Buat scene
3. Isi `project_settings.json`
4. Isi `scene_meta.json` per scene
5. Isi prompt sesuai tipe scene
6. Generate gambar awal jika scene membutuhkannya
7. Generate voice jika `voice_text` dipakai
8. Generate sound jika perlu
9. Jalankan scene untuk membuat video
10. Compose semua scene menjadi video final

## Command dari Folder `api_production`

### 1. Buat project dan scene

Launcher yang paling praktis:

```powershell
.\project_cli.bat --help
```

Contoh:

```powershell
.\project_cli.bat create-project --project demo_project
.\project_cli.bat create-project --project demo_project --with-default-scene
.\project_cli.bat create-scene --project demo_project --scene-type wan22_i2v --title "Intro" --scene-description "Anak menemukan magnet di meja belajar." --voice-text "Halo teman-teman! Hari ini kita belajar magnet, benda seru yang bisa menarik klip kertas dan benda logam kecil di sekitar kita!" --duration 10
```

### 2. Generate gambar awal

```powershell
..\.venv\Scripts\python.exe ..\scripts\generate_initial_image.py --project demo_project --scene scene_1
```

Untuk model Gemini:

```powershell
..\.venv\Scripts\python.exe ..\scripts\generate_initial_image_gemini.py --project demo_project --scene scene_1
```

### 3. Generate voice

```powershell
..\.venv\Scripts\python.exe ..\scripts\generate_voice.py --project demo_project --scene scene_1
..\.venv\Scripts\python.exe ..\scripts\generate_voice.py --project demo_project
```

### 4. Generate sound

```powershell
..\.venv\Scripts\python.exe ..\scripts\generate_sound.py --project demo_project --scene scene_1
```

### 5. Jalankan scene / render video

```powershell
..\.venv\Scripts\python.exe ..\main.py --project demo_project --scene scene_1
..\.venv\Scripts\python.exe ..\main.py --project demo_project
```

### 6. Compose video final

```powershell
..\.venv\Scripts\python.exe ..\scripts\generate_compose.py --project demo_project
..\.venv\Scripts\python.exe ..\scripts\generate_compose.py --project demo_project --music-file "..\music\Another Night (Corporate).m4a" --music-volume 1.0
```

### 7. Backup project

```powershell
..\.venv\Scripts\python.exe ..\backup_production.py --project demo_project
```

## Output yang Umum Dihasilkan

Contoh output yang biasanya muncul di folder scene:
- gambar hasil generate
- file speech berawalan `speech_`
- file sound `.wav`
- video hasil scene `.mp4`

Contoh output project:
- `combined/`
- `combined_all.mp4`
- `cover/cover.png`

## Kebutuhan Environment

Yang biasanya dibutuhkan:
- Python virtual environment di `..\.venv`
- `ffmpeg` dan `ffprobe` tersedia di `PATH`
- API key yang dibutuhkan ada di `..\keys.cfg`

Contoh isi `keys.cfg`:

```ini
GEMINIKEY=isi_api_key_gemini
ELEVENLABSKEY=isi_api_key_elevenlabs
FIRECRAWLKEY=isi_api_key_firecrawl
```

## Rekomendasi Praktis

Untuk operasi harian dari folder `api_production`, jalur paling aman biasanya:

1. buat project dan scene dengan `.\project_cli.bat`
2. isi metadata dan prompt per scene
3. generate voice per scene
4. generate gambar awal
5. jalankan `main.py` untuk render scene
6. jalankan `generate_compose.py` untuk hasil final

## Dokumen Tambahan

Jika butuh daftar command yang lebih teknis, lihat juga:
- `CLI.md`
