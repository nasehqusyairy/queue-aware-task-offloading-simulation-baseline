package com.mechalikh.pureedgesim.experiment;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Builds decision-interval system-reward transitions; independent of the legacy task-keyed DQN ledger. */
public final class DecisionEventTransitionBuilder {
    private static final class Open { final long id; final int taskId,action,edc; final DecisionStateSnapshot state; double reward; Open(long i,int t,DecisionStateSnapshot s,int a,int e){id=i;taskId=t;state=s;action=a;edc=e;} }
    private final Set<Integer> terminalIds=new HashSet<>();
    private Open open;
    private final double completionWeight,failureWeight,delayWeight,rho;
    public DecisionEventTransitionBuilder(double completionWeight,double failureWeight,double delayWeight,double rho) {
        if(!Double.isFinite(completionWeight)||!Double.isFinite(failureWeight)||!Double.isFinite(delayWeight)||!Double.isFinite(rho)||rho<0) throw new IllegalArgumentException("weights/rho must be finite and rho nonnegative");
        this.completionWeight=completionWeight;this.failureWeight=failureWeight;this.delayWeight=delayWeight;this.rho=rho;
    }
    public List<IntervalTransition> begin(DecisionStateSnapshot state,int action,int edc) {
        List<IntervalTransition> out=new ArrayList<>();
        if(action<0) return List.of(); // no eligible action is an environment event, not an epoch boundary
        if(open!=null) out.add(close(state,false));
        open=new Open(state.decisionId,state.task.taskId,state,action,edc);
        return List.copyOf(out);
    }
    /** Terminal event reward is counted once, in the currently open interval, regardless of its task ID. */
    public boolean recordTerminal(int taskId,boolean completed,double totalDelaySeconds) {
        if(!Double.isFinite(totalDelaySeconds)) throw new IllegalArgumentException("terminal delay must be finite");
        if(!terminalIds.add(taskId)) return false;
        if(open!=null) open.reward += (completed?completionWeight:-failureWeight)-delayWeight*Math.max(0,totalDelaySeconds);
        return true;
    }
    public List<IntervalTransition> finish(double timestampSeconds) {
        if(open==null) return List.of(); return List.of(close(null,timestampSeconds,true));
    }
    private IntervalTransition close(DecisionStateSnapshot next,boolean terminal) { return close(next,next.timestampSeconds,terminal); }
    private IntervalTransition close(DecisionStateSnapshot next,double timestampSeconds,boolean terminal) {
        Open old=open; open=null; double elapsed=Math.max(0,timestampSeconds-old.state.timestampSeconds);
        return new IntervalTransition(old.id,old.taskId,old.state,old.action,old.edc,old.reward,next,elapsed,Math.exp(-rho*elapsed),terminal);
    }
    public boolean hasOpenInterval(){return open!=null;}
}
