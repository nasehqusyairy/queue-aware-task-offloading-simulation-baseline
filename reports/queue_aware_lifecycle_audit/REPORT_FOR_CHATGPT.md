# Audit Lifecycle Kegagalan Task dan Siklus Keputusan Orchestrator

Tanggal audit: 3 November 2026. Cakupan: pemeriksaan kode dan hasil yang sudah tersedia; tidak ada simulasi ulang.

## Ringkasan eksekutif

Pada commit `03acb8635144a99b147b3d9e97017052cfaf4978`, success rate rendah terutama karena **deadline/latency failure**, bukan queue overflow, resource rejection, mobility, atau device death. Di semua 9 run matriks seed 1, seluruh terminal failure tercatat sebagai `Tasks failed (delay)`. Counter resource/long-wait, device dead, mobility, task tidak tergenerate karena device mati, dan pre-pipeline rejection semuanya nol. Accounting generated = completed + failed + pending valid.

Low workload pun hanya menyelesaikan 2.994 dari 29.000 task (10,324%). Low memakai rasio offered-load nominal 0,575 dan CPU usage EDC agregat tercatat 57,467%, sementara 25.977 task gagal karena delay. Konfigurasi aplikasi menetapkan deadline 0,02 s untuk Hard real-time dan 0,5 s untuk Soft real-time, dengan orchestrator di Cloud serta WAN latency 0,06 s. Karena `getTotalDelay()` memasukkan network + queue waiting + CPU, ketatnya deadline (terutama 20 ms yang lebih kecil dari satu WAN hop) merupakan penjelasan kode/konfigurasi yang kuat. Namun file hasil tidak menghubungkan failure ID ke tipe aplikasi, jadi pembagian tepat berdasarkan aplikasi atau komponen network/queue/CPU tidak dapat dibuktikan.

Queue-Aware saat ini lebih akurat disebut **Queue-Aware Application Placement/Re-placement**. PureEdgeSim memanggil orchestrator hanya ketika aplikasi UE belum ditempatkan. Setelah placement, task berikutnya memakai destination tersimpan; Queue-Aware tidak membuat keputusan baru untuk setiap task. Log matriks mencatat hanya 1.005 / 29.000, 2.017 / 58.000, dan 2.385 / 87.000 keputusan Queue-Aware yang mempunyai estimate (2,7–3,5%).

## Repository dan bukti yang diperiksa

- Branch: `main`.
- Commit SHA: `03acb8635144a99b147b3d9e97017052cfaf4978`.
- Saat audit dimulai, source tree tidak memiliki perubahan terlacak; terdapat direktori `reports/` tidak terlacak dari audit sebelumnya. Audit ini menambahkan file laporan dan bukti hanya di `reports/queue_aware_lifecycle_audit/`.
- Matriks yang dipakai: 9 run `EDGE_DC_ONLY`, 200 detik, seed 1, λ=1,0, masing-masing Trade-Off/Round Robin/Queue-Aware pada 10/20/30 UE. Data berasal dari `reports/queue_aware_audit_20261103T154150Z/evidence/runs/` dan telah disalin ke folder bukti laporan ini.
- Smoke/pasangan low seed 8128 juga tersedia di audit sebelumnya; dipakai hanya sebagai konfirmasi tambahan. Tidak ada matriks yang dijalankan ulang.
- File [failure_reason_counts.csv](evidence/failure_reason_counts.csv) berisi counter agregat dari CSV simulator untuk kesembilan kondisi. Folder [evidence/runs](evidence/runs) berisi manifest, metrics, CSV `Sequential_simulation.csv`, config penting, dan queue audit untuk tiga run Queue-Aware.

## A. Lifecycle task berdasarkan kode

```mermaid
sequenceDiagram
    participant G as PaperAlignedTaskGenerator
    participant M as DefaultSimulationManager
    participant N as DefaultNetworkModel / NetworkLink
    participant O as Orchestrator
    participant C as DefaultComputingNode
    participant R as SimLog / PaperAlignedSimulationManager
    G->>M: FutureQueue<Task>, task.time
    M->>M: jadwalkan SEND_TO_ORCH dan NEXT_BATCH
    M->>N: cek phase 0, hitung sent, kirim request ke orchestrator
    N->>M: transfer request selesai
    M->>M: SEND_TASK_FROM_ORCH_TO_DESTINATION, cek phase 1
    alt aplikasi UE belum placed
        M->>O: orchestrate(task)
        O->>M: pilih eligible destination; tetapkan destination dan application placement
    else aplikasi sudah placed
        M->>M: pakai applicationPlacementLocation tersimpan
    end
    M->>N: kirim request task; mungkin transfer container
    N->>M: EXECUTE_TASK setelah transfer
    M->>C: cek phase 2; submitTask
    alt core dan RAM siap
        C->>C: startExecution; jadwalkan EXECUTION_FINISHED
    else
        C->>C: append ke FIFO getTasksQueue()
    end
    C->>M: TRANSFER_RESULTS_TO_ORCH saat CPU selesai
    M->>N: kirim hasil ke orchestrator lalu UE
    N->>M: RESULT_RETURN_FINISHED
    M->>M: cek phase 3: totalDelay >= deadline?
    alt deadline lulus
        M->>R: terminal completed/success
    else deadline terlampaui
        M->>R: terminal failed (latency)
    end
    M->>R: PRINT_LOG pada horizon; unresolved dihitung pending
```

### Arti status/counter

| Istilah laporan | Makna implementasi aktual |
|---|---|
| Generated | Task berhasil dibuat dan dimasukkan ke `FutureQueue<Task>` oleh generator. Pada start, `simLog.setGeneratedTasks(taskList.size())`. Task yang tidak tergenerate akibat device mati adalah counter terpisah; nol pada hasil yang diaudit. |
| Submitted / sent | `SimLog.tasksSent` bertambah di `sendTaskToOrchestrator()` setelah pemeriksaan phase 0 lolos, sebelum request jaringan menuju orchestrator. Semua task generated pada matriks juga berstatus sent. |
| Dispatched / destination recorded | Destination diisi saat keputusan orchestrator (atau dibaca dari placement tersimpan); permintaan kemudian dikirim ke destination. Layer workload di analyzer adalah task yang ditugaskan/dikirim ke layer, bukan completion. |
| Queued | Di `DefaultComputingNode.submitTask()`, task mendapat arrival time; jika core atau RAM tidak tersedia, task ditambahkan ke `getTasksQueue()` (FIFO). Tidak ada batas panjang queue/queue overflow pada path ini. |
| Executing | `startExecution()` mengurangi core/RAM, menyimpan execution start, lalu menjadwalkan `EXECUTION_FINISHED` setelah `task.length / mipsPerCore`. Runtime queue/executing bukan nilai `Task.Status` tersendiri. |
| Completed / successful | Result kembali melalui jaringan ke UE, `taskFailed(task, 3)` menyatakan deadline tidak terlampaui, lalu `tasksCount` bertambah. Paper metric `completed` mengikuti terminal return yang berhasil, bukan sekadar CPU execution selesai. |
| Failed | Terminal failure pada phase 0/1/2/3. `setFailed()` menambah failed dan terminal task counters, menyimpan reason pada objek task, dan menandai application placement tidak valid. |
| Pending / incomplete | Pada `PRINT_LOG`/horizon 200 s, generated dikurangi completed dan terminal failure. Task belum terminal saat cutoff; bukan failure terminal. Ia bisa masih di jaringan, queue, sedang running, atau menunggu result. Deadline tidak dicek dengan timer di queue; latency check dipanggil setelah result mencapai UE. |

`Task.Status` hanya `SUCCESS`/`FAILED`; `DefaultTask` menginisialisasi status ke `SUCCESS` dan mengubahnya ke `FAILED` saat `setFailureReason()` dipanggil. Jadi `SUCCESS` bukan state-machine bukti bahwa result sudah kembali; task pending yang belum mendapat failure reason bisa masih memiliki nilai default tersebut. Generated/submitted/queued/running/pending adalah tahap lifecycle yang diwakili event/counter/list, bukan enum status internal.

### Call path utama

1. `PaperAlignedTaskGenerator.generate()` membuat tasks, memasang application ID, length, deadline, source UE, waktu arrival, lalu memasukkannya ke `FutureQueue`. Loop app/user/second/sequence di source membentuk blok ID berurutan per app.
2. `DefaultSimulationManager.onSimulationStart()` menjadwalkan batch pertama dan horizon. `processEvent(SEND_TO_ORCH)` memanggil `sendTaskToOrchestrator()`.
3. `sendTaskToOrchestrator()` cek `taskFailed(task, 0)`, memasang orchestrator dan menambah `SimLog.tasksSent`, lalu mengirim request ke `DefaultNetworkModel`.
4. Saat `SEND_TASK_FROM_ORCH_TO_DESTINATION`, `sendFromOrchToDestination()` mengecek phase 1. Jika aplikasi belum placed, ia memanggil orchestrator; jika sudah, ia langsung memakai `applicationPlacementLocation` UE. Request dikirim ke node terpilih.
5. `DefaultNetworkModel` menangani request device→orchestrator, orchestrator→destination, container, result destination→orchestrator, dan orchestrator→device. `NetworkLink.updateTransfer()` menambah transfer delay ke `Task.actualNetworkTime`; `transferFinished()` menambah latency link.
6. `EXECUTE_TASK` mengecek phase 2 (device/resources/mobility), kemudian `submitTask()`. Jika tidak bisa mulai langsung, task masuk FIFO; pada `executionFinished()`, core/RAM/storage dibebaskan lalu task pertama queue mulai.
7. Setelah CPU selesai, hasil menempuh path balik; di `RESULT_RETURN_FINISHED`, phase 3 mengecek deadline. Completion sukses hanya setelah check ini lulus.
8. `PaperAlignedSimulationManager` menghitung completed = `tasksCount - simLog.tasksFailed`, pending = generated − completed − failed. Analyzer menggunakan `Tasks completed / Number of generated tasks` untuk success rate.

File/method kunci:

- `experiment/src/com/mechalikh/pureedgesim/experiment/PaperAlignedTaskGenerator.java:generate()`.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/simulationmanager/DefaultSimulationManager.java:onSimulationStart`, `processEvent`, `sendTaskToOrchestrator`, `sendFromOrchToDestination`, `sendResultsToOchestrator`, `taskFailed`, `setFailed`.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/datacentersmanager/DefaultComputingNode.java:submitTask`, `startExecution`, `executionFinished`.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/network/DefaultNetworkModel.java:processEvent`, `send`, `sendRequestFromDeviceToOrch`, `sendRequestFromOrchToDest`, `transferFinished`; `NetworkLink.updateTransfer`, `transferFinished`.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/taskgenerator/TaskAbstract.java:getActualCpuTime`, `getWatingTime`, `getTotalDelay`; `DeadlinePolicy.isExceeded`.
- `experiment/src/com/mechalikh/pureedgesim/simulationmanager/PaperAlignedSimulationManager.java:processEvent`, `recordTerminalIfCountChanged`; `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/simulationmanager/SimLog.java:showIterationResults`, `incrementTasksFailed*`.
- `scripts/analyze.py:parse()`.

## B. Penyebab failure dan alasan success rate rendah

### Counter failure yang tersedia

`Task.FailureReason` memuat latency, device mati, mobility, tidak ada destination, insufficient resources, insufficient power, dan tidak tergenerate karena device mati. `DefaultSimulationManager.taskFailed()` memetakan phase 0–3 ke subset reason tersebut. `SimLog` menyimpan counter agregat untuk deadline, device dead, mobility, resource/long-wait, serta task tidak tergenerate karena device mati. Raw `Sequential_simulation.csv` memuat counter agregat ini; `analyze.py` saat ini tidak meneruskannya ke `metrics.json`. `NO_OFFLOADING_DESTINATIONS` dan `INSUFFICIENT_RESOURCES` sama-sama masuk counter resource yang labelnya “No resources available or long waiting time”; counter itu bukan kategori queue overflow terpisah. `INSUFFICIENT_POWER` ada pada enum tetapi tidak ditemukan call site yang menetapkan reason tersebut di source tree ini.

| Beban | Metode | Generated | Completed | Terminal failed | Delay/deadline failures | Resource atau long-wait counter | Device-dead failures | Mobility failures | Pre-pipeline rejection | Pending | Success % |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Low | Trade-Off | 29.000 | 2.994 | 25.977 | 25.977 | 0 | 0 | 0 | 0 | 29 | 10,324 |
| Low | Round Robin | 29.000 | 2.994 | 25.977 | 25.977 | 0 | 0 | 0 | 0 | 29 | 10,324 |
| Low | Queue-Aware | 29.000 | 2.994 | 25.977 | 25.977 | 0 | 0 | 0 | 0 | 29 | 10,324 |
| Medium | Trade-Off | 58.000 | 4.755 | 44.151 | 44.151 | 0 | 0 | 0 | 0 | 9.094 | 8,198 |
| Medium | Round Robin | 58.000 | 4.755 | 44.151 | 44.151 | 0 | 0 | 0 | 0 | 9.094 | 8,198 |
| Medium | Queue-Aware | 58.000 | 4.797 | 46.481 | 46.481 | 0 | 0 | 0 | 0 | 6.722 | 8,271 |
| High | Trade-Off | 87.000 | 5.605 | 44.937 | 44.937 | 0 | 0 | 0 | 0 | 36.458 | 6,443 |
| High | Round Robin | 87.000 | 5.605 | 44.937 | 44.937 | 0 | 0 | 0 | 0 | 36.458 | 6,443 |
| High | Queue-Aware | 87.000 | 5.526 | 45.175 | 45.175 | 0 | 0 | 0 | 0 | 36.299 | 6,352 |

Untuk semua baris, jumlah deadline/device-dead/mobility/resource counters yang terminal sama dengan terminal-failed count; accounting generated = completed + failed + pending valid. `Tasks not generated due to death` juga nol pada semua baris. Run low smoke seed 8128 memiliki 25.985 deadline failures dan 21 pending (konfigurasi sama, seed berbeda).

### Mengapa low tetap memiliki success rate rendah?

**Fakta kode/config:**

- Low memiliki 10 UE, pembagian app 2 Hard real-time, 3 Soft real-time, 5 Non-real-time. Dengan rates 20/30/3 task/s/UE selama 200 s, generator menghasilkan masing-masing 8.000 / 18.000 / 3.000 task (29.000 total).
- Deadline app adalah 0,02 s / 0,5 s / 300 s; task length 500 / 5.000 / 30.000 MI. EDC masing-masing 10 core × 40.000 MIPS, total kapasitas EDC 1,6 juta MIPS. Offered work low adalah 0,92 juta MI/s (ratio 0,575).
- Orchestrator ditempatkan di Cloud (`deploy_orchestrator=CLOUD`), dan WAN latency adalah 0,06 s. `DefaultNetworkModel` mengirim request UE→orchestrator dan task orchestrator→destination. Jaringan menambah transfer time dan link latency ke `actualNetworkTime`.
- Deadline dicek setelah task execution dan return network selesai. `getTotalDelay()` adalah network time + queue waiting + CPU time; deadline equality juga gagal (`>=`).
- Raw low Trade-Off CSV menunjukkan `Average CPU usage (Edge)=57,4672%`, `Task not executed (No resources available or long waiting time)=0`, 25.977 delay failures, dan hanya 29 pending. Jadi kegagalan terminal low bukan counter resource dan bukan karena sebagian besar task tertahan pada cutoff.

**Penjelasan yang didukung kuat:** deadline 20 ms untuk hard-real-time lebih kecil daripada WAN latency 60 ms yang dikonfigurasi untuk jalur ke orchestrator Cloud; setelah network request, dispatch, CPU dan hasil kembali, deadline tersebut tidak realistis untuk task offloaded melalui jalur ini. Deadline soft 0,5 s juga dapat habis oleh network, queue waiting, CPU dan overhead; formula total delay menjumlahkan semua komponen tersebut. Pada low, jumlah completion 2.994 dekat dengan 3.000 task Non-real-time yang dihasilkan, sedangkan 26.000 task Hard+Soft memiliki deadline ketat. Pola ini konsisten dengan deadline mismatch.

**Batas bukti:** raw CSV tidak memiliki failure IDs atau cross-tab app type × failure reason × delay component. Karena itu angka “berapa Hard vs Soft task gagal” tidak tersedia dan tidak boleh disimpulkan dari kedekatan jumlah saja. Raw memberi waktu network aggregate dan waiting average, bukan dekomposisi network/queue/CPU untuk tiap deadline-failed task. Maka penyebab terminal yang terbukti adalah deadline; kontribusi tepat per komponen dan per app belum diketahui.

### Deadline, queue, network, pending, dan denominator

- **Deadline/expiration:** tidak ada timer deadline yang membunuh task saat menunggu di queue. Pemeriksaan pada phase 3 baru terjadi pada `RESULT_RETURN_FINISHED`; semua kegagalan hasil matriks masuk counter `Tasks failed (delay)`. Task yang belum sampai event tersebut saat cutoff akan tetap pending.
- **Queue overflow/capacity:** `getTasksQueue().add(task)` menggunakan list tanpa max queue length atau overflow rejection. Jika core tidak tersedia, task menunggu. Resource check phase 2 hanya RAM/storage/dead node; counter resource/long-wait pada semua run = 0. Maka tidak ada bukti queue overflow sebagai penyebab failure.
- **Network:** tidak ditemukan `NETWORK_FAILURE` pada `FailureReason`; transfer delay/latency ditambahkan ke total delay dan dapat menyebabkan deadline failure. Tidak ada error simulation/validation pada run. Kategori per-task network failure tidak dicatat.
- **Pending berbeda dari failed:** low pending kecil; medium/high pending besar. Pending tidak dimasukkan terminal failures dan bukan success. Beberapa task yang sudah melewati deadline secara waktu tetapi belum menyelesaikan result return pada t=200 belum sempat diuji phase 3, sehingga statusnya pending, bukan failed.
- **Success denominator:** analyzer menggunakan `completed / generated`. Untuk estimand “selesai sebelum horizon 200 s”, denominator generated tepat dan pending harus tetap non-success; failed/generated dan pending/generated juga dipisah. Jangan mengganti dengan completed/(completed+failed) karena itu membuang pending dan menaikkan rate secara bias.

## C. Siklus keputusan orchestrator

| Metode | Kelas dan selector | Kondisi pemanggil | Unit keputusan aktual | Kandidat pada `EDGE_DC_ONLY` | Kapan destination ditetapkan/berubah? |
|---|---|---|---|---|---|
| Trade-Off | `PaperAlignedOrchestrator` → inherited `DefaultOrchestrator.findComputingNode()` → `tradeOff()` | `SEND_TASK_FROM_ORCH_TO_DESTINATION`; hanya saat `!edgeDevice.isApplicationPlaced()` | Application placement/re-placement yang dipicu sebuah task; bukan setiap task | Node `nodeList` layer Edge (= EDC), lolos reachability `offloadingIsPossible()` | `Orchestrator.assignTaskToComputingNode()` mengisi task destination dan UE `applicationPlacementLocation`; task selanjutnya memakai node tersimpan. Placement diinvalidasi setelah failure atau pada kondisi mobility tertentu (`LocationAwareNode.connectWith()`). |
| Round Robin | `PaperAlignedOrchestrator` → `DefaultOrchestrator.findComputingNode()` → `roundRobin()` | Kondisi event/gating sama dengan Trade-Off | Application placement/re-placement | Kandidat dan eligibility sama | Destination ditetapkan dengan cara yang sama dan dicache di UE. |
| Queue-Aware | `QueueAwareTradeOffOrchestrator.findComputingNode()`; extends `PaperAlignedOrchestrator` | Kondisi event/gating sama; algorithm property tetap `TRADE_OFF`, tetapi subclass menjalankan score queue-aware | Application placement/re-placement; tidak dipanggil untuk setiap task | Kandidat eligible EDC sama; skor dasar Trade-Off + λ × estimated wait | Assignment/caching sama; Queue-Aware hanya memberi efek saat method ini dipanggil. |

`DefaultOrchestrator.java:42–50` memilih tradeOff/Round Robin; `tradeOff()` ada pada 53–88 dan `roundRobin()` 90–106. `DefaultSimulationManager.java:294–320` memiliki decision gate: bila aplikasi UE belum ditempatkan, panggil orchestrator; selain itu salin destination tersimpan. `Orchestrator.assignTaskToComputingNode()` mengatur destination dan application placement. Queue-Aware mengambil nilai queue di `QueueAwareTradeOffOrchestrator.java:47–85`.

Ketiga metode memperoleh kesempatan pada kondisi placement yang sama, tetapi bukan kesempatan per task. Jumlah pemanggilan aktual dapat berbeda antar-metode karena keputusan dan failure/mobility berikutnya memengaruhi kapan placement diinvalidasi. Pada matriks, queue audit selected count adalah 1.005/29.000 low, 2.017/58.000 medium, 2.385/87.000 high. Semua run masih mencatat destination akhir untuk setiap task, tetapi kebanyakan bukan keputusan orchestrator baru.

## D. Apa yang dapat dan tidak dapat disimpulkan dari eksperimen

**Fakta hasil:**

- Low: semua metode 2.994 completed, 25.977 deadline failures, 29 pending.
- Medium: Trade-Off/Round Robin 4.755 completed; Queue-Aware 4.797. Semua terminal failures tetap deadline; Queue-Aware mengurangi pending dari 9.094 ke 6.722 tetapi menambah terminal deadline failure dari 44.151 ke 46.481.
- High: Trade-Off/Round Robin 5.605 completed; Queue-Aware 5.526. Semua terminal failures deadline; pending sekitar 36k.
- Semua acceptance status selesai, manifest validation error nol, dan accounting konsisten.

**Interpretasi:** success rendah di low bukan indikasi utama lifecycle accounting rusak. Bukti paling kuat adalah seluruh terminal failed dilabeli deadline dan konfigurasi hard deadline 20 ms dibanding WAN 60 ms/orchestrator Cloud. Low juga memiliki utilisasi Edge agregat sedang dan nol resource-failure counter. Pada medium/high, waiting/CPU pressure dan pending meningkat; EDC CPU edge di raw baseline naik 94,47% lalu 99,99%, sejalan dengan congested workload. Queue pressure dapat memperburuk deadline tetapi tidak menjelaskan semua low failure.

**Yang belum dapat disimpulkan:** jumlah failure per tipe aplikasi, komponen delay penyebab masing-masing failure, apakah seluruh pending akan kemudian menjadi deadline failure, dan performa jika tiap task boleh memilih destination baru. Satu seed tiap level juga tidak mendukung generalisasi/statistical significance. Eksperimen ini tidak memverifikasi konfigurasi terhadap paper.

## E. Rekomendasi keputusan penelitian

1. **Nama metode sekarang:** sebut “Queue-Aware Application Placement/Re-placement” agar selaras dengan gating lifecycle aktual. Jangan menyebut current results sebagai evaluasi task-by-task offloading.
2. **Hook yang ditemukan:** `SimulationAbstract.setCustomSimulationManager(Class)` tersedia; kelas custom harus turunan `DefaultSimulationManager`. `DefaultSimulationManager.sendFromOrchToDestination(Task)` adalah `protected` dan overridable. Method itu adalah titik terdekat sebelum task dikirim ke destination dan berisi cabang cache placement. `setCustomEdgeOrchestrator()` juga ada.
3. **Perubahan minimum untuk task-level (rekomendasi desain, belum diimplementasikan):** buat manager eksperimen yang memanggil `orchestrate(task)` pada setiap `SEND_TASK_FROM_ORCH_TO_DESTINATION`, bukan hanya ketika UE belum placed, sambil tetap mempertahankan phase checks, no-destination handling, transmission, result path, dan accounting. Terapkan decision cadence yang sama pada Trade-Off, Round Robin, dan Queue-Aware agar pembanding mendapat kesempatan yang setara. Jangan mengubah upstream baseline default.
4. **Failure accounting:** global lifecycle accounting tidak perlu diperbaiki sebelum langkah berikutnya; ia sudah merekonsiliasi 9/9 matriks. Counter alasan agregat tersedia di raw CSV dan menunjukkan akar terminal failure. Sebelum menyimpulkan lebih dalam, tambahkan logging per task yang menghubungkan task ID, `FailureReason`, phase, application ID/type, destination, timestamps request/network/queue/start/finish/return, dan state saat horizon. Analyzer juga sebaiknya mempertahankan kolom reason.
5. **Validasi workload/deadline:** audit task deadline dan network path terlebih dahulu. Buat diagnostic yang mengukur baseline minimum network+CPU per app. Jika deadline paper dipertahankan, nyatakan konsekuensi Cloud orchestrator; jika deadline/config diubah untuk diagnosis, pisahkan sebagai sensitivity/diagnostic run, bukan diam-diam mengganti baseline.
6. **Eksperimen berikut:** setelah decision granularity dan trace logging disepakati, jalankan smoke kecil untuk ketiga metode dengan decision counter yang harus sama dengan jumlah task yang memang ditargetkan. Pastikan low task rate dapat memenuhi deadline pada jalur network yang dipilih. Lanjutkan ke beberapa seed independen, λ=0 sebagai kontrol integrasi dan beberapa λ yang ditetapkan sebelumnya, lalu matriks multi-workload. Bandingkan estimated wait dengan observed wait cohort yang sama.

### Pertanyaan yang belum terjawab

- Apakah tujuan penelitian mendefinisikan pemilihan destination per task atau placement aplikasi per UE?
- Apakah deadline 0,02 / 0,5 / 300 detik, task sizes, serta semantics rate per UE sudah diverifikasi dari metode paper yang dimaksud?
- Apakah orchestrator Cloud memang harus menerima setiap task request sebelum dispatch, atau seharusnya edge orchestrator dipakai untuk aplikasi low-latency?
- Berapa banyak deadline failures berasal dari Hard, Soft, dan Non-real-time? Data saat ini tidak menyediakan status per task untuk menjawabnya.
- Untuk deadline failures, berapa proporsi network vs queue vs CPU delay? Tidak ada dekomposisi per task.
- Pending tasks di cutoff mana yang kemudian akan memenuhi deadline jika simulation horizon diperpanjang?
- Apa definisi keberhasilan yang ingin ditargetkan: completion sebelum 200s, completion sebelum task deadline, atau keduanya dilaporkan terpisah?

## File bukti

- `evidence/failure_reason_counts.csv` — agregat lifecycle/failure reason untuk 9 matriks, dapat ditelusuri ke raw sequential CSV.
- `evidence/runs/<run_id>/manifest.json` dan `metrics.json` — konfigurasi/validasi/metrics per run.
- `evidence/runs/<run_id>/raw/Sequential_simulation.csv` — sumber counter alasan failure dan network/CPU summary.
- `evidence/runs/<Queue-Aware run>/raw/queue_decisions.csv` — keputusan dan queue snapshots yang tercatat.
- `evidence/runs/*/applications.xml`, `simulation_parameters.properties`, `edge_datacenters.xml` — konfigurasi aplikasi, jaringan/horizon, dan kapasitas node.
- `evidence/extract_failure_evidence.py`, `evidence/evidence_scope.txt` — cara pemilihan run dan ekstraksi ringkasan.

ZIP hanya berisi laporan dan bukti terpilih; tidak menyertakan repository penuh atau seluruh destination traces berukuran besar.
