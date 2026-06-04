# Menjelaskan proses untuk membuat image menjadi video

## Konfigurasi json 
File konfigurasi : wan22_i2v_prompt.json

## Penjelasan wan22_i2v_prompt.json

### Hal yang perlu diisi pada wan22_i2v_prompt.json
1. `positive_prompt_one`
2. `positive_prompt_two`
    Hanya perlu diisi apabila `duration_seconds` 10s
3. `negative_prompt_one`
4. `negative_prompt_two`
    Hanya perlu diisi apabila `duration_seconds` 10s
5. Text prompt diisi pada field `id_new` dan `id_old` pada field `positive_prompt_one`, `positive_prompt_two`, `negative_prompt_one` dan `negative_prompt_two` 
6. Field `id_new` dan `id_old` isinya sama dan dalam bahasa Indonesia
7. Kemudian isikan versi bahasa inggris dalam field `en`
8. Tidak boleh mengubah setting lain selain yang dijelaskan di atas

### Flow pembuatan video untuk `duration_seconds` 5s 
1. Proses untuk membuat image menjadi video ini harus mempunyai minimal satu gambar awal pertama
2. Gambar awal pertama ini digerakkan memakai `positive_prompt_one` dan `negative_prompt_one` menghasilkan video pertama dengan durasi 5s
3. Video pertama ini akan menjadi output video durasi 5s

### Flow pembuatan video untuk `duration_seconds` 10s
1. Proses untuk membuat image menjadi video ini harus mempunyai minimal satu gambar awal pertama
2. Gambar awal pertama ini digerakkan memakai `positive_prompt_one` dan `negative_prompt_one` menghasilkan video pertama dengan durasi 5s
3. Gambar awal kedua ini digerakkan memakai `positive_prompt_two` dan `negative_prompt_two` menghasilkan video kedua dengan durasi 5s
4. Video pertama dan video kedua digabungkan menjadi output video durasi 10s

## Petunjuk pembuatan prompt
Sebagai petunjuk untuk pembuatan `positive_prompt_one`, `positive_prompt_two`, `negative_prompt_one` dan `negative_prompt_two` silahkan baca `VIDEO-PROMPT.md` 