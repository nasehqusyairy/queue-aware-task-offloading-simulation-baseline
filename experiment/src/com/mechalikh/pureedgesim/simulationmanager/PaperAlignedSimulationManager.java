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
                queueAuditWriter.write("task_id,decision_time_seconds,candidate_id,candidate_type,baseline_score_seconds,queue_wait_estimate_seconds,waiting_queue_length,active_task_count,queue_estimate_available,queue_penalty_weight,combined_score_seconds,selected\n");
            } catch (IOException e) {
                throw new IllegalStateException("cannot create queue decision audit file", e);
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
            return;
        }
        if (event.getTag() == SEND_TASK_FROM_ORCH_TO_DESTINATION) {
            Task task = (Task) event.getData();
            super.processEvent(event);
            recordTerminalIfCountChanged(task, terminalCountBefore, failedCountBefore);
            recordDecision(task);
            ComputingNode destination = task.getOffloadingDestination();
            if (destination != null && destination != ComputingNode.NULL) {
                dispatchedButUnresolved.put(task.getId(), destination.getType().name());
            }
            return;
        }
        if (event.getTag() == PRINT_LOG) {
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
                simLog.setCompletedTaskDelayAverages(completedLatencySamples == 0 ? -1
                                : completedTotalDelaySeconds / completedLatencySamples,
                        completedLatencySamples == 0 ? -1 : completedWaitingSeconds / completedLatencySamples);
                super.processEvent(event);
            } finally {
                closeDestinationLog();
                closeQueueAuditLog();
            }
            return;
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

    /** Write one candidate's decision-time estimate; absent values remain blank. */
    public void recordQueueCandidate(int taskId, double timeSeconds, ComputingNode candidate,
            double baselineScoreSeconds, OptionalDouble queueWaitSeconds, double combinedScoreSeconds,
            double weight, int waitingQueueLength, int activeTasks, boolean selected) {
        if (queueAuditWriter == null) throw new IllegalStateException("paper.queue-audit-log is required for queue-aware runs");
        try {
            String wait = queueWaitSeconds != null && queueWaitSeconds.isPresent()
                    ? Double.toString(queueWaitSeconds.getAsDouble()) : "";
            String queueLength = waitingQueueLength < 0 ? "" : Integer.toString(waitingQueueLength);
            String active = activeTasks < 0 ? "" : Integer.toString(activeTasks);
            queueAuditWriter.write(taskId + "," + timeSeconds + "," + candidate.getId() + ","
                    + candidate.getType().name() + "," + baselineScoreSeconds + "," + wait + ","
                    + queueLength + "," + active + "," + (wait.isEmpty() ? "false" : "true") + ","
                    + weight + "," + combinedScoreSeconds + "," + selected + "\n");
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
}
