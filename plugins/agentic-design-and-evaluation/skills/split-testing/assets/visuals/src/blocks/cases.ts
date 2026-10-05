/** The cases view (stub: being implemented). */
import type { RenderContext } from "../model";
import { empty, frame, FrameInput } from "./frame";

export function cases(input: FrameInput, ctx: RenderContext): string {
  void ctx;
  return frame("cases", input, empty("This view is not implemented yet."));
}
