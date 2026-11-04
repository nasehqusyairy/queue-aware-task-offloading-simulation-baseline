package com.mechalikh.pureedgesim.experiment;

import java.util.List;

/** Immutable task and candidate features supplied to a task-offloading policy. */
public final class OffloadingObservation {
    public static final class Candidate {
        public final int edcId;
        public final boolean eligible;
        public final Integer waitingQueueLength;
        public final Double waitingQueueLengthNormalized;
        public final Integer activeTaskCount;
        public final Double activeTaskCountNormalized;
        public final Double estimatedQueueWaitSeconds;
        public final Double estimatedQueueWaitNormalized;
        public final double mipsPerCore;
        public final double mipsPerCoreNormalized;
        public final double cpuCores;
        public final double cpuCoresNormalized;
        public final double currentCpuUtilizationPercent;
        public final double currentCpuUtilizationNormalized;
        public final boolean resourceAvailable;

        public Candidate(int edcId, boolean eligible, Integer waitingQueueLength, Integer activeTaskCount,
                Double estimatedQueueWaitSeconds, double mipsPerCore, double cpuCores,
                double currentCpuUtilizationPercent, boolean resourceAvailable) {
            this.edcId = edcId;
            this.eligible = eligible;
            this.waitingQueueLength = waitingQueueLength;
            this.waitingQueueLengthNormalized = waitingQueueLength == null ? null : waitingQueueLength / DqnStateEncoder.QUEUE_LENGTH_SCALE;
            this.activeTaskCount = activeTaskCount;
            this.activeTaskCountNormalized = activeTaskCount == null ? null : activeTaskCount / DqnStateEncoder.QUEUE_LENGTH_SCALE;
            this.estimatedQueueWaitSeconds = estimatedQueueWaitSeconds;
            this.estimatedQueueWaitNormalized = estimatedQueueWaitSeconds == null ? null
                    : estimatedQueueWaitSeconds / DqnStateEncoder.QUEUE_WAIT_SECONDS_SCALE;
            this.mipsPerCore = mipsPerCore;
            this.mipsPerCoreNormalized = mipsPerCore / DqnStateEncoder.MIPS_PER_CORE_SCALE;
            this.cpuCores = cpuCores;
            this.cpuCoresNormalized = cpuCores / DqnStateEncoder.CPU_CORES_SCALE;
            this.currentCpuUtilizationPercent = currentCpuUtilizationPercent;
            this.currentCpuUtilizationNormalized = currentCpuUtilizationPercent / 100.0;
            this.resourceAvailable = resourceAvailable;
        }
    }

    public final int taskId;
    public final int sourceUeId;
    public final double taskMi;
    public final double taskMiNormalized;
    public final double inputSizeBits;
    public final double inputSizeNormalized;
    public final double deadlineSeconds;
    public final double deadlineNormalized;
    public final List<Candidate> candidates;

    public OffloadingObservation(int taskId, int sourceUeId, double taskMi, double inputSizeBits,
            double deadlineSeconds, List<Candidate> candidates) {
        this.taskId = taskId;
        this.sourceUeId = sourceUeId;
        this.taskMi = taskMi;
        this.taskMiNormalized = taskMi / DqnStateEncoder.TASK_MI_SCALE;
        this.inputSizeBits = inputSizeBits;
        this.inputSizeNormalized = inputSizeBits / DqnStateEncoder.INPUT_BITS_SCALE;
        this.deadlineSeconds = deadlineSeconds;
        this.deadlineNormalized = deadlineSeconds / DqnStateEncoder.DEADLINE_SECONDS_SCALE;
        this.candidates = List.copyOf(candidates);
    }
}
