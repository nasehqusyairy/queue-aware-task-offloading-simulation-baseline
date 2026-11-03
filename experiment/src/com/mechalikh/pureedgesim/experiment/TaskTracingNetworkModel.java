package com.mechalikh.pureedgesim.experiment;

import com.mechalikh.pureedgesim.network.DefaultNetworkModel;
import com.mechalikh.pureedgesim.network.TransferProgress;
import com.mechalikh.pureedgesim.simulationmanager.PaperAlignedSimulationManager;
import com.mechalikh.pureedgesim.simulationmanager.SimulationManager;

/** Network-model observer enabled only for the experiment task-event trace. */
public final class TaskTracingNetworkModel extends DefaultNetworkModel {
    public TaskTracingNetworkModel(SimulationManager manager) {
        super(manager);
    }

    @Override
    protected void transferFinished(TransferProgress transfer) {
        if (transfer.getTransferType() == TransferProgress.Type.TASK
                && transfer.getVertexList().size() == 1) {
            ((PaperAlignedSimulationManager) simulationManager).recordTaskEvent(
                    transfer.getTask(), "DESTINATION_ARRIVAL", "TASK_TRANSFER_COMPLETE");
        }
        super.transferFinished(transfer);
    }
}
