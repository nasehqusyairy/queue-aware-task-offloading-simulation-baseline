package com.mechalikh.pureedgesim.simulationmanager;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HashMap;
import java.util.Map;

import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode;
import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode.LinkOrientation;
import com.mechalikh.pureedgesim.simulationengine.Event;
import com.mechalikh.pureedgesim.simulationengine.PureEdgeSim;
import com.mechalikh.pureedgesim.scenariomanager.Scenario;
import com.mechalikh.pureedgesim.taskgenerator.Task;

/** Hard simulation horizon and task-destination audit for paper-aligned runs. */
public final class PaperAlignedSimulationManager extends DefaultSimulationManager {
    private final Map<Integer, String> orchestrators = new HashMap<>();
    private BufferedWriter destinationWriter;

    public PaperAlignedSimulationManager(SimLog log, PureEdgeSim engine, int simulationId, int iteration, Scenario scenario) {
        super(log, engine, simulationId, iteration, scenario);
        String path = System.getProperty("paper.destination-log");
        if (path == null || path.isBlank()) throw new IllegalStateException("paper.destination-log is required");
        try {
            destinationWriter = Files.newBufferedWriter(Path.of(path), StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            destinationWriter.write("record_type,task_id,destination_type,local_execution,orchestrator_type,source_sensor,source_id,source_name,source_type,source_x,source_y,current_up_type\n");
        } catch (IOException e) {
            throw new IllegalStateException("cannot create destination audit file", e);
        }
    }

    @Override
    public void processEvent(Event event) {
        if (event.getTag() == SEND_TO_ORCH) {
            Task task = (Task) event.getData();
            ComputingNode orchestrator = task.getEdgeDevice().getOrchestrator();
            orchestrators.put(task.getId(), orchestrator.getType().name());
            super.processEvent(event);
            return;
        }
        if (event.getTag() == SEND_TASK_FROM_ORCH_TO_DESTINATION) {
            Task task = (Task) event.getData();
            super.processEvent(event);
            recordDecision(task);
            return;
        }
        if (event.getTag() == PRINT_LOG) {
            int pending = Math.max(0, sentTasks - tasksCount);
            simLog.tasksFailed += pending;
            System.out.printf("PAPER_HORIZON time_seconds=%.9f generated=%d sent=%d accounted=%d pending_at_cutoff=%d%n",
                    simulation.clock(), simLog.getGeneratedTasks(), sentTasks, tasksCount, pending);
            try {
                super.processEvent(event);
            } finally {
                closeDestinationLog();
            }
            return;
        }
        super.processEvent(event);
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
            destinationWriter.write("DECISION," + task.getId() + "," + type + "," + local + "," + orchestrator + ","
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
}
