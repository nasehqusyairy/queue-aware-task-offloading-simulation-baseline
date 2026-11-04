package com.mechalikh.pureedgesim.experiment;
import java.nio.file.Path;import java.util.List;
public final class DqnOffloadingPolicy implements OffloadingPolicy {
 private final DqnAgent agent;private final DqnConfig config;private final DqnStateEncoder encoder=new DqnStateEncoder();
 public DqnOffloadingPolicy(){String configPath=required("paper.dqn-config"),checkpoint=required("paper.dqn-checkpoint");config=DqnConfig.load(configPath);agent=new DqnAgent(config,System.getProperty("paper.dqn-mode","train"),Path.of(checkpoint));}
 public int selectAction(OffloadingObservation o,List<Integer> ids,boolean[] mask){DqnState s=encoder.encode(o,mask);return agent.select(s);}
 public void observe(OffloadingTransition t){agent.observe(t);}
 public void endEpisode(){System.out.printf("DQN_EPISODE_STATS mode=%s decisions=%d replay_size=%d updates=%d loss=%.12g epsilon=%.8f%n",agent.mode(),agent.episodeDecisions(),agent.replaySize(),agent.updates(),agent.lastLoss(),agent.epsilon());agent.save();}
 public String decisionMetadata(){return "DQN_"+agent.mode()+"_epsilon="+agent.epsilon()+"_replay="+agent.replaySize();}
 public double terminalReward(boolean success,double totalDelaySeconds){if(!Double.isFinite(totalDelaySeconds)||totalDelaySeconds<0)throw new IllegalArgumentException("terminal delay must be finite and non-negative");double delay=config.delayPenalty*totalDelaySeconds/config.delayReference;return success?config.completionReward-delay:-config.failurePenalty-delay;}
 public boolean updatesFromTransitions(){return agent.isTraining();}
 public long decisions(){return agent.decisions();}public long updates(){return agent.updates();}public double lastLoss(){return agent.lastLoss();}
 private static String required(String k){String v=System.getProperty(k);if(v==null||v.isBlank())throw new IllegalStateException(k+" is required");return v;}
}
