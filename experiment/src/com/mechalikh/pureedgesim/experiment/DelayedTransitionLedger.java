package com.mechalikh.pureedgesim.experiment;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Decision-event next-state sequence with delayed task-ID-keyed rewards.
 * Replay-ready transitions are emitted exactly once when reward and next state
 * are both known. Horizon-pending tasks remain outstanding without reward.
 */
public final class DelayedTransitionLedger {
    private static final class Step {
        final int taskId;
        final DqnState state;
        final int action;
        DqnState nextState;
        Double reward;
        boolean terminal;
        boolean emitted;

        Step(int taskId, DqnState state, int action) { this.taskId = taskId; this.state = state; this.action = action; }
    }

    private final Map<Integer, Step> steps = new HashMap<>();
    private final Set<Integer> terminalIds = new HashSet<>();
    private Integer lastEligibleActionTaskId;

    /** Every scheduler decision closes the prior decision's next-state slot. */
    public List<OffloadingTransition> onDecision(int taskId, DqnState state, int action) {
        if (steps.containsKey(taskId) || terminalIds.contains(taskId)) throw new IllegalStateException("duplicate decision task ID " + taskId);
        List<OffloadingTransition> ready = new ArrayList<>();
        if (lastEligibleActionTaskId != null) {
            Step previous = steps.get(lastEligibleActionTaskId);
            if (previous.nextState != null) throw new IllegalStateException("next state already assigned for task " + previous.taskId);
            previous.nextState = state;
            emitIfReady(previous, ready);
        }
        if (action >= 0) {
            if (state == null || action >= state.actionCount() || !state.actionMask[action])
                throw new IllegalArgumentException("action is not eligible in transition state");
            steps.put(taskId, new Step(taskId, state, action));
            lastEligibleActionTaskId = taskId;
        } else {
            lastEligibleActionTaskId = null;
        }
        return ready;
    }

    /** Reward belongs to this exact task, independent of terminal event order. */
    public List<OffloadingTransition> onTerminal(int taskId, double reward) {
        if (!Double.isFinite(reward)) throw new IllegalArgumentException("reward must be finite");
        if (!terminalIds.add(taskId)) throw new IllegalStateException("duplicate terminal outcome for task " + taskId);
        List<OffloadingTransition> ready = new ArrayList<>();
        Step step = steps.get(taskId);
        if (step != null) {
            step.reward = reward;
            emitIfReady(step, ready);
        }
        return ready;
    }

    /** Final action is terminal only at the simulation episode horizon. */
    public List<OffloadingTransition> finishEpisode() {
        List<OffloadingTransition> ready = new ArrayList<>();
        if (lastEligibleActionTaskId != null) {
            Step last = steps.get(lastEligibleActionTaskId);
            if (last.nextState == null) last.terminal = true;
            emitIfReady(last, ready);
            lastEligibleActionTaskId = null;
        }
        for (Step step : steps.values()) emitIfReady(step, ready);
        return ready;
    }

    public boolean hasReward(int taskId) { Step step = steps.get(taskId); return step != null && step.reward != null; }
    public boolean hasNextState(int taskId) { Step step = steps.get(taskId); return step != null && (step.nextState != null || step.terminal); }
    public boolean wasEmitted(int taskId) { Step step = steps.get(taskId); return step != null && step.emitted; }
    public int outstandingWithoutRewardCount() {
        int count = 0;
        for (Step step : steps.values()) if (!step.emitted && step.reward == null) count++;
        return count;
    }
    public Double reward(int taskId) { Step step = steps.get(taskId); return step == null ? null : step.reward; }
    public String status(int taskId) {
        Step step = steps.get(taskId);
        if (step == null) return "NO_POLICY_ACTION";
        if (step.emitted) return "INSERTED";
        if (step.reward == null) return "PENDING_NO_REWARD";
        if (step.nextState == null && !step.terminal) return "REWARD_WAITING_FOR_NEXT_STATE";
        return "READY";
    }

    private static void emitIfReady(Step step, List<OffloadingTransition> result) {
        if (step.emitted || step.reward == null || (step.nextState == null && !step.terminal)) return;
        step.emitted = true;
        result.add(new OffloadingTransition(step.taskId, step.state, step.action,
                step.reward, step.nextState, step.terminal));
    }
}
