package com.mechalikh.pureedgesim.experiment;

import java.io.Serializable;

/** Terminal task outcome payload for future learning policies. */
public final class OffloadingTransition implements Serializable {
    private static final long serialVersionUID = 1L;
    public final int taskId;
    public final int actionIndex;
    public final double reward;
    public final boolean terminal;
    public final DqnState state;
    public final DqnState nextState;

    public OffloadingTransition(int taskId, int actionIndex, double reward, boolean terminal) {
        this.taskId = taskId;
        this.actionIndex = actionIndex;
        this.reward = reward;
        this.terminal = terminal;
        this.state = null;
        this.nextState = null;
    }

    public OffloadingTransition(int taskId, DqnState state, int actionIndex, double reward,
            DqnState nextState, boolean terminal) {
        if (state == null) throw new IllegalArgumentException("transition state is required");
        if (!Double.isFinite(reward)) throw new IllegalArgumentException("transition reward must be finite");
        if (!terminal && nextState == null) throw new IllegalArgumentException("nonterminal transition requires next state");
        this.taskId = taskId;
        this.state = state;
        this.actionIndex = actionIndex;
        this.reward = reward;
        this.nextState = nextState;
        this.terminal = terminal;
    }
}
