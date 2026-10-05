/** The failures view (stub: being implemented). */
import type { RenderContext } from "../model";
import { empty, frame, FrameInput } from "./frame";

export function failures(input: FrameInput, ctx: RenderContext): string {
  void ctx;
  return frame("failures", input, empty("This view is not implemented yet."));
}
