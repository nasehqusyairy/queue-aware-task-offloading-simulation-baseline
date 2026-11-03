# Laporan Audit Eksperimen Queue-Aware

Tanggal audit: 3 November 2026. Bahasa laporan: Bahasa Indonesia.

## 1. Ringkasan eksekutif

Sebanyak 17 run PureEdgeSim baru selesai dengan status `completed` dan tanpa error validasi: smoke Queue-Aware, perbandingan tiga metode pada low, matriks 3 metode × 3 workload, serta empat run tambahan dari acceptance test opt-in. Tugas berhasil, gagal, dan pending direkonsiliasi pada setiap run. Pasangan metode memakai seed dan jejak tugas/sumber/posisi yang sebanding.

Pada matriks seed 1, Queue-Aware sama dengan Trade-Off dan Round Robin pada low. Pada medium, Queue-Aware mencatat 42 task selesai lebih banyak (+0,072 poin persentase success rate), dengan rata-rata delay sedikit lebih rendah tetapi energi sedikit lebih tinggi. Pada high, Queue-Aware menyelesaikan 79 task lebih sedikit (−0,091 poin persentase), dan rata-rata delay/waiting lebih tinggi. Jadi hasil ini **tidak mendukung klaim bahwa Queue-Aware meningkatkan kinerja secara konsisten**.

Temuan audit yang paling membatasi interpretasi: PureEdgeSim hanya meminta orchestrator memilih node saat aplikasi UE belum ditempatkan atau placement perlu diperbarui. Sesudah placement, task dikirim langsung ke node yang tersimpan. Pada matriks, log Queue-Aware mencatat 1.005, 2.017, dan 2.385 keputusan dari 29.000, 58.000, dan 87.000 task yang didispatch (2,7–3,5%). Dengan demikian implementasi saat ini adalah queue-aware **application placement/re-placement**, bukan keputusan ulang independen untuk setiap task. Hasilnya belum menjawab hipotesis task-level secara penuh.

## 2. Repository, branch, commit, dan kondisi kerja

- Repository: `queue-aware-task-offloading-simulation-baseline`.
- Branch saat mulai: `main`.
- Commit yang diuji: `03acb8635144a99b147b3d9e97017052cfaf4978`.
- Working tree sebelum eksperimen: bersih.
- Tidak ada perubahan kode, commit, push, merge, atau perubahan remote pada tugas audit ini. Laporan dan salinan bukti disimpan pada direktori baru `reports/queue_aware_audit_20261103T154150Z/`.
- Setiap simulasi membuat direktori bertimestamp baru di `results/runs/`; hasil lama tidak ditimpa.
- PureEdgeSim submodule revision: `bcdd239fa301bd7164526dc47685058288c305ef`.

## 3. Tujuan dan hipotesis

Tujuan: menilai apakah queue/workload-aware offloading dapat memperbaiki penyelesaian task, terutama pada beban tinggi atau workload yang tidak seimbang. Metode pembanding adalah Trade-Off, Round Robin, dan Queue-Aware.

Hipotesis yang diuji bersifat terbuka. Eksperimen tidak mengasumsikan Queue-Aware akan lebih baik. Unit analisis yang dimaksud dalam tujuan adalah task offloading; keterbatasan granularity implementasi saat ini dijelaskan di bagian 5 dan 12.

## 4. Implementasi metode dan pemeriksaan kode

- **Trade-Off**: formula upstream PureEdgeSim memilih kandidat dengan skor terendah: `(H_j + 1) × w_type × task_length / MIPS_per_core`. Pada EDC, `w_type=1,2`; `H_j` adalah riwayat assignment kumulatif.
- **Round Robin**: upstream memilih kandidat eligible dengan assignment count terendah. Pada target eksperimen ini semua kandidat EDC berjenis sama dan memiliki kapasitas per-core sama, sehingga urutan pilihan Round Robin identik dengan Trade-Off pada ketiga workload. Hasil identik yang ditemukan sesuai mekanisme ini, bukan bukti kedua metode berbeda.
- **Queue-Aware**: class eksperimen terpisah mempertahankan skor Trade-Off dan menambahkan penalti `λ × W_queue`; nilai lebih rendah dipilih. `W_queue` merupakan waktu tunggu prediksi dalam detik dari active work dan FIFO queue saat keputusan dibuat. Default matriks `λ=1,0` (tak berdimensi). Jika estimate unavailable, digunakan skor dasar. `λ=0` diuji pada helper scoring, tetapi tidak ada run integrasi `λ=0` dalam eksperimen ini.
- **Tidak ada perubahan** pada implementasi upstream `DefaultOrchestrator` untuk tugas audit ini. Tiga metode dipasangkan pada konfigurasi dan seed yang sama.
- Queue audit mencatat ID task dan kandidat, skor dasar, wait estimate, panjang queue, active task count, skor gabungan, weight, dan kandidat terpilih. Audit tidak menyimpan snapshot MIPS/core dan panjang task secara eksplisit di setiap baris; sehingga keputusan dapat diperiksa, tetapi tidak sepenuhnya dihitung ulang dari CSV itu saja tanpa merekonstruksi konteks task/config.
- Test helper mencakup kondisi kosong, queue tunggal/beragam, kapasitas heterogen dan tidak valid, tie, beban berat, estimate unavailable, bobot nol, serta formula dasar Trade-Off.

**Granularity keputusan:** pada `DefaultSimulationManager.sendFromOrchToDestination`, orchestrator dipanggil hanya bila `isApplicationPlaced()` bernilai false. Jika aplikasi telah ditempatkan, task berikutnya langsung memakai `getApplicationPlacementLocation()`. Karena baris Queue-Aware dibuat di orchestrator, hanya keputusan placement/re-placement yang tercatat. Ini memberi sinyal queue pada keputusan tersebut, tetapi tidak memperbarui destinasi pada tiap task.

## 5. Validitas implementasi dan data

- Ketiga metode berjalan dan menghasilkan manifest `completed`; semua 17 run audit memiliki `validation_errors=[]` dan `metric_validation_errors=[]`.
- Pada 9 run matriks, generated = completed + terminally failed + pending; jumlah completion per layer sama dengan completion global. Ketiganya menggunakan 4 EDC dan 1,6 juta MIPS total nominal. Tujuan `EDGE_DC_ONLY` mengizinkan hanya EDC sebagai destination; seluruh 29k/58k/87k task tercatat didispatch ke layer Edge/EDC, dan tidak ada dispatch Cloud/Mist.
- Jejak `task_id/source_id/source_x/source_y` identik di antara tiga metode pada tiap workload. Run Queue-Aware seed 8128 diulang tiga kali; jejak sumber, urutan destination, dan metrik utama sama. Ini mendukung repeatability terbatas pada konfigurasi yang diuji.
- Round Robin dan Trade-Off menghasilkan urutan destination yang identik di setiap workload. Alasannya konsisten dengan node EDC homogen dan mekanisme penempatan aplikasi. Karena itu baseline tambahan ini tidak memberi pembanding keputusan yang berbeda untuk konfigurasi ini.
- Queue-Aware memilih destination berbeda dari Trade-Off pada medium dan high, tetapi tidak pada low. Queue estimate terpilih low 0 s, medium mean 12,56 s (median 0 s), high mean 69,72 s (median 60,16 s). Queue length mean yang tercatat masing-masing 0, 572,94, dan 4.406,26 task.
- Pada medium/high, angka wait estimate tidak sebanding langsung dengan actual waiting mean: `W_queue` adalah prediksi pada sebagian keputusan placement; actual waiting mean hanya task sukses yang menuntaskan return path. Perbedaan ini juga mengalami selection/censoring bias dan belum membuktikan akurasi prediksi.

## 6. Konfigurasi eksperimen

| Level | UE | Task rate yang ditawarkan | Work offered | Kapasitas EDC nominal | Rasio offered/capacity |
|---|---:|---:|---:|---:|---:|
| Low | 10 | 145 task/s | 0,92 juta MI/s | 1,60 juta MIPS | 0,575 |
| Medium | 20 | 290 task/s | 1,84 juta MI/s | 1,60 juta MIPS | 1,15 |
| High | 30 | 435 task/s | 2,76 juta MI/s | 1,60 juta MIPS | 1,725 |

Durasi setiap run 200 detik, target `EDGE_DC_ONLY`, 4 EDC, queue weight 1,0. Matriks memakai seed 1. Smoke dan pasangan low memakai seed 8128; acceptance opt-in juga mengulang pasangan low tersebut. Aplikasi memakai rates 20/30/3 task per detik per UE pada grup aplikasi dengan task length 500/5.000/30.000 MI. Ini implementasi interpretasi rate yang tercatat di repository, belum divalidasi terhadap paper tertentu. Level beban dihitung sebagai offered work dibagi kapasitas EDC nominal; bukan measured utilization.

## 7. Perintah yang dijalankan

```bash
./run.sh --profile paper-aligned-baseline --method queue-aware --devices 10 --destination-config EDGE_DC_ONLY --seed 8128 --queue-weight 1.0
./run.sh --profile paper-aligned-baseline --method all --workload-level low --destination-config EDGE_DC_ONLY --seed 8128 --queue-weight 1.0
python3 scripts/run_queue_aware_matrix.py --dry-run
python3 scripts/run_queue_aware_matrix.py
./analyze.sh --latest --profile paper-aligned-baseline --output-dir reports/queue_aware_audit_20261103T154150Z/evidence/processed_all_paper_final
RUN_QUEUE_AWARE_SMOKE=1 python3 -m unittest discover -s tests -p test_acceptance_queue_aware.py -v
RUN_PAPER_SMOKE=1 python3 -m unittest discover -s tests -p test_acceptance_paper_smoke.py -v
python3 -m unittest discover -s tests -v
```

Matriks dry-run mengeluarkan 9 perintah: tiga metode × tiga workload, duration 200 s, seed 1, λ 1,0. Maven mencetak peringatan deprecation `sun.misc.Unsafe`, tetapi build berhasil dan classes diverifikasi.

## 8. Status run

| Batch | Run diminta/terjadi | Berhasil | Gagal | Dilewati |
|---|---:|---:|---:|---:|
| Smoke Queue-Aware A | 1 | 1 | 0 | 0 |
| Tiga metode low B | 3 | 3 | 0 | 0 |
| Matriks C | 9 | 9 | 0 | 0 |
| Acceptance Queue-Aware opt-in | 3 | 3 | 0 | 0 |
| Acceptance Trade-Off opt-in | 1 | 1 | 0 | 0 |
| **Total run yang dilakukan** | **17** | **17** | **0** | **0** |

Test suite default: 19 test ditemukan, 17 lulus dan 2 acceptance test dilewati karena opt-in. Kedua acceptance dijalankan terpisah dan lulus. Java `QueueAwareScoringTest` dikompilasi dan dijalankan; keduanya exit code 0. Tidak ada kombinasi matriks yang dilewati.

## 9. Hasil kuantitatif matriks seed 1

`Success % = completed / generated × 100`. `Failed` adalah terminally failed; `Pending` masih unresolved pada horizon 200 s. Latency dan waiting adalah rata-rata task yang menyelesaikan return path. CPU execution dan energy berasal dari logger simulator; energy hanya komputasi node (Cloud + EDC + UE), tidak termasuk energy jaringan. Nilai lebih tinggi pada success lebih baik; nilai delay/wait/CPU/energy lebih rendah biasanya lebih baik, tetapi latency/wait dihitung hanya dari survivor yang completed.

| Beban | Metode | Gen. | Selesai | Gagal | Pending | Success % | Delay s | Wait s | CPU s | Energy Wh |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Low | Trade-Off | 29.000 | 2.994 | 25.977 | 29 | 10,324 | 5,841 | 0,270 | 0,1585 | 63,9882 |
| Low | Round Robin | 29.000 | 2.994 | 25.977 | 29 | 10,324 | 5,841 | 0,270 | 0,1585 | 63,9882 |
| Low | Queue-Aware | 29.000 | 2.994 | 25.977 | 29 | 10,324 | 5,841 | 0,270 | 0,1585 | 63,9882 |
| Medium | Trade-Off | 58.000 | 4.755 | 44.151 | 9.094 | 8,198 | 24,523 | 18,956 | 0,1542 | 98,5870 |
| Medium | Round Robin | 58.000 | 4.755 | 44.151 | 9.094 | 8,198 | 24,523 | 18,956 | 0,1542 | 98,5870 |
| Medium | Queue-Aware | 58.000 | 4.797 | 46.481 | 6.722 | 8,271 | 24,431 | 18,865 | 0,1489 | 99,0422 |
| High | Trade-Off | 87.000 | 5.605 | 44.937 | 36.458 | 6,443 | 40,338 | 34,766 | 0,1580 | 122,0795 |
| High | Round Robin | 87.000 | 5.605 | 44.937 | 36.458 | 6,443 | 40,338 | 34,766 | 0,1580 | 122,0795 |
| High | Queue-Aware | 87.000 | 5.526 | 45.175 | 36.299 | 6,352 | 42,466 | 36,894 | 0,1575 | 122,0841 |

**Queue/load balance diagnostics** — node counts are dispatched task decisions by EDC ID 1–4, calculated from `raw/destinations.csv`; CV = population standard deviation / mean of those four counts. CV reflects task counts, not MI workload or CPU utilization.

| Beban | Metode | EDC 1 / 2 / 3 / 4 decisions | CV | Queue wait estimate terpilih mean / median s | Mean queue length saat dipilih | Selected estimate count |
|---|---|---|---:|---:|---:|---:|
| Low | Trade-Off / Round Robin / Queue-Aware | 14.600 / 12.600 / 1.800 / 0 | 0,886 | 0,00 / 0,00 (Queue-Aware) | 0,00 | 1.005 |
| Medium | Trade-Off / Round Robin | 13.003 / 11.230 / 17.687 / 16.080 | 0,174 | N/A | N/A | N/A |
| Medium | Queue-Aware | 8.453 / 11.900 / 13.777 / 23.870 | 0,396 | 12,56 / 0,00 | 572,94 | 2.017 |
| High | Trade-Off / Round Robin | 24.660 / 27.060 / 18.050 / 17.230 | 0,193 | N/A | N/A | N/A |
| High | Queue-Aware | 22.180 / 25.860 / 21.630 / 17.330 | 0,139 | 69,72 / 60,16 | 4.406,26 | 2.385 |

Semua dispatch berada pada layer Edge/EDC; layer Cloud dan Mist nol karena target konfigurasi. Distribusi destination-layer tidak menunjukkan beda algoritma dalam eksperimen ini; distribusi antar-EDC memperlihatkan perubahan pilihan Queue-Aware pada medium dan high.

### Selisih Queue-Aware terhadap Trade-Off / Round Robin

- **Low:** tidak berbeda pada metrik hasil atau urutan destination; queue wait estimate mean 0 s.
- **Medium:** 42 completed tambahan dan +0,072 poin persentase success. Pending turun 2.372, tetapi terminal failure naik 2.330. Delay turun 0,092 s; waiting turun 0,091 s; CPU turun 0,0053 s; energy naik 0,4552 Wh. CV dispatch antar-EDC naik 0,221 (beban berbasis task count lebih tidak merata).
- **High:** 79 completed lebih sedikit dan −0,091 poin persentase success. Pending turun 159, tetapi terminal failure naik 238. Delay naik 2,128 s; waiting naik 2,128 s; CPU turun 0,0005 s; energy naik 0,0046 Wh. CV turun 0,054 (dispatch task count lebih merata), namun hasil completion/delay memburuk.

## 10. Interpretasi per workload

- **Low:** karena semua kandidat yang dipilih memiliki queue estimate 0 s, penalti queue tidak mengubah urutan. Hasil semua metode persis sama. Kondisi ini menguji integrasi dan beban di bawah kapasitas nominal, tetapi tidak menguji efektivitas queue penalty.
- **Medium:** terdapat perubahan pilihan EDC Queue-Aware dan peningkatan completion yang kecil. Perubahan ini terjadi bersama lonjakan terminal failure dan penurunan pending yang hampir sama besar; sebagian task berpindah dari pending menjadi failure, sehingga kenaikan success tidak boleh ditafsirkan sebagai penurunan kegagalan. Queue count CV justru memburuk.
- **High:** queue penalty tercatat aktif dan distribusi task antar-EDC menjadi lebih merata menurut CV, tetapi completed turun dan delay/wait task sukses meningkat. Pada konfigurasi ini, load balancing berdasarkan jumlah task tidak cukup untuk menjamin peningkatan kinerja.
- **Round Robin:** hasil/destinasi sama dengan Trade-Off untuk semua beban. Karena itu perbandingan tambahan ini berkolaps pada skenario EDC homogen tersebut.

## 11. Penilaian terhadap tujuan penelitian

Implementasi benar-benar membaca active tasks dan FIFO queue saat keputusan placement/re-placement dibuat, dan pada medium/high informasi tersebut mengubah sebagian pemilihan destination. Jadi mekanisme queue-aware ada dan teramati di log. Akan tetapi ia tidak dipanggil ulang untuk setiap task setelah aplikasi UE terpasang.

Matriks terlalu terbatas untuk menyimpulkan efektivitas umum: hanya satu seed di tiap workload, λ tunggal, satu target layer homogen, serta satu durasi. Repeated seed 8128 memberi repeatability terbatas untuk low, bukan sampel statistik independen. Hasil medium kecil positif dan high negatif; tidak ada bukti peningkatan konsisten atau statistik signifikansi. Perbaikan CV pada high bersamaan dengan hasil utama yang lebih buruk adalah trade-off yang perlu dianalisis, bukan bukti keberhasilan.

## 12. Threats to validity dan keterbatasan

1. **Application placement vs per-task offloading:** sumber `DefaultSimulationManager.java:294–315` mengunci task ke `applicationPlacementLocation` saat aplikasi sudah ditempatkan. Log queue mencatat hanya 2,7–3,5% dari jumlah task dispatch pada matriks. Ini ancaman validitas paling besar terhadap tujuan task-level.
2. **Baseline Round Robin tidak diskriminatif di target ini:** empat EDC memakai class/capacity sama dan kandidat reachable; aturan minimum count dari Round Robin dan skor Trade-Off memberi urutan identik. Penelitian selanjutnya perlu target/resource heterogen atau workload/candidate set yang membuat baseline berbeda, ditetapkan sebelum melihat hasil.
3. **Queue estimate belum tervalidasi sebagai prediktor:** pada high mean estimasi queue 69,72 s dibanding observed waiting 36,89 s di task completed; median estimasi 60,16 s. Kedua nilai mengambil populasi berbeda. Queue mean length 4.406 menggambarkan antrean pada saat subset keputusan, bukan rata-rata tiap task.
4. **Metrik completion tersensor:** total delay dan waiting dihitung hanya untuk task yang kembali sukses. Task gagal/pending tidak masuk mean tersebut, sehingga comparison dapat memiliki survivorship bias.
5. **Satu seed matriks dan satu lambda:** tidak mengukur ketidakpastian antar-seed atau sensitivitas λ. Seed 8128 diulang pada low, tetapi itu bukan banyak seed independen.
6. **Workload dan konfigurasi:** interpretasi rate per UE adalah pilihan implementasi. Rasio offered load bukan utilisasi aktual. Konfigurasi belum diverifikasi terhadap paper; tidak ada klaim reproduksi paper.
7. **Queue audit bukan replay lengkap:** informasi kandidat/skor/queue cukup untuk memeriksa winner yang terekam; beberapa nilai state untuk mereproduksi skor secara independen tidak dicatat per keputusan.
8. **Energy:** hanya computing-node energy, jaringan terpisah; bukan total system energy.

## 13. Kesimpulan proporsional

Pada commit dan konfigurasi yang diuji, run dapat direproduksi dalam batas uji seed yang tersedia, accounting valid, dan Queue-Aware menggunakan queue state untuk keputusan yang terjadi. Namun algoritma saat ini bekerja saat application placement/re-placement, bukan pada setiap task. Hasil hanya memperlihatkan perubahan di medium/high: perubahan medium kecil dan high menurunkan success serta menaikkan delay. Tidak ada dasar untuk menyatakan Queue-Aware memperbaiki task offloading secara umum.

## 14. Langkah berikutnya yang direkomendasikan

1. Putuskan dan dokumentasikan unit keputusan penelitian: application placement atau setiap task. Jika hipotesis tetap task-level, buat jalur eksperimen dengan pemilihan ulang untuk tiap task dan terapkan mekanisme orchestrator yang sepadan pada semua metode supaya perbandingan tetap adil.
2. Tambahkan counter eksplisit: jumlah invocation orchestrator, jumlah task yang memakai cached placement, jumlah placement invalidation, dan persentase keputusan queue-aware dari task generated/sent.
3. Perkuat audit CSV dengan task app/type/length, per-candidate core count dan MIPS, placement state, serta alasan kandidat eligible, agar score/winner dapat direkonstruksi.
4. Jalankan beberapa seed independen dan interval ketidakpastian; tambahkan λ=0 integrasi serta beberapa λ positif yang ditetapkan sebelumnya.
5. Uji estimator dengan membandingkan prediksi wait dan observed wait untuk cohort yang sama, termasuk task gagal/pending atau jelaskan sensorannya; pertimbangkan metric workload berbasis MI, bukan hanya task count.
6. Uji target/resource heterogen dan pastikan Round Robin dan Trade-Off menghasilkan baseline perilaku berbeda sebelum memakai keduanya sebagai pembanding substantif.
7. Verifikasi konfigurasi, rate, deadline, resource, energy scope, dan lifecycle terhadap metodologi paper sebelum membuat klaim paper-aligned.

## 15. Artefak dan bukti

Semua artefak berikut berada pada folder audit ini:

- `evidence/run_summary.csv` — 17 run audit yang difilter, satu baris per run.
- `evidence/run_index.json` — manifest metrics dan status rinci tiap run, termasuk distribusi destination per EDC.
- `evidence/runs/<run_id>/` — salinan manifest, config, seluruh raw output, log, destination trace, dan queue decision audit untuk setiap 17 run.
- `evidence/matrix_console.log`, `evidence/matrix_dry_run.txt`, `evidence/executed_commands.txt` — perintah, console output matriks, dan dry-run.
- `evidence/paired_trace_check.json`, `evidence/same_seed_repeatability_check.json` — pemeriksaan jejak input berpasangan dan pengulangan seed.
- `evidence/unit_tests.log`, `evidence/queue_aware_acceptance_test.log`, `evidence/paper_smoke_acceptance_test.log`, `evidence/java_scoring_test.log` — hasil test.
- `evidence/processed_all_paper_final/` — output resmi `analyze.sh --latest`; berisi 38 run paper-profile termasuk historical. Untuk kesimpulan audit ini, gunakan 17 run yang terdaftar di `run_summary.csv`, bukan seluruh aggregate historis.
- `evidence/create_audit_artifacts.py` — skrip yang membangun ringkasan terfilter dan menyalin bukti run.

Tidak ada file run yang dikecualikan karena ukuran; folder evidence lengkap sekitar 92 MB sebelum kompresi.
