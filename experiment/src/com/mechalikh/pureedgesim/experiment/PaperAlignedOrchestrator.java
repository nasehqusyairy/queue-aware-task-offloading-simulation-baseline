package com.mechalikh.pureedgesim.experiment;

import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode;
import com.mechalikh.pureedgesim.simulationmanager.SimulationManager;
import com.mechalikh.pureedgesim.taskgenerator.Task;
import com.mechalikh.pureedgesim.taskorchestrator.DefaultOrchestrator;

/**
 * Uses PureEdgeSim's built-in Trade-Off/Round-Robin scoring but fixes its
 * candidate eligibility for the paper's target-layer sets. Upstream checks a
 * single current UP_LINK destination; with a Cloud orchestrator and multiple
 * links that pointer can be a peer UE and hide reachable EDCs.
 */
public final class PaperAlignedOrchestrator extends DefaultOrchestrator {
    public PaperAlignedOrchestrator(SimulationManager simulationManager) {
        super(simulationManager);
    }

    @Override
    protected boolean offloadingIsPossible(Task task, ComputingNode node, String[] architectureLayers) {
        if (node == null || node == ComputingNode.NULL || node.isDead() || node.isSensor()) return false;
        return switch (node.getType()) {
            case CLOUD -> arrayContains(architectureLayers, "Cloud");
            case EDGE_DATACENTER -> arrayContains(architectureLayers, "Edge");
            case EDGE_DEVICE -> arrayContains(architectureLayers, "Mist");
            default -> false;
        };
    }
}
