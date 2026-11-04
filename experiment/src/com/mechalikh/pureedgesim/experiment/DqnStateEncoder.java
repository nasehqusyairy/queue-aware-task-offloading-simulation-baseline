package com.mechalikh.pureedgesim.experiment;

import java.util.ArrayList;
import java.util.List;
import java.util.OptionalDouble;

import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode;
import com.mechalikh.pureedgesim.datacentersmanager.DefaultComputingNode;
import com.mechalikh.pureedgesim.taskgenerator.Task;

/**
 * First DQN state schema. Raw values remain in simulator units; normalized
 * counterparts use fixed, documented reference scales and are not clipped.
 * Missing observables remain null (serialized as JSON null), never zero-filled.
 */
public final class DqnStateEncoder {
    public static final int TASK_FEATURE_COUNT = 3;
    public static final int GLOBAL_FEATURE_COUNT = 5;
    public static final int CANDIDATE_FEATURE_COUNT = 11;
    public static final int NETWORK_INPUT_COUNT = TASK_FEATURE_COUNT + GLOBAL_FEATURE_COUNT + CANDIDATE_FEATURE_COUNT;
    public static final double TASK_MI_SCALE = 30_000.0;
    public static final double INPUT_BITS_SCALE = 160_000.0;
    public static final double DEADLINE_SECONDS_SCALE = 300.0;
    public static final double QUEUE_LENGTH_SCALE = 100.0;
    public static final double QUEUE_WAIT_SECONDS_SCALE = 300.0;
    public static final double MIPS_PER_CORE_SCALE = 110_000.0;
    public static final double CPU_CORES_SCALE = 10.0;

    public OffloadingObservation encode(Task task, List<ComputingNode> orderedNodes, boolean[] actionMask) {
        if (orderedNodes.size() != actionMask.length) throw new IllegalArgumentException("candidate/mask length mismatch");
        List<OffloadingObservation.Candidate> features = new ArrayList<>(orderedNodes.size());
        for (int i = 0; i < orderedNodes.size(); i++) {
            ComputingNode node = orderedNodes.get(i);
            Integer queue = null;
            Integer active = null;
            Double estimate = null;
            if (node instanceof QueueAwareComputingNode qnode) {
                queue = qnode.getWaitingQueueLength();
                active = qnode.getActiveTaskCount();
            }
            if (node instanceof QueueWorkloadView view) {
                OptionalDouble wait = view.estimateQueueWaitSeconds();
                if (wait.isPresent() && Double.isFinite(wait.getAsDouble())) estimate = wait.getAsDouble();
            }
            boolean resources = node.getAvailableRam() >= task.getContainerSizeInMBytes()
                    && node.getAvailableStorage() >= task.getContainerSizeInMBytes();
            features.add(new OffloadingObservation.Candidate(node.getId(), actionMask[i], queue, active,
                    estimate, node.getMipsPerCore(), node.getNumberOfCPUCores(),
                    node.getCurrentCpuUtilization(), resources));
        }
        return new OffloadingObservation(task.getId(), task.getEdgeDevice().getId(), task.getLength(),
                task.getFileSizeInBits(), task.getMaxLatency(), features);
    }

    /** Encodes explicit null/missing indicators and keeps variable candidate count. */
    public DqnState encode(OffloadingObservation observation, boolean[] actionMask) {
        if (observation.candidates.size() != actionMask.length) throw new IllegalArgumentException("candidate/mask length mismatch");
        int n = observation.candidates.size();
        int[] ids = new int[n];
        boolean[] mask = actionMask.clone();
        double[][] candidates = new double[n][CANDIDATE_FEATURE_COUNT];
        double queueSum = 0, waitSum = 0, cpuSum = 0;
        int queueCount = 0, waitCount = 0, cpuCount = 0;
        for (int i = 0; i < n; i++) {
            OffloadingObservation.Candidate c = observation.candidates.get(i);
            ids[i] = c.edcId;
            candidates[i][0] = c.waitingQueueLengthNormalized == null ? 0 : c.waitingQueueLengthNormalized;
            candidates[i][1] = c.waitingQueueLengthNormalized == null ? 1 : 0;
            candidates[i][2] = c.activeTaskCountNormalized == null ? 0 : c.activeTaskCountNormalized;
            candidates[i][3] = c.activeTaskCountNormalized == null ? 1 : 0;
            candidates[i][4] = c.estimatedQueueWaitNormalized == null ? 0 : c.estimatedQueueWaitNormalized;
            candidates[i][5] = c.estimatedQueueWaitNormalized == null ? 1 : 0;
            candidates[i][6] = c.mipsPerCoreNormalized;
            candidates[i][7] = c.cpuCoresNormalized;
            candidates[i][8] = c.currentCpuUtilizationNormalized;
            candidates[i][9] = c.resourceAvailable ? 1 : 0;
            candidates[i][10] = actionMask[i] ? 1 : 0;
            if (actionMask[i] && c.waitingQueueLengthNormalized != null) { queueSum += c.waitingQueueLengthNormalized; queueCount++; }
            if (actionMask[i] && c.estimatedQueueWaitNormalized != null) { waitSum += c.estimatedQueueWaitNormalized; waitCount++; }
            if (actionMask[i]) { cpuSum += c.currentCpuUtilizationNormalized; cpuCount++; }
        }
        double[] task = {observation.taskMiNormalized, observation.inputSizeNormalized, observation.deadlineNormalized};
        double[] global = {queueCount == 0 ? 0 : queueSum / queueCount, queueCount == 0 ? 1 : 0,
                waitCount == 0 ? 0 : waitSum / waitCount, waitCount == 0 ? 1 : 0,
                cpuCount == 0 ? 0 : cpuSum / cpuCount};
        return new DqnState(ids, mask, task, global, candidates);
    }
}
