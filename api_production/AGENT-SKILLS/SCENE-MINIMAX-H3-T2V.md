# Scene minimax-h3_t2v

Dokumen ini adalah aturan scene untuk satu workflow MiniMax H3 T2V. Scene memakai mode base T2VA dan tidak memakai gambar referensi atau stage I2V.

## File output

Scene harus menyediakan file:

- `minimax_h3_t2v_prompt.json`

Struktur file:

```json
{
  "positive_prompt": {
    "id_old": {
      "mode": "T2VA",
      "shots": [],
      "overall_soundscape": "",
      "non_diegetic_music": ""
    },
    "id_new": {
      "mode": "T2VA",
      "shots": [],
      "overall_soundscape": "",
      "non_diegetic_music": ""
    },
    "en": {
      "mode": "T2VA",
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

Field `positive_prompt.id_old`, `positive_prompt.id_new`, dan `positive_prompt.en` semuanya object JSON nested dengan struktur yang sama. `id_old` dan `id_new` berisi nilai bahasa Indonesia; `en` berisi nilai bahasa Inggris. T2V menggunakan `mode: "T2VA"` dan tidak memiliki `reference`. Ketiganya wajib memiliki array `shots` serta `overall_soundscape` dan `non_diegetic_music`. Setiap shot wajib memiliki `shot_id`, `start`, `end`, `visual`, `action`, `camera`, `dialogue`, dan `diegetic_sound`.

Aturan bilingual:

- `positive_prompt` wajib berupa object dengan field `id_old`, `id_new`, dan `en`.
- Tombol `Buat Prompt` meminta LLM membuat object `en` terlebih dahulu.
- Runtime menerjemahkan field teks `en` satu per satu menjadi object `id_new`; key, angka, timing, `shot_id`, dan urutan array disalin tanpa perubahan.
- `id_old` adalah deep-copy object `id_new`.
- UI menampilkan object `id_new` sebagai JSON yang dapat diedit.
- Jika `id_new` sama dengan `id_old`, Save tidak mengubah atau menerjemahkan prompt.
- Jika `id_new` berbeda dari `id_old`, runtime menerjemahkan field teks `id_new` satu per satu untuk membentuk ulang `en`, lalu menyalin `id_new` ke `id_old`.
- Hanya `en` yang diserialisasi dan dikirim ke MiniMax H3/ComfyUI.
- Jangan menghapus salah satu dari tiga field tersebut.
- Jangan menaruh prompt dalam fenced code block atau menambahkan penjelasan di dalam nilai prompt.

Nilai `lora_name` dan `lora_strength` harus berasal dari folder `MINIMAX-H3` di ComfyUI. Jangan menambahkan field `negative_prompt`; scene MiniMax H3 ini hanya memakai prompt positif.

## Aturan durasi

- Scene `minimax-h3_t2v` menerima angka `0.0` sampai `30.0` detik dengan maksimal 4 angka desimal. Gunakan nilai `Scene duration` tanpa membulatkannya ke pilihan preset.
- Seluruh durasi dikirim ke satu workflow T2V; tidak ada pembagian durasi atau stage lanjutan.
- FPS MiniMax H3 ditetapkan `24`.
- Durasi `0.0` tetap menghasilkan output minimum 5 frame pada 24 FPS; gunakan timeline singkat yang sesuai output minimum tersebut.

## Prompt T2VA

Tulis `minimax_h3_t2v_prompt.json.positive_prompt` mengikuti aturan prompt T2VA.

Prompt Inggris pada field `en` harus memiliki tiga bagian dalam urutan berikut:

```text
integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
```

Ketentuan:

- Tidak memakai instruksi alignment gambar pada awal prompt T2VA.
- `integrated_multimodal_description` menjelaskan visual, shot, aksi, kamera, dialog, dan suara diegetic sepanjang timeline.
- `overall_soundscape` menjelaskan ambience dan suara fisik.
- `non_diegetic_music` menjelaskan musik yang hanya terdengar oleh penonton atau menggunakan `N/A` bila tidak ada.
- Tulis seluruh bagian prompt dalam bahasa Inggris pada `en`.
- Dialog dan teks yang terlihat di layar tetap mempertahankan bahasa asli dan tanda baca aslinya.
- Timing dan cut harus berada di dalam durasi scene penuh.

## Resolusi

Ukuran scene disimpan pada prompt JSON dan diterapkan ke node `ResolutionSelector`:

| Ukuran | `aspect_ratio` | `megapixels` |
|---|---|---:|
| `368x640` | `9:16 (Portrait Widescreen)` | `0.2` |
| `480x848` | `9:16 (Portrait Widescreen)` | `0.4` |
| `720x1280` | `9:16 (Portrait Widescreen)` | `0.9` |
| `640x368` | `16:9 (Widescreen)` | `0.2` |
| `848x480` | `16:9 (Widescreen)` | `0.4` |
| `1280x720` | `16:9 (Widescreen)` | `0.9` |

## Checklist file hasil akhir

- `minimax_h3_t2v_prompt.json` tersedia.
- `positive_prompt` memiliki `id_old`, `id_new`, dan `en`.
- Prompt mengikuti format T2VA dan tidak memiliki negative prompt.
- `lora_name` dan `lora_strength` berasal dari folder `MINIMAX-H3` di ComfyUI.
- Tidak ada JSON tambahan yang diperlukan untuk stage lain.
