function avArchitectureFootprint(iconSize, box) {
  if (!box || ![box.x, box.y, box.width, box.height].every(Number.isFinite)) {
    return { width: iconSize, height: iconSize };
  }
  const center = iconSize / 2;
  // The graph coordinates remain icon centers. Reserve the complete measured
  // service around that anchor, including wrapped or styled caption extents.
  return {
    width: 2 * Math.max(center, Math.abs(box.x - center), Math.abs(box.x + box.width - center)),
    height: 2 * Math.max(center, Math.abs(box.y - center), Math.abs(box.y + box.height - center)),
  };
}

function avArchitectureIconEndpoint(cy, id, direction) {
  const icon = cy.getElementById(id).data('iconSize');
  const [x, y] = { L: [0, .5], R: [1, .5], T: [.5, 0], B: [.5, 1] }[direction];
  return Number.isFinite(icon) && icon > 0
    ? `${x * icon}px ${y * icon}px`
    : `${x * 100}% ${y * 100}%`;
}

function avArchitectureGroupEndpoint(cy, id, direction, point, iconSize) {
  const parent = cy.getElementById(id).parent();
  if (!parent.length) return point;
  const box = parent.boundingBox(), offset = iconSize / 2;
  return direction === 'L' || direction === 'R'
    ? { x: (direction === 'L' ? box.x1 : box.x2) + offset, y: point.y }
    : { x: point.x, y: (direction === 'T' ? box.y1 : box.y2) + offset };
}

function avArchitectureGroupMidpoint(start, end, sourceDirection, targetDirection) {
  const sourceIsX = sourceDirection === 'L' || sourceDirection === 'R';
  const targetIsX = targetDirection === 'L' || targetDirection === 'R';
  // Rebase the native straight or one-elbow route with its moved attachments.
  if (sourceIsX !== targetIsX) return sourceIsX
    ? { x: end.x, y: start.y }
    : { x: start.x, y: end.y };
  return { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 };
}

function avArchitectureGroupRoute(cy, sourceId, targetId, sourceGroup, targetGroup, start, end, sourceDirection, targetDirection, iconSize) {
  if (!avArchitectureRouter) return null;
  const source = cy.getElementById(sourceId), target = cy.getElementById(targetId);
  const first = sourceGroup && source.parent().length ? source.parent() : source;
  const last = targetGroup && target.parent().length ? target.parent() : target;
  const ancestors = new Set([...first.ancestors(), ...last.ancestors()].map(node => node.id()));
  const offset = iconSize / 2, boxes = [];
  for (const node of cy.nodes()) {
    if (ancestors.has(node.id())) continue;
    if (node.id() === sourceId && !sourceGroup || node.id() === targetId && !targetGroup) {
      // Incident junctions attach at their center; their layout box reserves
      // spacing but does not represent an opaque icon around that endpoint.
      if (node.data('type') === 'junction') continue;
      const point = node.position(); boxes.push({ x: point.x, y: point.y, width: iconSize, height: iconSize });
    } else {
      const box = node.boundingBox(); boxes.push({ x: box.x1 + offset, y: box.y1 + offset, width: box.w, height: box.h });
    }
  }
  const obstacles = boxes.filter((box, i) => !boxes.some((other, j) => j !== i
    && other.x <= box.x && other.y <= box.y && other.x + other.width >= box.x + box.width && other.y + other.height >= box.y + box.height
    && (other.width * other.height > box.width * box.height || j < i)));
  return avArchitectureRouter({ start, end, sourceDirection, targetDirection, obstacles, clearance: Math.max(16, iconSize / 4) });
}

function oLi(services, cy, db) {
  const iconSize = db.getConfigField('iconSize');
  for (const service of services) {
    const footprint = avArchitectureFootprint(iconSize, service.avMeasuredBounds);
    cy.add({
      group: 'nodes',
      data: {
        type: 'service', id: service.id, icon: service.icon,
        label: service.title, parent: service.in, iconSize,
        width: footprint.width, height: footprint.height,
      },
      classes: 'node-service',
    });
  }
}
