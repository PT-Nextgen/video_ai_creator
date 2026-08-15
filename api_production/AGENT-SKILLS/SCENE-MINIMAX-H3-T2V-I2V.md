# Scene minimax-h3_t2v_i2v

Dokumen ini adalah aturan scene untuk pipeline MiniMax H3 T2V lalu I2V. Untuk menulis isi prompt MiniMax H3, wajib membaca referensi berikut:

- `MINIMAX-H3/SKILL.md`
- `MINIMAX-H3/references/base-en.txt`

Gunakan `MINIMAX-H3/references/ref-en.txt` hanya jika workflow full-reference diperlukan pada pengembangan scene lain. Scene ini memakai mode base T2VA dan I2VA.

Tombol `Buat Prompt` pada tab T2V dan I2V memakai dokumen scene ini, `MINIMAX-H3/SKILL.md`, dan `MINIMAX-H3/references/base-en.txt` sebagai referensi pembuatan scene yang sama. Mode aktif tetap menentukan format akhir: aturan I2VA tidak boleh diterapkan ke T2VA, dan aturan T2VA tidak boleh menggantikan instruksi first-frame I2VA.

## File output

Agentic wajib menghasilkan dua file JSON:

- `minimax_h3_t2v_prompt.json`
- `minimax_h3_i2v_prompt.json`

Struktur kedua file:

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

Field `positive_prompt.id_old`, `positive_prompt.id_new`, dan `positive_prompt.en` semuanya object JSON nested dengan struktur yang sama. `id_old` dan `id_new` berisi nilai bahasa Indonesia; `en` berisi nilai bahasa Inggris. T2V menggunakan `mode: "T2VA"` dan tidak memiliki `reference`; I2V menggunakan `mode: "I2VA"` dan wajib memiliki `reference` untuk `Picture 1`. Ketiganya wajib memiliki array `shots` serta `overall_soundscape` dan `non_diegetic_music`. Setiap shot wajib memiliki `shot_id`, `start`, `end`, `visual`, `action`, `camera`, `dialogue`, dan `diegetic_sound`.

Aturan bilingual:

- `positive_prompt` wajib berupa object dengan field `id_old`, `id_new`, dan `en`.
- Tombol `Buat Prompt` meminta LLM membuat object `en` terlebih dahulu.
- Runtime menerjemahkan field teks `en` satu per satu menjadi object `id_new`; key, angka, timing, `shot_id`, urutan array, dan `reference` disalin tanpa perubahan.
- `id_old` adalah deep-copy object `id_new`.
- UI menampilkan object `id_new` sebagai JSON yang dapat diedit.
- Jika `id_new` sama dengan `id_old`, Save tidak mengubah atau menerjemahkan prompt.
- Jika `id_new` berbeda dari `id_old`, runtime menerjemahkan field teks `id_new` satu per satu untuk membentuk ulang `en`, lalu menyalin `id_new` ke `id_old`.
- Hanya `en` yang diserialisasi dan dikirim ke MiniMax H3/ComfyUI.
- Jangan menghapus salah satu dari tiga field tersebut.
- Jangan menaruh prompt dalam fenced code block atau menambahkan penjelasan di dalam nilai prompt.

### Kontrak respons Agentic MiniMax

Khusus saat Agentic membuat variasi, LLM hanya mengembalikan `positive_prompt.en` sebagai object JSON nested berbahasa Inggris. LLM tidak membuat dan tidak mengembalikan `positive_prompt.id_new` maupun `positive_prompt.id_old`.

Setelah respons LLM diterima, pipeline Agentic melakukan langkah berikut:

1. Memvalidasi object `en` terhadap mode T2VA atau I2VA yang sesuai.
2. Menerjemahkan setiap field teks natural-language di dalam `en` satu per satu menjadi bahasa Indonesia untuk membentuk object `id_new`.
3. Menyalin key, array, angka, timing, `shot_id`, `mode`, dan `reference` tanpa diterjemahkan atau diubah.
4. Membuat `id_old` sebagai deep-copy dari object `id_new`.
5. Menyimpan file variasi dalam bentuk lengkap `positive_prompt.id_old`, `positive_prompt.id_new`, dan `positive_prompt.en`.

Dengan demikian, schema respons LLM Agentic untuk prompt MiniMax hanya memuat `positive_prompt: {"en": {...}}`, sedangkan schema file hasil variasi tetap memuat tiga field bilingual lengkap.

File T2V dan I2V memiliki konfigurasi LoRA yang terpisah. Nilai `lora_name` dan `lora_strength` pada T2V tidak harus sama dengan nilai pada I2V. Masing-masing pilihan LoRA harus berasal dari folder `MINIMAX-H3` di ComfyUI.

Jangan menambahkan field `negative_prompt`. MiniMax H3 scene ini hanya memakai prompt positif.

## Aturan durasi

- `1`, `5`, `10`, atau `15` detik: jalankan workflow T2V dan gunakan hasilnya sebagai video final.
- `20` detik: T2V `15` detik lalu I2V `5` detik.
- `25` detik: T2V `15` detik lalu I2V `10` detik.
- `30` detik: T2V `15` detik lalu I2V `15` detik.

Untuk durasi di atas 15 detik, frame terakhir hasil T2V menjadi `Picture 1` atau first frame untuk tahap I2V. Scene tidak membutuhkan gambar awal dari user.

## Prompt T2VA

Tulis `minimax_h3_t2v_prompt.json.positive_prompt` mengikuti `MINIMAX-H3/SKILL.md` dan `references/base-en.txt` mode T2VA.

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
- Timing dan cut harus berada di dalam durasi stage T2V.

## Prompt I2VA

Tulis `minimax_h3_i2v_prompt.json.positive_prompt` mengikuti mode I2VA pada `references/base-en.txt`.

Field `en` wajib dimulai dengan instruksi persis berikut:

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.
```

Setelah satu baris kosong, lanjutkan dengan tiga bagian inti:

```text
integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
```

Ketentuan I2VA:

- Shot pertama harus menjadikan frame terakhir T2V sebagai titik awal visual.
- Pertahankan identitas karakter, pakaian, warna, objek penting, layout, pencahayaan, dan hubungan ruang dari frame pertama.
- Jelaskan perkembangan aksi secara kontinu dari frame pertama menuju hasil akhir stage I2V.
- Jangan menulis seolah-olah gambar awal berasal dari folder scene user.
- Jangan memakai format FL2VA atau L2VA karena scene ini hanya mengirim satu first frame.
- Timing dan cut harus berada di dalam durasi stage I2V.

## Resolusi

Ukuran tidak dibuat bebas oleh agentic. Nilainya mengikuti ukuran project dan akan diterapkan ke node `ResolutionSelector`:

| Ukuran | `aspect_ratio` | `megapixels` |
|---|---|---:|
| `368x640` | `9:16 (Portrait Widescreen)` | `0.2` |
| `480x848` | `9:16 (Portrait Widescreen)` | `0.4` |
| `720x1280` | `9:16 (Portrait Widescreen)` | `0.9` |
| `640x368` | `16:9 (Widescreen)` | `0.2` |
| `848x480` | `16:9 (Widescreen)` | `0.4` |
| `1280x720` | `16:9 (Widescreen)` | `0.9` |

## Checklist file hasil akhir Agentic

- Kedua file JSON tersedia.
- Kedua `positive_prompt` memiliki `id_old`, `id_new`, dan `en`.
- Prompt T2V mengikuti format T2VA.
- Prompt I2V dimulai dengan instruksi first-frame alignment yang diwajibkan.
- Prompt T2V dan I2V tidak memiliki negative prompt.
- `lora_name` dan `lora_strength` T2V tersimpan terpisah dari nilai I2V dan tidak harus sama.
- Pilihan LoRA T2V dan I2V berasal dari folder `MINIMAX-H3` di ComfyUI.
- Tidak ada JSON tambahan di luar schema yang diperlukan.
