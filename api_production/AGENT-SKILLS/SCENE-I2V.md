# Petunjuk untuk pembuatan scene dengan tipe i2v

## Pemahaman alur video
1. Baca `SCENE-GENERAL.md`

## Flow scene
1. Buat satu atau beberapa gambar
2. Apabila hanya satu gambar maka jadikan satu gambar itu menjadi video
3. Apabila beberapa gambar maka gabungkan beberapa gambar tersebut menjadi video
4. Untuk pembuatan gambar awal pertama
   Baca `TEXT-TO-IMAGE.md`

## Flow scene apabila hanya satu gambar
1. Buat gambar awal
   Baca `TEXT-TO-IMAGE.md`
   CLI untuk membuat gambar awal:
   ```powershell
   ..\.venv\Scripts\python.exe ..\scripts\generate_initial_image.py --project <nama_project> --scene <nama_scene>
   ```
2. Buat video dengan menggunakan gambar awal
   CLI untuk memproses scene dan membuat video:
   ```powershell
   ..\.venv\Scripts\python.exe ..\main.py --project <nama_project> --scene <nama_scene>
   ```

## Flow scene apabila menggunakan beberapa gambar
1. Buat gambar awal pertama
   Baca `TEXT-TO-IMAGE.md`
   CLI untuk membuat gambar awal pertama:
   ```powershell
   ..\.venv\Scripts\python.exe ..\scripts\generate_initial_image.py --project <nama_project> --scene <nama_scene>
   ```
2. Buat beberapa gambar lainnya
3. Buat video dengan menggunakan beberapa gambar
   CLI untuk memproses scene dan membuat video:
   ```powershell
   ..\.venv\Scripts\python.exe ..\main.py --project <nama_project> --scene <nama_scene>
   ```

### Panduan untuk pembuatan scene dari beberapa gambar
Ada dua tujuan scene ini apabila menggunakan beberapa gambar, pertama untuk visualisasi variasi, kedua untuk visualisasi flow atau alur

#### Tujuan visualisasi variasi
1. Gambar-gambar dibuat dengan tujuan menunjukkan variasi, misal macam-macam buah, macam-macam mobil, berbagai jenis pemandangan dan sebagainya
2. Gambar-gambar ini tidak menunjukkan alur atau flow atau proses dan biasanya berdiri sendiri
3. Gunakan `z_image_extra_prompts.json` untuk menambahkan gambar selain gambar awal pertama


#### Tambahan gambar dengan menggunakan z_image_extra_prompts.json
1. File yang dipakai adalah `z_image_extra_prompts.json`
2. File ini menyediakan total 3 slot prompt tambahan
3. Isi `positive_prompt` dan `negative_prompt` pada setiap slot pada field `id_new` dan `id_old`
4. Field `id_new` dan `id_old` isinya sama dan dalam bahasa Indonesia
5. Kemudian isikan versi bahasa inggris dalam field `en`
6. Struktur penyusunan prompt positif dan negatif tetap mengikuti aturan pada `IMAGE-PROMPT.md`
7. CLI untuk menambahkan gambar:
   ```powershell
   ..\.venv\Scripts\python.exe ..\scripts\generate_initial_image.py --project <nama_project> --scene <nama_scene> --prompt-file z_image_extra_prompts.json --prompt-index 1
   ..\.venv\Scripts\python.exe ..\scripts\generate_initial_image.py --project <nama_project> --scene <nama_scene> --prompt-file z_image_extra_prompts.json --prompt-index 2
   ..\.venv\Scripts\python.exe ..\scripts\generate_initial_image.py --project <nama_project> --scene <nama_scene> --prompt-file z_image_extra_prompts.json --prompt-index 3
   ```

#### Tujuan visualisasi flow atau alur
1. Gambar-gambar dibuat dengan tujuan menunjukkan alur atau flow, misal flow lampu lalu lintas, gambar pertama terlihat lampu merah menyala, kemudian gambar kedua lampu kuning menyala, gambar terakhir lampu hijau menyala
2. Gambar-gambar ini tidak berdiri sendiri tapi memakai gambar sebelumnya sebagai referensi
3. Gunakan `image_edit_prompt.json` untuk menambahkan gambar selain gambar awal pertama untuk mengedit gambar awal pertama menjadi gambar kedua dst, sehingga membuat flow yang lengkap


#### Tambahan gambar dengan menggunakan image_edit_prompt.json
1. File yang dipakai adalah `image_edit_prompt.json`
2. File ini dipakai untuk membuat gambar tambahan yang merupakan kelanjutan atau perubahan dari gambar sebelumnya
3. File ini menyediakan total 3 slot edit
4. Setiap slot memiliki:
   - `source_image`
   - `prompt`
5. `source_image` adalah nama file gambar input yang akan diedit
6. `prompt` adalah instruksi perubahan gambar, isikan dalam field `id_new` dan `id_old` dalam bahasa Indonesia, kemudian isikan versi bahasa inggris dalam field `en`
7. Struktur prompt edit harus ringkas, spesifik dan konsisten dengan alur scene
8. Struktur prompt edit harus fokus hanya pada bagian yang diedit saja
9. Gunakan urutan slot secara logis:
   - slot 1 mengedit gambar awal pertama menjadi gambar kedua
   - slot 2 mengedit gambar kedua menjadi gambar ketiga
   - slot 3 mengedit gambar ketiga menjadi gambar keempat
10. CLI untuk edit gambar:
   ```powershell
   ..\.venv\Scripts\python.exe ..\scripts\generate_image_edit.py --project <nama_project> --scene <nama_scene> --prompt-file image_edit_prompt.json --prompt-index 1
   ..\.venv\Scripts\python.exe ..\scripts\generate_image_edit.py --project <nama_project> --scene <nama_scene> --prompt-file image_edit_prompt.json --prompt-index 2
   ..\.venv\Scripts\python.exe ..\scripts\generate_image_edit.py --project <nama_project> --scene <nama_scene> --prompt-file image_edit_prompt.json --prompt-index 3
   ```
