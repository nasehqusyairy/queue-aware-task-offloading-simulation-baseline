package com.mechalikh.pureedgesim.experiment;

import com.mechalikh.pureedgesim.simulationengine.Event;
import com.mechalikh.pureedgesim.simulationmanager.DqnReadySimulationManager;
import com.mechalikh.pureedgesim.simulationmanager.SimulationManager;
import com.mechalikh.pureedgesim.taskgenerator.Task;

/** Queue-visible node with lifecycle callbacks for the isolated per-task mode. */
public final class DqnReadyComputingNode extends QueueAwareComputingNode {
    public DqnReadyComputingNode(SimulationManager manager, double mipsPerCore, int cores,
            double storage, double ram) {
        super(manager, mipsPerCore, cores, storage, ram);
    }

    @Override
    public void submitTask(Task task) {
        audit().recordTaskEvent(task, "TASK_SUBMISSION", "AT_COMPUTING_NODE");
        super.submitTask(task);
        if (getTasksQueue().contains(task)) audit().recordTaskEvent(task, "QUEUE_ENTER", "WAITING_FOR_CORE");
        audit().recordNodeState(this, "TASK_SUBMITTED", getActiveTaskCount(), getWaitingQueueLength());
    }

    @Override
    protected void startExecution(Task task) {
        super.startExecution(task);
        audit().recordTaskEvent(task, "EXECUTION_START", "CPU_RUNNING");
        audit().recordNodeState(this, "EXECUTION_START", getActiveTaskCount(), getWaitingQueueLength());
    }

    @Override
    protected void executionFinished(Event event) {
        super.executionFinished(event);
        Task task = (Task) event.getData();
        audit().recordTaskEvent(task, "EXECUTION_END", "CPU_FINISHED");
        audit().recordNodeState(this, "EXECUTION_END", getActiveTaskCount(), getWaitingQueueLength());
    }

    private DqnReadySimulationManager audit() {
        return (DqnReadySimulationManager) simulationManager;
    }
}
