export type GraphPosition = { x: number; y: number };

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
