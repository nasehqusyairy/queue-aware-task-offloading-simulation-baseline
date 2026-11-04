package com.mechalikh.pureedgesim.experiment;

import java.util.List;

/** Deterministic validation policy; this is not machine learning or DQN. */
public final class DeterministicTestPolicy implements OffloadingPolicy {
    @Override
    public int selectAction(OffloadingObservation observation, List<Integer> candidateEdcIds, boolean[] actionMask) {
        if (candidateEdcIds.size() != actionMask.length) throw new IllegalArgumentException("candidate/mask length mismatch");
        int eligibleCount = 0;
        for (boolean eligible : actionMask) if (eligible) eligibleCount++;
        if (eligibleCount == 0) return -1;
        int selectedEligibleOrdinal = Math.floorMod(observation.taskId - 1, eligibleCount);
        for (int i = 0; i < actionMask.length; i++) {
            if (actionMask[i] && selectedEligibleOrdinal-- == 0) return i;
        }
        throw new IllegalStateException("eligible action selection failed");
    }
}
