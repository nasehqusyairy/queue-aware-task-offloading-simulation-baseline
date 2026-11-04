package com.mechalikh.pureedgesim.experiment;

import java.io.Serializable;

/** Fixed-width global task context plus a variable-length ordered candidate set. */
public final class DqnState implements Serializable {
    private static final long serialVersionUID = 1L;
    public final int[] candidateIds;
    public final boolean[] actionMask;
    public final double[] taskFeatures;
    public final double[] globalFeatures;
    public final double[][] candidateFeatures;

    public DqnState(int[] candidateIds, boolean[] actionMask, double[] taskFeatures,
            double[] globalFeatures, double[][] candidateFeatures) {
        if (candidateIds.length != actionMask.length || candidateIds.length != candidateFeatures.length)
            throw new IllegalArgumentException("candidate ID/mask/features length mismatch");
        this.candidateIds = candidateIds.clone();
        this.actionMask = actionMask.clone();
        this.taskFeatures = taskFeatures.clone();
        this.globalFeatures = globalFeatures.clone();
        this.candidateFeatures = new double[candidateFeatures.length][];
        for (int i = 0; i < candidateFeatures.length; i++) this.candidateFeatures[i] = candidateFeatures[i].clone();
    }

    public int actionCount() { return candidateIds.length; }

    public double[] featuresForAction(int action) {
        if (action < 0 || action >= candidateFeatures.length) throw new IllegalArgumentException("action outside state");
        double[] result = new double[taskFeatures.length + globalFeatures.length + candidateFeatures[action].length];
        int p = 0;
        System.arraycopy(taskFeatures, 0, result, p, taskFeatures.length); p += taskFeatures.length;
        System.arraycopy(globalFeatures, 0, result, p, globalFeatures.length); p += globalFeatures.length;
        System.arraycopy(candidateFeatures[action], 0, result, p, candidateFeatures[action].length);
        return result;
    }
}
