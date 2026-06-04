# Menjelaskan proses untuk membuat image dan sound menjadi video

## Konfigurasi json 
File konfigurasi : wan22_s2v_prompt.json

## Penjelasan wan22_s2v_prompt.json

### Hal yang perlu diisi pada wan22_s2v_prompt.json
1. `positive_prompt`
2. `negative_prompt`
3. Text prompt diisi pada field `id_new` dan `id_old` pada field `positive_prompt` dan `negative_prompt` 
4. Field `id_new` dan `id_old` isinya sama dan dalam bahasa Indonesia
5. Kemudian isikan versi bahasa inggris dalam field `en`
6. Tidak boleh mengubah setting lain selain yang dijelaskan di atas

### Flow pembuatan video 
1. Proses ini harus mempunyai minimal satu gambar awal yang berisi wajah manusia dan satu voice berupa file mp3
2. Gambar awal digerakkan memakai `positive_prompt` dan `negative_prompt` menghasilkan video
3. Wajah manusia pada gambar awal akan terlihat berbicara pada video sesuai dengan voice file yang diberikan

## Petunjuk pembuatan prompt
Sebagai petunjuk untuk pembuatan `positive_prompt` dan `negative_prompt` silahkan baca `VIDEO-PROMPT.md` 