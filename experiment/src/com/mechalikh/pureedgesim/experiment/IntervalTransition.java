package com.mechalikh.pureedgesim.experiment;

/** Immutable transition audit record. The source task ID identifies the decision context only. */
public final class IntervalTransition {
    public final long decisionId;
    public final int sourceTaskId, action, selectedEdcId;
    public final DecisionStateSnapshot state, nextState;
    public final double reward, elapsedSeconds, discountFactor;
    public final boolean terminal;
    public IntervalTransition(long id,int taskId,DecisionStateSnapshot state,int action,int edcId,double reward,
            DecisionStateSnapshot next,double elapsed,double discount,boolean terminal) {
        this.decisionId=id; sourceTaskId=taskId; this.state=state; this.action=action; selectedEdcId=edcId;
        this.reward=reward; nextState=next; elapsedSeconds=elapsed; discountFactor=discount; this.terminal=terminal;
    }
}
