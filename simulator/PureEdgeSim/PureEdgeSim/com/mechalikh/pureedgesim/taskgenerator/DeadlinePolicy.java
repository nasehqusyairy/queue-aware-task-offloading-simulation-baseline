package com.mechalikh.pureedgesim.taskgenerator;

/** Shared deadline boundary rule used by task completion validation. */
public final class DeadlinePolicy {
	private DeadlinePolicy() {}

	/**
	 * Returns whether a completed task exceeded its deadline. Equality is a
	 * failure; a zero deadline therefore fails even a zero-delay task. Negative
	 * or non-finite values are invalid inputs and must not silently become success.
	 */
	public static boolean isExceeded(double totalDelay, double maxLatency) {
		if (!Double.isFinite(totalDelay) || totalDelay < 0)
			throw new IllegalArgumentException("total task delay must be finite and non-negative");
		if (!Double.isFinite(maxLatency) || maxLatency < 0)
			throw new IllegalArgumentException("task deadline must be finite and non-negative");
		return totalDelay >= maxLatency;
	}
}
