package com.mechalikh.pureedgesim.experiment;

import java.util.EnumMap;
import java.util.Map;

/** Mutually exclusive observed lifecycle stage per task; unknown network internals remain unavailable. */
public final class TaskLifecycleTracker {
    public enum Stage { REQUEST_IN_FLIGHT, AT_ORCHESTRATOR_DECISION, ASSIGNED_NOT_ADMITTED, WAITING_QUEUE, ACTIVE_EXECUTION, RESULT_TRANSFER, TERMINAL }
    private final Map<Integer,Stage> stages=new java.util.HashMap<>();
    public void update(int taskId,Stage stage){if(stage==Stage.TERMINAL)stages.remove(taskId);else stages.put(taskId,stage);}
    public Map<String,Integer> counts(){
        EnumMap<Stage,Integer> counts=new EnumMap<>(Stage.class); for(Stage s:stages.values()) counts.merge(s,1,Integer::sum);
        Map<String,Integer> out=new java.util.LinkedHashMap<>(); for(Stage s:Stage.values())out.put(s.name(),counts.getOrDefault(s,0)); return java.util.Collections.unmodifiableMap(new java.util.LinkedHashMap<>(out));
    }
    public Stage stage(int taskId){return stages.get(taskId);}
}
