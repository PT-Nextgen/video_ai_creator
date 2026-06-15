# Petunjuk pembuatan text menjadi image

## Konfigurasi json
File konfigurasi : `z_image_prompt.json`

## Penjelasan z_image_prompt.json

### Hal yang perlu diisi pada z_image_prompt.json
1. `positive_prompt`
2. `negative_prompt`
3. Text prompt diisi pada field `id_new` dan `id_old` pada field `positive_prompt` dan `negative_prompt`
4. Field `id_new` dan `id_old` isinya sama dan dalam bahasa Indonesia
5. Kemudian isikan versi bahasa inggris dalam field `en`
6. Tidak boleh mengubah setting lain selain yang dijelaskan di atas

### Flow pembuatan image 
1. Gambar dibuat dengan menggunakan `positive_prompt` dan `negative_prompt`

### Petunjuk pembuatan prompt
Sebagai petunjuk untuk pembuatan `positive_prompt` dan `negative_prompt` silahkan baca `Petunjuk pembuatan prompt untuk membuat text menjadi image`
