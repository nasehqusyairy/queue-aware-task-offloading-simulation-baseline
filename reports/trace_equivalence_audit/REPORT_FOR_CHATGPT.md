# Isolated Task Event Tracing dan Audit Ekuivalensi Trace-On/Trace-Off

Tanggal: 4 November 2026  
Repository: /home/nasyikhqusyairy/Projects/repositories/queue-aware-task-offloading-simulation-baseline  
Branch: main  
Commit awal yang dipakai kedua run: 03acb8635144a99b147b3d9e97017052cfaf4978  
Commit tidak dibuat dan tidak ada push.

## 1. Executive summary

Instrumentasi lifecycle task ditambahkan sebagai fitur eksperimen yang default-nya nonaktif. Trace-on menulis CSV terpisah; trace-off tidak membuat trace file dan menggunakan node/network model default. Tidak ada algoritma, deadline, network parameter, atau konfigurasi baseline yang diubah.

Dua pasangan run pendek dijalankan: Trade-Off dan Queue-Aware, masing-masing trace-off/trace-on, seed 4401, 10 UE, 1 detik, EDGE_DC_ONLY. Untuk kedua pasangan, seluruh metrics.json, seluruh sel Sequential_simulation.csv, seluruh destination assignments, dan pada Queue-Aware seluruh candidate/score/selection rows cocok. Float dibandingkan dengan toleransi absolut 1e-12. Run trace-on juga memvalidasi 145 task ID, 1.795 event, failure reason per task, pending events, dan rekonsiliasi ke summary simulator.

**Hasil ekuivalensi keseluruhan: INCONCLUSIVE untuk klaim strict per-task.** Semua output instrumentasi-independen yang tersedia cocok, tetapi trace-off tidak menyimpan terminal outcome per task ID. Karena itu identitas setiap task yang completed/failed tidak dapat dibandingkan langsung. Tidak ada perbedaan yang teramati pada output yang bisa dibandingkan; hasil ini tidak menyamakan count yang cocok dengan bukti terminal identity per task.

Temuan pengukuran utama: task delay simulator adalah accumulated network + queue + CPU, sedangkan simulation-clock elapsed tidak selalu sama dengan accumulated network delay. Contoh task 1: request-to-decision berlalu 0,060 s pada simulation clock, namun network-delay snapshot bertambah 0,136 s; result-return elapsed 0,120 s sedangkan accumulated network bertambah 0,277123 s. Source menunjukkan latency tiap hop ditambahkan ke task network accumulator, tetapi simulation event menunggu latency hanya pada hop terakhir. Ini adalah perilaku model aktual yang perlu diperhitungkan saat menafsirkan trace.

## 2. Repository, perubahan lokal, dan perlindungan hasil

Status awal: main...origin/main; satu-satunya perubahan awal adalah direktori reports/ untracked dari audit terdahulu. Source bersih pada commit di atas. Pembuatan branch gagal karena Git tidak dapat menulis refs ke metadata .git yang read-only; sesuai opsi perubahan lokal terpisah, perubahan dibatasi pada modul eksperimen dan script harness. Tidak ada file hasil lama yang ditimpa atau dihapus. Empat run final memiliki direktori baru di results/runs/.

Status akhir mencakup perubahan lokal source eksperimen, script analisis/test, dan laporan ini. Tidak ada commit/push.

Pemeriksaan package awal berhasil, tetapi eksekusi dependency:build-classpath pertama gagal sebelum simulator diluncurkan karena Maven mencoba menulis ~/.m2/repository/org/jacoco/resolver-status.properties pada filesystem read-only. Run final dijalankan ulang dengan Maven offline memakai cache yang tersedia. Manifest/metrics untuk percobaan setup gagal disertakan; tidak dihitung sebagai run simulasi.

## 3. Instrumentasi yang dilakukan

Perubahan source:

- experiment/src/com/mechalikh/pureedgesim/simulationmanager/PaperAlignedSimulationManager.java — trace writer opsional, event logging per task, accounting terminal/pending, flush/close pada PRINT_LOG.
- experiment/src/com/mechalikh/pureedgesim/experiment/PaperAlignedTaskGenerator.java — TASK_GENERATED pada simulation clock dan scheduled release time terpisah.
- experiment/src/com/mechalikh/pureedgesim/experiment/TaskTracingComputingNode.java — submission, queue enter/exit, CPU start/end.
- experiment/src/com/mechalikh/pureedgesim/experiment/TaskTracingQueueAwareComputingNode.java — hook queue/CPU untuk node Queue-Aware.
- experiment/src/com/mechalikh/pureedgesim/experiment/TaskTracingNetworkModel.java — destination arrival pada saat transfer TASK benar-benar sampai endpoint.
- experiment/src/com/mechalikh/pureedgesim/experiment/PaperAlignedMain.java dan QueueAwareMain.java — hanya memilih tracer node/network model saat flag tracing diberikan.
- experiment/src/com/mechalikh/pureedgesim/experiment/QueueAwareComputingNode.java — modifier final dihapus agar subclass tracer dapat memakai queue-workload implementation yang sama. Method execution/scoring tidak diubah.
- scripts/execute_run.py — PAPER_TASK_EVENT_TRACE mengaktifkan system property trace path dan mencatat flag di manifest.
- scripts/analyze_task_event_trace.py — validasi, timeline, komponen delay, deadline slack, failure reason, destination mapping, dan summary CSV.
- scripts/compare_trace_equivalence.py — perbandingan pasangan run yang konservatif.
- tests/test_task_event_trace.py — test validator.

Tidak ada source di simulator/PureEdgeSim yang diubah. Tidak ada perubahan algoritma Trade-Off, Round Robin, atau Queue-Aware.

### Trace enable/disable

- Default/off: jalankan run seperti biasa; jangan set PAPER_TASK_EVENT_TRACE. Tidak dibuat task_event_trace.csv dan tidak ada row per task.
- On: set PAPER_TASK_EVENT_TRACE=1 sebelum run. Harness meneruskan -Dpaper.task-event-trace=<run>/raw/task_event_trace.csv.
- File dibuat CREATE_NEW, UTF-8, comma-separated, header schema_version=1. Writer di-flush/close pada event PRINT_LOG normal. Run gagal sebelum PRINT_LOG dapat meninggalkan file belum tertutup secara eksplisit; ini keterbatasan lifecycle error path.
- Trace memakai simulation.clock dalam detik. Wall-clock tidak dipakai sebagai waktu simulasi.
- State trace adalah per-manager/per-node, tidak static/global. Hook hanya membaca Task, simulation clock, dan queue contents; tidak mengubah random generator, queue, event scheduling, atau task state.

## 4. Trace schema dan event definitions

Header utama memuat schema_version, task_id sebagai string CSV, event_name, timestamp_seconds, scheduled_release_time_seconds, application_id, task_type, source/destination ID dan layer, internal task status, failure_reason, stage, total_delay_seconds, network_delay_seconds, queue_wait_seconds, cpu_time_seconds, deadline_seconds.

| Event | Titik source | Arti |
|---|---|---|
| TASK_GENERATED | PaperAlignedTaskGenerator saat task object dibuat | Event generation pada simulation clock; scheduled_release_time terpisah |
| ORCHESTRATION_REQUEST | SEND_TO_ORCH setelah request dijadwalkan | Request orchestration dimulai |
| DESTINATION_DECISION | Manager setelah destination dipasang | Stage membedakan POLICY_SELECTED, CACHED_PLACEMENT_REUSED, POLICY_NO_DESTINATION |
| TASK_DISPATCH | Setelah request ke destination dijadwalkan | Dispatch dijadwalkan |
| DESTINATION_ARRIVAL | TaskTracingNetworkModel, akhir transfer Type.TASK | Task payload benar-benar tiba di endpoint destination |
| DESTINATION_EXECUTION_READY | Event EXECUTE_TASK di manager | Task siap disubmit ke compute node; dapat terjadi sesudah container transfer |
| TASK_SUBMISSION | Awal submitTask() pada compute node | Task masuk node execution |
| QUEUE_ENTER/QUEUE_EXIT | Queue list dan awal startExecution | Hanya untuk task yang benar-benar menunggu |
| EXECUTION_START/EXECUTION_END | startExecution/executionFinished | CPU lifecycle aktual |
| RESULT_RETURN | RESULT_RETURN_FINISHED | Result sudah mencapai source/UE, sebelum deadline check manager |
| TASK_COMPLETED/TASK_FAILED | Terminal counter transition | Satu terminal outcome; failed menyimpan FailureReason |
| TASK_PENDING_AT_HORIZON | PRINT_LOG untuk task generated nonterminal | Snapshot unresolved; tidak mengubah Task status/lifecycle |

TASK_GENERATED timestamp memakai clock saat object dibuat (semua pada 0.0 untuk run 1 detik ini); scheduled_release_time_seconds mencatat task.getTime(). Ini membedakan pembuatan objek dari release time scheduler.

Pada TASK_PENDING_AT_HORIZON, Task.Status internal masih bernilai SUCCESS pada object tertentu karena enum tersebut bukan state machine lifecycle. Event name/stage dan tidak adanya terminal event adalah penanda pending; instrumentation tidak mengubahnya menjadi FAILED.

## 5. Definisi dan perhitungan delay

Source yang ditelusuri:

- TaskAbstract.getTotalDelay(): actualNetworkTime + getWatingTime() + actualCpuTime.
- getWatingTime(): execution start - destination arrivalTime yang dicatat saat submitTask.
- DeadlinePolicy.isExceeded dipanggil di DefaultSimulationManager.taskFailed phase 3 pada saat RESULT_RETURN_FINISHED; equality juga failure.
- actualNetworkTime bertambah pada NetworkLink.updateTransfer dan transferFinished; result return sudah termasuk sebelum pengecekan deadline.

Script menghasilkan:
- request event elapsed = t_decision - t_orchestration_request (simulation clock);
- request network delay = network snapshot di decision dikurangi snapshot saat request;
- dispatch elapsed dan network accumulator delta;
- destination arrival-to-submit interval, termasuk container pre-submit bila ada;
- queue wait dari queue exit-entry (hanya task antre);
- CPU dari execution end-start;
- result return elapsed dan network accumulator delta;
- total delay dan deadline slack = deadline - total delay pada terminal event;
- generation-to-terminal elapsed sebagai observasi terpisah, bukan pengganti definisi deadline.

Komponen event elapsed/network accumulator tidak dijumlahkan satu sama lain karena keduanya dua observasi berbeda atas perjalanan yang overlap. Validasi memastikan pada tiap task terminal total_delay = network_delay + queue_wait + cpu_time dengan toleransi absolut 1e-12.

## 6. Konfigurasi dan command equivalence

Keempat run memakai konfigurasi setara: paper-aligned-baseline, Trade-Off atau Queue-Aware, 10 UE, 1 simulated second, EDGE_DC_ONLY (architecture EDGE_ONLY), seed 4401, deadline/network defaults unchanged. App groups [2,3,5], generator menghasilkan 145 task (40 Hard, 90 Soft, 15 Non-RT). Tujuan output baru per run di results/runs/.

Perintah aktual:
- PATH=/tmp/task-trace-bin:$PATH env -u PAPER_TASK_EVENT_TRACE ./run.sh --profile paper-aligned-baseline --method trade-off --devices 10 --duration-seconds 1 --destination-config EDGE_DC_ONLY --seed 4401
- PATH=/tmp/task-trace-bin:$PATH PAPER_TASK_EVENT_TRACE=1 ./run.sh --profile paper-aligned-baseline --method trade-off --devices 10 --duration-seconds 1 --destination-config EDGE_DC_ONLY --seed 4401
- Pasangan kedua menjalankan dua command setara dengan --method queue-aware.

Wrapper Maven hanya menambahkan mode offline untuk menghindari penulisan ke cache read-only; tidak mengubah classpath/source/config.

| Method | Trace off run ID | Trace on run ID | Runtime status |
|---|---|---|---|
| Trade-Off | 20261103T170846524194007_paper-aligned-baseline_trade-off_10ue_EDGE_DC_ONLY_seed4401 | 20261103T170855452417767_paper-aligned-baseline_trade-off_10ue_EDGE_DC_ONLY_seed4401 | completed, exit 0, validation errors 0 |
| Queue-Aware | 20261103T170907504227571_paper-aligned-baseline_queue-aware_10ue_EDGE_DC_ONLY_seed4401 | 20261103T170916785099633_paper-aligned-baseline_queue-aware_10ue_EDGE_DC_ONLY_seed4401 | completed, exit 0, validation errors 0 |

## 7. Hasil trace-on/trace-off

Comparator memeriksa:
- identitas config, seed, method, architecture, simulator properties dan configuration hashes;
- seluruh key/value metrics.json selain run_id/source;
- seluruh cell simulator Sequential_simulation.csv;
- seluruh destination audit CSV, termasuk task IDs dan assignment sequence;
- seluruh queue_decisions.csv bila tersedia;
- trace-off tidak membuat task_event_trace.csv dan trace-on membuat file;
- absolute float tolerance 1e-12.

Kedua pasangan mempunyai measurable_outputs_equivalent=true dan errors kosong. Jadi seluruh ringkasan/keputusan independen trace yang tersedia cocok. Status comparator keseluruhan INCONCLUSIVE karena trace-off memang tidak menyimpan terminal status/failure identity per task ID; identitas terminal tiap task tidak dapat dibandingkan langsung. Task counts dan failure reason counts saja tidak cukup untuk mengangkat keterbatasan itu.

| Metrik (sama pada keempat run) | Nilai |
|---|---:|
| Generated / sent | 145 / 145 |
| Completed | 6 |
| Terminal failed | 130 |
| Pending saat cutoff | 9 |
| Success = completed/generated | 4,1379% |
| Average CPU execution time | 0,1195 s |
| Average completed-task total delay | 5,576615 s |
| Average completed-task waiting time | 0 s |
| Energy consumption | 0,3189 Wh |
| Destination layer | 145 ke Edge Data Center |

Tidak dijalankan matriks penelitian. Ini hanya diagnostic 1 detik, satu seed, satu destination config, dan dua policy agar jalur trace baseline serta Queue-Aware teruji.

## 8. Hasil delay dan failure dari task trace

Trace validation pada tiap trace-on run:
- 1.795 records, 145 task IDs, no missing/invalid timestamps, no duplicate terminal, no contradictory terminal+pending, timestamp nondecreasing.
- 145 TASK_GENERATED, request, destination assignment, dispatch, destination arrival, submission, dan execution start.
- 109 QUEUE_ENTER dan 109 QUEUE_EXIT.
- 136 EXECUTION_END dan RESULT_RETURN; 6 completed + 130 failed = 136 terminal.
- 9 TASK_PENDING_AT_HORIZON; semua memiliki EXECUTION_START sebagai event terakhir sebelumnya, jadi saat cutoff masih executing.
- FailureReason pada 130 terminal failure adalah FAILED_DUE_TO_LATENCY. Raw Sequential_simulation.csv cocok: delay 130, device-dead 0, mobility 0, resources 0.
- 145 destination assignment events cocok persis urutannya ke destinations.csv.
- Trace schema v1 dan CSV dapat dibaca analyzer; summary accounting cocok dengan manifest.

Komponen rata-rata per application profile, dihitung sebagai mean event/component pada cohort yang memiliki timestamp terkait. Queue wait di bawah hanya cohort yang masuk antrean; total_delay mean hanya task terminal:

| Type | Tasks / terminal outcome | Request elapsed clock | Request network accumulator delta | Dispatch elapsed clock | Dispatch network delta | Queue wait observed | CPU execution | Result elapsed clock | Result network delta | Mean terminal total delay |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Hard RT | 40 / 40 failed | 0,060 s | 0,136 s | 0,005 s | 0,141123 s | 0,0125 s | 0,0125 s | 0,120 s | 0,277123 s | 0,572996 s |
| Soft RT | 90 / 90 failed | 0,060 s | 1,320 s | 0,023333 s | 1,329487 s | 0,159375 s | 0,125 s | 0,120 s | 0,323538 s | 3,239692 s |
| Non-RT | 15 / 6 completed, 9 pending | 0,060 s | 2,120 s | 0,038 s | 2,128154 s | 0,375 s | 0,750 s | 0,120 s | 0,566231 s | 5,576615 s (6 completed saja) |

Request elapsed clock bukan pure policy-computation overhead: ia mengukur event simulation-clock dari pengiriman request sampai decision event dan mencakup waktu event/network yang berjalan dalam simulator. Network accumulator delta merupakan perbedaan actualNetworkTime snapshot pada dua boundary; nilainya termasuk transfer delay dan latensi hop yang ditagihkan pada task. Selector berjalan sinkron dan wall-clock Java untuk policy tidak masuk simulated time.

Contoh task ID 1:
- Request mulai 0.000 s; destination decision 0.060 s; request network accumulator +0.136 s.
- Dispatch 0.060 s; destination arrival 0.065 s; network accumulator +0.141123 s.
- CPU start 0.065 s; end 0.0775 s.
- Result return dan terminal failure pada 0.1975 s.
- Total delay task saat terminal 0.566746 s, terdiri network 0.554246 + queue 0 + CPU 0.0125. Deadline Hard 0.02 s; failure reason FAILED_DUE_TO_LATENCY.
- Total delay deadline metric jauh di atas simulation-clock elapsed generation-to-terminal 0.1975 s. Ini akibat network accumulator dan event-clock hop scheduling berbeda di source.

Destination stage menunjukkan 10 POLICY_SELECTED dan 135 CACHED_PLACEMENT_REUSED dari 145 task assignment events, pada dua method ini. Ini konsisten dengan decision cadence application placement/reuse yang telah diaudit; trace mencatat assignment setiap task dan membedakan saat selector benar-benar dipanggil.

## 9. Perbedaan/risiko dan keterbatasan

- Tidak ada perbedaan pada output aggregate, energy, delay, destination rows, atau Queue-Aware candidate decision rows yang dibandingkan. Tidak ada perbedaan event/decision sequence pada destination audit.
- Per-task terminal identity trace-on tidak dapat dicocokkan dengan trace-off, karena trace-off dilarang menulis log per task dan output baseline tidak menyimpan terminal task IDs. Ini sebab status keseluruhan INCONCLUSIVE.
- Trace tidak menyimpan setiap network hop sebagai event; network component stage adalah delta actualNetworkTime snapshots di event boundaries. Untuk per-hop latency/bandwidth decomposition, diperlukan instrumentation lain pada NetworkLink.
- TASK_GENERATED object dibuat saat generator berjalan dan timestamp simulation clock-nya 0; scheduled_release_time ditulis terpisah. Tidak ada generasi dinamis selama simulasi pada generator profile ini.
- Pending object dapat menampilkan Task.Status SUCCESS karena status enum tidak membedakan pending; event TASK_PENDING_AT_HORIZON dan absence of terminal adalah outcome analisis, tanpa mutasi object.
- Satu seed/durasi pendek tidak mendukung klaim generalisasi performa atau Queue-Aware benefit.
- Logger menulis synchronous CSV. Comparison ini menunjukkan ringkasan, decisions, dan queue candidate rows tetap sama pada pasangan yang diuji, tetapi tidak membuktikan zero wall-clock overhead atau seluruh kemungkinan interleaving pada semua ukuran/runs.
- Equivalence pairs memakai same source commit awal, config, seed, policy. Trace instrumentation merupakan working-tree change yang sama di kedua run. Tidak ada baseline parameter atau policy yang dituning.

## 10. Test yang dijalankan

- python3 -m py_compile scripts/execute_run.py scripts/analyze_task_event_trace.py scripts/compare_trace_equivalence.py — pass.
- python3 -m pytest -q tests/test_task_event_trace.py tests/test_paper_experiment.py — 12 passed, 6 subtests passed.
- Dua trace-on diagnostic run: exit 0, per-run validation errors 0.
- Dua trace validator runs: valid=true; accounting, failure reason, destination event sequence checks match.
- Dua equivalence comparisons: no compared-output differences; measurable_outputs_equivalent=true, strict status INCONCLUSIVE sesuai keterbatasan terminal identity.
- Full test suite tidak dijalankan.

## 11. Rekomendasi

1. Pakai event trace ini untuk diagnostic deadline/network kecil berikutnya; pertahankan task IDs, trace schema, dan configuration manifest.
2. Untuk klaim strict per-task equivalence, sediakan mekanisme pembanding terminal identity yang tidak menulis per-task trace di trace-off run atau lakukan observational proof yang terpisah dan terdokumentasi. Jangan mengubah status INCONCLUSIVE menjadi PASS berdasarkan aggregate counts.
3. Investigasi mismatch antara simulation-clock elapsed dan Task.getTotalDelay pada multi-hop: NetworkLink.transferFinished menambah per-hop latency ke task accumulator tetapi hanya menjadwalkan delay simulasi pada hop terakhir. Jangan ubah semantics sebelum memutuskan estimand deadline yang hendak diuji.
4. Trace-hop breakdown dapat ditambahkan kemudian jika perlu menjawab queue vs propagation/bandwidth contributions; current stage deltas sudah memisahkan request, dispatch, queue, CPU dan return tanpa menambah run matrix.

## 12. File/method/line references

- `experiment/src/com/mechalikh/pureedgesim/simulationmanager/PaperAlignedSimulationManager.java`: constructor/header and optional writer, lines 39–70; event interception for orchestration, dispatch, execution-ready, result return, and horizon close, lines 72–155; generated event and pending-at-horizon record, lines 165–205; terminal event accounting, lines 244–254; destination audit decision, lines 257–280; writer close, lines 305–314.
- `experiment/src/com/mechalikh/pureedgesim/experiment/PaperAlignedTaskGenerator.java`: task timestamp/release and `recordTaskGenerated`, lines 84–90.
- `experiment/src/com/mechalikh/pureedgesim/experiment/TaskTracingComputingNode.java`: submission/queue entry, lines 21–29; queue exit/CPU start/end, lines 31–48. `TaskTracingQueueAwareComputingNode.java` has corresponding hooks at lines 20–47.
- `experiment/src/com/mechalikh/pureedgesim/experiment/TaskTracingNetworkModel.java`: final TASK endpoint arrival hook, lines 14–23.
- `experiment/src/com/mechalikh/pureedgesim/experiment/PaperAlignedMain.java`: tracing-only node/network selection, lines 9–20. `QueueAwareMain.java`: Queue-Aware tracing/default node selection, lines 10–23.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/simulationmanager/DefaultSimulationManager.java`: `processEvent()` lines 158–203; task dispatch/submission routes lines 277–338; `taskFailed()` and deadline phase 3 lines 360–410.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/network/DefaultNetworkModel.java`: `processEvent()` lines 45–76; request/task/result routing in `transferFinished()` lines 177–236.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/network/NetworkLink.java`: `updateTransfer()` and per-hop progress lines 128–160; `transferFinished()` lines 163–184.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/datacentersmanager/DefaultComputingNode.java`: `submitTask()` lines 222–236; `startExecution()` lines 238–269; `executionFinished()` lines 275–303.
- `simulator/PureEdgeSim/PureEdgeSim/com/mechalikh/pureedgesim/taskgenerator/TaskAbstract.java`: `getWatingTime()` lines 180–183 and `getTotalDelay()` lines 199–206.
- `scripts/execute_run.py`: `PAPER_TASK_EVENT_TRACE` parsing, manifest flag, Java system property, lines 200–211.
- `scripts/analyze_task_event_trace.py`: `analyze_rows()` validation and timeline construction, lines 52–140; CSV/manifests/source-summary reconciliation, lines 249–335.
- `scripts/compare_trace_equivalence.py`: run identity, output comparisons, and conservative INCONCLUSIVE status, lines 62–113.
- `tests/test_task_event_trace.py`: validator cases, lines 1–61.

Line references correspond to the current local working tree at report creation; they may shift if these uncommitted changes are edited.

## 13. Artefak

- evidence/tradeoff/ and evidence/queue_aware/ — config manifests, raw trace-on CSV, trace-off/on simulator summaries, destination audits, console logs, Queue-Aware decision audit, validation/timeline/summary output, comparison JSON.
- evidence/scripts/ — analyzer and comparator copies.
- evidence/tests/ — validator tests.
- evidence/regression_tests.log — captured test output.
- evidence/initial_maven_setup_attempt_manifest.json and metrics — failed setup attempt before simulator start.
- REPORT_FOR_CHATGPT.md and ZIP root content list.

Output trace tidak dicampur ke Sequential_simulation.csv dan tidak mencakup repository penuh.

