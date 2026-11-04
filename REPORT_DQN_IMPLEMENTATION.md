# REPORT_DQN_IMPLEMENTATION

**Status:** implementasi DQN dan pilot perangkat lunak selesai. Tidak ada klaim bahwa DQN telah belajar kebijakan yang efektif.  
**Repository commit dasar:** `c313a4090d9dd9bef5e7a05316e0bb7c5efe6e41` (seluruh perubahan tugas ini masih uncommitted).  
**Pilot final:** `results/experiments/20261104T010929Z_dqn_pilot/`  
**Simulator revision:** `bcdd239fa301bd7164526dc47685058288c305ef`

## 1. Executive Summary

Metode `dqn` kini terhubung ke jalur keputusan task-level dan menjalankan training, checkpoint save/load, serta frozen evaluation. Implementasi menggunakan Java dalam proses simulator karena PyTorch tidak tersedia (`import torch` menghasilkan `ModuleNotFoundError`) dan proyek tidak menyediakan integrasi agen Python yang persisten. Tidak ada subprocess per keputusan.

Pilot final menjalankan 3 episode training dan 6 evaluasi berpasangan. Semua 9 simulasi selesai dengan status `completed` dan nol validation error. Checkpoint berukuran 197,964 byte dibuat. Reproduksi mode eval tidak mengubah SHA-256 checkpoint. Tes internal transition ledger dan komponen DQN lulus. Hasil metrik pilot bersifat software validation dengan workload kecil deterministik, bukan bukti keunggulan performa atau generalisasi.

## 2. Architecture

- `DqnMain` memilih `DqnReadySimulationManager`, `DqnReadyOrchestrator`, `DqnReadyComputingNode` dan `PerTaskValidationTaskGenerator`.
- `DqnOffloadingPolicy` mengimplementasikan `OffloadingPolicy`; orchestrator tetap memanggilnya pada setiap dispatch task dan menerapkan kandidat terpilih.
- `DqnAgent` menjalankan epsilon-greedy, replay, optimizer, online network dan target network dalam JVM simulator yang sama.
- `DqnQNetwork` adalah MLP kandidat bersama: dua hidden layer ReLU dan satu output Q per kandidat. Jumlah kandidat dapat berubah antar-state.
- `DqnReplayBuffer` menyimpan transisi lengkap. Checkpoint Java serialization memuat kedua network, Adam moments, replay buffer, RNG, jumlah keputusan/update, loss terakhir, serta metadata fingerprint konfigurasi.
- Evaluasi tanpa eksplorasi (`epsilon=0`), tanpa replay insertion, training update maupun checkpoint save.

PureEdgeSim tidak diubah. Trade-Off dan Queue-Aware tidak diganti algoritmanya. Perubahan pada entry point `PaperAlignedMain`/`QueueAwareMain` hanya memilih workload validasi 64-task apabila properti opt-in dinyalakan. `run.sh` dan `execute_run.py` menambah routing metode `dqn` dan pencatatan artefak.

## 3. State Representation

`DqnStateEncoder` menggabungkan:

- 3 fitur task: MI, request bits, deadline (nilai ternormalisasi).
- 5 fitur konteks eligible candidates: queue mean dan missing flag, waiting-estimate mean dan missing flag, CPU utilization mean.
- 11 fitur tiap kandidat: waiting queue plus missing flag, active tasks plus missing flag, queue wait estimate plus missing flag, MIPS/core, cores, utilization, resource availability dan eligibility.

Input MLP berukuran 19 untuk satu pasangan state-candidate. Kandidat dengan mask `false` dikeluarkan dari pemilihan dan target max-Q. Urutan action memakai `DqnActionSpace.stableOrder`; EDC ID dipakai sebagai mapping action yang eksplisit, bukan sebagai fitur angka. Dimensi action tidak mengasumsikan jumlah EDC tetap.

Network-condition feature tidak dimasukkan: `OffloadingObservation` yang tersedia tidak memberikan fitur network-condition yang dapat dipasangkan dengan kandidat saat keputusan. Total delay network tetap masuk reward terminal dari metrik task aktual.

## 4. Action Space and Masking

Orchestrator membuat mask dari `offloadingIsPossible(task, candidate, architecture)`. `DqnAgent.select` hanya memilih dari indeks yang mask-nya aktif; state tanpa action mengembalikan `-1`. Replay insertion memvalidasi lagi aksi bahwa index valid dan mask aktif. Seleksi destinasi DQN bypass placement cache melalui `DqnReadySimulationManager.sendFromOrchToDestination`.

Pada lima DQN runs, masing-masing mempunyai 64 policy decisions dan 64 destination rows; jumlah mismatch antara `selected_edc_id` dan `actual_applied_destination_id` adalah **0**. Lebih dari satu EDC menerima task pada setiap run:

| Run | Task per EDC aktual |
|---|---|
| Training seed 11 | EDC 3: 32; EDC 4: 32 |
| Training seed 29 | EDC 2: 27; EDC 4: 37 |
| Training seed 47 | EDC 2: 28; EDC 4: 36 |
| Evaluation seed 8128 | EDC 1: 55; EDC 3: 9 |
| Evaluation seed 4401 | EDC 1: 55; EDC 2: 9 |

## 5. Reward Definition

Reward dihitung ketika task memiliki outcome terminal dan menggunakan `Task.getTotalDelay()` dalam detik:

```text
success: +completion_reward - delay_penalty_coefficient * total_delay_seconds / delay_normalization_seconds
failure: -failure_penalty - delay_penalty_coefficient * total_delay_seconds / delay_normalization_seconds
```

Pilot memakai `completion_reward=1.0`, `failure_penalty=1.0`, `delay_penalty_coefficient=0.1`, dan `delay_normalization_seconds=5.0` dari `configs/dqn/training.properties` (nilai evaluation harus identik). Failure tetap menerima reward negatif. Reward tersedia hanya pada completion/failure dan dicocokkan dengan task ID. Pending tidak diberi reward. Energi hanya metrik evaluasi; tidak dibebankan ke task karena atribusi individual tidak tersedia.

Mean episode reward training yang terukur: 56.6255, 56.5133, dan 56.6081 untuk episode 1–3. Nilai ini hanya ringkasan reward pada 64 terminal outcomes; tidak menunjukkan pembelajaran efektif.

## 6. Asynchronous Transition Semantics

Dipilih desain **event-driven next state dengan reward terminal tertunda yang dicocokkan lewat task ID**:

1. Pada policy decision task `i`, ledger menyimpan `(task_id, state_i, action_i)`.
2. State keputusan policy berikutnya menjadi `next_state_i`; makna ini adalah observasi keputusan task berikut dalam urutan event, bukan state setelah task yang sama selesai.
3. Reward task `i` dicatat saat outcome terminal task `i` tiba. Urutan completion boleh berbeda dari urutan keputusan.
4. Transition masuk replay sekali setelah reward dan `next_state` sama-sama tersedia. `emitted` dan terminal ID set mencegah duplikasi.
5. Aksi valid terakhir ditandai terminal pada horizon. Jika reward task masih belum tersedia, transition tetap tidak masuk replay.
6. Task pending mempertahankan catatan task/ledger dan ditulis `HORIZON_PENDING_NO_REWARD`; tidak diberi failure reward buatan.

`DelayedTransitionLedger` dites untuk completion out-of-order, korelasi reward per task ID, terminal duplikat, dan pending tanpa replay insertion. Dalam pilot seluruh 64 task DQN selesai, jadi cabang pending diintegrasi tetapi diverifikasi melalui unit test, bukan contoh simulasi pending DQN.

## 7. DQN Implementation

`DqnQNetwork` menggunakan backpropagation MSE dan Adam (`β1=.9`, `β2=.999`), gradient dari target DQN, dan target-network copy berkala. Default pilot: hidden 32×32, batch 16, warm-up 32 transition, gamma .95, learning rate .0005, target update interval 50 update, replay capacity 2,000, epsilon 1.0 ke .05 sepanjang 2,000 keputusan. Pilot mengumpulkan 64 transition/episode; replay size setelah training berturut-turut 64, 128, 192. Update count kumulatif 33, 97, 161.

Loss terakhir tiap episode training finite: `0.00709139055594`, `0.554111905862`, `0.163017556994`. Q value diperiksa finite pada semua action eligible termasuk saat eksplorasi. Target network sinkronisasi, optimizer, action mask, replay sample dan checkpoint/load diuji pada self-test Java.

## 8. Java–Python Integration

Tidak digunakan Python/PyTorch: runtime Python tersedia tetapi `torch` tidak terpasang, Maven project juga tidak mempunyai dependency ML yang sudah dipakai. Solusi adalah implementasi Java sederhana tanpa service/proses terpisah, sehingga tidak ada IPC, timeout per task, atau risiko blocking ke proses Python. Keterbatasannya: network/optimizer buatan sendiri memiliki cakupan lebih kecil dibanding framework ML matang dan checkpoint Java serialization bergantung kompatibilitas versi class/JVM.

## 9. Training Lifecycle

`scripts/run_dqn_pilot.py` menjalankan episode sebagai JVM simulator baru, sambil melanjutkan checkpoint dan RNG/replay state yang sama. Seed simulator training `11, 29, 47`; checkpoint agent diinisialisasi dengan seed `20261104`. Raw task trace, destination audit, per-task audit, transition audit, simulator CSV, log console, konfigurasi dan manifest disimpan per-run. Training mencatat episode reward, completion/failure/pending, delay, actual waiting, epsilon, decision count, replay size, loss dan update count dalam `training_metrics.csv`.

## 10. Frozen Evaluation

Seed evaluasi `8128` dan `4401` tidak digunakan saat training. Masing-masing menjalankan Trade-Off, Queue-Aware dan DQN dengan 10 UE, 4 EDC, 5 simulated seconds, `EDGE_DC_ONLY` dan workload identik berisi 64 task dari satu UE. `paired_evaluation_validation` menegaskan signature simulator/workload/config sama di setiap seed.

Checkpoint SHA-256 sebelum evaluasi sama dengan sesudahnya. Evaluasi melaporkan `epsilon=0`, mempertahankan replay size 192 dan update count 161, dan `dqn_transitions.csv` mencatat **0** baris dengan `replay_inserted=true` (64 transisi `TRANSITION_READY` per run, bukan pembelajaran).

## 11. Test Results

- `./scripts/test_dqn_foundation.sh`: `DqnActionSpaceSelfTest: 9 checks passed`; `DqnImplementationSelfTest: 18 checks passed`.
- `python3 -m pytest --import-mode=importlib -q`: **25 passed, 3 skipped, 6 subtests passed**.
- `python3 -m py_compile scripts/run_dqn_pilot.py scripts/execute_run.py`: lulus.
- `git diff --check`: lulus.
- Re-run `per-task-test` seed 1, 5 s: status `completed`, 64/64 selesai, 0 validation errors. Satu percobaan smoke sebelumnya gagal karena reward default dipanggil oleh deterministic policy; dispatch reward lalu dibatasi ke `DqnOffloadingPolicy`, dan run final lulus. Output percobaan gagal tetap tersimpan, tidak dipakai sebagai hasil.

## 12. Pilot Experiment Results

Final experiment `20261104T010929Z_dqn_pilot`: **9 direncanakan, 9 selesai, 0 gagal**. Semua raw output berada pada `runs/<run_id>/raw/`; seluruh manifest mencatat 0 validation errors.

| Metode | Seed | Generated | Completed | Failed | Pending | Completion | Energy (Wh) | Avg total delay (s) | Avg actual wait (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Trade-Off | 8128 | 64 | 59 | 0 | 5 | 92.1875% | 0.8719 | 6.6559 | 1.1059 |
| Queue-Aware | 8128 | 64 | 59 | 0 | 5 | 92.1875% | 0.8719 | 6.6559 | 1.1059 |
| DQN frozen | 8128 | 64 | 64 | 0 | 0 | 100% | 0.8726 | 6.3131 | 0.7594 |
| Trade-Off | 4401 | 64 | 59 | 0 | 5 | 92.1875% | 0.8719 | 6.6559 | 1.1059 |
| Queue-Aware | 4401 | 64 | 59 | 0 | 5 | 92.1875% | 0.8719 | 6.6559 | 1.1059 |
| DQN frozen | 4401 | 64 | 64 | 0 | 0 | 100% | 0.8726 | 6.3131 | 0.7594 |

Delay dan waiting adalah metrik simulator untuk completed tasks; energy adalah Wh computing nodes (network energy terpisah). Queue-Aware audit mencatat 2 candidate observations pada jalur application placement dan queue estimate terpilih 0.0 s; itu tidak mengukur seluruh task-level observations DQN. DQN per-task audit mencatat 256 queue-estimate values per run (4 EDC × 64 decisions). Nonzero: 85/256 (min 0, max 0.635 s) pada training seed 11; 74/256 (0.725 s max) seed 29; 84/256 (0.845 s max) seed 47; 43/256 (2.1 s max) pada masing-masing seed eval.

**Interpretasi terbatas:** DQN mendapat 5 completion tambahan dan pending berkurang 5 pada dua seed ini; delay/wait lebih rendah sekitar 0.3428/0.3466 s, sedangkan energi lebih tinggi 0.0007 Wh. Hasil konsisten pada dua seed pilot ini, namun tidak statistically supported. DQN membuat keputusan task-level (64 per run); baseline Trade-Off/Queue-Aware tetap menggunakan jalur placement/cached placement yang auditnya hanya mencatat dua scoring candidate rows. Offered workload sama, tetapi kesempatan/unit keputusan algoritma tidak setara, sehingga selisih tidak boleh diartikan sebagai bukti superioritas DQN.

## 13. Limitations

- Hanya tiga training episode dan dua evaluation seeds; workload 64 task, satu UE, satu application profile, simulasi 5 detik. Ini validasi plumbing, bukan eksperimen performa umum.
- Workload deterministik dan sukses task semuanya 100% untuk DQN; failure-reward learning belum diuji oleh pilot aktual.
- Tidak ada network feature pada observation yang tersedia.
- Baseline membandingkan application placement dan cache behavior, DQN melakukan task-level offloading; jumlah titik keputusan tidak setara.
- Queue-aware audit yang ada merekam scoring saat pemilihan placement, sedangkan DQN feature state merekam queue per task. Nilai queue audit baseline nol di sini tidak membuktikan antrean tak ada.
- Reward scale dan normalisasi adalah nilai awal konfigurasi, tidak dituning atau disebut optimal.
- Checkpoint Java serialization tidak dijamin kompatibel lintas perubahan class/JVM.

## 14. Next Research Steps

Sebelum evaluasi performa lebih besar, buat desain baseline task-level yang mendapat decision opportunity identik dengan DQN, lalu jalankan lebih banyak episode/seeds serta workload dengan failure, queue pressure dan variasi network nyata. Tambahkan network observation hanya setelah sumbernya tersedia dan tervalidasi. Laporkan evaluasi frozen terpisah dari training; jangan tuning reward/λ dan membandingkan pada seed evaluasi yang sama.

## 15. Code References

- `experiment/src/com/mechalikh/pureedgesim/experiment/DqnMain.java`
- `experiment/src/com/mechalikh/pureedgesim/experiment/DqnOffloadingPolicy.java`
- `experiment/src/com/mechalikh/pureedgesim/experiment/DqnAgent.java`
- `experiment/src/com/mechalikh/pureedgesim/experiment/DqnQNetwork.java`
- `experiment/src/com/mechalikh/pureedgesim/experiment/DqnReplayBuffer.java`
- `experiment/src/com/mechalikh/pureedgesim/experiment/DqnStateEncoder.java`, `DqnState.java`, `OffloadingObservation.java`
- `experiment/src/com/mechalikh/pureedgesim/experiment/DelayedTransitionLedger.java`, `OffloadingTransition.java`
- `experiment/src/com/mechalikh/pureedgesim/experiment/DqnReadyOrchestrator.java`
- `experiment/src/com/mechalikh/pureedgesim/simulationmanager/DqnReadySimulationManager.java`
- `configs/dqn/training.properties`, `configs/dqn/evaluation.properties`
- `scripts/run_dqn_pilot.py`, `scripts/execute_run.py`, `run.sh`
- `tests/java/DqnImplementationSelfTest.java`, `scripts/test_dqn_foundation.sh`

### Reproduction commands

```bash
./scripts/test_dqn_foundation.sh
python3 scripts/run_dqn_pilot.py
```

Pilot runner creates a fresh timestamped experiment directory and refuses to overwrite an existing one. Raw outputs/checkpoint/CSVs/manifest are under `results/experiments/20261104T010929Z_dqn_pilot/`. For a direct frozen run after training, set `DQN_MODE=eval`, `DQN_CONFIG=<evaluation.properties>`, `DQN_CHECKPOINT=<checkpoint.bin>`, `PAPER_TASK_EVENT_TRACE=1`, and a fresh `RUNS_ROOT`, then run:

```bash
./run.sh --profile paper-aligned-baseline --method dqn --devices 10 --duration-seconds 5 --destination-config EDGE_DC_ONLY --seed 8128
```
