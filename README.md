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
- `minimax_h3_t2v_prompt.json` (untuk stage T2V `minimax-h3_t2v_i2v`)
- `minimax_h3_i2v_prompt.json` (untuk scene `minimax-h3_i2v` dan stage I2V `minimax-h3_t2v_i2v`)
- `minimax_h3_s2v_prompt.json` (untuk scene `minimax-h3_s2v`)
- `web_scroll_prompt.json` (untuk `web_scroll`)
- `image_pan_prompt.json` (untuk `image_pan`)
- `image_zoom_prompt.json` (untuk `image_zoom`)
- `web_search_prompt.json` (untuk `i2v`, `image_pan`, `image_zoom`)

Catatan pembuatan file scene:
- saat membuat scene baru, baik dari UI maupun CLI, semua file JSON prompt inti di atas langsung dibuat otomatis
- tujuannya agar scene bisa langsung diganti `scene_type` tanpa perlu membuat file JSON tambahan secara manual

Catatan format prompt:
- prompt bilingual biasa yang tampil di UI memakai nilai `id_new`
- di JSON, field prompt bilingual biasa disimpan sebagai object:
  - `id_old`
  - `id_new`
  - `en`
- prompt MiniMax H3 juga memakai tiga field tersebut, tetapi nilai setiap field adalah object JSON nested, bukan string
- editor Prompt Positif MiniMax di UI menampilkan object `id_new` sebagai JSON berindentasi yang dapat diedit
- `en` adalah versi Inggris untuk runtime dan tidak dikirim ke ComfyUI sebagai representasi dictionary Python
- `id_old` selalu merupakan salinan persis dari `id_new`
- `id_new` adalah JSON Bahasa Indonesia yang ditampilkan dan diedit di UI
- prompt generation dan translate memakai konfigurasi yang sama di `project_settings.json.prompt_generation`
- provider `gemini` memakai default model API tanpa setting `temperature`
- provider `llama.cpp` memakai endpoint OpenAI-compatible bila tersedia
- runtime akan mencoba `v1/chat/completions` untuk text generation dan `v1/models` untuk daftar model
- jika endpoint modern tidak tersedia, runtime akan fallback ke endpoint legacy yang kompatibel
- tombol `Buat Prompt` tidak melakukan `Save Scene` terlebih dahulu; input dan konteks diambil langsung dari nilai yang sedang tampil di UI
- khusus MiniMax H3, `Save` hanya memvalidasi JSON `id_new` dan menyamakan `id_old` dengan `id_new`; `Save` tidak memanggil LLM untuk menerjemahkan prompt
- saat scene MiniMax dijalankan, runtime menerjemahkan `id_new` ke `en` hanya jika `id_old != id_new` atau `en` kosong, lalu menyimpan hasil sinkronisasi tersebut
- jika JSON MiniMax di UI tidak valid, Save menampilkan error dan tidak merusak file prompt
- `lora_trigger_words` disimpan sebagai text biasa dan tidak diterjemahkan
- `lora_trigger_words` hanya disisipkan ke awal prompt positif versi Inggris saat runtime, bukan ditulis permanen ke field prompt

Aturan khusus MiniMax H3 untuk tombol `Buat Prompt` dan Agentic:
- LLM hanya diminta menghasilkan `positive_prompt.en` dalam bentuk object JSON nested; LLM tidak diminta membuat `id_new` atau `id_old`
- setelah respons `en` lolos validasi, aplikasi menerjemahkan field teks satu per satu ke Bahasa Indonesia untuk membentuk `id_new`
- `id_old` kemudian dibuat sebagai deep-copy dari `id_new`, sehingga keduanya selalu identik setelah generate atau normalisasi Agentic
- field angka, array timeline, identifier, dan token referensi tidak diterjemahkan atau diubah
- token dalam tanda `<...>` wajib dipertahankan persis, termasuk `<Picture 1>`, `<Subject 1>`, `<Video 1>`, `<Audio 1>`, dan token kontrol lain yang ditentukan skill
- schema respons Agentic MiniMax tidak menyertakan field non-prompt seperti `lora_name`, `lora_strength`, `width`, dan `height`; setelah respons lolos validasi, field tersebut selalu dipulihkan dari file input tanpa perubahan
- hanya `positive_prompt.en` yang boleh diisi/diubah oleh LLM
- schema Agentic T2VA/I2VA mendefinisikan item `shots` secara eksplisit walaupun prompt scene awal masih kosong; `shot_id` wajib string dan blok `reference` I2VA memakai nilai kontrol tetap
- representasi ekuivalen dari provider seperti `shot_id: 1` dan `reference.time: 0` dinormalisasi menjadi `"Shot 1"` dan `0.0` sebelum validasi struktur

Schema prompt MiniMax H3 T2VA/I2VA:
- `positive_prompt.en` adalah object JSON dengan `mode`, `shots`, `overall_soundscape`, dan `non_diegetic_music`
- setiap item `shots` wajib memiliki `shot_id`, `start`, `end`, `visual`, `action`, `camera`, `dialogue`, dan `diegetic_sound`
- `shot_id` berbentuk string seperti `Shot 1`; `start` dan `end` berbentuk angka
- I2VA juga wajib memiliki alignment `Picture 1` pada awal prompt; T2VA tidak boleh memiliki alignment image tersebut
- `remove_sound` adalah boolean teknis di level root prompt; field ini tidak dikirim ke ComfyUI dan dipulihkan dari konfigurasi input saat Agentic membuat variasi

Schema prompt MiniMax H3 S2V/Ref2VA:
- `positive_prompt.en` adalah object dengan tepat enam field: `subject_definitions`, `summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`, dan `non_diegetic_music`
- scene S2V hanya menggunakan `<Picture 1>` dan `<Audio 1>`; referensi Picture 2/3, Video 1, dan Audio 2/3 tidak boleh muncul
- keenam field tersebut diterjemahkan satu per satu ke `id_new`; hasil prompt Inggris yang dikirim ke workflow diserialisasi dari `positive_prompt.en`

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
  - `prompt_generation.host` dan `prompt_generation.port` untuk llama.cpp
  - `voice.voice_provider` (`gemini` / `elevenlabs`)
  - `caption.generate_caption`
  - `cover` (struktur sama seperti `z_image_prompt.json`)
- `z_image_prompt.json`
  - `image_model`
  - `gemini_model_id` (khusus saat `image_model=gemini`)
  - `lora_trigger_words`
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
  - `lora_trigger_words`
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
  - `lora_trigger_words`
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
- `minimax-h3_t2v_i2v`
  - membutuhkan `scene_meta.json`, `minimax_h3_t2v_prompt.json`, dan `minimax_h3_i2v_prompt.json`
  - durasi scene berupa angka desimal `1.0` sampai `30.0` dengan maksimal 1 angka desimal
  - durasi sampai `15.0` detik hanya menjalankan stage MiniMax H3 T2V
  - durasi di atas `15.0` detik menjalankan T2V `15.0` detik lalu I2V dengan frame terakhir T2V sebagai gambar awal; sisa durasi dikirim ke stage I2V
  - FPS MiniMax H3 ditetapkan `24`, dan nilainya berlaku untuk stage T2V maupun I2V
- `minimax-h3_i2v`
  - membutuhkan `scene_meta.json`, `z_image_prompt.json`, `minimax_h3_i2v_prompt.json`, dan minimal satu gambar di root folder scene
  - durasi scene berupa angka desimal `1.0` sampai `15.0` dengan maksimal 1 angka desimal
  - memakai gambar terbaru dari root folder scene sebagai `Picture 1` untuk workflow MiniMax H3 I2VA
  - FPS MiniMax H3 ditetapkan `24`
- `minimax-h3_r2v`
  - membutuhkan `scene_meta.json`, `minimax_h3_r2v_prompt.json`, dan minimal satu reference image, video, atau audio sesuai manifest prompt
  - durasi scene berupa angka desimal `1.0` sampai `15.0` dengan maksimal 1 angka desimal
  - FPS MiniMax H3 ditetapkan `24`
- `minimax-h3_s2v`
  - membutuhkan `scene_meta.json`, `z_image_prompt.json`, `minimax_h3_s2v_prompt.json`, minimal satu gambar di root folder scene, dan minimal satu file audio speech berawalan `speech_`
  - durasi voice dikirim sebagai float ke workflow; output video dipertahankan utuh setelah diunduh
  - durasi audio speech tidak boleh lebih dari 15 detik; jika melebihi batas, scene diblokir
  - FPS MiniMax H3 ditetapkan `24`
  - workflow memakai `minimax_h3_r2v_api.json` secara in-memory dan menghapus referensi Picture 2, Picture 3, Video 1, Audio 2, dan Audio 3
  - Picture 1 berasal dari gambar root terbaru dan Audio 1 berasal dari audio speech root terbaru
- `wan22_t2v_batch`
  - membutuhkan `scene_meta.json`, `wan22_t2v_prompt.json`, dan `wan22_t2v_batch_extra_prompts.json`
  - durasi scene hanya `5` atau `10`
  - stage `WAN22_T2V` dijalankan satu per satu untuk prompt utama dan setiap prompt tambahan yang terisi
  - `lora_trigger_words` diambil dari `wan22_t2v_prompt.json` lalu ditambahkan ke awal prompt positif `en` untuk prompt utama dan semua prompt tambahan saat runtime
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
  - `lora_trigger_words` dari `wan22_i2v_prompt.json` otomatis ditambahkan ke awal `positive_prompt_one` dan `positive_prompt_two` versi `en` saat runtime
- `minimax-h3_i2v`
  - memakai satu gambar terbaru dari root folder scene sebagai input first frame
  - durasi workflow MiniMax H3 I2VA mengikuti durasi scene desimal (`1.0` sampai `15.0`)
  - FPS workflow MiniMax H3 ditetapkan `24`
- `wan22_t2v_i2v`
  - stage `WAN22_T2V` selalu dijalankan terlebih dahulu
  - jika durasi scene `5`, hasil akhir langsung dari stage `WAN22_T2V`
  - jika durasi scene `10` atau `15`, frame terakhir dari video T2V (frame ke 81) dipakai sebagai input image untuk stage `WAN22_I2V`
  - durasi stage `WAN22_I2V` otomatis menjadi `5` untuk scene `10` detik dan `10` untuk scene `15` detik
- `wan22_t2v_batch`
  - stage `WAN22_T2V` dijalankan untuk prompt utama dan setiap prompt tambahan yang terisi
  - `lora_trigger_words` dari `wan22_t2v_prompt.json` otomatis ditambahkan ke awal prompt positif versi `en` untuk prompt utama dan semua prompt tambahan saat runtime
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
- `wan22_s2v` dipotong mengikuti durasi speech dengan tambahan maksimal empat frame
- seluruh output scene MiniMax (`minimax-h3_i2v`, `minimax-h3_t2v_i2v`, `minimax-h3_s2v`, dan `minimax-h3_r2v`) dipertahankan utuh setelah download; frame alignment `17n+5` adalah bagian dari hasil generasi, bukan padding pascaproses yang dibuang
- khusus `minimax-h3_s2v` dengan provider Gemini, setelah WAV TTS dibuat:
  - sample rate harus `24 kHz`; jika bukan, proses menampilkan warning dan padding tidak diterapkan
  - durasi WAV dikonversi ke frame video dengan `round(sample_count * 24 / 24000)`
  - target alignment MiniMax mengikuti `frame_count % 17 == 5` pada 24 FPS
  - jika target alignment berikutnya masih berada di bawah atau sama dengan batas `15 detik`, silence ditambahkan di bagian akhir WAV
  - jika penambahan silence akan melewati `15 detik`, WAV dipotong ke target alignment-safe sebelumnya
  - target alignment-safe terbesar yang tidak melewati `15 detik` adalah `345 frame = 14.375 detik`; `360 frame = 15 detik` bukan alignment-safe
  - WAV yang sudah alignment-safe tidak diubah lagi pada pemrosesan berikutnya (operasi bersifat idempoten)
- dengan audio yang sudah alignment-safe, durasi audio mengikuti frame alignment output S2V dan video tidak perlu dipotong setelah download
- scene type lain tidak dipotong otomatis mengikuti speech

## Audio Scene dan Final Compose

Scene berikut menghasilkan video scene yang sudah memiliki audio setelah eksekusi scene selesai:

- `wan22_i2v`
- `wan22_t2v_i2v` (jalur WAN T2V/I2V)
- `minimax-h3_i2v`
- `minimax-h3_t2v_i2v`

Mix audio scene mengikuti pola WAN:

```text
video ComfyUI
+ voice scene
+ sound effect dari sound_prompt
= video scene ber-audio
```

Untuk `minimax-h3_i2v` dan `minimax-h3_t2v_i2v`:

- `remove_sound=true`: audio bawaan ComfyUI dihapus terlebih dahulu, kemudian voice dan sound effect di-mix
- `remove_sound=false`: audio bawaan ComfyUI dipertahankan dan di-mix bersama voice serta sound effect

Setelah mix berhasil, `scene_meta.json` diberi marker `audio_composed=true`. Saat `generate_compose.py` membuat final compose, video bertanda tersebut hanya diekspor dengan audio yang sudah ada; voice dan sound effect tidak ditambahkan lagi. Hal ini mencegah double mix.

Untuk `minimax-h3_s2v` dan `minimax-h3_r2v`, final compose hanya memilih satu video terbaru di root scene. Video lama yang masih berada di root tidak ikut digabung.

Pada Execute Agentic, folder variasi disalin sementara ke root scene dan diproses melalui jalur yang sama. Hasil mix audio dan marker `audio_composed` kemudian disalin kembali ke folder variasi.

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
- default model Gemini untuk `prompt_generation` dan `translate` adalah `gemini-3.1-flash-lite`
- `gemini-3.1-flash-lite` juga menjadi model default Agentic saat provider project adalah Gemini
- jika provider `llama.cpp` dipilih, UI akan membaca model yang tersimpan di JSON lalu mencoba mengambil daftar model dari server `host:port`
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
- `minimax-h3_t2v_i2v`
- `minimax-h3_i2v`
- `wan22_t2v_batch`
- `wan22_s2v`
- `i2v`
- `web_scroll`
- `image_pan`
- `image_zoom`

Contoh:
```powershell
.\.venv\Scripts\python.exe scripts\project_cli.py create-project --project demo_project
.\.venv\Scripts\python.exe scripts\project_cli.py create-project --project demo_project --description "Video edukasi anak" --width 360 --height 640 --comfyui-server nextgenserver:8188 --prompt-generation-provider llama.cpp --prompt-generation-model qwen3.6:35b-a3b-uc-q4_K_M --prompt-generation-host nextgenserver --prompt-generation-port 8080 --voice-provider gemini --generate-caption true
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
- `scene_type=minimax-h3_t2v_i2v`
  - stage MiniMax H3 T2V dijalankan lebih dahulu
  - untuk durasi di atas `15.0`, frame terakhir T2V dipakai sebagai input `first_frame` stage MiniMax H3 I2V
  - stage I2V memakai sisa durasi scene dan FPS yang dipilih pada tab T2V
  - hasil kedua stage digabung menjadi satu video final
- `scene_type=minimax-h3_i2v`
  - ambil satu gambar terbaru dari root folder scene
  - upload image ke ComfyUI
  - generate video dari `minimax_h3_i2v_prompt.json` menggunakan workflow MiniMax H3 I2V
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
    - provider: `Gemini` atau `llama.cpp`
    - model Gemini dibaca dari daftar model yang tersedia
    - model llama.cpp dibaca dari server `host:port`
    - jika model tersimpan di JSON tersedia, dropdown akan langsung memilihnya
    - jika model tidak tersedia, dropdown dibiarkan kosong dan harus dipilih ulang
    - provider `Gemini` memakai default API tanpa setting `temperature`
    - provider `llama.cpp` mencoba endpoint `v1/models` lebih dulu lalu fallback ke endpoint legacy bila perlu
  - `llama.cpp Host / Port`
    - berdampingan di satu baris
    - default: `nextgenserver:8080`
  - `Voice Project`
  - `Caption Project`
  - `Cover`
  - pada bagian `Cover`, ukuran cover otomatis mengikuti `Ukuran Video Project` dan dropdown ukuran cover dinonaktifkan
- menampilkan daftar scene dari project aktif
- drag-and-drop untuk reorder scene
- tambah, sisipkan, dan hapus scene
- grup toolbar `Edit` untuk append prompt massal ke semua scene dan semua variasi dalam project aktif
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
- tombol di sebelah `Buka Project` untuk menjalankan `Execute Agentic` ke beberapa project sekaligus
- saat pindah scene, tampilan otomatis kembali ke `Root Scene`
- untuk voice, tersedia field:
  - `Pilihan Suara Scene` (per scene): 8 karakter suara
- group `Audio` berisi proses generate voice/sound untuk scene atau semua scene
- tombol `Upscale Video` di group `Scene` untuk upscale video terakhir pada root scene aktif
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
- tombol `Clear VRAM` tersedia di dialog `Konfigurasi Project`
- daftar LoRa dimuat sekali saat UI dijalankan, lalu dipakai dari memory cache untuk semua dropdown LoRa
- jika ComfyUI tidak menjawab saat startup UI, akan muncul popup error berbahasa Indonesia dan daftar LoRa tidak dimuat
- grup toolbar runtime menyediakan tombol:
  - `L`: switch ke Llama
  - `C`: switch ke ComfyUI
  - `V`: memeriksa status kedua service
  - `LC`: membuka dialog log ComfyUI
  - `LL`: membuka dialog log Llama
- dialog `LC` dan `LL` berukuran sekitar dua pertiga layar, berada di tengah, dan mengambil 100 baris log terakhir
- dialog log bersifat read-only dan melakukan refresh async setiap 5 detik; waktu refresh terakhir ditampilkan
- posisi scroll vertikal dan horizontal dipertahankan saat isi log diperbarui, tanpa memaksa scrollbar ke baris paling akhir
- endpoint log runtime yang digunakan adalah:
  - `GET /v1/runtime/logs/comfyui`
  - `GET /v1/runtime/logs/llama`
- endpoint log memerlukan autentikasi Bearer yang sama dengan endpoint runtime lainnya; API key client dibaca dari `switch-key.cfg`
- jika Runtime Controller belum menyediakan endpoint log, dialog menampilkan error HTTP (misalnya `404`) dan tetap mencoba refresh setiap 5 detik
- `voice` dan `sound` bersifat opsional
- `voice` hanya wajib jika `voice_text` diisi
  - pilihan suara scene tersedia di metadata scene melalui `voice_character`, termasuk `lily_arab` (Lily - Arab)
- language TTS runtime dipaksa ke `id-ID`
- semua input prompt di UI tetap Bahasa Indonesia dan yang disimpan ke `id_new`; untuk MiniMax, nilainya ditampilkan sebagai object JSON berindentasi, sedangkan scene lain memakai string
- `id_old` dan `en` tidak diedit langsung dari UI, hanya tersimpan di JSON; editor MiniMax hanya membuka object `id_new`
- `Generate Config Agentic` hanya membuat JSON variasi dan menyimpannya ke folder `variasiN`
- folder `variasiN` baru dibuat setelah respons LLM lolos validasi; jika seluruh 3 percobaan gagal, kegagalan hanya dicatat ke `variasi_gagal.txt` dan tidak dibuat folder variasi kosong
- nomor folder variasi hanya bertambah setelah variasi berhasil disimpan, sehingga kegagalan tidak menimbulkan celah nomor
- `Execute Agentic` menjalankan setiap folder variasi yang belum punya file `status.done`, tanpa bergantung pada nilai `Jumlah Variasi`
- untuk `wan22_t2v_batch`, agentic memakai panduan khusus `SCENE-WAN22-T2V-BATCH.md`
- Agentic MiniMax H3 untuk `minimax-h3_i2v`, `minimax-h3_t2v_i2v`, dan `minimax-h3_s2v` meminta LLM mengisi hanya `positive_prompt.en` sesuai schema scene
- setelah Agentic berhasil, aplikasi menerjemahkan `en` per field, membuat `id_new`, lalu menyalin `id_new` ke `id_old`
- pada S2V/Ref2VA, Agentic hanya boleh menggunakan enam field Ref2VA dan referensi `<Picture 1>` serta `<Audio 1>`
- schema respons Agentic S2V menetapkan keenam field Ref2VA tersebut secara eksplisit sebagai string wajib; field teknis tetap dipulihkan dari root scene dan kegagalan 3 attempt mengikuti aturan tanpa folder `variasiN`
- output agentic untuk scene ini mencakup `wan22_t2v_prompt.json` dan `wan22_t2v_batch_extra_prompts.json`
- ukuran video project menjadi sumber ukuran tunggal untuk tab:
  - `WAN22_T2V`
  - `WAN22_I2V`
  - `WAN22 S2V`
  - `Web Scroll`
  - `Image Pan`
  - `Image Zoom`
  - `Gambar Awal` hanya untuk scene type `wan22_i2v`, `wan22_s2v`, `minimax-h3_i2v`, `i2v`
- dropdown ukuran pada tab-tab tersebut dikunci (disabled) dan hanya menampilkan ukuran project aktif
- scene type `wan22_t2v_i2v` hanya menampilkan 4 tab:
  - `Meta`
  - `WAN22_T2V`
  - `WAN22_I2V`
  - `Aset`
- scene type `minimax-h3_i2v` menampilkan tab berurutan:
  - `Meta`
  - `Gambar Awal`
  - `Image Edit`
  - `MINIMAX-H3_I2V`
  - `Agentic`
  - `Aset`
- scene type `minimax-h3_s2v` menampilkan tab berurutan:
  - `Meta`
  - `Gambar Awal`
  - `MINIMAX-H3_S2V`
  - `Agentic`
  - `Aset`
- scene type `minimax-h3_t2v_i2v` menampilkan tab berurutan:
  - `Meta`
  - `MINIMAX-H3_T2V`
  - `MINIMAX-H3_I2V`
  - `Agentic`
  - `Aset`
- urutan tab selalu di-reset ke urutan canonical saat berpindah scene sehingga tidak dipengaruhi scene yang sebelumnya dibuka
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
  - tombol `Edit Variasi` di atas prompt positif untuk mengkopikan semua konfigurasi Lora (`nama` dan `kekuatan`) ke semua folder variasi scene aktif pada file `wan22_t2v_prompt.json`
  - `Prompt Positif`
  - `Prompt Negatif`
  - tombol `Buat Prompt` pada `Prompt Positif`
- tab `WAN22_I2V` juga menyediakan tombol `Edit Variasi` dengan fungsi serupa untuk file `wan22_i2v_prompt.json`
- tab MiniMax T2V dan I2V masing-masing menyediakan:
  - `Ukuran` yang mengikuti ukuran video project
  - FPS MiniMax H3 ditetapkan `24`
  - `Lora` dan kekuatannya
  - `Prompt Positif` berupa JSON `id_new`
  - tombol `Buat Prompt`
  - tombol `Edit Variasi`
- `Edit Variasi` MiniMax T2V hanya mengkopikan `lora_name` dan `lora_strength` dari `minimax_h3_t2v_prompt.json` ke file T2V semua variasi
- `Edit Variasi` MiniMax I2V melakukan hal yang sama secara terpisah dari `minimax_h3_i2v_prompt.json`; LoRA T2V dan I2V tidak harus sama
- tab `MINIMAX-H3_S2V` tidak menampilkan CFG atau Negative Prompt; prompt positif memakai JSON `id_new` Ref2VA dan tombol `Buat Prompt` mengikuti schema enam field Ref2VA
- tab `MINIMAX-H3_R2V` menyediakan `Ukuran`, FPS `24`, dua LoRA, manifest reference, dan prompt positif Ref2VA
- tab `MINIMAX-H3_S2V` menyediakan `Ukuran`, FPS `24`, dua LoRA, dan prompt positif Ref2VA
- tombol `Edit Variasi` hanya aktif saat `Root Scene` sedang dipilih dan scene aktif memang memiliki folder variasi
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
- dialog `Edit Prompt` menyediakan 5 group append dengan tombol `Jalankan` terpisah:
  - append positive `wan22_t2v`
  - append negative `wan22_t2v`
  - append positive `wan22_i2v`
  - append negative `wan22_i2v`
  - append positive `image`
  - setiap aksi menerjemahkan teks tambahan sekali di awal untuk mengisi `en`, lalu menambahkan kalimat itu di awal prompt yang relevan pada semua `scene_*` dan semua folder `variasi*`
- dialog multi-project agentic menampilkan daftar project dalam bentuk checkbox dan tombol `Agentic`
- saat tombol `Agentic` dijalankan dari dialog itu, project terpilih diproses berurutan berdasarkan abjad dengan mode `Execute Agentic`
- saat `Compose Semua Adegan`, dialog compose juga menyediakan dropdown `Upscale`:
  - `Tanpa upscale`
  - `1.5x`
  - `2x`
  - jika dipilih `1.5x` atau `2x`, video final `combined_all.mp4` akan di-upscale langsung tanpa mengekspor frame PNG
- dialog compose menyediakan checkbox `Compose Lagu`:
  - memangkas 4 frame ekstra pada setiap video `wan22_s2v` berdasarkan durasi chunk speech
  - tidak mencampurkan file `speech_*.mp3` lagi ke video S2V karena audio sudah tertanam pada video
  - mempertahankan audio bawaan setiap video S2V dan menyusun video/audio per-scene secara bersamaan agar lip-sync tetap terjaga
- tombol `Upscale Video` pada group `Scene` membuka dialog kecil untuk memilih `1.5x` atau `2x`
- hasil tombol `Upscale Video` disimpan sebagai file video baru di root scene aktif tanpa mengekspor frame PNG
- tab `Gambar Awal`, `Prompt Tambahan`, `WAN22_I2V`, `WAN22_T2V`, dan `WAN22 S2V` mempunyai tombol `Buat Prompt` dengan alur bilingual string sesuai tipe prompt masing-masing
- tombol `Buat Prompt` pada semua tab MiniMax T2V/I2V memakai referensi scene MiniMax yang sesuai dan hanya meminta LLM membuat object JSON `en`; pipeline kemudian menerjemahkan field teks per-field menjadi `id_new` dan menyalin `id_new` ke `id_old`
- setelah Buat Prompt MiniMax berhasil, JSON `id_new` langsung dimuat ke UI tanpa menunggu reload scene dan tanpa Save Scene pendahuluan
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
     - untuk `minimax-h3_i2v`, output wajib berupa `z_image_prompt.json` dan `minimax_h3_i2v_prompt.json`, dengan referensi `SCENE-MINIMAX-H3-I2V.md`, `MINIMAX-H3/SKILL.md`, dan `MINIMAX-H3/references/base-en.txt`
     - untuk `minimax-h3_t2v_i2v`, output wajib mencakup `minimax_h3_t2v_prompt.json` dan `minimax_h3_i2v_prompt.json`, dengan referensi `SCENE-MINIMAX-H3-T2V-I2V.md`, `MINIMAX-H3/SKILL.md`, dan `MINIMAX-H3/references/base-en.txt`
     - isi JSON dari variasi yang sudah ada sebagai referensi anti-duplikasi
   - jika LLM gagal membuat variasi prompt setelah 3 percobaan, catatan akan ditulis ke `variasi_gagal.txt` di root project berisi nama scene dan variasi
   - pada section input JSON dan schema output, field prompt ditampilkan sebagai string kosong `""` agar LLM jelas mengisi bagian itu saja
   - output JSON divalidasi ketat:
     - struktur harus sama dengan input
     - field prompt harus konsisten
     - untuk prompt non-MiniMax, kontrak bilingual `id_old`, `id_new`, dan `en` tetap berlaku
     - khusus `minimax_h3_t2v_prompt.json` dan `minimax_h3_i2v_prompt.json`, schema respons LLM hanya memuat `positive_prompt.en` sebagai object JSON nested berbahasa Inggris
     - LLM Agentic MiniMax tidak diminta dan tidak diizinkan menghasilkan `positive_prompt.id_new` atau `positive_prompt.id_old`
     - pipeline memvalidasi `en` sebagai T2VA/I2VA, menerjemahkan setiap field teks natural-language satu per satu menjadi object Indonesia `id_new`, lalu membuat `id_old` sebagai deep-copy `id_new`
     - key, array, angka, timing, `shot_id`, `mode`, dan object `reference` disalin tanpa diterjemahkan
     - hasil file variasi MiniMax yang disimpan tetap lengkap dengan `positive_prompt.id_old`, `positive_prompt.id_new`, dan `positive_prompt.en`
     - I2VA wajib memiliki reference `<Picture 1>` pada `0.00` dari `[Shot 1]`; T2VA tidak boleh memiliki `reference`
     - array `shots` boleh berisi satu atau lebih shot dan setiap shot wajib memiliki `shot_id`, `start`, `end`, `visual`, `action`, `camera`, `dialogue`, dan `diegetic_sound`
     - perubahan field nested di bawah `positive_prompt.en`, termasuk `overall_soundscape`, dikenali sebagai perubahan prompt yang valid; field non-prompt seperti LoRA tetap tidak boleh diubah LLM

2. `Execute Agentic`
   - mencari semua folder `variasiN`/`variasi_N` yang belum mempunyai file `status.done`
   - tidak membaca `number_of_variations`; nilai itu hanya menentukan jumlah konfigurasi pada tahap Generate Config
   - copy isi folder variasi ke root scene
   - jalankan proses scene dari root
   - copy hasil root scene kembali ke folder variasi
   - buat `status.done`
   - bersihkan file `.png` dan `.mp4` di root scene
   - untuk `minimax-h3_i2v` saat `Buat Image Awal` dimatikan, gambar referensi `.png` di root dipertahankan agar tetap dapat dipakai sebagai `Picture 1`

Perilaku `status.done`:
- hanya mempengaruhi tahap `Execute Agentic`
- file `status.done` adalah satu-satunya penanda variasi sudah selesai dan harus di-skip pada eksekusi berikutnya
- variasi tanpa `status.done` tetap dieksekusi meskipun `number_of_variations=0`
- variasi dengan `status.failed` atau kegagalan sebelumnya tetap dianggap pending dan dapat dicoba ulang
- `Generate Config Agentic` tetap bisa membuat variasi baru walaupun variasi lama sudah ada `status.done`
- nomor variasi selalu lanjut dari indeks terbesar yang ada

Timeout Agentic:
- setiap workflow yang dikirim ke ComfyUI memiliki timeout `7200` detik (2 jam), dihitung per workflow call
- setiap call ke LLM memiliki timeout `600` detik (10 menit)
- Agentic tidak memiliki timeout tambahan per scene; Agentic mengikuti timeout internal call ComfyUI dan LLM
- jika proses gagal atau timeout, `status.done` tidak dibuat sehingga variasi tetap dapat dieksekusi ulang

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

File workflow yang dikirim ke ComfyUI:
- `api_template/vram-cleaner-api.json`

Di UI tersedia tombol manual `Clear VRAM` di dialog `Konfigurasi Project` untuk mengirim workflow ini secara langsung ke ComfyUI aktif.

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
    - `WAN2.2/HIGH/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors`
    - `WAN2.2/LOW/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors`
  - default kekuatan: `0`
  - dipetakan ke node `264` dan `265`
- `Lora High / Low` set 2
  - nama file dan kekuatan bisa diatur dari UI
  - default nama file:
    - `WAN2.2/HIGH/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors`
    - `WAN2.2/LOW/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors`
  - default kekuatan: `0`
  - dipetakan ke node `266` dan `267`
- `wan22_t2v_i2v` / `WAN22_T2V`
  - nama file dan kekuatan bisa diatur dari UI
  - default nama file:
    - `WAN2.2/HIGH/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors`
    - `WAN2.2/LOW/wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors`
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
- `lora_trigger_words` dari `z_image_prompt.json` otomatis ditambahkan ke awal prompt positif versi `en` saat generate gambar utama maupun prompt tambahan
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
    - `Yetty.txt`, `Nilasari.txt`, `Dany Saputra.txt`, `Dakocan.txt`, `Candy.txt`, `Lily.txt`, `Lily Ngaji.txt`, `Lily Arab.txt`, `Finn.txt`, `Kevin.txt`
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

### Generate Music dengan Lyria 3 Pro

Script: `lyria3/generate_music.py`

Fungsi:
- membuat musik menggunakan Gemini API dengan model `lyria-3-pro-preview`
- menyimpan hasil audio sebagai MP3 di folder `output-music`
- menyimpan lirik hasil generasi sebagai file `.lyrics.txt` jika tersedia
- durasi target dimasukkan ke prompt dan dibatasi maksimal `180` detik
- dapat menerima maksimal 10 gambar referensi untuk mengarahkan mood dan gaya musik

Argumen utama:
- `--prompt`, `-p`: prompt musik wajib
- `--duration`, `-d`: durasi target dalam detik, wajib, maksimal `180`
- `--output-name`, `-o`: nama file output tanpa ekstensi; default `lyria3_music`
- `--image`: gambar referensi, bisa diulang maksimal 10 kali
- `--timeout`: timeout request dalam detik; default `600`

Rekomendasi isi prompt:
- genre dan gaya
- mood dan arah emosi
- instrumen utama
- tempo atau BPM
- musik instrumental atau vokal
- struktur musik dan timestamp bila timing penting
- instruksi `instrumental only, no vocals, no lyrics` jika musik dipakai sebagai background music

Contoh musik instrumental:
```powershell
.\.venv\Scripts\python.exe lyria3\generate_music.py --prompt "Buat musik instrumental sinematik yang hangat, penuh rasa ingin tahu, dan cocok untuk video edukasi anak. Gunakan piano felt, pizzicato strings, marimba, woodwind lembut, tempo sedang sekitar 100 BPM, aransemen sederhana agar menyisakan ruang untuk narasi, tanpa vokal dan tanpa lirik." --duration 45 --output-name edukasi_magnet
```

Contoh dengan gambar referensi:
```powershell
.\.venv\Scripts\python.exe lyria3\generate_music.py --prompt "Buat musik ambient sinematik yang terinspirasi dari gambar, tenang dan penuh harapan, dengan piano lembut, string pad, dan tekstur udara. Musik instrumental saja." --duration 60 --output-name suasana_pagi --image input\scene_1.png
```

Kebutuhan key:
- `GEMINIKEY` di `keys.cfg`
- atau `GEMINI_API_KEY` sebagai environment variable

Output:
- `output-music/<nama>/<nama>.mp3`
- `output-music/<nama>/<nama>.lyrics.txt` jika Lyria mengembalikan lirik

Setiap lagu dibuat dalam folder sendiri berdasarkan nilai `--output-name`.


Catatan implementasi saat ini:
- folder `lyria3` saat ini hanya menyediakan `generate_music.py`
- fitur pemotongan musik menjadi chunk belum tersedia di folder ini
- alignment lirik dan analisis jeda vokal belum menjadi bagian dari pipeline yang terdokumentasi
- file `.lyrics.txt` hanya disimpan jika respons Lyria mengembalikan teks lirik

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
- `faster-whisper` hanya membantu menentukan waktu caption; isi teks tidak diambil dari hasil transkripsi
- file `.caption.srt` hanya dipakai sebagai file sementara dan dihapus setelah proses selesai

### Caption bahasa Arab

- setiap entry caption diperiksa berdasarkan karakter Unicode Arab
- teks Arab dipertahankan dalam urutan logis persis seperti sumbernya; aplikasi tidak membalik karakter atau urutan kata secara manual
- entry Arab dirender menggunakan Pillow dengan Arabic shaping dan arah `rtl`, kemudian ditempel sebagai overlay ke video
- entry non-Arab tetap memakai jalur subtitle SRT/libass yang sudah ada
- jika satu video memiliki entry Arab dan non-Arab, pemilihan renderer dilakukan per-entry; renderer khusus Arab tidak diterapkan ke teks non-Arab
- teks campuran Arab dengan tanda baca atau angka tetap diberi anchor RTL agar urutan bacanya stabil
- scene yang sudah memiliki video caption lama harus diproses ulang agar perubahan renderer Arab diterapkan

Catatan:
- `faster-whisper` akan mengunduh model saat pertama kali dipakai
- model default caption saat ini adalah `base`

## Compose Video

Script: `scripts/generate_compose.py`

Fungsi:
- compose per scene ke folder `api_production/<project_name>/combined` dengan mix audio:
  - `wan22_s2v` dan `minimax-h3_s2v`: mempertahankan speech/audio bawaan video dan tidak mencampurkan ulang file `speech_*`
  - `minimax-h3_i2v` dan `minimax-h3_t2v_i2v`: mempertahankan audio hasil ComfyUI lalu mencampurkannya dengan file `speech_*` dan sound effect scene
  - video root/variasi MiniMax tetap merupakan video asli hasil ComfyUI; master audio tidak dicampurkan dan tidak menimpa file video pada tahap generation
  - saat Compose Scene/Compose All dijalankan, master audio ComfyUI dibuat dari video root ke `.comfy_audio_source/audio.wav` jika cache belum ada, lalu dipakai untuk membangun mix tanpa menggandakan audio scene
  - Compose All memakai satu video final terbaru untuk scene MiniMax H3, sehingga file stage T2V tidak tergabung ulang bersama hasil T2V-I2V
  - scene type lain: mix speech + sound ke video scene
- merge semua hasil scene di `combined` menjadi `combined_all.mp4`
- ukuran master compose selalu diambil dari `project_settings.json.video_size`, bukan dari resolusi video scene pertama
- setiap video scene dinormalisasi ke ukuran master project menggunakan `scale + pad`; aspect ratio dipertahankan dan video sumber tidak ditimpa
- sebelum merge dengan `-c copy`, parameter audio utama (codec, sample rate, jumlah channel, dan layout) dibandingkan; jika berbeda antar-scene, setiap video dinormalisasi ke AAC stereo `44100 Hz` agar konfigurasi AAC tidak berubah di tengah `combined_all.mp4`
- jika `--compose-song` aktif, semua video scene selalu dinormalisasi dan di-re-encode sebelum penggabungan, walaupun fps, resolusi, dan signature audio awalnya sama; hal ini mencegah encoder padding membuat celah audio di batas scene
- opsi `--compose-song` menjadikan audio `speech_chunk_*` dari setiap scene sebagai master timeline: semua chunk didekode, di-resample ke `44100 Hz` stereo, timestamp di-reset, lalu digabung tanpa jeda; setiap video scene dipotong/diatur mengikuti durasi chunk audionya
- pada `--compose-song`, trim empat frame ekstra hanya diterapkan pada `wan22_s2v`; `minimax-h3_s2v` tidak menjalankan trim empat frame tersebut
- pada mode `--compose-song`, audio scene bawaan video tidak dipakai sebagai timeline akhir; video scene digabung tanpa audio, kemudian master audio Lagu di-mux sebagai AAC `192 kbps`, `44100 Hz`, stereo
- pada merge akhir bisa menambahkan background music opsional:
  - file music dari folder `music` dengan ekstensi `.m4a`, `.mp3`, `.wav`
  - music bisa kosong (tidak dipilih)
  - volume music bisa diatur dari `0.00` sampai `2.00`
  - music dipotong jika lebih panjang dari video
  - music diulang jika lebih pendek dari video
  - fade out `0.5` detik pada akhir setiap segmen music (termasuk saat loop dan akhir video)
  - track music dinormalisasi ke `44100 Hz` stereo sebelum di-mix dengan audio utama
  - audio utama dan music diubah ke format `44100 Hz` stereo sebelum `amix`; speech/audio scene tetap dipertahankan sebagai track utama
- jika folder `cover` berisi gambar, gambar pertama dipakai sebagai intro `2 frame` di awal video final
- merge akhir dibuat sederhana:
  - jika fps, resolusi master, dan signature audio scene seragam, concat langsung `-c copy`
  - jika fps, resolusi, atau signature audio berbeda, normalisasi lalu merge
  - jika `Compose Lagu` aktif, selalu gunakan jalur normalisasi dan re-encode khusus Lagu
- upscale `1.5x` atau `2x` dilakukan setelah `combined_all.mp4` selesai dibuat
  - project `368x640` menghasilkan final `368x640`, lalu `2x` menghasilkan `736x1280`
  - project `480x848` menghasilkan final `480x848`, lalu `2x` menghasilkan `960x1696`

Di UI:
- tersedia tombol `Compose Semua Adegan`
- saat `Compose Semua Adegan`, muncul dialog untuk memilih music, volume, dan checkbox `Compose Lagu`

Contoh:
```powershell
.\.venv\Scripts\python.exe scripts\generate_compose.py --project demo_project --scene scene_1
.\.venv\Scripts\python.exe scripts\generate_compose.py --project demo_project --scene scene_1 --scene scene_2
.\.venv\Scripts\python.exe scripts\generate_compose.py --project demo_project
.\.venv\Scripts\python.exe scripts\generate_compose.py --project demo_project --music-file ".\\music\\Another Night (Corporate).m4a" --music-volume 1.00
.\.venv\Scripts\python.exe scripts\generate_compose.py --project song_allah_mendengar_semua_doa --compose-song
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

## MiniMax H3 T2V-I2V Workflow

Scene type: `minimax-h3_t2v_i2v`

Implementasi adapter:

- `minimax_h3_t2v/minimax_h3_t2v.py`
- `minimax_h3_i2v/minimax_h3_i2v.py`
- `api_template/minimax_h3_t2v_api.json`
- `api_template/minimax_h3_i2v_api.json`

File prompt scene:

- `minimax_h3_t2v_prompt.json`
- `minimax_h3_i2v_prompt.json`

Kedua file memakai satu `positive_prompt` nested dengan field `id_old`, `id_new`, dan `en`; ketiganya berupa object JSON dengan struktur yang sama. Scene MiniMax H3 tidak memakai `negative_prompt`. Konfigurasi `lora_name` dan `lora_strength` untuk stage T2V dan I2V terpisah, tidak harus sama, dan masing-masing harus berasal dari folder `MINIMAX-H3` di ComfyUI.

Setiap tab MiniMax H3 memiliki group `H3 Cache` di bawah prompt. Konfigurasi ini disimpan pada key `h3_cache` di file prompt scene:

```json
"h3_cache": {
  "steps": 20,
  "reuse_threshold": 0.05,
  "start_percent": 0.15,
  "end_percent": 0.90,
  "max_steps": 1
}
```

Checkbox `H3 Cache` disimpan sebagai `h3_cache_enabled` dan default-nya `true`. Jika dicentang, workflow memakai node `UC_MiniMaxH3Cache` dari API saat ini. Jika tidak dicentang, node Cache dihapus dari workflow in-memory sebelum dikirim ke ComfyUI; template API di disk tetap tidak berubah.

Saat Cache dinonaktifkan, koneksi wajib tetap melewati LoRA 2:

```text
UNETLoader → LoRA 2 → LoRA 1 → BasicScheduler/BasicGuider
```

LoRA 1 tidak boleh dihubungkan langsung ke `UNETLoader`, karena hal tersebut akan membypass LoRA 2.

Validasi field H3 Cache: `Steps` integer `20`-`50`, `Reuse Threshold` `0.00`-`0.50`, `Start Percent` dan `End Percent` `0.00`-`1.00` dengan tepat dua desimal, serta `Max Steps` integer `1`-`3`. Semua field wajib diisi. Nilai default mengikuti API workflow MiniMax H3 dan konfigurasi ini ikut disalin oleh tombol `Edit Variasi`.

Aturan durasi:

- durasi scene adalah angka `1.0` sampai `30.0` dengan maksimal 1 angka desimal;
- durasi `<= 15.0` hanya menjalankan T2V;
- durasi `> 15.0` menjalankan T2V selama `15.0` detik lalu I2V dengan sisa durasi;
- contoh `23.2` menjadi T2V `15.0` detik + I2V `8.2` detik.

Untuk durasi 20 detik atau lebih, frame terakhir video T2V diekstrak, di-upload ke ComfyUI, lalu dipakai sebagai `first_frame` pada workflow I2V.

Secara default audio hasil ComfyUI dipertahankan di video root/variasi. Pada alur dua stage, audio T2V dan I2V tetap disusun berurutan pada video hasil stage, lalu saat Compose audio tersebut dibuat sebagai master `.comfy_audio_source/audio.wav` jika cache belum ada dan dicampur dengan speech serta sound effect scene.

Kontrol audio per stage:

- tab `MINIMAX-H3_T2V` memiliki checkbox `Hapus Sound` untuk output T2V;
- tab `MINIMAX-H3_I2V` memiliki checkbox `Hapus Sound` untuk output I2V;
- setelah file video selesai diunduh, seluruh frame hasil generasi dipertahankan;
- jika `Hapus Sound` dicentang, audio output stage kemudian dihapus sebelum ekstraksi frame, concat T2V-I2V, penyimpanan master audio, atau proses audio scene berikutnya;
- jika hanya satu stage yang dibisukan, concat memasukkan audio silence pada stage tersebut sehingga audio stage lain tetap berada pada timeline yang benar.

Node workflow utama:

- T2V:
  - durasi: node `133`, input `value`
  - H3 Cache: Steps node `124`; parameter cache node `137`
  - Cache aktif: `127 → 137 → 136 → 135`
- Cache nonaktif: `127 → 136 → 135`
- node Steps tetap dioverwrite dari konfigurasi tab walaupun Cache nonaktif
  - resolusi: node `115` (`ResolutionSelector`)
  - FPS workflow tetap `24` pada node `130`; expression frame pada node `132` menggunakan FPS `24`
- LoRA: node `135`
- LoRA kedua: node `136`; konfigurasi disimpan sebagai `lora_name_2` dan `lora_strength_2`
- I2V:
  - durasi: node `135`, input `value`
  - H3 Cache: Steps node `126`; parameter cache node `138`
  - Cache aktif: `129 → 138 → 137 → 136`
- Cache nonaktif: `129 → 137 → 136`
- node Steps tetap dioverwrite dari konfigurasi tab walaupun Cache nonaktif
  - resolusi: node `115` (`ResolutionSelector`)
  - FPS workflow tetap `24` pada node `132`; expression frame pada node `134` menggunakan FPS `24`
- gambar awal: node `114`
- LoRA: node `136`
- LoRA kedua: node `137`; konfigurasi disimpan sebagai `lora_name_2` dan `lora_strength_2`

Untuk scene `minimax-h3_s2v` dan `minimax-h3_r2v`, H3 Cache memakai Steps node `124` dan parameter cache node `162`:

- Cache aktif: `127 → 162 → 156 → 157` pada template R2V saat ini;
- Cache nonaktif: `127 → 157 → 156`;
- node Steps tetap dioverwrite dari konfigurasi tab walaupun Cache nonaktif;
- node `162` dihapus dari workflow in-memory saat checkbox tidak dicentang;
- S2V menggunakan adapter R2V yang sama.

Prompt MiniMax H3 mengikuti:

- `api_production/AGENT-SKILLS/MINIMAX-H3/SKILL.md`
- `api_production/AGENT-SKILLS/MINIMAX-H3/references/base-en.txt`
- `api_production/AGENT-SKILLS/SCENE-MINIMAX-H3-T2V-I2V.md`

## MiniMax H3 I2V Workflow

Scene type: `minimax-h3_i2v`

- durasi berupa angka `1.0` sampai `15.0` dengan maksimal 1 angka desimal
- tab berurutan: `Meta`, `Gambar Awal`, `Image Edit`, `MINIMAX-H3_I2V`, `Agentic`, `Aset`
- gambar terbaru di root scene menjadi `Picture 1` dan input node `LoadImage`
- hanya workflow MiniMax H3 I2VA yang dijalankan; tidak ada stage T2V
- setelah output ComfyUI diunduh, seluruh frame hasil generasi MiniMax dipertahankan;
- secara default audio hasil ComfyUI dipertahankan di video root/variasi dan baru dicampur dengan speech serta sound effect saat Compose; master audio dibuat saat Compose di `.comfy_audio_source/audio.wav`
- tab `MINIMAX-H3_I2V` memiliki checkbox `Hapus Sound`; jika aktif, audio output ComfyUI dihapus setelah video selesai diunduh dan sebelum proses audio scene berikutnya; Compose tidak membuat master dari video yang sudah tidak memiliki audio
- prompt utama ada di `minimax_h3_i2v_prompt.json` dan tidak memiliki `negative_prompt`
- jika `id_new` diedit, runtime meregenerasi `en` memakai aturan prompt I2VA MiniMax H3 dan menolak format yang tidak valid
- LoRA pertama dan kedua dibaca dari `lora_name`/`lora_strength` serta `lora_name_2`/`lora_strength_2` pada file prompt dan folder `MINIMAX-H3`
- ukuran scene pada prompt JSON diterjemahkan ke `aspect_ratio` dan `megapixels` pada node `ResolutionSelector`; untuk `minimax-h3_t2v_i2v`, ukuran pada tab T2V menjadi sumber ukuran kedua stage
- FPS workflow ditetapkan `24`; nilai FPS diterapkan ke node `132` dan expression frame node `134`
- tombol `Buat Prompt` memakai `SCENE-MINIMAX-H3-I2V.md`, `MINIMAX-H3/SKILL.md`, `MINIMAX-H3/references/base-en.txt`, serta mode I2VA

## MiniMax H3 R2V Workflow

Template workflow:

- `api_template/minimax_h3_r2v_api.json`
- node utama: `136` (`MiniMaxH3ReferenceToVideo`)
- prompt dikirim langsung ke `136.inputs.prompt`
- resolusi dibaca dari node `115` (`ResolutionSelector`)
- durasi dibaca dari node `132` (`PrimitiveFloat`)
- durasi menerima angka desimal `1.0` sampai `15.0` dengan maksimal 1 angka desimal
- FPS workflow ditetapkan `24`; nilai FPS diterapkan ke node `130` dan expression frame node `131`
- LoRA pertama memakai node `156`, sedangkan LoRA kedua memakai node `157`
- field prompt `lora_name`/`lora_strength` dan `lora_name_2`/`lora_strength_2` diisi melalui dropdown UI
- output video disimpan melalui node `92`

Workflow ini memakai mode full-reference `Ref2VA` dari skill `MINIMAX-H3`. Formatnya berbeda dari `T2VA`/`I2VA`: prompt harus mempunyai enam section berikut secara berurutan:

1. `subject_definitions`
2. `summary`
3. `retention_analysis`
4. `detailed_description`
5. `overall_soundscape`
6. `non_diegetic_music`

Semua section ditulis dalam bahasa Inggris. Bahasa asli hanya dipertahankan untuk dialog, lirik, dan teks yang terlihat di dalam scene.

### Pemetaan input R2V

| Label prompt | Slot workflow |
| --- | --- |
| `<Picture 1>` | `ref_images.ref_image_0` |
| `<Picture 2>` | `ref_images.ref_image_1` |
| `<Picture 3>` | `ref_images.ref_image_2` |
| `<Video 1>` | `ref_videos.ref_video_0` |
| audio sinkron dari `<Video 1>` | `ref_video_audios.ref_video_audio_0` |
| `<Audio 1>` | `ref_audios.ref_audio_0` |
| `<Audio 2>` | `ref_audios.ref_audio_1` |
| `<Audio 3>` | `ref_audios.ref_audio_2` |

`<Picture N>`, `<Video N>`, dan `<Audio N>` memiliki penomoran independen. Audio yang ikut di dalam `Video 1` dapat diberi label audio tersendiri apabila perannya perlu dijelaskan secara eksplisit, misalnya:

```text
<Video 1> is the source video for the target video edit.
<Audio 4> is the synchronized audio track of <Video 1> and is reused in the target video.
```

`<Audio 4>` adalah label semantik prompt, bukan berarti audio tersebut masuk ke `ref_audios.ref_audio_3`. Koneksi teknisnya tetap `ref_video_audios.ref_video_audio_0`.

### Aturan label referensi

- `<Subject N>` mengidentifikasi orang, hewan, objek, lingkungan, pakaian, pose, aksi, atau konten visual yang digunakan dalam video.
- `<Picture N>` digunakan jika gambar menjadi frame awal, keyframe, frame akhir, atau anchor komposisi/storyboard.
- `<Video N>` digunakan untuk sumber editing, continuation, gerakan kamera, cut, ritme, atau struktur temporal.
- `<Audio N>` digunakan untuk audio yang disalin atau direferensikan: musik, voice timbre, dialog, lirik, sound effect, beat, atau continuity.
- Jika karakter dari `Video 1` dipakai sebagai konten visual, karakter tersebut tetap diberi `<Subject N>`; `<Video 1>` hanya menandai sumber video.
- Label yang sudah ditetapkan harus konsisten di keenam section.
- Token dalam tanda `<...>` tidak boleh diterjemahkan atau diubah, termasuk `<Subject N>`, `<Picture N>`, `<Video N>`, dan `<Audio N>`.

### Bentuk prompt Ref2VA

Contoh minimal yang mengikuti skill:

```text
subject_definitions:
<Subject 1> is the woman whose appearance comes from <Picture 1> and whose movement comes from <Video 1>.
<Picture 1> is the opening composition reference for [Shot 1].
<Video 1> is the source video for the target video edit.
<Audio 1> is the standalone voice-timbre reference for <Subject 1> (S1).
<Audio 4> is the synchronized audio track of <Video 1> and is reused in the target video.

summary:
[video editing + audio reuse + keyframe completion] The target video adapts <Video 1> while preserving <Subject 1>, beginning from the composition established by <Picture 1>, and reusing the synchronized audio from <Audio 4>.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - the subject's identity and clothing are retained.
<Picture 1> ([Shot 1] first frame): fully_preserved - its opening composition is retained.
<Video 1> (source video structure): partially_preserved - its movement and timing are adapted.
<Audio 1>: reference - its voice timbre guides <Subject 1> (S1) without copying the signal.
<Audio 4>: fully_copy - the synchronized audio from <Video 1> is reused in the target video.

detailed_description:
The target video uses a cinematic live-action style with soft natural lighting.
[Shot 1] The scene begins from <Picture 1>. <Subject 1> stands in the same position and clothing while the adapted motion and temporal structure of <Video 1> unfold. The synchronized audio from <Audio 4> remains audible throughout the shot. <Subject 1> (S1) speaks using the voice timbre referenced from <Audio 1>, saying, <d>[English] Welcome home.</d>

overall_soundscape:
The copied ambient layer from <Audio 4> continues throughout the target video.

non_diegetic_music:
N/A
```

Aturan tambahan:

- `summary` dimulai dengan task-type dalam tanda kurung siku, misalnya `[reference generation]`, `[video editing + audio reuse]`, atau gabungan beberapa task type.
- Jangan menganggap keberadaan video/audio otomatis berarti `video editing` atau `audio reuse`; gunakan task type sesuai peran sebenarnya.
- `retention_analysis` memakai marker tetap: `fully_preserved`, `partially_preserved`, `attribute_transfer`, `weak_reference`, `fully_copy`, `reference`, atau `weak_reference`.
- `detailed_description` adalah bagian utama dan menjelaskan video berdasarkan urutan playback, shot, komposisi, subjek, aksi, kamera, suara, dialog, serta titik penggunaan referensi.
- Shot pertama memakai `[Shot 1]` tanpa timestamp. Shot berikutnya memakai format `[Shot N] At MM:SS.mmm, ...`.
- Speaker memakai ID stabil `(S1)`, `(S2)`, dan seterusnya. Dialog/lyrics ditulis dalam `<d>[Language] ...</d>`.
- Dialog dan lirik lengkap hanya ditulis di `detailed_description`, bukan di `overall_soundscape` atau `non_diegetic_music`.

Adapter `minimax_h3_r2v/minimax_h3_r2v.py` sekarang menyediakan builder workflow in-memory. Adapter ini dipakai oleh scene `minimax-h3_s2v` dan dapat menghapus referensi yang tidak digunakan sebelum workflow dikirim ke ComfyUI.

## MiniMax H3 S2V Workflow

Scene type: `minimax-h3_s2v`

Scene ini memakai tab dan alur S2V WAN22, dengan perbedaan berikut:

- tab `Gambar Awal` tetap tersedia;
- tab utama bernama `MINIMAX-H3_S2V`;
- tab `Image Edit` tidak tersedia;
- urutan tab: `Meta`, `Gambar Awal`, `MINIMAX-H3_S2V`, `Agentic`, `Aset`;
- tab utama memiliki `Ukuran`, dua LoRA, `Prompt Positif`, dan `Buat Prompt`; FPS workflow tetap `24` tanpa dropdown UI;
- tidak ada `CFG` dan `Prompt Negatif`;
- workflow sumber selalu `api_template/minimax_h3_r2v_api.json`;
- hanya Picture 1 dan Audio 1 yang digunakan.

Pemetaan input runtime:

- gambar terbaru di root scene di-upload ke node `143` (`Picture 1`), lalu masuk ke `ref_images.ref_image_0`;
- audio speech terbaru yang berawalan `speech_` di root scene di-upload ke node `153` (`Audio 1`), lalu masuk ke `ref_audios.ref_audio_0`;
- node Picture 2 (`144`), Picture 3 (`151`), Video 1 (`152`), Audio 2 (`154`), dan Audio 3 (`155`) dihapus dari workflow in-memory;
- koneksi `ref_images.ref_image_1`, `ref_images.ref_image_2`, `ref_videos.ref_video_0`, `ref_video_audios.ref_video_audio_0`, `ref_audios.ref_audio_1`, dan `ref_audios.ref_audio_2` juga dihapus.

Durasi:

- durasi scene tidak ditentukan dari dropdown Meta;
- durasi dibaca dari file audio speech yang dipilih memakai `ffprobe`;
- audio dengan durasi lebih dari `15` detik membuat scene tidak dapat dijalankan;
- durasi audio dimasukkan langsung ke node `132` (`PrimitiveFloat`), yang menjadi sumber panjang frame node `131`;
- setelah output video diunduh, seluruh frame hasil generasi dipertahankan; penyesuaian durasi dilakukan pada WAV sebelum workflow dikirim.
- FPS workflow ditetapkan `24` pada node `130` dan expression frame node `131`.
Ukuran mengikuti mapping `ResolutionSelector` MiniMax H3 yang sama dengan scene MiniMax H3 lainnya. Prompt memakai mode `Ref2VA` dengan enam section skill MINIMAX: `subject_definitions`, `summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`, dan `non_diegetic_music`.

## Format Prompt MiniMax H3

Kontrak file yang disimpan:

```json
{
  "positive_prompt": {
    "id_old": { "mode": "T2VA", "shots": [], "overall_soundscape": "...", "non_diegetic_music": "..." },
    "id_new": { "mode": "T2VA", "shots": [], "overall_soundscape": "...", "non_diegetic_music": "..." },
    "en": { "mode": "T2VA", "shots": [], "overall_soundscape": "...", "non_diegetic_music": "..." }
  },
  "lora_name": "MINIMAX-H3/example.safetensors",
  "lora_strength": 1.0,
  "lora_name_2": "MINIMAX-H3/example-2.safetensors",
  "lora_strength_2": 1.0,
  "width": 368,
  "height": 640
}
```

Aturan bahasa dan sinkronisasi:

- `en` berisi object berbahasa Inggris dan merupakan satu-satunya object yang diserialisasi untuk ComfyUI
- `id_new` berisi object Indonesia yang ditampilkan dan dapat diedit di UI
- `id_old` selalu deep-copy dari `id_new` setelah generate/translate/save berhasil
- Buat Prompt MiniMax meminta LLM menghasilkan object `en` saja, bukan `id_new` dan `id_old`
- pipeline menerjemahkan hanya field teks natural-language di `en` satu per satu menjadi `id_new`; nilai angka dan struktur dikopikan secara lokal
- jika `id_new == id_old`, Save tidak melakukan translasi
- jika `id_new != id_old`, Save menerjemahkan field teks `id_new` satu per satu ke Inggris untuk memperbarui `en`, kemudian menyalin `id_new` ke `id_old`

Struktur satu item `shots`:

```json
{
  "shot_id": "Shot 1",
  "start": 0.0,
  "end": 2.5,
  "visual": "Deskripsi komposisi, subjek, lingkungan, gaya, dan pencahayaan.",
  "action": "Aksi atau perubahan keadaan subjek selama shot.",
  "camera": "Framing, posisi, atau gerakan kamera.",
  "dialogue": "Dialog pada shot atau string kosong.",
  "diegetic_sound": "Suara yang benar-benar terjadi di dalam adegan."
}
```

Aturan multi-shot:

- `shots` minimal berisi satu item
- `shot_id` wajib string berurutan: `Shot 1`, `Shot 2`, dan seterusnya
- shot pertama mulai pada `0.0`; waktu harus meningkat, tidak tumpang tindih, dan akhir shot terakhir mengikuti durasi stage
- setiap shot wajib mempunyai `visual`, `action`, `camera`, `dialogue`, dan `diegetic_sound`
- `overall_soundscape` dan `non_diegetic_music` berada di luar `shots` karena berlaku untuk keseluruhan video
- perubahan kecil jarak/sudut sebaiknya dinyatakan sebagai camera motion dalam shot yang sama; cut baru harus memberikan informasi visual, ruang, keadaan, sudut pandang, atau waktu yang baru
- identitas karakter, pakaian, objek, layout, pencahayaan, serta ID pembicara harus konsisten lintas shot

T2VA tidak memiliki field `reference`. I2VA wajib menambahkan:

```json
"reference": {
  "instruction": "fully referenced",
  "picture": "Picture 1",
  "source": "[Shot 1]",
  "time": 0.0
}
```

Saat dikirim ke ComfyUI, object `en` diserialisasi menjadi tiga bagian:

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description:
[Shot 1] From 0.00 to 2.50 seconds, visual: ...; action: ...; camera: ...; dialogue: ...; diegetic sound: ....
[Shot 2] From 2.50 to 5.00 seconds, visual: ...; action: ...; camera: ...; dialogue: ...; diegetic sound: ....

overall_soundscape: ...

non_diegetic_music: ...
```

Baris reference hanya ada untuk I2VA. T2VA langsung dimulai dari `integrated_multimodal_description`.

Token yang wajib dipertahankan persis selama translasi per-field:

- semua substring dalam `<...>`, termasuk `<Subject N>`, `<Picture N>`, `<Video N>`, `<Audio N>` dan nomor aktualnya
- token kontrol `<d>`, `</d>`, `<scenetrans>`, dan `<cutoff>`
- identifier `[Shot N]`, `(S1)`, `(S2)`, `(S1,S2)`, serta mode `T2VA`, `I2VA`, `FL2VA`, `L2VA`, dan `Ref2VA`

Mapping ukuran scene MiniMax H3 ke `ResolutionSelector`:

| Ukuran | `aspect_ratio` | `megapixels` |
| --- | --- | ---: |
| `368x640` | `9:16 (Portrait Widescreen)` | `0.2` |
| `480x848` | `9:16 (Portrait Widescreen)` | `0.3` |
| `720x1280` | `9:16 (Portrait Widescreen)` | `0.4` |
| `640x368` | `16:9 (Widescreen)` | `0.2` |
| `848x480` | `16:9 (Widescreen)` | `0.3` |
| `1280x720` | `16:9 (Widescreen)` | `0.4` |

Semua mapping memakai `multiple=32`. Karena itu, output aktual node `ResolutionSelector` MiniMax dapat dibulatkan ke ukuran kompatibel terdekat yang lebih kecil, misalnya target UI/project `368x640` dapat menghasilkan raw output MiniMax `352x608`. Final Compose kemudian menormalkan kembali video ke ukuran `project_settings.json.video_size` menggunakan `scale + pad`.

Mapping ini berlaku untuk `minimax-h3_t2v_i2v`, `minimax-h3_i2v`, `minimax-h3_s2v`, dan `minimax-h3_r2v`. Nilai `width` dan `height` tetap disimpan di file prompt scene; workflow JSON meneruskannya melalui node `115` (`ResolutionSelector`) sebagai kombinasi `aspect_ratio`, `megapixels`, dan `multiple`.

Pada workflow MiniMax, expression jumlah frame selalu menggunakan FPS `24`. Formula frame mengikuti grid valid `frame_count % 17 == 5`, sehingga durasi aktual dapat sedikit lebih panjang dari durasi input. Seluruh frame tersebut merupakan bagian dari output generasi dan tidak dipotong oleh aplikasi.

Timeout runtime:

- workflow ComfyUI per call: `7200` detik
- call LLM: `600` detik
- call Gemini TTS atau ElevenLabs TTS: `600` detik
- tidak ada timeout tambahan per scene; jika satu scene mengirim beberapa workflow, setiap workflow memiliki timeout sendiri

## Logging

File logging utama:
- `logging_config.py`

Log runtime default:
- `content_creation.log`
- kegagalan HTTP saat mengirim workflow ke ComfyUI menyertakan status, URL, dan body respons server (maksimal 4000 karakter) agar error validasi node/LoRA dapat ditelusuri


## Catatan MiniMax H3 (alur prompt dan dialog)

Dokumentasi ini menjadi ringkasan aturan terbaru untuk seluruh scene MiniMax H3.

- File prompt scene yang didukung mencakup `minimax_h3_t2v_prompt.json`, `minimax_h3_i2v_prompt.json`, `minimax_h3_s2v_prompt.json`, dan `minimax_h3_r2v_prompt.json`.
- Referensi ringkas yang dikirim ke LLM untuk tombol `Buat Prompt` dan Agentic disesuaikan dengan scene: `SCENE-GENERAL.md` serta dokumen scene dan prompt khususnya. Aturan dialog bersama berasal dari `MINIMAX-H3-DIALOG.md`.
- S2V hanya boleh memakai reference aktif `<Picture 1>` dan `<Audio 1>`. R2V memakai manifest reference aktif secara dinamis, dengan batas maksimal 3 Picture, 3 Audio, dan 1 Video. Token reference yang tidak aktif tidak boleh dikembalikan oleh LLM.
- Struktur JSON keluaran harus mengikuti schema file scene, tetapi bagian `OUTPUT YANG DIHASILKAN` pada input Agentic tetap berupa schema kosong agar LLM mengisi konfigurasi berdasarkan scene/variasi yang diberikan.
- Validasi saat save berfokus pada JSON `id_new` yang valid. Translasi `id_new` ke `en` dilakukan saat scene dijalankan; bila validasi runtime atau translasi gagal, eksekusi scene dihentikan.

### Aturan dialog MiniMax H3

Gunakan speaker stabil seperti `(S1)` dan `(S2)`, lalu tulis dialog aktual dalam format:

`<d>[Bahasa] Kalimat dialog.</d>`

Pada translasi runtime MiniMax dari `id_new` ke `en`, seluruh blok `<d>...</d>` diproteksi dan tidak diterjemahkan. Teks di luar blok dialog tetap diterjemahkan. Dengan demikian dialog dapat dipertahankan persis dalam bahasa yang diminta, termasuk tanda baca dan isi kalimatnya. Aturan lengkapnya ada di `api_production/AGENT-SKILLS/MINIMAX-H3-DIALOG.md`.
