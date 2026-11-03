package com.mechalikh.pureedgesim.experiment;

import java.util.OptionalDouble;

/** Decision-time view of a destination's existing service backlog. */
public interface QueueWorkloadView {
    OptionalDouble estimateQueueWaitSeconds();
}
