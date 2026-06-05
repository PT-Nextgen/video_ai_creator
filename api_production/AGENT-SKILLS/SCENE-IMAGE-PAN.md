# Petunjuk untuk pembuatan scene dengan tipe image_pan

## Pemahaman alur video
1. Baca `SCENE-GENERAL.md`

## Flow scene
1. Buat gambar awal
   Baca `TEXT-TO-IMAGE.md`
   CLI untuk membuat gambar awal:
   ```powershell
   ..\.venv\Scripts\python.exe ..\scripts\generate_initial_image.py --project <nama_project> --scene <nama_scene>
   ```
2. Buat video dengan menggunakan teknik image pan
   CLI untuk memproses scene dan membuat video:
   ```powershell
   ..\.venv\Scripts\python.exe ..\main.py --project <nama_project> --scene <nama_scene>
   ```
3. Tidak boleh mengubah setting apapun selain yang dijelaskan pada `TEXT-TO-IMAGE.md`

## Panduan untuk pembuatan scene

1. Scene image-pan adalah menggerakkan gambar awal dengan gerakan kamera yang pelan menyapu atau bergeser di dalam gambar tersebut
2. Gerakan bisa dari kiri dan bisa juga dari kanan