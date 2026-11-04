#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIM="$ROOT/simulator/PureEdgeSim"
(cd "$SIM" && mvn -q -DskipTests -Dmaven.javadoc.skip=true package)
CP="$SIM/target/classes:$(cat "$ROOT/scripts/java/classpath.txt")"
TMP="$(mktemp -d /tmp/dqn-foundation-check.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
mapfile -t SOURCES < <(find "$ROOT/experiment/src" -name '*.java' -print | sort)
javac -cp "$CP" -d "$TMP" "${SOURCES[@]}" "$ROOT/tests/java/DqnActionSpaceSelfTest.java" "$ROOT/tests/java/DqnImplementationSelfTest.java"
java -cp "$TMP:$CP" DqnActionSpaceSelfTest
java -cp "$TMP:$CP" DqnImplementationSelfTest
