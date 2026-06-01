# Menjelaskan proses untuk membuat text menjadi image

## Konfigurasi json
File konfigurasi : z_image_prompt.json

## Penjelasan z_image_prompt.json

### Hal yang wajib diisi pada z_image_prompt.json
1. `positive_prompt`
2. `negative_prompt`
3. Text prompt diisi pada field `id_new` pada field `positive_prompt` dan `negative_prompt`

### Flow pembuatan image 
1. Gambar dibuat dengan menggunakan `positive_prompt` dan `negative_prompt`

### Petunjuk pembuatan prompt
Sebagai petunjuk untuk pembuatan `positive_prompt` dan `negative_prompt` silahkan baca `IMAGE-PROMPT.md`
