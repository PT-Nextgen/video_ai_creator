# Pembuatan video dengan menggunakan Agent AI

## Penjelasan umum
1. Agent digunakan untuk membuat variasi prompt 
2. Prompt yang divariasikan adalah prompt untuk gambar awal dan prompt untuk pembuatan video
3. Agent akan diberikan perintah spesifik untuk memulai variasi ini

## Alur agent bekerja
1. Agent tidak bekerja dari nol
2. Project pembuatan video sudah dibuatkan terlebih dahulu dengan konfigurasi lengkap
3. Agent membuat variasi prompt untuk setiap scene sesuai dengan perintah yang diberikan
4. Agent tidak boleh pakai script untuk generate dan membuat variasi scene, gunakan cara agentic 
5. Hasil image atau video tidak perlu direname atau digandakan karena akan membuat banyak file-file duplikasi dalam folder scene

## Isi perintah ke Agent
1. Agent akan diberitahu project apa saja yang harus diproses
2. Agent akan diberitahu berapa variasi yang dibutuhkan untuk setiap scene pada setiap project
3. Agent akan diberikan panduan khusus per project
4. Agent akan diberikan panduan khusus per scene per project

## Referensi panduan untuk agent (lakukan secara berurutan)
1. Lihat isi folder `AGENT-SKILLS`
2. Baca `SCENE-GENERAL.md`
3. Baca `SCENE-WAN22-I2V.md`, `SCENE-WAN22-S2V.md`, `SCENE-I2V.md`, `SCENE-IMAGE-PAN.md` dan `SCENE-IMAGE-ZOOM.md` dan baca juga file .md referensi pada setiap file tersebut
4. Pahami semua file panduan (file .md) yang diberikan
5. Jangan membuat eksekusi yang tidak sesuai dengan panduan (file .md) yang diberikan

## Proses teknis per project 
1. Proses setiap scene per project secara berurutan
2. Proses setiap scene mulai dari pembuatan gambar sampai video akhir
3. Setelah selesai kopikan semua isi folder scene ke dalam direktori variasi<nomor_variasi> di dalam folder scene, buat foldernya apabila belum ada
4. `nomor_variasi` harus berurutan 
5. Hapus file .mp4 dan .png dalam folder root scene
6. Ulang lagi proses scene sesuai dengan jumlah variasi yang diberikan
7. Apabila satu scene sudah selesai semua variasinya, maka lanjutkan ke scene berikutnya
8. Apabila satu project sudah selesai semua scenenya divariasikan, maka lanjutkan ke project berikut

## Larangan untuk Agent
1. Agent dilarang untuk menganalisa source code python, karena akan menghabiskan token dan akan memperlama proses pengerjaan
2. Untuk membuat gambar dan membuat video, gunakan CLI yang sudah dijelaskan pada panduan 

