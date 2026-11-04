package com.mechalikh.pureedgesim.experiment;

/** Experimental arrival-cutoff/drain state machine; censored workload is never converted into task failure. */
public final class DecisionEventDrainController {
    public enum Outcome { DRAINING, DRAINED, CENSORED }
    private final double capSeconds;
    private Double startSeconds;
    public DecisionEventDrainController(double capSeconds) {
        if(!Double.isFinite(capSeconds)||capSeconds<=0) throw new IllegalArgumentException("drain cap must be finite and positive");
        this.capSeconds=capSeconds;
    }
    public void begin(double nowSeconds) {
        if(!Double.isFinite(nowSeconds)||startSeconds!=null) throw new IllegalStateException("invalid or repeated drain start");
        startSeconds=nowSeconds;
    }
    public Outcome evaluate(double nowSeconds,int unresolvedTasks) {
        if(startSeconds==null) throw new IllegalStateException("drain has not started");
        if(!Double.isFinite(nowSeconds)||unresolvedTasks<0) throw new IllegalArgumentException("invalid drain observation");
        if(unresolvedTasks==0) return Outcome.DRAINED;
        return nowSeconds-startSeconds>=capSeconds?Outcome.CENSORED:Outcome.DRAINING;
    }
    public double elapsed(double nowSeconds) { if(startSeconds==null) throw new IllegalStateException("drain has not started"); return Math.max(0,nowSeconds-startSeconds); }
}
