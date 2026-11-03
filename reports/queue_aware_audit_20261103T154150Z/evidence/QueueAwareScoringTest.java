import java.util.OptionalDouble;

import com.mechalikh.pureedgesim.experiment.QueueAwareScoring;
import com.mechalikh.pureedgesim.scenariomanager.SimulationParameters;

/** Dependency-free focused checks for the Queue-Aware scoring/queue estimator. */
public final class QueueAwareScoringTest {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static void close(double actual, double expected, String message) {
        check(Math.abs(actual - expected) < 1e-9, message + ": expected " + expected + ", got " + actual);
    }

    private static double wait(double[] active, double[] queued, int cores, double mips) {
        OptionalDouble estimate = QueueAwareScoring.estimateQueueWaitSeconds(active, queued, cores, mips);
        check(estimate.isPresent(), "expected a valid queue estimate");
        return estimate.getAsDouble();
    }

    public static void main(String[] args) {
        // Empty queue and idle cores.
        close(wait(new double[0], new double[0], 4, 100), 0, "empty queue wait");

        // One core has an active task and two FIFO waiters; all service times are seconds.
        close(wait(new double[]{2}, new double[]{500, 1000}, 1, 100), 17, "single-core queued wait");

        // Different node queues can be compared without assuming equal MIPS.
        double shortNodeWait = wait(new double[]{1}, new double[]{100}, 1, 100);
        double longNodeWait = wait(new double[]{1}, new double[]{1000, 1000}, 1, 100);
        check(shortNodeWait < longNodeWait, "longer queue must have larger estimated wait");
        close(wait(new double[]{1}, new double[]{1000}, 1, 1000), 2, "heterogeneous service rate");

        // Equal conditions preserve node order on ties.
        check(QueueAwareScoring.firstMinimum(new double[]{3, 3, 4}) == 0, "stable tie order");

        // Invalid capacity/workload information is unavailable, never divided by zero.
        check(!QueueAwareScoring.estimateQueueWaitSeconds(new double[0], new double[0], 0, 100).isPresent(),
                "zero cores must be unavailable");
        check(!QueueAwareScoring.estimateQueueWaitSeconds(new double[0], new double[0], 1, 0).isPresent(),
                "zero MIPS must be unavailable");
        check(!QueueAwareScoring.estimateQueueWaitSeconds(new double[0], new double[]{-1}, 1, 100).isPresent(),
                "negative task length must be unavailable");
        check(Double.isInfinite(QueueAwareScoring.tradeOffBaseScore(0, 100, SimulationParameters.TYPES.EDGE_DATACENTER, 0)),
                "invalid candidate capacity must not win");
        check(QueueAwareScoring.firstMinimum(new double[]{Double.POSITIVE_INFINITY, 10}) == 1,
                "invalid capacity candidate must be skipped");

        // Overloaded candidates remain measurable and can be penalized.
        double loadedScore = QueueAwareScoring.combinedScore(5, OptionalDouble.of(20), 1);
        double emptyScore = QueueAwareScoring.combinedScore(5, OptionalDouble.of(0), 1);
        check(loadedScore > emptyScore, "overloaded node receives a queue penalty");

        // Unavailable workload falls back to Trade-Off. Lambda zero is exact baseline behavior.
        close(QueueAwareScoring.combinedScore(7.25, OptionalDouble.empty(), 1), 7.25,
                "unavailable estimate baseline fallback");
        close(QueueAwareScoring.combinedScore(7.25, OptionalDouble.of(100), 0), 7.25,
                "queue awareness disabled");

        // Regression against DefaultOrchestrator.tradeOff's built-in type weights/formula.
        double edge = QueueAwareScoring.tradeOffBaseScore(0, 1000, SimulationParameters.TYPES.EDGE_DATACENTER, 100);
        double cloud = QueueAwareScoring.tradeOffBaseScore(0, 1000, SimulationParameters.TYPES.CLOUD, 200);
        double mist = QueueAwareScoring.tradeOffBaseScore(0, 1000, SimulationParameters.TYPES.EDGE_DEVICE, 100);
        close(edge, 12, "Edge Trade-Off base score");
        close(cloud, 9, "Cloud Trade-Off base score");
        close(mist, 13, "Mist Trade-Off base score");
        check(QueueAwareScoring.firstMinimum(new double[]{edge, cloud, mist}) == 1,
                "lambda-zero selection must match baseline score order");
    }
}
