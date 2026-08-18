---
name: minimax-h3-s2v-prompt
description: Menulis prompt MiniMax H3 S2V dalam mode Ref2VA dengan satu Picture dan satu Audio aktif.
---

# MiniMax H3 S2V Prompt

Gunakan mode full-reference `Ref2VA` untuk scene S2V. Prompt harus memiliki tepat enam field berikut dan urutannya tidak boleh diubah:

```text
subject_definitions
summary
retention_analysis
detailed_description
overall_soundscape
non_diegetic_music
```

Semua nilai pada `positive_prompt.en` harus ditulis dalam bahasa Inggris. Dialog, lirik, dan teks visual dipertahankan dalam bahasa aslinya jika memang muncul di scene.

## Reference yang aktif

Workflow S2V hanya memiliki dua reference media:

```text
<Picture 1> = gambar awal scene
<Audio 1> = audio reference scene
```

Reference berikut tidak aktif dan dilarang ditulis:

```text
<Picture 2>
<Picture 3>
<Video 1>
<Audio 2>
<Audio 3>
```

Jangan membuat, mengganti nama, atau melompati nomor reference. Token semantic seperti `<Subject 1>`, `<Shot 1>`, `<d>`, `</d>`, dan speaker ID bukan reference media dan tetap boleh digunakan.

Pertahankan `<Picture 1>` dan `<Audio 1>` secara konsisten di seluruh field yang relevan. Jangan menyebut reference yang tidak aktif meskipun muncul dalam contoh atau dokumen lain.

## Struktur JSON

LLM hanya mengisi `positive_prompt.en`. Struktur yang dihasilkan harus seperti berikut; nilai kosong hanya contoh struktur:

```json
{
  "positive_prompt": {
    "en": {
      "subject_definitions": "",
      "summary": "",
      "retention_analysis": "",
      "detailed_description": "",
      "overall_soundscape": "",
      "non_diegetic_music": ""
    }
  }
}
```

Jangan menambahkan `mode`, `shots`, `reference`, `negative_prompt`, atau field baru lain ke object Ref2VA S2V. Pipeline akan membuat `id_new` dan `id_old` setelah proses translasi.

## Cara menulis enam field

- `subject_definitions`: jelaskan identitas subjek pada `<Picture 1>`, lingkungan, dan hubungan subjek dengan reference audio `<Audio 1>` bila relevan.
- `summary`: ringkas tujuan adegan, alur aksi, serta fungsi gambar dan audio reference.
- `retention_analysis`: jelaskan detail `<Picture 1>` yang harus dipertahankan—identitas, pakaian, bentuk, warna, objek, komposisi, ruang, dan pencahayaan. Jelaskan juga karakteristik `<Audio 1>` yang harus dipertahankan.
- `detailed_description`: tulis timeline visual lengkap dari awal sampai akhir, termasuk komposisi, aksi, kamera, dialog, suara diegetic, dan penggunaan reference.
- `overall_soundscape`: jelaskan ambience, suara fisik, suara manusia, serta apakah `<Audio 1>` menjadi reference karakteristik atau disalin ke hasil.
- `non_diegetic_music`: jelaskan musik latar yang hanya didengar penonton, atau tulis `N/A` jika tidak ada.

## Penulisan shot

Jumlah shot mengikuti perintah khusus pengguna. Jangan mengasumsikan jumlah shot tertentu dan jangan melakukan validasi jumlah shot.

Karena Ref2VA S2V memakai `detailed_description` sebagai satu string, shot ditulis di dalam field tersebut menggunakan marker teks:

```text
[Shot 1] From 0.00 to 5.00 seconds, describe the opening composition, subject action, camera, and sound.

[Shot 2] From 5.00 to 10.00 seconds, describe the next action, camera transition, continuity, and sound.
```

Jika pengguna meminta dua shot, gunakan `[Shot 1]` dan `[Shot 2]`. Jika meminta tiga shot, gunakan `[Shot 1]`, `[Shot 2]`, dan `[Shot 3]`. Setiap shot harus menjelaskan:

- rentang waktu yang tidak tumpang tindih;
- visual dan posisi subjek;
- aksi utama;
- kamera dan transisi;
- dialog atau suara diegetic jika ada;
- kesinambungan identitas dan detail dari `<Picture 1>`;
- penggunaan atau kesinambungan karakteristik `<Audio 1>`.

Jangan membuat array JSON `shots` untuk S2V. Marker `[Shot N]` hanya digunakan di dalam teks `detailed_description`.

## Audio reference

`<Audio 1>` adalah audio yang benar-benar dipakai workflow. Jika audio hanya digunakan sebagai karakteristik, jelaskan dengan marker `reference`. Jika audio disalin seluruhnya atau sebagian, gunakan `fully_copy` atau `partially_copy` sesuai kebutuhan adegan.

## Aturan akhir

- Gunakan hanya `<Picture 1>` dan `<Audio 1>` sebagai reference media.
- Jangan memakai format T2VA atau I2VA.
- Jangan menambahkan instruksi first-frame I2VA atau object `reference` I2VA.
- Pastikan semua timing berada dalam durasi scene, maksimal 15 detik.
- Kembalikan JSON valid sesuai struktur yang diminta.
