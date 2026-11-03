package com.mechalikh.pureedgesim.experiment;

import com.mechalikh.pureedgesim.simulationmanager.Simulation;
import com.mechalikh.pureedgesim.simulationmanager.PaperAlignedSimulationManager;

/** Entry point for the separate Queue-Aware Trade-Off experiment method. */
public final class QueueAwareMain {
    private QueueAwareMain() {}

    public static void main(String[] args) {
        Simulation simulation = new Simulation();
        simulation.setCustomMobilityModel(SeededMobilityModel.class);
        simulation.setCustomTaskGenerator(PaperAlignedTaskGenerator.class);
        simulation.setCustomComputingNode(QueueAwareComputingNode.class);
        simulation.setCustomComputingNodesGenerator(PaperAlignedComputingNodesGenerator.class);
        simulation.setCustomEdgeOrchestrator(QueueAwareTradeOffOrchestrator.class);
        simulation.setCustomSimulationManager(PaperAlignedSimulationManager.class);
        simulation.launchSimulation();
    }
}
