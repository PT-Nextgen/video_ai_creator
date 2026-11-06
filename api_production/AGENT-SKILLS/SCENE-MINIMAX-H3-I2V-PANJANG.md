# Scene minimax-h3_i2v-panjang

Dokumen ini mengatur scene MiniMax H3 I2V berantai dengan maksimal empat stage. Setiap stage aktif wajib memiliki image referensi awal dan image referensi akhir.

## Aturan scene

- Scene memakai workflow MiniMax H3 I2VA pada setiap stage.
- `continuations` bernilai `0` sampai `3`; jumlah stage aktif adalah `continuations + 1`.
- `run_start_stage` menentukan stage pertama yang dijalankan pada partial run.
- Setiap stage aktif wajib memilih `first` dan `last` pada `stage_references`.
- Referensi dapat berupa image lokal (`source: "scene"`) atau frame terakhir stage sebelumnya (`source: "stage_last"`).
- Nilai `source: "none"` atau referensi kosong tidak valid untuk stage aktif.
- Untuk stage 1, `stage_last` tidak valid karena belum ada stage sebelumnya.
- Frame pertama dan terakhir dikirim ke ComfyUI dalam urutan tersebut.
- Prompt setiap stage harus mendeskripsikan transisi kontinu dari first frame menuju last frame dan mengikuti schema I2VA MiniMax H3 dengan instruksi first/last frame.
- FPS workflow ditetapkan `24`; durasi scene menerima angka `0.0` sampai `15.0` detik dengan maksimal 4 angka desimal.

## Struktur prompt

File `minimax_h3_i2v_panjang_prompt.json` tetap menggunakan struktur root yang ada:

```json
{
  "continuations": 1,
  "run_start_stage": 1,
  "prompts": [
    {"id_old": {}, "id_new": {}, "en": {}},
    {"id_old": {}, "id_new": {}, "en": {}},
    {"id_old": {}, "id_new": {}, "en": {}},
    {"id_old": {}, "id_new": {}, "en": {}}
  ],
  "stage_references": [
    {
      "first": {"source": "scene", "name": "awal.png"},
      "last": {"source": "scene", "name": "akhir.png"}
    },
    {
      "first": {"source": "stage_last", "stage": 1, "name": ""},
      "last": {"source": "scene", "name": "akhir-2.png"}
    },
    {
      "first": {"source": "stage_last", "stage": 2, "name": ""},
      "last": {"source": "scene", "name": "akhir-3.png"}
    },
    {
      "first": {"source": "stage_last", "stage": 3, "name": ""},
      "last": {"source": "scene", "name": "akhir-4.png"}
    }
  ]
}
```

`prompts` selalu berisi empat item. `stage_references` juga berisi empat konfigurasi; validasi hanya memblokir stage aktif yang belum memiliki first frame atau last frame yang valid. Frame dari stage sebelumnya boleh dipakai sebagai `stage_last` untuk first maupun last.

## Checklist

- File JSON tersedia dan valid.
- Setiap prompt stage aktif memiliki `id_old`, `id_new`, dan `en` dengan schema I2VA yang valid.
- Setiap stage aktif memiliki first frame dan last frame yang dipilih.
- Referensi lokal benar-benar ada di folder scene.
- Referensi `stage_last` menunjuk stage sebelumnya yang valid.
- Tidak ada stage aktif dengan `source: "none"`.
- Tidak ada `negative_prompt` pada prompt MiniMax H3.
