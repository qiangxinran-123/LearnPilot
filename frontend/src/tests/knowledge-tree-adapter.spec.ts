import { describe, expect, it } from 'vitest';

import { adaptKnowledgeModelToTree, searchKnowledgeTree } from '@/components/knowledge/treeAdapter';
import type { KnowledgeEdge, KnowledgeModelResponse, KnowledgeNode } from '@/types/knowledge';

function node(id: number, name: string, courseId = 7): KnowledgeNode {
  return {
    id,
    course_id: courseId,
    name,
    normalized_name: name.toLowerCase(),
    description: '',
    importance: 'medium',
    difficulty: 'basic',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

function edge(
  id: number,
  sourceNodeId: number,
  targetNodeId: number,
  relationType: KnowledgeEdge['relation_type'] = 'contains',
  courseId = 7,
): KnowledgeEdge {
  return {
    id,
    course_id: courseId,
    source_node_id: sourceNodeId,
    target_node_id: targetNodeId,
    relation_type: relationType,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

function model(overrides: Partial<KnowledgeModelResponse> = {}): KnowledgeModelResponse {
  return {
    course_id: 7,
    nodes: [node(1, '代数'), node(2, '向量'), node(3, '微积分'), node(4, '导数'), node(5, '矩阵')],
    edges: [edge(11, 1, 2), edge(12, 3, 4), edge(13, 2, 5, 'prerequisite')],
    ...overrides,
  };
}

describe('adaptKnowledgeModelToTree', () => {
  it('builds multiple real roots and uses only CONTAINS for parent-child relationships', () => {
    const tree = adaptKnowledgeModelToTree(model());

    expect(tree.roots.map((root) => root.id)).toEqual([1, 5, 3]);
    expect(tree.nodeById.size).toBe(5);
    expect(tree.nodeById.get(1)?.children.map((child) => child.id)).toEqual([2]);
    expect(tree.nodeById.get(3)?.children.map((child) => child.id)).toEqual([4]);
    expect(tree.parentIdByNodeId.get(5)).toBeUndefined();
    expect(tree.ignoredEdgeIds).toEqual([]);
  });

  it('keeps disconnected nodes visible when no hierarchy relationships exist', () => {
    const tree = adaptKnowledgeModelToTree(model({ edges: [] }));

    expect(tree.roots).toHaveLength(5);
    expect(tree.nodeById.size).toBe(5);
    expect(tree.roots.every((root) => root.children.length === 0)).toBe(true);
  });

  it('drops stale endpoints, self-edges and cross-course data without losing valid nodes', () => {
    const tree = adaptKnowledgeModelToTree(
      model({
        nodes: [...model().nodes, node(6, '另一门课', 8)],
        edges: [
          ...model().edges,
          edge(20, 1, 999),
          edge(21, 1, 1),
          edge(22, 1, 6),
          edge(23, 1, 5, 'contains', 8),
        ],
      }),
    );

    expect(tree.nodeById.has(6)).toBe(false);
    expect(tree.nodeById.size).toBe(5);
    expect(tree.ignoredEdgeIds).toEqual([20, 21, 22, 23]);
  });

  it('rejects a second parent or a cycle deterministically', () => {
    const input = model({
      edges: [edge(11, 1, 2), edge(12, 2, 3), edge(13, 4, 3), edge(14, 3, 1)],
    });
    const tree = adaptKnowledgeModelToTree(input);

    expect(tree.ignoredEdgeIds).toEqual([13, 14]);
    expect(tree.parentIdByNodeId.get(3)).toBe(2);
    expect(tree.roots.map((root) => root.id)).toContain(1);
    expect(tree.nodeById.size).toBe(5);
    expect(
      adaptKnowledgeModelToTree({ ...input, edges: [...input.edges].reverse() }).ignoredEdgeIds,
    ).toEqual(tree.ignoredEdgeIds);
  });

  it('sorts roots and siblings by canonical name with ID tie-breaks, regardless of API order', () => {
    const input = model({
      nodes: [node(6, 'Beta'), node(2, 'alpha'), node(5, 'Alpha'), node(1, 'Root')],
      edges: [edge(1, 1, 6), edge(2, 1, 5), edge(3, 1, 2)],
    });
    const tree = adaptKnowledgeModelToTree(input);

    expect(tree.nodeById.get(1)?.children.map((child) => child.id)).toEqual([2, 5, 6]);
    expect(
      adaptKnowledgeModelToTree({ ...input, nodes: [...input.nodes].reverse() }).roots.map(
        (root) => root.id,
      ),
    ).toEqual(tree.roots.map((root) => root.id));
  });
});

describe('searchKnowledgeTree', () => {
  it('shows all nodes for an empty query and no forced expansion', () => {
    const tree = adaptKnowledgeModelToTree(model());
    const result = searchKnowledgeTree(tree.roots, '  ');

    expect([...result.visibleIds].sort()).toEqual([1, 2, 3, 4, 5]);
    expect(result.matchedIds.size).toBe(0);
    expect(result.expandedIds.size).toBe(0);
  });

  it('matches a child by name and exposes its parent path for positioning', () => {
    const tree = adaptKnowledgeModelToTree(model());
    const result = searchKnowledgeTree(tree.roots, '  向量  ');

    expect([...result.matchedIds]).toEqual([2]);
    expect([...result.visibleIds].sort()).toEqual([1, 2]);
    expect([...result.expandedIds]).toEqual([1, 2]);
  });

  it('keeps the full subtree visible when a parent topic matches', () => {
    const tree = adaptKnowledgeModelToTree(model());
    const result = searchKnowledgeTree(tree.roots, '代数');

    expect([...result.matchedIds]).toEqual([1]);
    expect([...result.visibleIds].sort()).toEqual([1, 2]);
    expect([...result.expandedIds]).toEqual([1]);
  });

  it('returns an empty visible set when no canonical name matches', () => {
    const tree = adaptKnowledgeModelToTree(model());
    const result = searchKnowledgeTree(tree.roots, '不存在的概念');

    expect(result.visibleIds.size).toBe(0);
    expect(result.matchedIds.size).toBe(0);
  });
});
