export type GraphPosition = { x: number; y: number };

type PositionedItem = { id: string; x: number; y: number };

export function routeGraphEdge(
  from: { x: number; y: number; width: number; height: number },
  to: { x: number; y: number; width: number; height: number },
): { path: string; direction: "horizontal" | "vertical" } {
  const fromCenter = { x: from.x + from.width / 2, y: from.y + from.height / 2 };
  const toCenter = { x: to.x + to.width / 2, y: to.y + to.height / 2 };
  const horizontal = Math.abs(toCenter.x - fromCenter.x) >= Math.abs(toCenter.y - fromCenter.y);

  if (horizontal) {
    const forward = toCenter.x >= fromCenter.x;
    const start = { x: forward ? from.x + from.width : from.x, y: fromCenter.y };
    const end = { x: forward ? to.x : to.x + to.width, y: toCenter.y };
    const curve = Math.max(24, Math.abs(end.x - start.x) * 0.48);
    const bend = forward ? curve : -curve;
    return {
      path: `M ${start.x} ${start.y} C ${start.x + bend} ${start.y}, ${end.x - bend} ${end.y}, ${end.x} ${end.y}`,
      direction: "horizontal",
    };
  }

  const forward = toCenter.y >= fromCenter.y;
  const start = { x: fromCenter.x, y: forward ? from.y + from.height : from.y };
  const end = { x: toCenter.x, y: forward ? to.y : to.y + to.height };
  const curve = Math.max(24, Math.abs(end.y - start.y) * 0.48);
  const bend = forward ? curve : -curve;
  return {
    path: `M ${start.x} ${start.y} C ${start.x} ${start.y + bend}, ${end.x} ${end.y - bend}, ${end.x} ${end.y}`,
    direction: "vertical",
  };
}

export function resolveGraphPosition<T extends PositionedItem>(
  item: T | undefined,
  localPositions: Record<string, GraphPosition>,
): GraphPosition {
  if (!item) return { x: 0, y: 0 };
  return localPositions[item.id] ?? { x: item.x, y: item.y };
}

export function fitGraphToViewport(
  items: Array<{ x: number; y: number; width: number; height: number }>,
  viewport: { width: number; height: number },
  padding = 40,
): { zoom: number; pan: GraphPosition } | null {
  if (items.length === 0 || viewport.width <= 0 || viewport.height <= 0) return null;

  const minX = Math.min(...items.map((item) => item.x));
  const minY = Math.min(...items.map((item) => item.y));
  const maxX = Math.max(...items.map((item) => item.x + item.width));
  const maxY = Math.max(...items.map((item) => item.y + item.height));
  const graphWidth = maxX - minX;
  const graphHeight = maxY - minY;
  if (graphWidth <= 0 || graphHeight <= 0) return null;

  const zoom = Math.min(
    1.2,
    (viewport.width - padding * 2) / graphWidth,
    (viewport.height - padding * 2) / graphHeight,
  );
  if (!Number.isFinite(zoom) || zoom <= 0) return null;

  return {
    zoom: Number(zoom.toPrecision(6)),
    pan: {
      x: Math.round((viewport.width - graphWidth * zoom) / 2 - minX * zoom),
      y: Math.round((viewport.height - graphHeight * zoom) / 2 - minY * zoom),
    },
  };
}

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
