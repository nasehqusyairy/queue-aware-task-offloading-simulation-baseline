package com.mechalikh.pureedgesim.experiment;

import java.util.ArrayList;
import java.util.List;
import java.util.OptionalDouble;

import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode;
import com.mechalikh.pureedgesim.scenariomanager.SimulationParameters;
import com.mechalikh.pureedgesim.simulationmanager.PaperAlignedSimulationManager;
import com.mechalikh.pureedgesim.simulationmanager.SimulationManager;
import com.mechalikh.pureedgesim.taskgenerator.Task;

/** Separate Trade-Off extension; the built-in orchestrator remains unchanged. */
public final class QueueAwareTradeOffOrchestrator extends PaperAlignedOrchestrator {
    private static final class Candidate {
        final int index;
        final ComputingNode node;
        final double baseScore;
        final OptionalDouble wait;
        final double combinedScore;
        final int waitingQueueLength;
        final int activeTasks;

        Candidate(int index, ComputingNode node, double baseScore, OptionalDouble wait,
                double combinedScore, int waitingQueueLength, int activeTasks) {
            this.index = index;
            this.node = node;
            this.baseScore = baseScore;
            this.wait = wait;
            this.combinedScore = combinedScore;
            this.waitingQueueLength = waitingQueueLength;
            this.activeTasks = activeTasks;
        }
    }

    private final double queuePenaltyWeight;

    public QueueAwareTradeOffOrchestrator(SimulationManager manager) {
        super(manager);
        if (!"TRADE_OFF".equals(algorithmName)) {
            throw new IllegalArgumentException("Queue-Aware extension requires TRADE_OFF as its baseline algorithm");
        }
        queuePenaltyWeight = parseQueuePenaltyWeight(System.getProperty("paper.queue-penalty-weight", "1.0"));
    }

    @Override
    protected int findComputingNode(String[] architecture, Task task) {
        double[] scores = new double[nodeList.size()];
        double[] baselineScores = new double[nodeList.size()];
        java.util.Arrays.fill(scores, Double.POSITIVE_INFINITY);
        java.util.Arrays.fill(baselineScores, Double.POSITIVE_INFINITY);
        List<Candidate> candidates = new ArrayList<>();
        for (int i = 0; i < nodeList.size(); i++) {
            ComputingNode node = nodeList.get(i);
            if (!offloadingIsPossible(task, node, architecture)) continue;

            double baseScore = QueueAwareScoring.tradeOffBaseScore(historyMap.get(i), task.getLength(),
                    node.getType(), node.getMipsPerCore());
            OptionalDouble wait = OptionalDouble.empty();
            int waitingQueueLength = -1;
            int activeTasks = -1;
            if (node instanceof QueueWorkloadView) {
                QueueWorkloadView workload = (QueueWorkloadView) node;
                wait = workload.estimateQueueWaitSeconds();
                if (node instanceof QueueAwareComputingNode) {
                    waitingQueueLength = ((QueueAwareComputingNode) node).getWaitingQueueLength();
                    activeTasks = ((QueueAwareComputingNode) node).getActiveTaskCount();
                }
            }
            double combinedScore = QueueAwareScoring.combinedScore(baseScore, wait, queuePenaltyWeight);
            scores[i] = combinedScore;
            baselineScores[i] = baseScore;
            candidates.add(new Candidate(i, node, baseScore, wait, combinedScore, waitingQueueLength, activeTasks));
        }

        int selected = QueueAwareScoring.firstMinimum(scores);
        int baselineSelected = QueueAwareScoring.firstMinimum(baselineScores);
        int[] baselineRanks = ranks(candidates, false);
        int[] combinedRanks = ranks(candidates, true);
        boolean rankingChanged = !java.util.Arrays.equals(baselineRanks, combinedRanks);
        int selectedCandidateId = selected < 0 ? -1 : nodeList.get(selected).getId();
        int baselineSelectedCandidateId = baselineSelected < 0 ? -1 : nodeList.get(baselineSelected).getId();
        boolean selectedDestinationChanged = selected != baselineSelected;
        if (selected >= 0) historyMap.put(selected, historyMap.get(selected) + 1);

        if (!(simulationManager instanceof PaperAlignedSimulationManager)) {
            throw new IllegalStateException("queue-aware decisions require PaperAlignedSimulationManager audit support");
        }
        PaperAlignedSimulationManager audit = (PaperAlignedSimulationManager) simulationManager;
        for (Candidate candidate : candidates) {
            double penalty = candidate.wait != null && candidate.wait.isPresent()
                    ? queuePenaltyWeight * candidate.wait.getAsDouble() : 0;
            audit.recordQueueCandidate(task.getId(), simulationManager.getSimulation().clock(), candidate.node,
                    candidate.activeTasks, candidate.waitingQueueLength, candidate.wait,
                    candidate.baseScore, queuePenaltyWeight, penalty, candidate.combinedScore,
                    baselineRanks[candidate.index], combinedRanks[candidate.index], rankingChanged,
                    baselineSelectedCandidateId, selectedCandidateId, selectedDestinationChanged, false,
                    candidate.index == selected);
        }
        return selected;
    }

    private static int[] ranks(List<Candidate> candidates, boolean combined) {
        List<Candidate> sorted = new ArrayList<>(candidates);
        sorted.sort((a, b) -> {
            double left = combined ? a.combinedScore : a.baseScore;
            double right = combined ? b.combinedScore : b.baseScore;
            int scoreOrder = Double.compare(left, right);
            return scoreOrder != 0 ? scoreOrder : Integer.compare(a.index, b.index);
        });
        int[] ranks = new int[sorted.stream().mapToInt(c -> c.index).max().orElse(-1) + 1];
        for (int i = 0; i < sorted.size(); i++) ranks[sorted.get(i).index] = i + 1;
        return ranks;
    }

    private static double parseQueuePenaltyWeight(String value) {
        double parsed = Double.parseDouble(value);
        if (!Double.isFinite(parsed) || parsed < 0) {
            throw new IllegalArgumentException("paper.queue-penalty-weight must be finite and non-negative");
        }
        return parsed;
    }
}
