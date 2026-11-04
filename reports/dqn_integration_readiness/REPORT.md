# Audit Kesiapan Integrasi DQN untuk Queue-Aware Task Offloading

**Repository:** `queue-aware-task-offloading-simulation-baseline`  
**Commit yang diaudit:** `4dff71514fdc01adf08eb902faa3cedb2941e8f2`  
**Status working tree saat audit:** bersih  
**Ruang lingkup:** audit source dan tes terpilih; tidak ada implementasi/training DQN dan tidak ada perubahan algoritma atau konfigurasi.

> Path dan nomor baris di bawah merujuk pada commit tersebut. `simulator/PureEdgeSim/PureEdgeSim` adalah source PureEdgeSim yang disertakan di repository.

## 1. Executive Summary

**Fakta kode:** PureEdgeSim telah menyediakan titik ekstensi `Simulation.setCustomEdgeOrchestrator(...)` dan abstraksi `Orchestrator.findComputingNode(...)`. Queue-Aware saat ini memilih kandidat di `QueueAwareTradeOffOrchestrator.findComputingNode`, tetapi pemanggilan keputusan dibatasi oleh cache placement per UE: `DefaultSimulationManager.sendFromOrchToDestination` memanggil orchestrator hanya jika `edgeDevice.isApplicationPlaced()` bernilai false; task sesudahnya diarahkan ke `applicationPlacementLocation` yang tersimpan.

**Interpretasi:** tanpa perubahan pada lifecycle/manager itu, mengganti rumus Queue-Aware dengan DQN hanya mengajarkan pemilihan **placement awal atau re-placement**, bukan keputusan tujuan untuk setiap task. Titik integrasi policy paling tepat adalah custom simulation manager pada gerbang tersebut, dengan keputusan per task yang tetap memakai mekanisme dispatch/network PureEdgeSim.

**Kesiapan:** hook scheduler memadai; observasi queue/CPU tersedia atau dapat dibentuk untuk EDC; loop training, replay buffer, target network, checkpoint, dan pemisahan train/evaluation belum ada di project. Eksperimen DQN belum siap dijalankan secara valid sampai cache placement dapat dilewati secara eksplisit, transisi multi-task asinkron didefinisikan, serta evaluasi dan model checkpoint ditambahkan.

**Bukti validasi:** `python3 -m pytest -q tests/test_paper_experiment.py tests/test_task_event_trace.py tests/test_analyze.py` lulus, 21 tests dan 6 subtests. Pemanggilan yang sama dengan `python` gagal karena executable `python` tidak tersedia; `python3` berhasil. Tidak ada simulasi atau training dijalankan.

## 2. Current Architecture

| Komponen | File dan method | Peran aktual |
|---|---|---|
| Entry point normal | `experiment/src/com/mechalikh/pureedgesim/experiment/PaperAlignedMain.java:9-20`, `main` | Membuat `Simulation`, mendaftarkan task generator, node generator, orchestrator kustom, simulation manager, lalu memanggil `launchSimulation()`. |
| Entry point Queue-Aware | `experiment/src/com/mechalikh/pureedgesim/experiment/QueueAwareMain.java:10-23`, `main` | Mendaftarkan `QueueAwareTradeOffOrchestrator`, node Queue-Aware dan manager audit. Ini saat ini policy heuristik, bukan learning agent. |
| Runner | `scripts/run_experiment.py:27-35, 117-128`; `scripts/execute_run.py:63-80, 213-242` | Matriks memilih method/profile/seed; runner membangun dan menjalankan satu run terisolasi. Queue-Aware memakai `QueueAwareMain`; seed diberikan melalui system property. |
| Orchestrator API | `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/taskorchestrator/Orchestrator.java:31-51, 127-149` | `orchestrate(task)` memanggil `assignTaskToComputingNode`, lalu `findComputingNode`; destination ditulis ke task dan placement UE. |
| Baseline Trade-Off | `.../taskorchestrator/DefaultOrchestrator.java:42-88` | `findComputingNode` merutekan ke `tradeOff`; skor menggunakan history, panjang task, tipe node dan MIPS/core; kandidat pertama dengan minimum menang. |
| Queue-Aware | `experiment/src/com/mechalikh/pureedgesim/experiment/QueueAwareTradeOffOrchestrator.java:46-100` | Mengiterasi kandidat layak, menghitung skor Trade-Off dan queue wait, menggabungkan penalty, memilih first minimum, menulis queue audit dan mengembalikan indeks. |
| Penerapan destination | `.../taskorchestrator/Orchestrator.java:129-149`; `.../simulationmanager/DefaultSimulationManager.java:294-321` | `task.setOffloadingDestination(node)`; kemudian manager/network mengirim task ke destination yang terpilih. |
| Seleksi kandidat terjangkau | `experiment/src/com/mechalikh/pureedgesim/experiment/PaperAlignedOrchestrator.java:21-49` | Menyaring kandidat berdasarkan layer target, node hidup/non-sensor serta reachability/geometric radius untuk EDC. |

### Alur keputusan aktual

```text
task generator -> NEXT_BATCH / SEND_TO_ORCH
 -> DefaultSimulationManager.sendTaskToOrchestrator
 -> request jaringan UE -> orchestrator
 -> DefaultSimulationManager.sendFromOrchToDestination
      -> jika UE belum applicationPlaced: edgeOrchestrator.orchestrate(task)
         -> findComputingNode(...) -> task.destination + UE placement location
      -> jika sudah placed: destination = cached UE.applicationPlacementLocation
 -> NetworkModel kirim task/container -> EXECUTE_TASK -> destination.submitTask
 -> task execution -> transfer result -> deadline check -> terminal success/failure
```

Urutan ini berasal dari `DefaultSimulationManager.processEvent` (`:158-203`), `sendTaskToOrchestrator` (`:329-338`), `sendFromOrchToDestination` (`:294-321`), `Orchestrator.orchestrate/assignTaskToComputingNode` (`:49-51,129-149`), `DefaultNetworkModel.sendRequestFromOrchToDest/addContainer` (`:128-163`) dan event execution/completion manager.

## 3. Scheduler Decision Flow

### PureEdgeSim baseline Trade-Off

`DefaultOrchestrator.findComputingNode` memutuskan antara Round Robin dan Trade-Off menurut `algorithmName` (`DefaultOrchestrator.java:42-51`). `tradeOff` menilai seluruh kandidat yang lolos `offloadingIsPossible`, dengan:

`score = (historyMap[i] + 1) × typeWeight × taskLengthMI / mipsPerCore`

Bobot tipe: Cloud 1.8, Edge DC 1.2, Edge Device 1.3. History kandidat terpilih ditambah satu (`DefaultOrchestrator.java:53-87`). Queue-Aware mengimplementasikan skor ekuivalen sebagai `QueueAwareScoring.tradeOffBaseScore` (`experiment/.../QueueAwareScoring.java:39-50`).

### Queue-Aware sekarang

`QueueAwareTradeOffOrchestrator.findComputingNode` mengambil `task.getLength()`, tipe/MIPS, dan queue estimator tiap kandidat (`:53-74`); menghitung `baseline + λ × estimatedQueueWait` (`:70`), menentukan ranking/winner baseline dan gabungan (`:76-84`), lalu mengaudit kandidat (`:86-100`). Tie menggunakan urutan node yang stabil (`QueueAwareScoring.java:69-80`). Kelas ini adalah contoh integrasi policy pada hook orchestrator yang sesuai, tetapi tidak mengatasi cache placement manager.

## 4. Placement Cache and Decision Reuse Audit

**Fakta:** `DefaultSimulationManager.sendFromOrchToDestination` membuat keputusan hanya pada cabang `!task.getEdgeDevice().isApplicationPlaced()` (`DefaultSimulationManager.java:298-311`). Keputusan scheduler menetapkan `applicationPlacementLocation` dan menandai UE placed (`Orchestrator.java:141-145`; setter aktual di `DefaultComputingNode.java:308-311` dan `LocationAwareNode.java:106-115`). Cabang selanjutnya memakai lokasi tersebut secara langsung (`DefaultSimulationManager.java:312-316`).

**Invalidasi/re-placement:** `DefaultSimulationManager.setFailed` mengeset `applicationPlaced(false)` agar task mendatang mencari destination lagi (`DefaultSimulationManager.java:419-430`); kontrak `ComputingNode.setApplicationPlaced` juga menyebut invalidasi saat device berpindah dari placement (`ComputingNode.java:283-302`). Jejak audit manager lokal merekam `placementWasCached` dan mengklasifikasikan pemilihan/cached reuse (`experiment/.../PaperAlignedSimulationManager.java:109-120`).

**Implikasi DQN:** pada alur default, DQN di hook orchestrator **tidak dipanggil untuk setiap task**. Ia hanya dipanggil pada keputusan placement pertama atau setelah invalidasi. Selain itu, task berikutnya mengabaikan state queue yang berubah karena destination sudah ditetapkan. Agar evaluasi benar-benar task-level, pilihan harus dihitung ulang pada dispatch setiap task, atau cache harus diubah menjadi mode eksplisit `per-task` versus `per-UE placement`. Jangan sekadar mengganti heuristik di `findComputingNode` lalu menyebutnya task offloading.

**Titik penerapan yang direkomendasikan:** subclass `PaperAlignedSimulationManager` dan override gerbang `sendFromOrchToDestination` (method induk protected). Pada mode DQN task-level, panggil policy untuk tiap task sambil mempertahankan pemeriksaan failure, network events, pengiriman container, dan accounting baseline. Pertahankan manager/orchestrator lama untuk metode baseline; jangan ubah perilaku Trade-Off/Queue-Aware. Tambahkan assertion/decision audit yang membuktikan satu keputusan per task yang eligible.

## 5. State Feature Availability

Klasifikasi untuk observasi **pada waktu keputusan**. “Tersedia langsung” berarti dapat dibaca dari task/node saat policy dipanggil, tidak berarti sudah dinormalisasi atau dikemas sebagai vektor.

| Kandidat fitur | Status | Bukti / batasan |
|---|---|---|
| Task workload / jumlah MI | Tersedia langsung | `Task.getLength()` (`Task.java:288-295`); generator menetapkan panjang dari application profile (`PaperAlignedTaskGenerator.java:109-115`). |
| Request/task input size | Tersedia langsung | `Task.getFileSizeInBits()` dan setter (`Task.java:270-302`). Input, output dan container adalah ukuran berbeda; unit perlu distandardisasi. |
| Deadline | Tersedia langsung | `Task.getMaxLatency()` (`Task.java:54-66`); generator mengisi dari latency aplikasi (`PaperAlignedTaskGenerator.java:109-115`). Deadline adalah end-to-end latency limit, bukan countdown sisa deadline yang saat ini disimpan eksplisit. Sisa waktu dapat dihitung jika timestamp kedatangan dan waktu sim sudah terdefinisi konsisten. |
| Queue length per EDC | Tersedia langsung pada Queue-Aware node | `QueueAwareComputingNode.getWaitingQueueLength()` (`:74-76`) menggunakan `DefaultComputingNode.getTasksQueue()`; node default menyediakan queue (`ComputingNode.java:430-437`). Pada node normal, queue length juga dapat dibaca via interface. |
| Active task count | Perlu instrumentasi/subclass | PureEdgeSim mengelola `availableCores` dan CPU utilization, tetapi tidak menyediakan daftar/count aktif umum. `QueueAwareComputingNode` melacak active task dalam map melalui `startExecution`/`executionFinished` (`:30-48,78-80`). Jangan mengasumsikan map Queue-Aware tersedia di node baseline. |
| Estimasi queue waiting time | Tersedia melalui extension | `QueueWorkloadView.estimateQueueWaitSeconds()` dan implementasi `QueueAwareComputingNode.java:51-71`. Ini estimasi service time berbasis active remaining, FIFO waiting, core dan MIPS, bukan ukuran langsung dari simulator. Nilai `OptionalDouble.empty()` harus diperlakukan sebagai missing. |
| CPU capacity / MIPS / cores | Tersedia langsung | `ComputingNode.getNumberOfCPUCores()` (`ComputingNode.java:304-326`), node `getMipsPerCore()` (implementasi `DefaultComputingNode.java:271`), total capacity API pada interface. |
| CPU utilization | Tersedia langsung, semantik perlu dipilih | `getCurrentCpuUtilization()` dan `getAvgCpuUtilization()` (`DefaultComputingNode.java:103-117`). Current memakai task MI aktif dibanding kapasitas; average memakai total MI sepanjang waktu simulasi. Perbedaan ini penting untuk state DQN. |
| Network latency / bandwidth | Dapat dihitung dari objek link/path | `NetworkLink` memiliki latency dan bandwidth (`NetworkLink.java:38-45,69-80`); `DefaultNetworkModel.send` membangun jalur dan simulasi transfer (`:75-126`). State harus menghitung path dari UE/orchestrator ke setiap EDC dan memperhitungkan congestion/transfer aktual bila itu sasaran. Path latency statis saja bukan observed task delay. |
| Failure / resource availability | Sebagian tersedia langsung | `ComputingNode.isDead`, `getAvailableRam`, `getAvailableStorage` dan available cores APIs; task failure enum/status (`Task.java:41-50,240-252,312-326`). Eligibility saat keputusan saat ini mengeluarkan dead node pada `PaperAlignedOrchestrator.java:22-31`; untuk masking action, sediakan himpunan eligible explicit. |
| Task state/reward terminal | Tersedia saat terminal event | `Task.Status`, `FailureReason`, delay dan waiting time tersedia melalui task. `DefaultSimulationManager.taskFailed` memutuskan kematian/resource/mobility/deadline (`:360-410`); status sukses/failed perlu dibaca setelah callback/failure handling. |

**Batas state:** seluruh kandidat EDC tidak selalu valid untuk setiap UE. `PaperAlignedOrchestrator.offloadingIsPossible` memberikan filter untuk architecture, reachability, node mati dan sensor (`:21-32,40-49`). State perlu action mask eksplisit agar jaringan/arsitektur tidak dilanggar.

## 6. Action Space Design

Pada konfigurasi saat ini, EDC berjumlah empat menurut konfigurasi eksperimen, tetapi action space tidak boleh mengasumsikan empat tujuan permanen. `Orchestrator.edgeOnly()` memuat node list Edge DC dari generator (`Orchestrator.java:103-109`); jumlahnya berasal dari deployment/configuration dan dapat berubah antarskenario. Destination diwakili `ComputingNode` object; orchestrator mengembalikan **index** ke `nodeList`, lalu `assignTaskToComputingNode` memakai index tersebut (`Orchestrator.java:127-149`).

**Rekomendasi awal:** action = index dari daftar EDC stabil berdasarkan ID; simpan `action_index -> node_id` di manifest. Mask action yang dead, unreachable, tidak diizinkan architecture, atau tidak mempunyai resource sesuai kebijakan. Jika semua action termask, jalankan kebijakan fallback yang tercatat (mis. task failure/no eligible destination), jangan memilih node invalid. Verifikasi bahwa `setOffloadingDestination(node)` yang sudah ada dapat menerima hasil pemilihan langsung.

Action space fixed berukuran 4 cocok hanya untuk eksperimen empat EDC dengan topologi/ordering terkunci. Untuk topologi dinamis, implementasi DQN fixed-output memerlukan action ID konsisten, padding/masking dan jumlah maksimum yang terdokumentasi; DQN vanilla tidak otomatis mendukung jumlah tujuan berubah-ubah.

## 7. Reward Design

**Reward awal yang disarankan bersifat per task dan berbasis metrik yang sudah tersedia:** reward terminal setelah task dinyatakan sukses/gagal; penalti kegagalan, dan biaya delay/energi yang dinormalisasi oleh rentang baseline. Contoh bentuk tanpa menetapkan bobot:

`r_task = +R_success × 1[success] − R_failure × 1[failure] − w_delay × normalized_total_delay − w_energy × normalized_task_energy`

Queue waiting time sudah termasuk komponen waiting delay, sehingga menguranginya lagi sebagai term reward terpisah dapat menghitung dua kali kecuali memang tujuan penelitian memprioritaskan waiting time. Bobot `R_success`, `R_failure`, `w_delay`, `w_energy`, skala normalisasi, serta apakah reward harus memasukkan hanya computing energy atau juga energi jaringan **belum ditentukan** dan perlu dipratentukan/analisis sensitivitas; tidak dituning pada set evaluasi.

**Waktu pemberian:** task terminal terjadi setelah task dieksekusi dan hasil dikembalikan; deadline check `phase == 3` memakai `task.getTotalDelay()` (`DefaultSimulationManager.java:396-408`). Total delay terdefinisi sebagai actual network time + waiting time + actual CPU time (`TaskAbstract.java:197-207`). Energi task khusus belum tampak tersedia sebagai atribut task di interface; log/model energi mencatat konsumsi per node, sehingga atribusi per task perlu dipastikan atau reward dibatasi pada metric energi per run/node dengan rancangan delayed reward. Jangan mengklaim reward energi per task sebelum atribusinya valid.

**Masalah RL asinkron:** banyak task dapat overlap. Setiap action perlu direkam dengan task ID, state/action serta terminal outcome task tersebut. Transition tidak boleh dipasangkan ke terminal task yang salah. Definisi `next_state` untuk lingkungan global asynchronous perlu ditetapkan (mis. state ketika keputusan task berikutnya diambil); penanganan task pending di akhir episode juga harus eksplisit. Jika target reward dihitung per terminal event, tidak otomatis menjadi transisi satu langkah DQN standar tanpa aturan next-state dan horizon yang jelas.

## 8. DQN Training Readiness

| Kapabilitas | Status sekarang | Bukti / konsekuensi |
|---|---|---|
| Episode simulasi | Partial | Satu panggilan `Simulation.launchSimulation()` meluncurkan skenario (`Simulation.java:139+`). Belum ada konsep episode RL atau callback reset agent. |
| Reset simulator | Partial, proses baru | Runner membangun run baru dan menjalankan entry point Java per run (`scripts/execute_run.py:213-242`). `Simulation` menginisialisasi skenario internal; API reset simulator yang dapat dipanggil berulang dalam proses tidak teridentifikasi. Untuk versi awal, satu episode per proses JVM lebih aman. |
| Seed terkendali | Ada untuk eksperimen terkait | `execute_run.py` mengirim `-Dpaper.seed=...` (`:221`); generator/mobility custom memakai seed. Semantik RNG untuk setiap stochastic component perlu tetap diaudit saat train/eval. |
| State-action-reward-next-state | Belum ada sebagai RL transition | Audit queue/destination mencatat keputusan, tetapi tidak ada replay transition/reward ledger. Task ID dan task event trace dapat menjadi dasar correlating terminal outcome, bukan replay buffer yang sudah tersedia. |
| Replay buffer | Tidak ditemukan | Tidak ada implementasi atau dependency RL yang terdeteksi. |
| Target network / optimizer / epsilon schedule | Tidak ditemukan | Belum ada learning loop. |
| Checkpoint model | Tidak ditemukan | Tambahkan format model, metadata state/action schema, λ/config, seed/training run dan versi commit. |
| Train/evaluation separation | Tidak ditemukan | Runner saat ini menjalankan paired benchmark, bukan fase training lalu holdout evaluation. Buat protokol terpisah agar evaluasi tidak mengupdate bobot. |
| Dependency ML | Tidak ditemukan di Maven | `simulator/PureEdgeSim/pom.xml:367-399` mendeklarasikan JGraphT, XChart, JUnit, KDTree, Mockito dan jFuzzyLogic; bukan framework DQN. Tidak ada dependency TensorFlow/PyTorch/ND4J terdeteksi di source/POM. |

Project utamanya Java. Implementasi DQN dapat memakai Java library yang dipilih kemudian atau service Python lokal, tetapi pilihan itu menambah dependency/proses dan overhead. Untuk eksperimen ini, mula-mula lebih sederhana menetapkan framework/library Java atau Python, version pinning, determinisme, dan protocol komunikasi. Jika inference dilakukan melalui Python subprocess setiap task, latency host execution bukan waktu simulated clock, namun overhead dinding dan reliabilitas inter-process tetap harus diukur.

## 9. Proposed Integration Architecture

1. Tambahkan `DqnTaskOffloadingOrchestrator extends PaperAlignedOrchestrator`; `findComputingNode` membangun fitur task + kandidat EDC, membentuk action mask, meminta action pada `DqnAgent`, mencatat state/action dan mengembalikan index.
2. Tambahkan `DqnTaskOffloadingSimulationManager extends PaperAlignedSimulationManager`; pada gerbang dispatch, aktifkan mode per-task sehingga policy dipanggil untuk setiap task eligible. Pertahankan pengiriman jaringan, container, failure checks, dan manager audit. Jangan gunakan placement cache lama pada mode DQN per-task; tegaskan semantik ini dengan flag/tes dan event audit.
3. Tambahkan `DqnAgent` interface terpisah (act, observe, endEpisode, save/load) agar policy dapat diuji dengan deterministic stub tanpa framework ML. Pisahkan `DqnTrainingController` dari evaluator.
4. Tambahkan terminal listener/ledger keyed by task ID; rekam generated, decision, assigned destination, start, completion/failure reason, reward, pending-at-horizon. Pastikan completed, failed, pending accounting eksklusif dan menyusun generated total.
5. Definisikan state schema dengan normalisasi yang disimpan; action mapping/masking deterministic; reward scale; next-state semantics asynchronous; horizon/drain policy.
6. Training: satu fresh simulation process per episode, episode seed dari jadwal reproduktif, epsilon-greedy, replay buffer, target network/update schedule dan checkpoint. Evaluasi: load checkpoint read-only, fixed held-out seeds, bandingkan Trade-Off/Queue-Aware pada workload/config berpasangan, tidak belajar selama evaluation.
7. Pertahankan entry point dan konfigurasi metode lama tanpa perubahan. Metode DQN menjadi method baru dengan manifest mencatat commit, model checkpoint hash, hyperparameter, feature schema, action map, train seeds dan evaluation seeds.

## 10. Files to Add or Modify

**Diusulkan, belum dibuat:**

| File/modul | Tujuan |
|---|---|
| `experiment/.../DqnTaskOffloadingOrchestrator.java` | Menyediakan state/action policy khusus DQN dan menerapkan action destination melalui API orchestrator. |
| `experiment/.../DqnTaskOffloadingSimulationManager.java` | Memasukkan ulang keputusan per task ke lifecycle tanpa cache placement; mempertahankan failure/accounting/network flow. |
| `experiment/.../DqnAgent.java`, `DqnTransition.java`, `DqnReplayBuffer.java` | Abstraksi agent, pengalaman keyed task dan replay. Bisa dipisahkan menurut pilihan ML framework. |
| `experiment/.../DqnTrainingController.java` | Episode, epsilon schedule, optimizer/target network dan checkpoint. |
| `experiment/.../DqnStateEncoder.java`, `DqnRewardPolicy.java` | Schema fitur/masking/reward yang teruji dan versioned. |
| `experiment/.../DqnMain.java` | Entry point baru; baseline mains tetap utuh. |
| `scripts/run_dqn_training.py` (atau runner Java) | Menjalankan episode terisolasi, seed schedule, resume/checkpoint dan manifest training. |
| `scripts/evaluate_dqn.py` / konfigurasi baru | Evaluasi frozen checkpoint yang paired dengan baseline. |
| `tests/...` Java/Python | Uji feature/action mask, force-per-task decision, transition terminal correlation, pending accounting, deterministic tie/mapping, dan baseline equivalence. |

File manager perlu perubahan untuk mem-bypass cache hanya pada method DQN. Jangan modifikasi `DefaultOrchestrator.tradeOff` atau `QueueAwareTradeOffOrchestrator` untuk menambahkan DQN.

## 11. Risks and Mitigations

| Risiko | Mitigasi |
|---|---|
| Placement cache membuat DQN tampak per-task padahal action hanya placement awal | Mode per-task eksplisit di manager; cocokkan jumlah decision per eligible task; audit `cache_used=false`. |
| Reward asynchronous tertaut ke task yang keliru | Ledger task ID immutable; terminal callback mengambil action record task yang sama; uji completion out-of-order dan task pending. |
| Future queue state dan failure horizon bias | Nyatakan drain policy; pending bukan failure reward kecuali aturan eksplisit; hitung horizon cutoff dan episodes konsisten. |
| Action memilih EDC tidak terjangkau atau mati | Gunakan candidate filter sama dengan orchestrator dan action mask; simpan candidate IDs pada audit. |
| State mengandung estimasi atau skala berubah ant-run | Versioned encoder dan normalisasi dari data train/config saja; tandai estimated queue wait terpisah dari observed queue. |
| Leakage dari evaluasi | Pisahkan seeds dan checkpoint; evaluator tidak memanggil `learn/update`; hash model dan config pada manifest. |
| Network/energy reward salah atribusi | Mulai dari metrik task yang benar-benar tersedia; jangan alokasikan node energy agregat per task tanpa model valid. |
| Variasi/seed tidak sepenuhnya terkendali | Satu JVM fresh per episode; catat seed seluruh RNG, profile, simulator config dan git SHA; cek determinisme baseline. |
| Training overfit atau pembandingan tidak adil | Freeze protokol, held-out paired seeds dan beberapa seed training; laporkan learning curve, bukan hanya checkpoint terbaik. |

## 12. Recommended Next Implementation Steps

1. **Sebelum DQN coding**, buat perubahan kecil terisolasi yang menambahkan mode `decision_scope=per_task` pada manager, tanpa ubah baseline policy; test bahwa orchestrator dipanggil sekali per task eligible dan destination dapat berubah ketika queue state berubah.
2. Tambahkan audit terminal task-ID yang exhaustive: generated = completed + failed + pending; failure reason, destination, decision count, terminal timestamp/reward available. Pending-at-horizon jangan diperlakukan sebagai failed.
3. Putuskan state schema dan action mask; ukur korelasi queue estimator dengan queue/actual waiting yang tersedia. Pin normalisasi dan unit.
4. Buat deterministic `DqnAgent` stub (selalu memilih action tertentu) untuk verifikasi end-to-end keputusan diterapkan ke `task.getOffloadingDestination()` per task sebelum menghubungkan framework ML.
5. Tetapkan MDP transition untuk banyak task asynchronous, terminal/pending policy, reward/weight/normalization melalui eksperimen train/validation yang dipisahkan.
6. Baru implementasikan DQN training/checkpoint dan jalankan smoke pilot kecil; validasi trace, accounting, reproducibility dan no-learning evaluation.
7. Jalankan benchmark holdout yang paired: Trade-Off, Queue-Aware dan frozen DQN dengan konfigurasi/workload/seed sama; laporkan mean/CI dan keterbatasan sampel.

## 13. Evidence and Code References

Daftar sumber yang ditelusuri (path relatif repository):

- `experiment/src/com/mechalikh/pureedgesim/experiment/PaperAlignedMain.java` — `main`, model registration.
- `experiment/src/com/mechalikh/pureedgesim/experiment/QueueAwareMain.java` — `main`, setup Queue-Aware.
- `experiment/src/com/mechalikh/pureedgesim/experiment/PaperAlignedOrchestrator.java` — `find` eligibility via `offloadingIsPossible`, reachability.
- `experiment/src/com/mechalikh/pureedgesim/experiment/QueueAwareTradeOffOrchestrator.java` — `findComputingNode`, score, rank, audit.
- `experiment/src/com/mechalikh/pureedgesim/experiment/QueueAwareScoring.java` — `tradeOffBaseScore`, `combinedScore`, `firstMinimum`, estimator helper.
- `experiment/src/com/mechalikh/pureedgesim/experiment/QueueAwareComputingNode.java` — active/waiting queue instrumentation and estimated waiting.
- `experiment/src/com/mechalikh/pureedgesim/experiment/PaperAlignedTaskGenerator.java` — task fields and generation.
- `experiment/src/com/mechalikh/pureedgesim/simulationmanager/PaperAlignedSimulationManager.java` — decision, cache-use, destination and event trace audit.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/taskorchestrator/Orchestrator.java` — architecture candidate lists, `orchestrate`, `assignTaskToComputingNode`.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/taskorchestrator/DefaultOrchestrator.java` — baseline `tradeOff`, history map and selection.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/simulationmanager/DefaultSimulationManager.java` — lifecycle events, placement cache, network dispatch, task failure phases and deadlines.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/datacentersmanager/DefaultComputingNode.java` — `submitTask`, queueing, `startExecution`, execution completion, CPU utilization.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/datacentersmanager/ComputingNode.java` and `LocationAwareNode.java` — node API: queue, capacity, utilization and application placement.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/taskgenerator/Task.java`, `TaskAbstract.java` — task fields/status/failure reason and delay semantics.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/network/DefaultNetworkModel.java`, `NetworkLink.java` — transfer lifecycle, path, link properties.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/simulationmanager/Simulation.java` — custom model hooks and launch entry.
- `scripts/run_experiment.py`, `scripts/execute_run.py` — experiment matrix, per-run process, seed property and Java main selection.
- `simulator/PureEdgeSim/pom.xml` — current Maven dependency declarations.

**Pemeriksaan yang dijalankan:**

```text
python -m pytest -q tests/test_paper_experiment.py tests/test_task_event_trace.py tests/test_analyze.py
  -> gagal sebelum tes: /bin/bash: python: command not found

python3 -m pytest -q tests/test_paper_experiment.py tests/test_task_event_trace.py tests/test_analyze.py
  -> 21 passed, 6 subtests passed
```

Tes tersebut menguji helper konfigurasi/analisis/trace dan bukan validasi integrasi DQN. Tidak ada source, konfigurasi, hasil eksperimen, atau checkpoint baseline yang diubah. Working tree awal bersih; laporan ini adalah satu-satunya artefak yang ditambahkan oleh audit ini.

### Pertanyaan yang belum terjawab

1. Apakah formulasi tujuan utama adalah reward per-task (delay/failure) atau objective run-level termasuk energi agregat?
2. Bagaimana tepatnya next state ditentukan ketika task masuk dan selesai secara asynchronous: state pada arrival task berikutnya, atau state global saat completion?
3. Apakah episode berakhir pada simulation horizon atau menunggu drain seluruh task, dan bagaimana pending task diberi treatment?
4. Library DQN dan tempat training yang disetujui (Java in-process atau Python) belum dipilih.
5. Apakah energy model bisa mengatribusi energi computing/network ke task tertentu secara valid, atau objective energi hanya akan dibandingkan agregat per run?
6. Jumlah EDC/action maksimum untuk generalisasi deployment belum ditentukan; konfigurasi empat EDC saat ini bukan bukti action space selalu empat.
