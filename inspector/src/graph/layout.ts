export type GraphPosition = { x: number; y: number };

type PositionedItem = { id: string; x: number; y: number };

export function preserveGraphPositions<
  N extends PositionedItem,
  G extends PositionedItem,
>(
  current: { nodes: N[]; groups: G[] },
  next: { nodes: N[]; groups: G[] },
  localPositions: Record<string, GraphPosition>,
): { nodes: N[]; groups: G[] } {
  const positions = new Map(
    [...current.nodes, ...current.groups].map((item) => [item.id, { x: item.x, y: item.y }]),
  );
  Object.entries(localPositions).forEach(([id, position]) => positions.set(id, position));
  return {
    nodes: next.nodes.map((item) => ({ ...item, ...(positions.get(item.id) ?? {}) })),
    groups: next.groups.map((item) => ({ ...item, ...(positions.get(item.id) ?? {}) })),
  };
}

export function translatePositions(
  positions: Record<string, GraphPosition>,
  ids: string[],
  delta: GraphPosition,
): Record<string, GraphPosition> {
  return Object.fromEntries(
    ids
      .filter((id) => positions[id] !== undefined)
      .map((id) => [
        id,
        {
          x: positions[id].x + delta.x,
          y: positions[id].y + delta.y,
        },
      ]),
  );
}
