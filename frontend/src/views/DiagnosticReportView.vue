<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { fetchAssessmentResult } from '@/services/diagnostics';
import type { DiagnosticQuestionReview, DiagnosticResult, PreliminaryStatus } from '@/types/diagnostic';

const route = useRoute();
const router = useRouter();
const report = ref<DiagnosticResult | null>(null);
const loading = ref(true);
const error = ref('');
const reviewFilter = ref<'wrong' | 'all'>('wrong');
const knowledgeDialogOpen = ref(false);

const assessmentId = computed(() => Number(route.params.assessmentId));
const percent = (value: number | null) => (value === null ? '未测评' : `${Math.round(value * 100)}%`);
const statusLabel: Record<PreliminaryStatus, string> = {
  needs_attention: '需要关注',
  partially_correct: '表现有待巩固',
  good_performance: '本次表现较好',
  limited_evidence: '证据有限',
  not_assessed: '尚未测评',
};
const statusType: Record<PreliminaryStatus, 'danger' | 'warning' | 'success' | 'info'> = {
  needs_attention: 'danger', partially_correct: 'warning', good_performance: 'success',
  limited_evidence: 'info', not_assessed: 'info',
};
const wrongQuestions = computed<DiagnosticQuestionReview[]>(() => {
  if (!report.value) return [];
  return report.value.question_reviews.filter(
    (item) => item.selected_options.length > 0 && !item.is_correct,
  );
});
const reviewedQuestions = computed<DiagnosticQuestionReview[]>(() => {
  if (!report.value) return [];
  return reviewFilter.value === 'all' ? report.value.question_reviews : wrongQuestions.value;
});
const attentionNodes = computed(() =>
  [...(report.value?.knowledge_performance ?? [])]
    .filter((node) => node.incorrect_count > 0)
    .sort((left, right) =>
      right.incorrect_count - left.incorrect_count
      || (left.accuracy ?? 1) - (right.accuracy ?? 1)
      || left.historical_node_id - right.historical_node_id,
    )
    .slice(0, 3),
);

function answerText(item: DiagnosticQuestionReview, keys: string[]) {
  if (!keys.length) return '未作答';
  return keys.map((key) => `${key}. ${item.options.find((option) => option.key === key)?.text ?? key}`).join('；');
}

async function loadReport() {
  loading.value = true;
  error.value = '';
  try {
    report.value = await fetchAssessmentResult(assessmentId.value);
  } catch {
    error.value = '暂时无法读取这份诊断报告。请确认诊断已提交后重试。';
  } finally {
    loading.value = false;
  }
}

function openKnowledgeMap(node: { historical_node_id: number; map_available: boolean }) {
  if (!report.value || !node.map_available) {
    ElMessage.info('该历史知识点已不在当前知识地图中。');
    return;
  }
  void router.push({
    name: 'course-detail',
    params: { courseId: report.value.course_id },
    query: { tab: 'knowledge-structure', nodeId: String(node.historical_node_id) },
  });
}

onMounted(loadReport);
</script>

<template>
  <main class="report-page">
    <el-button text class="back-link" @click="router.push({ name: 'diagnose' })">← 返回诊断</el-button>
    <section v-if="loading" class="state-panel"><el-skeleton :rows="8" animated /></section>
    <section v-else-if="error" class="state-panel error-panel">
      <h1>报告暂不可用</h1><p>{{ error }}</p><el-button type="primary" @click="loadReport">重新加载</el-button>
    </section>
    <template v-else-if="report">
      <header class="report-header">
        <div><p class="eyebrow">初始诊断 · 已完成</p><h1>{{ report.course_name }}诊断报告</h1>
          <p>这是本次固定试卷的结果观察，不代表长期掌握度或能力标签。</p></div>
        <el-button @click="router.push({ name: 'diagnose' })">查看历史诊断</el-button>
      </header>
      <section class="overview-grid" aria-label="本次诊断概览">
        <article><span>本次正确率</span><strong>{{ percent(report.accuracy) }}</strong></article>
        <article><span>正确题数</span><strong>{{ report.correct_questions }} / {{ report.total_questions }}</strong></article>
        <article><span>已答题数</span><strong>{{ report.answered_questions }} / {{ report.total_questions }}</strong></article>
        <article><span>实际覆盖</span><strong>{{ report.covered_knowledge_nodes }} 个知识点</strong></article>
      </section>
      <section class="content-section">
        <div class="section-heading"><div><p class="eyebrow">本次测评观察</p><h2>需要关注的知识点</h2></div>
          <el-button plain @click="knowledgeDialogOpen = true">查看完整知识点表现</el-button></div>
        <p class="section-intro">这里只呈现与本次错题直接相关的知识点，最多 3 项；本次表现不等于长期掌握度。</p>
        <div v-if="attentionNodes.length" class="attention-list">
          <article v-for="node in attentionNodes" :key="node.historical_node_id" class="attention-card">
            <div class="performance-top"><div><h3>{{ node.historical_node_name }}</h3>
              <p>{{ node.incorrect_count }} 道错题 · 本次 {{ node.correct_count }} / {{ node.question_count }} 题正确</p></div>
              <el-tag :type="statusType[node.preliminary_status]" effect="light">{{ statusLabel[node.preliminary_status] }}</el-tag></div>
          </article>
        </div>
        <p v-else class="knowledge-empty">本次没有可明确归入错题的知识点。可查看本次诊断涉及的完整知识点表现。</p>
      </section>
      <section class="content-section">
        <div class="section-heading"><div><p class="eyebrow">回看固定题目与资料依据</p><h2>错题回顾</h2></div>
          <el-radio-group v-model="reviewFilter" size="small"><el-radio-button value="wrong">错题优先</el-radio-button><el-radio-button value="all">全部题目</el-radio-button></el-radio-group></div>
        <el-empty v-if="!reviewedQuestions.length" :description="reviewFilter === 'wrong' ? '本次没有答错的题目。' : '本次没有可回顾的题目。'">
          <el-button v-if="reviewFilter === 'wrong'" plain @click="reviewFilter = 'all'">查看全部题目</el-button>
        </el-empty>
        <el-collapse v-else class="review-list">
          <el-collapse-item v-for="item in reviewedQuestions" :key="item.assessment_question_id" :name="item.assessment_question_id">
            <template #title><div class="review-heading"><span class="review-title">第 {{ item.order_index + 1 }} 题 · {{ item.stem }}</span>
              <el-tag :type="item.selected_options.length === 0 ? 'info' : item.is_correct ? 'success' : 'danger'" size="small">
                {{ item.selected_options.length === 0 ? '未作答' : item.is_correct ? '答对' : '答错' }}
              </el-tag></div></template>
            <div class="review-body"><section class="review-question"><b>完整题目：</b><p>{{ item.stem }}</p>
              <ol v-if="item.options.length"><li v-for="option in item.options" :key="option.key"><strong>{{ option.key }}.</strong> {{ option.text }}</li></ol></section>
              <p><b>你的答案：</b>{{ answerText(item, item.selected_options) }}</p>
              <p><b>正确答案：</b>{{ answerText(item, item.correct_answer) }}</p><p><b>解析：</b>{{ item.explanation }}</p>
              <p><b>主要知识点：</b>{{ item.primary_node.historical_node_name }}</p>
              <div class="source-block"><b>课程资料来源</b><p v-if="!item.source_refs.length">该历史题目未保留可展示的来源片段。</p>
                <ul v-else><li v-for="source in item.source_refs" :key="`${source.material_id}-${source.source_reference}`">
                  {{ source.material_title || '历史资料' }} · {{ source.source_reference }}
                  <span v-if="!source.is_accessible" class="unavailable">（原始资料当前不可访问）</span>
                  <small v-if="source.excerpt">{{ source.excerpt }}</small>
                </li></ul></div></div>
          </el-collapse-item>
        </el-collapse>
      </section>
      <el-dialog v-model="knowledgeDialogOpen" title="完整知识点表现" width="min(920px, 94vw)" destroy-on-close>
        <p class="knowledge-dialog-note">以下均为本次固定试卷的观察结果。长期掌握度未随本报告加载时统一显示为“暂无充分证据”。</p>
        <div class="performance-list knowledge-detail-list">
          <article v-for="node in report.knowledge_performance" :key="node.historical_node_id" class="performance-card">
            <div class="performance-top"><div><h3>{{ node.historical_node_name }}</h3>
              <p>本次：{{ node.correct_count }} / {{ node.question_count }} 题正确 · {{ node.unanswered_count }} 道未作答</p></div>
              <el-tag :type="statusType[node.preliminary_status]" effect="light">{{ statusLabel[node.preliminary_status] }}</el-tag></div>
            <el-progress v-if="node.accuracy !== null" :percentage="Math.round(node.accuracy * 100)" :show-text="false" />
            <p class="mastery-unavailable">长期掌握度：暂无充分证据</p>
            <p v-if="node.evidence_status === 'limited_evidence'" class="evidence-note">证据有限：本次只有 {{ node.question_count }} 道关联题，暂不判断整体掌握程度。</p>
            <el-button text size="small" :disabled="!node.map_available" @click="openKnowledgeMap(node)">
              {{ node.map_available ? '在知识地图中查看' : '该知识点已不在当前地图中' }}
            </el-button>
          </article>
        </div>
      </el-dialog>
    </template>
  </main>
</template>

<style scoped>
.report-page { width: 100%; min-width: 0; max-width: 1120px; margin: 0 auto; padding: 28px 28px 64px; box-sizing: border-box; color: var(--lp-text-primary, #243142); }
.back-link { margin-bottom: 12px; }.report-header,.section-heading,.performance-top { display:flex; justify-content:space-between; gap:24px; align-items:flex-start; }
.report-header > div,.section-heading > div,.performance-top > div { min-width:0; }
.report-header { padding: 28px 0 24px; border-bottom: 1px solid var(--el-border-color-lighter); }.report-header h1 { margin: 4px 0 10px; font-size: 30px; }.report-header p { color: var(--lp-text-secondary, #667085); margin:0; }
.eyebrow { color:var(--el-color-primary); font-size:13px; font-weight:700; letter-spacing:.06em; }
.overview-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin:24px 0; }
.overview-grid article,.performance-card { border:1px solid var(--el-border-color-lighter); border-radius:12px; background:#fff; }
.overview-grid article { display:grid; min-width:0; gap:8px; padding:18px; }
.overview-grid span,.policy-note { color:var(--lp-text-secondary,#667085); font-size:13px; }
.overview-grid strong { font-size:23px; line-height:1.2; font-variant-numeric:tabular-nums; overflow-wrap:anywhere; }
.content-section { min-width:0; max-width:100%; margin-top:40px; }
.section-heading h2 { margin:4px 0; }
.section-intro,.evidence-note { color:var(--lp-text-secondary,#667085); font-size:14px; }
.attention-list { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin-top:16px; }
.attention-card { min-width:0; padding:16px; border:1px solid var(--el-border-color-lighter); border-radius:12px; background:#fff; }
.attention-card h3,.attention-card p { overflow-wrap:anywhere; }
.attention-card h3 { margin:0 0 5px; }
.attention-card p { margin:0; color:var(--lp-text-secondary,#667085); font-size:13px; }
.knowledge-empty { padding:18px; border:1px dashed var(--el-border-color); border-radius:12px; color:var(--lp-text-secondary,#667085); text-align:center; }
.knowledge-dialog-note,.mastery-unavailable { color:var(--lp-text-secondary,#667085); font-size:13px; }
.knowledge-detail-list { max-height:62vh; padding-right:4px; overflow-y:auto; }
.performance-list { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }
.performance-card { min-width:0; padding:18px; }
.performance-card h3 { margin:0 0 4px; overflow-wrap:anywhere; }
.performance-card p { margin:0 0 14px; overflow-wrap:anywhere; }
.review-list { min-width:0; max-width:100%; border-top:1px solid var(--el-border-color-lighter); }
.review-list :deep(.el-collapse-item__header) { min-width:0; height:auto; min-height:48px; padding:8px 0; line-height:1.5; }
.review-list :deep(.el-collapse-item__content),.review-list :deep(.el-collapse-item__wrap) { min-width:0; max-width:100%; }
.review-heading { display:grid; min-width:0; width:100%; grid-template-columns:minmax(0,1fr) auto; align-items:start; gap:10px; padding-right:10px; }
.review-title { display:-webkit-box; min-width:0; max-width:100%; overflow:hidden; -webkit-box-orient:vertical; -webkit-line-clamp:3; white-space:pre-wrap; overflow-wrap:anywhere; }
.review-body { min-width:0; max-width:850px; line-height:1.7; }
.review-body p,.review-body li,.source-block small { min-width:0; max-width:100%; white-space:pre-wrap; overflow-wrap:anywhere; }
.review-question { padding:12px 14px; border-radius:8px; background:var(--lp-surface-subtle,#f7f9fc); }
.review-question p { margin:6px 0 10px; color:var(--lp-ink); font-weight:600; }
.review-question ol { margin:0; padding-left:24px; }
.review-body pre { max-width:100%; overflow-x:auto; white-space:pre; }
.review-body code { overflow-wrap:anywhere; }
.source-block { min-width:0; padding-left:12px; margin-top:16px; border-left:3px solid var(--el-color-primary-light-5); }
.source-block ul { min-width:0; padding-left:18px; }
.source-block small { display:block; color:var(--lp-text-secondary,#667085); }
.unavailable { color:var(--el-color-warning); }
.state-panel { max-width:640px; margin:70px auto; padding:28px; }
.error-panel { text-align:center; }
@media (max-width:800px) { .overview-grid { grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }.overview-grid article { gap:6px; padding:14px 16px; }.attention-list,.performance-list { grid-template-columns:1fr; }.report-header,.section-heading { flex-direction:column; }.report-page { padding:20px 16px 48px; } }
@media (max-width:420px) { .review-heading { grid-template-columns:minmax(0,1fr); }.review-heading .el-tag { width:max-content; }.review-list :deep(.el-collapse-item__arrow) { margin-left:8px; } }
</style>
