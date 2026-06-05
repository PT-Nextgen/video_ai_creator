# Petunjuk untuk pembuatan scene dengan tipe image_zoom

## Pemahaman alur video
1. Baca `SCENE-GENERAL.md`

## Flow scene
1. Buat gambar awal
   Baca `TEXT-TO-IMAGE.md`
   CLI untuk membuat gambar awal:
   ```powershell
   ..\.venv\Scripts\python.exe ..\scripts\generate_initial_image.py --project <nama_project> --scene <nama_scene>
   ```
2. Buat video dengan menggunakan teknik image zomm
   CLI untuk memproses scene dan membuat video:
   ```powershell
   ..\.venv\Scripts\python.exe ..\main.py --project <nama_project> --scene <nama_scene>
   ```
3. Tidak boleh mengubah setting apapun selain yang dijelaskan pada `TEXT-TO-IMAGE.md`

## Panduan untuk pembuatan scene

1. Scene image-zoom adalah menggerakkan gambar awal dengan cara mendekat atau menjauh secara pelan sehingga fokus penonton terasa masuk ke dalam gambar
2. Gerakan bisa zoom in untuk memberi kesan mendekat ke objek utama, dan bisa juga zoom out untuk memberi kesan membuka tampilan gambar yang lebih luas
