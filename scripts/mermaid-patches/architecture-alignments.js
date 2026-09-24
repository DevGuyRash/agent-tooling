function fLi(db, spatialMaps, _groupAlignments, layoutHints = []) {
  // Source groups govern containment. Inferring cross-group alignments from a
  // grid coincidence can force an external node into a group's bounding box.
  // Keep the within-group grid and leave cross-group alignment to author hints.
  const horizontal = [], vertical = [];
  for (const spatialMap of spatialMaps) {
    const parents = new Map();
    for (const [id, [x, y]] of spatialMap) {
      const parent = db.getNode(id)?.in;
      let axes = parents.get(parent);
      if (!axes) { axes = { rows: new Map(), columns: new Map() }; parents.set(parent, axes); }
      for (const [axis, coordinate] of [[axes.rows, y], [axes.columns, x]]) {
        const members = axis.get(coordinate) || [];
        members.push(id); axis.set(coordinate, members);
      }
    }
    for (const axes of parents.values()) {
      horizontal.push(...[...axes.rows.values()].filter(members => members.length > 1));
      vertical.push(...[...axes.columns.values()].filter(members => members.length > 1));
    }
  }
  const declared = new Set(layoutHints.flatMap(hint => hint.members));
  const result = {
    horizontal: horizontal.filter(members => !members.some(id => declared.has(id))),
    vertical: vertical.filter(members => !members.some(id => declared.has(id))),
  };
  for (const hint of layoutHints) if (hint.members.length > 1) {
    result[hint.direction === 'row' ? 'horizontal' : 'vertical'].push([...hint.members]);
  }
  return result;
}
