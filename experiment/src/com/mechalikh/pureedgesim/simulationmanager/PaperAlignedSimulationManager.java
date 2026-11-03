package com.mechalikh.pureedgesim.simulationmanager;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HashMap;
import java.util.Map;
import java.util.EnumMap;
import java.util.OptionalDouble;

import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode;
import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode.LinkOrientation;
import com.mechalikh.pureedgesim.simulationengine.Event;
import com.mechalikh.pureedgesim.simulationengine.PureEdgeSim;
import com.mechalikh.pureedgesim.scenariomanager.Scenario;
import com.mechalikh.pureedgesim.scenariomanager.SimulationParameters;
import com.mechalikh.pureedgesim.taskgenerator.Task;
import com.mechalikh.pureedgesim.experiment.QueueAwareComputingNode;
import com.mechalikh.pureedgesim.experiment.TaskTracingComputingNode;

/** Hard simulation horizon and task-destination audit for paper-aligned runs. */
public final class PaperAlignedSimulationManager extends DefaultSimulationManager {
    private final Map<Integer, String> orchestrators = new HashMap<>();
    // A destination assignment is not success. Keep it outstanding until a terminal event.
    private final Map<Integer, String> dispatchedButUnresolved = new HashMap<>();
    private final java.util.Set<Integer> terminalTaskIds = new java.util.HashSet<>();
    private final java.util.Set<Integer> acceptedTaskIds = new java.util.HashSet<>();
    private final java.util.Set<Integer> terminalFailureTaskIds = new java.util.HashSet<>();
    private BufferedWriter destinationWriter;
    private BufferedWriter queueAuditWriter;
    private BufferedWriter taskEventWriter;
    private BufferedWriter nodeStateWriter;
    private final Map<Integer, Task> tracedTasks = new HashMap<>();
    private final java.util.Set<Integer> tracedTerminalIds = new java.util.HashSet<>();
    private double completedTotalDelaySeconds;
    private double completedWaitingSeconds;
    private int completedLatencySamples;

    public PaperAlignedSimulationManager(SimLog log, PureEdgeSim engine, int simulationId, int iteration, Scenario scenario) {
        super(log, engine, simulationId, iteration, scenario);
        String path = System.getProperty("paper.destination-log");
        if (path == null || path.isBlank()) throw new IllegalStateException("paper.destination-log is required");
        try {
            destinationWriter = Files.newBufferedWriter(Path.of(path), StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            destinationWriter.write("record_type,task_id,destination_type,destination_id,local_execution,orchestrator_type,source_sensor,source_id,source_name,source_type,source_x,source_y,current_up_type\n");
        } catch (IOException e) {
            throw new IllegalStateException("cannot create destination audit file", e);
        }
        String queuePath = System.getProperty("paper.queue-audit-log");
        if (queuePath != null && !queuePath.isBlank()) {
            try {
                queueAuditWriter = Files.newBufferedWriter(Path.of(queuePath), StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
                queueAuditWriter.write("task_id,estimate_timestamp_seconds,candidate_id,candidate_type,active_task_count,waiting_queue_length,queue_estimate_available,queue_wait_estimate_seconds,baseline_score_seconds,queue_penalty_weight,queue_penalty_seconds,combined_score_seconds,baseline_rank,combined_rank,ranking_changed,baseline_selected_candidate_id,selected_candidate_id,selected_destination_changed,placement_cache_used,selected\n");
            } catch (IOException e) {
                throw new IllegalStateException("cannot create queue decision audit file", e);
            }
        }
        String tracePath = System.getProperty("paper.task-event-trace");
        if (tracePath != null && !tracePath.isBlank()) {
            try {
                taskEventWriter = Files.newBufferedWriter(Path.of(tracePath), StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
                taskEventWriter.write("schema_version,task_id,event_name,timestamp_seconds,scheduled_release_time_seconds,application_id,task_type,source_id,source_layer,destination_id,destination_layer,status,failure_reason,stage,total_delay_seconds,network_delay_seconds,queue_wait_seconds,cpu_time_seconds,deadline_seconds\n");
            } catch (IOException e) {
                throw new IllegalStateException("cannot create task event trace", e);
            }
        }
        String nodeStatePath = System.getProperty("paper.node-state-log");
        if (nodeStatePath != null && !nodeStatePath.isBlank()) {
            try {
                nodeStateWriter = Files.newBufferedWriter(Path.of(nodeStatePath), StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
                nodeStateWriter.write("timestamp_seconds,node_id,node_type,event,active_task_count,waiting_queue_length,current_cpu_utilization_percent,average_cpu_utilization_percent,computing_energy_wh,network_energy_wh,queue_wait_estimate_seconds\n");
            } catch (IOException e) {
                throw new IllegalStateException("cannot create node state audit", e);
            }
        }
    }

    @Override
    public void processEvent(Event event) {
        int terminalCountBefore = tasksCount;
        int failedCountBefore = simLog.tasksFailed;
        if (event.getData() instanceof Task && terminalTaskIds.contains(((Task) event.getData()).getId())) {
            return; // Ignore duplicate/stale lifecycle events after exactly one terminal outcome.
        }
        if (event.getTag() == SEND_TO_ORCH) {
            Task task = (Task) event.getData();
            // The base manager assigns task.orchestrator inside this event. Record the
            // post-assignment value rather than inferring it from the source UE first.
            int sentBefore = simLog.tasksSent;
            super.processEvent(event);
            if (simLog.tasksSent > sentBefore) acceptedTaskIds.add(task.getId());
            recordTerminalIfCountChanged(task, terminalCountBefore, failedCountBefore);
            ComputingNode orchestrator = task.getOrchestrator();
            String type = orchestrator == null || orchestrator == ComputingNode.NULL
                    ? "UNKNOWN" : orchestrator.getType().name();
            orchestrators.put(task.getId(), type);
            if (simLog.tasksSent > sentBefore) recordTaskEvent(task, "ORCHESTRATION_REQUEST", "REQUEST_SENT");
            return;
        }
        if (event.getTag() == SEND_TASK_FROM_ORCH_TO_DESTINATION) {
            Task task = (Task) event.getData();
            boolean placementWasCached = task.getEdgeDevice().isApplicationPlaced();
            super.processEvent(event);
            recordTerminalIfCountChanged(task, terminalCountBefore, failedCountBefore);
            recordDecision(task);
            ComputingNode destination = task.getOffloadingDestination();
            if (destination == null || destination == ComputingNode.NULL) {
                if (task.getFailureReason() == Task.FailureReason.NO_OFFLOADING_DESTINATIONS) {
                    recordTaskEvent(task, "DESTINATION_DECISION", "POLICY_NO_DESTINATION");
                }
            } else {
                recordTaskEvent(task, "DESTINATION_DECISION",
                        placementWasCached ? "CACHED_PLACEMENT_REUSED" : "POLICY_SELECTED");
            }
            if (destination != null && destination != ComputingNode.NULL) {
                dispatchedButUnresolved.put(task.getId(), destination.getType().name());
                recordTaskEvent(task, "TASK_DISPATCH", "DISPATCH_SCHEDULED");
            }
            return;
        }
        if (event.getTag() == PRINT_LOG) {
            for (ComputingNode node : getDataCentersManager().getComputingNodesGenerator().getEdgeOnlyList()) {
                int active = node instanceof QueueAwareComputingNode
                        ? ((QueueAwareComputingNode) node).getActiveTaskCount()
                        : (node instanceof TaskTracingComputingNode
                                ? ((TaskTracingComputingNode) node).getActiveTaskCount() : -1);
                recordNodeState(node, "HORIZON_FINAL", active, node.getTasksQueue().size());
            }
            int failed = simLog.tasksFailed;
            int completed = tasksCount - failed;
            int pending = simLog.getGeneratedTasks() - completed - failed;
            int rejectedBeforePipeline = terminalFailureTaskIds.size() - acceptedFailureCount();
            EnumMap<SimulationParameters.TYPES, Integer> pendingByLayer = new EnumMap<>(SimulationParameters.TYPES.class);
            for (String type : dispatchedButUnresolved.values()) {
                SimulationParameters.TYPES nodeType = SimulationParameters.TYPES.valueOf(type);
                pendingByLayer.merge(nodeType, 1, Integer::sum);
            }
            int cloudPending = pendingByLayer.getOrDefault(SimulationParameters.TYPES.CLOUD, 0);
            int edgePending = pendingByLayer.getOrDefault(SimulationParameters.TYPES.EDGE_DATACENTER, 0);
            int mistPending = pendingByLayer.getOrDefault(SimulationParameters.TYPES.EDGE_DEVICE, 0);
            simLog.setCutoffAccounting(completed, pending, cloudPending, edgePending, mistPending, rejectedBeforePipeline);
            boolean valid = completed >= 0 && failed >= 0 && pending >= 0
                    && simLog.getGeneratedTasks() == completed + failed + pending
                    && cloudPending + edgePending + mistPending <= pending;
            System.out.printf("PAPER_HORIZON time_seconds=%.9f generated=%d sent=%d accounted=%d pending_at_cutoff=%d completed=%d terminally_failed=%d accounting_valid=%s cloud_pending=%d edge_pending=%d mist_pending=%d rejected_before_pipeline=%d%n",
                    simulation.clock(), simLog.getGeneratedTasks(), simLog.tasksSent, completed + failed, pending,
                    completed, failed, valid, cloudPending, edgePending, mistPending, rejectedBeforePipeline);
            try {
                recordPendingAtHorizon();
                simLog.setCompletedTaskDelayAverages(completedLatencySamples == 0 ? -1
                                : completedTotalDelaySeconds / completedLatencySamples,
                        completedLatencySamples == 0 ? -1 : completedWaitingSeconds / completedLatencySamples);
                super.processEvent(event);
            } finally {
                closeDestinationLog();
                closeQueueAuditLog();
                closeTaskEventLog();
                closeNodeStateLog();
            }
            return;
        }
        if (event.getTag() == EXECUTE_TASK && event.getData() instanceof Task) {
            recordTaskEvent((Task) event.getData(), "DESTINATION_EXECUTION_READY", "EXECUTION_READY");
        } else if (event.getTag() == RESULT_RETURN_FINISHED && event.getData() instanceof Task) {
            recordTaskEvent((Task) event.getData(), "RESULT_RETURN", "RESULT_AT_SOURCE");
        }
        super.processEvent(event);
        if (event.getTag() == RESULT_RETURN_FINISHED && tasksCount > terminalCountBefore
                && simLog.tasksFailed == failedCountBefore) {
            Task completed = (Task) event.getData();
            completedTotalDelaySeconds += completed.getTotalDelay();
            completedWaitingSeconds += completed.getWatingTime();
            completedLatencySamples++;
        }
        if (event.getData() instanceof Task) recordTerminalIfCountChanged((Task) event.getData(), terminalCountBefore, failedCountBefore);
    }

    /** Called by the task generator; no state is retained when tracing is disabled. */
    public void recordTaskGenerated(Task task) {
        if (taskEventWriter == null) return;
        tracedTasks.put(task.getId(), task);
        writeTaskEvent(task, "TASK_GENERATED", simulation.clock(), task.getEdgeDevice(),
                task.getOffloadingDestination(), task.getStatus().name(), "", "GENERATED");
    }

    /** Event-time, direct PureEdgeSim state observation for one EDC. */
    public void recordNodeState(ComputingNode node, String event, int activeTasks, int waitingTasks) {
        if (nodeStateWriter == null || node.getType() != SimulationParameters.TYPES.EDGE_DATACENTER) return;
        try {
            var energy = node.getEnergyModel();
            double cpuEnergy = energy == null ? Double.NaN : energy.getCpuEnergyConsumption();
            double networkEnergy = energy == null ? Double.NaN : energy.getTotalEnergyConsumption() - cpuEnergy;
            nodeStateWriter.write(simulation.clock() + "," + node.getId() + "," + node.getType().name() + ","
                    + event + "," + activeTasks + "," + waitingTasks + "," + node.getCurrentCpuUtilization() + ","
                    + node.getAvgCpuUtilization() + "," + cpuEnergy + "," + networkEnergy + ",\n");
        } catch (IOException e) {
            throw new IllegalStateException("cannot write EDC state audit", e);
        }
    }

    /** Read-only event emission for experiment-specific computing-node subclasses. */
    public void recordTaskEvent(Task task, String eventName, String stage) {
        if (taskEventWriter == null || task == null) return;
        ComputingNode source = task.getEdgeDevice();
        ComputingNode destination = task.getOffloadingDestination();
        String status = task.getStatus() == null ? "" : task.getStatus().name();
        String reason = task.getFailureReason() == null ? "" : task.getFailureReason().name();
        writeTaskEvent(task, eventName, simulation.clock(), source, destination, status, reason, stage);
    }

    private void recordPendingAtHorizon() {
        if (taskEventWriter == null) return;
        for (Task task : tracedTasks.values()) {
            if (!tracedTerminalIds.contains(task.getId())) {
                recordTaskEvent(task, "TASK_PENDING_AT_HORIZON", "UNRESOLVED_AT_CUTOFF");
            }
        }
    }

    private void writeTaskEvent(Task task, String eventName, double time, ComputingNode source,
            ComputingNode destination, String status, String reason, String stage) {
        try {
            taskEventWriter.write("1," + task.getId() + "," + eventName + "," + time + "," + task.getTime() + ","
                    + task.getApplicationID() + "," + csv(task.getType()) + ","
                    + nodeId(source) + "," + nodeType(source) + "," + nodeId(destination) + ","
                    + nodeType(destination) + "," + csv(status) + "," + csv(reason) + "," + csv(stage) + ","
                    + task.getTotalDelay() + "," + task.getActualNetworkTime() + ","
                    + task.getWatingTime() + "," + task.getActualCpuTime() + "," + task.getMaxLatency() + "\n");
        } catch (IOException e) {
            throw new IllegalStateException("cannot write task event trace", e);
        }
    }

    private static String nodeId(ComputingNode node) {
        return node == null || node == ComputingNode.NULL ? "" : Integer.toString(node.getId());
    }

    private static String nodeType(ComputingNode node) {
        return node == null || node == ComputingNode.NULL ? "" : node.getType().name();
    }

    private static String csv(Object value) {
        if (value == null) return "";
        String text = value.toString();
        return "\"" + text.replace("\"", "\"\"") + "\"";
    }

    /** Write one candidate's decision-time estimate; absent values remain blank. */
    public void recordQueueCandidate(int taskId, double timeSeconds, ComputingNode candidate,
            int activeTasks, int waitingQueueLength, OptionalDouble queueWaitSeconds,
            double baselineScoreSeconds, double weight, double queuePenaltySeconds,
            double combinedScoreSeconds, int baselineRank, int combinedRank,
            boolean rankingChanged, int baselineSelectedCandidateId, int selectedCandidateId,
            boolean selectedDestinationChanged, boolean placementCacheUsed, boolean selected) {
        if (queueAuditWriter == null) throw new IllegalStateException("paper.queue-audit-log is required for queue-aware runs");
        try {
            String wait = queueWaitSeconds != null && queueWaitSeconds.isPresent()
                    ? Double.toString(queueWaitSeconds.getAsDouble()) : "";
            String queueLength = waitingQueueLength < 0 ? "" : Integer.toString(waitingQueueLength);
            String active = activeTasks < 0 ? "" : Integer.toString(activeTasks);
            queueAuditWriter.write(taskId + "," + timeSeconds + "," + candidate.getId() + ","
                    + candidate.getType().name() + "," + active + "," + queueLength + ","
                    + (wait.isEmpty() ? "false" : "true") + "," + wait + "," + baselineScoreSeconds + ","
                    + weight + "," + queuePenaltySeconds + "," + combinedScoreSeconds + ","
                    + baselineRank + "," + combinedRank + "," + rankingChanged + ","
                    + baselineSelectedCandidateId + "," + selectedCandidateId + ","
                    + selectedDestinationChanged + "," + placementCacheUsed + "," + selected + "\n");
        } catch (IOException e) {
            throw new IllegalStateException("cannot write queue decision audit record", e);
        }
    }

    private int acceptedFailureCount() {
        int count = 0;
        for (Integer id : terminalFailureTaskIds) if (acceptedTaskIds.contains(id)) count++;
        return count;
    }

    private void recordTerminalIfCountChanged(Task task, int before, int failedBefore) {
        if (tasksCount > before) {
            terminalTaskIds.add(task.getId());
            dispatchedButUnresolved.remove(task.getId());
            if (simLog.tasksFailed > failedBefore) terminalFailureTaskIds.add(task.getId());
            if (taskEventWriter != null && tracedTerminalIds.add(task.getId())) {
                boolean failed = simLog.tasksFailed > failedBefore;
                recordTaskEvent(task, failed ? "TASK_FAILED" : "TASK_COMPLETED",
                        failed ? "TERMINAL_FAILED" : "TERMINAL_COMPLETED");
            }
        }
    }

    private void recordDecision(Task task) {
        ComputingNode destination = task.getOffloadingDestination();
        String type = destination == null || destination == ComputingNode.NULL ? "NONE" : destination.getType().name();
        boolean local = destination != null && destination != ComputingNode.NULL && destination == task.getEdgeDevice();
        String orchestrator = orchestrators.getOrDefault(task.getId(), "UNKNOWN");
        ComputingNode source = task.getEdgeDevice();
        String currentUp = "NONE";
        try {
            ComputingNode up = source.getCurrentLink(LinkOrientation.UP_LINK).getDst();
            if (up != null && up != ComputingNode.NULL) currentUp = up.getType().name();
        } catch (RuntimeException ignored) {
            // Preserve the missing link as an explicit NONE audit value.
        }
        var location = source.getMobilityModel().getCurrentLocation();
        try {
            String sourceName = source.getName() == null ? "UE-" + source.getId() : source.getName();
            String destinationId = destination == null || destination == ComputingNode.NULL
                    ? "" : Integer.toString(destination.getId());
            destinationWriter.write("DECISION," + task.getId() + "," + type + "," + destinationId + "," + local + "," + orchestrator + ","
                    + source.isSensor() + "," + source.getId() + ",\"" + sourceName.replace("\"", "\"\"") + "\"," + source.getType().name()
                    + "," + location.getXPos() + "," + location.getYPos() + "," + currentUp + "\n");
        } catch (IOException e) {
            throw new IllegalStateException("cannot write destination audit record", e);
        }
    }

    private void closeDestinationLog() {
        if (destinationWriter == null) return;
        try {
            destinationWriter.flush();
            destinationWriter.close();
            destinationWriter = null;
        } catch (IOException e) {
            throw new IllegalStateException("cannot close destination audit log", e);
        }
    }

    private void closeQueueAuditLog() {
        if (queueAuditWriter == null) return;
        try {
            queueAuditWriter.flush();
            queueAuditWriter.close();
            queueAuditWriter = null;
        } catch (IOException e) {
            throw new IllegalStateException("cannot close queue decision audit log", e);
        }
    }

    private void closeTaskEventLog() {
        if (taskEventWriter == null) return;
        try {
            taskEventWriter.flush();
            taskEventWriter.close();
            taskEventWriter = null;
        } catch (IOException e) {
            throw new IllegalStateException("cannot close task event trace", e);
        }
    }

    private void closeNodeStateLog() {
        if (nodeStateWriter == null) return;
        try {
            nodeStateWriter.flush();
            nodeStateWriter.close();
            nodeStateWriter = null;
        } catch (IOException e) {
            throw new IllegalStateException("cannot close EDC state audit", e);
        }
    }
}
