package com.mechalikh.pureedgesim.experiment;

import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode;
import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode.LinkOrientation;
import com.mechalikh.pureedgesim.scenariomanager.SimulationParameters;
import com.mechalikh.pureedgesim.simulationengine.FutureQueue;
import com.mechalikh.pureedgesim.simulationmanager.DqnReadySimulationManager;
import com.mechalikh.pureedgesim.simulationmanager.SimulationManager;
import com.mechalikh.pureedgesim.taskgenerator.Application;
import com.mechalikh.pureedgesim.taskgenerator.DefaultTaskGenerator;
import com.mechalikh.pureedgesim.taskgenerator.Task;

/** Small deterministic load used only to validate fresh decisions and changing queue state. */
public final class PerTaskValidationTaskGenerator extends DefaultTaskGenerator {
    private static final int TASK_COUNT = 64;
    private static final double ARRIVAL_GAP_SECONDS = 0.03;
    private static final int APPLICATION_INDEX = 2;

    public PerTaskValidationTaskGenerator(SimulationManager manager) { super(manager); }

    @Override
    public FutureQueue<Task> generate() {
        ComputingNode source = null;
        for (ComputingNode device : devicesList) {
            if (!device.isGeneratingTasks()) continue;
            long reachable = getSimulationManager().getDataCentersManager().getComputingNodesGenerator()
                    .getEdgeOnlyList().stream()
                    .filter(node -> !node.isDead() && !node.isSensor())
                    .filter(node -> device.getMobilityModel().distanceTo(node) <= SimulationParameters.edgeDataCentersRange)
                    .count();
            if (reachable >= 2) { source = device; break; }
        }
        if (source == null) throw new IllegalStateException("validation scenario requires one task-generating UE with at least two eligible EDCs");
        Application app = SimulationParameters.applicationList.get(APPLICATION_INDEX);
        source.setApplicationType(APPLICATION_INDEX);
        ComputingNode cloud = getSimulationManager().getDataCentersManager().getComputingNodesGenerator().getCloudOnlyList().get(0);
        if (SimulationParameters.enableOrchestrators && "CLOUD".equals(SimulationParameters.deployOrchestrators)) {
            source.setOrchestrator(cloud);
        }
        for (int i = 0; i < TASK_COUNT; i++) {
            Task task = createTask(++id);
            if (task == null) throw new IllegalStateException("could not create validation task");
            task.setType(app.getType()).setFileSizeInBits(app.getRequestSize()).setOutputSizeInBits(app.getResultsSize())
                    .setContainerSizeInBits(app.getContainerSizeInBits()).setApplicationID(APPLICATION_INDEX)
                    .setMaxLatency(app.getLatency()).setLength((long) app.getTaskLength()).setEdgeDevice(source)
                    .setRegistry(cloud).setTime(i * ARRIVAL_GAP_SECONDS);
            if (SimulationParameters.enableOrchestrators && "CLOUD".equals(SimulationParameters.deployOrchestrators)) {
                task.setOrchestrator(cloud);
            }
            taskList.add(task);
            if (getSimulationManager() instanceof DqnReadySimulationManager audit) audit.recordTaskGenerated(task);
        }
        System.out.printf("PAPER_TASK_GENERATION simulated_seconds=%d active_devices=1 app_user_counts=validation generated_tasks=%d%n",
                (int) Math.round(SimulationParameters.simulationDuration), TASK_COUNT);
        System.out.printf("PER_TASK_VALIDATION source_ue_id=%d task_count=%d arrival_gap_seconds=%.3f task_mi=%.0f%n",
                source.getId(), TASK_COUNT, ARRIVAL_GAP_SECONDS, app.getTaskLength());
        return taskList;
    }
}
