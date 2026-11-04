package com.mechalikh.pureedgesim.experiment;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Collections;

import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode;
import com.mechalikh.pureedgesim.datacentersmanager.DefaultComputingNode;
import com.mechalikh.pureedgesim.locationmanager.Location;
import com.mechalikh.pureedgesim.taskgenerator.Task;

/** Immutable, decision-time snapshot. Null measurements mean the simulator did not expose them. */
public final class DecisionStateSnapshot {
    public static final class TaskState {
        public final int taskId, sourceUeId;
        public final double mi, inputBits, deadlineSeconds, deadlineRemainingSeconds, releaseTimeSeconds;
        public final Long containerBits;
        public final Double outputBits, sourceX, sourceY;
        public final int applicationId;
        TaskState(Task task, double now) {
            taskId=task.getId(); sourceUeId=task.getEdgeDevice().getId(); mi=task.getLength(); inputBits=task.getFileSizeInBits();
            deadlineSeconds=task.getMaxLatency(); releaseTimeSeconds=task.getTime();
            deadlineRemainingSeconds=Math.max(0, deadlineSeconds-(now-releaseTimeSeconds));
            containerBits=task.getContainerSizeInBits(); outputBits=task.getOutputSizeInBits(); applicationId=task.getApplicationID();
            Location loc=task.getEdgeDevice().getMobilityModel().getCurrentLocation();
            sourceX=loc==null?null:loc.getXPos(); sourceY=loc==null?null:loc.getYPos();
        }
    }
    public static final class EdcState {
        public final int edcId, waitingTaskCount;
        public final Boolean eligible;
        public final Integer activeTaskCount, totalCores, availableCores;
        public final Double remainingActiveServiceSeconds, estimatedQueueWaitSeconds, mipsPerCore, cpuUtilizationPercent, availableRamMb, availableStorageMb;
        EdcState(ComputingNode node, boolean eligible) {
            edcId=node.getId(); this.eligible=eligible; waitingTaskCount=node.getTasksQueue().size();
            if (node instanceof QueueAwareComputingNode q) {
                activeTaskCount=q.getActiveTaskCount(); remainingActiveServiceSeconds=q.getActiveRemainingServiceSeconds();
                var estimate=q.estimateQueueWaitSeconds(); estimatedQueueWaitSeconds=estimate.isPresent()?estimate.getAsDouble():null;
                availableCores=q.getAvailableCpuCores();
            } else { activeTaskCount=null; remainingActiveServiceSeconds=null; estimatedQueueWaitSeconds=null; availableCores=null; }
            if (node instanceof DefaultComputingNode d) totalCores=(int)d.getNumberOfCPUCores(); else totalCores=null;
            mipsPerCore=node.getMipsPerCore(); cpuUtilizationPercent=node.getCurrentCpuUtilization();
            availableRamMb=node.getAvailableRam(); availableStorageMb=node.getAvailableStorage();
        }
    }
    public final long decisionId;
    public final double timestampSeconds;
    public final Long processedEventSerial;
    public final TaskState task;
    public final List<EdcState> edcs;
    /** Mutually exclusive observed lifecycle buckets; network active-transfer counts are not exposed by PureEdgeSim. */
    public final Map<String,Integer> outstandingTaskStages;
    public final Integer activeNetworkTransferCount;

    public DecisionStateSnapshot(long id,double time,Long eventSerial,Task task,List<ComputingNode> candidates,boolean[] mask,Map<String,Integer> stages) {
        if(candidates.size()!=mask.length) throw new IllegalArgumentException("candidate/mask length mismatch");
        decisionId=id; timestampSeconds=time; processedEventSerial=eventSerial; this.task=new TaskState(task,time);
        List<EdcState> copy=new ArrayList<>(); for(int i=0;i<candidates.size();i++) copy.add(new EdcState(candidates.get(i),mask[i]));
        edcs=List.copyOf(copy); outstandingTaskStages=Collections.unmodifiableMap(new java.util.LinkedHashMap<>(stages)); activeNetworkTransferCount=null;
    }
}
