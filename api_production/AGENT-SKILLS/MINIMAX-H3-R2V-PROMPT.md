---
name: minimax-h3-r2v-prompt
description: Menulis prompt MiniMax H3 Ref2VA/R2V dengan reference image, video, dan audio yang aktif.
---

# MiniMax H3 R2V Ref2VA Prompt

Gunakan mode `Ref2VA`. Prompt harus memakai tepat enam section berikut dalam urutan yang sama:

```text
subject_definitions: ...

summary: ...

retention_analysis: ...

detailed_description: ...

overall_soundscape: ...

non_diegetic_music: ...
```

## Struktur JSON

```json
{
  "positive_prompt": {
    "id_old": {
      "mode": "Ref2VA",
      "subject_definitions": "",
      "summary": "",
      "retention_analysis": "",
      "detailed_description": "",
      "overall_soundscape": "",
      "non_diegetic_music": ""
    },
    "id_new": {},
    "en": {}
  },
  "references": {
    "images": [],
    "audios": [],
    "video": ""
  }
}
```

`id_old`, `id_new`, dan `en` memiliki enam field Ref2VA yang sama. `en` berisi bahasa Inggris; `id_new` dan `id_old` berisi bahasa Indonesia. `id_old` adalah salinan `id_new`.

## Reference aktif

Token reference harus dibuat dari manifest aktif, dengan penomoran rapat mulai dari 1:

- image pertama → `<Picture 1>`
- image kedua → `<Picture 2>`
- video aktif → `<Video 1>`
- audio pertama → `<Audio 1>`
- audio kedua → `<Audio 2>`

Gunakan hanya token yang benar-benar tersedia. Reference yang tidak aktif harus dihapus dari prompt. Jangan mengarang, mengganti nama, atau melompati nomor token.

Token semantik berikut bukan file reference dan tetap boleh digunakan:

```text
<Subject N>, <Shot N>, <d>, </d>, dan speaker IDs
```

Contoh manifest:

```text
Picture references: <Picture 1>, <Picture 2>
Video references: none
Audio references: <Audio 1>
```

Dalam contoh tersebut, `<Video 1>`, `<Audio 2>`, dan `<Picture 3>` dilarang.

## Cara menulis enam section

- `subject_definitions`: definisikan identitas subjek dan hubungan subjek dengan token reference yang aktif.
- `summary`: ringkas adegan, tujuan aksi, dan hubungan antar-reference.
- `retention_analysis`: jelaskan detail yang harus dipertahankan dari setiap reference—identitas, pakaian, bentuk, warna, objek, ruang, dan audio penting.
- `detailed_description`: jelaskan timeline visual, aksi, kamera, transisi, dialog, dan penggunaan reference secara rinci.
- `overall_soundscape`: gabungkan ambience, suara fisik, suara manusia non-verbal, dan suara dari reference audio yang aktif.
- `non_diegetic_music`: jelaskan musik latar yang hanya didengar penonton, atau gunakan `N/A`.

## Penulisan shot

`detailed_description` tetap berupa satu string Ref2VA. Jika perintah pengguna meminta beberapa shot, tulis timeline di dalam string tersebut menggunakan marker teks, misalnya:

```text
[Shot 1] From 0.00 to 5.00 seconds, describe the first composition, action, camera, and sound.

[Shot 2] From 5.00 to 10.00 seconds, describe the next action, transition, continuity, and sound.
```

Jumlah shot mengikuti perintah pengguna dan tidak dipaksa oleh validator. Setiap shot yang ditulis harus memiliki timing yang tidak tumpang tindih, visual, aksi, kamera, suara, dan kesinambungan reference aktif. Jangan menambahkan array JSON `shots`; marker shot hanya berada di dalam `detailed_description`.

Pertahankan setiap token reference persis sama pada keenam section. Jangan menulis token yang tidak tersedia, termasuk token yang hanya muncul pada contoh dokumen referensi.
