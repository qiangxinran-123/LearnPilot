import { describe, expect, it } from 'vitest';

import {
  adaptKnowledgeModelToFocus,
  canonicalNodeIndex,
  chooseDefaultFocusNodeId,
  directParentNodes,
} from '@/components/knowledge/knowledgeMapAdapter';
import type { KnowledgeEdge, KnowledgeModelResponse, KnowledgeNode } from '@/types/knowledge';

function node(id: number, name: string, courseId = 7): KnowledgeNode {
  return {
    id,
    course_id: courseId,
    name,
    normalized_name: name.toLowerCase(),
    description: `${name}说明`,
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
  relationType: KnowledgeEdge['relation_type'],
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
    nodes: [node(1, '主题'), node(2, '前置'), node(3, '当前'), node(4, '后续'), node(5, '孤立')],
    edges: [
      edge(11, 1, 3, 'contains'),
      edge(12, 2, 3, 'prerequisite'),
      edge(13, 3, 4, 'prerequisite'),
    ],
    ...overrides,
  };
}

describe('knowledgeMapAdapter', () => {
  it('separates CONTAINS parents from one-hop PREREQUISITE directions', () => {
    const input = model();
    const focus = adaptKnowledgeModelToFocus(input, 3);

    expect(focus.prerequisiteNodes.map((item) => item.id)).toEqual([2]);
    expect(focus.dependentNodes.map((item) => item.id)).toEqual([4]);
    expect(focus.prerequisiteEdges.map((item) => item.id)).toEqual([12]);
    expect(focus.dependentEdges.map((item) => item.id)).toEqual([13]);
    expect(directParentNodes(input, 3).map((item) => item.id)).toEqual([1]);
  });

  it('keeps isolated nodes focusable when no prerequisite relation exists', () => {
    const focus = adaptKnowledgeModelToFocus(model(), 5);

    expect(focus.focusNode?.id).toBe(5);
    expect(focus.prerequisiteNodes).toEqual([]);
    expect(focus.dependentNodes).toEqual([]);
  });

  it('filters cross-course nodes and malformed endpoints without hiding valid data', () => {
    const input = model({
      nodes: [...model().nodes, node(6, '其他课程', 8)],
      edges: [
        ...model().edges,
        edge(20, 6, 3, 'prerequisite'),
        edge(21, 3, 999, 'prerequisite'),
        edge(22, 3, 3, 'prerequisite'),
        edge(23, 2, 3, 'prerequisite', 8),
      ],
    });

    expect(canonicalNodeIndex(input).has(6)).toBe(false);
    expect(adaptKnowledgeModelToFocus(input, 3).ignoredEdgeIds).toEqual([20, 21, 22, 23]);
  });

  it('distinguishes same-name nodes by ID and returns every direct neighbor', () => {
    const nodes = [
      node(1, '焦点'),
      ...Array.from({ length: 8 }, (_, index) => node(index + 2, '重名')),
    ];
    const edges = nodes.slice(1).map((item, index) => edge(index + 1, item.id, 1, 'prerequisite'));
    const focus = adaptKnowledgeModelToFocus(model({ nodes, edges }), 1);

    expect(focus.prerequisiteNodes).toHaveLength(8);
    expect(new Set(focus.prerequisiteNodes.map((item) => item.id)).size).toBe(8);
  });

  it('chooses a deterministic real hierarchy root and rejects an unknown focus', () => {
    const input = model();
    expect(chooseDefaultFocusNodeId(input)).toBe(5);
    expect(adaptKnowledgeModelToFocus(input, 404).focusNode).toBeNull();
    expect(chooseDefaultFocusNodeId(model({ nodes: [], edges: [] }))).toBeNull();
  });
});
