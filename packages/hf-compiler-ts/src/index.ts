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
  if (!Number.isFinite(plan.duration_s) || plan.duration_s <= 0 || !Number.isFinite(plan.fps) || plan.fps <= 0) {
    throw new Error("EditPlan duration_s and fps must be finite and positive.");
  }
  if (!Number.isFinite(plan.width) || plan.width < 360 || !Number.isFinite(plan.height) || plan.height < 360) {
    throw new Error("EditPlan dimensions must be finite and at least 360x360.");
  }
}
