package com.mechalikh.pureedgesim.experiment;

import com.mechalikh.pureedgesim.simulationmanager.Simulation;
import com.mechalikh.pureedgesim.simulationmanager.PaperAlignedSimulationManager;

/** Entry point for the separate Queue-Aware Trade-Off experiment method. */
public final class QueueAwareMain {
    private QueueAwareMain() {}

    public static void main(String[] args) {
        Simulation simulation = new Simulation();
        simulation.setCustomMobilityModel(SeededMobilityModel.class);
        simulation.setCustomTaskGenerator(Boolean.getBoolean("paper.per-task-validation-workload")
                ? PerTaskValidationTaskGenerator.class : PaperAlignedTaskGenerator.class);
        if (System.getProperty("paper.task-event-trace") != null) {
            simulation.setCustomComputingNode(TaskTracingQueueAwareComputingNode.class);
            simulation.setCustomNetworkModel(TaskTracingNetworkModel.class);
        } else {
            simulation.setCustomComputingNode(QueueAwareComputingNode.class);
        }
        simulation.setCustomComputingNodesGenerator(PaperAlignedComputingNodesGenerator.class);
        simulation.setCustomEdgeOrchestrator(QueueAwareTradeOffOrchestrator.class);
        simulation.setCustomSimulationManager(PaperAlignedSimulationManager.class);
        simulation.launchSimulation();
    }
}
