package com.mechalikh.pureedgesim.experiment;

import java.util.HashSet;
import java.util.Set;

import com.mechalikh.pureedgesim.simulationengine.Event;
import com.mechalikh.pureedgesim.simulationmanager.PaperAlignedSimulationManager;
import com.mechalikh.pureedgesim.simulationmanager.SimulationManager;
import com.mechalikh.pureedgesim.taskgenerator.Task;

/** Queue-Aware node with observational task lifecycle tracing enabled. */
public final class TaskTracingQueueAwareComputingNode extends QueueAwareComputingNode {
    private final Set<Integer> queuedTaskIds = new HashSet<>();

    public TaskTracingQueueAwareComputingNode(SimulationManager manager, double mipsPerCore, int cores,
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
    }

    @Override
    protected void startExecution(Task task) {
        if (queuedTaskIds.remove(task.getId())) {
            traceManager().recordTaskEvent(task, "QUEUE_EXIT", "LEAVING_WAIT_QUEUE");
        }
        super.startExecution(task);
        traceManager().recordTaskEvent(task, "EXECUTION_START", "CPU_RUNNING");
    }

    @Override
    protected void executionFinished(Event event) {
        super.executionFinished(event);
        traceManager().recordTaskEvent((Task) event.getData(), "EXECUTION_END", "CPU_FINISHED");
    }

    private PaperAlignedSimulationManager traceManager() {
        return (PaperAlignedSimulationManager) simulationManager;
    }
}
