import com.mechalikh.pureedgesim.experiment.*;
import java.nio.file.*;import java.util.*;

public final class DqnImplementationSelfTest {
 private static int checks;
 public static void main(String[] args)throws Exception{
  DqnState s=state(new int[]{4,9,12},new boolean[]{true,false,true});
  DqnQNetwork net=new DqnQNetwork(16,8,new Random(17));double[] q=net.qValues(s);check(q.length==3,"q output shape varies with candidates");
  List<OffloadingTransition> batch=List.of(new OffloadingTransition(1,s,0,1,state(new int[]{4,9},new boolean[]{true,true}),false));
  DqnQNetwork target=net.copy();double[] targetBefore=target.qValues(s);double loss=net.trainBatch(batch,target,.95,.001);check(Double.isFinite(loss),"finite DQN loss");
  check(!Arrays.equals(net.qValues(s),targetBefore),"online network learns independently of target");target.copyWeightsFrom(net);check(Arrays.equals(net.qValues(s),target.qValues(s)),"target network synchronization");
  DqnReplayBuffer replay=new DqnReplayBuffer(8);replay.add(batch.get(0));check(replay.size()==1&&replay.sample(1,new Random(1)).size()==1,"replay insertion/sample");
  boolean bad=false;try{net.trainBatch(List.of(new OffloadingTransition(2,s,1,0,null,true)),net,.9,.01);}catch(IllegalArgumentException e){bad=true;}check(bad,"masked action rejected in training");
  transitionChecks();agentChecks();System.out.println("DqnImplementationSelfTest: "+checks+" checks passed");
 }
 private static void transitionChecks(){
  DelayedTransitionLedger ledger=new DelayedTransitionLedger();DqnState a=state(new int[]{1,2},new boolean[]{true,true}),b=state(new int[]{1,2,3},new boolean[]{true,true,true}),c=state(new int[]{1},new boolean[]{true});
  check(ledger.onDecision(10,a,0).isEmpty(),"first action waits");ledger.onDecision(11,b,2);
  List<OffloadingTransition> ready=ledger.onTerminal(11,-2);check(ready.isEmpty(),"later task terminal does not consume earlier action");
  ready=ledger.onTerminal(10,0.75);check(ready.size()==1&&ready.get(0).taskId==10&&ready.get(0).reward==0.75&&ready.get(0).nextState==b,"task ID reward correlation and async completion");
  boolean duplicate=false;try{ledger.onTerminal(10,1);}catch(IllegalStateException e){duplicate=true;}check(duplicate&&ledger.wasEmitted(10),"duplicate terminal cannot reinsert transition");
  ledger.onDecision(12,c,0);List<OffloadingTransition> pending=ledger.finishEpisode();check(pending.isEmpty()&&ledger.outstandingWithoutRewardCount()==1&&ledger.status(12).equals("PENDING_NO_REWARD"),"pending task receives no fabricated reward/replay entry");
 }
 private static void agentChecks()throws Exception{
  Path dir=Files.createTempDirectory("dqn-selftest");Path config=dir.resolve("dqn.properties");Files.writeString(config,"hidden1=8\nhidden2=8\nreplay_capacity=64\nbatch_size=1\nwarmup_transitions=1\ntarget_update_interval=1\nepsilon_decay_decisions=10\nseed=303\n");
  DqnConfig cfg=DqnConfig.load(config.toString());DqnAgent one=new DqnAgent(cfg,"train",dir.resolve("one.bin")),two=new DqnAgent(cfg,"train",dir.resolve("two.bin"));DqnState s=state(new int[]{5,8},new boolean[]{false,true});
  check(one.epsilon()==1.0,"training starts at configured epsilon");
  check(one.select(s)==1,"masked action never selected");check(two.select(s)==1,"reproducible random/action mask");
  DqnState terminal=state(new int[]{5,8},new boolean[]{false,true});one.observe(new OffloadingTransition(7,terminal,1,1.0,null,true));
  check(one.replaySize()==1&&one.updates()==1&&Double.isFinite(one.lastLoss()),"training updates replay/network");
  Path ck=dir.resolve("model.bin");DqnAgent saver=new DqnAgent(cfg,"train",ck);saver.observe(new OffloadingTransition(8,terminal,1,1.0,null,true));saver.save();check(Files.size(ck)>0,"checkpoint created");
  byte[] before=Files.readAllBytes(ck);DqnAgent eval=new DqnAgent(cfg,"eval",ck);check(eval.epsilon()==0&&eval.select(s)==1&&eval.replaySize()==1,"frozen checkpoint evaluation and mask");check(Arrays.equals(before,Files.readAllBytes(ck)),"evaluation leaves checkpoint unchanged");
 }
 private static DqnState state(int[] ids,boolean[] mask){double[][] f=new double[ids.length][DqnStateEncoder.CANDIDATE_FEATURE_COUNT];for(int i=0;i<f.length;i++)f[i][0]=i*.1;return new DqnState(ids,mask,new double[]{.2,.3,.4},new double[]{.1,0,.2,0,.4},f);}
 private static void check(boolean ok,String message){checks++;if(!ok)throw new AssertionError(message);}
}
