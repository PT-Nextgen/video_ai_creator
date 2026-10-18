---
name: scene-wan22-t2v
description: Create WAN22 text-to-video scenes with one T2V workflow.
---

# Scene wan22_t2v

Scene ini membuat video langsung dari prompt teks menggunakan satu workflow WAN T2V. Scene tidak memerlukan gambar awal atau prompt tahap tambahan.

## File output Agentic

Agentic menghasilkan:

- `wan22_t2v_prompt.json`

File tersebut berisi prompt positif, prompt negatif, ukuran, dan empat konfigurasi LoRA. Prompt memakai format bilingual `id_old`, `id_new`, dan `en`.

## Aturan scene

- Durasi yang didukung adalah `5`, `10`, atau `15` detik.
- Durasi diterapkan langsung pada panjang workflow T2V.
- Scene tidak membutuhkan file gambar sebagai input.
- Workflow memakai template WAN T2V empat langkah dengan LoRA.

## Checklist

- `scene_meta.json` memiliki `scene_type: "wan22_t2v"`.
- `wan22_t2v_prompt.json` tersedia.
- `positive_prompt` tidak kosong.
- Durasi scene adalah `5`, `10`, atau `15` detik.
