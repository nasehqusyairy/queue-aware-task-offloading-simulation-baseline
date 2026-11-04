# Audit Metodologi DQN untuk Task Offloading

## Ringkasan eksekutif

**Status keseluruhan — METHODOLGICAL RISK.** Kode menjalankan DQN secara komputasional dan reward terminal dikaitkan ke task asal, tetapi kontrak transisi saat ini belum cukup untuk disebut formulasi DQN standar yang tervalidasi secara metodologis.

Masalah intinya: `DelayedTransitionLedger.onDecision()` memakai observasi keputusan task berikutnya sebagai `next_state` bagi aksi task sebelumnya; reward yang dipasangkan justru outcome terminal task sebelumnya, yang baru tersedia beberapa event kemudian. Antara dua keputusan itu PureEdgeSim dapat menerima request dari beberapa task, mentransmisikan task, mengubah active/waiting queue, menyelesaikan task lain, dan memperbarui resource bersama. Dengan task yang overlap, reward dan state selanjutnya tidak membentuk transisi satu-langkah task-level yang jelas tanpa definisi lingkungan dan state yang lebih lengkap. Perilaku ini diverifikasi dari event call path, bukan hanya komentar implementasi.

Tidak ada perubahan kode atau hasil eksperimen dalam audit ini. Pilot final yang diperiksa adalah `results/experiments/20261104T010929Z_dqn_pilot/`. Hasilnya tidak mendukung klaim DQN superior: Trade-Off dan Queue-Aware masing-masing menjalankan satu keputusan placement untuk 64 task dari satu UE (64 task kemudian memakai EDC yang tersimpan); DQN menjalankan 64 keputusan task-level. Offered workload sama, kesempatan keputusan berbeda.

## 1. Siklus event simulator aktual

Urutan aktual untuk task yang berhasil di-offload:

```text
task generator menjadwalkan SEND_TO_ORCH
  → DefaultSimulationManager.sendTaskToOrchestrator()
  → network SEND_REQUEST_FROM_DEVICE_TO_ORCH (bila orchestrator remote)
  → SEND_TASK_FROM_ORCH_TO_DESTINATION
  → sendFromOrchToDestination(): policy menentukan destination / placement cache dipakai
  → task dikirim lewat network SEND_REQUEST_FROM_ORCH_TO_DESTINATION
  → EXECUTE_TASK di destination
  → DefaultComputingNode.submitTask(): mulai langsung jika core/RAM tersedia, atau masuk FIFO waiting queue
  → EXECUTION_FINISHED: resource dibebaskan, task FIFO berikutnya mulai
  → TRANSFER_RESULTS_TO_ORCH dan result-network transfer
  → RESULT_RETURN_FINISHED di UE/orchestrator, deadline diperiksa, tasksCount dinaikkan
  → PaperAlignedSimulationManager mencatat TASK_COMPLETED atau TASK_FAILED
```

Detail penting:

- Request ke orchestrator dijadwalkan di `DefaultSimulationManager.sendTaskToOrchestrator()`; ketika orchestrator remote, transfer jaringan selesai sebelum `SEND_TASK_FROM_ORCH_TO_DESTINATION` (`DefaultNetworkModel.sendRequestFromDeviceToOrch()` / `transferFinished()`). Jadi observasi DQN bukan di waktu task dibuat.
- Event `SEND_TASK_FROM_ORCH_TO_DESTINATION` memanggil `sendFromOrchToDestination()`. Bila placement belum ada, `edgeOrchestrator.orchestrate(task)` memanggil algoritma; bila sudah ada, simulator langsung memakai `applicationPlacementLocation` tanpa meminta algoritma. Orchestrator menulis `task.offloadingDestination` dan juga placement UE.
- DQN manager mengosongkan `isApplicationPlaced` pada setiap task sebelum memanggil implementasi dasar; karena itu DQN dipanggil tiap task. Ini bypass yang eksplisit dan khusus mode DQN.
- Pemilihan destination belum berarti task sudah masuk queue. Network request/container kemudian dapat tertunda; queue berubah ketika `EXECUTE_TASK` memanggil `submitTask()`. PureEdgeSim menjalankan task langsung bila core dan RAM cukup, selain itu menambahkannya ke `tasksQueue`.
- `EXECUTION_FINISHED` bukan task success. Node melepas resource lalu mengirim `TRANSFER_RESULTS_TO_ORCH`. Task terminal setelah hasil kembali (`RESULT_RETURN_FINISHED`) dan `taskFailed(task, 3)` memeriksa deadline dari total delay.
- Failure dapat terjadi di beberapa tahap: UE/orchestrator mati, destination mati, RAM/storage tidak cukup, mobility, deadline, dan tidak ada destination. `setFailed()` menghitung kegagalan terminal. Pending horizon bukan failure: manager menghitung `generated = completed + failed + pending`, menulis `TASK_PENDING_AT_HORIZON`, lalu menghentikan simulasi.

**Bukti kode:**

- `DefaultSimulationManager.processEvent()` memetakan `SEND_TO_ORCH`, `SEND_TASK_FROM_ORCH_TO_DESTINATION`, `EXECUTE_TASK`, `TRANSFER_RESULTS_TO_ORCH`, `RESULT_RETURN_FINISHED`: `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/simulationmanager/DefaultSimulationManager.java:171-203`.
- Pemilihan dan cache placement: file yang sama, `sendFromOrchToDestination()`, baris 294-320; placement disimpan oleh `Orchestrator.assignTaskToComputingNode()`, `.../taskorchestrator/Orchestrator.java:129-147`.
- Network dispatch: `DefaultNetworkModel.processEvent()` dan `sendRequestFromDeviceToOrch()` / `sendRequestFromOrchToDest()`: `.../network/DefaultNetworkModel.java:45-74, 165-175`.
- Queue, start execution dan FIFO release: `DefaultComputingNode.submitTask()`, `startExecution()`, `executionFinished()`: `.../datacentersmanager/DefaultComputingNode.java:222-269, 275-304`.
- Deadline/failure accounting: `DefaultSimulationManager.taskFailed()` dan `setFailed()`: file manager yang sama, baris 360-435.
- Terminal trace dan pending cutoff: `PaperAlignedSimulationManager.processEvent()` serta `recordTerminalIfCountChanged()`: `experiment/src/com/mechalikh/pureedgesim/simulationmanager/PaperAlignedSimulationManager.java:86-183, 286-297`.

## 2. Formulasi RL saat ini

Satu call `DqnReadyOrchestrator.findComputingNode()` membentuk `OffloadingObservation`, meminta aksi dari `OffloadingPolicy`, validasi mask, lalu menerapkan node terpilih. Unit aksi adalah destination EDC untuk task yang sedang diproses. Pengamatan termasuk queue state pada waktu keputusan, tetapi keputusan terjadi sebelum transfer request/task selesai.

Implementasi kemudian menyimpan `state/action` dengan task ID. Outcome terminal task tersebut menjadi reward. Ledger menetapkan `next_state` ke state keputusan *berikutnya menurut urutan event policy*, yang dapat berasal dari task ID lain. `terminal` pada transition hanya menjadi `true` untuk aksi eligible terakhir yang tidak mempunyai next decision saat horizon; completion/failure task sendiri hanya mengisi reward dan tidak menandai `done`.

Definisi ini campuran antara:

1. urutan keputusan dispatch secara global untuk state bootstrap;
2. reward terminal per-task untuk action terdahulu;
3. penghentian episode berbasis horizon.

Campuran tersebut bisa menjadi algoritma delayed-credit khusus jika didefinisikan eksplisit. Namun ia **belum diverifikasi sebagai transition MDP biasa** karena tidak jelas bahwa task reward merupakan reward interval dari `S_t` ke `S_{t+1}`, dan observasi tidak mencakup seluruh state outstanding yang membuat resource-sharing Markov.

## 3. Analisis alternatif transition semantics

| Formulasi | State transition dan reward | Overlap/out-of-order/horizon | Kesesuaian dan penilaian |
|---|---|---|---|
| **Urutan decision-event (implementasi sekarang)** | `S_t` adalah observasi untuk task yang sekarang diputuskan; `A_t` destination task itu; `S_{t+1}` observasi dispatch selanjutnya. Reward akhirnya adalah outcome task `t`, walau bisa datang setelah banyak keputusan lain. | Task boleh overlap; reward task-ID dapat datang out-of-order dan ledger menahannya sampai reward/state tersedia. Pending tidak punya reward/replay. | Sesuai DQN standar hanya jika satu langkah keputusan didefinisikan sebagai transisi environment yang berakhir pada keputusan berikut, reward task `t` memang reward untuk interval itu, dan state cukup Markov. Syarat reward interval tidak terpenuhi secara jelas: task belum tentu tiba di EDC, apalagi selesai, sebelum keputusan berikut. **METHODOLGICAL RISK.** |
| **Environment-event MDP** | State snapshot pada event simulator, mencakup seluruh tugas in-flight/queue/active; aksi destination hanya pada event keputusan, event lain merupakan evolusi tanpa aksi baru. Reward incremental dicatat ketika task selesai/gagal di interval event. | Overlap merupakan bagian state; out-of-order terminal outcomes menambah reward saat terjadi, tidak perlu dipasangkan ke state task lain. Horizon menjadi terminal/truncation eksplisit. | Dapat memakai DQN bila aksi/reward antar-event didefinisikan konsisten, tetapi event tanpa keputusan membuat timestep sangat tidak seragam dan state penuh mahal dikodekan. Jika memakai diskon waktu, perlu γ berbasis elapsed simulated time. **RECOMMENDED CHANGE** bila targetnya optimasi kinerja sistem global. |
| **Semi-Markov/task lifetime** | Aksi task `i` memulai opsi yang berakhir saat task `i` terminal; reward milik task itu; transition menuju state sesudah opsi berakhir. Diskon perlu mempertimbangkan durasi. | Opsi task concurrent, sehingga beberapa “next state setelah opsi” dapat saling menyilang; completion bisa out-of-order. State dan action lain tetap mengubah resource selama opsi berjalan. Pending di horizon adalah right-censoring, bukan terminal failure. | SMDP standar berasumsi aksi berjalan sampai next state sebelum aksi berikutnya; tidak cocok langsung karena simulator menerima keputusan baru sebelum task lama selesai. Perlu concurrent-options/centralized critic atau perlakuan event-driven yang lebih spesifik. **NOT VERIFIED** pada implementasi sekarang. |

### Rekomendasi formulasi

Untuk tahap selanjutnya pilih satu objective terlebih dahulu. Rekomendasi praktis:

1. **Sebelum klaim DQN temporal, mulai dengan delayed contextual bandit / one-step outcome learner**: simpan `(state_at_decision, action, task_id)` lalu regresikan Q terhadap reward terminal task yang sama tanpa `next_state` bootstrapping (`target = reward`). Ini paling transparan untuk “destination mana yang memberi outcome task terbaik”, namun perlu menyebut keterbatasan interference karena pilihan task lain berbagi queue.
2. Jika tujuan penelitian adalah kinerja jangka panjang sistem dengan antrean bersama, lanjutkan ke **decision-event MDP ber-state sistem**: decision epoch tiap dispatch; state memuat current task serta semua EDC queues, active residual service, request/container/results yang in-flight, resource dan task deadline/atribut yang relevan. Reward adalah akumulasi terminal outcome yang terjadi sejak decision sebelumnya, bukan reward task yang kebetulan terkait dengan action sebelumnya. Terapkan horizon dan discount dengan definisi waktu yang dinyatakan.
3. Hindari memakai completion per-task sebagai delayed reward sekaligus bootstrap ke task lain, kecuali desain formal menjelaskan kredit silang itu serta membuktikan asumsi Markov/semi-Markovnya.

Ini rekomendasi metodologis, bukan perubahan yang dibuat dalam audit ini.

## 4. Audit state representation

| Fitur | Sumber dan ketersediaan | Status / risiko |
|---|---|---|
| Task MI/length, input bits, deadline | Task saat `findComputingNode()` dipanggil (`getLength`, `getFileSizeInBits`, `getMaxLatency`). | **VERIFIED** tersedia sebelum aksi; tidak ada future completion data. |
| Waiting queue length | `QueueAwareComputingNode.getWaitingQueueLength()` → `getTasksQueue().size()`. | **VERIFIED** observasi langsung pada waktu pemilihan. Tidak memuat queue network/in-flight menuju EDC. |
| Active task count | `QueueAwareComputingNode.activeTasks`, ditambah/dihapus pada `startExecution`/`executionFinished`. | **VERIFIED** untuk running CPU jobs pada waktu pemilihan. |
| Estimated queue wait | `estimateQueueWaitSeconds()` memakai remaining active service dan panjang FIFO waiting queue dengan panjang task/MIPS/core. | **PARTIALLY VERIFIED** available pada waktu keputusan; ini estimator deterministik, bukan actual future waiting time. Tidak memuat task yang sudah dipilih tetapi masih ditransmisikan ke EDC. |
| CPU utilization | `node.getCurrentCpuUtilization()` pada saat observasi. | **VERIFIED** tersedia sebelum aksi. Persentase dinormalisasi dengan 100. |
| RAM/storage availability | `getAvailableRam()/getAvailableStorage()` dibanding `task.getContainerSizeInMBytes()`, disimpan sebagai boolean. | **PARTIALLY VERIFIED** informasi cukup untuk flag sederhana, tetapi rasio kapasitas/besar sisa resource tidak dibedakan dan berbeda failure lain dapat terjadi sesudah seleksi. |
| MIPS/core dan core count | Properti node pada observasi. | **VERIFIED**, tetapi nilai normalisasi adalah konstanta referensi, tidak di-clip atau di-fit dari data. |
| Missing values | Queue/active/estimate null; encoder menyimpan zero plus indikator missing untuk queue/active/wait. | **VERIFIED** untuk ketiga fitur tersebut. CPU/MIPS/cores tidak memiliki missing mask; nilai NaN/Inf akan menggagalkan Q check alih-alih merepresentasikan missing. |
| Network | Tidak ada RTT/bandwidth/path delay candidate pada `OffloadingObservation`. | **NOT VERIFIED / missing feature**. Network dapat mengubah task arrival, completion delay dan feasibility; geografi/path route juga tidak direpresentasikan. |
| Candidate identity | `candidateIds` menjaga mapping action→EDC, tetapi ID tidak masuk fitur network. | **METHODOLGICAL RISK** bila EDC setara pada queue/capacity tetapi beda network/location. Shared scorer memberi Q sama dan `>` tie break memilih kandidat eligible pertama. |
| System state / outstanding work | Tidak ada task list in-flight, per-UE pending requests, task attributes dari active/waiting jobs sebagai satu state, atau keputusan sebelumnya. | **METHODOLGICAL RISK** untuk asumsi Markov pada shared queue dengan concurrent tasks. Queue estimate merangkum workload, tetapi tidak membuktikan state aggregation sufficient. |

Normalisasi aktual membagi MI 30,000; input bits 160,000; deadline 300 s; queue/active count 100; estimated wait 300 s; MIPS/core 110,000; cores 10. Skala ini adalah konstanta code/config, bukan hasil statistik dari training. Nilai bisa jauh di atas 1 karena tidak di-clip. **RECOMMENDED CHANGE:** analisis distribusi fitur dan lakukan ablation/normalisasi berbasis data train saja sebelum eksperimen besar, tanpa mengintip test seeds.

**Bukti:** `DqnStateEncoder.encode(Task,...)` `experiment/src/com/mechalikh/pureedgesim/experiment/DqnStateEncoder.java:21-53`; pengubahan ke tensor fitur di file sama, baris 55-87; `OffloadingObservation.Candidate`, `.../OffloadingObservation.java:8-37`; queue tracker/estimator `.../QueueAwareComputingNode.java:19-80`.

## 5. Audit reward

Reward kode: untuk sukses `+completion_reward - c × totalDelaySeconds / delayReference`; untuk gagal `-failurePenalty - c × totalDelaySeconds / delayReference`. Pilot memakai `+1`, penalty `1`, `c=0.1`, reference `5 s`. Reward dihitung saat `TASK_COMPLETED`/`TASK_FAILED` callbacks dari lifecycle manager, dan `totalDelay` bersumber dari task aktual. Failure selalu bernilai lebih rendah dari success untuk delay yang sama; delay besar dapat membuat success reward negatif, tetapi tidak lebih buruk dari failure dengan delay sama.

Keterbatasan dan insentif:

- **Task difficulty bias:** MI/input/deadline menentukan state, tetapi reward delay tidak dinormalisasi per kelas task. Dengan beban heterogen, task panjang lebih mungkin mendapat penalty lebih besar walau destination tidak dapat menghindarinya; hal itu bisa mendorong policy memilih task mudah secara implisit jika exposure/arrival task berbeda.
- **Horizon censoring:** task pending tidak diberi reward dan tidak dimasukkan replay. Ini menghindari label failure palsu, tetapi transition yang outcome-nya belum ada menjadi missing/censored. Bila peluang pending bergantung pada queue/destination (sangat mungkin), mengabaikannya dapat bias training ke outcome yang selesai sebelum horizon.
- **No intermediate feedback:** queue wait/CPU/network tidak diberi reward saat terjadi; hanya total delay saat terminal. Karena itu feedback terlambat dan sulit dipisahkan dari keputusan task-task lain.
- **Energy excluded:** tepat untuk mencegah atribusi energi per-task yang tak tersedia, tetapi objective agent hanya completion/failure/delay; energi pilot bukan objective reward.

**Rekomendasi:** pertahankan terminal per-task reward bila menggunakan delayed contextual bandit; untuk system MDP gunakan reward incremental yang mencerminkan objective sistem pada event completion/failure, dengan horizon drain/censoring rule eksplisit. Jangan tuning koefisien sebelum distribusi reward dan trade-off objective ditentukan. `DqnOffloadingPolicy.terminalReward()` ada di `experiment/src/com/mechalikh/pureedgesim/experiment/DqnOffloadingPolicy.java:10`; callback/korelasi di `.../simulationmanager/DqnReadySimulationManager.java:103-116`.

## 6. Audit matematis DQN

| Bagian | Hasil pemeriksaan |
|---|---|
| Q(s,a) / candidate architecture | **VERIFIED (implementasi)**: shared MLP memetakan task context + global + candidate features menjadi satu skor Q per candidate; kandidat count variabel. Ini adalah valid parameterization Q(s,a) bila fitur kandidat/state cukup dan kandidat di-mask. Fitur EDC identity/path yang hilang tetap risiko aliasing. |
| Action masking | **VERIFIED (implementasi)**: ε-greedy memilih hanya eligible; validation orchestrator fail-closed; replay memeriksa aksi tersimpan; target max-Q melewati hanya action mask aktif. |
| Target | **VERIFIED (rumus kode)**: `y = r` bila `terminal`; selain itu `r + γ max_a Q_target(next_state,a)` untuk eligible actions. Jika next state tanpa eligible action, max dibiarkan non-finite dan bootstrap 0. Ini setara zero bootstrap tapi terminal flag tetap false; perlu tes eksplisit dan definisi no-action state. |
| Loss / gradients | **PARTIALLY VERIFIED**: MSE `error²` dan turunan `2 error / batch`; backprop ReLU kedua layer, bias/weights, output benar secara inspeksi aljabar. Belum ada finite-difference gradient check, jadi correctness numerik belum independen diverifikasi. |
| Adam | **PARTIALLY VERIFIED**: `β1=.9`, `β2=.999`, epsilon `1e-8`, bias correction memakai satu `optimizerStep` per batch dan state moment per parameter. Inspeksi konsisten; belum dibandingkan optimizer referensi pada toy batch. |
| Target sync | **VERIFIED (mekanisme)**: setiap `target_update_interval` optimizer updates, `copyWeightsFrom(online)`. Self-test memeriksa salinan online/target sama setelah sync. Interval dalam update, bukan simulator time/episode. |
| Replay sampling | **VERIFIED**: ring buffer capacity, sampling tanpa pengembalian dalam batch via shuffle. Tidak prioritized replay. Ledger mencegah duplicate emit, bukan replay buffer sendiri. |
| Epsilon/seed | **VERIFIED (mekanisme)**: linear decay global terhadap total policy decisions dan `Random` disimpan pada checkpoint. ε dicek sebelum counter increment; training action selection reproducible dari seed/checkpoint. Evaluation ε=0. |
| Checkpoint | **VERIFIED (pilot)**: online/target, Adam state di network, replay, RNG, counter, fingerprint diserialisasi; training save pakai temp + atomic move; eval required checkpoint dan tidak menulis ulang file. SHA pilot tidak berubah sebelum/sesudah eval. Java serialization bersifat version-sensitive. |
| Terminal/pending | **PARTIALLY VERIFIED**: terminal flag menghilangkan bootstrap; pending tidak mendapat fabricated reward/replay insertion. Namun semantics terminal adalah akhir urutan episode, bukan “task complete”. Pending hanya diuji unit test, bukan dalam pilot DQN. |

**Bukti:** `DqnQNetwork.qValues()/trainBatch()/copyWeightsFrom()/adam()` `experiment/src/com/mechalikh/pureedgesim/experiment/DqnQNetwork.java:31-88`; `DqnAgent.select()/observe()/epsilon()/save()` `.../DqnAgent.java:9-25`; `DqnReplayBuffer` `.../DqnReplayBuffer.java:3-8`; ledger `.../DelayedTransitionLedger.java:32-103`.

### Tes numerik tambahan yang diperlukan

1. Finite-difference gradient check per-layer untuk beberapa parameter dan batch kecil; toleransi ditetapkan sebelumnya, ReLU titik nondifferentiable dikecualikan.
2. Toy MDP deterministik dengan nilai Q optimum diketahui; pastikan online net belajar action terbaik dan target sync tidak menyebabkan update salah.
3. Target terminal vs nonterminal, next-state tanpa action eligible, serta masked maximum dengan nilai Q terbesar berada pada action masked.
4. Ring buffer overflow/wrap, serialisasi + restore RNG/replay/optimizer dan aksi berikutnya identik dibanding proses yang tidak restart.
5. Reward outcome order permutation dan same-timestamp completion/decision ordering sesuai event queue simulator.

Software self-tests lulus, tetapi mencakup 18 checks DQN buatan sendiri; tidak ada gradient check atau bukti konvergensi toy environment pada cakupan sekarang.

## 7. Audit validitas pilot dan fairness

Final pilot: 3 training episodes (seed 11, 29, 47), frozen evaluation seeds 8128 dan 4401; 10 UE yang dikonfigurasi, 4 EDC, target `EDGE_DC_ONLY`, 5 s. Per paired eval seed, Trade-Off, Queue-Aware, DQN menerima 64 task workload identik. Training DQN membuat 64 keputusan dan 64 transisi per episode; eval DQN membuat 64 keputusan. Trade-Off destination audit menunjukkan semua 64 task ke EDC ID 1; Queue-Aware juga 64 ke EDC ID 1 dan hanya 2 row kandidat di `queue_decisions.csv` (dua kandidat pada satu placement selection). DQN memutuskan per task dan memilih dua EDC: seed eval 8128: ID1=55, ID3=9; seed 4401: ID1=55, ID2=9. DQN selected/applied mismatches = 0. Ini menunjukkan cache/decision frequency **tidak setara**.

| Seed eval | Metode | Complete/64 | Failed | Pending | Success rate | Energy Wh | Mean total delay s | Mean actual wait s |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 8128 | Trade-Off | 59 | 0 | 5 | 92.19% | 0.8719 | 6.6559 | 1.1059 |
| 8128 | Queue-Aware | 59 | 0 | 5 | 92.19% | 0.8719 | 6.6559 | 1.1059 |
| 8128 | DQN | 64 | 0 | 0 | 100% | 0.8726 | 6.3131 | 0.7594 |
| 4401 | Trade-Off | 59 | 0 | 5 | 92.19% | 0.8719 | 6.6559 | 1.1059 |
| 4401 | Queue-Aware | 59 | 0 | 5 | 92.19% | 0.8719 | 6.6559 | 1.1059 |

Semua run berstatus completed; paired configuration manifest valid. Walau DQN di dua seed mencatat lebih banyak complete dan lebih rendah delay/wait, **jangan menyimpulkan superioritas**: hanya dua eval seed dan decision protocol berbeda. Kesamaan workload/config tidak memperbaiki bias karena DQN diberi 64 kesempatan rerouting task-level sementara baseline memilih placement lalu memakai cache. Queue-Aware pilot juga merekam queue estimate 0.0 pada scoring placement yang jarang; itu tidak sama dengan per-task queue state DQN.

**Fair comparison yang disarankan, tanpa mengganti baseline asli:** laporkan dua kelompok:

1. **Intended/default behavior:** Trade-Off dan Queue-Aware application placement/caching versus DQN task-level sebagai perbedaan arsitektur, dengan klaim terbatas sebagai end-to-end policy comparison.
2. **Decision-protocol controlled ablation:** tambahkan runner adapters terpisah `trade-off-per-task` dan `queue-aware-per-task`, dipanggil di event dan candidate mask yang sama dengan DQN, bypass cache per task, sambil mempertahankan formula scoring masing-masing. Ini tidak mengubah implementasi baseline default; ia mengisolasi scorer dengan jumlah keputusan, observasi, candidate set, seed dan destination application yang sama. Laporkan juga default baselines, jangan menggantikannya dengan ablation.

Raw evidence: `results/experiments/20261104T010929Z_dqn_pilot/evaluation_comparison.csv`, `manifest.json`, dan masing-masing `runs/<id>/raw/{destinations.csv,per_task_decisions.csv,queue_decisions.csv,dqn_transitions.csv,task_event_trace.csv}`.

## 8. Risiko metodologis teridentifikasi

1. **METHODOLGICAL RISK — transition credit/time mismatch:** task-specific terminal reward dipasangkan dengan next task state sebelum task asal selesai.
2. **METHODOLGICAL RISK — partial observability:** observation tidak memuat in-flight network requests/results, pending action/task set, seluruh state needed untuk mengembalikan sistem ke Markov.
3. **METHODOLGICAL RISK — horizon censoring:** pending outcomes hilang dari replay secara nonrandom bila queue/delay memengaruhi probabilitas selesai.
4. **METHODOLGICAL RISK — baseline decision opportunity confound:** 1 placement choice versus 64 task decisions pada pilot.
5. **PARTIALLY VERIFIED — action identity/network aliasing:** candidate ID tidak masuk Q features, network/path conditions missing; tie score memilih action eligible pertama.
6. **NOT VERIFIED — numeric gradients/toy convergence:** training loss finite pada tiga episode tidak membuktikan gradient benar menyeluruh atau convergence.
7. **NOT VERIFIED — performance/generalization:** hanya dua evaluation seeds, workload buatan satu UE, dan tidak ada failure DQN. Tidak ada klaim peningkatan.

## 9. Formulasi yang direkomendasikan

**RECOMMENDED CHANGE — jangan perluas matriks standard DQN dengan transition contract sekarang.** Pilih objective:

- Untuk keputusan tiap task dan reward yang benar-benar milik task tersebut, validasi dulu delayed contextual bandit tanpa bootstrap. Replay record menyertakan originating task ID; episode/horizon censoring dianalisis eksplisit. Sebutkan shared-queue interference sebagai batasan dan evaluasi dengan paired randomized seeds/workloads.
- Untuk optimasi total sistem dan future congestion externality, definisikan global decision-event MDP. Tambahkan observasi full/approximate sufficient system state atas active/waiting/in-flight workload di tiap EDC; setiap interval decision-to-decision mendapat accrued system reward, dengan simulated-time discount/truncation yang konsisten. Verifikasi Markov sufficiency melalui ablation/state perturbation dan trace replay.
- Jika tetap ingin per-task option/SMDP, buat formulasi concurrent actions eksplisit dan jangan gunakan asumsi satu action menyelesaikan sebelum action berikut. Perlu model yang menangani beberapa reward/option outstanding dan pengaruh silang queue.

## 10. Prioritized implementation plan

1. **P0 — tulis MDP/objective satu halaman:** unit decision, state snapshot, reward timing, discount unit (per decision atau simulated second), episode boundary, pending/truncation, sistem-level vs per-task utility.
2. **P1 — pilih dan implement transition ledger yang cocok:** contextual bandit tanpa next-state bootstrap, atau accrued reward antar decision epoch dengan state sistem. Hapus ambiguitas `terminal` task-vs-episode.
3. **P2 — cegah censoring bias:** jalankan drain phase setelah arrival cutoff atau define incomplete transition/truncation bootstrap; jangan masukkan fabricated failure. Laporkan pending per destination/arrival/decision-time.
4. **P3 — validasi numeric:** gradient finite difference, toy MDP, masked targets, ring buffer wrap, restart reproducibility.
5. **P4 — tambah per-task comparator wrappers untuk scorer Trade-Off dan Queue-Aware** tanpa menyentuh default/canonical methods; assert opportunity count/candidate masks equal dengan DQN.
6. **P5 — sebelum skala besar:** multiple training seeds/episodes dan held-out eval seeds/workloads, baseline paired run, checkpoint hash/pair config verification, confidence intervals; pisahkan validasi software dari performance study.

## 11. Tests yang dibutuhkan sebelum eksperimen besar

| Tes | Status sekarang | Kebutuhan |
|---|---|---|
| Task lifecycle event ordering / destination applied | **VERIFIED pada pilot** (64/64 DQN task decision match actual destination) | Tambah assertion network arrival dan exact decision timestamp/state freeze. |
| Async outcomes out of order, duplicate, pending no fabricated reward | **VERIFIED di unit ledger** | Tambah simulator integration dengan beberapa completions out of order dan task pending saat cutoff. |
| Target mask, target network synchronization, Q shape, epsilon, checkpoint/frozen eval | **VERIFIED sebagian di 18 DQN checks + pilot** | Tambahkan negative target mask, wrap-around replay, serialization full RNG continuation test. |
| Gradient correctness | **NOT VERIFIED** | Finite difference per-layer dan optimizer reference comparison. |
| Toy MDP convergence | **NOT VERIFIED** | Deterministic known-optimum task/queue environment. |
| Markov/state sufficiency dan reward interval semantics | **NOT VERIFIED** | State aliasing tests, event-sourced transition audit, formal contract test. |
| Equal baseline decision protocol | **NOT VERIFIED** | Per-task wrappers + automated equality checks; default behavior tetap sebagai pembanding terpisah. |
| Statistical DQN benefit | **NOT VERIFIED** | Tidak relevan sebelum formulation/fair comparison lulus; kemudian held-out multiple seeds and workloads. |

Tes yang dijalankan saat audit:

- `./scripts/test_dqn_foundation.sh` → `DqnActionSpaceSelfTest: 9 checks passed`, `DqnImplementationSelfTest: 18 checks passed`.
- `python3 -m pytest --import-mode=importlib -q` → `25 passed, 3 skipped, 6 subtests passed`.

## 12. Code and result references

- Decision/state/action: `experiment/src/com/mechalikh/pureedgesim/experiment/DqnReadyOrchestrator.java:28-53`.
- Cache bypass, per-task ledger input, terminal reward, horizon flush: `experiment/src/com/mechalikh/pureedgesim/simulationmanager/DqnReadySimulationManager.java:70-95, 103-135, 138-147, 247-255`.
- Transition contract and readiness: `experiment/src/com/mechalikh/pureedgesim/experiment/DelayedTransitionLedger.java:32-103`.
- State/feature source: `experiment/src/com/mechalikh/pureedgesim/experiment/DqnStateEncoder.java:21-87`; queue implementation: `.../QueueAwareComputingNode.java:37-80`.
- Reward: `experiment/src/com/mechalikh/pureedgesim/experiment/DqnOffloadingPolicy.java:10` and manager above.
- Q/target/backprop/Adam: `experiment/src/com/mechalikh/pureedgesim/experiment/DqnQNetwork.java:31-88`; policy/replay/epsilon/checkpoint: `.../DqnAgent.java:9-25`; replay: `.../DqnReplayBuffer.java:3-8`.
- Pilot report/config/results: `REPORT_DQN_IMPLEMENTATION.md`, `results/experiments/20261104T010929Z_dqn_pilot/manifest.json`, `training_metrics.csv`, `evaluation_comparison.csv`.

### Kesimpulan audit

Implementasi **menjalankan neural Q-learner dengan task-level actions dan delayed per-task rewards**, tetapi transisi bootstrap saat ini belum cocok secara jelas dengan dinamika concurrent/asynchronous PureEdgeSim. Status yang dapat dipertanggungjawabkan: **training/software pipeline VERIFIED; formulasi standard DQN NOT VERIFIED; metodologi eksperimen METHODOLGICAL RISK; tidak ada bukti superiority/convergence**. Rekomendasi berikutnya adalah menetapkan objective dan transition contract secara formal sebelum training lebih besar.
