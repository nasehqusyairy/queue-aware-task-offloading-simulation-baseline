package com.mechalikh.pureedgesim.experiment;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Collection;
import java.util.stream.Collectors;

import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode;

/** Stable EDC action ordering and fail-closed action-mask validation helpers. */
public final class DqnActionSpace {
    private DqnActionSpace() {}

    public static List<ComputingNode> stableOrder(List<ComputingNode> nodes) {
        List<ComputingNode> ordered = new ArrayList<>(nodes);
        ordered.sort(Comparator.comparingInt(ComputingNode::getId));
        return ordered;
    }

    public static List<Integer> stableIds(List<ComputingNode> nodes) {
        return stableOrder(nodes).stream().map(ComputingNode::getId).collect(Collectors.toUnmodifiableList());
    }

    public static List<Integer> stableIdsFromIds(Collection<Integer> nodeIds) {
        return nodeIds.stream().sorted().collect(Collectors.toUnmodifiableList());
    }

    public static int validateAction(int action, boolean[] actionMask) {
        if (action < 0 || action >= actionMask.length) throw new IllegalArgumentException("policy action outside action space: " + action);
        if (!actionMask[action]) throw new IllegalArgumentException("policy selected masked action: " + action);
        return action;
    }

    public static boolean anyEligible(boolean[] mask) {
        for (boolean eligible : mask) if (eligible) return true;
        return false;
    }
}
