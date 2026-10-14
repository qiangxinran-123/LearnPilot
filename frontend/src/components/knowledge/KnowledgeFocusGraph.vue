<script setup lang="ts">
import { FullScreen, RefreshLeft, ZoomIn, ZoomOut } from '@element-plus/icons-vue';
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import type { KnowledgeFocusData } from '@/components/knowledge/knowledgeMapAdapter';

const props = withDefaults(
  defineProps<{
    data: KnowledgeFocusData;
    initialLimit?: number;
  }>(),
  { initialLimit: 5 },
);

const emit = defineEmits<{ focus: [nodeId: number] }>();
const showAllPrerequisites = ref(false);
const showAllDependents = ref(false);
const viewport = ref<HTMLElement>();
const canvas = ref<HTMLElement>();
const scale = ref(1);
const translateX = ref(0);
const translateY = ref(0);
const isPanning = ref(false);
const minimumScale = 0.5;
const maximumScale = 2;
const scaleStep = 0.15;
let activePointerId: number | null = null;
let previousPointerX = 0;
let previousPointerY = 0;
let resizeObserver: ResizeObserver | undefined;
let observedWidth = 0;
let observedHeight = 0;

const visiblePrerequisites = computed(() =>
  showAllPrerequisites.value
    ? props.data.prerequisiteNodes
    : props.data.prerequisiteNodes.slice(0, props.initialLimit),
);
const visibleDependents = computed(() =>
  showAllDependents.value
    ? props.data.dependentNodes
    : props.data.dependentNodes.slice(0, props.initialLimit),
);
const hiddenPrerequisiteCount = computed(
  () => props.data.prerequisiteNodes.length - visiblePrerequisites.value.length,
);
const hiddenDependentCount = computed(
  () => props.data.dependentNodes.length - visibleDependents.value.length,
);
const scalePercent = computed(() => Math.round(scale.value * 100));
const canZoomIn = computed(() => scale.value < maximumScale);
const canZoomOut = computed(() => scale.value > minimumScale);
const canvasStyle = computed(() => ({
  transform: `translate(${translateX.value}px, ${translateY.value}px) scale(${scale.value})`,
}));

function clampScale(value: number): number {
  return Math.min(maximumScale, Math.max(minimumScale, Number(value.toFixed(2))));
}

function zoomBy(delta: number): void {
  scale.value = clampScale(scale.value + delta);
}

function resetView(): void {
  scale.value = 1;
  translateX.value = 0;
  translateY.value = 0;
}

function fitView(): void {
  if (!viewport.value || !canvas.value || !props.data.focusNode) return;

  const horizontalPadding = 32;
  const verticalPadding = 32;
  const availableWidth = Math.max(0, viewport.value.clientWidth - horizontalPadding);
  const availableHeight = Math.max(0, viewport.value.clientHeight - verticalPadding);
  const contentWidth = canvas.value.scrollWidth;
  const contentHeight = canvas.value.scrollHeight;

  if (!availableWidth || !availableHeight || !contentWidth || !contentHeight) {
    resetView();
    return;
  }

  scale.value = clampScale(
    Math.min(1, availableWidth / contentWidth, availableHeight / contentHeight),
  );
  translateX.value = 0;
  translateY.value = 0;
}

function isInteractiveTarget(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest('button, a, .focus-graph__group'));
}

function startPan(event: PointerEvent): void {
  if (event.button !== 0 || isInteractiveTarget(event.target)) return;
  activePointerId = event.pointerId;
  previousPointerX = event.clientX;
  previousPointerY = event.clientY;
  isPanning.value = true;
  (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
}

function movePan(event: PointerEvent): void {
  if (!isPanning.value || event.pointerId !== activePointerId) return;
  translateX.value += event.clientX - previousPointerX;
  translateY.value += event.clientY - previousPointerY;
  previousPointerX = event.clientX;
  previousPointerY = event.clientY;
  event.preventDefault();
}

function stopPan(event: PointerEvent): void {
  if (event.pointerId !== activePointerId) return;
  (event.currentTarget as HTMLElement).releasePointerCapture?.(event.pointerId);
  activePointerId = null;
  isPanning.value = false;
}

watch(
  () => props.data.focusNode?.id,
  async () => {
    showAllPrerequisites.value = false;
    showAllDependents.value = false;
    await nextTick();
    fitView();
  },
);

onMounted(async () => {
  if (typeof ResizeObserver === 'undefined' || !viewport.value) return;
  await nextTick();
  fitView();
  observedWidth = viewport.value.clientWidth;
  observedHeight = viewport.value.clientHeight;
  resizeObserver = new ResizeObserver(() => {
    if (!viewport.value) return;
    const nextWidth = viewport.value.clientWidth;
    const nextHeight = viewport.value.clientHeight;
    if (nextWidth === observedWidth && nextHeight === observedHeight) return;
    observedWidth = nextWidth;
    observedHeight = nextHeight;
    fitView();
  });
  resizeObserver.observe(viewport.value);
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  resizeObserver = undefined;
  activePointerId = null;
});
</script>

<template>
  <section class="focus-graph" aria-labelledby="focus-graph-heading">
    <div class="focus-graph__heading">
      <div>
        <h3 id="focus-graph-heading">直接学习关系</h3>
        <p>仅展示与当前知识点直接相连的一层先修关系。</p>
      </div>
      <span class="focus-graph__legend">先修知识 → 后续知识</span>
    </div>

    <div v-if="data.focusNode" class="focus-graph__toolbar" aria-label="知识关系图视图控制">
      <button
        type="button"
        class="focus-graph__tool-button"
        :disabled="!canZoomIn"
        aria-label="放大知识关系图"
        title="放大"
        @click="zoomBy(scaleStep)"
        @keydown.enter.prevent="zoomBy(scaleStep)"
      >
        <el-icon><ZoomIn /></el-icon>
      </button>
      <span class="focus-graph__scale" aria-live="polite">{{ scalePercent }}%</span>
      <button
        type="button"
        class="focus-graph__tool-button"
        :disabled="!canZoomOut"
        aria-label="缩小知识关系图"
        title="缩小"
        @click="zoomBy(-scaleStep)"
        @keydown.enter.prevent="zoomBy(-scaleStep)"
      >
        <el-icon><ZoomOut /></el-icon>
      </button>
      <button
        type="button"
        class="focus-graph__tool-button"
        aria-label="适应知识关系图画布"
        title="适应画布"
        @click="fitView"
        @keydown.enter.prevent="fitView"
      >
        <el-icon><FullScreen /></el-icon>
      </button>
      <button
        type="button"
        class="focus-graph__tool-button"
        aria-label="恢复知识关系图默认视图"
        title="恢复默认视图"
        @click="resetView"
        @keydown.enter.prevent="resetView"
      >
        <el-icon><RefreshLeft /></el-icon>
      </button>
    </div>

    <div
      v-if="data.focusNode"
      ref="viewport"
      class="focus-graph__viewport"
      :class="{ 'is-panning': isPanning }"
      data-testid="knowledge-focus-viewport"
      @pointerdown="startPan"
      @pointermove="movePan"
      @pointerup="stopPan"
      @pointercancel="stopPan"
    >
      <div ref="canvas" class="focus-graph__columns" :style="canvasStyle">
        <section class="focus-graph__group" aria-labelledby="prerequisite-heading">
          <h4 id="prerequisite-heading">学习前可以先了解</h4>
          <div v-if="visiblePrerequisites.length" class="focus-graph__nodes">
            <button
              v-for="node in visiblePrerequisites"
              :key="node.id"
              type="button"
              class="focus-node focus-node--before"
              @click="emit('focus', node.id)"
            >
              <strong>{{ node.name }}</strong>
              <span>{{ node.description || '查看它与课程中其他知识的联系' }}</span>
            </button>
            <button
              v-if="hiddenPrerequisiteCount > 0"
              type="button"
              class="focus-graph__more"
              @click="showAllPrerequisites = true"
            >
              查看其余 {{ hiddenPrerequisiteCount }} 个前置知识
            </button>
          </div>
          <p v-else class="focus-graph__empty">当前没有已建立的直接前置关系。</p>
        </section>

        <div class="focus-graph__arrow" aria-hidden="true">
          <span>→</span>
        </div>

        <section
          class="focus-graph__group focus-graph__group--current"
          aria-labelledby="current-heading"
        >
          <h4 id="current-heading">当前知识点</h4>
          <article class="focus-node focus-node--current" aria-current="true">
            <strong>{{ data.focusNode.name }}</strong>
            <span>{{ data.focusNode.description || '当前尚无已保存的知识点说明。' }}</span>
          </article>
        </section>

        <div class="focus-graph__arrow" aria-hidden="true">
          <span>→</span>
        </div>

        <section class="focus-graph__group" aria-labelledby="dependent-heading">
          <h4 id="dependent-heading">接下来还可以看看</h4>
          <div v-if="visibleDependents.length" class="focus-graph__nodes">
            <button
              v-for="node in visibleDependents"
              :key="node.id"
              type="button"
              class="focus-node focus-node--after"
              @click="emit('focus', node.id)"
            >
              <strong>{{ node.name }}</strong>
              <span>{{ node.description || '查看它与课程中其他知识的联系' }}</span>
            </button>
            <button
              v-if="hiddenDependentCount > 0"
              type="button"
              class="focus-graph__more"
              @click="showAllDependents = true"
            >
              查看其余 {{ hiddenDependentCount }} 个后续知识
            </button>
          </div>
          <p v-else class="focus-graph__empty">当前没有已建立的直接后续关系。</p>
        </section>
      </div>
    </div>
  </section>
</template>

<style scoped>
.focus-graph {
  min-width: 0;
  padding: var(--lp-space-5);
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-lg);
  background: var(--lp-surface);
}

.focus-graph__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--lp-space-4);
  margin-bottom: var(--lp-space-5);
}

.focus-graph__heading h3,
.focus-graph__group h4 {
  margin: 0;
  color: var(--lp-ink);
}

.focus-graph__heading p {
  margin: 0.3rem 0 0;
  color: var(--lp-text-secondary);
  font-size: 0.86rem;
}

.focus-graph__legend {
  flex: 0 0 auto;
  padding: 0.35rem 0.65rem;
  border-radius: 999px;
  color: #315b91;
  background: #edf4ff;
  font-size: 0.76rem;
  font-weight: 700;
}

.focus-graph__toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.35rem;
  margin: calc(var(--lp-space-3) * -1) 0 var(--lp-space-3);
}

.focus-graph__tool-button {
  display: inline-grid;
  width: 2rem;
  height: 2rem;
  padding: 0;
  place-items: center;
  border-color: #d5e1f2;
  border-style: solid;
  border-width: 1px;
  border-radius: 50%;
  color: #3d568a;
  background: #fff;
  font: inherit;
  cursor: pointer;
}

.focus-graph__tool-button:hover,
.focus-graph__tool-button:focus-visible {
  border-color: #8daee0;
  color: var(--lp-primary);
  background: #edf4ff;
}

.focus-graph__tool-button:focus-visible {
  outline: 3px solid rgb(61 111 183 / 25%);
  outline-offset: 2px;
}

.focus-graph__tool-button:disabled {
  color: #9ba8ba;
  background: #f3f5f8;
  cursor: not-allowed;
}

.focus-graph__scale {
  min-width: 3rem;
  color: var(--lp-text-secondary);
  font-size: 0.78rem;
  font-variant-numeric: tabular-nums;
  text-align: center;
}

.focus-graph__viewport {
  min-width: 0;
  overflow: hidden;
  border-radius: var(--lp-radius-md);
  cursor: grab;
  touch-action: pan-y;
}

.focus-graph__viewport.is-panning {
  cursor: grabbing;
  user-select: none;
}

.focus-graph__columns {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 32px minmax(180px, 0.9fr) 32px minmax(0, 1fr);
  align-items: center;
  gap: var(--lp-space-3);
  min-height: 19rem;
  transform-origin: center center;
  will-change: transform;
}

.focus-graph__group {
  align-self: stretch;
  min-width: 0;
  padding: var(--lp-space-4);
  border-radius: var(--lp-radius-md);
  background: #f7faff;
}

.focus-graph__group--current {
  display: grid;
  align-content: center;
  background: #f2f6ff;
}

.focus-graph__group h4 {
  margin-bottom: var(--lp-space-3);
  font-size: 0.86rem;
  text-align: center;
}

.focus-graph__nodes {
  display: grid;
  gap: var(--lp-space-2);
}

.focus-node {
  display: grid;
  width: 100%;
  min-width: 0;
  gap: 0.28rem;
  padding: 0.8rem;
  border: 1px solid #d5e1f2;
  border-radius: var(--lp-radius-md);
  color: var(--lp-text);
  background: #fff;
  text-align: left;
  overflow-wrap: anywhere;
}

button.focus-node {
  cursor: pointer;
  transition:
    border-color 150ms ease,
    box-shadow 150ms ease,
    transform 150ms ease;
}

button.focus-node:hover {
  border-color: #83a7dc;
  box-shadow: 0 7px 18px rgb(48 82 128 / 10%);
  transform: translateY(-1px);
}

button.focus-node:focus-visible,
.focus-graph__more:focus-visible {
  outline: 3px solid rgb(61 111 183 / 25%);
  outline-offset: 2px;
}

.focus-node strong {
  color: var(--lp-ink);
  font-size: 0.9rem;
}

.focus-node span {
  display: -webkit-box;
  overflow: hidden;
  color: var(--lp-text-secondary);
  font-size: 0.76rem;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.focus-node--current {
  border: 2px solid var(--lp-primary);
  box-shadow: 0 12px 24px rgb(50 93 159 / 15%);
}

.focus-node--current strong {
  color: var(--lp-primary);
  font-size: 1rem;
}

.focus-node--after {
  border-color: #c9e4da;
}

.focus-graph__arrow {
  display: grid;
  place-items: center;
  color: #57739a;
  font-size: 1.45rem;
  font-weight: 800;
}

.focus-graph__more {
  padding: 0.55rem;
  border: 0;
  color: var(--lp-primary);
  background: transparent;
  font: inherit;
  font-size: 0.78rem;
  font-weight: 700;
  cursor: pointer;
}

.focus-graph__empty {
  margin: 0;
  color: var(--lp-text-secondary);
  font-size: 0.82rem;
  line-height: 1.6;
  text-align: center;
}

@media (max-width: 900px) {
  .focus-graph__columns {
    grid-template-columns: 1fr;
    min-height: 0;
  }

  .focus-graph__arrow {
    transform: rotate(90deg);
  }
}

@media (max-width: 600px) {
  .focus-graph,
  .focus-graph__group {
    padding: var(--lp-space-3);
  }

  .focus-graph__heading {
    display: block;
  }

  .focus-graph__legend {
    display: inline-flex;
    margin-top: var(--lp-space-3);
  }

  .focus-graph__toolbar {
    justify-content: flex-start;
    margin-top: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  button.focus-node {
    transition: none;
  }

  .focus-graph__columns {
    will-change: auto;
  }
}
</style>
