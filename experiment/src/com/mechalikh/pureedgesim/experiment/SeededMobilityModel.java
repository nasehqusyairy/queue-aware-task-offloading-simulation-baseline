package com.mechalikh.pureedgesim.experiment;

import java.util.Random;

import com.mechalikh.pureedgesim.locationmanager.DefaultMobilityModel;
import com.mechalikh.pureedgesim.locationmanager.Location;
import com.mechalikh.pureedgesim.scenariomanager.SimulationParameters;
import com.mechalikh.pureedgesim.simulationmanager.SimulationManager;

/** Seed-controlled mobility stream for paired paper-aligned algorithm runs. */
public final class SeededMobilityModel extends DefaultMobilityModel {
    public SeededMobilityModel(SimulationManager manager, Location location) {
        super(manager, location);
    }

    /** Reset both initial placement and movement RNG from seed plus stable UE id. */
    public void configureSeed(long seed, int stableNodeId) {
        Random placement = new Random(mix(seed, stableNodeId, 0x5DEECE66DL));
        double x = placement.nextDouble() * SimulationParameters.simulationMapLength;
        double y = placement.nextDouble() * SimulationParameters.simulationMapWidth;
        currentLocation = new Location(x, y);

        random = new Random(mix(seed, stableNodeId, 0xB4B82E39L));
        orientationAngle = random.nextInt(359);
    }

    private static long mix(long seed, int stableNodeId, long salt) {
        long value = seed ^ (salt + stableNodeId * 0x9E3779B97F4A7C15L);
        value = (value ^ (value >>> 30)) * 0xBF58476D1CE4E5B9L;
        value = (value ^ (value >>> 27)) * 0x94D049BB133111EBL;
        return value ^ (value >>> 31);
    }
}
