package com.mechalikh.pureedgesim.experiment;

import java.util.ArrayList;
import java.util.List;

import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode;
import com.mechalikh.pureedgesim.simulationmanager.DqnReadySimulationManager;
import com.mechalikh.pureedgesim.simulationmanager.SimulationManager;
import com.mechalikh.pureedgesim.taskgenerator.Task;

/** Per-task policy adapter. The current deterministic policy is validation-only. */
public final class DqnReadyOrchestrator extends PaperAlignedOrchestrator {
    private final OffloadingPolicy policy;
    private final DqnStateEncoder encoder = new DqnStateEncoder();

    public DqnReadyOrchestrator(SimulationManager manager) {
        super(manager);
        if (!(manager instanceof DqnReadySimulationManager)) {
            throw new IllegalArgumentException("DqnReadyOrchestrator requires DqnReadySimulationManager");
        }
        String policyName = System.getProperty("paper.per-task-policy", "deterministic-task-modulo");
        if (!"deterministic-task-modulo".equals(policyName)) {
            throw new IllegalArgumentException("unsupported validation policy: " + policyName);
        }
        policy = new DeterministicTestPolicy();
    }

    @Override
    protected int findComputingNode(String[] architecture, Task task) {
        List<ComputingNode> ordered = DqnActionSpace.stableOrder(nodeList);
        boolean[] mask = new boolean[ordered.size()];
        List<Integer> ids = new ArrayList<>(ordered.size());
        for (int i = 0; i < ordered.size(); i++) {
            ComputingNode candidate = ordered.get(i);
            mask[i] = offloadingIsPossible(task, candidate, architecture);
            ids.add(candidate.getId());
        }
        OffloadingObservation observation = encoder.encode(task, ordered, mask);
        int action = policy.selectAction(observation, ids, mask);
        int selectedNodeId = -1;
        if (DqnActionSpace.anyEligible(mask)) {
            action = DqnActionSpace.validateAction(action, mask);
            selectedNodeId = ids.get(action);
        } else if (action != -1) {
            throw new IllegalArgumentException("policy must return -1 when no action is eligible");
        }
        ((DqnReadySimulationManager) simulationManager).recordPolicyDecision(
                task, observation, ids, mask, action, selectedNodeId);
        if (action < 0) return -1;
        ComputingNode selected = ordered.get(action);
        if (selected == null || !mask[action]) throw new IllegalStateException("invalid destination escaped action mask");
        return nodeList.indexOf(selected);
    }

    public void endEpisode() {
        policy.endEpisode();
    }
}
