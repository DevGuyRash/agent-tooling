/** The setup view (stub: being implemented). */
import type { RenderContext } from "../model";
import { empty, frame, FrameInput } from "./frame";

export function setup(input: FrameInput, ctx: RenderContext): string {
  void ctx;
  return frame("setup", input, empty("This view is not implemented yet."));
}
