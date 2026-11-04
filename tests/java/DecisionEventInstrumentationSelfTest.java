import java.lang.reflect.Proxy;
import java.util.List;
import java.util.Map;
import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode;
import com.mechalikh.pureedgesim.experiment.DecisionEventTransitionBuilder;
import com.mechalikh.pureedgesim.experiment.DecisionEventDrainController;
import com.mechalikh.pureedgesim.experiment.DecisionStateSnapshot;
import com.mechalikh.pureedgesim.experiment.IntervalTransition;
import com.mechalikh.pureedgesim.experiment.TaskLifecycleTracker;
import com.mechalikh.pureedgesim.locationmanager.Location;
import com.mechalikh.pureedgesim.simulationengine.Event;
import com.mechalikh.pureedgesim.simulationengine.FutureQueue;
import com.mechalikh.pureedgesim.locationmanager.MobilityModel;
import com.mechalikh.pureedgesim.taskgenerator.Task;

public final class DecisionEventInstrumentationSelfTest {
 static int checks;
 static void ok(boolean x,String m){checks++;if(!x)throw new AssertionError(m);}
 static Object proxy(Class<?> type,java.util.function.Function<String,Object> f){return Proxy.newProxyInstance(type.getClassLoader(),new Class<?>[]{type},(p,m,a)->f.apply(m.getName()));}
 static DecisionStateSnapshot snap(long id,double time,long serial,int taskId,Map<String,Integer> stages){
   Location loc=new Location(2,3);
   MobilityModel mobility=new MobilityModel() { { currentLocation=loc; } protected Location getNextLocation(Location location){return location;} };
   ComputingNode source=(ComputingNode)proxy(ComputingNode.class,n->switch(n){case "getId"->7;case "getMobilityModel"->mobility;default->null;});
   Task task=(Task)proxy(Task.class,n->switch(n){case "getId"->taskId;case "getEdgeDevice"->source;case "getLength"->100.0;case "getFileSizeInBits"->20.0;case "getMaxLatency"->50.0;case "getTime"->0.0;case "getContainerSizeInBits"->10L;case "getOutputSizeInBits"->5.0;case "getApplicationID"->2;default->null;});
   return new DecisionStateSnapshot(id,time,serial,task,List.of(),new boolean[0],stages);
 }
 public static void main(String[] args){
   var stages=new TaskLifecycleTracker(); stages.update(1,TaskLifecycleTracker.Stage.ASSIGNED_NOT_ADMITTED); stages.update(1,TaskLifecycleTracker.Stage.WAITING_QUEUE);
   ok(stages.counts().get("ASSIGNED_NOT_ADMITTED")==0 && stages.counts().get("WAITING_QUEUE")==1,"exclusive lifecycle stage avoids double count");
   var s1=snap(1,1,9,11,stages.counts()); ok(s1.processedEventSerial==9 && s1.task.containerBits==10L,"decision-time fields and event serial copied");
   Event queued=new Event(null,1.0,1), immediate=new Event(null,1.0,2); FutureQueue<Event> q=new FutureQueue<>(); q.add(queued); q.addFirst(immediate);
   ok(q.first()==immediate && immediate.getSerial()<queued.getSerial(),"same-timestamp immediate event precedes normal event by actual serial order");
   try{s1.outstandingTaskStages.put("X",1);throw new AssertionError("stages mutable");}catch(UnsupportedOperationException expected){checks++;}
   try{s1.edcs.add(null);throw new AssertionError("EDC snapshot mutable");}catch(UnsupportedOperationException expected){checks++;}
   var b=new DecisionEventTransitionBuilder(2,3,0.5,Math.log(2));
   ok(b.begin(s1,-1,-1).isEmpty()&&!b.hasOpenInterval(),"empty candidate action does not open interval");
   b.begin(s1,0,20); ok(b.recordTerminal(13,true,2),"first completion recorded"); ok(!b.recordTerminal(13,true,2),"duplicate terminal ignored");
   ok(b.recordTerminal(12,false,4),"out-of-order failure recorded");
   var s2=snap(2,2,10,12,Map.of()); List<IntervalTransition> closed=b.begin(s2,0,21);
   ok(closed.size()==1,"interval closes at next decision");
   IntervalTransition t=closed.get(0); ok(Math.abs(t.reward-(2-1-3-2))<1e-9,"multiple terminal outcomes accumulate once");
   ok(Math.abs(t.elapsedSeconds-1)<1e-9 && Math.abs(t.discountFactor-0.5)<1e-9,"elapsed time discount");
   var terminal=b.finish(2); ok(terminal.size()==1&&terminal.get(0).terminal&&terminal.get(0).nextState==null,"terminal cap closes without fabricated next state");
   var drained=new DecisionEventDrainController(3);drained.begin(5);ok(drained.evaluate(5.1,0)==DecisionEventDrainController.Outcome.DRAINED,"drain exits when unresolved work reaches zero");
   ok(drained.evaluate(7.9,1)==DecisionEventDrainController.Outcome.DRAINING,"unresolved work remains active before cap");
   ok(drained.evaluate(8,1)==DecisionEventDrainController.Outcome.CENSORED,"unresolved work at cap is censored");
   var censorBuilder=new DecisionEventTransitionBuilder(2,3,0,0);censorBuilder.begin(s1,0,20);var censored=censorBuilder.finish(8).get(0);ok(censored.reward==0,"censored tasks create no fabricated failure reward");
   System.out.println("DecisionEventInstrumentationSelfTest: "+checks+" checks passed");
 }
}
