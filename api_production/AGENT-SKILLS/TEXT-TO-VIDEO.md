# Petunjuk pembuatan WAN T2V

## Konfigurasi JSON

Gunakan satu file prompt:

1. `wan22_t2v_prompt.json`

Field yang dapat diatur:

- `positive_prompt`
- `negative_prompt`
- `width` dan `height`
- empat konfigurasi LoRA WAN

Prompt bilingual menggunakan `id_old`, `id_new`, dan `en`. Teks Indonesia ditulis pada `id_new`; runtime memakai `en` setelah sinkronisasi translasi.

## Alur pembuatan video

1. Scene tidak membutuhkan gambar awal.
2. Pipeline membaca `wan22_t2v_prompt.json`.
3. Satu workflow WAN T2V dikirim ke ComfyUI.
4. Durasi scene `5`, `10`, atau `15` detik diterapkan langsung ke panjang workflow.
5. Video hasil workflow menjadi output scene.

## Petunjuk prompt

Tulis prompt positif dengan menjelaskan subjek, aksi, kamera, komposisi, pencahayaan, dan gaya visual. Gunakan prompt negatif untuk artefak atau elemen yang harus dihindari.
