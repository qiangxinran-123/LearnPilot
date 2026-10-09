import type {
  KnowledgeEdge,
  KnowledgeModelResponse,
  KnowledgeRelationType,
} from '@/types/knowledge';

export interface KnowledgeRelationVisibility {
  contains: boolean;
  prerequisite: boolean;
}

export interface KnowledgeGraphData {
  data: KnowledgeGraphRenderData;
  nodeIds: string[];
  edgeIds: string[];
  nodeIdByGraphId: ReadonlyMap<string, number>;
  edgeIdByGraphId: ReadonlyMap<string, number>;
  rootNodeIds: number[];
}

/**
 * A minimal, library-neutral rendering shape. Keeping it local prevents G6's
 * internal rendering types from leaking into the course domain or API layer.
 */
export interface KnowledgeGraphRenderData {
  nodes: KnowledgeGraphRenderNode[];
  edges: KnowledgeGraphRenderEdge[];
}

export interface KnowledgeGraphRenderNode {
  id: string;
  type: 'rect';
  data: Record<string, unknown>;
  style: Record<string, unknown>;
}

export interface KnowledgeGraphRenderEdge {
  id: string;
  type: 'line';
  source: string;
  target: string;
  data: Record<string, unknown>;
  style: Record<string, unknown>;
}

const DEFAULT_VISIBILITY: KnowledgeRelationVisibility = {
  contains: true,
  prerequisite: true,
};

const NODE_WIDTH = 176;
const NODE_HEIGHT = 48;
const HORIZONTAL_GAP = 204;
const VERTICAL_GAP = 108;
const ROOT_COLUMNS = 3;
const COMPONENT_GAP_X = 72;
const COMPONENT_GAP_Y = 72;

function graphNodeId(nodeId: number): string {
  return `knowledge-node-${nodeId}`;
}

function graphEdgeId(edgeId: number): string {
  return `knowledge-edge-${edgeId}`;
}

function sortById<T extends { id: number }>(items: readonly T[]): T[] {
  return [...items].sort((left, right) => left.id - right.id);
}

function isKnownRelation(value: unknown): value is KnowledgeRelationType {
  return value === 'contains' || value === 'prerequisite';
}

function validEdges(model: KnowledgeModelResponse): KnowledgeEdge[] {
  const nodeIds = new Set(model.nodes.map((node) => node.id));
  return sortById(model.edges).filter(
    (edge) =>
      isKnownRelation(edge.relation_type) &&
      edge.source_node_id !== edge.target_node_id &&
      nodeIds.has(edge.source_node_id) &&
      nodeIds.has(edge.target_node_id),
  );
}

interface NodePosition {
  x: number;
  y: number;
}

interface ForestLayout {
  positions: ReadonlyMap<number, NodePosition>;
  rootNodeIds: number[];
}

interface ForestComponent {
  positions: ReadonlyMap<number, NodePosition>;
  width: number;
  height: number;
}

/**
 * The domain model already guarantees a CONTAINS forest for generated edges. The
 * defensive first-parent rule below also keeps manually-added malformed data
 * readable without letting it change prerequisite semantics or create a fake root.
 */
function buildForestLayout(model: KnowledgeModelResponse, containsEdges: KnowledgeEdge[]): ForestLayout {
  const nodeIds = sortById(model.nodes).map((node) => node.id);
  const childrenById = new Map<number, number[]>();
  const parentByChild = new Map<number, number>();

  for (const nodeId of nodeIds) {
    childrenById.set(nodeId, []);
  }

  for (const edge of containsEdges) {
    if (parentByChild.has(edge.target_node_id)) {
      continue;
    }
    parentByChild.set(edge.target_node_id, edge.source_node_id);
    childrenById.get(edge.source_node_id)?.push(edge.target_node_id);
  }

  for (const children of childrenById.values()) {
    children.sort((left, right) => left - right);
  }

  const rootNodeIds = nodeIds.filter((nodeId) => !parentByChild.has(nodeId));
  const positions = new Map<number, NodePosition>();
  const visited = new Set<number>();

  const buildComponent = (rootNodeId: number): ForestComponent => {
    const componentPositions = new Map<number, NodePosition>();
    let leafIndex = 0;
    let maxDepth = 0;

    const place = (nodeId: number, depth: number, ancestry: ReadonlySet<number>): number => {
      if (visited.has(nodeId) || ancestry.has(nodeId)) {
        return leafIndex * HORIZONTAL_GAP;
      }

      visited.add(nodeId);
      maxDepth = Math.max(maxDepth, depth);
      const nextAncestry = new Set(ancestry);
      nextAncestry.add(nodeId);
      const children = (childrenById.get(nodeId) ?? []).filter(
        (childId) => !nextAncestry.has(childId) && !visited.has(childId),
      );
      const childPositions = children.map((childId) => place(childId, depth + 1, nextAncestry));
      const x =
        childPositions.length > 0
          ? childPositions.reduce((sum, value) => sum + value, 0) / childPositions.length
          : leafIndex++ * HORIZONTAL_GAP;

      componentPositions.set(nodeId, { x, y: depth * VERTICAL_GAP });
      return x;
    };

    place(rootNodeId, 0, new Set());
    const xPositions = [...componentPositions.values()].map((position) => position.x);
    const minX = Math.min(...xPositions);
    const maxX = Math.max(...xPositions);

    return {
      positions: componentPositions,
      width: Math.max(NODE_WIDTH, maxX - minX + NODE_WIDTH),
      height: maxDepth * VERTICAL_GAP + NODE_HEIGHT,
    };
  };

  const components: ForestComponent[] = [];
  for (const rootNodeId of rootNodeIds) {
    components.push(buildComponent(rootNodeId));
  }

  // A malformed manual cycle has no root. Place it as a disconnected component
  // while retaining every real backend node and without inventing a domain root.
  for (const nodeId of nodeIds) {
    if (!visited.has(nodeId)) {
      components.push(buildComponent(nodeId));
    }
  }

  const widestComponent = Math.max(NODE_WIDTH, ...components.map((component) => component.width));
  const tallestComponent = Math.max(NODE_HEIGHT, ...components.map((component) => component.height));

  // A bounded grid keeps many valid forest roots legible. It is a layout choice,
  // not a virtual course-domain node: every visual node remains a real concept.
  components.forEach((component, index) => {
    const column = index % ROOT_COLUMNS;
    const row = Math.floor(index / ROOT_COLUMNS);
    const originX = column * (widestComponent + COMPONENT_GAP_X) + (widestComponent - component.width) / 2;
    const originY = row * (tallestComponent + COMPONENT_GAP_Y);

    for (const [nodeId, position] of component.positions) {
      positions.set(nodeId, { x: originX + position.x, y: originY + position.y });
    }
  });

  return { positions, rootNodeIds };
}

function edgeStyle(relationType: KnowledgeRelationType): Record<string, unknown> {
  if (relationType === 'prerequisite') {
    return {
      stroke: '#5874d1',
      lineWidth: 1.7,
      lineDash: [7, 5],
      endArrow: true,
      opacity: 0.95,
    };
  }

  return {
    stroke: '#91a1ba',
    lineWidth: 1.5,
    endArrow: true,
    opacity: 0.88,
  };
}
export function adaptKnowledgeModelToGraph(
  model: KnowledgeModelResponse,
  visibility: KnowledgeRelationVisibility = DEFAULT_VISIBILITY,
): KnowledgeGraphData {
  const allEdges = validEdges(model);
  const containsEdges = allEdges.filter((edge) => edge.relation_type === 'contains');
  const layout = buildForestLayout(model, containsEdges);
  const nodeIdByGraphId = new Map<string, number>();
  const edgeIdByGraphId = new Map<string, number>();

  const nodes: KnowledgeGraphRenderNode[] = sortById(model.nodes).map((node) => {
    const id = graphNodeId(node.id);
    const position = layout.positions.get(node.id) ?? { x: 0, y: 0 };
    nodeIdByGraphId.set(id, node.id);
    return {
      id,
      type: 'rect',
      data: { knowledgeNodeId: node.id },
      style: {
        x: position.x,
        y: position.y,
        size: [NODE_WIDTH, NODE_HEIGHT],
        radius: 12,
        fill: '#fbfcff',
        stroke: '#7088bb',
        lineWidth: 1.25,
        shadowColor: 'rgba(33, 51, 88, 0.08)',
        shadowBlur: 8,
        shadowOffsetY: 2,
        labelText: node.name,
        labelPlacement: 'center',
        labelTextAlign: 'center',
        labelTextBaseline: 'middle',
        labelFill: '#263859',
        labelFontSize: 13,
        labelFontWeight: 600,
        labelMaxWidth: NODE_WIDTH - 24,
        labelWordWrap: true,
      },
    };
  });

  const edges: KnowledgeGraphRenderEdge[] = allEdges
    .filter((edge) => visibility[edge.relation_type])
    .map((edge) => {
      const id = graphEdgeId(edge.id);
      edgeIdByGraphId.set(id, edge.id);
      return {
        id,
        type: 'line',
        source: graphNodeId(edge.source_node_id),
        target: graphNodeId(edge.target_node_id),
        data: { knowledgeEdgeId: edge.id, relationType: edge.relation_type },
        style: edgeStyle(edge.relation_type),
      };
    });

  return {
    data: { nodes, edges },
    nodeIds: nodes.map((node) => node.id),
    edgeIds: edges.map((edge) => edge.id),
    nodeIdByGraphId,
    edgeIdByGraphId,
    rootNodeIds: layout.rootNodeIds,
  };
}
