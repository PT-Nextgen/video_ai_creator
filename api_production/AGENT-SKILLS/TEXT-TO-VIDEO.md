# Menjelaskan proses untuk membuat text menjadi video

## Konfigurasi json
File konfigurasi :
1. `wan22_t2v_prompt.json`
2. `wan22_i2v_prompt.json`

## Penjelasan wan22_t2v_prompt.json

### Hal yang perlu diisi pada wan22_t2v_prompt.json
1. `positive_prompt`
2. `negative_prompt`
3. Text prompt diisi pada field `id_new` dan `id_old` pada field `positive_prompt` dan `negative_prompt`
4. Field `id_new` dan `id_old` isinya sama dan dalam bahasa Indonesia
5. Kemudian isikan versi bahasa inggris dalam field `en`
6. Tidak boleh mengubah setting lain selain yang dijelaskan di atas

## Penjelasan wan22_i2v_prompt.json

### Hal yang perlu diisi pada wan22_i2v_prompt.json
1. `positive_prompt_one`
2. `positive_prompt_two`
    Hanya perlu diisi apabila `duration_seconds` scene 15s
3. `negative_prompt_one`
4. `negative_prompt_two`
    Hanya perlu diisi apabila `duration_seconds` scene 15s
5. Text prompt diisi pada field `id_new` dan `id_old` pada field `positive_prompt_one`, `positive_prompt_two`, `negative_prompt_one` dan `negative_prompt_two`
6. Field `id_new` dan `id_old` isinya sama dan dalam bahasa Indonesia
7. Kemudian isikan versi bahasa inggris dalam field `en`
8. Tidak boleh mengubah setting lain selain yang dijelaskan di atas

## Flow pembuatan video

### Flow pembuatan video untuk `duration_seconds` 5s
1. Proses ini tidak membutuhkan gambar awal
2. Text prompt pada `wan22_t2v_prompt.json` dipakai untuk membuat video tahap pertama memakai `positive_prompt` dan `negative_prompt`
3. Video hasil tahap pertama ini menjadi output video durasi 5s

### Flow pembuatan video untuk `duration_seconds` 10s
1. Proses ini tidak membutuhkan gambar awal
2. Text prompt pada `wan22_t2v_prompt.json` dipakai untuk membuat video tahap pertama memakai `positive_prompt` dan `negative_prompt` menghasilkan video pertama dengan durasi 5s
3. Frame terakhir dari video pertama dipakai sebagai gambar awal otomatis untuk tahap kedua
4. Gambar awal otomatis dari frame terakhir ini digerakkan memakai `positive_prompt_one` dan `negative_prompt_one` dari `wan22_i2v_prompt.json`
5. Hasil tahap kedua menghasilkan video kedua dengan durasi 5s
6. Video pertama dan video kedua digabungkan menjadi output video durasi 10s

### Flow pembuatan video untuk `duration_seconds` 15s
1. Proses ini tidak membutuhkan gambar awal
2. Text prompt pada `wan22_t2v_prompt.json` dipakai untuk membuat video tahap pertama memakai `positive_prompt` dan `negative_prompt` menghasilkan video pertama dengan durasi 5s
3. Frame terakhir dari video pertama akan menjadi gambar awal pertama
4. Gambar awal pertama ini digerakkan memakai `positive_prompt_one` dan `negative_prompt_one` menghasilkan video kedua dengan durasi 5s
5. Frame terakhir dari video kedua akan menjadi gambar awal kedua
5. Gambar awal kedua digerakkan memakai `positive_prompt_two` dan `negative_prompt_two` menghasilkan video ketiga dengan durasi 5s
6. Video pertama, video kedua dan video ketiga digabungkan menjadi video dengan durasi 15s

## Petunjuk pembuatan prompt
1. Sebagai petunjuk untuk pembuatan `positive_prompt`, `negative_prompt` silahkan baca `TEXT-TO-VIDEO-PROMPT.md`
2. Sebagai petunjuk untuk pembuatan `positive_prompt_one`, `positive_prompt_two`, `negative_prompt_one` dan `negative_prompt_two` silahkan baca `IMAGE-TO-VIDEO-PROMPT.md`
