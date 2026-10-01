// This executable manifest must never be evaluated by the graph.
import Foundation
try! "unexpected execution".write(toFile: "SWIFTPM_RAN", atomically: true, encoding: .utf8)
