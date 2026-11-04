package com.mechalikh.pureedgesim.experiment;
import java.io.Serializable;import java.util.*;
public final class DqnReplayBuffer implements Serializable {
 private static final long serialVersionUID=1L;private final OffloadingTransition[] data;private int size,next;
 public DqnReplayBuffer(int capacity){data=new OffloadingTransition[capacity];}
 public void add(OffloadingTransition t){if(t.state==null)throw new IllegalArgumentException("transition state required");data[next]=t;next=(next+1)%data.length;if(size<data.length)size++;}
 public int size(){return size;} public int capacity(){return data.length;}
 public List<OffloadingTransition> sample(int count,Random rng){if(count>size)throw new IllegalArgumentException("sample exceeds replay size");List<OffloadingTransition> pool=new ArrayList<>(size);for(int i=0;i<size;i++)pool.add(data[i]);Collections.shuffle(pool,rng);return new ArrayList<>(pool.subList(0,count));}
}
