package com.mechalikh.pureedgesim.experiment;

import java.io.*;import java.nio.file.*;import java.util.*;

/** In-process Java DQN: shared-candidate MLP, masked epsilon-greedy, replay and Adam. */
public final class DqnAgent {
 private static final class Checkpoint implements Serializable {private static final long serialVersionUID=1L;DqnQNetwork online,target;DqnReplayBuffer replay;long decisions,updates,episodes;double lastLoss;Random random;String configFingerprint;Checkpoint(DqnConfig c){configFingerprint=c.fingerprint();random=new Random(c.seed);online=new DqnQNetwork(c.hidden1,c.hidden2,random);target=online.copy();replay=new DqnReplayBuffer(c.replayCapacity);}}
 private final DqnConfig config;private final String mode;private final Path path;private final Random rng;private final Checkpoint state;private final boolean saveAtEnd;private long episodeDecisions;
 public DqnAgent(DqnConfig c,String mode,Path checkpoint){this.config=c;this.mode=mode;this.path=checkpoint;this.saveAtEnd="train".equals(mode);
  if(!mode.equals("train")&&!mode.equals("eval"))throw new IllegalArgumentException("DQN mode must be train or eval");
  if(Files.exists(checkpoint)){state=load(checkpoint);if(state.online==null||state.target==null||state.replay==null)throw new IllegalStateException("invalid DQN checkpoint");}
  else {if(mode.equals("eval"))throw new IllegalStateException("frozen evaluation checkpoint does not exist: "+checkpoint);state=new Checkpoint(c);}
  if(state.replay.capacity()!=c.replayCapacity||!c.fingerprint().equals(state.configFingerprint))throw new IllegalArgumentException("checkpoint and DQN config differ");rng=state.random;
 }
 public int select(DqnState s){List<Integer> eligible=new ArrayList<>();for(int i=0;i<s.actionCount();i++)if(s.actionMask[i])eligible.add(i);if(eligible.isEmpty())return -1;
  double[] q=state.online.qValues(s);for(int a:eligible)if(!Double.isFinite(q[a]))throw new IllegalStateException("DQN produced non-finite Q value");
  double epsilon=epsilon();state.decisions++;episodeDecisions++;if(mode.equals("train")&&rng.nextDouble()<epsilon)return eligible.get(rng.nextInt(eligible.size()));
  int best=eligible.get(0);for(int a:eligible)if(q[a]>q[best])best=a;return best;
 }
 public void observe(OffloadingTransition t){if(!mode.equals("train"))return;state.replay.add(t);if(state.replay.size()>=Math.max(config.warmup,config.batchSize)){state.lastLoss=state.online.trainBatch(state.replay.sample(config.batchSize,rng),state.target,config.gamma,config.learningRate);state.updates++;if(state.updates%config.targetUpdate==0)state.target.copyWeightsFrom(state.online);}}
 public double epsilon(){if(mode.equals("eval"))return 0;double f=Math.min(1.0,state.decisions/(double)config.epsilonDecayDecisions);return config.epsilonStart+f*(config.epsilonEnd-config.epsilonStart);}
 public int replaySize(){return state.replay.size();}public long decisions(){return state.decisions;}public long episodeDecisions(){return episodeDecisions;}public long updates(){return state.updates;}public double lastLoss(){return state.lastLoss;}public String mode(){return mode;}
 public boolean isTraining(){return mode.equals("train");}
 public void save(){if(!saveAtEnd)return;state.episodes++;try{Path parent=path.toAbsolutePath().getParent();Files.createDirectories(parent);Path tmp=path.resolveSibling(path.getFileName()+".tmp");try(ObjectOutputStream o=new ObjectOutputStream(Files.newOutputStream(tmp,StandardOpenOption.CREATE,StandardOpenOption.TRUNCATE_EXISTING))){o.writeObject(state);}try{Files.move(tmp,path,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);}catch(AtomicMoveNotSupportedException e){Files.move(tmp,path,StandardCopyOption.REPLACE_EXISTING);}}catch(IOException e){throw new IllegalStateException("could not save DQN checkpoint",e);}}
 private static Checkpoint load(Path p){try(ObjectInputStream in=new ObjectInputStream(Files.newInputStream(p))){return (Checkpoint)in.readObject();}catch(Exception e){throw new IllegalStateException("could not load DQN checkpoint "+p,e);}}
}
