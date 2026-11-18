export * from "./contracts.js";
export * from "./compiler.js";
export * from "./lint.js";
export * from "./distributed.js";

import type { EditPlan } from "./contracts.js";

/**
 * Structural guard verifying an EditPlan before HyperFrames composition compilation.
 */
export function assertPlanStructure(plan: EditPlan): void {
  if (plan.schema_version !== "1.0") {
    throw new Error(`Unsupported EditPlan schema_version: ${plan.schema_version}`);
  }
  if (plan.duration_s <= 0 || plan.fps <= 0) {
    throw new Error("EditPlan duration_s and fps must be positive.");
  }
  if (plan.width < 360 || plan.height < 360) {
    throw new Error("EditPlan dimensions must be at least 360x360.");
  }
}
