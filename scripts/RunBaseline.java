package experiment;

import com.mechalikh.pureedgesim.simulationmanager.Simulation;

public class RunBaseline {
  public static void main(String[] args) {
    String settings = args[0] + "/";
    Simulation sim = new Simulation();
    sim.setCustomSettingsFolder(settings);
    sim.setCustomOutputFolder(args[1]);
    sim.launchSimulation();
  }
}
