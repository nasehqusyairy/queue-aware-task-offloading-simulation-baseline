# Experiment Report

## 1. Objective

Menguji alur eksperimen satu perintah dan membandingkan Trade-Off dengan Queue-Aware pada workload low, medium, dan high dengan kondisi berpasangan. Hipotesis yang diperiksa: penambahan skor antrean dapat mengubah pemilihan EDC dan memperbaiki completion/delay. Ini uji quick satu seed, bukan uji konklusif.

## 2. Changes Made

- `run_experiment.sh`, `scripts/run_experiment.py`: entry point matriks, validasi dependency, progres, output terisolasi, resume tanpa menimpa sel selesai.
- `run.sh`: menerima `RUNS_ROOT` supaya run masuk ke direktori eksperimen.
- `configs/experiment/matrix.json`: workload, metode, seed, durasi, target, dan lambda.
- `scripts/aggregate_experiment.py`: mengambil metrik dari `metrics.json` tiap run dan membuat CSV level-run/summary.
- `scripts/visualize_experiment.py`, `view_results.sh`: membuat PNG dan HTML viewer dari data aktual.
- `README.md`: instruksi run/resume/view.
- `REPORT.md`, `EXPERIMENT_REPORT.md`, CSV, PNG, HTML: bukti hasil eksperimen.

Perubahan workflow tidak mengubah formula algoritma atau parameter baseline. Run Queue-Aware memakai konfigurasi antrian yang sudah ada, λ=1.0. Kode tracing/audit lokal yang menjadi prasyarat dari pekerjaan sebelumnya juga ada di working tree; tidak diubah untuk matriks ini. Semua output eksperimen memakai profil `paper-aligned-baseline`, target `EDGE_DC_ONLY`.

## 3. Experiment Configuration

- Experiment ID: `20261103T173420Z_quick`
- HEAD: `7cd0acabe3255552a79f33dd55dc31612833914b`; working tree **dirty**. Manifest run menyimpan commit ini dan hash konfigurasi. Pasangan per workload memiliki hash konfigurasi dan simulator properties yang sama.
- Metode: `trade-off`, `queue-aware`; 4 EDC (`dc1`–`dc4`), 10/20/30 UE untuk low/medium/high.
- Workload: `paper-aligned-baseline`; seed 1; durasi 1 detik simulasi per sel; target `EDGE_DC_ONLY`.
- λ: 1.0 Queue-Aware; tidak berlaku untuk Trade-Off.
- Command yang menyelesaikan matriks di sesi ini: `PATH=/tmp/task-trace-bin:$PATH ./run_experiment.sh --quick --resume`. Wrapper Maven lokal dipakai untuk mode offline karena cache Maven host read-only. Command normal pada checkout dengan dependency siap: `./run_experiment.sh --quick`.
- Enam pasangan cell lengkap: masing-masing method × workload. Manifest per-run berada di `runs/<run_id>/manifest.json`.

## 4. Execution Status

- Direncanakan 6 run; 6 run simulator berstatus `completed`, exit 0, tanpa validation errors; simulasi gagal: 0.
- Percobaan awal menemukan bug output root (`RUNS_ROOT` ditimpa); dua run low yang sudah selesai dipertahankan, dipindahkan ke direktori experiment, lalu sel tersebut dilewati pada resume. Bukti status pemulihan tersimpan di `experiment.json` (`last_error`); tidak ada hasil lama yang ditimpa.
- Output utama tersedia untuk keenam run: `metrics.json`, manifest, `raw/destinations.csv`, simulator CSV, dan log. Quick matrix berstatus completed dengan `completed_cells=6`.

## 5. Destination Selection Verification

Jumlah task dari `raw/destinations.csv` menurut ID EDC. ID dipetakan ke nama EDC dari `configs/paper-aligned/edge_datacenters.xml`.

| Workload | Trade-Off: dc1, dc2, dc3, dc4 | Queue-Aware: dc1, dc2, dc3, dc4 | EDC aktif |
|---|---:|---:|---:|
| Low (10 UE) | 83, 53, 9, 0 | 83, 53, 9, 0 | 3 dari 4 |
| Medium (20 UE) | 62, 59, 59, 110 | 62, 59, 59, 110 | 4 dari 4 |
| High (30 UE) | 169, 169, 59, 38 | 169, 169, 59, 38 | 4 dari 4 |

Lebih dari satu EDC benar-benar menerima task di semua workload; bukti hitungan berasal dari audit destination per task, bukan sekadar konfigurasi kandidat. Queue-Aware memiliki audit candidate/score/selected di `raw/queue_decisions.csv`. Contoh low: 16 candidate rows, 10 pemilihan, queue estimate tersedia untuk 10 pemilihan; medium 30 rows/20 pemilihan; high 42 rows/30 pemilihan. Source `QueueAwareTradeOffOrchestrator.findComputingNode()` memanggil `estimateQueueWaitSeconds()` dan memasukkan hasil serta λ ke `QueueAwareScoring.combinedScore()` (baris 47–85); `QueueAwareComputingNode.estimateQueueWaitSeconds()` menggunakan active task dan waiting queue (baris 50–71).

Namun semua queue-wait estimate dan waiting queue length yang tercatat pada ketiga run Queue-Aware adalah 0.0/0, sehingga log membuktikan jalur queue-aware dieksekusi, tetapi tidak membuktikan adanya sinyal beban nonzero yang mengubah ranking kandidat. Nilai yang tersedia menunjukkan skor terpilih sama dengan baseline score pada sampel ini. Pemilihan terjadi pada hook orchestrator yang dipanggil saat placement aplikasi; task berikutnya dapat memakai placement cache. Ini bukan bukti pemilihan ulang mandiri untuk setiap task.

## 6. Results

Success rate = completed/generated. Failed adalah terminal failure; pending adalah task belum terminal pada cutoff. Energy = simulator computing-node energy (Wh; network energy terpisah). Delay = simulator average completed-task total delay (detik): accumulated network + queue waiting + CPU. Per-EDC merupakan jumlah task pada destination audit. Queue wait adalah average waiting time task completed menurut metrik simulator; utilization tidak tersedia.

| Workload | Method | Generated | Completed | Failed | Pending | Rate | Energy (Wh) | Delay (s) | Avg queue wait (s) | Per-EDC task allocation dc1/dc2/dc3/dc4 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Low | Trade-Off | 145 | 9 | 120 | 16 | 6.21% | 0.3189 | 5.5766 | 0.0000 | 83/53/9/0 |
| Low | Queue-Aware | 145 | 9 | 120 | 16 | 6.21% | 0.3189 | 5.5766 | 0.0000 | 83/53/9/0 |
| Medium | Trade-Off | 290 | 0 | 230 | 60 | 0.00% | 0.5127 | N/A | N/A | 62/59/59/110 |
| Medium | Queue-Aware | 290 | 0 | 230 | 60 | 0.00% | 0.5127 | N/A | N/A | 62/59/59/110 |
| High | Trade-Off | 435 | 10 | 260 | 165 | 2.30% | 0.6262 | 5.6016 | 0.0250 | 169/169/59/38 |
| High | Queue-Aware | 435 | 10 | 260 | 165 | 2.30% | 0.6262 | 5.6016 | 0.0250 | 169/169/59/38 |

Medium delay and completed-task queue wait are N/A because no task completed; they are not zero. Queue-aware estimated queue wait in its decision audit was 0.0 s in all three workloads. Queue utilization is not reported by these artifacts.

## 7. Quick Comparison

Queue-Aware minus Trade-Off completion rate was 0.00 percentage point at low, medium, and high; task outcomes, energy, delay where defined, and per-EDC allocation matched exactly. There is one paired seed only, so cross-seed consistency cannot be assessed. The observed results do not support the improvement hypothesis in this run; because recorded queue loads were zero, they also do not test Queue-Aware under a nonzero queue signal.

## 8. Known Limitations

- One seed, one-second horizon, six runs: preliminary and not statistically supported.
- Queue estimates were all zero; no positive queue-pressure condition was observed.
- Per-EDC placement counts are available, but per-node queue/utilization is not. Equal allocation counts do not establish equal utilization.
- Medium had no completed tasks; delay statistics are undefined there.
- Simulator delay is accumulated network + queue + CPU. PureEdgeSim event-clock elapsed may differ because per-hop delay accumulation and event scheduling have different semantics; do not interpret delay as wall-clock or pure network latency.
- First launcher attempt exposed the `RUNS_ROOT` issue. The fix was applied; all final six outputs are inside this experiment directory and manifest validations pass.

## 9. Reproduction

```bash
./run_experiment.sh --quick
./view_results.sh results/experiments/20261103T173420Z_quick
```

Config: `configs/experiment/matrix.json`. Raw run files: `runs/<run_id>/raw/`. Aggregation: `aggregate.csv`, `aggregate_summary.csv`. Charts: `charts/*.png`; HTML: `index.html`. Each run's exact properties, command, seed, and configuration hashes are recorded in its manifest.

## 10. Recommended Next Step

Run a longer paired diagnostic at a workload/duration that produces nonzero queue estimates, preserving identical seeds and configurations across methods; first verify from `queue_decisions.csv` that candidate queue waits differ from zero. Only then expand to multiple seeds and evaluate paired outcomes.

## 11. Audit Checklist

- [PASS] Experiment completed — `experiment.json`: completed, 6/6 cells; six manifests completed with no validation errors.
- [PASS] Expected output files exist — six raw run folders, aggregate CSVs, five PNGs, `index.html`, this report.
- [PASS] Both methods used same seed/configuration — seed 1 and equal configuration hashes/properties per workload.
- [PASS] Multiple EDCs received tasks — 3 EDC at low; 4 at medium/high, verified in `destinations.csv`.
- [PASS] Destination selection is logged — per-task records in each `raw/destinations.csv`.
- [PASS] Queue-Aware queue/workload scoring path executed — candidate queue estimates logged and passed into combined score; **observed estimates were all zero**, so meaningful queue-pressure influence is INCONCLUSIVE.
- [PASS] Metrics are calculated from valid data — six manifests have empty validation errors; CSV rows reconcile to raw `metrics.json`; undefined medium delay stays N/A.
- [INCONCLUSIVE] Results are reproducible — exact seed/config/command are recorded, but this matrix has only one realization per cell and was not independently rerun.
