/** The contrast view (stub: being implemented). */
import type { RenderContext } from "../model";
import { empty, frame, FrameInput } from "./frame";

export function contrast(input: FrameInput, ctx: RenderContext): string {
  void ctx;
  return frame("contrast", input, empty("This view is not implemented yet."));
}
