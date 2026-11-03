package com.mechalikh.pureedgesim.experiment;

import java.util.HashSet;
import java.util.Set;

import com.mechalikh.pureedgesim.datacentersmanager.DefaultComputingNode;
import com.mechalikh.pureedgesim.simulationengine.Event;
import com.mechalikh.pureedgesim.simulationmanager.PaperAlignedSimulationManager;
import com.mechalikh.pureedgesim.simulationmanager.SimulationManager;
import com.mechalikh.pureedgesim.taskgenerator.Task;

/** Experiment-only computing node that observes queue and CPU lifecycle events. */
public final class TaskTracingComputingNode extends DefaultComputingNode {
    private final Set<Integer> queuedTaskIds = new HashSet<>();
    private final Set<Integer> activeTaskIds = new HashSet<>();

    public TaskTracingComputingNode(SimulationManager manager, double mipsPerCore, int cores,
            double storage, double ram) {
        super(manager, mipsPerCore, cores, storage, ram);
    }

    @Override
    public void submitTask(Task task) {
        traceManager().recordTaskEvent(task, "TASK_SUBMISSION", "AT_COMPUTING_NODE");
        super.submitTask(task);
        if (getTasksQueue().contains(task)) {
            queuedTaskIds.add(task.getId());
            traceManager().recordTaskEvent(task, "QUEUE_ENTER", "WAITING_FOR_CORE");
        }
        traceManager().recordNodeState(this, "TASK_SUBMITTED", activeTaskIds.size(), getTasksQueue().size());
    }

    @Override
    protected void startExecution(Task task) {
        if (queuedTaskIds.remove(task.getId())) {
            traceManager().recordTaskEvent(task, "QUEUE_EXIT", "LEAVING_WAIT_QUEUE");
        }
        super.startExecution(task);
        activeTaskIds.add(task.getId());
        traceManager().recordTaskEvent(task, "EXECUTION_START", "CPU_RUNNING");
        traceManager().recordNodeState(this, "EXECUTION_START", activeTaskIds.size(), getTasksQueue().size());
    }

    @Override
    protected void executionFinished(Event event) {
        super.executionFinished(event);
        Task task = (Task) event.getData();
        activeTaskIds.remove(task.getId());
        traceManager().recordTaskEvent(task, "EXECUTION_END", "CPU_FINISHED");
        traceManager().recordNodeState(this, "EXECUTION_END", activeTaskIds.size(), getTasksQueue().size());
    }

    public int getActiveTaskCount() { return activeTaskIds.size(); }

    private PaperAlignedSimulationManager traceManager() {
        return (PaperAlignedSimulationManager) simulationManager;
    }
}
