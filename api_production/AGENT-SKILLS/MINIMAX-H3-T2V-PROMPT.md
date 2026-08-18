---
name: minimax-h3-t2v-prompt
description: Menulis prompt MiniMax H3 T2VA berbasis teks tanpa image alignment reference.
---

# MiniMax H3 T2VA Prompt

Gunakan mode `T2VA`. Prompt tidak boleh memiliki instruksi alignment gambar dan tidak boleh memiliki field `reference`.

## Struktur JSON

```json
{
  "positive_prompt": {
    "id_old": {
      "mode": "T2VA",
      "shots": [],
      "overall_soundscape": "",
      "non_diegetic_music": ""
    },
    "id_new": {},
    "en": {}
  }
}
```

`id_old`, `id_new`, dan `en` harus memiliki struktur nested yang sama. `en` berisi bahasa Inggris; `id_new` dan `id_old` berisi bahasa Indonesia. `id_old` adalah salinan `id_new`.

Field wajib pada setiap object bahasa:

- `mode`: harus `T2VA`
- `shots`: array minimal satu item
- `overall_soundscape`: string
- `non_diegetic_music`: string

Setiap item `shots` wajib memiliki:

```json
{
  "shot_id": "Shot 1",
  "start": 0.0,
  "end": 5.0,
  "visual": "...",
  "action": "...",
  "camera": "...",
  "dialogue": "...",
  "diegetic_sound": "..."
}
```

## Struktur prompt Inggris yang dikirim ke model

Prompt T2VA harus langsung dimulai dengan tiga section berikut:

```text
integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
```

## Cara menulis prompt

1. `integrated_multimodal_description` menjadi timeline audiovisual utama.
2. Untuk setiap shot, jelaskan gaya visual, komposisi, subjek, lingkungan, aksi, kamera, dialog, dan suara diegetic.
3. Gunakan `Shot 1`, `Shot 2`, dan seterusnya sebagai string.
4. `start` dan `end` harus berupa angka JSON, berurutan, tidak tumpang tindih, dan berada dalam durasi video.
5. Shot berikutnya boleh memperkenalkan cut, perubahan sudut pandang, ruang, waktu, atau informasi visual baru.
6. `overall_soundscape` merangkum ambience, suara fisik, dan suara manusia non-verbal sepanjang video.
7. `non_diegetic_music` menjelaskan musik yang hanya didengar penonton; gunakan `N/A` bila tidak ada.

Jangan menambahkan `reference`, `negative_prompt`, atau instruksi first-frame/image alignment ke prompt T2VA.
