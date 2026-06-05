# Petunjuk untuk pembuatan scene dengan tipe wan22_i2v

## Pemahaman alur video
1. Baca `SCENE-GENERAL.md`

## Flow scene
1. Buat gambar awal
   Baca `TEXT-TO-IMAGE.md`
   CLI untuk membuat gambar awal:
   ```powershell
   ..\.venv\Scripts\python.exe ..\scripts\generate_initial_image.py --project <nama_project> --scene <nama_scene>
   ```
2. Buat video dengan menggunakan gambar awal 
   Baca `IMAGE-TO-VIDEO.md`
   CLI untuk memproses scene dan membuat video:
   ```powershell
   ..\.venv\Scripts\python.exe ..\main.py --project <nama_project> --scene <nama_scene>
   ```
3. Tidak boleh mengubah setting apapun selain yang dijelaskan pada `TEXT-TO-IMAGE.md` dan `IMAGE-TO-VIDEO.md`

## Panduan untuk pembuatan scene
1. Scene ini tidak untuk membuat konsep teknis dengan nilai benar dan salah yang jelas
2. Contoh konsep teknis misal gambar teknis yang ada nilai benar atau salahnya, gambar yang berhubungan dengan scientific dan sejenisnya 
3. Contoh konsep teknis lain misal pembuatan video dengan gerakan yang ada nilai benar salah, misal pergerakan bumi mengitari matahari, proses ulat menjadi kupu-kupu dan sejenisnya 
4. Scene ini tidak untuk membuat gambar atau video dengan screen rumit, misal split screen dan sejenisnya
5. Scene ini tidak untuk membuat gambar atau video pakai text, karena akurasi text sangat rendah
6. Jadikan pedoman di atas sebagai panduan untuk pembuatan prompt gambar awal dan video


