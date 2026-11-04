package com.mechalikh.pureedgesim.experiment;

/** Terminal task outcome payload for future learning policies. */
public final class OffloadingTransition {
    public final int taskId;
    public final int actionIndex;
    public final double reward;
    public final boolean terminal;

    public OffloadingTransition(int taskId, int actionIndex, double reward, boolean terminal) {
        this.taskId = taskId;
        this.actionIndex = actionIndex;
        this.reward = reward;
        this.terminal = terminal;
    }
}
