/** Metric-aware views of any comparison (stubs; being implemented): scorecard, metric, difference, hierarchy. */
import type { RenderContext } from "../model";
import { empty, frame, FrameInput } from "./frame";

const stub = (kind: string) => (input: FrameInput, ctx: RenderContext): string => { void ctx; return frame(kind, input, empty("This view is not implemented yet.")); };
export const scorecard = stub("scorecard");
export const metric = stub("metric");
export const difference = stub("difference");
export const hierarchy = stub("hierarchy");
