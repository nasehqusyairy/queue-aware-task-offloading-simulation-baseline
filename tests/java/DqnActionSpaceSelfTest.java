import java.lang.reflect.Proxy;
import java.util.List;

import com.mechalikh.pureedgesim.datacentersmanager.ComputingNode;
import com.mechalikh.pureedgesim.experiment.DeterministicTestPolicy;
import com.mechalikh.pureedgesim.experiment.DqnActionSpace;
import com.mechalikh.pureedgesim.experiment.OffloadingObservation;

/** Small dependency-light executable checks for the action mapping contract. */
public final class DqnActionSpaceSelfTest {
    public static void main(String[] args) {
        List<ComputingNode> nodes = List.of(node(7), node(2), node(4));
        check(DqnActionSpace.stableIds(nodes).equals(List.of(2, 4, 7)), "stable EDC ID order");
        check(DqnActionSpace.stableIdsFromIds(List.of(7, 2, 4)).equals(List.of(2, 4, 7)), "stable action mapping");
        boolean[] mask = {false, true, true};
        check(DqnActionSpace.validateAction(1, mask) == 1, "eligible action accepted");
        expectInvalid(() -> DqnActionSpace.validateAction(0, mask), "masked action rejected");
        expectInvalid(() -> DqnActionSpace.validateAction(3, mask), "out-of-range action rejected");
        check(!DqnActionSpace.anyEligible(new boolean[] {false, false}), "no eligible destination detected");

        DeterministicTestPolicy policy = new DeterministicTestPolicy();
        OffloadingObservation first = observation(1);
        check(policy.selectAction(first, List.of(2, 4, 7), mask) == 1, "first enabled action selected");
        check(policy.selectAction(observation(2), List.of(2, 4, 7), mask) == 2, "deterministic action rotation");
        check(policy.selectAction(first, List.of(), new boolean[0]) == -1, "no-eligible policy returns sentinel");
        System.out.println("DqnActionSpaceSelfTest: 9 checks passed");
    }

    private static OffloadingObservation observation(int taskId) {
        return new OffloadingObservation(taskId, 1, 30_000, 160_000, 300, List.of());
    }

    private static ComputingNode node(int id) {
        return (ComputingNode) Proxy.newProxyInstance(ComputingNode.class.getClassLoader(),
                new Class<?>[] {ComputingNode.class}, (proxy, method, args) -> {
                    if (method.getName().equals("getId")) return id;
                    if (method.getReturnType() == boolean.class) return false;
                    if (method.getReturnType() == int.class) return 0;
                    if (method.getReturnType() == double.class) return 0.0;
                    return null;
                });
    }

    private static void expectInvalid(Runnable action, String label) {
        try { action.run(); throw new AssertionError(label + " did not throw"); }
        catch (IllegalArgumentException expected) { }
    }

    private static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }
}
