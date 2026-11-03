package com.mechalikh.pureedgesim.experiment;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.OptionalDouble;

import com.mechalikh.pureedgesim.datacentersmanager.DefaultComputingNode;
import com.mechalikh.pureedgesim.simulationengine.Event;
import com.mechalikh.pureedgesim.simulationmanager.SimulationManager;
import com.mechalikh.pureedgesim.taskgenerator.Task;

/**
 * Observational subclass used only by queue-aware experiments. Execution and
 * queue transitions remain in DefaultComputingNode; this class tracks the
 * start time of active tasks to estimate their remaining service time.
 */
public class QueueAwareComputingNode extends DefaultComputingNode implements QueueWorkloadView {
    private static final class ActiveTask {
        final double lengthMi;
        final double startedAtSeconds;

        ActiveTask(double lengthMi, double startedAtSeconds) {
            this.lengthMi = lengthMi;
            this.startedAtSeconds = startedAtSeconds;
        }
    }

    private final Map<Integer, ActiveTask> activeTasks = new LinkedHashMap<>();

    public QueueAwareComputingNode(SimulationManager manager, double mipsPerCore, int cores,
            double storage, double ram) {
        super(manager, mipsPerCore, cores, storage, ram);
    }

    @Override
    protected void startExecution(Task task) {
        activeTasks.put(task.getId(), new ActiveTask(task.getLength(), getSimulation().clock()));
        super.startExecution(task);
    }

    @Override
    protected void executionFinished(Event event) {
        Task task = (Task) event.getData();
        activeTasks.remove(task.getId());
        super.executionFinished(event);
    }

    @Override
    public OptionalDouble estimateQueueWaitSeconds() {
        if (numberOfCPUCores <= 0 || !Double.isFinite(mipsPerCore) || mipsPerCore <= 0
                || activeTasks.size() > numberOfCPUCores) {
            return OptionalDouble.empty();
        }
        double now = getSimulation().clock();
        List<Double> activeRemainingSeconds = new ArrayList<>();
        for (ActiveTask active : activeTasks.values()) {
            double elapsed = now - active.startedAtSeconds;
            if (!Double.isFinite(elapsed) || elapsed < 0) return OptionalDouble.empty();
            double serviceSeconds = active.lengthMi / mipsPerCore;
            if (!Double.isFinite(serviceSeconds) || serviceSeconds < 0) return OptionalDouble.empty();
            activeRemainingSeconds.add(Math.max(0, serviceSeconds - elapsed));
        }
        double[] active = new double[activeRemainingSeconds.size()];
        for (int i = 0; i < active.length; i++) active[i] = activeRemainingSeconds.get(i);

        List<Task> waiting = getTasksQueue();
        double[] queuedLengths = new double[waiting.size()];
        for (int i = 0; i < queuedLengths.length; i++) queuedLengths[i] = waiting.get(i).getLength();
        return QueueAwareScoring.estimateQueueWaitSeconds(active, queuedLengths, numberOfCPUCores, mipsPerCore);
    }

    public int getWaitingQueueLength() {
        return getTasksQueue().size();
    }

    public int getActiveTaskCount() {
        return activeTasks.size();
    }
}
