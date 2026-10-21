# Experiment protocol

1. Pilih metode bawaan PureEdgeSim (TRADE_OFF atau ROUND_ROBIN), jumlah perangkat, durasi simulasi dalam **menit**, dan arsitektur (default EDGE_AND_CLOUD).
2. Wrapper memeriksa Java, Maven, Python, dan source simulator. Maven membangun project, kemudian simulasi dijalankan dari konfigurasi khusus run.
3. Log/output simulator disimpan dalam folder run baru. `config.json` dan `manifest.json` mencatat parameter, commit simulator, perintah, waktu, status dan keterangan seed.
4. Analyzer menulis `metrics.json`, `summary.txt`, CSV agregat, JSON agregat, dan dashboard HTML. Data yang belum ditemukan tidak diubah menjadi nol.
5. Jalankan metode kedua dengan setting sama untuk perbandingan. Gunakan tiga pengulangan independen sebelum inferensi statistik; saat ini wrapper membuat run berbeda tetapi belum mengatur random seed.

## Keterbatasan baseline

Paket ini memulai dengan satu arsitektur, bukan enam pilihan tujuan offloading dalam artikel. Target artikel menyebut 10/20/30 UE, 4 Edge DC, 200 detik, tiga repetisi. Versi konfigurasi saat ini belum menegakkan empat DC dan durasi 200 detik. Properties upstream mengukur waktu dalam menit. Jangan melabeli hasil ini sebagai reproduksi paper. Metrik energi dan distribusi node baru disediakan jika dapat diekstrak secara valid dari log asli.
