package com.mechalikh.pureedgesim.experiment;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode;
import com.mechalikh.pureedgesim.scenariomanager.SimulationParameters;
import com.mechalikh.pureedgesim.simulationengine.FutureQueue;
import com.mechalikh.pureedgesim.simulationmanager.SimulationManager;
import com.mechalikh.pureedgesim.simulationmanager.PaperAlignedSimulationManager;
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
        String seedProperty = System.getProperty("paper.seed", "");
        if (!seedProperty.isBlank()) random = new Random(Long.parseLong(seedProperty));
        Collections.shuffle(sources, random);

        int[][] homeMatrix = parseHomeMatrix(System.getProperty("paper.home-workload-matrix", ""), appUserCounts);
        int[] sourceApps = new int[sources.size()];
        int[] sourceHomes = new int[sources.size()];
        if (homeMatrix != null) {
            int sourceIndex = 0;
            for (int home = 0; home < homeMatrix.length; home++) {
                for (int app = 0; app < homeMatrix[home].length; app++) {
                    for (int n = 0; n < homeMatrix[home][app]; n++) {
                        if (sourceIndex >= sources.size()) throw new IllegalStateException("home matrix exceeds task sources");
                        sourceApps[sourceIndex] = app;
                        sourceHomes[sourceIndex] = home + 1;
                        sourceIndex++;
                    }
                }
            }
            if (sourceIndex != sources.size()) throw new IllegalStateException("home matrix does not cover all task sources");
        } else {
            int sourceIndex = 0;
            for (int app = 0; app < appUserCounts.length; app++) {
                for (int n = 0; n < appUserCounts[app]; n++) sourceApps[sourceIndex++] = app;
            }
        }

        String auditPath = System.getProperty("paper.home-workload-audit", "");
        BufferedWriter workloadAudit = null;
        if (homeMatrix != null) {
            if (auditPath.isBlank()) throw new IllegalStateException("paper.home-workload-audit is required with a home workload matrix");
            try {
                workloadAudit = Files.newBufferedWriter(Path.of(auditPath), StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
                workloadAudit.write("task_id,home_edc_id,source_id,application_id,release_time_seconds,task_length_mi\n");
            } catch (IOException e) {
                throw new IllegalStateException("cannot create home workload audit", e);
            }
        }

        long generated = 0;
        long[] homeTaskCounts = new long[4];
        long[] homeWorkMi = new long[4];
        try {
        for (int sourceIndex = 0; sourceIndex < sources.size(); sourceIndex++) {
            int app = sourceApps[sourceIndex];
            int home = homeMatrix == null ? 0 : sourceHomes[sourceIndex];
            Application params = SimulationParameters.applicationList.get(app);
            int ratePerSecond = params.getRate();
            if (ratePerSecond <= 0) throw new IllegalArgumentException("application rates must be positive");
            ComputingNode device = sources.get(sourceIndex);
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
                    ComputingNode cloud = getSimulationManager().getDataCentersManager()
                            .getComputingNodesGenerator().getCloudOnlyList().get(0);
                    if (SimulationParameters.enableOrchestrators
                            && "CLOUD".equals(SimulationParameters.deployOrchestrators)) {
                        // The task API lazily promotes its UE to orchestrator if this
                        // field is unset. Explicitly bind the configured Cloud instead.
                        if (device.getOrchestrator() != cloud) device.setOrchestrator(cloud);
                        task.setOrchestrator(cloud);
                    }
                    task.setRegistry(cloud);
                    task.setTime(second);
                    taskList.add(task);
                    if (getSimulationManager() instanceof PaperAlignedSimulationManager traceManager) {
                        traceManager.recordTaskGenerated(task);
                    }
                    if (workloadAudit != null) {
                        workloadAudit.write(task.getId() + "," + home + "," + device.getId() + "," + app + ","
                                + second + "," + params.getTaskLength() + "\n");
                    }
                    if (home > 0) {
                        homeTaskCounts[home - 1]++;
                        homeWorkMi[home - 1] += params.getTaskLength();
                    }
                    generated++;
                }
            }
        }
        } catch (IOException e) {
            throw new IllegalStateException("cannot write home workload audit", e);
        } finally {
            if (workloadAudit != null) try { workloadAudit.close(); }
            catch (IOException e) { throw new IllegalStateException("cannot close home workload audit", e); }
        }
        System.out.printf("PAPER_TASK_GENERATION simulated_seconds=%d active_devices=%d app_user_counts=%s generated_tasks=%d%n",
                seconds, sources.size(), encode(appUserCounts), generated);
        if (homeMatrix != null) {
            System.out.printf("PAPER_HOME_WORKLOAD matrix=%s task_counts=%s work_mi=%s execution_destination_unconstrained=true%n",
                    encode(homeMatrix), encode(homeTaskCounts), encode(homeWorkMi));
        }
        return taskList;
    }

    private static int[][] parseHomeMatrix(String encoded, int[] appUserCounts) {
        if (encoded == null || encoded.isBlank()) return null;
        String[] rows = encoded.split(";");
        if (rows.length != 4) throw new IllegalArgumentException("home workload matrix must have four EDC rows");
        int[][] matrix = new int[4][appUserCounts.length];
        int[] columnSums = new int[appUserCounts.length];
        for (int row = 0; row < rows.length; row++) {
            String[] values = rows[row].split(",");
            if (values.length != appUserCounts.length) throw new IllegalArgumentException("home matrix app column count mismatch");
            for (int col = 0; col < values.length; col++) {
                matrix[row][col] = Integer.parseInt(values[col].trim());
                if (matrix[row][col] < 0) throw new IllegalArgumentException("home workload counts cannot be negative");
                columnSums[col] += matrix[row][col];
            }
        }
        if (!java.util.Arrays.equals(columnSums, appUserCounts)) {
            throw new IllegalArgumentException("home matrix columns must equal app user counts: "
                    + encode(columnSums) + " != " + encode(appUserCounts));
        }
        return matrix;
    }

    private static String encode(int[][] values) {
        StringBuilder out = new StringBuilder();
        for (int r = 0; r < values.length; r++) {
            if (r > 0) out.append(';');
            for (int c = 0; c < values[r].length; c++) {
                if (c > 0) out.append(',');
                out.append(values[r][c]);
            }
        }
        return out.toString();
    }

    private static String encode(long[] values) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < values.length; i++) {
            if (i > 0) out.append(',');
            out.append(values[i]);
        }
        return out.toString();
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
