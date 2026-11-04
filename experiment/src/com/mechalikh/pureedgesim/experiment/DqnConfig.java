package com.mechalikh.pureedgesim.experiment;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public final class DqnConfig {
    public final int hidden1, hidden2, replayCapacity, batchSize, warmup, targetUpdate, epsilonDecayDecisions;
    public final double gamma, learningRate, epsilonStart, epsilonEnd, completionReward, failurePenalty, delayPenalty, delayReference;
    public final long seed;
    private DqnConfig(Properties p) {
        hidden1=i(p,"hidden1",64); hidden2=i(p,"hidden2",64); replayCapacity=i(p,"replay_capacity",5000); batchSize=i(p,"batch_size",32);
        warmup=i(p,"warmup_transitions",64); targetUpdate=i(p,"target_update_interval",100); epsilonDecayDecisions=i(p,"epsilon_decay_decisions",5000);
        gamma=d(p,"gamma",0.95); learningRate=d(p,"learning_rate",0.0005); epsilonStart=d(p,"epsilon_start",1.0); epsilonEnd=d(p,"epsilon_end",0.05);
        completionReward=d(p,"completion_reward",1.0); failurePenalty=d(p,"failure_penalty",1.0); delayPenalty=d(p,"delay_penalty_coefficient",0.1);
        delayReference=d(p,"delay_normalization_seconds",5.0); seed=Long.parseLong(p.getProperty("seed","1"));
        if(hidden1<1||hidden2<1||replayCapacity<1||batchSize<1||warmup<0||targetUpdate<1||epsilonDecayDecisions<1||gamma<0||gamma>1||learningRate<=0||epsilonStart<epsilonEnd||epsilonEnd<0||delayReference<=0||completionReward<=0||failurePenalty<=0||delayPenalty<0)
            throw new IllegalArgumentException("invalid DQN configuration");
    }
    public static DqnConfig load(String path) {
        Properties p=new Properties(); try(var in=Files.newInputStream(Path.of(path))){p.load(in);}catch(IOException e){throw new IllegalStateException("cannot read DQN config "+path,e);} return new DqnConfig(p);
    }
    public String fingerprint(){return hidden1+"|"+hidden2+"|"+replayCapacity+"|"+batchSize+"|"+warmup+"|"+targetUpdate+"|"+epsilonDecayDecisions+"|"+gamma+"|"+learningRate+"|"+epsilonStart+"|"+epsilonEnd+"|"+completionReward+"|"+failurePenalty+"|"+delayPenalty+"|"+delayReference+"|"+seed;}
    private static int i(Properties p,String k,int v){return Integer.parseInt(p.getProperty(k,Integer.toString(v)));}
    private static double d(Properties p,String k,double v){return Double.parseDouble(p.getProperty(k,Double.toString(v)));}
}
