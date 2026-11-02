# Petunjuk Buat Prompt untuk scene

Gunakan informasi yang tersedia dalam request `Buat Prompt`:

- `Context` memuat `Scene title`, `Scene type`, target prompt, mode aktif, serta ukuran, durasi, atau referensi yang tersedia untuk target tersebut.
- `Prompt`, jika disertakan, berisi prompt awal yang perlu dikembangkan.
- `ADDITIONAL INSTRUCTION FROM UI`, jika disertakan, berisi instruksi pengguna untuk target aktif.
- `ORDERED PICTURE MANIFEST`, gambar terlampir, dan manifest referensi aktif, jika tersedia, menentukan sumber dan urutan referensi yang boleh digunakan.

## Aturan penyusunan prompt

- Susun hanya prompt untuk target dan tahap aktif. Dokumen scene dapat menjelaskan beberapa file atau tahap, tetapi satu request tidak meminta seluruh konfigurasi scene.
- Ikuti schema respons dan mode aktif pada request. Untuk MiniMax H3, hasilkan object `en`; aplikasi menangani translasi ke `id_new` dan sinkronisasi `id_old`.
- Gunakan durasi dari konteks sesuai aturan scene dan tahap aktif. Pertahankan nilai desimal; jangan membulatkannya ke pilihan durasi preset.
- Pertahankan token dan urutan referensi aktif. Contoh dalam dokumen tidak menambah referensi yang tersedia pada scene.
- Pertahankan parameter teknis seperti ukuran dan LoRA; perubahan kreatif hanya diterapkan pada isi prompt.
- Informasi yang tidak disertakan dalam request tidak perlu diminta atau direka.
