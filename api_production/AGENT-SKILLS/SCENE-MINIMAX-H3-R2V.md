# Scene MiniMax H3 R2V

## Tujuan

Scene `minimax-h3_r2v` membuat video MiniMax H3 Reference-to-Video dengan reference media yang dipilih secara dinamis.

Reference yang tersedia:

- maksimal 3 Picture;
- maksimal 3 Audio;
- maksimal 1 Video;
- minimal 1 reference dari salah satu kategori tersebut.

Reference yang tidak dipakai harus dihapus dari JSON dan workflow. Jika jumlah reference suatu kategori lebih sedikit, gunakan nomor terendah secara berurutan. Contoh: dua Picture harus menjadi `<Picture 1>` dan `<Picture 2>`; `<Picture 3>` tidak boleh muncul.

Token semantic seperti `<Subject 1>`, `<Shot 1>`, `<d>`, `</d>`, dan speaker ID bukan reference media dan tetap boleh digunakan jika diperlukan.

## Prompt

Gunakan mode full-reference `Ref2VA` sesuai `MINIMAX-H3-R2V-PROMPT.md`.

Prompt positif harus memiliki enam section berikut dalam urutan yang sama:

1. `subject_definitions`
2. `summary`
3. `retention_analysis`
4. `detailed_description`
5. `overall_soundscape`
6. `non_diegetic_music`

Semua section prompt `en` ditulis dalam bahasa Inggris. Dialog, lirik, dan teks visual harus mempertahankan bahasa aslinya jika memang menjadi bagian dari scene.

Gunakan hanya token Picture, Audio, dan Video yang tercantum pada reference aktif scene. Jangan membuat, mengganti nama, atau mengubah nomor token reference. Reference yang tidak tersedia tidak boleh disebutkan meskipun muncul dalam contoh atau dokumen lain.

Reference media harus dipertahankan konsisten di seluruh enam section. Reference non-media seperti `<Subject 1>` tetap boleh digunakan dan tidak tunduk pada batas jumlah Picture, Audio, atau Video.

Untuk Audio, jelaskan apakah audio digunakan sebagai reference karakteristik atau disalin ke hasil. Gunakan `reference`, `fully_copy`, atau `partially_copy` sesuai kebutuhan scene.

## Struktur file

Agentic menggunakan satu file input dan output:

- `minimax_h3_r2v_prompt.json`

Struktur prompt bilingual harus memiliki `id_old`, `id_new`, dan `en` dengan struktur nested yang sama. `id_old` dan `id_new` berisi bahasa Indonesia; `en` berisi bahasa Inggris.

MiniMax H3 R2V hanya menggunakan prompt positif. Jangan menambahkan `negative_prompt` atau field baru di luar schema scene.

## Kontrak Agentic

Agentic menerima template JSON dari root scene dengan isi prompt dikosongkan, tetapi struktur dan parameter teknis tetap dipertahankan sebagai acuan.

Output LLM wajib memiliki root JSON berikut:

```json
{
  "minimax_h3_r2v_prompt.json": {
    "positive_prompt": {
      "en": {}
    }
  }
}
```

LLM hanya membuat `positive_prompt.en`. Setelah validasi, pipeline menerjemahkan field teks `en` menjadi `id_new`, lalu membuat `id_old` sebagai salinan `id_new`. Key, angka, urutan array, timing, dan token reference tidak boleh diterjemahkan atau diubah.

## Durasi

- Durasi yang valid: `1`, `5`, `10`, atau `15` detik.
- Durasi lebih dari 15 detik tidak valid.
- Video tidak boleh dipotong setelah output ComfyUI diterima.
- Minimal satu reference aktif wajib tersedia sebelum scene dijalankan.

## Resolusi

Ukuran video mengikuti mapping `ResolutionSelector` MiniMax H3 yang sama dengan scene MiniMax H3 lainnya. Agentic tidak boleh mengubah ukuran secara bebas; nilai ukuran mengikuti pilihan pada UI dan konfigurasi scene.

## Input UI

- Tab `Meta` berisi metadata scene dan durasi.
- Tab `Gambar Awal` menampilkan media reference yang dipilih jika tersedia.
- Tab `MINIMAX-H3_R2V` berisi ukuran dan prompt positif R2V.
- Tab `Aset` digunakan untuk memilih Picture, Audio, dan Video reference.
- Tab `Agentic` digunakan untuk membuat variasi prompt.
- Tidak ada checkbox `Buat Image Awal`.
- Tidak ada checkbox `Hapus Sound`.

## Checklist validasi

- `minimax_h3_r2v_prompt.json` tersedia dan JSON valid.
- Minimal satu Picture, Audio, atau Video aktif.
- Jumlah maksimal tidak melebihi 3 Picture, 3 Audio, dan 1 Video.
- Nomor token setiap kategori dimulai dari 1 dan berurutan.
- Tidak ada token media yang tidak tersedia.
- Keenam section Ref2VA tersedia dan urutannya benar.
- `positive_prompt.id_old`, `id_new`, dan `en` memiliki struktur yang sama.
- `en` berisi bahasa Inggris, sedangkan `id_new` dan `id_old` berisi bahasa Indonesia.
- Tidak ada `negative_prompt` atau field tambahan yang tidak diperlukan.
