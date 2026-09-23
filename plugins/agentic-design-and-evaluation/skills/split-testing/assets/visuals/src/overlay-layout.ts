/** Shared geometry for owned floating controls. Coordinates are layout-viewport
 * CSS pixels; visualViewport offsets keep panels reachable when magnified or
 * when a software keyboard reduces the visible area. No global state. */
export interface OverlayBounds { left: number; top: number; right: number; bottom: number }
export interface OverlayAnchor { left: number; right: number; top: number; bottom: number }
const finite = (value: number | undefined, fallback: number): number => Number.isFinite(value) ? value! : fallback;
/** Position an already measured border box inside the visible rectangle. */
export function clampOverlayPosition(bounds: OverlayBounds, width: number, height: number, left: number, top: number): { left: number; top: number } {
  return {
    left: Math.max(bounds.left, Math.min(finite(left, bounds.left), bounds.right - Math.max(0, finite(width, 0)))),
    top: Math.max(bounds.top, Math.min(finite(top, bounds.top), bounds.bottom - Math.max(0, finite(height, 0)))),
  };
}
export function visibleViewport(view: Window | null, margin = 12): OverlayBounds {
  const viewport = view?.visualViewport;
  const x = finite(viewport?.offsetLeft, 0), y = finite(viewport?.offsetTop, 0);
  const width = Math.max(0, finite(viewport?.width, view?.innerWidth || 1024));
  const height = Math.max(0, finite(viewport?.height, view?.innerHeight || 720));
  const dx = Math.min(margin, width / 2), dy = Math.min(margin, height / 2);
  return { left: x + dx, right: x + width - dx, top: y + dy, bottom: y + height - dy };
}
export function anchoredPanel(anchor: OverlayAnchor, bounds: OverlayBounds, width: number, height: number, gap = 8): { left: number; top: number; width: number; maxHeight: number; side: 'up' | 'down' } {
  const availableWidth = Math.max(0, bounds.right - bounds.left), availableHeight = Math.max(0, bounds.bottom - bounds.top);
  const top = Math.max(bounds.top, Math.min(finite(anchor.top, bounds.top), bounds.bottom));
  const bottom = Math.max(bounds.top, Math.min(finite(anchor.bottom, top), bounds.bottom));
  const below = Math.max(0, bounds.bottom - bottom - gap), above = Math.max(0, top - bounds.top - gap);
  const up = below < Math.min(Math.max(0, height), 280) && above > below;
  const maxHeight = Math.min(availableHeight, up ? above : below);
  const fittedWidth = Math.min(availableWidth, Math.max(0, finite(width, availableWidth)));
  const fittedHeight = Math.min(maxHeight, Math.max(0, finite(height, maxHeight)));
  const position = clampOverlayPosition(bounds, fittedWidth, fittedHeight, finite(anchor.right, bounds.right) - fittedWidth, up ? top - gap - fittedHeight : bottom + gap);
  return {
    ...position,
    width: fittedWidth, maxHeight, side: up ? 'up' : 'down',
  };
}
