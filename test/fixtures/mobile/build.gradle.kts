// This Gradle script must never be evaluated by the graph.
java.io.File("GRADLE_RAN").writeText("unexpected execution")
error("Graph must not evaluate Gradle")
