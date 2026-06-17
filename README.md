## Overview

Proyek ini menjalankan pipeline pembuatan konten video per scene berbasis project dari folder `api_production/<project_name>/scene_*`.

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

Folder scene berada di `api_production/<project_name>/scene_<n>/`.

File utama:
- `project_settings.json`
- `scene_meta.json`
- `z_image_prompt.json`
- `z_image_extra_prompts.json`
- `image_edit_prompt.json`
- `wan22_t2v_prompt.json` (untuk `wan22_t2v_i2v` dan `wan22_t2v_batch`)
- `wan22_t2v_batch_extra_prompts.json` (untuk `wan22_t2v_batch`)
- `wan22_s2v_prompt.json`
- `wan22_i2v_prompt.json` (untuk `wan22_i2v` dan stage 2 `wan22_t2v_i2v`)
- `web_scroll_prompt.json` (untuk `web_scroll`)
- `image_pan_prompt.json` (untuk `image_pan`)
- `image_zoom_prompt.json` (untuk `image_zoom`)
- `web_search_prompt.json` (untuk `i2v`, `image_pan`, `image_zoom`)

Catatan pembuatan file scene:
- saat membuat scene baru, baik dari UI maupun CLI, semua file JSON prompt inti di atas langsung dibuat otomatis
- tujuannya agar scene bisa langsung diganti `scene_type` tanpa perlu membuat file JSON tambahan secara manual

Catatan format prompt:
- prompt yang tampil di UI selalu memakai nilai `id_new`
- di JSON, field prompt disimpan sebagai object bilingual:
  - `id_old`
  - `id_new`
  - `en`
- `id_old` dan `id_new` selalu disamakan oleh runtime; kalau salah satu kosong, yang ada akan disalin ke yang kosong
- `en` adalah versi Inggris untuk runtime
- prompt generation dan translate memakai konfigurasi yang sama di `project_settings.json.prompt_generation`
- provider `gemini` memakai default model API tanpa setting `temperature`
- provider `ollama` memakai mode thinking dengan parameter hardcoded:
  - `temperature=1`
  - `top_k=20`
  - `top_p=0.95`
  - `presence_penalty=1.5`
  - `repeat_penalty=1`
  - `draft_num_predict=4`
- saat `Save` di UI, prompt hanya disimpan ke format bilingual dan tidak langsung diterjemahkan

Field utama:
- `scene_meta.json`
  - `scene_title`
  - `scene_description` (wajib)
  - `scene_type`
  - `duration_seconds`
  - `voice_text`
  - `voice_character`
  - `sound_prompt`
  - `sound_volume`
- `project_settings.json`
  - `project_description`
  - `video_size.width`
  - `video_size.height`
  - `prompt_generation.provider`
  - `prompt_generation.model`
  - `prompt_generation.host` dan `prompt_generation.port` untuk Ollama
  - `voice.voice_provider` (`gemini` / `elevenlabs`)
  - `caption.generate_caption`
  - `cover` (struktur sama seperti `z_image_prompt.json`)
- `z_image_prompt.json`
  - `image_model`
  - `gemini_model_id` (khusus saat `image_model=gemini`)
  - `positive_prompt`
  - `negative_prompt`
  - `width`
  - `height`
  - `use_random_seed`
  - `seed`
  - `lora_name`
  - `strength_model`

Nilai `image_model` yang didukung:
- `z-image turbo`
- `flux.2`
- `flux.2 klein 9b`
- `gemini`
- `wan22_i2v_prompt.json`
  - `duration_seconds` (`5` / `10`)
  - `positive_prompt_one` sampai `positive_prompt_two`
  - `negative_prompt_one` sampai `negative_prompt_two`
  - `width`
  - `height`
  - `lora_high_name`
  - `lora_high_strength`
  - `lora_low_name`
  - `lora_low_strength`
  - `lora_high_name_2`
  - `lora_high_strength_2`
  - `lora_low_name_2`
  - `lora_low_strength_2`
- `wan22_t2v_prompt.json`
  - `positive_prompt`
  - `negative_prompt`
  - `width`
  - `height`
  - `lora_high_name`
  - `lora_high_strength`
  - `lora_low_name`
  - `lora_low_strength`
  - `lora_high_name_2`
  - `lora_high_strength_2`
  - `lora_low_name_2`
  - `lora_low_strength_2`
- `wan22_t2v_batch_extra_prompts.json`
  - `groups` berisi 3 item
  - setiap item:
    - `positive_prompt`
    - `negative_prompt`
- `wan22_s2v_prompt.json`
  - `positive_prompt`
  - `negative_prompt`
  - `width`
  - `height`
  - `cfg`
- `web_scroll_prompt.json`
  - `url`
  - `width`
  - `height`
  - `duration_seconds`
  - `speed`
- `image_pan_prompt.json`
  - `width` (portrait only)
  - `height` (portrait only)
  - `direction` (`from_right` / `from_left`)
- `image_zoom_prompt.json`
  - `width`
  - `height`
  - `zoom_direction` (`in` / `out`)
  - `focal_point` (`center`, `top_left`, `top_center`, `top_right`, `center_left`, `center_right`, `bottom_left`, `bottom_center`, `bottom_right`)
  - `zoom_strength` (`1.0` sampai `1.5`)
- `image_edit_prompt.json`
  - `image_model` (`flux.2` / `gemini`)
  - `gemini_model_id` (khusus saat `image_model=gemini`)
  - `groups` (3 grup edit)
    - `source_image`
    - `prompt`  
      disimpan sebagai object bilingual `id_old` / `id_new` / `en`

Kebutuhan prompt per `scene_type`:
- `wan22_i2v`
  - membutuhkan `scene_meta.json`, `wan22_i2v_prompt.json`, dan minimal satu gambar di root folder scene
- `wan22_t2v_i2v`
  - membutuhkan `scene_meta.json`, `wan22_t2v_prompt.json`, dan `wan22_i2v_prompt.json` (isi WAN22_I2V tetap seperti scene `wan22_i2v` biasa)
  - durasi scene hanya `5`, `10`, atau `15`
  - jika durasi `5`, hanya stage `WAN22_T2V` yang dijalankan
  - jika durasi `10` atau `15`, stage `WAN22_T2V` dijalankan dulu lalu frame terakhir (frame ke 81) dipakai sebagai input untuk stage `WAN22_I2V`
- `wan22_t2v_batch`
  - membutuhkan `scene_meta.json`, `wan22_t2v_prompt.json`, dan `wan22_t2v_batch_extra_prompts.json`
  - durasi scene hanya `5` atau `10`
  - stage `WAN22_T2V` dijalankan satu per satu untuk prompt utama dan setiap prompt tambahan yang terisi
  - jumlah video total = prompt utama + jumlah slot `Prompt Tambahan` yang terisi
  - jumlah frame per video dihitung dengan `ceil((duration * 16) / total_video)`
  - seluruh video hasil stage `WAN22_T2V` digabung menjadi satu video final
- `wan22_s2v`
  - membutuhkan `scene_meta.json`, `wan22_s2v_prompt.json`, minimal satu gambar di root folder scene, dan minimal satu file audio speech berawalan `speech_` di root folder scene
  - `voice_text` wajib diisi
- semua `scene_type`
  - `scene_title` dan `scene_description` wajib diisi
- `i2v`
  - membutuhkan `scene_meta.json`, `z_image_prompt.json` (untuk ukuran target video), dan minimal satu gambar di root folder scene
- `web_scroll`
  - membutuhkan `scene_meta.json` dan `web_scroll_prompt.json`
  - `url` wajib diisi dan harus valid (`http://` atau `https://`)
  - `duration_seconds` wajib angka desimal `0.0` sampai `20.0` (kelipatan `0.1`)
  - `speed` wajib bilangan bulat `1` sampai `5`
- `image_pan`
  - membutuhkan `scene_meta.json`, `z_image_prompt.json`, dan minimal satu gambar di root folder scene
  - `width`/`height` pada `image_pan_prompt.json` wajib portrait (tinggi > lebar)
  - durasi diambil dari `scene_meta.duration_seconds`
  - `direction` wajib `from_right` atau `from_left`
- `image_zoom`
  - membutuhkan `scene_meta.json`, `image_zoom_prompt.json`, dan minimal satu gambar di root folder scene
  - `width`/`height` pada `image_zoom_prompt.json` bebas mengikuti rasio target video
  - durasi diambil dari `scene_meta.duration_seconds`
  - `zoom_direction` wajib `in` atau `out`
  - `focal_point` wajib salah satu nilai yang didukung di `image_zoom_prompt.json`
  - `zoom_strength` wajib di antara `1.0` sampai `1.5`

Catatan sumber image:
- `wan22_i2v`
  - memakai satu gambar terbaru dari root folder scene
  - durasi gerak WAN mengikuti `wan22_i2v_prompt.json.duration_seconds` (`5` / `10`)
- `wan22_t2v_i2v`
  - stage `WAN22_T2V` selalu dijalankan terlebih dahulu
  - jika durasi scene `5`, hasil akhir langsung dari stage `WAN22_T2V`
  - jika durasi scene `10` atau `15`, frame terakhir dari video T2V (frame ke 81) dipakai sebagai input image untuk stage `WAN22_I2V`
  - durasi stage `WAN22_I2V` otomatis menjadi `5` untuk scene `10` detik dan `10` untuk scene `15` detik
- `wan22_t2v_batch`
  - stage `WAN22_T2V` dijalankan untuk prompt utama dan setiap prompt tambahan yang terisi
  - frame per video dihitung dengan `ceil((duration * 16) / total_video)`
  - semua hasil video digabung menjadi video final
  - prompt tambahan yang kosong dilewati
- `wan22_s2v`
  - memakai satu gambar terbaru dan satu file audio speech terbaru dari root folder scene
  - file speech harus berawalan `speech_`
  - durasi speech harus kurang dari `19.2` detik
  - hasil video dipotong mengikuti durasi speech dengan tambahan maksimal `4 frame`
- `i2v`
  - memakai semua gambar dari root folder scene
- `web_scroll`
  - membuat video dengan membuka URL website lalu scroll dari atas ke bawah selama durasi
  - jika output portrait, browser dirender sebagai mobile browser (emulasi)
  - jika output landscape, browser dirender sebagai desktop browser (non-mobile)
  - mode default `stable_pan` direkomendasikan untuk hasil scroll yang lebih halus
  - capture halaman panjang dibatasi otomatis agar proses tetap stabil
  - fps mengikuti scene type `i2v` (`16`)
- `image_pan`
  - membuat video dari satu gambar awal dengan pan horizontal sesuai arah (`from_right` / `from_left`)
  - pan selalu menempuh penuh dari sisi ke sisi dalam durasi scene
  - frame selalu mengikuti tinggi penuh gambar sumber (full height), lalu bergerak ke samping
  - mode default `stable_pan` direkomendasikan untuk gerakan yang lebih halus
  - fps mengikuti scene type `i2v` (`16`)
- `image_zoom`
  - membuat video dari satu gambar awal dengan zoom in atau zoom out sesuai `zoom_direction`
  - titik fokus zoom mengikuti `focal_point` agar anchor zoom tetap konsisten
  - `zoom_strength` mengatur seberapa jauh zoom bergerak dalam rentang `1.0` sampai `1.5`
  - mode default `stable_pan` direkomendasikan untuk hasil yang lebih stabil
  - fps mengikuti scene type `i2v` (`16`)

Catatan voice dan caption:
- `voice_text`
  - dipakai sebagai sumber TTS
  - dipakai juga sebagai sumber caption
- `voice_character`
  - dipilih per scene dari 8 karakter suara:
    - `yetty`, `nilasari`, `dany_saputra`, `dakocan`, `candy`, `lily`, `finn`, `kevin`
- prompt lain seperti `sound_prompt`, `positive_prompt`, `negative_prompt`, dan prompt grup edit/image juga mengikuti format bilingual `id_old` / `id_new` / `en`
- konfigurasi provider voice bersifat global per project di `project_settings.json.voice`:
  - `voice_provider=gemini` -> model runtime fixed `gemini-3.1-flash-tts-preview` (language `id-ID`)
  - `voice_provider=elevenlabs` -> model runtime fixed `eleven_v3`
- konfigurasi caption bersifat global per project di `project_settings.json.caption`:
  - `generate_caption`
  - boolean
  - default `true`
  - jika aktif, video yang selesai dibuat akan langsung diburn caption otomatis
  - caption tidak membuat file `__captioned` tambahan pada alur otomatis; video final ditimpa dengan versi yang sudah bercaption

Catatan trimming video:
- pemotongan video mengikuti durasi speech hanya berlaku untuk `scene_type=wan22_s2v`
- scene type lain tidak dipotong otomatis mengikuti speech

## Server Config

Konfigurasi server ComfyUI disimpan per-project di `project_settings.json` pada key:

- `comfyui_server`
  - format: `<ip/host>:<port>`
  - default: `nextgenserver:8188`

Contoh:
```json
{
  "comfyui_server": "nextgenserver:8188"
}
```

Pemakaian:
- dipakai oleh `main.py`, `scripts/generate_initial_image.py`, `scripts/generate_image_edit.py`, `scripts/generate_voice.py`, `scripts/generate_cover_image.py`, dan `scene_manager_ui.py`
- model `prompt_generation` bersifat per-project dan dibaca dari `project_settings.json`
- jika provider `ollama` dipilih, UI akan membaca model yang tersimpan di JSON lalu mencoba mengambil daftar model dari server `host:port`
- jika model tersimpan tersedia, dropdown akan memilih model itu
- jika model tersimpan tidak tersedia, nilai tersimpan tetap ditampilkan sebagai opsi supaya konfigurasi lama tidak hilang
- di UI, konfigurasi ini diubah lewat dialog `Konfigurasi Project` (bukan dialog server terpisah)

## Project CLI

Script: `scripts/project_cli.py`

Fungsi:
- membuat project baru dari CLI dengan struktur dan format file yang sama seperti UI
- menambah scene baru ke project yang sudah ada dengan pilihan `scene_type` yang sama seperti UI
- backend pembuatan project dan scene dipakai bersama oleh UI dan CLI agar format JSON tetap konsisten
- tersedia launcher tipis di folder `api_production`:
  - `api_production/project_cli.py`
  - `api_production/project_cli.bat`
  - launcher ini mengasumsikan source code ada di parent directory dari `api_production`
  - launcher harus dijalankan dari dalam folder `api_production`

Subcommand:
- `create-project`
  - default membuat project kosong, hanya `project_settings.json`
  - bisa memakai `--with-default-scene` untuk mengikuti perilaku tombol `Project Baru` di UI dan otomatis membuat `scene_1`
  - bisa mengisi:
    - `project_description`
    - `video_size.width`
    - `video_size.height`
    - `comfyui_server`
    - `prompt_generation.model`
    - `prompt_generation.provider`
    - `prompt_generation.host`
    - `prompt_generation.port`
    - `voice.voice_provider`
    - `caption.generate_caption`
- `create-scene`
  - menambah scene baru berurutan (`scene_1`, `scene_2`, dst)
  - bisa mengisi:
    - `scene_title`
    - `scene_description`
    - `voice_text`
    - `scene_type`
    - `duration_seconds`
  - setelah scene dibuat, ukuran project otomatis disinkronkan ke file prompt scene yang relevan

Pilihan `scene_type`:
- `wan22_i2v`
- `wan22_t2v_i2v`
- `wan22_t2v_batch`
- `wan22_s2v`
- `i2v`
- `web_scroll`
- `image_pan`
- `image_zoom`

Contoh:
```powershell
.\.venv\Scripts\python.exe scripts\project_cli.py create-project --project demo_project
.\.venv\Scripts\python.exe scripts\project_cli.py create-project --project demo_project --description "Video edukasi anak" --width 360 --height 640 --comfyui-server nextgenserver:8188 --prompt-generation-provider ollama --prompt-generation-model qwen3.6:35b-a3b-uc-q4_K_M --prompt-generation-host nextgenserver --prompt-generation-port 11434 --voice-provider gemini --generate-caption true
.\.venv\Scripts\python.exe scripts\project_cli.py create-project --project demo_project --with-default-scene
.\.venv\Scripts\python.exe scripts\project_cli.py create-scene --project demo_project --scene-type wan22_i2v --title "Intro Magnet" --scene-description "Anak menemukan magnet di meja belajar." --voice-text "Halo teman-teman! Hari ini kita belajar magnet, benda seru yang bisa menarik klip kertas dan benda logam kecil di sekitar kita!" --duration 10
.\.venv\Scripts\python.exe scripts\project_cli.py create-scene --project demo_project --scene-type wan22_t2v_i2v --title "Intro Gerak" --scene-description "Pembuka dua tahap T2V lalu I2V." --voice-text "Halo teman-teman! Hari ini kita mulai dengan gerakan singkat, lalu dilanjutkan ke gerakan yang lebih panjang." --duration 15
.\.venv\Scripts\python.exe scripts\project_cli.py create-scene --project demo_project --scene-type wan22_t2v_batch --title "Intro Batch" --scene-description "T2V utama dengan prompt tambahan." --voice-text "Halo teman-teman! Hari ini kita buat video utama lalu beberapa variasi prompt tambahan." --duration 10
```

Contoh dari folder `api_production`:
```powershell
.\project_cli.bat create-project --project demo_project
.\project_cli.bat create-scene --project demo_project --scene-type image_zoom --title "Zoom Intro" --scene-description "Close-up magnet merah biru." --voice-text "Halo teman-teman! Hari ini kita belajar magnet, benda seru yang bisa menarik klip kertas dan benda logam kecil di sekitar kita!" --duration 10
.\project_cli.bat create-scene --project demo_project --scene-type wan22_t2v_i2v --title "Intro Gerak" --scene-description "Pembuka dua tahap T2V lalu I2V." --voice-text "Halo teman-teman! Hari ini kita mulai dengan gerakan singkat, lalu dilanjutkan ke gerakan yang lebih panjang." --duration 15
.\project_cli.bat create-scene --project demo_project --scene-type wan22_t2v_batch --title "Intro Batch" --scene-description "T2V utama dengan prompt tambahan." --voice-text "Halo teman-teman! Hari ini kita buat video utama lalu beberapa variasi prompt tambahan." --duration 10
```

## Main Runner

Script utama: `main.py`

Fungsi:
- `scene_type=wan22_t2v_i2v`
  - ambil video dari stage `WAN22_T2V`
  - jika durasi scene `5`, hasil akhir langsung dari stage `WAN22_T2V`
  - jika durasi scene `10` atau `15`, frame terakhir dari video T2V (frame ke 81) dipakai sebagai input image untuk stage `WAN22_I2V`
  - stage `WAN22_I2V` tetap memakai script yang sudah ada di repo
- `scene_type=wan22_t2v_batch`
  - ambil video dari stage `WAN22_T2V` untuk prompt utama dan setiap prompt tambahan yang terisi
  - jumlah frame per video dihitung dengan `ceil((duration * 16) / total_video)`
  - semua hasil video digabung jadi satu video final
  - prompt tambahan yang kosong dilewati
- `scene_type=wan22_i2v`
  - ambil satu gambar terbaru dari root folder scene
  - upload image ke ComfyUI
  - generate video dari `wan22_i2v_prompt.json`
  - jika `project_settings.caption.generate_caption=true`, burn caption ke video hasil
- `scene_type=wan22_s2v`
  - ambil satu gambar terbaru dari root folder scene
  - ambil satu file audio speech terbaru dari root folder scene
  - upload image dan audio ke ComfyUI
  - generate video dari `wan22_s2v_prompt.json`
  - potong hasil video sesuai durasi speech dengan tambahan maksimal `4 frame`
  - jika `project_settings.caption.generate_caption=true`, burn caption ke video hasil setelah trim
- `scene_type=i2v`
  - ambil semua gambar dari root folder scene
  - compose gambar menjadi video sederhana
  - jika `project_settings.caption.generate_caption=true`, burn caption ke video hasil
- `scene_type=web_scroll`
  - membaca `web_scroll_prompt.json`
  - render website di browser headless dan scroll dari atas ke bawah selama durasi
  - output portrait memakai mobile emulation, output landscape memakai desktop context
  - kecepatan scroll disesuaikan dengan `speed`
  - mode capture:
    - `stable_pan` (default): screenshot halaman lalu pan vertikal dengan hasil gerak lebih halus
  - capture halaman panjang dibatasi otomatis agar proses tetap stabil
  - jika `project_settings.caption.generate_caption=true`, burn caption ke video hasil
- `scene_type=image_pan`
  - membaca `image_pan_prompt.json`
  - mengambil satu gambar terbaru dari root folder scene sebagai sumber pan horizontal
  - arah pan ditentukan oleh `direction` (`from_right` atau `from_left`)
  - mode capture:
    - `stable_pan` (default): pan gambar dengan hasil gerak lebih halus
  - jika `project_settings.caption.generate_caption=true`, burn caption ke video hasil
- `scene_type=image_zoom`
  - membaca `image_zoom_prompt.json`
  - mengambil satu gambar terbaru dari root folder scene sebagai sumber zoom
  - zoom ditentukan oleh `zoom_direction` (`in` atau `out`)
  - titik fokus zoom ditentukan oleh `focal_point`
  - mode capture:
    - `stable_pan` (default): zoom gambar dengan hasil gerak lebih halus
  - jika `project_settings.caption.generate_caption=true`, burn caption ke video hasil

Argumen:
- `--server`, `-s`
  - ComfyUI server `host:port`
- `--project`, `-p`
  - nama project di dalam `api_production`
- `--scene`, `-S`
  - nama scene, repeatable
- `--loop`, `-L`
  - jumlah loop, minimal `1`

Contoh:
```powershell
.\.venv\Scripts\python.exe main.py --server 127.0.0.1:8188 --project demo_project
.\.venv\Scripts\python.exe main.py --server 127.0.0.1:8188 --project demo_project --scene scene_1
.\.venv\Scripts\python.exe main.py --server 127.0.0.1:8188 --project demo_project --scene scene_1 --scene scene_2
```

## Scene Manager UI

Script: `scene_manager_ui.py`

Fungsi utama:
- project-based workspace:
  - `Project Baru` membuat folder project baru di `api_production/<project_name>`
  - project baru otomatis dibuat dengan `project_settings.json` dan `scene_1`
  - `Buka Project` memilih project yang sudah ada
  - `Tutup Project` menutup project aktif
  - nama project harus unik (tidak boleh duplikat)
- tombol `Konfigurasi Project` untuk mengatur:
  - `Deskripsi Project`
  - `ComfyUI Server` (`<ip/host>:<port>`, wajib diisi, default `nextgenserver:8188`)
  - `Ukuran Video Project`
  - `Model Prompt Generation`
    - provider: `Gemini` atau `Ollama`
    - model Gemini dibaca dari daftar model yang tersedia
    - model Ollama dibaca dari server `host:port`
    - jika model tersimpan di JSON tersedia, dropdown akan langsung memilihnya
    - jika model tidak tersedia, dropdown dibiarkan kosong dan harus dipilih ulang
    - provider `Gemini` memakai default API tanpa setting `temperature`
    - provider `Ollama` selalu memakai `thinking` dan parameter hardcoded
  - `Ollama Host / Port`
    - berdampingan di satu baris
    - default: `nextgenserver:11434`
  - `Voice Project`
  - `Caption Project`
  - `Cover`
  - pada bagian `Cover`, ukuran cover otomatis mengikuti `Ukuran Video Project` dan dropdown ukuran cover dinonaktifkan
- menampilkan daftar scene dari project aktif
- drag-and-drop untuk reorder scene
- tambah, sisipkan, dan hapus scene
- edit metadata scene
- edit prompt image
- tab `Prompt Tambahan` untuk 3 prompt image tambahan berbasis aturan `Gambar Awal`
- edit prompt WAN
- edit prompt WAN22 S2V
- tab `Image Edit` untuk edit gambar berbasis prompt
- tab `Web Search` untuk mencari gambar referensi dari web dan menyimpannya langsung ke folder scene aktif
- dropdown `Variasi` di toolbar untuk melihat isi `variasiN` secara read-only
- tombol di sebelah dropdown `Variasi` untuk mengkopikan video terbaru dari variasi terpilih ke root scene
  - dipakai saat ingin memakai satu hasil video terbaru sebagai isi root sebelum proses `combine all`
  - file video root lama akan dihapus, folder variasi tetap dipertahankan
  - folder `variasi*` tetap dipertahankan
- saat pindah scene, tampilan otomatis kembali ke `Root Scene`
- untuk voice, tersedia field:
  - `Pilihan Suara Scene` (per scene): 8 karakter suara
- group `Audio` berisi proses generate voice/sound untuk scene atau semua scene
- edit ukuran image dan WAN
- edit ukuran WAN22 S2V
- edit `CFG` untuk WAN22 S2V
- edit pengaturan seed image
- edit Lora image
- edit Lora WAN High 1, Low 1, High 2, dan Low 2
- langkah WAN fixed `4 langkah`
- pilih durasi WAN `5 detik`, `10 detik`, atau `15 detik` (khusus `wan22_t2v_i2v`)
- pilih model image:
  - `Z-Image Turbo`
  - `Flux.2`
  - `Flux.2 Klein 9B`
  - `Gemini`
- pilih model image edit:
  - `Flux.2`
  - `Gemini`
- menampilkan aset media per scene
- klik sekali pada aset membuka preview:
  - `Image` langsung tampil sebagai preview
  - `Video` tampil sebagai thumbnail preview dulu
  - `Suara` tampil sebagai ikon speaker
- klik ganda pada aset menjalankan media:
  - `Image` tetap hanya preview
  - `Video` langsung diputar
  - `Suara` langsung diputar
- klik pada preview membuka file dengan aplikasi default sistem operasi
- klik ganda pada preview memiliki perilaku yang sama
- hapus aset dari menu klik kanan
- jalankan proses image, scene, voice, sound, dan compose
- tombol `Save` untuk backup project aktif menjadi ZIP
- menampilkan log proses
- memakai backend pembuatan project/scene yang sama dengan `scripts/project_cli.py`, tetapi perilaku `Project Baru` di UI tetap otomatis membuat `scene_1`

Perilaku UI:
- operasi scene hanya aktif jika project sudah dibuka
- konfigurasi cover disimpan global per project di `project_settings.json.cover`
- hasil generate cover disimpan ke `api_production/<project_name>/cover/cover.png`
- `Status Adegan` menampilkan masalah validasi scene aktif
- `Jalankan Adegan` dan `Jalankan Semua Adegan` diblok jika masih ada scene bermasalah
- `voice` dan `sound` bersifat opsional
- `voice` hanya wajib jika `voice_text` diisi
- pilihan suara scene tersedia di metadata scene melalui `voice_character`
- language TTS runtime dipaksa ke `id-ID`
- semua input prompt di UI tetap Bahasa Indonesia dan yang disimpan ke `id_new`
- `id_old` dan `en` tidak diedit langsung dari UI, hanya tersimpan di JSON
- `Generate Config Agentic` hanya membuat JSON variasi dan menyimpannya ke folder `variasiN`
- `Execute Agentic` menjalankan variasi yang belum punya `status.done`
- untuk `wan22_t2v_batch`, agentic memakai panduan khusus `SCENE-WAN22-T2V-BATCH.md`
- output agentic untuk scene ini mencakup `wan22_t2v_prompt.json` dan `wan22_t2v_batch_extra_prompts.json`
- ukuran video project menjadi sumber ukuran tunggal untuk tab:
  - `WAN22_T2V`
  - `WAN22_I2V`
  - `WAN22 S2V`
  - `Web Scroll`
  - `Image Pan`
  - `Image Zoom`
  - `Gambar Awal` hanya untuk scene type `wan22_i2v`, `wan22_s2v`, `i2v`
- dropdown ukuran pada tab-tab tersebut dikunci (disabled) dan hanya menampilkan ukuran project aktif
- scene type `wan22_t2v_i2v` hanya menampilkan 4 tab:
  - `Meta`
  - `WAN22_T2V`
  - `WAN22_I2V`
  - `Aset`
- scene type `wan22_t2v_batch` menampilkan:
  - `Meta`
  - `WAN22_T2V`
  - `Prompt Tambahan`
  - `Aset`
  - tab `WAN22_I2V` disembunyikan
- khusus tab `Gambar Awal` pada scene type `image_pan` dan `image_zoom`, dropdown ukuran tetap aktif (tidak mengikuti ukuran project)
- tab `WAN22_I2V` selalu memakai Lora dan tidak lagi menampilkan checkbox `Pakai Lora`
- tab `WAN22_T2V` juga selalu memakai Lora dan tidak menampilkan checkbox `Pakai Lora`
- tab `WAN22_T2V` menyediakan:
  - `Ukuran`
  - 4 field Lora: `Lora High 1`, `Lora Low 1`, `Lora High 2`, `Lora Low 2`
  - `Prompt Positif`
  - `Prompt Negatif`
  - tombol `Buat Prompt` pada `Prompt Positif`
- saat model image `Gemini` dipilih:
  - field `Model Gemini` (image only) ditampilkan untuk memilih model Gemini spesifik
  - negative prompt dinonaktifkan
  - pengaturan seed statik dinonaktifkan
  - pengaturan Lora image dinonaktifkan
- tab `Prompt Tambahan` menyediakan 3 grup:
  - `Prompt Positif`
  - `Prompt Negatif`
  - tombol `Buat Image`
  - semua grup memakai aturan model/ukuran/seed/Lora/Gemini yang sama seperti tab `Gambar Awal`
- `sound_prompt` tidak wajib
- `Generate Caption` default aktif untuk project baru dan disimpan di `project_settings.json.caption`
- caption tidak lagi dibuat lewat tombol terpisah; caption berjalan otomatis setelah video selesai dibentuk jika `project_settings.caption.generate_caption` aktif
- untuk `web_scroll`:
  - tab `S2V`, `I2V`, dan `Gambar Awal` disembunyikan
  - tab `Web Scroll` ditampilkan dengan input: `url`, `ukuran`, `duration_seconds`, `speed`
  - tombol `Generate Image Awal` nonaktif (disabled)
- untuk scene type `i2v`, `image_pan`, dan `image_zoom`:
  - tab `Web Search` tersedia
  - input: `search_term` dan `ukuran`
  - tombol `Cari Gambar Web` akan mengunduh hasil gambar ke root folder scene
  - hasil unduhan langsung terlihat di tab `Aset` setelah proses selesai
- untuk `image_pan`:
  - tab `Gambar Awal` tetap tersedia
  - tab `Image Pan` ditampilkan dengan input: `ukuran` (portrait-only), `direction`
  - durasi diatur dari field durasi scene di tab `Metadata`
  - tombol `Generate Image Awal` tetap aktif
- untuk `image_zoom`:
  - tab `Gambar Awal` tetap tersedia
  - tab `Image Zoom` ditampilkan dengan input: `ukuran`, `zoom_direction`, `focal_point`, `zoom_strength`
  - durasi diatur dari field durasi scene di tab `Metadata`
  - tombol `Generate Image Awal` tetap aktif
- untuk `wan22_s2v`, tab `WAN22 S2V` menyediakan:
  - `Ukuran`
  - `CFG`
  - `Prompt Positif`
  - `Prompt Negatif`
  - tombol `Buat Prompt` pada field `Prompt Positif` dan `Prompt Negatif` untuk menyusun ulang prompt lewat LLM lalu menyimpan `en`, `id_new`, dan `id_old`
- untuk `image_edit` (tab `Image Edit`):
  - field `Model`: `Flux.2` / `Gemini`
  - field `Model Gemini` ditampilkan saat model `Gemini` dipilih
  - tersedia 3 group edit:
    - dropdown `Gambar Awal` (diisi dari file gambar di root scene aktif)
    - input `Prompt`
    - tombol `Image Gen Prompt` untuk menyalin template clipboard edit gambar
    - tombol `Buat Prompt` untuk menyusun ulang prompt lewat LLM lalu menyimpan `en` dan `id_new`
    - tombol `Edit Gambar`
  - input `Prompt` di UI selalu menampilkan `id_new`
  - saat tombol `Edit Gambar` ditekan:
    - model `Flux.2`: memakai template `api_template/flux2_edit_api.json`, input gambar di node `46`, ukuran mengikuti gambar input, seed selalu random
    - model `Gemini`: prompt runtime diambil dari `en` di JSON jika sudah sinkron; jika `id_old != id_new` atau `en` kosong, sistem translate `id_new` ke bahasa Inggris pakai Gemini, lalu hasilnya dipakai untuk edit
  - isi dropdown `Gambar Awal` ikut diperbarui saat daftar aset dimuat ulang (`Muat Ulang`)
- tab `Gambar Awal`, `Prompt Tambahan`, `WAN22_I2V`, `WAN22_T2V`, dan `WAN22 S2V` juga punya tombol `Buat Prompt` untuk menyusun ulang prompt lewat LLM lalu menyimpan `en`, `id_new`, dan `id_old`
- tab `Gambar Awal` dan `Prompt Tambahan` juga punya tombol `Image Gen Prompt` untuk menyalin template prompt ke clipboard
- untuk `wan22_t2v_batch`, tab `Prompt Tambahan` menyediakan 3 grup `Prompt Positif` / `Prompt Negatif` dan tombol `Buat Prompt` di setiap grup
- setelah proses selesai dari UI, akan muncul popup:
  - informasi keberhasilan beserta file output yang terdeteksi
  - atau ringkasan error jika proses gagal

## Agentic Variations

Agentic dipakai untuk membuat dan menjalankan variasi per scene dalam dua tahap:

1. `Generate Config Agentic`
   - menjalankan LLM dulu untuk membuat JSON variasi saja
   - hasil LLM disimpan ke folder `variasiN`
   - setiap folder variasi juga menyimpan:
     - `input-prompt.txt`
     - `output-prompt.txt`
   - isi file `.md` tidak dikirim sebagai attachment terpisah, melainkan ditempel langsung ke isi prompt
   - prompt LLM berisi:
     - deskripsi project
     - daftar semua scene
     - scene aktif
     - special command
     - file JSON/template input
     - file `.md` referensi
     - untuk `wan22_t2v_batch`, referensi markdown yang ditempel adalah `SCENE-GENERAL.md`, `SCENE-WAN22-T2V-BATCH.md`, `TEXT-TO-VIDEO-BATCH.md`, dan `TEXT-TO-VIDEO-PROMPT.md`
     - isi JSON dari variasi yang sudah ada sebagai referensi anti-duplikasi
   - jika LLM gagal membuat variasi prompt setelah 3 percobaan, catatan akan ditulis ke `variasi_gagal.txt` di root project berisi nama scene dan variasi
   - pada section input JSON dan schema output, field prompt ditampilkan sebagai string kosong `""` agar LLM jelas mengisi bagian itu saja
   - output JSON divalidasi ketat:
     - struktur harus sama dengan input
     - field prompt harus konsisten
     - `id_old` dan `id_new` disamakan oleh runtime

2. `Execute Agentic`
   - mencari folder variasi yang belum punya `status.done`
   - copy isi folder variasi ke root scene
   - jalankan proses scene dari root
   - copy hasil root scene kembali ke folder variasi
   - buat `status.done`
   - bersihkan file `.png` dan `.mp4` di root scene

Perilaku `status.done`:
- hanya mempengaruhi tahap `Execute Agentic`
- folder variasi yang sudah punya `status.done` akan di-skip pada eksekusi berikutnya
- `Generate Config Agentic` tetap bisa membuat variasi baru walaupun variasi lama sudah ada `status.done`
- nomor variasi selalu lanjut dari indeks terbesar yang ada

Catatan:
- kalau ada variasi gagal karena prompt kosong atau output LLM tidak valid, proses akan skip variasi itu dan lanjut ke variasi berikutnya
- untuk scene `wan22_t2v_i2v`, image awal tidak dibuat pada tahap execute
- untuk scene `i2v` dengan `image_extra` atau `image_edit`, alur image tambahan mengikuti setting di tab `Agentic`

Menjalankan UI:
```powershell
.\.venv\Scripts\python.exe scene_manager_ui.py
.\run_ui.bat
```

Linux/macOS:
```bash
./.venv/bin/python scene_manager_ui.py
./run_ui.sh
```

Catatan:
- `run_ui.bat` otomatis memakai Python dari `.venv` sehingga tidak perlu aktivasi manual virtual environment.
- `run_ui.sh` otomatis memakai Python dari `.venv` dan menjalankan UI di background.

## VRAM Cleanup

Cleanup VRAM dijalankan otomatis setelah proses yang berhasil selesai:

- setelah generate gambar awal
- setelah generate image edit
- setelah generate cover
- setelah scene selesai diproses lewat `main.py`

File workflow yang dikirim ke ComfyUI:
- `api_template/vram-cleaner-api.json`

Di UI juga tersedia tombol manual `Clear VRAM` pada toolbar untuk mengirim workflow ini secara langsung ke ComfyUI aktif.

## Image Models

Implementasi domain image:
- `z_image/z_image.py`
- `flux2/flux2.py`
- `gemini/gemini_image.py`

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
- `Flux.2 (Image Edit)`
  - template edit: `api_template/flux2_edit_api.json`
  - input gambar sumber di node `46`
  - prompt positif dikirim dari group edit yang dipilih
  - ukuran output mengikuti ukuran gambar input
  - seed selalu random
- `Gemini`
  - generate image via Gemini API (tanpa ComfyUI workflow)
  - model Gemini spesifik dipilih dari `gemini_model_id`
  - request image size memakai mode strict `1K`
  - hasil diproses ke ukuran target scene/image dengan metode `scale + center crop` (tanpa stretching)
  - `json_api` disimpan sebagai `gemini_flash_05k`
  - tidak memakai negative prompt
  - tidak memakai seed statik dan Lora image

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
- `wan22_t2v/wan22_t2v.py`
- `wan22_s2v/wan22_s2v.py`

Template WAN:
- `4 langkah` lora-only
  - `api_template/wan22_i2v_4steps_lora_api.json`
  - `api_template/wan22_t2v_4steps_lora_api.json`

Resolusi WAN yang tersedia:
- `368x640`
- `480x848`
- `720x1280`
- `640x368`
- `848x480`
- `1280x720`

Lora WAN:
- `Lora High / Low` set 1
  - nama file dan kekuatan bisa diatur dari UI
  - default nama file:
    - `WAN2.2/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors`
    - `WAN2.2/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors`
  - default kekuatan: `0`
  - dipetakan ke node `264` dan `265`
- `Lora High / Low` set 2
  - nama file dan kekuatan bisa diatur dari UI
  - default nama file:
    - `WAN2.2/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors`
    - `WAN2.2/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors`
  - default kekuatan: `0`
  - dipetakan ke node `266` dan `267`
- `wan22_t2v_i2v` / `WAN22_T2V`
  - nama file dan kekuatan bisa diatur dari UI
  - default nama file:
    - `WAN2.2/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors`
    - `WAN2.2/wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors`
  - default kekuatan: `0`
  - dipetakan ke node `114` dan `115`
  - layer tambahan dipetakan ke node `133` dan `134`

Durasi WAN:
- diatur per scene melalui `scene_meta.json.duration_seconds`
- nilai yang didukung:
  - `5`
  - `10`
- untuk `wan22_t2v_i2v`:
  - nilai yang didukung: `5`, `10`, `15`
  - `5` = hanya stage `WAN22_T2V`
  - `10` = stage `WAN22_T2V` lalu `WAN22_I2V` selama `5` detik
  - `15` = stage `WAN22_T2V` lalu `WAN22_I2V` selama `10` detik
- UI `WAN22_I2V` tidak lagi menyediakan dropdown durasi
- prompt WAN yang dipakai hanya 2 pasang:
  - `positive_prompt_one` / `negative_prompt_one`
  - `positive_prompt_two` / `negative_prompt_two`
- file `wan22_i2v_prompt.json` tetap dipakai untuk stage `WAN22_I2V`, sedangkan `wan22_t2v_prompt.json` menyimpan prompt positif/negatif, ukuran, dan 4 field Lora stage `WAN22_T2V`

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
- prompt UI yang disimpan di JSON menggunakan `id_new`, lalu runtime akan memakai `en` jika tersedia atau akan menerjemahkan `id_new` ke Inggris saat diperlukan
- bisa juga membaca file prompt tambahan berbasis group untuk generate image alternatif dengan aturan model scene yang sama
- jalur model dipilih otomatis dari `z_image_prompt.json`
- jika model image scene adalah model biasa / ComfyUI:
  - membangun workflow image sesuai model yang dipilih
  - mengirim workflow ke ComfyUI
  - mendownload image hasil ke folder scene
- jika model image scene adalah `Gemini`:
  - generate image via Gemini API
  - simpan image hasil ke folder scene sesuai ukuran target scene (scale + center crop)

Contoh:
```powershell
.\.venv\Scripts\python.exe scripts\generate_initial_image.py --server 127.0.0.1:8188 --project demo_project --scene scene_1
.\.venv\Scripts\python.exe scripts\generate_initial_image.py --project demo_project --scene scene_1 --prompt-file z_image_extra_prompts.json --prompt-index 1
```

## Generate Image Edit

Script: `scripts/generate_image_edit.py`

Fungsi:
- membaca konfigurasi model edit dari UI (`Flux.2` atau `Gemini`)
- mengambil gambar sumber dari root folder scene sesuai pilihan dropdown
- bisa dijalankan manual dengan `--source-image` + `--prompt`
- bisa juga membaca slot prompt dari `image_edit_prompt.json` dengan `--prompt-file image_edit_prompt.json --prompt-index 1|2|3`
- jika model `Flux.2`:
  - upload gambar sumber ke ComfyUI
  - membangun workflow dari `api_template/flux2_edit_api.json`
  - set input gambar di node `46`
  - set prompt dari group edit yang dipilih
  - set ukuran output sama seperti ukuran gambar sumber
  - set seed random
  - download hasil edit ke root folder scene
- jika model `Gemini`:
  - kirim gambar sumber + prompt runtime ke Gemini API
  - prompt runtime diambil dari `en` bila tersedia; jika belum sinkron, `id_new` diterjemahkan dulu ke bahasa Inggris memakai model `project_settings.json.prompt_generation`
  - request image size `1K`
  - simpan hasil akhir ke root folder scene dengan ukuran mengikuti orientasi/ukuran gambar sumber

Contoh:
```powershell
.\.venv\Scripts\python.exe scripts\generate_image_edit.py --server 127.0.0.1:8188 --project demo_project --scene scene_1 --model flux.2 --source-image input.png --prompt "Tambahkan nuansa cinematic malam"
.\.venv\Scripts\python.exe scripts\generate_image_edit.py --server 127.0.0.1:8188 --project demo_project --scene scene_1 --model gemini --gemini-model-id gemini-3.1-flash-image-preview --source-image input.png --prompt "Ubah menjadi gaya watercolor"
.\.venv\Scripts\python.exe scripts\generate_image_edit.py --server 127.0.0.1:8188 --project demo_project --scene scene_1 --prompt-file image_edit_prompt.json --prompt-index 1
.\.venv\Scripts\python.exe scripts\generate_image_edit.py --server 127.0.0.1:8188 --project demo_project --scene scene_1 --prompt-file image_edit_prompt.json --prompt-index 2
.\.venv\Scripts\python.exe scripts\generate_image_edit.py --server 127.0.0.1:8188 --project demo_project --scene scene_1 --prompt-file image_edit_prompt.json --prompt-index 3
```

## Generate Cover Project

Script: `scripts/generate_cover_image.py`

Fungsi:
- membaca konfigurasi cover dari `project_settings.json.cover`
- saat tombol `Generate Cover` dijalankan, prompt cover disinkronkan dulu:
  - jika `id_new != id_old`, runtime menyamakan `id_old = id_new`
  - `en` diisi hasil translate dari `id_new`
  - untuk ComfyUI, yang dikirim adalah nilai `en`
- perilaku ini berlaku sama untuk `positive_prompt` dan `negative_prompt`
- generate image cover sesuai model image (`ComfyUI` atau `Gemini`)
- menyimpan hasil final sebagai `api_production/<project_name>/cover/cover.png`

Contoh:
```powershell
.\.venv\Scripts\python.exe scripts\generate_cover_image.py --server 127.0.0.1:8188 --project demo_project
```

## Voice dan Sound

### Generate Voice

Script: `scripts/generate_voice.py`

Fungsi:
- membaca provider voice global dari `project_settings.json.voice`:
  - `gemini`
  - `elevenlabs`
- membaca `voice_text` dan `voice_character` dari `scene_meta.json`
- jika provider `gemini`:
  - memakai Gemini API native TTS
  - model fixed `gemini-3.1-flash-tts-preview`
  - prompt style dipilih dari `voice_character` (Yetty/Nilasari/Dany Saputra/Dakocan/Candy/Lily/Finn/Kevin)
  - profile Gemini bisa diedit lewat file TXT di folder `gemini_voice_profile/`:
    - `Yetty.txt`, `Nilasari.txt`, `Dany Saputra.txt`, `Dakocan.txt`, `Candy.txt`, `Lily.txt`, `Finn.txt`, `Kevin.txt`
  - format TXT mengikuti pola prompt Gemini TTS: `# AUDIO PROFILE`, scene, director notes, sample context, lalu `#### TRANSCRIPT`
  - `voice_text` runtime ditempel otomatis tepat di bawah `#### TRANSCRIPT`
  - jika file TXT kosong atau tidak ada, sistem fallback ke profile bawaan di kode
  - saat menjalankan semua scene sekaligus, sistem mencoba mode konsisten per `voice_character`:
    - scene dikelompokkan berdasarkan `voice_character`
    - grup yang berisi lebih dari satu scene digabung menjadi satu transcript
    - grup yang hanya berisi satu scene tetap digenerate per scene
    - menyisipkan token `SCENEBREAKTOKEN` sebagai instruksi jeda panjang antar scene
    - menghasilkan satu WAV gabungan dan menyimpannya di `api_production/<project_name>/voice_combined/`
    - membagi WAV berdasarkan jeda panjang, lalu trim silence, snap akhir ke zero crossing, dan memberi fade-out pendek untuk mengurangi bunyi klik
    - jika deteksi jeda panjang gagal, proses fallback ke generate per scene
- jika provider `elevenlabs`:
  - memakai ElevenLabs API
  - model fixed `eleven_v3`
  - `voice_id` otomatis mengikuti `voice_character`
- file output voice selalu memakai awalan `speech_`

Contoh:
```powershell
.\.venv\Scripts\python.exe scripts\generate_voice.py --server 127.0.0.1:8188 --project demo_project --scene scene_1
.\.venv\Scripts\python.exe scripts\generate_voice.py --server 127.0.0.1:8188 --project demo_project
```

Contoh `keys.cfg`:
```ini
GEMINIKEY=isi_api_key_gemini
ELEVENLABSKEY=isi_api_key_elevenlabs
FIRECRAWLKEY=isi_api_key_firecrawl
```

Catatan key Gemini:
- pencarian key Gemini dilakukan dengan urutan:
  - `GEMINIKEY` di `keys.cfg`
  - `GEMINI_API_KEY` di `keys.cfg` atau environment variable
  - `GOOGLE_API_KEY` di `keys.cfg` atau environment variable

Catatan key Firecrawl (untuk Web Search):
- `FIRECRAWLKEY` dibaca dari `keys.cfg`
- alias lama `FIRECRAWL_API_KEY` masih diterima untuk kompatibilitas
- jika key tidak ada, proses `Cari Gambar Web` di UI akan gagal

### Generate Sound

Script: `scripts/generate_sound.py`

Fungsi:
- membaca `sound_prompt` dan `duration_seconds` dari `scene_meta.json`
- `sound_prompt` juga mengikuti format bilingual `id_old` / `id_new` / `en`, dan runtime memakai `en` bila tersedia
- request sound effect ke ElevenLabs Sound Effects API
- output ElevenLabs dikonversi ke WAV memakai `ffmpeg`, lalu disimpan ke folder scene

Catatan:
- membaca `keys.cfg` di root project untuk `ELEVENLABSKEY`

Contoh:
```powershell
.\.venv\Scripts\python.exe scripts\generate_sound.py --project demo_project --scene scene_1
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
- caption berjalan otomatis setelah video scene selesai dibuat jika `project_settings.caption.generate_caption=true`
- sumber teks caption selalu dari `voice_text`
- file `.caption.srt` disimpan di samping video yang dicaption

Catatan:
- `faster-whisper` akan mengunduh model saat pertama kali dipakai
- model default caption saat ini adalah `base`

## Compose Video

Script: `scripts/generate_compose.py`

Fungsi:
- compose per scene ke folder `api_production/<project_name>/combined` dengan mix audio:
  - `wan22_s2v`: mempertahankan speech bawaan video dan hanya menambahkan sound
  - scene type lain: mix speech + sound ke video scene
- merge semua hasil scene di `combined` menjadi `combined_all.mp4`
- pada merge akhir bisa menambahkan background music opsional:
  - file music dari folder `music` dengan ekstensi `.m4a`, `.mp3`, `.wav`
  - music bisa kosong (tidak dipilih)
  - volume music bisa diatur dari `0.00` sampai `2.00`
  - music dipotong jika lebih panjang dari video
  - music diulang jika lebih pendek dari video
  - fade out `0.5` detik pada akhir setiap segmen music (termasuk saat loop dan akhir video)
- jika folder `cover` berisi gambar, gambar pertama dipakai sebagai intro `2 frame` di awal video final
- merge akhir dibuat sederhana:
  - jika format scene seragam (fps/resolusi), concat langsung `-c copy`
  - jika berbeda, normalisasi lalu merge

Di UI:
- tersedia tombol `Compose Semua Adegan`
- saat `Compose Semua Adegan`, muncul dialog untuk memilih music dan volume

Contoh:
```powershell
.\.venv\Scripts\python.exe scripts\generate_compose.py --project demo_project --scene scene_1
.\.venv\Scripts\python.exe scripts\generate_compose.py --project demo_project --scene scene_1 --scene scene_2
.\.venv\Scripts\python.exe scripts\generate_compose.py --project demo_project
.\.venv\Scripts\python.exe scripts\generate_compose.py --project demo_project --music-file ".\\music\\Another Night (Corporate).m4a" --music-volume 1.00
```

Catatan:
- `ffmpeg` dan `ffprobe` harus tersedia di `PATH`
- jangan menjalankan `generate_compose.py` paralel untuk project yang sama karena semua proses menulis ke folder `combined` yang sama

## Backup Production ZIP

Script: `backup_production.py`

Fungsi:
- membuat file ZIP yang berisi satu folder project aktif
- output disimpan ke folder `backup_production`
- nama file ZIP selalu `<project_name>.zip`

Argumen:
- `--project`, `-p`
  - nama project yang akan dibackup

Contoh:
```powershell
.\.venv\Scripts\python.exe backup_production.py --project demo_project
```

Di UI:
- tombol `Save` ada di grup `Backup`
- saat diklik, UI akan konfirmasi backup project aktif dengan nama file tetap `<project_name>.zip`

## Logging

File logging utama:
- `logging_config.py`

Log runtime default:
- `content_creation.log`


