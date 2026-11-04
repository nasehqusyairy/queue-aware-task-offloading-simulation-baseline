package com.mechalikh.pureedgesim.simulationmanager;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode;
import com.mechalikh.pureedgesim.simulationengine.Event;
import com.mechalikh.pureedgesim.simulationengine.PureEdgeSim;
import com.mechalikh.pureedgesim.scenariomanager.Scenario;
import com.mechalikh.pureedgesim.taskgenerator.Task;
import com.mechalikh.pureedgesim.experiment.OffloadingObservation;
import com.mechalikh.pureedgesim.experiment.OffloadingPolicy;
import com.mechalikh.pureedgesim.experiment.OffloadingTransition;
import com.mechalikh.pureedgesim.experiment.DqnStateEncoder;
import com.mechalikh.pureedgesim.experiment.DqnState;
import com.mechalikh.pureedgesim.experiment.DelayedTransitionLedger;
import com.mechalikh.pureedgesim.experiment.DecisionStateSnapshot;
import com.mechalikh.pureedgesim.experiment.DecisionEventTransitionBuilder;
import com.mechalikh.pureedgesim.experiment.IntervalTransition;
import com.mechalikh.pureedgesim.experiment.TaskLifecycleTracker;
import com.mechalikh.pureedgesim.experiment.DecisionEventDrainController;

/** Isolated manager that requests a fresh policy destination at every task dispatch. */
public final class DqnReadySimulationManager extends PaperAlignedSimulationManager {
    private static final class Decision {
        final long decisionId;
        final DecisionStateSnapshot snapshot;
        final OffloadingObservation observation;
        final List<Integer> candidateIds;
        final boolean[] mask;
        final int action;
        final int selectedEdcId;

        Decision(long decisionId, DecisionStateSnapshot snapshot, OffloadingObservation observation, List<Integer> candidateIds, boolean[] mask,
                int action, int selectedEdcId) {
            this.decisionId=decisionId; this.snapshot=snapshot; this.observation = observation;
            this.candidateIds = List.copyOf(candidateIds);
            this.mask = mask.clone();
            this.action = action;
            this.selectedEdcId = selectedEdcId;
        }
    }

    private final Map<Integer, Decision> decisions = new HashMap<>();
    private final Map<Integer, DecisionStateSnapshot> preparedSnapshots = new HashMap<>();
    private final TaskLifecycleTracker lifecycle = new TaskLifecycleTracker();
    private long nextDecisionId=1;
    private Long currentEventSerial;
    private BufferedWriter decisionEventWriter, snapshotWriter, intervalWriter;
    private DecisionEventTransitionBuilder intervalBuilder;
    private static final int DECISION_EVENT_DRAIN_CHECK=99103;
    private final double decisionEventDrainCapSeconds=Double.parseDouble(System.getProperty("paper.decision-event-drain-seconds","0"));
    private boolean decisionEventDraining;
    private DecisionEventDrainController drainController;
    private final Map<Integer, Boolean> cachedBeforeDispatch = new HashMap<>();
    private final Map<Integer, Integer> cachedDestinationBeforeDispatch = new HashMap<>();
    private final java.util.Set<Integer> cacheBypassTasks = new java.util.HashSet<>();
    private final java.util.Set<Integer> finalizedDecisionIds = new java.util.HashSet<>();
    private BufferedWriter decisionWriter;
    private BufferedWriter ledgerWriter;
    private BufferedWriter transitionWriter;
    private OffloadingPolicy policy;
    private final DelayedTransitionLedger transitionLedger = new DelayedTransitionLedger();
    private final DqnStateEncoder stateEncoder = new DqnStateEncoder();

    public DqnReadySimulationManager(SimLog log, PureEdgeSim engine, int simulationId, int iteration, Scenario scenario) {
        super(log, engine, simulationId, iteration, scenario);
        decisionWriter = open("paper.per-task-decision-log", "task_id,simulation_timestamp_seconds,source_ue_id,selected_action,selected_edc_id,candidate_edc_ids,action_mask,task_mi,task_mi_normalized,input_size_bits,input_size_normalized,deadline_seconds,deadline_normalized,queue_length_per_edc,queue_length_normalized_per_edc,active_tasks_per_edc,active_tasks_normalized_per_edc,estimated_queue_wait_seconds_per_edc,estimated_queue_wait_normalized_per_edc,mips_per_core_per_edc,mips_per_core_normalized_per_edc,cpu_cores_per_edc,cpu_cores_normalized_per_edc,cpu_utilization_percent_per_edc,cpu_utilization_normalized_per_edc,resource_available_per_edc,cache_bypassed,cached_placement_existed,cached_placement_destination_id,decision_source,actual_applied_destination_id,decision_status");
        ledgerWriter = open("paper.per-task-ledger-log", "task_id,event_name,timestamp_seconds,source_ue_id,destination_id,status,failure_reason,total_delay_seconds,network_delay_seconds,queue_wait_seconds,cpu_execution_seconds,stage");
        String transitionPath = System.getProperty("paper.dqn-transition-log");
        if (transitionPath != null && !transitionPath.isBlank())
            transitionWriter = open("paper.dqn-transition-log", "task_id,event_name,timestamp_seconds,reward,transition_status,replay_inserted");
        snapshotWriter=open("paper.decision-event-snapshot-log", "decision_id,timestamp_seconds,event_serial,task_id,source_ue_id,task_mi,input_bits,container_bits,output_bits,deadline_seconds,deadline_remaining_seconds,release_time_seconds,source_x,source_y,application_id,edc_state_json,outstanding_stages_json,active_network_transfer_count");
        decisionEventWriter=open("paper.decision-event-decision-log", "decision_id,task_id,timestamp_seconds,event_serial,candidate_ids,mask,selected_action,selected_edc_id,actual_applied_edc_id,placement_cache_used");
        intervalWriter=open("paper.decision-event-transition-log", "decision_id,source_task_id,state_timestamp_seconds,next_decision_id,next_state_timestamp_seconds,action,selected_edc_id,reward,elapsed_seconds,discount_factor,terminal,next_mask");
        if(intervalWriter!=null) {
            intervalBuilder=new DecisionEventTransitionBuilder(requiredDouble("paper.decision-event-completion-weight"),
                    requiredDouble("paper.decision-event-failure-weight"),requiredDouble("paper.decision-event-delay-weight"),
                    requiredDouble("paper.decision-event-rho"));
        }
    }

    public void registerPolicy(OffloadingPolicy value) {
        if (policy != null) throw new IllegalStateException("policy registered twice");
        policy = value;
    }

    @Override
    protected void sendFromOrchToDestination(Task task) {
        boolean wasCached = task.getEdgeDevice().isApplicationPlaced();
        cachedBeforeDispatch.put(task.getId(), wasCached);
        ComputingNode cachedDestination = task.getEdgeDevice().getApplicationPlacementLocation();
        cachedDestinationBeforeDispatch.put(task.getId(), cachedDestination == null || cachedDestination == ComputingNode.NULL
                ? -1 : cachedDestination.getId());
        cacheBypassTasks.add(task.getId());
        // This isolated policy mode deliberately bypasses the UE placement gate for every task.
        task.getEdgeDevice().setApplicationPlaced(false);
        super.sendFromOrchToDestination(task);
    }

    /** Freeze state before policy selection; the returned ID is finalized after action application. */
    public long preparePolicyDecision(Task task,List<ComputingNode> candidates,boolean[] mask) {
        lifecycle.update(task.getId(),TaskLifecycleTracker.Stage.AT_ORCHESTRATOR_DECISION);
        long id=nextDecisionId++;
        DecisionStateSnapshot snapshot=new DecisionStateSnapshot(id,simulation.clock(),currentEventSerial,task,candidates,mask,lifecycle.counts());
        if(preparedSnapshots.putIfAbsent(task.getId(),snapshot)!=null) throw new IllegalStateException("duplicate prepared snapshot for task "+task.getId());
        writeSnapshot(snapshot);
        return id;
    }

    /** Called exactly once per orchestrator invocation; duplicate task decisions fail closed. */
    public void recordPolicyDecision(Task task, OffloadingObservation observation, List<Integer> candidateIds,
            boolean[] actionMask, int action, int selectedEdcId, String decisionSource) {
        DecisionStateSnapshot snapshot=preparedSnapshots.remove(task.getId());
        if(snapshot==null) throw new IllegalStateException("decision snapshot missing for task "+task.getId());
        Decision previous = decisions.putIfAbsent(task.getId(),
                new Decision(snapshot.decisionId,snapshot,observation, candidateIds, actionMask, action, selectedEdcId));
        if (previous != null) throw new IllegalStateException("duplicate per-task policy decision for task " + task.getId());
        if(intervalBuilder!=null) for(IntervalTransition t:intervalBuilder.begin(snapshot,action,selectedEdcId)) writeInterval(t);
        if (policy instanceof com.mechalikh.pureedgesim.experiment.DqnOffloadingPolicy) {
            DqnState state = stateEncoder.encode(observation, actionMask);
            for (OffloadingTransition ready : transitionLedger.onDecision(task.getId(), state, action)) {
                deliverTransition(ready);
            }
        }
    }

    @Override
    public void recordTaskGenerated(Task task) {
        super.recordTaskGenerated(task);
        ledger(task, "TASK_GENERATED", "GENERATED");
    }

    @Override
    public void recordTaskEvent(Task task, String eventName, String stage) {
        if(task!=null) updateLifecycle(task.getId(),eventName);
        super.recordTaskEvent(task, eventName, stage);
        ledger(task, eventName, stage);
        if (policy instanceof com.mechalikh.pureedgesim.experiment.DqnOffloadingPolicy && "TASK_PENDING_AT_HORIZON".equals(eventName))
            transitionEvent(task.getId(), "HORIZON_PENDING_NO_REWARD", null, transitionLedger.status(task.getId()), false);
        if(intervalBuilder!=null && ("TASK_COMPLETED".equals(eventName) || "TASK_FAILED".equals(eventName)))
            intervalBuilder.recordTerminal(task.getId(),"TASK_COMPLETED".equals(eventName),task.getTotalDelay());
        if (policy instanceof com.mechalikh.pureedgesim.experiment.DqnOffloadingPolicy && ("TASK_COMPLETED".equals(eventName) || "TASK_FAILED".equals(eventName))) {
            boolean success = "TASK_COMPLETED".equals(eventName);
            double reward = policy.terminalReward(success, task.getTotalDelay());
            for (OffloadingTransition ready : transitionLedger.onTerminal(task.getId(), reward)) {
                deliverTransition(ready);
            }
            transitionEvent(task.getId(), "TERMINAL_REWARD", reward, success ? "COMPLETED" : "FAILED", false);
        }
    }

    @Override
    public void processEvent(Event event) {
        Long previousSerial=currentEventSerial; currentEventSerial=event.getSerial();
        if(decisionEventDrainCapSeconds<0||!Double.isFinite(decisionEventDrainCapSeconds)) throw new IllegalArgumentException("decision-event drain cap must be finite and nonnegative");
        if(decisionEventDrainCapSeconds>0 && event.getTag()==PRINT_LOG && !decisionEventDraining) {
            decisionEventDraining=true; drainController=new DecisionEventDrainController(decisionEventDrainCapSeconds); drainController.begin(simulation.clock());
            System.out.printf("DECISION_EVENT_ARRIVAL_CUTOFF time_seconds=%.9f drain_cap_seconds=%.9f generated=%d%n",simulation.clock(),decisionEventDrainCapSeconds,simLog.getGeneratedTasks());
            schedule(this,Math.min(1.0,decisionEventDrainCapSeconds),DECISION_EVENT_DRAIN_CHECK);
            currentEventSerial=previousSerial; return;
        }
        if(decisionEventDrainCapSeconds>0 && event.getTag()==DECISION_EVENT_DRAIN_CHECK) {
            int unresolved=Math.max(0,simLog.getGeneratedTasks()-tasksCount);
            double elapsed=drainController.elapsed(simulation.clock());
            DecisionEventDrainController.Outcome drainOutcome=drainController.evaluate(simulation.clock(),unresolved);
            if(drainOutcome==DecisionEventDrainController.Outcome.DRAINING) {
                schedule(this,Math.min(1.0,decisionEventDrainCapSeconds-elapsed),DECISION_EVENT_DRAIN_CHECK);
                currentEventSerial=previousSerial; return;
            }
            int censored=drainOutcome==DecisionEventDrainController.Outcome.CENSORED?unresolved:0;
            System.out.printf("DECISION_EVENT_DRAIN_END time_seconds=%.9f elapsed_seconds=%.9f unresolved_censored=%d drained=%s%n",simulation.clock(),elapsed,censored,drainOutcome==DecisionEventDrainController.Outcome.DRAINED);
            event=new Event(this,simulation.clock(),PRINT_LOG);
        }
        boolean decisionEvent = event.getTag() == SEND_TASK_FROM_ORCH_TO_DESTINATION && event.getData() instanceof Task;
        Task decisionTask = decisionEvent ? (Task) event.getData() : null;
        super.processEvent(event);
        if (decisionEvent) finalizeDecision(decisionTask);
        if (event.getTag() == PRINT_LOG && intervalBuilder!=null) for(IntervalTransition t:intervalBuilder.finish(simulation.clock())) writeInterval(t);
        if (event.getTag() == PRINT_LOG && policy instanceof com.mechalikh.pureedgesim.experiment.DqnOffloadingPolicy) {
            for (OffloadingTransition ready : transitionLedger.finishEpisode()) {
                deliverTransition(ready);
            }
            transitionEvent(-1, "HORIZON_PENDING_WITHOUT_REWARD", null,
                    "count=" + transitionLedger.outstandingWithoutRewardCount(), false);
        }
        if (event.getTag() == PRINT_LOG && edgeOrchestrator instanceof com.mechalikh.pureedgesim.experiment.DqnReadyOrchestrator dqnReady) {
            dqnReady.endEpisode();
        }
        if (event.getTag() == PRINT_LOG) closeOwnLogs();
        else if(decisionEventDrainCapSeconds>0 && decisionEventDraining && simLog.getGeneratedTasks()>0
                && tasksCount>=simLog.getGeneratedTasks()) scheduleNow(this,DECISION_EVENT_DRAIN_CHECK);
        currentEventSerial=previousSerial;
    }

    private void finalizeDecision(Task task) {
        if (!finalizedDecisionIds.add(task.getId())) throw new IllegalStateException("duplicate decision audit row for task " + task.getId());
        Decision d = decisions.get(task.getId());
        ComputingNode actual = task.getOffloadingDestination();
        int actualId = actual == null || actual == ComputingNode.NULL ? -1 : actual.getId();
        boolean bypassed = cacheBypassTasks.contains(task.getId()) && d != null;
        String status = d == null ? "POLICY_NOT_CALLED" : (d.action < 0 ? "NO_ELIGIBLE_DESTINATION" : "DECIDED");
        if (d != null) writeDecisionRow(task,d,actualId);
        if (d != null && d.selectedEdcId != actualId) {
            throw new IllegalStateException("policy destination " + d.selectedEdcId + " was not applied for task " + task.getId()
                    + "; actual destination=" + actualId);
        }
        if (d == null) {
            write(decisionWriter, String.join(",", csv(task.getId()), csv(simulation.clock()), csv(task.getEdgeDevice().getId()),
                    "", "", "[]", "[]", "", "", "", "", csv(task.getMaxLatency()), "",
                    "{}", "{}", "{}", "{}", "{}", "{}", "{}", "{}", "{}", "{}", "{}", "{}", "{}",
                    Boolean.toString(bypassed), Boolean.toString(cachedBeforeDispatch.getOrDefault(task.getId(), false)),
                    cachedDestinationBeforeDispatch.getOrDefault(task.getId(), -1) < 0 ? "" : csv(cachedDestinationBeforeDispatch.get(task.getId())),
                    "NO_POLICY_CALL", actualId < 0 ? "" : csv(actualId), status));
            return;
        }
        OffloadingObservation o = d.observation;
        write(decisionWriter, String.join(",", csv(task.getId()), csv(simulation.clock()), csv(o.sourceUeId),
                d.action < 0 ? "" : csv(d.action), d.selectedEdcId < 0 ? "" : csv(d.selectedEdcId),
                csv(jsonInts(d.candidateIds)), csv(jsonMask(d.mask)), csv(o.taskMi), csv(o.taskMiNormalized),
                csv(o.inputSizeBits), csv(o.inputSizeNormalized), csv(o.deadlineSeconds), csv(o.deadlineNormalized),
                csv(candidateValues(o, "queue")), csv(candidateValues(o, "queue_norm")),
                csv(candidateValues(o, "active")), csv(candidateValues(o, "active_norm")),
                csv(candidateValues(o, "wait")), csv(candidateValues(o, "wait_norm")),
                csv(candidateValues(o, "mips")), csv(candidateValues(o, "mips_norm")),
                csv(candidateValues(o, "cores")), csv(candidateValues(o, "cores_norm")),
                csv(candidateValues(o, "cpu")), csv(candidateValues(o, "cpu_norm")),
                csv(candidateValues(o, "resource")), Boolean.toString(true),
                Boolean.toString(cachedBeforeDispatch.getOrDefault(task.getId(), false)),
                cachedDestinationBeforeDispatch.getOrDefault(task.getId(), -1) < 0 ? "" : csv(cachedDestinationBeforeDispatch.get(task.getId())),
                d == null ? "NO_POLICY_CALL" : System.getProperty("paper.per-task-policy", "deterministic-task-modulo"),
                actualId < 0 ? "" : csv(actualId), status));
    }

    public void recordNetworkTransferFinished(Task task,String transferType,double remainingBits) {
        // Completion callbacks reveal the transfer type, but active transfers are not exposed as a stable global snapshot.
        if("RESULTS_TO_DEV".equals(transferType)||"RESULTS_TO_ORCH".equals(transferType)) lifecycle.update(task.getId(),TaskLifecycleTracker.Stage.RESULT_TRANSFER);
    }
    private void updateLifecycle(int taskId,String event) {
        switch(event) {
            case "ORCHESTRATION_REQUEST" -> lifecycle.update(taskId,TaskLifecycleTracker.Stage.REQUEST_IN_FLIGHT);
            case "TASK_DISPATCH" -> lifecycle.update(taskId,TaskLifecycleTracker.Stage.ASSIGNED_NOT_ADMITTED);
            case "QUEUE_ENTER" -> lifecycle.update(taskId,TaskLifecycleTracker.Stage.WAITING_QUEUE);
            case "EXECUTION_START" -> lifecycle.update(taskId,TaskLifecycleTracker.Stage.ACTIVE_EXECUTION);
            case "EXECUTION_END", "RESULT_RETURN" -> lifecycle.update(taskId,TaskLifecycleTracker.Stage.RESULT_TRANSFER);
            case "TASK_COMPLETED", "TASK_FAILED" -> lifecycle.update(taskId,TaskLifecycleTracker.Stage.TERMINAL);
            default -> { }
        }
    }
    private void writeSnapshot(DecisionStateSnapshot s) {
        if(snapshotWriter==null)return;
        StringBuilder edcs=new StringBuilder("[");
        for(int i=0;i<s.edcs.size();i++){if(i>0)edcs.append(',');var e=s.edcs.get(i);edcs.append("{\"id\":").append(e.edcId).append(",\"eligible\":").append(e.eligible)
            .append(",\"waiting\":").append(e.waitingTaskCount).append(",\"active\":").append(json(e.activeTaskCount)).append(",\"remaining_active_service_s\":").append(json(e.remainingActiveServiceSeconds))
            .append(",\"queue_wait_estimate_s\":").append(json(e.estimatedQueueWaitSeconds)).append(",\"mips_per_core\":").append(json(e.mipsPerCore)).append(",\"total_cores\":").append(json(e.totalCores))
            .append(",\"available_cores\":").append(json(e.availableCores)).append(",\"cpu_util_percent\":").append(json(e.cpuUtilizationPercent)).append(",\"available_ram_mb\":").append(json(e.availableRamMb)).append(",\"available_storage_mb\":").append(json(e.availableStorageMb)).append('}');}
        edcs.append(']'); var t=s.task;
        write(snapshotWriter,String.join(",",csv(s.decisionId),csv(s.timestampSeconds),csv(s.processedEventSerial),csv(t.taskId),csv(t.sourceUeId),csv(t.mi),csv(t.inputBits),csv(t.containerBits),csv(t.outputBits),csv(t.deadlineSeconds),csv(t.deadlineRemainingSeconds),csv(t.releaseTimeSeconds),csv(t.sourceX),csv(t.sourceY),csv(t.applicationId),csv(edcs.toString()),csv(s.outstandingTaskStages.toString()),csv(s.activeNetworkTransferCount)));
    }
    private void writeDecisionRow(Task task,Decision d,int actualId){if(decisionEventWriter==null)return;write(decisionEventWriter,String.join(",",csv(d.decisionId),csv(task.getId()),csv(d.snapshot.timestampSeconds),csv(d.snapshot.processedEventSerial),csv(d.candidateIds),csv(java.util.Arrays.toString(d.mask)),csv(d.action),csv(d.selectedEdcId),csv(actualId<0?null:actualId),Boolean.toString(cachedBeforeDispatch.getOrDefault(task.getId(),false))));}
    private void writeInterval(IntervalTransition t){if(intervalWriter==null)return;write(intervalWriter,String.join(",",csv(t.decisionId),csv(t.sourceTaskId),csv(t.state.timestampSeconds),csv(t.nextState==null?null:t.nextState.decisionId),csv(t.nextState==null?null:t.nextState.timestampSeconds),csv(t.action),csv(t.selectedEdcId),csv(t.reward),csv(t.elapsedSeconds),csv(t.discountFactor),Boolean.toString(t.terminal),csv(t.nextState==null?null:java.util.Arrays.toString(t.nextState.edcs.stream().map(e->Boolean.TRUE.equals(e.eligible)).toList().toArray()))));}
    private static String json(Number n){return n==null||!Double.isFinite(n.doubleValue())?"null":n.toString();}
    private static double requiredDouble(String key){String value=System.getProperty(key);if(value==null)throw new IllegalStateException(key+" is required when interval transition logging is enabled");return Double.parseDouble(value);}

    private static String candidateValues(OffloadingObservation o, String feature) {
        StringBuilder out = new StringBuilder("{");
        for (int i = 0; i < o.candidates.size(); i++) {
            if (i > 0) out.append(',');
            OffloadingObservation.Candidate c = o.candidates.get(i);
            out.append('"').append(c.edcId).append("\":");
            Object value = switch (feature) {
                case "queue" -> c.waitingQueueLength;
                case "queue_norm" -> c.waitingQueueLengthNormalized;
                case "active" -> c.activeTaskCount;
                case "active_norm" -> c.activeTaskCountNormalized;
                case "wait" -> c.estimatedQueueWaitSeconds;
                case "wait_norm" -> c.estimatedQueueWaitNormalized;
                case "mips" -> c.mipsPerCore;
                case "mips_norm" -> c.mipsPerCoreNormalized;
                case "cores" -> c.cpuCores;
                case "cores_norm" -> c.cpuCoresNormalized;
                case "cpu" -> c.currentCpuUtilizationPercent;
                case "cpu_norm" -> c.currentCpuUtilizationNormalized;
                case "resource" -> c.resourceAvailable;
                default -> throw new IllegalArgumentException("unknown feature " + feature);
            };
            out.append(value == null ? "null" : value);
        }
        return out.append('}').toString();
    }

    private void ledger(Task task, String eventName, String stage) {
        if (ledgerWriter == null || task == null) return;
        ComputingNode destination = task.getOffloadingDestination();
        int destinationId = destination == null || destination == ComputingNode.NULL ? -1 : destination.getId();
        write(ledgerWriter, String.join(",", csv(task.getId()), csv(eventName), csv(simulation.clock()),
                csv(task.getEdgeDevice() == null ? "" : task.getEdgeDevice().getId()),
                destinationId < 0 ? "" : csv(destinationId), csv(task.getStatus() == null ? "" : task.getStatus().name()),
                csv(task.getFailureReason() == null ? "" : task.getFailureReason().name()), csv(task.getTotalDelay()),
                csv(task.getActualNetworkTime()), csv(task.getWatingTime()), csv(task.getActualCpuTime()), csv(stage)));
    }

    private static BufferedWriter open(String property, String header) {
        String path = System.getProperty(property);
        if (path == null || path.isBlank()) throw new IllegalStateException(property + " system property is required");
        try {
            BufferedWriter out = Files.newBufferedWriter(Path.of(path), StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            out.write(header + "\n");
            return out;
        } catch (IOException e) {
            throw new IllegalStateException("cannot create " + property + " CSV", e);
        }
    }

    private static String jsonInts(List<Integer> values) { return values.toString(); }
    private static String jsonMask(boolean[] values) {
        StringBuilder out = new StringBuilder("[");
        for (int i = 0; i < values.length; i++) { if (i > 0) out.append(','); out.append(values[i]); }
        return out.append(']').toString();
    }
    private static String csv(Object value) {
        if (value == null) return "";
        String text = value.toString();
        if (text.contains(",") || text.contains("\"") || text.contains("\n")) return "\"" + text.replace("\"", "\"\"") + "\"";
        return text;
    }
    private static void write(BufferedWriter out, String row) {
        try { out.write(row + "\n"); }
        catch (IOException e) { throw new IllegalStateException("cannot write per-task audit", e); }
    }
    private void closeOwnLogs() {
        close(decisionWriter); close(ledgerWriter); close(transitionWriter); close(decisionEventWriter); close(snapshotWriter); close(intervalWriter);
        decisionWriter = null; ledgerWriter = null; transitionWriter = null; decisionEventWriter=null; snapshotWriter=null; intervalWriter=null;
    }
    private void transitionEvent(int taskId,String event,Double reward,String status,boolean inserted) {
        if (transitionWriter == null) return;
        write(transitionWriter,String.join(",",csv(taskId),csv(event),csv(simulation.clock()),csv(reward),csv(status),Boolean.toString(inserted)));
    }
    private void deliverTransition(OffloadingTransition transition) {
        boolean replayInsertion=policy.updatesFromTransitions();
        policy.observe(transition);
        transitionEvent(transition.taskId,replayInsertion?"REPLAY_INSERTED":"TRANSITION_READY",transition.reward,"READY",replayInsertion);
    }
    private static void close(BufferedWriter out) {
        if (out == null) return;
        try { out.flush(); out.close(); }
        catch (IOException e) { throw new IllegalStateException("cannot close per-task audit", e); }
    }
}
