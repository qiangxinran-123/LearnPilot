<script setup lang="ts">
import { computed } from 'vue';

import {
  confidenceLabel,
  masteryScoreLabel,
  masteryStatusLabel,
} from '@/components/knowledge/masteryPresentation';
import type { KnowledgeEvidenceExplanation } from '@/types/mastery';

const props = defineProps<{
  loading: boolean;
  error: string;
  explanation: KnowledgeEvidenceExplanation | null;
}>();
defineEmits<{ retry: [] }>();

const state = computed(() => props.explanation?.state);
const difficultyLabel = { easy: '简单', medium: '中等', hard: '困难' } as const;
const scoreLabel = (score: string) => `${(Number(score) * 100).toFixed(0)}%`;
const dateLabel = (value: string) =>
  new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' }).format(
    new Date(value),
  );
</script>

<template>
  <section class="mastery-detail" aria-labelledby="mastery-detail-heading">
    <div class="mastery-detail__heading">
      <div>
        <p>个人学习状态</p>
        <h2 id="mastery-detail-heading">我的掌握情况</h2>
      </div>
      <span v-if="state?.algorithm_version">算法版本：{{ state.algorithm_version }}</span>
    </div>
    <p v-if="loading" role="status">正在读取已保存的掌握状态…</p>
    <div v-else-if="error" class="mastery-detail__error" role="alert">
      <p>掌握情况暂时无法读取：{{ error }}</p>
      <el-button size="small" @click="$emit('retry')">重试</el-button>
    </div>
    <template v-else-if="explanation && state">
      <div class="mastery-detail__metrics">
        <div>
          <span>掌握度</span><strong>{{ masteryScoreLabel(state) }}</strong>
        </div>
        <div>
          <span>状态</span><strong>{{ masteryStatusLabel[state.mastery_status] }}</strong>
        </div>
        <div>
          <span>置信度</span><strong>{{ confidenceLabel[state.confidence_level] }}</strong>
        </div>
        <div>
          <span>有效证据</span><strong>{{ state.evidence_count }} 条</strong>
        </div>
        <div>
          <span>独立诊断</span><strong>{{ state.assessment_count }} 次</strong>
        </div>
      </div>
      <p v-if="state.calculation_state === 'not_calculated'" class="mastery-detail__notice">
        当前状态尚未计算。阅读页面不会自动生成或更新掌握度。
      </p>
      <p v-else-if="state.calculation_state === 'stale'" class="mastery-detail__notice">
        已保存状态与当前有效证据不一致，暂不展示旧的掌握结论。
      </p>
      <p v-else-if="state.mastery_score === null" class="mastery-detail__notice">
        当前有效独立证据不足，暂不发布掌握度百分比。
      </p>
      <div v-if="explanation.evidence.length" class="mastery-detail__evidence">
        <h3>计算采用的诊断证据</h3>
        <ul>
          <li v-for="item in explanation.evidence" :key="item.evidence_id">
            <div>
              <strong>诊断 #{{ item.source_assessment_id }}</strong>
              <span>{{ dateLabel(item.occurred_at) }}</span>
            </div>
            <p>
              历史题目 #{{ item.source_question_reference }} ·
              {{ difficultyLabel[item.difficulty] }} · 表现 {{ scoreLabel(item.normalized_score) }}
            </p>
          </li>
        </ul>
      </div>
      <p v-else class="mastery-detail__notice">当前没有可公开且已计入该状态的证据明细。</p>
    </template>
  </section>
</template>

<style scoped>
.mastery-detail {
  margin: 1rem 0 1.5rem;
  padding: 1.15rem;
  border: 1px solid #dbe4ef;
  border-radius: var(--lp-radius-lg);
  background: #f8fbff;
}
.mastery-detail__heading,
.mastery-detail__evidence li > div {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}
.mastery-detail__heading p,
.mastery-detail__heading h2,
.mastery-detail__error p,
.mastery-detail__evidence p {
  margin: 0;
}
.mastery-detail__heading p,
.mastery-detail__metrics span,
.mastery-detail__heading > span,
.mastery-detail__evidence span {
  color: var(--lp-text-secondary);
  font-size: 0.75rem;
}
.mastery-detail__heading h2 {
  margin-top: 0.18rem;
  color: var(--lp-ink);
  font-size: 1.12rem;
}
.mastery-detail__metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.6rem;
  margin-top: 1rem;
}
.mastery-detail__metrics div {
  display: grid;
  gap: 0.3rem;
  padding: 0.7rem;
  border-radius: 10px;
  background: #fff;
}
.mastery-detail__metrics strong {
  color: #294774;
}
.mastery-detail__notice,
.mastery-detail__error {
  margin: 0.9rem 0 0;
  color: #67542e;
}
.mastery-detail__error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.mastery-detail__evidence {
  margin-top: 1rem;
}
.mastery-detail__evidence h3 {
  margin: 0 0 0.65rem;
  font-size: 0.92rem;
}
.mastery-detail__evidence ul {
  display: grid;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.mastery-detail__evidence li {
  padding: 0.7rem;
  border: 1px solid #e0e7f1;
  border-radius: 10px;
  background: #fff;
}
.mastery-detail__evidence p {
  margin-top: 0.32rem;
  color: var(--lp-text-secondary);
  font-size: 0.8rem;
}
@media (max-width: 800px) {
  .mastery-detail__metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
