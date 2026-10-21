package com.mechalikh.pureedgesim.experiment;

import java.io.InputStream;
import java.io.FileInputStream;
import java.lang.reflect.InvocationTargetException;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.List;

import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode;
import com.mechalikh.pureedgesim.datacentersmanager.DefaultComputingNodesGenerator;
import com.mechalikh.pureedgesim.locationmanager.MobilityModel;
import com.mechalikh.pureedgesim.scenariomanager.SimulationParameters;
import com.mechalikh.pureedgesim.simulationmanager.SimulationManager;

/** Applies largest-remainder counts supplied by the Python protocol layer. */
public final class PaperAlignedComputingNodesGenerator extends DefaultComputingNodesGenerator {
    public PaperAlignedComputingNodesGenerator(SimulationManager manager,
            Class<? extends MobilityModel> mobilityModel, Class<? extends ComputingNode> computingNode) {
        super(manager, mobilityModel, computingNode);
    }

    @Override
    public void generateEdgeDevices() {
        String encoded = System.getProperty("paper.profile-counts", "");
        if (encoded.isBlank()) {
            throw new IllegalStateException("paper.profile-counts system property is required");
        }
        int[] counts = parseCounts(encoded);
        try (InputStream input = new FileInputStream(SimulationParameters.edgeDevicesFile)) {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            NodeList profiles = factory.newDocumentBuilder().parse(input).getElementsByTagName("device");
            if (profiles.getLength() != counts.length) {
                throw new IllegalStateException("profile count vector length does not match edge_devices.xml");
            }
            List<Integer> actual = new ArrayList<>();
            int activeSources = 0;
            int cloudAssignments = 0;
            for (int i = 0; i < profiles.getLength(); i++) {
                Element profile = (Element) profiles.item(i);
                int count = counts[i];
                actual.add(0);
                for (int n = 0; n < count; n++) {
                    ComputingNode node = createComputingNode(profile, SimulationParameters.TYPES.EDGE_DEVICE);
                    // Upstream setAsOrchestrator(false) still sets the node's orchestrator reference to itself.
                    // Override that reference explicitly when the study deploys its orchestrator at Cloud.
                    if (SimulationParameters.enableOrchestrators
                            && "CLOUD".equals(SimulationParameters.deployOrchestrators)) {
                        if (cloudOnlyList.size() != 1) {
                            throw new IllegalStateException("Cloud orchestrator requested but exactly one Cloud is required");
                        }
                        node.setOrchestrator(cloudOnlyList.get(0));
                        cloudAssignments++;
                    }
                    insertEdgeDevice(node);
                    actual.set(i, actual.get(i) + 1);
                    if (node.isGeneratingTasks()) activeSources++;
                }
            }
            int requested = getSimulationManager().getScenario().getDevicesCount();
            if (mistOnlyList.size() != requested || sum(counts) != requested) {
                throw new IllegalStateException("actual UE count " + mistOnlyList.size() + " != requested " + requested);
            }
            System.out.printf("PAPER_DEVICE_COUNTS requested=%d actual=%d profiles=%s active_task_sources=%d edge_data_centers=%d cloud=%d%n",
                    requested, mistOnlyList.size(), encoded, activeSources, edgeOnlyList.size(), cloudOnlyList.size());
            if (SimulationParameters.enableOrchestrators
                    && "CLOUD".equals(SimulationParameters.deployOrchestrators)) {
                System.out.printf("PAPER_ORCHESTRATOR_ASSIGNMENTS target=CLOUD assigned_user_devices=%d cloud_flag=%s%n",
                        cloudAssignments, cloudOnlyList.get(0).isOrchestrator());
            }
        } catch (Exception e) {
            if (e instanceof RuntimeException runtime) throw runtime;
            throw new IllegalStateException("could not instantiate paper-aligned UE profiles", e);
        }
    }

    private static int[] parseCounts(String encoded) {
        String[] parts = encoded.split(",");
        int[] result = new int[parts.length];
        for (int i = 0; i < parts.length; i++) {
            result[i] = Integer.parseInt(parts[i].trim());
            if (result[i] < 0) throw new IllegalArgumentException("profile counts cannot be negative");
        }
        return result;
    }

    private static int sum(int[] values) {
        int result = 0;
        for (int value : values) result += value;
        return result;
    }
}
