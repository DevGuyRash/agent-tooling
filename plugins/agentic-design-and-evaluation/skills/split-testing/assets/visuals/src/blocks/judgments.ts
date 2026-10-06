/** Views of what was compared and how it was judged (stubs; being implemented): alternatives, preferences, decision matrix, observations. */
import type { RenderContext } from "../model";
import { empty, frame, FrameInput } from "./frame";

const stub = (kind: string) => (input: FrameInput, ctx: RenderContext): string => { void ctx; return frame(kind, input, empty("This view is not implemented yet.")); };
export const alternatives = stub("alternatives");
export const preferences = stub("preferences");
export const decisionMatrix = stub("decision-matrix");
export const observations = stub("observations");
