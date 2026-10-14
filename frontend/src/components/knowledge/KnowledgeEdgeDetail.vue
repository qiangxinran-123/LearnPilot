<script setup lang="ts">
import { computed, ref } from 'vue';

import type { Material } from '@/types/course';
import type { KnowledgeEdge, KnowledgeEdgeEvidence, KnowledgeNode } from '@/types/knowledge';

const props = defineProps<{
  modelValue: boolean;
  edge: KnowledgeEdge | null;
  nodes: KnowledgeNode[];
  evidence: KnowledgeEdgeEvidence[];
  materials: Material[];
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
}>();

const expandedEvidenceIds = ref(new Set<number>());

const sourceNode = computed(
  () => props.nodes.find((node) => node.id === props.edge?.source_node_id) ?? null,
);
const targetNode = computed(
  () => props.nodes.find((node) => node.id === props.edge?.target_node_id) ?? null,
);
const relationTitle = computed(() =>
  props.edge?.relation_type === 'prerequisite' ? '先修关系' : '层级关系',
);
const relationDescription = computed(() => {
  if (!props.edge || !sourceNode.value || !targetNode.value) {
    return '';
  }
  return props.edge.relation_type === 'prerequisite'
    ? `学习“${targetNode.value.name}”前，需要先掌握“${sourceNode.value.name}”。`
    : `“${sourceNode.value.name}”包含或统摄“${targetNode.value.name}”。`;
});

function materialTitle(materialId: number | null): string | null {
  if (materialId === null) {
    return null;
  }
  return props.materials.find((material) => material.id === materialId)?.title ?? '课程资料';
}

function evidenceTitle(evidence: KnowledgeEdgeEvidence): string {
  if (evidence.evidence_type === 'material') {
    return materialTitle(evidence.material_id) ?? '课程资料依据';
  }
  if (evidence.evidence_type === 'structural') {
    return '知识结构约束';
  }
  return '模型关系判断';
}

function isExpanded(evidenceId: number): boolean {
  return expandedEvidenceIds.value.has(evidenceId);
}

function toggleExcerpt(evidenceId: number): void {
  const next = new Set(expandedEvidenceIds.value);
  if (next.has(evidenceId)) {
    next.delete(evidenceId);
  } else {
    next.add(evidenceId);
  }
  expandedEvidenceIds.value = next;
}
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    title="关系详情"
    size="min(29rem, 100%)"
    direction="rtl"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template v-if="edge && sourceNode && targetNode">
      <div class="knowledge-edge-heading">
        <p class="knowledge-edge-eyebrow">{{ relationTitle }}</p>
        <h2>{{ sourceNode.name }} <span aria-hidden="true">→</span> {{ targetNode.name }}</h2>
      </div>
      <p class="knowledge-edge-description">{{ relationDescription }}</p>

      <section class="knowledge-edge-evidence" aria-labelledby="edge-evidence-title">
        <div class="knowledge-edge-section-title">
          <div>
            <p class="knowledge-edge-eyebrow">可追溯依据</p>
            <h3 id="edge-evidence-title">生成关系的说明</h3>
          </div>
          <span>{{ evidence.length }} 条</span>
        </div>

        <p v-if="evidence.length === 0" class="knowledge-edge-empty">
          此关系暂未记录可展示的生成依据。
        </p>
        <ul v-else class="knowledge-evidence-list">
          <li v-for="item in evidence" :key="item.id">
            <p class="knowledge-evidence-title">{{ evidenceTitle(item) }}</p>
            <p class="knowledge-evidence-reason">{{ item.reason }}</p>
            <p
              v-if="item.evidence_type === 'material' && item.source_reference"
              class="knowledge-evidence-reference"
            >
              {{ item.source_reference }}
            </p>
            <template v-if="item.evidence_type === 'material' && item.excerpt">
              <p class="knowledge-evidence-excerpt" :class="{ expanded: isExpanded(item.id) }">
                {{ item.excerpt }}
              </p>
              <el-button link type="primary" @click="toggleExcerpt(item.id)">
                {{ isExpanded(item.id) ? '收起摘录' : '展开摘录' }}
              </el-button>
            </template>
          </li>
        </ul>
      </section>
    </template>
  </el-drawer>
</template>

<style scoped>
.knowledge-edge-heading h2,
.knowledge-edge-section-title h3 {
  margin: 0;
  color: #213552;
  font-family: var(--lp-font-display, inherit);
}

.knowledge-edge-heading h2 {
  font-size: 1.32rem;
  line-height: 1.5;
}

.knowledge-edge-eyebrow {
  margin: 0 0 0.32rem;
  color: #6d7d99;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.knowledge-edge-description {
  margin: 1rem 0 1.4rem;
  color: #596982;
  line-height: 1.75;
}

.knowledge-edge-evidence {
  padding-top: 1.2rem;
  border-top: 1px solid #e5ebf3;
}

.knowledge-edge-section-title {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}

.knowledge-edge-section-title h3 {
  font-size: 1rem;
}

.knowledge-edge-section-title > span {
  color: #607299;
  font-size: 0.82rem;
}

.knowledge-edge-empty {
  margin: 1rem 0 0;
  color: #687891;
  line-height: 1.65;
}

.knowledge-evidence-list {
  display: grid;
  gap: 0.75rem;
  margin: 1rem 0 0;
  padding: 0;
  list-style: none;
}

.knowledge-evidence-list li {
  padding: 0.9rem;
  border: 1px solid #e0e7f1;
  border-radius: 12px;
  background: #fff;
}

.knowledge-evidence-title,
.knowledge-evidence-reason,
.knowledge-evidence-reference,
.knowledge-evidence-excerpt {
  margin: 0;
}

.knowledge-evidence-title {
  color: #2a426e;
  font-size: 0.9rem;
  font-weight: 700;
}

.knowledge-evidence-reason {
  margin-top: 0.45rem;
  color: #53637d;
  font-size: 0.88rem;
  line-height: 1.65;
}

.knowledge-evidence-reference {
  margin-top: 0.45rem;
  color: #71809a;
  font-size: 0.8rem;
}

.knowledge-evidence-excerpt {
  display: -webkit-box;
  overflow: hidden;
  margin-top: 0.65rem;
  color: #596982;
  font-size: 0.84rem;
  line-height: 1.65;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.knowledge-evidence-excerpt.expanded {
  display: block;
}
</style>
