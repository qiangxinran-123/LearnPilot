<script setup lang="ts">
import { computed, ref } from 'vue';

import type { Material } from '@/types/course';
import type { KnowledgeNodeDetailResponse } from '@/types/knowledge';

const props = defineProps<{
  modelValue: boolean;
  detail: KnowledgeNodeDetailResponse | null;
  materials: Material[];
  loading?: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
}>();

const expandedSourceIds = ref(new Set<number>());

const importanceLabel = computed(() => {
  const importance = props.detail?.node.importance;
  return { low: '低', medium: '中', high: '高' }[importance ?? 'medium'];
});

const difficultyLabel = computed(() => {
  const difficulty = props.detail?.node.difficulty;
  return { basic: '基础', intermediate: '进阶', advanced: '高级' }[difficulty ?? 'intermediate'];
});

function materialTitle(materialId: number): string {
  return props.materials.find((material) => material.id === materialId)?.title ?? '课程资料';
}

function isExpanded(sourceId: number): boolean {
  return expandedSourceIds.value.has(sourceId);
}

function toggleExcerpt(sourceId: number): void {
  const next = new Set(expandedSourceIds.value);
  if (next.has(sourceId)) {
    next.delete(sourceId);
  } else {
    next.add(sourceId);
  }
  expandedSourceIds.value = next;
}
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    title="知识点详情"
    size="min(29rem, 100%)"
    direction="rtl"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-skeleton v-if="loading" :rows="10" animated />
    <template v-else-if="detail">
      <div class="knowledge-detail-heading">
        <p class="knowledge-detail-eyebrow">课程知识点</p>
        <h2>{{ detail.node.name }}</h2>
      </div>

      <p class="knowledge-detail-description">
        {{ detail.node.description || '该知识点暂未提供简要说明。' }}
      </p>

      <dl class="knowledge-detail-metadata">
        <div>
          <dt>课程重要程度</dt>
          <dd>{{ importanceLabel }}</dd>
        </div>
        <div>
          <dt>学习难度</dt>
          <dd>{{ difficultyLabel }}</dd>
        </div>
      </dl>

      <section class="knowledge-provenance" aria-labelledby="node-provenance-title">
        <div class="knowledge-section-title">
          <div>
            <p class="knowledge-detail-eyebrow">来源追溯</p>
            <h3 id="node-provenance-title">支持该知识点的课程资料</h3>
          </div>
          <span>{{ detail.sources.length }} 条</span>
        </div>

        <el-empty
          v-if="detail.sources.length === 0"
          description="暂未记录来源片段"
          :image-size="76"
        />
        <ul v-else class="knowledge-source-list">
          <li v-for="source in detail.sources" :key="source.id">
            <p class="knowledge-source-title">{{ materialTitle(source.material_id) }}</p>
            <p class="knowledge-source-reference">{{ source.source_reference }}</p>
            <template v-if="source.excerpt">
              <p class="knowledge-source-excerpt" :class="{ expanded: isExpanded(source.id) }">
                {{ source.excerpt }}
              </p>
              <el-button link type="primary" @click="toggleExcerpt(source.id)">
                {{ isExpanded(source.id) ? '收起摘录' : '展开摘录' }}
              </el-button>
            </template>
          </li>
        </ul>
      </section>
    </template>
  </el-drawer>
</template>

<style scoped>
.knowledge-detail-heading h2,
.knowledge-section-title h3 {
  margin: 0;
  color: #213552;
  font-family: var(--lp-font-display, inherit);
}

.knowledge-detail-heading h2 {
  font-size: 1.55rem;
  line-height: 1.35;
}

.knowledge-detail-eyebrow {
  margin: 0 0 0.32rem;
  color: #6d7d99;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.knowledge-detail-description {
  margin: 1rem 0 1.25rem;
  color: #596982;
  line-height: 1.75;
}

.knowledge-detail-metadata {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
  margin: 0 0 1.6rem;
}

.knowledge-detail-metadata div {
  padding: 0.84rem 0.9rem;
  border: 1px solid #e0e7f1;
  border-radius: 12px;
  background: #f9fbff;
}

.knowledge-detail-metadata dt {
  color: #73809a;
  font-size: 0.78rem;
}

.knowledge-detail-metadata dd {
  margin: 0.35rem 0 0;
  color: #2f4d87;
  font-weight: 700;
}

.knowledge-provenance {
  padding-top: 1.25rem;
  border-top: 1px solid #e5ebf3;
}

.knowledge-section-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.knowledge-section-title h3 {
  font-size: 1rem;
}

.knowledge-section-title > span {
  flex: 0 0 auto;
  color: #607299;
  font-size: 0.82rem;
}

.knowledge-source-list {
  display: grid;
  gap: 0.75rem;
  margin: 1rem 0 0;
  padding: 0;
  list-style: none;
}

.knowledge-source-list li {
  padding: 0.9rem;
  border: 1px solid #e0e7f1;
  border-radius: 12px;
  background: #fff;
}

.knowledge-source-title,
.knowledge-source-reference,
.knowledge-source-excerpt {
  margin: 0;
}

.knowledge-source-title {
  color: #2a426e;
  font-size: 0.9rem;
  font-weight: 700;
}

.knowledge-source-reference {
  margin-top: 0.28rem;
  color: #6f7f98;
  font-size: 0.8rem;
}

.knowledge-source-excerpt {
  display: -webkit-box;
  overflow: hidden;
  margin-top: 0.7rem;
  color: #53637d;
  font-size: 0.86rem;
  line-height: 1.65;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.knowledge-source-excerpt.expanded {
  display: block;
}
</style>
