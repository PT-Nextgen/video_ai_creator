# CLI dari Folder `api_production`

Dokumen ini menjelaskan CLI yang tersedia saat agent dijalankan dari folder `api_production`.

Asumsi kerja:
- current working directory adalah folder `api_production`
- source code repo ada di parent directory: `..`
- Python virtual environment ada di `..\.venv`

## Pola Umum

Untuk CLI yang belum punya wrapper khusus, pakai pola ini:

```powershell
..\.venv\Scripts\python.exe ..\path\to\script.py ...
```

Di Windows, penulisan yang benar tanpa spasi adalah:

```powershell
..\.venv\Scripts\python.exe ..\path\to\script.py ...
```

## CLI Paling Praktis

### 1. `project_cli.bat`

Launcher ini dibuat khusus untuk dipakai dari folder `api_production`.

File:
- `project_cli.bat`
- `project_cli.py`

Fungsi:
- membuat project baru
- membuat scene baru

Contoh:

```powershell
.\project_cli.bat --help
.\project_cli.bat create-project --project demo_project
.\project_cli.bat create-project --project demo_project --with-default-scene
.\project_cli.bat create-scene --project demo_project --scene-type wan22_i2v --title "Intro" --scene-description "Anak menemukan magnet di meja belajar." --voice-text "Halo teman-teman! Hari ini kita belajar magnet, benda seru yang bisa menarik klip kertas dan benda logam kecil di sekitar kita!" --duration 10
```

Catatan:
- launcher ini harus dijalankan dari dalam folder `api_production`
- source code utama tetap ada di `..\scripts\project_cli.py`

## CLI Utama

### 2. `main.py`

Fungsi:
- menjalankan workflow scene sesuai `scene_type`

Contoh:

```powershell
..\.venv\Scripts\python.exe ..\main.py --project apa_itu_magnet
..\.venv\Scripts\python.exe ..\main.py --project apa_itu_magnet --scene scene_1
..\.venv\Scripts\python.exe ..\main.py --project apa_itu_magnet --scene scene_1 --scene scene_2
..\.venv\Scripts\python.exe ..\main.py --server 127.0.0.1:8188 --project apa_itu_magnet
```

Argumen utama:
- `--server`, `-s`
- `--project`, `-p`
- `--scene`, `-S`
- `--loop`, `-L`

### 3. `scripts/generate_initial_image.py`

Fungsi:
- membuat gambar awal dari `z_image_prompt.json`
- bisa juga membaca `z_image_extra_prompts.json`

Contoh:

```powershell
..\.venv\Scripts\python.exe ..\scripts\generate_initial_image.py --project apa_itu_magnet --scene scene_1
..\.venv\Scripts\python.exe ..\scripts\generate_initial_image.py --server 127.0.0.1:8188 --project apa_itu_magnet --scene scene_1 --loop 5
..\.venv\Scripts\python.exe ..\scripts\generate_initial_image.py --project apa_itu_magnet --scene scene_1 --prompt-file z_image_extra_prompts.json --prompt-index 1
```

Argumen utama:
- `--server`, `-s`
- `--project`, `-p`
- `--scene`, `-S`
- `--prompt-file`
- `--prompt-index`
- `--loop`, `-L`

### 4. `scripts/generate_initial_image_gemini.py`

Fungsi:
- membuat gambar awal khusus untuk scene yang memakai model image `Gemini`

Contoh:

```powershell
..\.venv\Scripts\python.exe ..\scripts\generate_initial_image_gemini.py --project apa_itu_magnet --scene scene_1
```

### 5. `scripts/generate_voice.py`

Fungsi:
- generate voice per scene atau per project sesuai `project_settings.json.voice`

Contoh:

```powershell
..\.venv\Scripts\python.exe ..\scripts\generate_voice.py --project apa_itu_magnet --scene scene_1
..\.venv\Scripts\python.exe ..\scripts\generate_voice.py --project apa_itu_magnet
```

Argumen utama:
- `--project`, `-p`
- `--scene`, `-s`
- `--server`

Catatan:
- `--server` hanya untuk kompatibilitas lama dan tidak dipakai

### 6. `scripts/generate_sound.py`

Fungsi:
- generate sound effect dari `sound_prompt`

Contoh:

```powershell
..\.venv\Scripts\python.exe ..\scripts\generate_sound.py --project apa_itu_magnet --scene scene_1
..\.venv\Scripts\python.exe ..\scripts\generate_sound.py --project apa_itu_magnet
```

### 7. `scripts/generate_compose.py`

Fungsi:
- compose audio dan video per scene
- merge final ke `combined_all.mp4`

Contoh:

```powershell
..\.venv\Scripts\python.exe ..\scripts\generate_compose.py --project apa_itu_magnet
..\.venv\Scripts\python.exe ..\scripts\generate_compose.py --project apa_itu_magnet --scene scene_1
..\.venv\Scripts\python.exe ..\scripts\generate_compose.py --project apa_itu_magnet --music-file "..\music\Another Night (Corporate).m4a" --music-volume 1.0
```

Argumen utama:
- `--project`, `-p`
- `--scene`, `-s`
- `--speech-volume`
- `--no-final-merge`
- `--music-file`
- `--music-volume`

### 8. `scripts/generate_cover_image.py`

Fungsi:
- generate cover project dari `project_settings.json.cover`

Contoh:

```powershell
..\.venv\Scripts\python.exe ..\scripts\generate_cover_image.py --project apa_itu_magnet
..\.venv\Scripts\python.exe ..\scripts\generate_cover_image.py --server 127.0.0.1:8188 --project apa_itu_magnet
```

### 9. `scripts/generate_image_edit.py`

Fungsi:
- edit gambar dari satu scene memakai model `flux.2` atau `gemini`

Contoh:

```powershell
..\.venv\Scripts\python.exe ..\scripts\generate_image_edit.py --project apa_itu_magnet --scene scene_1 --model flux.2 --source-image input.png --prompt "Tambahkan nuansa cinematic malam"
..\.venv\Scripts\python.exe ..\scripts\generate_image_edit.py --project apa_itu_magnet --scene scene_1 --model gemini --gemini-model-id gemini-3.1-flash-image-preview --source-image input.png --prompt "Ubah menjadi gaya watercolor"
```

### 10. `backup_production.py`

Fungsi:
- backup satu project menjadi ZIP ke folder `backup_production`

Contoh:

```powershell
..\.venv\Scripts\python.exe ..\backup_production.py --project apa_itu_magnet
```

## CLI Helper Video

### 11. `scripts/generate_image_pan_video.py`

Fungsi:
- membuat video `image_pan` dari satu file gambar

Contoh:

```powershell
..\.venv\Scripts\python.exe ..\scripts\generate_image_pan_video.py --project apa_itu_magnet --scene scene_8 --image "D:\Project\video_ai_creator\api_production\apa_itu_magnet\scene_8\input.png" --width 368 --height 640 --duration 10 --direction from_right
```

### 12. `scripts/generate_image_zoom_video.py`

Fungsi:
- membuat video `image_zoom` dari satu file gambar

Contoh:

```powershell
..\.venv\Scripts\python.exe ..\scripts\generate_image_zoom_video.py --project apa_itu_magnet --scene scene_4 --image "D:\Project\video_ai_creator\api_production\apa_itu_magnet\scene_4\input.png" --width 368 --height 640 --duration 10 --zoom-direction in --focal-point center --zoom-strength 1.3
```

### 13. `scripts/generate_web_scroll_video.py`

Fungsi:
- membuat video `web_scroll` dari URL website

Status saat ini:
- script ini ada
- saat dicek langsung dengan `--help`, import gagal karena path `logging_config`
- untuk saat ini lebih aman jalankan `web_scroll` lewat `main.py` atau UI

## CLI Caption

### 14. `scripts/generate_caption.py`

Fungsi:
- burn caption ke video terbaru per scene memakai `faster-whisper`

Contoh:

```powershell
..\.venv\Scripts\python.exe ..\scripts\generate_caption.py --scene scene_1 --model base
```

Catatan penting:
- script ini saat ini tidak memakai argumen `--project`
- implementasinya masih mencari folder `scene_*` langsung di root `api_production`
- dengan struktur project-based saat ini, script ini kurang cocok dipakai langsung dari folder `api_production`
- untuk workflow normal, caption lebih aman dibiarkan berjalan otomatis lewat `main.py` atau UI

## UI

### 15. `scene_manager_ui.py`

Walaupun bukan CLI murni, ini tetap entry point penting.

Contoh menjalankan UI dari folder `api_production`:

```powershell
..\.venv\Scripts\python.exe ..\scene_manager_ui.py
```

Atau dari root repo:

```powershell
..\run_ui.bat
```

## Rekomendasi Pakai

Untuk kerja harian dari folder `api_production`, yang paling sering dipakai:
1. `.\project_cli.bat`
2. `..\main.py`
3. `..\scripts\generate_initial_image.py`
4. `..\scripts\generate_voice.py`
5. `..\scripts\generate_compose.py`

Kalau nanti wrapper untuk CLI lain ditambahkan, dokumen ini bisa diperbarui supaya command-nya makin pendek dan nyaman.
