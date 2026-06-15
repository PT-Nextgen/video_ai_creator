# Petunjuk pembuatan text menjadi beberapa video 

## Konfigurasi json
File konfigurasi :
1. `wan22_t2v_prompt.json`
2. `wan22_t2v_batch_extra_prompts.json`

## Penjelasan wan22_t2v_prompt.json

### Hal yang perlu diisi pada wan22_t2v_prompt.json
1. `positive_prompt`
2. `negative_prompt`
3. Text prompt diisi pada field `id_new` dan `id_old` pada field `positive_prompt` dan `negative_prompt`
4. Field `id_new` dan `id_old` isinya sama dan dalam bahasa Indonesia
5. Kemudian isikan versi bahasa inggris dalam field `en`
6. Tidak boleh mengubah setting lain selain yang dijelaskan di atas

## Penjelasan wan22_t2v_batch_extra_prompts.json

### Hal yang perlu diisi pada wan22_t2v_batch_extra_prompts.json
1. File ini menyediakan total 3 slot prompt tambahan
2. Setiap slot mempunyai `positive_prompt` dan `negative_prompt`
3. Text prompt diisi pada field `id_new` dan `id_old` pada field `positive_prompt` dan `negative_prompt`
4. Field `id_new` dan `id_old` isinya sama dan dalam bahasa Indonesia
5. Kemudian isikan versi bahasa inggris dalam field `en`
6. Tidak boleh mengubah setting lain selain yang dijelaskan di atas

## Flow pembuatan video

### Membuat video pertama
1. Proses ini tidak membutuhkan gambar awal
2. Text prompt pada `wan22_t2v_prompt.json` dipakai untuk membuat video pertama memakai `positive_prompt` dan `negative_prompt`

### Membuat video tambahan
1. Apabila diminta untuk membuat lebih dari satu video maka isi `wan22_t2v_batch_extra_prompts.json`
2. Terdapat maksimal 3 video tambahan dengan konfigurasi 3 slot pasangan `positive_prompt` dan `negative_prompt`
3. Text `positive_prompt` dan `negative_prompt` pada setiap slot dipakai untuk membuat video 
4. Video pertama dan video tambahan digabungkan menjadi hasil video scene

## Aturan jumlah video
1. Apabila diminta membuat satu video saja, maka cukup isi `wan22_t2v_prompt.json`
2. Apabila diminta membuat dua video, maka isi `wan22_t2v_prompt.json` dan satu slot tambahan di `wan22_t2v_batch_extra_prompts.json`
3. Apabila diminta membuat tiga video, maka isi `wan22_t2v_prompt.json` dan dua slot tambahan di `wan22_t2v_batch_extra_prompts.json`
4. Apabila diminta membuat empat video, maka isi `wan22_t2v_prompt.json` dan dua tiga tambahan di `wan22_t2v_batch_extra_prompts.json`

## Petunjuk pembuatan prompt
1. Sebagai petunjuk untuk pembuatan `positive_prompt`, `negative_prompt` silahkan baca `Petunjuk pembuatan prompt untuk membuat text menjadi video`