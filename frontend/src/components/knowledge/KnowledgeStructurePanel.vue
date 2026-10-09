<script setup lang="ts">
import { MagicStick, RefreshRight } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { computed, defineAsyncComponent, toRef } from 'vue';

import KnowledgeEdgeDetail from '@/components/knowledge/KnowledgeEdgeDetail.vue';
import KnowledgeNodeDetail from '@/components/knowledge/KnowledgeNodeDetail.vue';
import { useKnowledgeModel } from '@/composables/useKnowledgeModel';
import type { Material } from '@/types/course';

const KnowledgeGraph = defineAsyncComponent(
  () => import('@/components/knowledge/KnowledgeGraph.vue'),
);

const props = defineProps<{
  courseId: number;
  materials: Material[];
}>();

const {
  state,
  model,
  errorMessage,
  buildErrorMessage,
  isBuilding,
  selectedNodeDetail,
  isNodeDetailOpen,
  isNodeDetailLoading,
  selectedEdge,
  isEdgeDetailOpen,
  visibility,
  nodeCount,
  containsCount,
  prerequisiteCount,
  load,
  build,
  selectNode,
  selectEdge,
  edgeEvidence,
} = useKnowledgeModel(toRef(props, 'courseId'));

const canBuild = computed(() =>
  props.materials.some(
    (material) =>
      material.extraction_status === 'SUCCESS' || material.extraction_status === 'EXTRACTED',
  ),
);
const hasNodes = computed(() => (model.value?.nodes.length ?? 0) > 0);
const buildLabel = computed(() => (hasNodes.value ? '更新知识结构' : '建立知识结构'));

async function handleBuild(): Promise<void> {
  const succeeded = await build();
  if (succeeded) {
    ElMessage.success('课程知识结构已更新。');
  }
}
</script>

<template>
  <section class="knowledge-structure" aria-labelledby="knowledge-structure-heading">
    <header class="knowledge-structure__header">
      <div>
        <p class="knowledge-structure__eyebrow">Course Knowledge Model</p>
        <h2 id="knowledge-structure-heading">课程知识结构</h2>
        <p>查看课程知识点之间的层级与先修关系。</p>
      </div>
      <div class="knowledge-structure__actions">
        <el-tooltip
          :disabled="canBuild"
          content="请先上传并完成至少一份课程资料的解析。"
          placement="top"
        >
          <span>
            <el-button
              type="primary"
              :loading="isBuilding"
              :disabled="!canBuild || isBuilding"
              @click="handleBuild"
            >
              <el-icon><RefreshRight v-if="hasNodes" /><MagicStick v-else /></el-icon>
              {{ isBuilding ? '正在分析课程资料并建立知识结构…' : buildLabel }}
            </el-button>
          </span>
        </el-tooltip>
      </div>
    </header>

    <p v-if="isBuilding" class="knowledge-structure__build-status" role="status" aria-live="polite">
      正在分析课程资料并建立知识结构…
    </p>
    <el-alert
      v-if="buildErrorMessage"
      title="更新知识结构失败，当前结果已保留"
      :description="buildErrorMessage"
      type="error"
      :closable="false"
      show-icon
      class="knowledge-structure__alert"
    />

    <section v-if="state === 'loading' && !model" class="knowledge-structure__loading" aria-label="正在加载课程知识结构">
      <el-skeleton animated>
        <template #template>
          <el-skeleton-item variant="p" style="width: 24%; margin-bottom: 1rem" />
          <el-skeleton-item variant="rect" style="height: 34rem; border-radius: 18px" />
        </template>
      </el-skeleton>
    </section>

    <section v-else-if="state === 'error' && !model" class="knowledge-structure__error">
      <el-result icon="error" title="课程知识结构加载失败" :sub-title="errorMessage">
        <template #extra>
          <el-button type="primary" @click="load()">重新加载</el-button>
        </template>
      </el-result>
    </section>

    <section v-else-if="model && !hasNodes" class="knowledge-structure__empty">
      <el-empty description="尚未建立课程知识结构" :image-size="112">
        <template #description>
          <p>尚未建立课程知识结构</p>
          <p class="knowledge-structure__empty-copy">上传并完成课程资料解析后，即可在这里建立可追溯的知识结构。</p>
        </template>
        <el-button v-if="canBuild" type="primary" :loading="isBuilding" @click="handleBuild">
          <el-icon><MagicStick /></el-icon>建立知识结构
        </el-button>
      </el-empty>
    </section>

    <template v-else-if="model">
      <section class="knowledge-structure__overview" aria-label="知识结构概览">
        <div class="knowledge-stat">
          <strong>{{ nodeCount }}</strong>
          <span>知识点</span>
        </div>
        <div class="knowledge-stat">
          <strong>{{ containsCount }}</strong>
          <span>层级关系</span>
        </div>
        <div class="knowledge-stat">
          <strong>{{ prerequisiteCount }}</strong>
          <span>先修关系</span>
        </div>
        <div class="knowledge-structure__filters" aria-label="关系筛选">
          <el-switch v-model="visibility.contains" inline-prompt active-text="层级" inactive-text="层级" />
          <el-switch
            v-model="visibility.prerequisite"
            inline-prompt
            active-text="先修"
            inactive-text="先修"
          />
        </div>
      </section>

      <section class="knowledge-structure__legend" aria-label="关系图例">
        <span><i class="legend-line contains" aria-hidden="true" />层级关系：父概念指向子概念</span>
        <span><i class="legend-line prerequisite" aria-hidden="true" />先修关系：先修知识指向依赖知识</span>
      </section>

      <KnowledgeGraph
        :model="model"
        :visibility="visibility"
        @select-node="selectNode"
        @select-edge="selectEdge"
      />
    </template>

    <KnowledgeNodeDetail
      v-model="isNodeDetailOpen"
      :detail="selectedNodeDetail"
      :materials="materials"
      :loading="isNodeDetailLoading"
    />
    <KnowledgeEdgeDetail
      v-model="isEdgeDetailOpen"
      :edge="selectedEdge"
      :nodes="model?.nodes ?? []"
      :evidence="selectedEdge ? edgeEvidence(selectedEdge.id) : []"
      :materials="materials"
    />

    <p v-if="state === 'ready' && errorMessage" class="knowledge-structure__soft-error" role="status">
      {{ errorMessage }}
    </p>
  </section>
</template>

<style scoped>
.knowledge-structure {
  display: grid;
  gap: 1.15rem;
}

.knowledge-structure__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.25rem;
}

.knowledge-structure__eyebrow {
  margin: 0 0 0.36rem;
  color: #6f7f9c;
  font-size: 0.72rem;
  font-weight: 750;
  letter-spacing: 0.11em;
  text-transform: uppercase;
}

.knowledge-structure__header h2 {
  margin: 0;
  color: #203451;
  font-family: var(--lp-font-display, inherit);
  font-size: clamp(1.35rem, 2vw, 1.7rem);
}

.knowledge-structure__header p:not(.knowledge-structure__eyebrow) {
  margin: 0.52rem 0 0;
  color: #667792;
}

.knowledge-structure__actions {
  flex: 0 0 auto;
}

.knowledge-structure__build-status {
  margin: -0.45rem 0 0;
  color: #4b669d;
  font-size: 0.88rem;
}

.knowledge-structure__alert {
  margin: 0;
}

.knowledge-structure__overview {
  display: flex;
  align-items: stretch;
  gap: 0.7rem;
  flex-wrap: wrap;
}

.knowledge-stat {
  display: grid;
  min-width: 7.1rem;
  padding: 0.75rem 0.9rem;
  border: 1px solid #dfe7f2;
  border-radius: 12px;
  background: #fbfcff;
}

.knowledge-stat strong {
  color: #2b4f94;
  font-size: 1.13rem;
}

.knowledge-stat span {
  margin-top: 0.18rem;
  color: #6c7c97;
  font-size: 0.78rem;
}

.knowledge-structure__filters {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  margin-left: auto;
  padding: 0.45rem 0.1rem;
}

.knowledge-structure__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem 1.4rem;
  color: #5f708c;
  font-size: 0.83rem;
}

.knowledge-structure__legend span {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
}

.legend-line {
  position: relative;
  display: inline-block;
  width: 2.15rem;
  height: 0;
  border-top: 2px solid #91a1ba;
}

.legend-line::after {
  position: absolute;
  top: -5px;
  right: -1px;
  width: 0;
  height: 0;
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  border-left: 6px solid currentColor;
  content: '';
}

.legend-line.contains {
  color: #91a1ba;
}

.legend-line.prerequisite {
  border-top-style: dashed;
  border-color: #5874d1;
  color: #5874d1;
}

.knowledge-structure__loading,
.knowledge-structure__error,
.knowledge-structure__empty {
  min-height: 25rem;
  padding: 1.2rem;
  border: 1px solid #e0e7f1;
  border-radius: 18px;
  background: #fbfdff;
}

.knowledge-structure__error,
.knowledge-structure__empty {
  display: grid;
  place-items: center;
}

.knowledge-structure__empty-copy {
  max-width: 31rem;
  margin: 0.55rem auto 0;
  color: #697994;
  line-height: 1.65;
}

.knowledge-structure__soft-error {
  margin: 0;
  color: #af5047;
  font-size: 0.88rem;
}

@media (max-width: 767px) {
  .knowledge-structure__header {
    flex-direction: column;
  }

  .knowledge-structure__actions,
  .knowledge-structure__actions :deep(.el-button) {
    width: 100%;
  }

  .knowledge-structure__filters {
    width: 100%;
    justify-content: flex-start;
    margin-left: 0;
  }
}
</style>
