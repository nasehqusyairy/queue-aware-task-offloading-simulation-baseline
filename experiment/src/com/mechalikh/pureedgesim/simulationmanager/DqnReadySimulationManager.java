package com.mechalikh.pureedgesim.simulationmanager;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode;
import com.mechalikh.pureedgesim.simulationengine.Event;
import com.mechalikh.pureedgesim.simulationengine.PureEdgeSim;
import com.mechalikh.pureedgesim.scenariomanager.Scenario;
import com.mechalikh.pureedgesim.taskgenerator.Task;
import com.mechalikh.pureedgesim.experiment.OffloadingObservation;

/** Isolated manager that requests a fresh policy destination at every task dispatch. */
public final class DqnReadySimulationManager extends PaperAlignedSimulationManager {
    private static final class Decision {
        final OffloadingObservation observation;
        final List<Integer> candidateIds;
        final boolean[] mask;
        final int action;
        final int selectedEdcId;

        Decision(OffloadingObservation observation, List<Integer> candidateIds, boolean[] mask,
                int action, int selectedEdcId) {
            this.observation = observation;
            this.candidateIds = List.copyOf(candidateIds);
            this.mask = mask.clone();
            this.action = action;
            this.selectedEdcId = selectedEdcId;
        }
    }

    private final Map<Integer, Decision> decisions = new HashMap<>();
    private final Map<Integer, Boolean> cachedBeforeDispatch = new HashMap<>();
    private final Map<Integer, Integer> cachedDestinationBeforeDispatch = new HashMap<>();
    private final java.util.Set<Integer> cacheBypassTasks = new java.util.HashSet<>();
    private final java.util.Set<Integer> finalizedDecisionIds = new java.util.HashSet<>();
    private BufferedWriter decisionWriter;
    private BufferedWriter ledgerWriter;

    public DqnReadySimulationManager(SimLog log, PureEdgeSim engine, int simulationId, int iteration, Scenario scenario) {
        super(log, engine, simulationId, iteration, scenario);
        decisionWriter = open("paper.per-task-decision-log", "task_id,simulation_timestamp_seconds,source_ue_id,selected_action,selected_edc_id,candidate_edc_ids,action_mask,task_mi,task_mi_normalized,input_size_bits,input_size_normalized,deadline_seconds,deadline_normalized,queue_length_per_edc,queue_length_normalized_per_edc,active_tasks_per_edc,active_tasks_normalized_per_edc,estimated_queue_wait_seconds_per_edc,estimated_queue_wait_normalized_per_edc,mips_per_core_per_edc,mips_per_core_normalized_per_edc,cpu_cores_per_edc,cpu_cores_normalized_per_edc,cpu_utilization_percent_per_edc,cpu_utilization_normalized_per_edc,resource_available_per_edc,cache_bypassed,cached_placement_existed,cached_placement_destination_id,decision_source,actual_applied_destination_id,decision_status");
        ledgerWriter = open("paper.per-task-ledger-log", "task_id,event_name,timestamp_seconds,source_ue_id,destination_id,status,failure_reason,total_delay_seconds,network_delay_seconds,queue_wait_seconds,cpu_execution_seconds,stage");
    }

    @Override
    protected void sendFromOrchToDestination(Task task) {
        boolean wasCached = task.getEdgeDevice().isApplicationPlaced();
        cachedBeforeDispatch.put(task.getId(), wasCached);
        ComputingNode cachedDestination = task.getEdgeDevice().getApplicationPlacementLocation();
        cachedDestinationBeforeDispatch.put(task.getId(), cachedDestination == null || cachedDestination == ComputingNode.NULL
                ? -1 : cachedDestination.getId());
        cacheBypassTasks.add(task.getId());
        // This isolated policy mode deliberately bypasses the UE placement gate for every task.
        task.getEdgeDevice().setApplicationPlaced(false);
        super.sendFromOrchToDestination(task);
    }

    /** Called exactly once per orchestrator invocation; duplicate task decisions fail closed. */
    public void recordPolicyDecision(Task task, OffloadingObservation observation, List<Integer> candidateIds,
            boolean[] actionMask, int action, int selectedEdcId) {
        Decision previous = decisions.putIfAbsent(task.getId(),
                new Decision(observation, candidateIds, actionMask, action, selectedEdcId));
        if (previous != null) throw new IllegalStateException("duplicate per-task policy decision for task " + task.getId());
    }

    @Override
    public void recordTaskGenerated(Task task) {
        super.recordTaskGenerated(task);
        ledger(task, "TASK_GENERATED", "GENERATED");
    }

    @Override
    public void recordTaskEvent(Task task, String eventName, String stage) {
        super.recordTaskEvent(task, eventName, stage);
        ledger(task, eventName, stage);
    }

    @Override
    public void processEvent(Event event) {
        boolean decisionEvent = event.getTag() == SEND_TASK_FROM_ORCH_TO_DESTINATION && event.getData() instanceof Task;
        Task decisionTask = decisionEvent ? (Task) event.getData() : null;
        super.processEvent(event);
        if (decisionEvent) finalizeDecision(decisionTask);
        if (event.getTag() == PRINT_LOG && edgeOrchestrator instanceof com.mechalikh.pureedgesim.experiment.DqnReadyOrchestrator dqnReady) {
            dqnReady.endEpisode();
        }
        if (event.getTag() == PRINT_LOG) closeOwnLogs();
    }

    private void finalizeDecision(Task task) {
        if (!finalizedDecisionIds.add(task.getId())) throw new IllegalStateException("duplicate decision audit row for task " + task.getId());
        Decision d = decisions.get(task.getId());
        ComputingNode actual = task.getOffloadingDestination();
        int actualId = actual == null || actual == ComputingNode.NULL ? -1 : actual.getId();
        boolean bypassed = cacheBypassTasks.contains(task.getId()) && d != null;
        String status = d == null ? "POLICY_NOT_CALLED" : (d.action < 0 ? "NO_ELIGIBLE_DESTINATION" : "DECIDED");
        if (d != null && d.selectedEdcId != actualId) {
            throw new IllegalStateException("policy destination " + d.selectedEdcId + " was not applied for task " + task.getId()
                    + "; actual destination=" + actualId);
        }
        if (d == null) {
            write(decisionWriter, String.join(",", csv(task.getId()), csv(simulation.clock()), csv(task.getEdgeDevice().getId()),
                    "", "", "[]", "[]", "", "", "", "", csv(task.getMaxLatency()), "",
                    "{}", "{}", "{}", "{}", "{}", "{}", "{}", "{}", "{}", "{}", "{}", "{}", "{}",
                    Boolean.toString(bypassed), Boolean.toString(cachedBeforeDispatch.getOrDefault(task.getId(), false)),
                    cachedDestinationBeforeDispatch.getOrDefault(task.getId(), -1) < 0 ? "" : csv(cachedDestinationBeforeDispatch.get(task.getId())),
                    "NO_POLICY_CALL", actualId < 0 ? "" : csv(actualId), status));
            return;
        }
        OffloadingObservation o = d.observation;
        write(decisionWriter, String.join(",", csv(task.getId()), csv(simulation.clock()), csv(o.sourceUeId),
                d.action < 0 ? "" : csv(d.action), d.selectedEdcId < 0 ? "" : csv(d.selectedEdcId),
                csv(jsonInts(d.candidateIds)), csv(jsonMask(d.mask)), csv(o.taskMi), csv(o.taskMiNormalized),
                csv(o.inputSizeBits), csv(o.inputSizeNormalized), csv(o.deadlineSeconds), csv(o.deadlineNormalized),
                csv(candidateValues(o, "queue")), csv(candidateValues(o, "queue_norm")),
                csv(candidateValues(o, "active")), csv(candidateValues(o, "active_norm")),
                csv(candidateValues(o, "wait")), csv(candidateValues(o, "wait_norm")),
                csv(candidateValues(o, "mips")), csv(candidateValues(o, "mips_norm")),
                csv(candidateValues(o, "cores")), csv(candidateValues(o, "cores_norm")),
                csv(candidateValues(o, "cpu")), csv(candidateValues(o, "cpu_norm")),
                csv(candidateValues(o, "resource")), Boolean.toString(true),
                Boolean.toString(cachedBeforeDispatch.getOrDefault(task.getId(), false)),
                cachedDestinationBeforeDispatch.getOrDefault(task.getId(), -1) < 0 ? "" : csv(cachedDestinationBeforeDispatch.get(task.getId())),
                "DETERMINISTIC_TEST_POLICY",
                actualId < 0 ? "" : csv(actualId), status));
    }

    private static String candidateValues(OffloadingObservation o, String feature) {
        StringBuilder out = new StringBuilder("{");
        for (int i = 0; i < o.candidates.size(); i++) {
            if (i > 0) out.append(',');
            OffloadingObservation.Candidate c = o.candidates.get(i);
            out.append('"').append(c.edcId).append("\":");
            Object value = switch (feature) {
                case "queue" -> c.waitingQueueLength;
                case "queue_norm" -> c.waitingQueueLengthNormalized;
                case "active" -> c.activeTaskCount;
                case "active_norm" -> c.activeTaskCountNormalized;
                case "wait" -> c.estimatedQueueWaitSeconds;
                case "wait_norm" -> c.estimatedQueueWaitNormalized;
                case "mips" -> c.mipsPerCore;
                case "mips_norm" -> c.mipsPerCoreNormalized;
                case "cores" -> c.cpuCores;
                case "cores_norm" -> c.cpuCoresNormalized;
                case "cpu" -> c.currentCpuUtilizationPercent;
                case "cpu_norm" -> c.currentCpuUtilizationNormalized;
                case "resource" -> c.resourceAvailable;
                default -> throw new IllegalArgumentException("unknown feature " + feature);
            };
            out.append(value == null ? "null" : value);
        }
        return out.append('}').toString();
    }

    private void ledger(Task task, String eventName, String stage) {
        if (ledgerWriter == null || task == null) return;
        ComputingNode destination = task.getOffloadingDestination();
        int destinationId = destination == null || destination == ComputingNode.NULL ? -1 : destination.getId();
        write(ledgerWriter, String.join(",", csv(task.getId()), csv(eventName), csv(simulation.clock()),
                csv(task.getEdgeDevice() == null ? "" : task.getEdgeDevice().getId()),
                destinationId < 0 ? "" : csv(destinationId), csv(task.getStatus() == null ? "" : task.getStatus().name()),
                csv(task.getFailureReason() == null ? "" : task.getFailureReason().name()), csv(task.getTotalDelay()),
                csv(task.getActualNetworkTime()), csv(task.getWatingTime()), csv(task.getActualCpuTime()), csv(stage)));
    }

    private static BufferedWriter open(String property, String header) {
        String path = System.getProperty(property);
        if (path == null || path.isBlank()) throw new IllegalStateException(property + " system property is required");
        try {
            BufferedWriter out = Files.newBufferedWriter(Path.of(path), StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            out.write(header + "\n");
            return out;
        } catch (IOException e) {
            throw new IllegalStateException("cannot create " + property + " CSV", e);
        }
    }

    private static String jsonInts(List<Integer> values) { return values.toString(); }
    private static String jsonMask(boolean[] values) {
        StringBuilder out = new StringBuilder("[");
        for (int i = 0; i < values.length; i++) { if (i > 0) out.append(','); out.append(values[i]); }
        return out.append(']').toString();
    }
    private static String csv(Object value) {
        if (value == null) return "";
        String text = value.toString();
        if (text.contains(",") || text.contains("\"") || text.contains("\n")) return "\"" + text.replace("\"", "\"\"") + "\"";
        return text;
    }
    private static void write(BufferedWriter out, String row) {
        try { out.write(row + "\n"); }
        catch (IOException e) { throw new IllegalStateException("cannot write per-task audit", e); }
    }
    private void closeOwnLogs() {
        close(decisionWriter); close(ledgerWriter);
        decisionWriter = null; ledgerWriter = null;
    }
    private static void close(BufferedWriter out) {
        if (out == null) return;
        try { out.flush(); out.close(); }
        catch (IOException e) { throw new IllegalStateException("cannot close per-task audit", e); }
    }
}
