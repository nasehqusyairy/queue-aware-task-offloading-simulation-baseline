package com.mechalikh.pureedgesim.experiment;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode;
import com.mechalikh.pureedgesim.scenariomanager.SimulationParameters;
import com.mechalikh.pureedgesim.simulationengine.FutureQueue;
import com.mechalikh.pureedgesim.simulationmanager.SimulationManager;
import com.mechalikh.pureedgesim.taskgenerator.Application;
import com.mechalikh.pureedgesim.taskgenerator.DefaultTaskGenerator;
import com.mechalikh.pureedgesim.taskgenerator.Task;

/**
 * Uses the stated task rate as tasks/second per UE assigned to each app profile.
 * App usage percentages allocate UE groups; this is an explicit PureEdgeSim mapping.
 */
public final class PaperAlignedTaskGenerator extends DefaultTaskGenerator {
    public PaperAlignedTaskGenerator(SimulationManager manager) {
        super(manager);
    }

    @Override
    public FutureQueue<Task> generate() {
        double configuredSeconds = SimulationParameters.simulationDuration;
        int seconds = (int) Math.round(configuredSeconds);
        if (Math.abs(configuredSeconds - seconds) > 1e-9) {
            throw new IllegalArgumentException("paper duration must be a whole number of seconds");
        }
        int[] appUserCounts = parseCounts(System.getProperty("paper.app-counts", ""));
        if (appUserCounts.length != SimulationParameters.applicationList.size()) {
            throw new IllegalStateException("paper.app-counts does not match applications.xml");
        }

        List<ComputingNode> sources = new ArrayList<>();
        for (ComputingNode device : devicesList) {
            if (device.isGeneratingTasks()) sources.add(device);
        }
        int expectedSources = 0;
        for (int count : appUserCounts) expectedSources += count;
        if (sources.size() != expectedSources) {
            throw new IllegalStateException("task-source count " + sources.size() + " != app assignment count " + expectedSources);
        }
        Collections.shuffle(sources, random);

        long generated = 0;
        int offset = 0;
        for (int app = 0; app < appUserCounts.length; app++) {
            Application params = SimulationParameters.applicationList.get(app);
            int ratePerSecond = params.getRate();
            if (ratePerSecond <= 0) throw new IllegalArgumentException("application rates must be positive");
            int count = appUserCounts[app];
            for (int user = 0; user < count; user++) {
                ComputingNode device = sources.get(offset++);
                device.setApplicationType(app);
                for (int second = 0; second < seconds; second++) {
                    for (int sequence = 0; sequence < ratePerSecond; sequence++) {
                        Task task = createTask(++id);
                        if (task == null) throw new IllegalStateException("PureEdgeSim could not instantiate a task");
                        task.setType(params.getType());
                        task.setFileSizeInBits(params.getRequestSize());
                        task.setOutputSizeInBits(params.getResultsSize());
                        task.setContainerSizeInBits(params.getContainerSizeInBits());
                        task.setApplicationID(app);
                        task.setMaxLatency(params.getLatency());
                        task.setLength((long) params.getTaskLength());
                        task.setEdgeDevice(device);
                        task.setRegistry(getSimulationManager().getDataCentersManager()
                                .getComputingNodesGenerator().getCloudOnlyList().get(0));
                        task.setTime(second);
                        taskList.add(task);
                        generated++;
                    }
                }
            }
        }
        System.out.printf("PAPER_TASK_GENERATION simulated_seconds=%d active_devices=%d app_user_counts=%s generated_tasks=%d%n",
                seconds, sources.size(), encode(appUserCounts), generated);
        return taskList;
    }

    private static int[] parseCounts(String encoded) {
        if (encoded == null || encoded.isBlank()) throw new IllegalStateException("paper.app-counts is required");
        String[] parts = encoded.split(",");
        int[] result = new int[parts.length];
        for (int i = 0; i < parts.length; i++) {
            result[i] = Integer.parseInt(parts[i].trim());
            if (result[i] < 0) throw new IllegalArgumentException("application user counts cannot be negative");
        }
        return result;
    }

    private static String encode(int[] values) {
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < values.length; i++) {
            if (i > 0) result.append(',');
            result.append(values[i]);
        }
        return result.toString();
    }
}
