# Runtime Service Switch API

Dokumen ini adalah kontrak implementasi untuk AI Agent server yang mengelola dua service secara eksklusif:

- `llama`: server llama.cpp/OpenAI-compatible.
- `comfyui`: server ComfyUI.

## Tujuan

Saat tidak ada pekerjaan image/video, hanya `llama` yang hidup. Saat workflow ComfyUI diperlukan, server harus mematikan Llama terlebih dahulu, menyalakan ComfyUI, dan menunggu health check berhasil. Setelah pekerjaan selesai, server melakukan urutan sebaliknya.

Client project menganggap perpindahan belum berhasil sampai kondisi proses dan health endpoint sama-sama terverifikasi.

## Konfigurasi client

Project membaca API key dari file lokal yang tidak masuk git:

```text
switch-key.cfg
```

Isi file dapat berupa satu baris langsung atau format:

```text
api_key=secret-value
```

Nama variable dan URL controller dikonfigurasi di `server_config.json`:

```json
{
  "runtime_controller": {
    "url": "http://nextgenserver:9000",
    "api_key_env": "VIDEO_RUNTIME_API_KEY"
  }
}
```

Client memakai `switch-key.cfg` sebagai sumber utama. `api_key_env` hanya fallback kompatibilitas. API key tidak boleh dikembalikan dalam response, ditulis ke log, atau disimpan di workflow/project JSON.

## Authentication

Semua endpoint harus menerima:

```http
Authorization: Bearer <api-key>
Accept: application/json
Content-Type: application/json
```

Request tanpa key atau dengan key invalid harus menghasilkan `401`. Key valid tetapi tidak berwenang menghasilkan `403`.

## Endpoint status

```http
GET /v1/runtime/status
```

Response minimum:

```json
{
  "active": "llama",
  "transition": null,
  "services": {
    "llama": {
      "desired": "running",
      "process_state": "running",
      "pid": 1234,
      "health": true,
      "health_url": "http://nextgenserver:8080/v1/models"
    },
    "comfyui": {
      "desired": "stopped",
      "process_state": "stopped",
      "pid": null,
      "health": false,
      "health_url": "http://nextgenserver:8188/system_stats"
    }
  }
}
```

Nilai `active` hanya boleh `llama`, `comfyui`, atau `none`. Saat transisi berlangsung, gunakan `active: "none"` dan isi `transition`.

## Endpoint switch

```http
POST /v1/runtime/switch
```

Request:

```json
{
  "target": "comfyui",
  "reason": "main.py project=contoh",
  "wait_ready": false
}
```

`target` wajib salah satu dari `llama` atau `comfyui`. `reason` hanya untuk audit log dan tidak boleh berisi API key.

Response saat transisi selesai:

```json
{
  "ok": true,
  "active": "comfyui",
  "transition_id": "tr_abc123",
  "verified": {
    "llama_stopped": true,
    "comfyui_running": true,
    "comfyui_healthy": true
  }
}
```

Walaupun `wait_ready` bernilai `false`, endpoint tetap harus menunggu sampai target siap dan service lain benar-benar mati sebelum mengembalikan `200`.

Jika timeout, proses gagal dimatikan, atau health check target gagal, kembalikan `409` atau `504` dengan format:

```json
{
  "ok": false,
  "error": {
    "code": "TARGET_HEALTH_TIMEOUT",
    "message": "ComfyUI belum sehat setelah 600 detik",
    "transition_id": "tr_abc123",
    "active": "none"
  }
}
```

Jangan mengembalikan `ok: true` bila proses lama masih hidup.

## Urutan switch wajib

### Ke ComfyUI

1. Ambil distributed lock.
2. Tandai state `transitioning_to_comfyui`.
3. Hentikan Llama dengan graceful shutdown.
4. Tunggu process Llama keluar dan PID tidak lagi aktif.
5. Verifikasi endpoint Llama gagal diakses atau service state `stopped`.
6. Nyalakan ComfyUI.
7. Tunggu PID ComfyUI tersedia.
8. Poll `GET http://<comfyui-host>:8188/system_stats` sampai HTTP `200` dan JSON valid.
9. Baru ubah state menjadi `active: comfyui`.
10. Lepaskan lock dan response `200`.

### Ke Llama

1. Ambil distributed lock.
2. Tandai state `transitioning_to_llama`.
3. Hentikan ComfyUI dan tunggu process benar-benar keluar.
4. Verifikasi `/system_stats` tidak lagi sehat.
5. Nyalakan Llama.
6. Tunggu PID Llama tersedia.
7. Poll `GET http://<llama-host>:8080/v1/models` sampai HTTP `200` dan JSON valid.
8. Pastikan model `qwen3.6-35b-a3b-uc-q4_k_m` terlihat pada response model jika model tersebut dikonfigurasi sebagai default.
9. Baru ubah state menjadi `active: llama`.
10. Lepaskan lock dan response `200`.

## Health check

Health check harus benar-benar memeriksa service, bukan hanya keberadaan PID.

Llama:

```http
GET /v1/models
```

ComfyUI:

```http
GET /system_stats
```

Health check harus memiliki timeout koneksi, interval polling, dan batas waktu total. Nilai yang digunakan client saat ini adalah interval 2 detik dan timeout health 600 detik.

## Lock dan konkurensi

Controller harus menolak atau mengantrikan request switch kedua selama transisi pertama berlangsung. Jangan mematikan service aktif karena request kedua datang ketika job masih berjalan.

Tambahkan lease/lock dengan:

- `transition_id`;
- pemilik request;
- waktu mulai dan expiry;
- status job aktif.

Jika ada job ComfyUI aktif, request switch ke Llama harus menunggu job selesai atau menghasilkan `409 JOB_IN_PROGRESS`.

## Startup dan recovery

Saat controller server mulai:

1. Pulihkan state berdasarkan PID aktual, bukan state file saja.
2. Jika kedua service hidup, matikan ComfyUI dan pertahankan Llama sebagai default, kecuali ada lease job ComfyUI yang valid.
3. Jika tidak ada service hidup, nyalakan Llama.
4. Jangan menyatakan startup selesai sebelum Llama sehat.

Jika proses target crash setelah switch:

- catat error dan `transition_id`;
- jangan menyalakan dua service sekaligus;
- kembalikan ke Llama bila memungkinkan;
- expose state `degraded` bila recovery gagal.

## Idempotensi

`POST /v1/runtime/switch` harus idempotent:

- target sudah aktif dan service lain mati: kembalikan `200` tanpa restart;
- target sedang dalam transisi yang sama: tunggu atau kembalikan status transisi;
- target berbeda sedang berjalan: kembalikan `409`.

## Logging dan keamanan

Log minimal yang perlu disimpan:

- timestamp;
- target service;
- reason;
- transition id;
- PID sebelum dan sesudah;
- durasi stop/start/health check;
- hasil akhir.

Jangan log API key, header Authorization, token proses, atau isi prompt pengguna.

## Acceptance test

Implementasi server dianggap selesai bila semua skenario berikut lulus:

1. Startup tanpa service: hanya Llama hidup dan `/v1/models` sehat.
2. Switch ke ComfyUI: Llama PID sudah mati sebelum ComfyUI dinyalakan.
3. Switch ke Llama: ComfyUI PID sudah mati sebelum Llama dinyalakan.
4. Health endpoint target belum siap: API tidak mengembalikan sukses.
5. Switch dua kali bersamaan: tidak terjadi dua service hidup bersamaan.
6. Proses target crash saat startup: status menjadi error/degraded dan recovery dijalankan.
7. API key salah: response `401` tanpa membocorkan detail rahasia.
8. Request switch ke target yang sudah aktif: idempotent dan tidak restart.
9. Model default yang terlihat pada Llama adalah `qwen3.6-35b-a3b-uc-q4_k_m`.
