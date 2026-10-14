<script setup lang="ts">
import { FullScreen, RefreshLeft, ZoomIn, ZoomOut } from '@element-plus/icons-vue';
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import {
  adaptKnowledgeModelToGraph,
  type KnowledgeGraphData,
  type KnowledgeRelationVisibility,
} from '@/components/knowledge/graphAdapter';
import { loadG6Graph } from '@/components/knowledge/g6Loader';
import type { KnowledgeModelResponse } from '@/types/knowledge';

interface G6GraphLike {
  setData: CallableFunction;
  render: CallableFunction;
  fitView: CallableFunction;
  zoomBy: CallableFunction;
  zoomTo: CallableFunction;
  resize: CallableFunction;
  destroy: CallableFunction;
  on: CallableFunction;
}

const props = defineProps<{
  model: KnowledgeModelResponse;
  visibility: KnowledgeRelationVisibility;
}>();

const emit = defineEmits<{
  selectNode: [nodeId: number];
  selectEdge: [edgeId: number];
}>();

const container = ref<HTMLElement>();
const graph = ref<G6GraphLike>();
const graphData = ref<KnowledgeGraphData>(
  adaptKnowledgeModelToGraph(props.model, props.visibility),
);
const graphError = ref(false);
let resizeObserver: ResizeObserver | undefined;
let disposed = false;

const accessibleSummary = computed(
  () =>
    `课程知识结构，共 ${graphData.value.nodeIds.length} 个知识点，显示 ${graphData.value.edgeIds.length} 条关系。`,
);

function getGraphElementId(event: unknown): string | undefined {
  if (typeof event !== 'object' || event === null || !('target' in event)) {
    return undefined;
  }
  const target = event.target;
  if (typeof target !== 'object' || target === null || !('id' in target)) {
    return undefined;
  }
  return typeof target.id === 'string' ? target.id : undefined;
}

async function redraw({ fit = false }: { fit?: boolean } = {}): Promise<void> {
  if (!graph.value || disposed) {
    return;
  }

  graph.value.setData(graphData.value.data);
  await graph.value.render();
  if (fit) {
    await graph.value.fitView();
  }
}

async function createGraph(): Promise<void> {
  if (!container.value || disposed) {
    return;
  }

  try {
    const Graph = await loadG6Graph();
    if (disposed || !container.value) {
      return;
    }

    const instance = Reflect.construct(Graph as unknown as CallableFunction, [
      {
        container: container.value,
        data: graphData.value.data,
        animation: false,
        autoFit: 'view',
        padding: [48, 56],
        behaviors: [{ type: 'drag-canvas', key: 'drag-canvas' }],
        node: {
          type: 'rect',
        },
        edge: {
          type: 'line',
        },
      },
    ]) as G6GraphLike;

    instance.on('node:click', (event: unknown) => {
      const nodeId = graphData.value.nodeIdByGraphId.get(getGraphElementId(event) ?? '');
      if (nodeId !== undefined) {
        emit('selectNode', nodeId);
      }
    });
    instance.on('edge:click', (event: unknown) => {
      const edgeId = graphData.value.edgeIdByGraphId.get(getGraphElementId(event) ?? '');
      if (edgeId !== undefined) {
        emit('selectEdge', edgeId);
      }
    });

    graph.value = instance;
    await instance.render();
    await instance.fitView();
  } catch {
    graphError.value = true;
  }
}

async function zoomIn(): Promise<void> {
  await graph.value?.zoomBy(1.2);
}

async function zoomOut(): Promise<void> {
  await graph.value?.zoomBy(1 / 1.2);
}

async function fitView(): Promise<void> {
  await graph.value?.fitView();
}

async function resetView(): Promise<void> {
  await graph.value?.zoomTo(1);
  await fitView();
}

watch(
  () => [props.model, props.visibility.contains, props.visibility.prerequisite] as const,
  async () => {
    graphData.value = adaptKnowledgeModelToGraph(props.model, props.visibility);
    await nextTick();
    await redraw({ fit: true });
  },
  { deep: true },
);

onMounted(async () => {
  await createGraph();
  if (!container.value) {
    return;
  }

  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      graph.value?.resize();
      void graph.value?.fitView();
    });
    resizeObserver.observe(container.value);
  }
});

onBeforeUnmount(() => {
  disposed = true;
  resizeObserver?.disconnect();
  resizeObserver = undefined;
  graph.value?.destroy();
  graph.value = undefined;
});
</script>

<template>
  <section class="knowledge-graph-shell" :aria-label="accessibleSummary">
    <div class="knowledge-graph-toolbar" aria-label="图谱视图控制">
      <el-tooltip content="放大" placement="top">
        <el-button circle aria-label="放大知识结构图" @click="zoomIn">
          <el-icon><ZoomIn /></el-icon>
        </el-button>
      </el-tooltip>
      <el-tooltip content="缩小" placement="top">
        <el-button circle aria-label="缩小知识结构图" @click="zoomOut">
          <el-icon><ZoomOut /></el-icon>
        </el-button>
      </el-tooltip>
      <el-tooltip content="适配视图" placement="top">
        <el-button circle aria-label="适配知识结构图视图" @click="fitView">
          <el-icon><FullScreen /></el-icon>
        </el-button>
      </el-tooltip>
      <el-tooltip content="重置视图" placement="top">
        <el-button circle aria-label="重置知识结构图视图" @click="resetView">
          <el-icon><RefreshLeft /></el-icon>
        </el-button>
      </el-tooltip>
    </div>

    <div
      ref="container"
      class="knowledge-graph-canvas"
      role="application"
      :aria-label="accessibleSummary"
    />
    <div v-if="graphError" class="knowledge-graph-fallback" role="status">
      图谱渲染暂不可用，请重新加载页面。
    </div>
  </section>
</template>

<style scoped>
.knowledge-graph-shell {
  position: relative;
  min-height: clamp(30rem, 58vh, 44rem);
  overflow: hidden;
  border: 1px solid var(--lp-border-subtle, #dce4f1);
  border-radius: 18px;
  background:
    linear-gradient(rgba(96, 117, 166, 0.055) 1px, transparent 1px),
    linear-gradient(90deg, rgba(96, 117, 166, 0.055) 1px, transparent 1px), #fafdff;
  background-size: 24px 24px;
}

.knowledge-graph-canvas {
  min-height: inherit;
  width: 100%;
}

.knowledge-graph-toolbar {
  position: absolute;
  z-index: 2;
  top: 16px;
  right: 16px;
  display: flex;
  gap: 8px;
  padding: 7px;
  border: 1px solid rgba(196, 207, 227, 0.92);
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 8px 22px rgba(41, 57, 92, 0.1);
  backdrop-filter: blur(8px);
}

.knowledge-graph-toolbar :deep(.el-button) {
  border-color: transparent;
  color: #3d568a;
}

.knowledge-graph-toolbar :deep(.el-button:hover),
.knowledge-graph-toolbar :deep(.el-button:focus-visible) {
  border-color: #b5c6ef;
  background: #edf2ff;
  color: #3158af;
}

.knowledge-graph-fallback {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 2rem;
  color: #66728a;
  background: rgba(250, 253, 255, 0.9);
}

@media (max-width: 767px) {
  .knowledge-graph-shell {
    min-height: 27rem;
  }

  .knowledge-graph-toolbar {
    top: 12px;
    right: 12px;
    gap: 4px;
  }
}
</style>
