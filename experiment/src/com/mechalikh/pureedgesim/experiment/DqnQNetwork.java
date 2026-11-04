package com.mechalikh.pureedgesim.experiment;

import java.io.Serializable;
import java.util.List;
import java.util.Random;

/** Shared candidate-scoring MLP; candidate count may vary between states. */
public final class DqnQNetwork implements Serializable {
    private static final long serialVersionUID = 2L;
    private final int input, h1, h2;
    private final double[][] w1, w2;
    private final double[] b1, b2, wOut;
    private double bOut;
    private final double[][] mw1, vw1, mw2, vw2;
    private final double[] mb1, vb1, mb2, vb2, mwOut, vwOut;
    private double mbOut, vbOut;
    private long optimizerStep;

    public DqnQNetwork(int hidden1, int hidden2, Random random) {
        if (hidden1 < 1 || hidden2 < 1) throw new IllegalArgumentException("hidden dimensions must be positive");
        input = DqnStateEncoder.NETWORK_INPUT_COUNT; h1 = hidden1; h2 = hidden2;
        w1 = matrix(h1, input); b1 = new double[h1]; w2 = matrix(h2, h1); b2 = new double[h2]; wOut = new double[h2];
        mw1 = matrix(h1, input); vw1 = matrix(h1, input); mw2 = matrix(h2, h1); vw2 = matrix(h2, h1);
        mb1 = new double[h1]; vb1 = new double[h1]; mb2 = new double[h2]; vb2 = new double[h2];
        mwOut = new double[h2]; vwOut = new double[h2];
        for (int j=0;j<h1;j++) for(int i=0;i<input;i++) w1[j][i]=random.nextGaussian()*Math.sqrt(2.0/input);
        for (int j=0;j<h2;j++) for(int i=0;i<h1;i++) w2[j][i]=random.nextGaussian()*Math.sqrt(2.0/h1);
        for (int i=0;i<h2;i++) wOut[i]=random.nextGaussian()*Math.sqrt(2.0/h2);
    }

    public double[] qValues(DqnState state) {
        double[] q=new double[state.actionCount()];
        for(int a=0;a<q.length;a++) q[a]=forward(state.featuresForAction(a), null);
        return q;
    }

    public double trainBatch(List<OffloadingTransition> batch, DqnQNetwork target, double gamma, double lr) {
        if (batch.isEmpty()) return 0;
        double[][] gw1=matrix(h1,input), gw2=matrix(h2,h1);
        double[] gb1=new double[h1], gb2=new double[h2], gwo=new double[h2];
        double gbo=0, loss=0;
        for (OffloadingTransition t:batch) {
            if(t.state==null || t.actionIndex<0 || t.actionIndex>=t.state.actionCount() || !t.state.actionMask[t.actionIndex])
                throw new IllegalArgumentException("replay action is masked or out of range");
            double y=t.reward;
            if(!t.terminal) {
                if(t.nextState==null) throw new IllegalArgumentException("nonterminal replay has no next state");
                double[] nq=target.qValues(t.nextState); double max=Double.NEGATIVE_INFINITY;
                for(int a=0;a<nq.length;a++) if(t.nextState.actionMask[a]) max=Math.max(max,nq[a]);
                if(Double.isFinite(max)) y+=gamma*max;
            }
            double[] x=t.state.featuresForAction(t.actionIndex); Forward f=forward(x);
            double error=f.q-y; loss+=error*error; double d=2*error/batch.size(); gbo+=d;
            double[] dz2=new double[h2], da1=new double[h1];
            for(int j=0;j<h2;j++) {
                gwo[j]+=d*f.a2[j]; dz2[j]=d*wOut[j]*(f.z2[j]>0?1:0); gb2[j]+=dz2[j];
                for(int i=0;i<h1;i++){gw2[j][i]+=dz2[j]*f.a1[i];da1[i]+=dz2[j]*w2[j][i];}
            }
            for(int j=0;j<h1;j++) {double d1=da1[j]*(f.z1[j]>0?1:0);gb1[j]+=d1;for(int i=0;i<input;i++)gw1[j][i]+=d1*x[i];}
        }
        long step=++optimizerStep;
        adam(w1,gw1,mw1,vw1,lr,step); adam(b1,gb1,mb1,vb1,lr,step);
        adam(w2,gw2,mw2,vw2,lr,step); adam(b2,gb2,mb2,vb2,lr,step);
        adam(wOut,gwo,mwOut,vwOut,lr,step);
        double[] pp={bOut},gg={gbo},mm={mbOut},vv={vbOut}; adam(pp,gg,mm,vv,lr,step); bOut=pp[0];mbOut=mm[0];vbOut=vv[0];
        return loss/batch.size();
    }

    public DqnQNetwork copy() {
        try { var bytes=new java.io.ByteArrayOutputStream();try(var out=new java.io.ObjectOutputStream(bytes)){out.writeObject(this);}
            try(var in=new java.io.ObjectInputStream(new java.io.ByteArrayInputStream(bytes.toByteArray()))){return (DqnQNetwork)in.readObject();}
        } catch(Exception e){throw new IllegalStateException("could not copy target network",e);}
    }
    public void copyWeightsFrom(DqnQNetwork n) {
        if(input!=n.input||h1!=n.h1||h2!=n.h2)throw new IllegalArgumentException("network dimensions differ");
        copy(n.w1,w1);copy(n.w2,w2);copy(n.wOut,wOut);System.arraycopy(n.b1,0,b1,0,h1);System.arraycopy(n.b2,0,b2,0,h2);bOut=n.bOut;
    }
    private static final class Forward {final double[] z1,a1,z2,a2;final double q;Forward(double[]z1,double[]a1,double[]z2,double[]a2,double q){this.z1=z1;this.a1=a1;this.z2=z2;this.a2=a2;this.q=q;}}
    private Forward forward(double[] x) {
        if(x.length!=input)throw new IllegalArgumentException("network input width mismatch");
        double[] z1=new double[h1],a1=new double[h1],z2=new double[h2],a2=new double[h2];
        for(int j=0;j<h1;j++){double s=b1[j];for(int i=0;i<input;i++)s+=w1[j][i]*x[i];z1[j]=s;a1[j]=Math.max(0,s);}
        for(int j=0;j<h2;j++){double s=b2[j];for(int i=0;i<h1;i++)s+=w2[j][i]*a1[i];z2[j]=s;a2[j]=Math.max(0,s);}
        double q=bOut;for(int i=0;i<h2;i++)q+=wOut[i]*a2[i];return new Forward(z1,a1,z2,a2,q);
    }
    private double forward(double[] x,Object ignored){return forward(x).q;}
    private static void adam(double[][]p,double[][]g,double[][]m,double[][]v,double lr,long t){for(int i=0;i<p.length;i++)adam(p[i],g[i],m[i],v[i],lr,t);}
    private static void adam(double[]p,double[]g,double[]m,double[]v,double lr,long t){double b1=.9,b2=.999,eps=1e-8;for(int i=0;i<p.length;i++){m[i]=b1*m[i]+(1-b1)*g[i];v[i]=b2*v[i]+(1-b2)*g[i]*g[i];p[i]-=lr*(m[i]/(1-Math.pow(b1,t)))/(Math.sqrt(v[i]/(1-Math.pow(b2,t)))+eps);}}
    private static double[][] matrix(int r,int c){return new double[r][c];}
    private static void copy(double[][]a,double[][]b){for(int i=0;i<a.length;i++)System.arraycopy(a[i],0,b[i],0,a[i].length);}
    private static void copy(double[]a,double[]b){System.arraycopy(a,0,b,0,a.length);}
}
