package com.mechalikh.pureedgesim.experiment;

import java.util.OptionalDouble;

import com.mechalikh.pureedgesim.scenariomanager.SimulationParameters;

/** Pure, independently testable Trade-Off plus FIFO queue-wait scoring math. */
public final class QueueAwareScoring {
    private QueueAwareScoring() {}

    /**
     * Estimate when a newly arriving task could start. Active remaining times
     * seed the per-core availability; existing FIFO waiters are assigned to the
     * earliest-free core using PureEdgeSim's length / MIPS-per-core service rule.
     */
    public static OptionalDouble estimateQueueWaitSeconds(double[] activeRemainingSeconds,
            double[] queuedTaskLengthsMi, int coreCount, double mipsPerCore) {
        if (activeRemainingSeconds == null || queuedTaskLengthsMi == null || coreCount <= 0
                || !Double.isFinite(mipsPerCore) || mipsPerCore <= 0
                || activeRemainingSeconds.length > coreCount) {
            return OptionalDouble.empty();
        }
        double[] freeAt = new double[coreCount]; // Idle cores are available now.
        for (int i = 0; i < activeRemainingSeconds.length; i++) {
            double remaining = activeRemainingSeconds[i];
            if (!Double.isFinite(remaining) || remaining < 0) return OptionalDouble.empty();
            freeAt[i] = remaining;
        }
        for (double taskLength : queuedTaskLengthsMi) {
            if (!Double.isFinite(taskLength) || taskLength < 0) return OptionalDouble.empty();
            int earliestCore = earliest(freeAt);
            double serviceSeconds = taskLength / mipsPerCore;
            if (!Double.isFinite(serviceSeconds)) return OptionalDouble.empty();
            freeAt[earliestCore] += serviceSeconds;
        }
        return OptionalDouble.of(minimum(freeAt));
    }

    /** Exact base score used by DefaultOrchestrator.tradeOff(). */
    public static double tradeOffBaseScore(int assignedHistory, double taskLengthMi,
            SimulationParameters.TYPES nodeType, double mipsPerCore) {
        if (assignedHistory < 0 || !Double.isFinite(taskLengthMi) || taskLengthMi < 0 || nodeType == null
                || !Double.isFinite(mipsPerCore) || mipsPerCore <= 0) {
            return Double.POSITIVE_INFINITY;
        }
        double typeWeight;
        if (nodeType == SimulationParameters.TYPES.CLOUD) typeWeight = 1.8;
        else if (nodeType == SimulationParameters.TYPES.EDGE_DEVICE) typeWeight = 1.3;
        else typeWeight = 1.2;
        return (assignedHistory + 1) * typeWeight * taskLengthMi / mipsPerCore;
    }

    /** Missing queue information falls back to the unchanged Trade-Off score. */
    public static double combinedScore(double tradeOffScore, OptionalDouble queueWaitSeconds,
            double queuePenaltyWeight) {
        if (Double.isNaN(tradeOffScore) || tradeOffScore < 0 || !Double.isFinite(queuePenaltyWeight)
                || queuePenaltyWeight < 0) {
            return Double.POSITIVE_INFINITY;
        }
        if (queuePenaltyWeight == 0 || queueWaitSeconds == null || !queueWaitSeconds.isPresent()) {
            return tradeOffScore;
        }
        double wait = queueWaitSeconds.getAsDouble();
        if (!Double.isFinite(wait) || wait < 0) return tradeOffScore;
        double combined = tradeOffScore + queuePenaltyWeight * wait;
        return Double.isFinite(combined) ? combined : Double.POSITIVE_INFINITY;
    }

    /** Return the first finite minimum, preserving the baseline's stable tie order. */
    public static int firstMinimum(double[] scores) {
        if (scores == null) throw new IllegalArgumentException("scores are required");
        int selected = -1;
        double best = Double.POSITIVE_INFINITY;
        for (int i = 0; i < scores.length; i++) {
            if (Double.isFinite(scores[i]) && scores[i] < best) {
                selected = i;
                best = scores[i];
            }
        }
        return selected;
    }

    private static int earliest(double[] values) {
        int selected = 0;
        for (int i = 1; i < values.length; i++) if (values[i] < values[selected]) selected = i;
        return selected;
    }

    private static double minimum(double[] values) {
        double result = values[0];
        for (int i = 1; i < values.length; i++) result = Math.min(result, values[i]);
        return result;
    }
}
