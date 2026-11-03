# Audit Diagnostik Deadline/Network dan Desain Task-Level Offloading

Tanggal audit: 3 November 2026  
Repository: `queue-aware-task-offloading-simulation-baseline`  
Commit yang diaudit: `03acb8635144a99b147b3d9e97017052cfaf4978` (`main`)  
Cakupan: inspeksi kode dan hasil eksperimen yang sudah tersedia. Tidak ada simulasi yang dijalankan ulang; tidak ada kode/config baseline yang diubah.

## Ringkasan keputusan

1. Akar dominan **terminal failure** pada 9 run matriks yang tersedia adalah pemeriksaan deadline di akhir perjalanan task. Counter resource, device-death, mobility, dan pre-pipeline rejection semuanya nol. Klasifikasi ini tidak mengungkap komponen delay per task.
2. Ada ketidakcocokan deadline/jalur yang dapat menjelaskan success rendah pada workload low: aplikasi Hard Real-Time memakai deadline 0,02 s; konfigurasi menetapkan UE mengirim request orchestration ke Cloud; topologi membuat WAN path UE–Cloud; dan latency WAN adalah 0,06 s per hop yang dilewati. Karena total delay mencakup network, task Hard yang menempuh WAN sudah melampaui deadline bahkan sebelum queue/CPU/return. Ini bukti konfigurasi dan jalur, tetapi artefak hasil tidak menghubungkan failure ke tipe aplikasi, jadi jumlah Hard failure tidak dapat ditentukan.
3. Queue-Aware saat ini adalah **Queue-Aware Application Placement/Re-placement**. Orchestrator dipanggil hanya ketika UE belum memiliki cached application placement. Pemicu kebijakan tetap sebuah task event, tetapi objek yang diputuskan/cached adalah placement untuk task berikutnya.
4. PureEdgeSim menyediakan hook SimulationManager custom. Titik paling tepat yang ditemukan adalah override `DefaultSimulationManager.sendFromOrchToDestination(Task)`—dipanggil untuk setiap task setelah request orchestrator tiba dan sebelum pengiriman ke destination. Namun `PaperAlignedSimulationManager` bersifat `final`, jadi reuse langsung subclass tersebut memerlukan desain manager baru atau perubahan kecil pada modifier di tahap implementasi nanti. Tidak ada perubahan yang dilakukan dalam audit ini.
5. Accounting global cukup untuk membedakan completed, terminal failed, dan pending serta merekonsiliasi total. Sebelum eksperimen komparatif task-level, tambahkan dulu trace per-task minimal yang mengaitkan aplikasi, alasan/phase failure, delay, keputusan, dan kondisi cutoff.

## 1. Diagnostik deadline dan network

### Fakta konfigurasi dan kode

| Fakta | Bukti |
|---|---|
| UE mengirim request orchestration ke Cloud | `configs/paper-aligned/simulation_parameters.properties:18-22` (`enable_orchestrators=true`, `deploy_orchestrator=CLOUD`, `wait_for_all_tasks=false`) |
| Hard RT: latency/deadline 0,02 s; Soft RT 0,5 s; Non-RT 300 s | `configs/paper-aligned/applications.xml`; salinan ada di `evidence/applications.xml` |
| WAN latency dikonfigurasi 0,06 s; MAN 0,01; Wi-Fi 0,005; Ethernet 0,002; cellular 0,03 | `configs/paper-aligned/simulation_parameters.properties:32-53` |
| Topologi menghubungkan edge devices ke WAN node dan WAN node ke cloud | `DefaultTopologyCreator.generateTopologyGraph()` baris 81-95; shared WAN dibuat di `createWanLink()` baris 129-152 |
| Delay aktual per link ditambahkan ke `Task.actualNetworkTime`; saat transfer selesai latency hop juga ditambahkan dan event hop selanjutnya dijadwalkan | `NetworkLink.updateTransfer()` baris 128-160 dan `transferFinished()` baris 163-182 |
| Deadline diperiksa sebagai `task.getTotalDelay() >= maxLatency` pada phase hasil kembali | `DefaultSimulationManager.taskFailed()` dan `DeadlinePolicy.isExceeded()`; lihat daftar file di bawah |
| Total delay adalah network + waiting + CPU execution | `TaskAbstract.getTotalDelay()` (`TaskAbstract.java`, method `getTotalDelay`) |

`DefaultTopologyCreator` memastikan WAN path UE–Cloud. Karena konfigurasi memakai cloud orchestrator, request orchestration dan jawaban/hasil yang melintasi Cloud melibatkan WAN sesuai path yang dipilih. `NetworkLink` menjumlahkan latency per hop; 60 ms bukan total network end-to-end. Maka Hard deadline 20 ms tak kompatibel dengan perjalanan yang memasukkan satu hop WAN 60 ms. Soft deadline 500 ms masih dapat dipenuhi pada kondisi ringan, tetapi antrian, transfer ukuran input/output, serta jalur pergi-pulang akan menambah delay. Non-RT deadline 300 s tidak otomatis menjamin completion sebelum cutoff 200 s.

Konfigurasi memakai `realistic_network_model=false`, sehingga file transfer diselesaikan secara instan dalam model transfer bandwidth pada event update, tetapi delay transmisi dihitung dari ukuran/bandwidth; propagation latency tetap dimasukkan. Artinya jaringan tetap dapat berkontribusi signifikan dan WAN bandwidth 20 Mbps tetap relevan.

### Interpretasi diagnostik

- **Fakta hasil:** pada workload low seed 1, hanya 2.994/29.000 task completed; 25.977 terminal failures seluruhnya masuk counter `Tasks failed (delay)`; pending 29. Resource/long-wait, device-dead, mobility, ungenerated-device-death, serta rejected-before-pipeline masing-masing nol.
- **Fakta konfigurasi:** pada 10 UE, task generator menghasilkan 8.000 Hard, 18.000 Soft, dan 3.000 Non-RT tasks selama 200 detik (task rate 40/90/15 per detik per app class agregat sesuai konfigurasi generator dan kelompok UE). Completed 2.994 dekat dengan 3.000 task Non-RT, tetapi kedekatan ini **bukan** pemetaan status per aplikasi.
- **Kesimpulan kuat namun bukan atribusi individual:** perbedaan Hard deadline dan WAN latency dapat menjelaskan porsi besar kegagalan di low. Tanpa task ID + app type pada failure event, tidak sah menyatakan tepat berapa dari 25.977 failure adalah Hard/Soft.
- **Belum terukur:** dekomposisi `totalDelay` ke network, queue, CPU untuk setiap task yang gagal. `Sequential_simulation.csv` hanya menyimpan counter/aggregate; log reason tidak mempertahankan task ID/type/destination per failure.

Tidak ditemukan overflow queue: `DefaultComputingNode.submitTask()` menambahkan task ke queue FIFO ketika core/RAM tidak tersedia; queue adalah list tanpa batas kapasitas dan tidak ada rejection karena panjang queue. Network delay yang tinggi berujung pada kategori deadline failure, bukan failure reason network tersendiri. Pending adalah task yang belum mencapai terminal completion/failure event saat cutoff, bukan sinonim failed.

## 2. Hasil run yang tersedia

Sumber angka: `evidence/run_summary.csv` (manifest run asli dalam arsip audit sebelumnya) dan agregasi `evidence/failure_reason_counts.csv`. Matriks yang dibandingkan di bawah hanya run seed 1, durasi 200 s, konfigurasi EDGE_DC_ONLY, 10/20/30 UE, ketiga algoritma. Tidak dicampur dengan smoke seed 8128 atau acceptance checks.

| UE / workload | Metode | Generated | Completed | Terminal failed (delay) | Pending | Success = completed/generated | CPU EDC |
|---|---|---:|---:|---:|---:|---:|---:|
| 10 / low | Trade-Off, Round Robin, Queue-Aware* | 29.000 | 2.994 | 25.977 | 29 | 10,324% | 57,467% |
| 20 / medium | Trade-Off, Round Robin | 58.000 | 4.755 | 44.151 | 9.094 | 8,198% | 94,465% |
| 20 / medium | Queue-Aware | 58.000 | 4.797 | 46.481 | 6.722 | 8,271% | 95,730% |
| 30 / high | Trade-Off, Round Robin | 87.000 | 5.605 | 44.937 | 36.458 | 6,443% | 99,988% |
| 30 / high | Queue-Aware | 87.000 | 5.526 | 45.175 | 36.299 | 6,352% | 99,978% |

\* Nilai untuk tiga metode low identik. Semua run mencatat 29.000 dispatched pada low, dan 58.000/87.000 untuk medium/high. `generated = completed + terminal failed + pending` pada setiap run. Di seluruh sembilan run, semua terminal failures tercatat sebagai delay; counter kegagalan lainnya nol.

### Apa yang dapat disimpulkan

- Rendahnya rasio completion konsisten dengan cutoff deadline dan beban kombinasi aplikasi; low pun mengirim 29k task sepanjang horizon dan satu kelas memiliki deadline lebih kecil daripada satu WAN hop.
- Medium/high menunjukkan pressure tambahan: CPU edge sekitar 94–100%, waiting time rata-rata untuk task yang dieksekusi meningkat dari 0,27 s (low) ke 13,56 s/38,82 s (Trade-Off medium/high), dan pending naik tajam. Ini mendukung hipotesis queue/saturation pada beban yang lebih tinggi.
- Queue-Aware di medium sedikit menaikkan completed (+42) tetapi lebih banyak menandai failure deadline (+2.330) dan pending berkurang; di high completion lebih rendah 79 dari Trade-Off. Satu seed dan decision cadence placement-level tidak cukup untuk menilai task-level algorithm atau signifikansi statistik.
- Success rate memakai denominator generated, tepat untuk estimand “selesai sebelum horizon”. Mengeluarkan pending dari denominator akan menggelembungkan hasil dan menjawab pertanyaan berbeda.

### Batas kesimpulan

- Hasil tidak membuktikan bahwa workload XML atau simulator salah; tetapi deadline 20 ms vs WAN 60 ms adalah ketidakcocokan konfigurasi yang nyata untuk task Hard yang melewati WAN.
- Tidak ada data per-task untuk membedakan Hard/Soft/Non-RT failure, request vs result network, queue vs CPU contribution, atau task yang pending namun nantinya akan gagal.
- Medium/high mengalami CPU saturation dan waiting; low tidak menunjukkan resource counter failure. Maka satu penjelasan “semua karena load” tidak cukup untuk low.
- Tidak ada dasar untuk mengklaim implementasi sekarang sebagai task-level offloading; eksperimen yang ada mengukur placement-level behavior.

## 3. Lifecycle dan failure accounting yang relevan

1. `PaperAlignedTaskGenerator.generateTasks()` membuat task, menetapkan application ID/type, deadline, ukuran kerja, source UE, creation time, dan task ID.
2. `DefaultSimulationManager.onSimulationStart()` menjadwalkan pengiriman batch; `processEvent()` mengarahkan event `SEND_TO_ORCH` ke request orchestrator.
3. `sendTaskToOrchestrator()` memeriksa phase awal dan mengirim request jaringan.
4. Saat event `SEND_TASK_FROM_ORCH_TO_DESTINATION`, `sendFromOrchToDestination()` memeriksa kondisi node. Jika placement UE belum ditetapkan, orchestrator memilih; jika sudah ada, destination cache dipakai. Task lalu mengirim request/data ke node tujuan.
5. `DefaultComputingNode.submitTask()` menjalankan task jika tersedia core dan RAM, jika tidak memasukkan ke queue FIFO. Setelah task selesai, task pertama di queue dimulai.
6. Saat execution selesai, hasil melewati network path kembali ke orchestrator/UE. Di `RESULT_RETURN_FINISHED`, phase deadline check berjalan. Lolos deadline menaikkan completed; melampaui deadline membuat terminal failed.
7. Pada waktu simulasi berhenti, manager menghitung `pending = generated - completed - failed`. Task yang belum mencapai event result-return final belum diklasifikasikan oleh phase deadline check.

Jadi `generated` adalah dibuat oleh generator; `submitted/dispatched` adalah masuk pipeline/request (counter generated dan sent sama untuk matriks); `queued` adalah task di list FIFO; `executing` adalah task yang menggunakan core; `completed/successful` baru terjadi setelah hasil kembali dan lolos deadline; `failed` adalah kegagalan terminal di phase pemeriksaan; `pending/incomplete` adalah residu saat horizon, bukan status terminal failure. `Task` memiliki enum success/failed yang bukan state machine rinci untuk semua tahap lifecycle.

## 4. Unit keputusan dan jalur orchestrator

| Metode | Selector | Pemanggil/gate | Unit aktual | Kandidat | Kapan cache berubah |
|---|---|---|---|---|---|
| Trade-Off | `DefaultOrchestrator.findComputingNode()` → `tradeOff()`; subclass konfigurasi `PaperAlignedOrchestrator` | event `SEND_TASK_FROM_ORCH_TO_DESTINATION`; hanya jika `!edgeDevice.isApplicationPlaced()` | placement aplikasi pada UE yang dipicu task pertama/re-placement | EDC eligible dalam arsitektur EDGE_DC_ONLY, lolos `offloadingIsPossible()` | `assignTaskToComputingNode()` mengatur destination task dan UE placement; task berikutnya menggunakan destination cached |
| Round Robin | `DefaultOrchestrator.findComputingNode()` → `roundRobin()` | gate/event sama | placement/re-placement | node eligible yang sama | assignment/cache sama |
| Queue-Aware | `QueueAwareTradeOffOrchestrator.findComputingNode()` dengan skor Trade-Off + λ × estimated wait | gate/event sama | placement/re-placement | kandidat EDC eligible | assignment/cache sama |

Urutan kunci: `DefaultSimulationManager.processEvent()` menangani event `SEND_TASK_FROM_ORCH_TO_DESTINATION`, lalu memanggil `sendFromOrchToDestination(Task)`. Method itu hanya memanggil `orchestrator.orchestrate(task)` ketika placement belum ada; selain itu ia mengisi destination task dari cache. `Orchestrator.assignTaskToComputingNode()` menetapkan destination. Placement dapat diinvalidasi setelah failure atau kondisi mobility tertentu, sehingga selector dipanggil ulang untuk re-placement.

Pada Queue-Aware matrix, decision counter 1.005/29.000 low, 2.017/58.000 medium, 2.385/87.000 high—jauh di bawah satu keputusan per task. Trade-Off dan RR memakai call path dan gate yang sama. Pada edge datacenter homogen, hasil placement Trade-Off dan RR pada run yang tersedia identik; ini tidak membuktikan algoritma akan identik untuk konfigurasi heterogen.

## 5. Apakah PureEdgeSim memberi hook untuk custom manager?

**Ya, hook class-level terverifikasi.** `SimulationAbstract.setCustomSimulationManager(Class<? extends SimulationManager>)` menerima custom class dan dokumentasi sumber mensyaratkan turunan `DefaultSimulationManager` (`SimulationAbstract.java:168-175`). `SimulationThread` membuatnya lewat constructor reflection dengan signature `(SimLog, PureEdgeSim, int, int, Scenario)` (`SimulationThread.java:124-128`). `DefaultSimulationManager.sendFromOrchToDestination(Task)` bersifat `protected`, bukan `final`; dapat dioverride. Method ini adalah titik kebijakan yang dekat dengan dispatch: request sudah tiba di orchestrator, destination belum dikirim ke jaringan.

Batas reuse: `PaperAlignedSimulationManager` adalah `final` (`experiment/src/com/mechalikh/pureedgesim/simulationmanager/PaperAlignedSimulationManager.java:23`), jadi custom manager baru tidak bisa langsung mewarisi accounting manager tersebut. Untuk mempertahankan instrumentasi, desain minimum yang aman adalah salah satu dari:

- kelak jadikan manager eksperimen paper-aligned dapat diwarisi, lalu buat subclass task-level yang override decision gate; atau
- buat `TaskLevelPaperSimulationManager extends DefaultSimulationManager` dan port/reuse accounting hooks secara eksplisit.

Ini rekomendasi desain, bukan perubahan audit ini. Jangan menyimpulkan ada callback task-level siap pakai di orchestrator: hook yang ditemukan ialah custom manager dan protected dispatch method.

### Rancangan integrasi minimum

Pada manager eksperimen terpisah, override `sendFromOrchToDestination(Task)` agar setiap task yang mencapai titik dispatch meminta keputusan baru. Pertahankan pemeriksaan failure phase, penanganan tidak ada destination, rute transmisi, eksekusi, return result, dan accounting yang sama dengan parent. Sebaiknya refactor konseptualnya menjadi satu metode `selectDestination(task, policy)` yang dipanggil pada event yang sama untuk semua algoritma, sehingga Trade-Off, RR, dan QA punya decision opportunity setara. Per-task destination tidak boleh ditimpa oleh cache UE sebelum policy dipanggil.

Queue-Aware harus mengambil queue state pada timestamp keputusan yang sama dengan lawan; catat kandidat, score tiap kandidat, predicted wait, destination terpilih, λ, dan alasan infeasible. Kontrol QA dengan λ=0 harus menghasilkan fungsi skor baseline yang terdokumentasi; tentukan tie-break secara identik. Karena pilihan kebijakan mengubah event scheduling dan queue trajectories, paired seed tidak menjamin setiap event setelah keputusan pertama identik. Laporkan workload/task trace yang sama dan bandingkan beberapa seed berpasangan.

## 6. Logging minimum sebelum matriks task-level

| Data per task/event | Saat ini tersedia? | Kebutuhan |
|---|---|---|
| Task ID, UE ID, app ID/type, generated time, deadline | object task memiliki; generator menetapkan sebagian besar | ekspor ke event trace dan hubungkan ke terminal/pending row |
| policy, decision timestamp, candidate set, score, selected destination, queue snapshot | QA mencatat audit agregat/decision; T/R tidak mencatat kandidat lengkap | trace seragam untuk ketiga metode, satu record per task decision |
| phase dan `FailureReason` untuk setiap terminal failure | object failure/manager serta agregat counter; tidak persistent per-task | log task ID + reason enum + phase + time |
| network time, queue waiting, CPU time per task | object `Task` menghitungnya; aggregate summary tersedia | emit komponen saat completion/failure/cutoff |
| pending state saat t=200 | manager menghitung jumlah residu; tidak ada row per task | simpan ID dan tahap terakhir (transmitting/queued/executing/result-return) |
| network path/hop delay | agregat network usage dan task total network time; per-task hop trace tidak tersimpan dalam analyzer | minimal total upload/request/return delay atau setiap hop untuk diagnostik |
| destination/cache provenance | destination CSV ada; tak cukup untuk membuktikan apakah task menerima keputusan baru | log `decision_kind=initial/replacement/per-task` serta cached destination sebelum keputusan |

Jangan tambahkan instrumentasi besar sekaligus. Minimum valid adalah satu CSV per task yang mengaitkan ID, app/type, deadline, decision/candidates, destination, `FailureReason`+phase, waktu network/wait/CPU, terminal/pending state, dan timestamp cutoff.

## 7. Urutan eksperimen yang direkomendasikan

1. Tambahkan trace task-level dan satu diagnostic kecil untuk memvalidasi jalur laten: uji satu Hard, Soft, dan Non-RT task pada jalur edge/cloud; verifikasi delay network sebelum menafsirkan semua deadline failure. Bukan rerun matriks.
2. Buat custom manager terpisah dengan satu titik keputusan per task dan accounting yang setara. Tambahkan assertion decision count = eligible dispatched task count untuk ketiga metode.
3. Smoke deterministic pada satu seed, jumlah UE kecil, dan horizon cukup untuk membaca completed/failed/pending; jalankan tiga baseline policy melalui hook yang sama. Sertakan λ=0 sebagai kontrol QA integration.
4. Setelah accounting dan opportunity setara lolos, jalankan beberapa seed independen untuk low workload terlebih dahulu. Pisahkan pertanyaan estimand “completion sebelum cutoff” dan “deadline success”.
5. Baru lanjutkan medium/high serta sweep λ yang ditetapkan sebelumnya. Pertahankan konfigurasi paper-aligned; jika deadline/orchestrator/network diubah untuk diagnosis, jadikan sensitivity arm terpisah dengan manifest konfigurasi tersendiri.

### Apakah failure accounting harus diperbaiki dulu?

Accounting agregat **tidak perlu diganti** agar tahu bahwa terminal failed adalah delay; rekonsiliasi generated/completed/failed/pending valid. Namun **task-level failure observability perlu ditambah sebelum eksperimen komparatif baru** jika tujuan penelitian adalah menjelaskan mengapa task gagal atau menilai deadline/network trade-off. Pisahkan ini sebagai peningkatan logging eksperimen, bukan koreksi algoritma/baseline.

## 8. Daftar file dan method yang ditelusuri

Path berikut relatif terhadap repository pada commit di atas:

- `experiment/src/com/mechalikh/pureedgesim/experiment/PaperAlignedTaskGenerator.java` — `generateTasks()`.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/simulationmanager/DefaultSimulationManager.java` — `onSimulationStart()`, `processEvent()`, `sendTaskToOrchestrator()`, `sendFromOrchToDestination()`, `taskFailed()`, `setFailed()`.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/datacentersmanager/DefaultComputingNode.java` — `submitTask()`, execution completion/queue service.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/taskorchestrator/DefaultOrchestrator.java` — `findComputingNode()`, `tradeOff()`, `roundRobin()`.
- `experiment/src/com/mechalikh/pureedgesim/taskorchestrator/QueueAwareTradeOffOrchestrator.java` — `findComputingNode()` dan queue wait scoring.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/taskorchestrator/Orchestrator.java` — `assignTaskToComputingNode()`.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/datacentersmanager/DefaultTopologyCreator.java` — `generateTopologyGraph()`, `createWanLink()`.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/network/DefaultNetworkModel.java` — `send()`, `sendRequestFromOrchToDest()`, result routing.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/network/NetworkLink.java` — `updateTransfer()`, `transferFinished()`.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/simulationmanager/SimulationAbstract.java` — `setCustomSimulationManager()`.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/simulationmanager/SimulationThread.java` — reflective manager construction.
- `experiment/src/com/mechalikh/pureedgesim/simulationmanager/PaperAlignedSimulationManager.java` — accounting, pending, manager class final.
- `experiment/src/com/mechalikh/pureedgesim/experiment/PaperAlignedMain.java` — custom manager registration.
- `configs/paper-aligned/applications.xml`, `configs/paper-aligned/simulation_parameters.properties` — workload/deadline/network/horizon.

## Pertanyaan yang belum terjawab

1. Apakah definisi kontribusi penelitian memang memilih destination baru untuk setiap task, atau menempatkan aplikasi per UE lalu menggunakan placement cache?
2. Apakah deadline Hard 20 ms, ukuran task, dan Cloud orchestrator mencerminkan asumsi paper yang hendak direplikasi?
3. Berapa banyak terminal failure/pending per application type dan berapa komponen delay network/queue/CPU? Raw artifact saat ini tidak cukup untuk menjawab.
4. Dari pending di cutoff, berapa yang akhirnya completed atau gagal deadline bila simulasi diteruskan?
5. Apakah kandidat di task-level perlu meliputi Cloud dan local execution, atau hanya EDC yang reachable?
6. Apakah metrik utama yang diinginkan completion sebelum horizon, deadline success, atau keduanya?
7. Apakah perlu mempertahankan manager paper-aligned saat custom manager task-level diperkenalkan, dan apakah perubahan modifier `final` dapat diterima pada modul eksperimen?

## Artefak bukti

`evidence/run_summary.csv` adalah ringkasan run lama; `evidence/failure_reason_counts.csv` adalah hitungan kategori agregat; `evidence/run_index.json` mempertahankan identitas run; file XML/properties adalah konfigurasi baseline yang relevan. Tidak ada repository penuh atau log mentah besar dalam ZIP.
