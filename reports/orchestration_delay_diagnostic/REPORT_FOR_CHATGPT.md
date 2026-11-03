# Diagnostic Trace untuk Orchestration Overhead dan Task Delay

Tanggal pemeriksaan: 3 November 2026  
Repository: /home/nasyikhqusyairy/Projects/repositories/queue-aware-task-offloading-simulation-baseline  
Branch: main  
Commit: 03acb8635144a99b147b3d9e97017052cfaf4978  
Status awal: main...origin/main; reports/ adalah artefak audit untracked sebelumnya. Tidak ada source/config baseline diubah dan tidak ada simulasi baru dijalankan.

## 1. Executive summary

- Run terdahulu tidak memiliki timestamp per-task dari generation sampai terminal state. Tidak ada nilai valid untuk orchestration elapsed, network request, dispatch, queue, CPU, result return, atau deadline slack per task; laporan ini tidak membuat nilai sintetis.
- Request orchestration dikirim untuk setiap task. Dengan deploy_orchestrator=CLOUD, request pergi dari UE ke Cloud sebelum dispatch. Cache UE hanya melewati pemanggilan algoritma pemilih destination; cache tidak melewati request network ke Cloud.
- Shared WAN topologi menghubungkan UE ke router WAN dan router ke Cloud. Link UE→router dibuat sebagai Wi-Fi link bertipe WAN; NetworkLinkWifiUp mengatur latency ke wan_latency. Router→Cloud juga WAN. Kode/config membentuk dua link WAN pada rute UE→Cloud, masing-masing 60 ms. Ini konsekuensi topology builder, bukan pengukuran hop trace per-task.
- Task.getTotalDelay() menjumlah actualNetworkTime + waitingTime + actualCpuTime. Request network ke orchestrator ikut menambah actualNetworkTime. Deadline diuji ketika RESULT_RETURN_FINISHED tiba, bukan sebagai timer saat generation/queue. Task pending pada cutoff belum menjalani terminal deadline check.
- Sembilan run matriks seed 1 sebelumnya selesai dan accounting aggregate valid; semua terminal failures masuk kategori delay. Data tersebut tidak mengisolasi komponen delay atau failure per tipe aplikasi.
- Instrumentation tidak ditambahkan: trace lengkap perlu hook event manager, transfer network, compute node, serta ekspor terminal/pending. Tanpa paired equivalence check, logger baru belum dapat disebut non-intrusive. Lokasi dan rencana minimum dicantumkan di bawah. Pembuatan branch gagal karena Git tidak dapat menulis ref di metadata repository; tidak ada perubahan kode lokal.

## 2. Repository dan hasil terdahulu

Laporan yang diperiksa:
- reports/queue_aware_lifecycle_audit/REPORT_FOR_CHATGPT.md
- reports/task_level_offloading_design_audit/REPORT_FOR_CHATGPT.md

Sembilan run seed 1 yang dirujuk ialah 10/20/30 UE × Trade-Off/Round Robin/Queue-Aware, 200 detik, EDGE_DC_ONLY. Manifest completed dan accounting aggregate direkonsiliasi. Tidak ada trace event/task individual. Smoke run seed berbeda tidak digabungkan.

Percobaan git switch -c codex/orchestration-delay-diagnostic gagal: Git tidak dapat membuat direktori refs/heads/codex/... di metadata .git. Branch tetap main.

## 3. Tujuan dan status diagnostic run

Diagnostic trace baru tidak dijalankan. Harness saat ini menghasilkan summary aggregate, destination dan queue audit, bukan lifecycle trace per-task. Tidak ada status/error run baru.

Usulan di evidence/diagnostic_plan.json: paper-aligned baseline, EDGE_DC_ONLY, 10 UE, 1 detik, seed 1, app-user allocation [2,3,5], 145 task. Belum dijalankan. Generator tidak bisa membuat tepat satu task per application type dari opsi yang ada: rate 20/30/3 per UE per detik. Durasi integer 1 detik mengurangi volume tanpa mengubah rate. Tidak ada parameter baseline yang diubah.

## 4. Definisi timestamp dan komponen delay

Method yang memakai simulation.clock()/getSimulation().clock() memakai simulation clock dalam detik. Task.getTime() generator adalah integer second, bukan timestamp event yang diekspor. Raw lama tidak menyimpan event timestamps.

| Label analisis | Event/method aktual | Ketersediaan di raw lama |
|---|---|---|
| t_generate | generator membuat task; task.setTime(second) | Tidak per-task |
| t_orchestration_request | SEND_TO_ORCH lalu sendTaskToOrchestrator | Tidak per-task |
| t_decision | SEND_TASK_FROM_ORCH_TO_DESTINATION, lalu orchestrate(task) bila placement belum ada | Tidak per-task |
| t_dispatch | scheduleNow SEND_REQUEST_FROM_ORCH_TO_DESTINATION setelah destination dipilih | Tidak per-task |
| t_destination_arrival | EXECUTE_TASK setelah transfer task dan mungkin container download | Tidak per-task |
| t_queue_enter | DefaultComputingNode.submitTask; hanya saat tidak dapat langsung start | Tidak per-task |
| t_queue_exit | startExecution ketika task queued mulai; task langsung start tidak antre | Tidak per-task |
| t_execution_start/end | Task execution time setters | Tersedia pada object saat run, tidak diekspor per task |
| t_result_arrival | RESULT_RETURN_FINISHED setelah result path ke UE | Tidak per-task |
| t_terminal | completion counter atau setFailed; deadline diuji saat result return | Aggregate saja |
| deadline | task.getMaxLatency() dari profil aplikasi | Config diketahui, tidak tergabung ke terminal rows |

Deadline aktual ialah task.getTotalDelay() >= task.getMaxLatency(); total delay = accumulated network + queue waiting + CPU. Ini bukan current_simulation_time - t_generate. Waktu sebelum request pertama tidak dihitung sebagai komponen terpisah; transfer request sendiri masuk network time. Deadline diuji pada phase 3 setelah result mencapai UE. Pending belum diuji sebagai terminal delay failure.

Komponen tidak boleh dihitung dua kali: t_decision - t_orchestration_request mencakup request network ke orchestrator; ia merupakan bagian network delay. t_result_arrival - t_execution_end mencakup result network destination→orchestrator→UE. Timestamp transfer boundaries diperlukan untuk memecahnya.

## 5. Konfigurasi diagnostic dan network path

Fakta config:
- simulation_parameters.properties: enable_orchestrators=true, deploy_orchestrator=CLOUD, one_shared_wan_network=true, wan_latency=0.06 s, wan_bandwidth=20 Mbps, wifi_latency=0.005 s, wifi_bandwidth=1300 Mbps, realistic_network_model=false, wait_for_all_tasks=false, horizon 200 s.
- applications.xml: Hard RT 0.02 s; Soft RT 0.5 s; Non-RT 300 s.

Fakta kode: DefaultTopologyCreator membuat shared WAN node, menghubungkan UE ke WAN node dan WAN node ke Cloud/dc1. Jika connectivity UE Wi-Fi, connect(..., WAN) memakai NetworkLinkWifiUp bertipe WAN; constructor itu menetapkan latency wan_latency dan bandwidth=min(wan,wifi). Router→Cloud menggunakan NetworkLinkWanUp dengan WAN latency. Rute UE→Cloud karenanya mempunyai UE–WAN router dan WAN router–Cloud links. Transfer bandwidth dapat menambah delay; realistic_network_model=false tidak menghilangkan latency hop.

| Tahap | Path source | Parameter |
|---|---|---|
| Request UE→Cloud | UE→shared WAN router→Cloud | WAN 60 ms per link; access link bertipe WAN menggunakan WAN latency |
| Dispatch Cloud→EDC | shortest path Cloud→WAN router→edge datacenter graph | WAN hop(s), tergantung destination |
| Return EDC→Cloud→UE | destination ke orchestrator, lalu orchestrator ke UE | latency dan transfer tiap hop terakumulasi |
| CPU | task_length / MIPS per core | app profile dan node capacity |

Tidak tersedia path/hop list task aktual. Klaim dua links UE→Cloud adalah konsekuensi source topology dan config, bukan pengamatan trace per-task.

## 6. Hasil task-level trace

Tidak ada row trace per-task. Semua waktu dan failure attribution per task unavailable, bukan perkiraan. Hasil low terdahulu: 29.000 generated, 2.994 completed, 25.977 terminal delay failures, 29 pending. Medium/high juga menandai seluruh terminal failures sebagai delay. Data tidak mengisolasi app type, network, queue, CPU, request atau return.

## 7. Analisis orchestration overhead

Fakta kode:
1. Orchestrator Cloud dikonfigurasi; task generator mengikat UE/task ke Cloud.
2. Setiap SEND_TO_ORCH memanggil sendTaskToOrchestrator(), menambah tasksSent, kemudian menjadwalkan SEND_REQUEST_FROM_DEVICE_TO_ORCH.
3. DefaultNetworkModel mengirim TransferProgress.Type.REQUEST ke orchestrator. Saat request sampai, manager mendapat event untuk dispatch.
4. sendFromOrchToDestination memeriksa cached placement. Jika belum ada, selector memilih destination; jika ada, destination cache dipakai. Kedua jalur menjadwalkan task ke destination.
5. NetworkLink menambah transmission delay dan hop latency ke Task.actualNetworkTime. Request Cloud masuk deadline calculation. Selector berjalan sinkron; waktu CPU Java/wall-clock selector tidak dimasukkan ke simulated time.

Jawaban:
- Orchestrator di Cloud menurut config.
- Request WAN terjadi per task sebelum destination gate.
- Deadline meliputi request network, dispatch, container download jika ada, return result, queue, CPU. Selector CPU time tidak dimodelkan.
- Request dibayar per task; selector hanya initial placement/re-placement saat application placement invalid.
- Task-level selector menambah policy computation per task yang tidak dimodelkan saat ini. Itu tidak otomatis menambah network request baru karena request uplink sudah per task.
- Queue state dapat dibaca saat SEND_TASK_FROM_ORCH_TO_DESTINATION, setelah request tiba dan sebelum dispatch. State dapat berubah sebelum task tiba.
- Request UE→orchestrator adalah one-way. Tidak ada pesan response keputusan; orchestrator langsung menjadwalkan task dispatch. Lifecycle setelahnya mencakup dispatch dan result return.
- Transfer link eksplisit; selector processing time tidak.

Tidak ada observasi trace baru atau nilai numerik overhead langsung.

## 8. Diagnosis network, queue, CPU, dan failure

| Tahap | Bukti | Batas kesimpulan |
|---|---|---|
| Sebelum destination decision | Request network dimulai sebelum decision dan terakumulasi | Tidak ada delay delta per task saat decision |
| Request/dispatch network | NetworkLink menambah delay; route UE ke Cloud melalui shared WAN | Tiada transfer timestamps/hop trace per task |
| Queue | DefaultComputingNode memakai FIFO bila tidak bisa langsung start; queue tidak dibatasi | Tidak tersedia queue wait per task |
| CPU | Execution start/end tersimpan di Task; durasi memakai length/MIPS | Tidak diekspor per task |
| Result | EDC→orchestrator→UE; arrival memicu phase 3 | Return delay per task unavailable |
| Pending | Horizon menghitung generated-completed-failed | Tidak ada task ID/stage saat cutoff |
| Failure lama | Semua terminal failure delay; resource/dead/mobility/pre-pipeline zero pada matriks | Aggregate, bukan component attribution |

Path UE→Cloud mempunyai dua links WAN dengan konfigurasi 60 ms, jadi request saja secara nominal mencakup 120 ms propagation sebelum transmission delay. Hard deadline 20 ms tidak kompatibel secara struktural untuk task yang memakai path tersebut. Ini inferensi topology/config, bukan nilai observed task row atau jumlah Hard failures.

## 9. Validitas pengukuran

- Event clock source sama-sama simulation clock dalam detik; tanpa trace, kesamaan tidak diverifikasi empiris.
- Task ID dibuat generator dan ada di destination/queue decision logs, tetapi tidak terhubung ke terminal row.
- Manager mendeduplikasi terminal task IDs, namun duplicate timestamp tidak bisa diaudit.
- Aggregate accounting run terdahulu valid: generated = completed + failed + pending.
- Tidak ada instrumentation, maka tidak ada klaim non-intrusive.
- Instrumentation nanti harus diuji paired trace-off/trace-on dengan config/seed sama, membandingkan destinations, terminal counters, network/CPU summaries dan event ordering. Synchronous log dapat menambah wall-time atau gagal I/O meski tidak mengubah simulation clock.

## 10. Implikasi custom SimulationManager task-level

Call path aktual:
Task generation/NEXT_BATCH → SEND_TO_ORCH → DefaultSimulationManager.sendTaskToOrchestrator → request network UE→Cloud → SEND_TASK_FROM_ORCH_TO_DESTINATION → sendFromOrchToDestination → selector jika belum placed atau cached destination jika sudah → task dispatch Cloud→destination → EXECUTE_TASK/submitTask → queue atau CPU → result destination→orchestrator→UE → RESULT_RETURN_FINISHED/deadline/success/failure.

SimulationAbstract.setCustomSimulationManager menerima manager yang extend DefaultSimulationManager; SimulationThread membangun via constructor (SimLog, PureEdgeSim, int, int, Scenario). sendFromOrchToDestination(Task) protected dan overridable; hook dipanggil setiap task yang mencapai dispatch, setelah request network ke orchestrator dan sebelum dispatch ke destination.

Task-level selection tidak perlu mengubah generation, queue, CPU, atau result lifecycle. Custom manager dapat mengganti cache gate dan menjaga phase checks, no-destination handling, dan dispatch. PaperAlignedSimulationManager final; manager eksperimen baru perlu extend DefaultSimulationManager atau accounting perlu dirancang ulang untuk reuse. Tidak dilakukan di sini. Pisahkan decision logic dari dispatch agar Trade-Off/RR/QA menggunakan call point dan opportunity yang setara.

## 11. Fakta, inferensi, unknown

Fakta kode/config:
- Cloud orchestrator aktif; tiap task mengirim request network sebelum destination gate.
- UE→Cloud shared WAN memakai WAN-type UE access link dan router-cloud WAN link.
- Deadline = network + queue + CPU; diuji saat result kembali.
- Placement cache melewati selector, bukan request.

Fakta run:
- 9 matriks seed1/horizon200 completed; accounting konsisten.
- Semua terminal failure berlabel delay; tidak ada trace per-task.

Inferensi:
- Hard 20 ms tidak kompatibel dengan request path nominal dua WAN link 60 ms: request network sendiri melampaui deadline sebelum dispatch/queue/CPU/result. Dasarnya topology/config, bukan observed trace.
- Low tidak tampak CPU-overload-driven saja (CPU EDC aggregate terdahulu sekitar 57,5%); deadline/network mismatch kandidat kuat. Failure app type belum diketahui.

Belum diketahui:
Actual hop/delay per task, queue/CPU per task, deadline slack, terminal state per app, pending stage, wall-clock policy runtime, serta apakah instrumentation mengubah hasil.

## 12. Rekomendasi

1. Buat instrumentation terpisah pada modul eksperimen. Hook generator; manager SEND_TO_ORCH, SEND_TASK_FROM_ORCH_TO_DESTINATION, EXECUTE_TASK, RESULT_RETURN_FINISHED dan horizon; DefaultNetworkModel awal/akhir transfer request/task/result; compute node submitTask, queue add/start, execution finish. Simpan keyed by task ID dan ekspor pending stage.
2. Trace minimal memuat ID/type/app/source, orchestrator/destination, event time, transfer type/hop path/latency, queue transitions, CPU start/end, failure reason+phase, max latency, terminal/pending.
3. Tandai request-to-decision sebagai elapsed yang overlap network; jangan dijumlah dua kali.
4. Diagnostic pendek yang diusulkan di evidence/diagnostic_plan.json: 1 detik, 10 UE, groups [2,3,5], seed1, EDGE_DC_ONLY, 145 task. Bukan tepat satu task per type.
5. Jalankan paired trace off/on sebelum klaim logger non-intrusive. Bandingkan decisions, counts, network/CPU aggregates, event order.
6. Setelah valid, periksa cohort singkat tiap app type, lalu durasi sedikit lebih lama untuk queue contention. Jangan mulai matriks besar dulu.
7. Bandingkan semua policy pada satu manager decision hook per task. Ukur selector wall-clock terpisah; simulator saat ini tidak memodelkan policy CPU time.

## 13. Referensi file/method/lines

- experiment/src/com/mechalikh/pureedgesim/experiment/PaperAlignedTaskGenerator.java — generate(), rate, app ID, task time.
- experiment/src/com/mechalikh/pureedgesim/simulationmanager/PaperAlignedSimulationManager.java — processEvent(), horizon accounting, aggregate logs.
- experiment/src/com/mechalikh/pureedgesim/experiment/QueueAwareComputingNode.java — startExecution(), executionFinished().
- simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/simulationmanager/DefaultSimulationManager.java — processEvent 158-203; sendFromOrchToDestination 294-322; sendTaskToOrchestrator 329-338; taskFailed 360-410; setFailed 419-435.
- simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/network/DefaultNetworkModel.java — send 76-126; request 165-175; transfer dispatch 177-218; result routing.
- simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/network/NetworkLink.java — updateTransfer 128-160; transferFinished 163-182.
- simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/datacentersmanager/DefaultComputingNode.java — submitTask 221-236; startExecution 238-269; executionFinished 275+.
- simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/taskgenerator/TaskAbstract.java — waiting/total delay 180-206; execution setters 211-232.
- simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/datacentersmanager/DefaultTopologyCreator.java — WAN topology 80-120; createWanLink 129-154; connect 227-265.
- NetworkLinkWifiUp.java — WAN-type Wi-Fi access latency/bandwidth; NetworkLinkWanUp/Down.java — WAN values.
- SimulationAbstract.java — setCustomSimulationManager 168-176; SimulationThread.java — reflection constructor 124-128.
- configs/paper-aligned/applications.xml and simulation_parameters.properties — deadline/network/orchestrator/horizon.

## 14. Artefak

- evidence/timestamp_map.csv — event mapping and raw availability.
- evidence/diagnostic_plan.json — proposed run, not executed.
- evidence/previous_run_summary.csv — prior aggregate metrics.
- evidence/previous_failure_reason_counts.csv — prior failure categories.
- evidence/paper_aligned_applications.xml and paper_aligned_simulation_parameters.properties — baseline copies.
- evidence/commands_executed.txt — inspection commands and failed branch attempt.

Tidak ada console log diagnostic baru atau raw task trace karena run tidak dilakukan.

