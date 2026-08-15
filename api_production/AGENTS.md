# CLI untuk Project dan Scene

Dokumen ini menjelaskan cara memakai CLI untuk membuat project baru dan menambahkan scene baru di `api_production`.

## 1. Membuat Project

Gunakan script:

```powershell
.\.venv\Scripts\python.exe scripts\project_cli.py create-project --project <nama_project>
```

Contoh:

```powershell
.\.venv\Scripts\python.exe scripts\project_cli.py create-project --project demo_project
```

Opsi yang umum dipakai:

- `--description` untuk deskripsi project
- `--width` dan `--height` untuk ukuran video
- `--comfyui-server` untuk alamat server ComfyUI
- `--prompt-generation-provider` untuk provider prompt generation (`gemini` atau `llama.cpp`)
- `--prompt-generation-model` untuk model prompt generation
- `--prompt-generation-host` dan `--prompt-generation-port` untuk konfigurasi llama.cpp
- `--voice-provider` untuk provider voice default (`gemini` atau `elevenlabs`)
- `--generate-caption` untuk aktif atau nonaktifkan caption otomatis
- `--with-default-scene` untuk langsung membuat `scene_1` saat project dibuat

Contoh project dengan konfigurasi lengkap:

```powershell
.\.venv\Scripts\python.exe scripts\project_cli.py create-project --project demo_project --description "Video edukasi anak" --width 360 --height 640 --comfyui-server nextgenserver:8188 --prompt-generation-provider llama.cpp --prompt-generation-model qwen3.6:35b-a3b-uc-q4_K_M --prompt-generation-host nextgenserver --prompt-generation-port 8080 --voice-provider gemini --generate-caption true
```

## 2. Membuat Scene

Gunakan script:

```powershell
.\.venv\Scripts\python.exe scripts\project_cli.py create-scene --project <nama_project> --scene-type <tipe_scene>
```

Contoh:

```powershell
.\.venv\Scripts\python.exe scripts\project_cli.py create-scene --project demo_project --scene-type wan22_i2v --title "Intro Magnet" --scene-description "Anak menemukan magnet di meja belajar." --voice-text "Halo teman-teman! Hari ini kita belajar magnet." --duration 10
```

Argumen yang umum dipakai:

- `--project` untuk nama project di `api_production`
- `--scene-type` untuk tipe scene
- `--title` untuk judul scene
- `--scene-description` untuk deskripsi scene
- `--voice-text` untuk naskah suara
- `--duration` untuk durasi scene dalam detik

Tipe scene yang didukung:

- `wan22_i2v`
- `wan22_t2v_i2v`
- `minimax-h3_t2v_i2v`
- `minimax-h3_i2v`
- `wan22_t2v_batch`
- `wan22_s2v`
- `i2v`
- `web_scroll`
- `image_pan`
- `image_zoom`

Contoh tambahan:

```powershell
.\.venv\Scripts\python.exe scripts\project_cli.py create-scene --project demo_project --scene-type wan22_t2v_i2v --title "Intro Gerak" --scene-description "Pembuka dua tahap T2V lalu I2V." --voice-text "Halo teman-teman! Hari ini kita mulai dengan gerakan singkat." --duration 15
```

```powershell
.\.venv\Scripts\python.exe scripts\project_cli.py create-scene --project demo_project --scene-type minimax-h3_t2v_i2v --title "Intro MiniMax H3" --scene-description "Scene MiniMax H3 T2V lalu I2V." --voice-text "Halo teman-teman! Kita mulai dengan gerakan yang halus." --duration 20
```

```powershell
.\.venv\Scripts\python.exe scripts\project_cli.py create-scene --project demo_project --scene-type minimax-h3_i2v --title "Intro MiniMax H3 I2V" --scene-description "Scene MiniMax H3 I2V dari gambar referensi." --voice-text "Halo teman-teman! Kita mulai dari gambar referensi." --duration 10
```

```powershell
.\.venv\Scripts\python.exe scripts\project_cli.py create-scene --project demo_project --scene-type image_zoom --title "Zoom Intro" --scene-description "Close-up magnet merah biru." --voice-text "Halo teman-teman! Hari ini kita belajar magnet." --duration 10
```
