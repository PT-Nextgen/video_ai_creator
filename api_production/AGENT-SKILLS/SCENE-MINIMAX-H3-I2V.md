---
name: scene-minimax-h3-i2v
description: Create standalone MiniMax H3 I2V scenes with an optional generated initial image and a MiniMax H3 I2VA video stage.
---

# Scene minimax-h3_i2v

Scene ini adalah workflow I2V mandiri dengan dua kemungkinan tahap persiapan:

1. `Gambar Awal` membuat gambar awal dari `z_image_prompt.json` bila diperlukan.
2. Workflow MiniMax H3 I2VA memakai gambar terbaru di root folder scene sebagai `Picture 1`.

Gunakan aturan umum scene, aturan I2V MiniMax H3, dan aturan khusus prompt I2V dalam dokumen ini.

## File output

Scene harus menyediakan dua file JSON:

- `z_image_prompt.json`
- `minimax_h3_i2v_prompt.json`

`z_image_prompt.json` mengikuti aturan prompt Gambar Awal, termasuk field bilingual `id_old`, `id_new`, dan `en` pada prompt yang didukung.

`minimax_h3_i2v_prompt.json` harus mengikuti schema berikut tanpa menambah field baru:

```json
{
  "positive_prompt": {
    "id_old": {
      "mode": "I2VA",
      "reference": {
        "picture": "Picture 1",
        "source": "[Shot 1]",
        "time": 0.0,
        "instruction": "fully referenced"
      },
      "shots": [],
      "overall_soundscape": "",
      "non_diegetic_music": ""
    },
    "id_new": {
      "mode": "I2VA",
      "reference": {
        "picture": "Picture 1",
        "source": "[Shot 1]",
        "time": 0.0,
        "instruction": "fully referenced"
      },
      "shots": [],
      "overall_soundscape": "",
      "non_diegetic_music": ""
    },
    "en": {
      "mode": "I2VA",
      "reference": {
        "picture": "Picture 1",
        "source": "[Shot 1]",
        "time": 0.0,
        "instruction": "fully referenced"
      },
      "shots": [],
      "overall_soundscape": "",
      "non_diegetic_music": ""
    }
  },
  "lora_name": "MINIMAX-H3/AI-Girl-Fictional.safetensors",
  "lora_strength": 0,
  "width": 368,
  "height": 640
}
```

Field `positive_prompt.id_old`, `positive_prompt.id_new`, dan `positive_prompt.en` semuanya object JSON nested dengan struktur I2VA yang sama. `id_old` dan `id_new` berisi nilai bahasa Indonesia; `en` berisi nilai bahasa Inggris. Setiap object wajib memiliki `mode: "I2VA"`, `reference`, `shots`, `overall_soundscape`, dan `non_diegetic_music`. Setiap item `shots` wajib memiliki `shot_id`, `start`, `end`, `visual`, `action`, `camera`, `dialogue`, dan `diegetic_sound`.

Aturan MiniMax H3:

- `positive_prompt` wajib memiliki `id_old`, `id_new`, dan `en`.
- Tombol `Buat Prompt` meminta LLM membuat object `en`, lalu runtime menerjemahkan setiap field teks menjadi object `id_new`.
- Key, angka, timing, `shot_id`, urutan array, dan object `reference` disalin tanpa perubahan selama translasi.
- `id_old` adalah deep-copy object `id_new`; UI menampilkan `id_new` sebagai JSON yang dapat diedit.
- Jika `id_new` sama dengan `id_old`, Save tidak mengubah atau menerjemahkan prompt.
- Jika `id_new` berubah, runtime menerjemahkan setiap field teks `id_new` untuk membentuk ulang `en`, lalu menyalin `id_new` ke `id_old`.
- Hanya object `en` yang diserialisasi dan dikirim ke MiniMax H3/ComfyUI. Hasil I2VA tanpa alignment `Picture 1` dan tiga section wajib ditolak.
- `lora_name` dan `lora_strength` berasal dari pilihan LoRA folder `MINIMAX-H3`.
- Jangan menambahkan `negative_prompt` ke `minimax_h3_i2v_prompt.json`.
- Ukuran mengikuti ukuran project dan diterapkan ke node `ResolutionSelector`.

## Aturan durasi dan sumber gambar

- Durasi scene menerima angka `0.0` sampai `15.0` detik dengan maksimal 4 angka desimal, misalnya `7.5` atau `7.1234`.
- Gunakan durasi yang diberikan pada `Scene duration` tanpa membulatkannya ke pilihan preset. Nilai `0.0` tetap menghasilkan output minimum 5 frame pada runtime.
- Scene tidak menjalankan T2V.
- Ambil satu gambar terbaru dari root folder scene.
- Gambar tersebut menjadi `Picture 1` dan first frame workflow MiniMax H3 I2VA.
- Jangan menulis seolah-olah first frame berasal dari folder lain atau dari T2V.

## Prompt MiniMax H3 I2VA

Tulis `minimax_h3_i2v_prompt.json.positive_prompt` mengikuti aturan prompt I2VA.

Field `en` wajib dimulai persis dengan:

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.
```

Setelah satu baris kosong, tulis tiga bagian berikut dalam urutan yang sama:

```text
integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
```

Ketentuan:

- Mulai deskripsi dari komposisi, subjek, identitas karakter, pakaian, objek, pencahayaan, dan layout pada gambar awal.
- Kembangkan aksi secara kontinu dari first frame menuju akhir video.
- Pertahankan identitas karakter, warna, objek penting, hubungan ruang, dan gaya visual.
- Jelaskan shot, aksi, kamera, dialog, suara diegetic, ambience, dan musik sesuai aturan base-en.
- Untuk durasi positif, seluruh timing harus berada di dalam durasi scene yang diberikan. Untuk `0.0`, gunakan timeline singkat sesuai output minimum 5 frame pada 24 FPS.
- Jangan memakai format T2VA, FL2VA, L2VA, atau Ref2VA.

## Qwen Image Edit

Jika perlu menyiapkan gambar referensi baru, gunakan tab `Qwen Image Edit`. Proses ini terpisah dari workflow video MiniMax dan tidak mengubah file prompt scene.

## Checklist file hasil akhir

- Durasi scene berada pada rentang `0.0` sampai `15.0` detik dengan maksimal 4 angka desimal; timing mengikuti durasi aktif atau output minimum untuk `0.0`.
- `z_image_prompt.json` dan `minimax_h3_i2v_prompt.json` tersedia.
- `minimax_h3_i2v_prompt.json.positive_prompt` memiliki `id_old`, `id_new`, dan `en`.
- Prompt Inggris MiniMax dimulai dengan instruksi `<Picture 1>` yang diwajibkan.
- Prompt MiniMax memiliki tiga bagian base I2VA dalam urutan yang benar.
- Tidak ada `negative_prompt` pada file MiniMax.
- Gambar terbaru root scene dipakai sebagai first frame.
- LoRA MiniMax berasal dari folder `MINIMAX-H3`.
