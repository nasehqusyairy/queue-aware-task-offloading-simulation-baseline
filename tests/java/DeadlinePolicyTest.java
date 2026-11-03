import com.mechalikh.pureedgesim.taskgenerator.DeadlinePolicy;

/** Dependency-free executable checks for PureEdgeSim's deadline boundary. */
public final class DeadlinePolicyTest {
	private static void check(boolean condition, String message) {
		if (!condition) throw new AssertionError(message);
	}

	private static void rejects(double delay, double deadline) {
		try {
			DeadlinePolicy.isExceeded(delay, deadline);
			throw new AssertionError("expected invalid deadline input to be rejected");
		} catch (IllegalArgumentException expected) {
			// Expected: invalid values must not silently pass as a successful task.
		}
	}

	public static void main(String[] args) {
		check(!DeadlinePolicy.isExceeded(4.99, 5), "below-deadline task must pass");
		check(DeadlinePolicy.isExceeded(5, 5), "exact-deadline task must fail");
		check(DeadlinePolicy.isExceeded(5.01, 5), "above-deadline task must fail");
		check(DeadlinePolicy.isExceeded(0, 0), "zero deadline expires at zero delay");
		check(!DeadlinePolicy.isExceeded(0, 1), "zero-delay task meets positive deadline");
		rejects(-1, 1);
		rejects(1, -1);
		rejects(1, Double.NaN);
		rejects(Double.POSITIVE_INFINITY, 1);
	}
}
