import type { KnowledgeEdge, KnowledgeModelResponse, KnowledgeNode } from '@/types/knowledge';

export interface KnowledgeTreeNode {
  id: number;
  label: string;
  node: KnowledgeNode;
  children: KnowledgeTreeNode[];
}

export interface KnowledgeTreeData {
  roots: KnowledgeTreeNode[];
  nodeById: ReadonlyMap<number, KnowledgeTreeNode>;
  parentIdByNodeId: ReadonlyMap<number, number>;
  ignoredEdgeIds: number[];
}

export interface KnowledgeTreeSearchResult {
  matchedIds: ReadonlySet<number>;
  visibleIds: ReadonlySet<number>;
  expandedIds: ReadonlySet<number>;
}

const nameCollator = new Intl.Collator('zh-CN', { numeric: true, sensitivity: 'base' });

function compareNodes(left: KnowledgeNode, right: KnowledgeNode): number {
  return nameCollator.compare(left.name, right.name) || left.id - right.id;
}

function createsCycle(
  sourceNodeId: number,
  targetNodeId: number,
  parentIdByNodeId: ReadonlyMap<number, number>,
): boolean {
  let ancestorId: number | undefined = sourceNodeId;
  while (ancestorId !== undefined) {
    if (ancestorId === targetNodeId) {
      return true;
    }
    ancestorId = parentIdByNodeId.get(ancestorId);
  }
  return false;
}

/**
 * Convert canonical nodes and real CONTAINS edges into a forest. PREREQUISITE
 * edges never imply a parent-child relationship. Backend constraints enforce a
 * forest; these guards keep stale or malformed responses from hiding nodes.
 */
export function adaptKnowledgeModelToTree(model: KnowledgeModelResponse): KnowledgeTreeData {
  const nodes = [...model.nodes]
    .filter((node) => node.course_id === model.course_id)
    .sort(compareNodes);
  const nodeByDomainId = new Map<number, KnowledgeNode>();
  for (const node of nodes) {
    if (!nodeByDomainId.has(node.id)) {
      nodeByDomainId.set(node.id, node);
    }
  }

  const parentIdByNodeId = new Map<number, number>();
  const childIdsByNodeId = new Map<number, number[]>();
  const ignoredEdgeIds: number[] = [];
  for (const nodeId of nodeByDomainId.keys()) {
    childIdsByNodeId.set(nodeId, []);
  }

  const containsEdges = model.edges
    .filter((edge): edge is KnowledgeEdge => edge.relation_type === 'contains')
    .sort((left, right) => left.id - right.id);

  for (const edge of containsEdges) {
    if (
      edge.course_id !== model.course_id ||
      edge.source_node_id === edge.target_node_id ||
      !nodeByDomainId.has(edge.source_node_id) ||
      !nodeByDomainId.has(edge.target_node_id) ||
      parentIdByNodeId.has(edge.target_node_id) ||
      createsCycle(edge.source_node_id, edge.target_node_id, parentIdByNodeId)
    ) {
      ignoredEdgeIds.push(edge.id);
      continue;
    }
    parentIdByNodeId.set(edge.target_node_id, edge.source_node_id);
    childIdsByNodeId.get(edge.source_node_id)?.push(edge.target_node_id);
  }

  for (const childIds of childIdsByNodeId.values()) {
    childIds.sort((leftId, rightId) =>
      compareNodes(nodeByDomainId.get(leftId)!, nodeByDomainId.get(rightId)!),
    );
  }

  const nodeById = new Map<number, KnowledgeTreeNode>();
  function buildNode(nodeId: number): KnowledgeTreeNode {
    const node = nodeByDomainId.get(nodeId)!;
    const treeNode: KnowledgeTreeNode = {
      id: nodeId,
      label: node.name,
      node,
      children: (childIdsByNodeId.get(nodeId) ?? []).map(buildNode),
    };
    nodeById.set(nodeId, treeNode);
    return treeNode;
  }

  const roots = [...nodeByDomainId.values()]
    .filter((node) => !parentIdByNodeId.has(node.id))
    .map((node) => buildNode(node.id));

  return { roots, nodeById, parentIdByNodeId, ignoredEdgeIds };
}

/**
 * Search by canonical name only. Matching descendants, their ancestors and
 * the full subtree of a matched topic remain visible in the filtered tree.
 */
export function searchKnowledgeTree(
  roots: readonly KnowledgeTreeNode[],
  query: string,
): KnowledgeTreeSearchResult {
  const normalizedQuery = query.trim().replace(/\s+/g, ' ').toLowerCase();
  const matchedIds = new Set<number>();
  const visibleIds = new Set<number>();
  const expandedIds = new Set<number>();

  function showSubtree(treeNode: KnowledgeTreeNode): void {
    visibleIds.add(treeNode.id);
    treeNode.children.forEach(showSubtree);
  }

  function search(treeNode: KnowledgeTreeNode, ancestors: readonly number[]): void {
    const searchText = `${treeNode.node.name} ${treeNode.node.normalized_name}`.toLowerCase();
    if (normalizedQuery && searchText.includes(normalizedQuery)) {
      matchedIds.add(treeNode.id);
      ancestors.forEach((id) => {
        visibleIds.add(id);
        expandedIds.add(id);
      });
      showSubtree(treeNode);
      expandedIds.add(treeNode.id);
    } else if (!normalizedQuery) {
      visibleIds.add(treeNode.id);
    }
    treeNode.children.forEach((child) => search(child, [...ancestors, treeNode.id]));
  }

  roots.forEach((root) => search(root, []));
  return { matchedIds, visibleIds, expandedIds };
}
