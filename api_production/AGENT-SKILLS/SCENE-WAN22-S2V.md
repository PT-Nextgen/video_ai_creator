# Petunjuk untuk pembuatan scene dengan tipe wan22_s2v

## Pemahaman alur video
1. Baca `SCENE-GENERAL.md` 

## Flow scene
1. Buat gambar awal 
   Baca `TEXT-TO-IMAGE.md` 
   CLI untuk membuat gambar awal:
   ```powershell
   ..\.venv\Scripts\python.exe ..\scripts\generate_initial_image.py --project <nama_project> --scene <nama_scene>
   ```
2. Buat video dengan menggunakan gambar awal dan voice
   Baca `IMAGE-SOUND-TO-VIDEO.md`
   CLI untuk memproses scene dan membuat video:
   ```powershell
   ..\.venv\Scripts\python.exe ..\main.py --project <nama_project> --scene <nama_scene>
   ```
3. Tidak boleh mengubah setting apapun selain yang dijelaskan pada `TEXT-TO-IMAGE.md` dan `IMAGE-SOUND-TO-VIDEO.md`

## Panduan untuk pembuatan scene
1. Scene wan22_s2v biasanya sudah mempunyai gambar awal yang fix, jadi tidak perlu dibuat ulang, jadi perhatikan perintah yang diberikan, apakah perlu membuat gambar awal atau tidak. 
2. Gambar awal harus mempunyai wajah manusia yang jelas
3. Wajah manusia harus terlihat jelas dan dari dekat
4. Pastikan kamera untuk gambar awal menyorot wajah manusia tersebut dari dekat (medium atau close up) dan dari arah depan
5. Jadikan pedoman di atas sebagai panduan untuk pembuatan prompt gambar awal dan video

