import type { KnowledgeEdge, KnowledgeModelResponse, KnowledgeNode } from '@/types/knowledge';

export interface KnowledgeFocusData {
  focusNode: KnowledgeNode | null;
  prerequisiteNodes: KnowledgeNode[];
  dependentNodes: KnowledgeNode[];
  prerequisiteEdges: KnowledgeEdge[];
  dependentEdges: KnowledgeEdge[];
  ignoredEdgeIds: number[];
}

const nameCollator = new Intl.Collator('zh-CN', { numeric: true, sensitivity: 'base' });

function compareNodes(left: KnowledgeNode, right: KnowledgeNode): number {
  return nameCollator.compare(left.name, right.name) || left.id - right.id;
}

export function canonicalNodeIndex(
  model: KnowledgeModelResponse,
): ReadonlyMap<number, KnowledgeNode> {
  const result = new Map<number, KnowledgeNode>();
  for (const node of model.nodes) {
    if (node.course_id === model.course_id && !result.has(node.id)) result.set(node.id, node);
  }
  return result;
}

/**
 * A prerequisite edge is directional: source is learned before target. Only
 * valid, direct, same-course edges touching the focus node are returned.
 */
export function adaptKnowledgeModelToFocus(
  model: KnowledgeModelResponse,
  focusNodeId: number | null,
): KnowledgeFocusData {
  const nodeById = canonicalNodeIndex(model);
  const focusNode = focusNodeId === null ? null : (nodeById.get(focusNodeId) ?? null);
  const prerequisiteIds = new Set<number>();
  const dependentIds = new Set<number>();
  const prerequisiteEdges: KnowledgeEdge[] = [];
  const dependentEdges: KnowledgeEdge[] = [];
  const ignoredEdgeIds: number[] = [];

  for (const edge of [...model.edges].sort((left, right) => left.id - right.id)) {
    if (edge.relation_type !== 'prerequisite') continue;
    if (
      edge.course_id !== model.course_id ||
      edge.source_node_id === edge.target_node_id ||
      !nodeById.has(edge.source_node_id) ||
      !nodeById.has(edge.target_node_id)
    ) {
      ignoredEdgeIds.push(edge.id);
      continue;
    }
    if (!focusNode) continue;
    if (edge.target_node_id === focusNode.id) {
      prerequisiteIds.add(edge.source_node_id);
      prerequisiteEdges.push(edge);
    }
    if (edge.source_node_id === focusNode.id) {
      dependentIds.add(edge.target_node_id);
      dependentEdges.push(edge);
    }
  }

  return {
    focusNode,
    prerequisiteNodes: [...prerequisiteIds].map((id) => nodeById.get(id)!).sort(compareNodes),
    dependentNodes: [...dependentIds].map((id) => nodeById.get(id)!).sort(compareNodes),
    prerequisiteEdges,
    dependentEdges,
    ignoredEdgeIds,
  };
}

export function chooseDefaultFocusNodeId(model: KnowledgeModelResponse): number | null {
  const nodes = [...canonicalNodeIndex(model).values()].sort(compareNodes);
  if (!nodes.length) return null;

  const childIds = new Set(
    model.edges
      .filter(
        (edge) =>
          edge.course_id === model.course_id &&
          edge.relation_type === 'contains' &&
          edge.source_node_id !== edge.target_node_id,
      )
      .map((edge) => edge.target_node_id),
  );
  return nodes.find((node) => !childIds.has(node.id))?.id ?? nodes[0]!.id;
}

export function directParentNodes(model: KnowledgeModelResponse, nodeId: number): KnowledgeNode[] {
  const nodeById = canonicalNodeIndex(model);
  const parentIds = new Set<number>();
  for (const edge of model.edges) {
    if (
      edge.course_id === model.course_id &&
      edge.relation_type === 'contains' &&
      edge.target_node_id === nodeId &&
      edge.source_node_id !== nodeId &&
      nodeById.has(edge.source_node_id)
    ) {
      parentIds.add(edge.source_node_id);
    }
  }
  return [...parentIds].map((id) => nodeById.get(id)!).sort(compareNodes);
}
