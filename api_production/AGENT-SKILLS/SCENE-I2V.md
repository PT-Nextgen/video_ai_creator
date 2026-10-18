## Flow scene
1. Buat satu atau beberapa gambar
2. Apabila hanya satu gambar maka jadikan satu gambar itu menjadi video
3. Apabila beberapa gambar maka gabungkan beberapa gambar tersebut menjadi video
4. Untuk pembuatan gambar awal pertama
   Baca `Petunjuk pembuatan text menjadi image`

## Flow scene apabila hanya satu gambar
1. Buat gambar awal
   Baca `Petunjuk pembuatan text menjadi image`
2. Buat video dengan menggunakan gambar awal

## Flow scene apabila menggunakan beberapa gambar
1. Buat gambar awal pertama
   Baca `Petunjuk pembuatan text menjadi image`
2. Buat beberapa gambar lainnya
3. Buat video dengan menggunakan beberapa gambar

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
6. Struktur penyusunan prompt positif dan negatif tetap mengikuti aturan pada `Petunjuk pembuatan prompt untuk membuat text menjadi image`

## Aturan jumlah image
1. Apabila diminta membuat satu image saja, maka cukup isi `z_image_prompt.json`
2. Apabila diminta membuat dua image, maka isi `z_image_prompt.json` dan satu slot tambahan di `z_image_extra_prompts.json`
3. Apabila diminta membuat tiga image, maka isi `z_image_prompt.json` dan dua slot tambahan di `z_image_extra_prompts.json`
4. Apabila diminta membuat empat image, maka isi `z_image_prompt.json` dan tiga slot tambahan di `z_image_extra_prompts.json`
