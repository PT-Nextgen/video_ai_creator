# Scene MiniMax H3 S2V

## Tujuan

Scene `minimax-h3_s2v` membuat video MiniMax H3 Reference-to-Video dengan satu gambar awal dan satu audio referensi.

Workflow yang digunakan adalah `api_template/minimax_h3_r2v_api.json` dengan referensi berikut:

- `<Picture 1>` terhubung ke `ref_images.ref_image_0`.
- `<Audio 1>` terhubung ke `ref_audios.ref_audio_0`.
- Picture 2, Picture 3, Video 1, Audio 2, dan Audio 3 dihapus dari workflow.

## Prompt

Gunakan mode full-reference `Ref2VA` sesuai:

- `MINIMAX-H3/SKILL.md`
- `MINIMAX-H3/references/ref-en.txt`

Prompt harus memiliki enam section dalam urutan berikut:

1. `subject_definitions`
2. `summary`
3. `retention_analysis`
4. `detailed_description`
5. `overall_soundscape`
6. `non_diegetic_music`

Gunakan label `<Picture 1>` dan `<Audio 1>` secara konsisten. Jangan membuat label untuk referensi yang sudah dihapus. Semua section ditulis dalam bahasa Inggris, kecuali dialog, lirik, dan teks visual yang memang harus mempertahankan bahasa aslinya.

Audio 1 adalah audio yang dipakai oleh workflow. Jika audio hanya menjadi referensi karakteristik, gunakan marker `reference`. Jika audio disalin langsung, gunakan `fully_copy` atau `partially_copy` sesuai cakupannya.

## Durasi dan ukuran

- Durasi video mengikuti durasi file audio `speech_*` yang dipilih.
- Audio dengan durasi lebih dari 15 detik membuat scene tidak valid dan tidak boleh dijalankan.
- Video tidak boleh dipotong setelah output ComfyUI diterima.
- Ukuran memakai mapping ResolutionSelector MiniMax H3 yang sama dengan scene MiniMax H3 lainnya.

## Input UI

- Tab `Gambar Awal` tetap tersedia dan digunakan untuk membuat Picture 1.
- Runtime mengambil gambar terbaru dari root scene, seperti WAN22 S2V.
- Runtime mengambil audio speech terbaru dari root scene, seperti WAN22 S2V.
- Tab `MINIMAX-H3_S2V` hanya memiliki ukuran dan prompt positif; tidak ada CFG dan negative prompt.
