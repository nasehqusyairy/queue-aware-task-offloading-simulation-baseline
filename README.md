[![License: GPL v3](https://img.shields.io/badge/Upstream-PureEdgeSim%20GPLv3-blue.svg)](simulator/PureEdgeSim/LICENSE)

# Queue-Aware Task Offloading — baseline experiment

Project penelitian ini membungkus PureEdgeSim untuk menjalankan baseline teknis bawaan Trade-Off dan Round Robin. **Ini belum reproduksi paper** dan belum mengimplementasikan Queue-Aware, GNN, atau DQN.

## Mulai cepat

Perlu Java dan Maven, Python 3, Git. Perintah cepat:

```bash
./run.sh --help
./run.sh --method trade-off --devices 10
./run.sh --method round-robin --devices 10
```

Gunakan server statis agar dashboard dapat memuat JSON (browser sering melarang `fetch()` saat file://):

```bash
python3 -m http.server 8000 --directory results
# buka http://localhost:8000/dashboard.html
```

CSV dan JSON agregat tersedia di `results/processed/summary.csv` dan `.json`. Untuk membangun ulang dari run sukses: `./analyze.sh --latest`.

## Apa yang dilakukan

PureEdgeSim's tracked `pom.xml` needs a small source-root correction (`${project.basedir}/PureEdgeSim`) because repository Java files live there, not Maven's default `src/main/java`; without it Maven `package` reported success while compiling zero classes. This is an explicit local change in the nested upstream checkout and is visible in its Git diff. Dashboard and analyzer use the real row in `Sequential_simulation.csv`; metrics parser uses the simulator's actual column names and Wh energy field.

PureEdgeSim default properties mendefinisikan `TRADE_OFF,ROUND_ROBIN`; `DefaultOrchestrator` mengimplementasikan keduanya. Perubahan konfigurasi penelitian mengatur 10/20/30 device dan satu arsitektur aktif. Pengaturan waktu PureEdgeSim bernilai **menit**, bukan detik. Simulasi di penelitian menyebut 200 detik, berbeda dari konfigurasi default; konfigurasi ini belum disamakan penuh.

## Status

- **Berhasil diverifikasi**: upstream entry point `com.mechalikh.pureedgesim.MainApplication` berjalan dari Maven; source-root correction menghasilkan 87 source compiled; Trade-Off dan Round Robin masing-masing selesai, menulis CSV asli, dan terparse.
- **Belum diuji penuh**: 20/30 perangkat dan seluruh konfigurasi paper.
- **Belum tersedia**: GNN/DQN paper, Queue-Aware, 4 DC terkontrol, enam target, serta seed/repetisi yang direproduksikan.


## Hindari klaim berlebihan

Parser tidak memalsukan metrik. Nilai yang tidak bisa diekstrak ditampilkan sebagai N/A. Dashboard bersumber dari berkas hasil setiap run. Hasil upstream dan setting yang dipakai harus diperiksa terhadap manifest; simulator tidak dijanjikan deterministik, dan seed tidak diasumsikan.

## Lisensi

PureEdgeSim merupakan GPL-3.0 (lihat lisensi upstream). Kode wrapper baru dan dokumentasi ini dipisahkan dari kode upstream; tidak ada lisensi baru yang mengubah lisensi upstream.
