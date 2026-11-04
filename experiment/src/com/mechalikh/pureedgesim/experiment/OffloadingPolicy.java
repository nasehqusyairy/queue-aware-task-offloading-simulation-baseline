package com.mechalikh.pureedgesim.experiment;

import java.util.List;

/** Policy contract for selecting one currently eligible action index. */
public interface OffloadingPolicy {
    int selectAction(OffloadingObservation observation, List<Integer> candidateEdcIds, boolean[] actionMask);

    default void observe(OffloadingTransition transition) {}

    default void endEpisode() {}
}
