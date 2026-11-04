package com.mechalikh.pureedgesim.experiment;
import com.mechalikh.pureedgesim.simulationmanager.DqnReadySimulationManager;import com.mechalikh.pureedgesim.simulationmanager.Simulation;
/** DQN task-level decision entry point. */
public final class DqnMain {private DqnMain(){}public static void main(String[] args){Simulation s=new Simulation();s.setCustomMobilityModel(SeededMobilityModel.class);s.setCustomTaskGenerator(PerTaskValidationTaskGenerator.class);s.setCustomComputingNodesGenerator(PaperAlignedComputingNodesGenerator.class);s.setCustomComputingNode(DqnReadyComputingNode.class);s.setCustomNetworkModel(TaskTracingNetworkModel.class);s.setCustomEdgeOrchestrator(DqnReadyOrchestrator.class);s.setCustomSimulationManager(DqnReadySimulationManager.class);s.launchSimulation();}}
