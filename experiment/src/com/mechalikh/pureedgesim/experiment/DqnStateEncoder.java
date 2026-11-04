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
}
