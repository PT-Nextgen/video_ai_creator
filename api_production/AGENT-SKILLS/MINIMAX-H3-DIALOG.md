# MiniMax H3 Dialogue Rules

Aturan ini berlaku untuk semua mode MiniMax H3: T2VA, I2VA, dan Ref2VA S2V/R2V.

## Speaker ID

Setiap sumber suara manusia yang benar-benar berbicara atau bernyanyi harus memiliki speaker ID stabil:

```text
(S1), (S2), (S3)
```

Tetapkan ID berdasarkan urutan kemunculan sumber suara dalam video. Gunakan ID yang sama setiap kali karakter atau sumber suara tersebut berbicara di shot berikutnya. Karakter yang tidak pernah menghasilkan suara tidak perlu diberi speaker ID.

Jika karakter berasal dari reference, gabungkan subject reference dan speaker ID:

```text
<Subject 1> (S1), the presenter shown in <Picture 1>, speaks in a calm male voice.
```

Jika sumber suara tidak memiliki subject reference, jelaskan identitas suaranya sebelum speaker ID:

```text
The off-screen female narrator with a warm, measured voice (S1) speaks.
```

## Dialog aktual

Dialog atau lirik aktual harus ditulis di dalam `<d>` dan diawali language tag. Pertahankan kata dan tanda baca dialog sesuai permintaan pengguna; jangan menerjemahkan atau memparafrasekan isi dialog.

```text
The presenter (S1) looks into the camera and says:
<d>[Indonesian] Selamat datang di acara kami.</d>
```

Gunakan bahasa asli dialog, misalnya `[Indonesian]`, `[English]`, atau `[Japanese]`. `<d>` hanya berisi ucapan atau lirik aktual, bukan deskripsi aksi, emosi, kamera, atau suara latar.

## Beberapa pembicara

Gunakan ID berbeda untuk pembicara berbeda dan pertahankan ID tersebut sepanjang video:

```text
[Shot 1] The woman (S1) asks:
<d>[Indonesian] Kamu sudah siap?</d>

[Shot 2] At 00:04.000, the man (S2) turns toward her and replies:
<d>[Indonesian] Saya sudah siap.</d>
```

Jika beberapa speaker berbicara bersamaan, gunakan ID gabungan `(S1,S2)`.

## Dialog dari audio reference

Jika `<Audio N>` hanya menjadi reference timbre, ritme, emosi, atau cara bicara, jangan menyalin isi dialog audio. Jelaskan bahwa speaker mengikuti karakteristik suara reference:

```text
<Subject 1> (S1) speaks with the vocal timbre and measured delivery referenced from <Audio 1>:
<d>[English] We should leave now.</d>
```

Jika dialog dari audio reference memang diminta untuk disalin atau digunakan kembali, pertahankan kata-kata asli dan bahasa aslinya di dalam `<d>`.

## Voice-over

Untuk suara dari luar layar, gunakan frasa `says in an off-screen voiceover`. Setelah blok `<d>`, jelaskan bahwa bibir karakter yang terlihat tetap tertutup:

```text
The man (S1) says in an off-screen voiceover:
<d>[Indonesian] Saya masih mengingat tempat itu.</d>
while his lips remain completely closed.
```

## Dialog melewati pergantian shot

Jika dialog yang sama berlanjut melewati cut, gunakan `<scenetrans>` pada titik sambungan dan jelaskan bahwa audio berlanjut tanpa terputus. Gunakan `<cutoff>` jika ucapan terpotong karena video berakhir. Jangan membuat speaker ID baru hanya karena terjadi pergantian shot.

## Penempatan berdasarkan mode

- T2VA/I2VA: tulis dialog pada field `dialogue` setiap object `shots`.
- S2V/R2V Ref2VA: tulis dialog di dalam `detailed_description`, pada shot dan urutan waktu yang sesuai.
- Jangan menulis dialog lengkap di `overall_soundscape` atau `non_diegetic_music`.
