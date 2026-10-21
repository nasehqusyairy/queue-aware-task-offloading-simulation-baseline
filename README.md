[![License: GPL v3](https://img.shields.io/badge/Upstream-PureEdgeSim%20GPLv3-blue.svg)](simulator/PureEdgeSim/LICENSE)

# Queue-Aware Task Offloading — baseline experiment

Project penelitian ini membungkus PureEdgeSim untuk menjalankan baseline teknis bawaan Trade-Off dan Round Robin. **Ini belum reproduksi paper** dan belum mengimplementasikan Queue-Aware, GNN, atau DQN.

## Mulai cepat

Perlu Java dan Maven (sudah terpasang di lingkungan yang diperiksa), Python 3.11+, Git, serta koneksi internet hanya saat pertama mengambil source/dependensi Maven. Dari direktori ini:

```bash
./run.sh --help
./run.sh --method trade-off --devices 10
./run.sh --method round-robin --devices 10
./run.sh --all-baselines --devices 10
```

Catatan: opsi `--all-baselines` belum diterima di versi awal; gunakan `--method all` untuk menjalankan keduanya. Durasi default 10 menit simulasi, dapat diubah `--duration-minutes`. Eksperimen default membatasi satu arsitektur `EDGE_AND_CLOUD` supaya baseline cepat dan jumlah skenario eksplisit.

Run masuk ke `results/runs/<UTC-id>/` (tiap run terpisah). Metrik terproses: `results/processed/summary.csv` dan `.json`. Dashboard statis lokal: buka `results/dashboard.html` dengan browser (`xdg-open results/dashboard.html`) atau buka file dari browser. Untuk memproses ulang: `./analyze.sh --latest` atau `./analyze.sh --run results/runs/<id>`.

## Apa yang dilakukan

PureEdgeSim source berada di `simulator/PureEdgeSim` (repositori upstream terpisah); konfigurasi baseline salinan berada di `configs/baseline`. Wrapper mengkompilasi lalu menjalankan kelas runner sementara di source tree upstream, menghapusnya setelah proses, dan mengumpulkan hasil ke direktori run. Source upstream tidak dimodifikasi secara permanen.

PureEdgeSim default properties mendefinisikan `TRADE_OFF,ROUND_ROBIN`; `DefaultOrchestrator` mengimplementasikan keduanya. Perubahan konfigurasi penelitian mengatur 10/20/30 device dan satu arsitektur aktif. Pengaturan waktu PureEdgeSim bernilai **menit**, bukan detik. Simulasi di penelitian menyebut 200 detik, berbeda dari konfigurasi default; konfigurasi ini belum disamakan penuh.

## Status

- **Berhasil diverifikasi**: clone source; Maven `package` berhasil dengan Java 25; kelas algoritma Trade-Off/Round Robin ada pada `DefaultOrchestrator`.
- **Sudah diimplementasikan, belum diverifikasi end-to-end**: wrapper run, ekstraksi metrik, ekspor dan dashboard.
- **Belum tersedia**: reproduksi parameter paper lengkap, enam tujuan offloading, tiga pengulangan, GNN/DQN paper, Queue-Aware.

## Hindari klaim berlebihan

Parser tidak memalsukan metrik. Nilai yang tidak bisa diekstrak ditampilkan sebagai N/A. Dashboard bersumber dari berkas hasil setiap run. Hasil upstream dan setting yang dipakai harus diperiksa terhadap manifest; simulator tidak dijanjikan deterministik, dan seed tidak diasumsikan.

## Lisensi

PureEdgeSim merupakan GPL-3.0 (lihat lisensi upstream). Kode wrapper baru dan dokumentasi ini dipisahkan dari kode upstream; tidak ada lisensi baru yang mengubah lisensi upstream.
