package com.mechalikh.pureedgesim.experiment;

import com.mechalikh.pureedgesim.simulationmanager.DqnReadySimulationManager;
import com.mechalikh.pureedgesim.simulationmanager.Simulation;

/** Launches the isolated per-task decision path with a deterministic test policy. */
public final class PerTaskTestMain {
    private PerTaskTestMain() {}

    public static void main(String[] args) {
        Simulation simulation = new Simulation();
        simulation.setCustomMobilityModel(SeededMobilityModel.class);
        simulation.setCustomTaskGenerator(PerTaskValidationTaskGenerator.class);
        simulation.setCustomComputingNodesGenerator(PaperAlignedComputingNodesGenerator.class);
        simulation.setCustomComputingNode(DqnReadyComputingNode.class);
        simulation.setCustomNetworkModel(TaskTracingNetworkModel.class);
        simulation.setCustomEdgeOrchestrator(DqnReadyOrchestrator.class);
        simulation.setCustomSimulationManager(DqnReadySimulationManager.class);
        simulation.launchSimulation();
    }
}
