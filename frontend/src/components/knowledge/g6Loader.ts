/**
 * Keeps the heavyweight graph runtime behind an explicit lazy boundary.
 * Domain and presentation components never need to import G6 types directly.
 */
export async function loadG6Graph(): Promise<unknown> {
  const { Graph } = await import('@antv/g6');
  return Graph;
}
