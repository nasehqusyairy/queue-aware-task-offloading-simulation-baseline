package com.mechalikh.pureedgesim.experiment;

import com.mechalikh.pureedgesim.simulationmanager.Simulation;

/** Entry point that keeps PureEdgeSim's built-in algorithms and network model. */
public final class PaperAlignedMain {
    private PaperAlignedMain() {}

    public static void main(String[] args) {
        Simulation simulation = new Simulation();
        simulation.setCustomTaskGenerator(PaperAlignedTaskGenerator.class);
        simulation.setCustomComputingNodesGenerator(PaperAlignedComputingNodesGenerator.class);
        simulation.setCustomEdgeOrchestrator(PaperAlignedOrchestrator.class);
        simulation.setCustomSimulationManager(com.mechalikh.pureedgesim.simulationmanager.PaperAlignedSimulationManager.class);
        simulation.launchSimulation();
    }
}
