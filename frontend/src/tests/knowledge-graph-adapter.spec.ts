import { describe, expect, it } from 'vitest';

import { adaptKnowledgeModelToGraph } from '@/components/knowledge/graphAdapter';
import type { KnowledgeModelResponse } from '@/types/knowledge';

function model(overrides: Partial<KnowledgeModelResponse> = {}): KnowledgeModelResponse {
  return {
    course_id: 7,
    nodes: [
      {
        id: 1,
        course_id: 7,
        name: '向量',
        normalized_name: '向量',
        description: '向量基础。',
        importance: 'high',
        difficulty: 'basic',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 2,
        course_id: 7,
        name: '线性变换',
        normalized_name: '线性变换',
        description: '线性变换基础。',
        importance: 'high',
        difficulty: 'intermediate',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 3,
        course_id: 7,
        name: '矩阵',
        normalized_name: '矩阵',
        description: '矩阵基础。',
        importance: 'medium',
        difficulty: 'basic',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 4,
        course_id: 7,
        name: '特征值',
        normalized_name: '特征值',
        description: '特征值基础。',
        importance: 'high',
        difficulty: 'advanced',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ],
    edges: [
      {
        id: 11,
        course_id: 7,
        source_node_id: 1,
        target_node_id: 2,
        relation_type: 'contains',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 12,
        course_id: 7,
        source_node_id: 3,
        target_node_id: 4,
        relation_type: 'contains',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 13,
        course_id: 7,
        source_node_id: 1,
        target_node_id: 4,
        relation_type: 'prerequisite',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ],
    ...overrides,
  };
}

describe('adaptKnowledgeModelToGraph', () => {
  it('keeps multiple hierarchy roots and never creates a synthetic domain node', () => {
    const adapted = adaptKnowledgeModelToGraph(model());

    expect(adapted.rootNodeIds).toEqual([1, 3]);
    expect(adapted.nodeIds).toEqual([
      'knowledge-node-1',
      'knowledge-node-2',
      'knowledge-node-3',
      'knowledge-node-4',
    ]);
    expect(adapted.nodeIds.some((id) => id.includes('virtual'))).toBe(false);
  });

  it('renders disconnected nodes without requiring edges', () => {
    const adapted = adaptKnowledgeModelToGraph(model({ edges: [] }));

    expect(adapted.data.nodes).toHaveLength(4);
    expect(adapted.data.edges).toEqual([]);
    expect(adapted.rootNodeIds).toEqual([1, 2, 3, 4]);
  });

  it('packs disconnected roots into deterministic bounded rows for readable fit-to-view', () => {
    const adapted = adaptKnowledgeModelToGraph(model({ edges: [] }));
    const positions = new Map(
      adapted.data.nodes.map((node) => [node.id, { x: Number(node.style.x), y: Number(node.style.y) }]),
    );

    expect(positions.get('knowledge-node-1')?.y).toBe(positions.get('knowledge-node-3')?.y);
    expect(positions.get('knowledge-node-4')?.y).toBeGreaterThan(
      positions.get('knowledge-node-1')?.y ?? 0,
    );
    expect(positions.get('knowledge-node-1')?.x).not.toBe(positions.get('knowledge-node-2')?.x);
  });

  it('filters relation overlays locally without changing the hierarchy nodes', () => {
    const allRelations = adaptKnowledgeModelToGraph(model());
    const onlyContains = adaptKnowledgeModelToGraph(model(), {
      contains: true,
      prerequisite: false,
    });
    const onlyPrerequisites = adaptKnowledgeModelToGraph(model(), {
      contains: false,
      prerequisite: true,
    });

    expect(allRelations.edgeIds).toHaveLength(3);
    expect(onlyContains.edgeIds).toEqual(['knowledge-edge-11', 'knowledge-edge-12']);
    expect(onlyPrerequisites.edgeIds).toEqual(['knowledge-edge-13']);
    expect(onlyPrerequisites.nodeIds).toEqual(allRelations.nodeIds);
  });

  it('drops edges with an unknown endpoint or relation type rather than corrupting the graph', () => {
    const invalidModel = model({
      edges: [
        ...model().edges,
        {
          id: 99,
          course_id: 7,
          source_node_id: 1,
          target_node_id: 404,
          relation_type: 'contains',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
        {
          id: 100,
          course_id: 7,
          source_node_id: 2,
          target_node_id: 3,
          relation_type: 'unknown',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        } as unknown as KnowledgeModelResponse['edges'][number],
      ],
    });

    expect(adaptKnowledgeModelToGraph(invalidModel).edgeIds).toEqual([
      'knowledge-edge-11',
      'knowledge-edge-12',
      'knowledge-edge-13',
    ]);
  });

  it('adapts a test-only course-size graph without random layout or hidden nodes', () => {
    const nodes = Array.from({ length: 50 }, (_, index) => ({
      id: index + 1,
      course_id: 7,
      name: `知识点 ${index + 1}`,
      normalized_name: `知识点 ${index + 1}`,
      description: '',
      importance: 'medium' as const,
      difficulty: 'intermediate' as const,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }));
    const contains = Array.from({ length: 49 }, (_, index) => ({
      id: index + 1,
      course_id: 7,
      source_node_id: Math.max(1, Math.floor((index + 2) / 2)),
      target_node_id: index + 2,
      relation_type: 'contains' as const,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }));
    const prerequisites = Array.from({ length: 31 }, (_, index) => ({
      id: index + 50,
      course_id: 7,
      source_node_id: 1,
      target_node_id: index + 20,
      relation_type: 'prerequisite' as const,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }));

    const adapted = adaptKnowledgeModelToGraph({ course_id: 7, nodes, edges: [...contains, ...prerequisites] });

    expect(adapted.data.nodes).toHaveLength(50);
    expect(adapted.data.edges).toHaveLength(80);
    expect(adapted.rootNodeIds).toEqual([1]);
  });
});
