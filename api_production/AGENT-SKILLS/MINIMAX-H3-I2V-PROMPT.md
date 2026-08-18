---
name: minimax-h3-i2v-prompt
description: Menulis prompt MiniMax H3 I2VA dengan satu gambar sebagai first frame.
---

# MiniMax H3 I2VA Prompt

Gunakan mode `I2VA`. Prompt harus dimulai persis dengan satu baris berikut, lalu satu baris kosong:

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.
```

`<Picture 1>` adalah gambar referensi aktual dan merupakan kondisi visual persis pada frame pertama. `[Shot 1]` adalah shot timeline tempat gambar tersebut berlaku.

## Struktur JSON

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
    "id_new": {},
    "en": {}
  }
}
```

`id_old`, `id_new`, dan `en` harus memiliki struktur nested yang sama. `en` berisi bahasa Inggris; `id_new` dan `id_old` berisi bahasa Indonesia. `id_old` adalah salinan `id_new`.

Field wajib pada setiap object bahasa:

- `mode`: harus `I2VA`
- `reference`: harus persis memetakan `Picture 1` ke `[Shot 1]` pada `0.0`
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

## Cara menulis prompt

1. Mulai `Shot 1` dari komposisi, subjek, identitas, pakaian, warna, objek penting, pencahayaan, dan layout yang terlihat pada `<Picture 1>`.
2. Tegaskan bahwa `<Picture 1>` adalah exact first frame pada `0.00` detik.
3. Kembangkan gerakan secara kontinu dari kondisi gambar tersebut menuju akhir video.
4. Pertahankan identitas subjek, komposisi, pakaian, objek, pencahayaan, hubungan ruang, dan gaya visual.
5. Jelaskan aksi, kamera, dialog, suara diegetic, ambience, dan musik sesuai timeline.
6. Gunakan urutan: first-frame anchor → action onset → continuous development → result/reaction.

## Struktur prompt Inggris yang dikirim ke model

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
```

Jangan memakai format T2VA, FL2VA, atau L2VA. Jangan menambahkan `negative_prompt`.
