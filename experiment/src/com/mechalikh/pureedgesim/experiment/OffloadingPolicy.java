package com.mechalikh.pureedgesim.experiment;

import java.util.List;

/** Policy contract for selecting one currently eligible action index. */
public interface OffloadingPolicy {
    int selectAction(OffloadingObservation observation, List<Integer> candidateEdcIds, boolean[] actionMask);

    default void observe(OffloadingTransition transition) {}

    default String decisionMetadata() { return "POLICY"; }

    default double terminalReward(boolean success, double totalDelaySeconds) {
        throw new UnsupportedOperationException("this policy does not define a training reward");
    }

    default boolean updatesFromTransitions() { return false; }

    default void endEpisode() {}
}
