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
const reviewFilter = ref<'attention' | 'all'>('attention');

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
const reviewedQuestions = computed<DiagnosticQuestionReview[]>(() => {
  if (!report.value) return [];
  return reviewFilter.value === 'all'
    ? report.value.question_reviews
    : report.value.question_reviews.filter((item) => !item.is_correct || item.selected_options.length === 0);
});

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
        <div class="section-heading"><div><p class="eyebrow">本次测评观察</p><h2>知识点表现</h2></div>
          <span class="policy-note">规则版本：{{ report.report_policy_version }}</span></div>
        <p class="section-intro">每道题仅计入其历史主知识点；关联题少于 3 道时只展示实际表现，不作整体判断。</p>
        <div class="performance-list">
          <article v-for="node in report.knowledge_performance" :key="node.historical_node_id" class="performance-card">
            <div class="performance-top"><div><h3>{{ node.historical_node_name }}</h3>
              <p>{{ node.correct_count }} / {{ node.question_count }} 正确 · {{ node.unanswered_count }} 道未作答</p></div>
              <el-tag :type="statusType[node.preliminary_status]" effect="light">{{ statusLabel[node.preliminary_status] }}</el-tag></div>
            <el-progress v-if="node.accuracy !== null" :percentage="Math.round(node.accuracy * 100)" :show-text="false" />
            <p v-if="node.evidence_status === 'limited_evidence'" class="evidence-note">证据有限：本次只有 {{ node.question_count }} 道关联题，暂不判断整体掌握程度。</p>
            <el-button text size="small" :disabled="!node.map_available" @click="openKnowledgeMap(node)">
              {{ node.map_available ? '在知识地图中查看' : '该知识点已不在当前地图中' }}
            </el-button>
          </article>
        </div>
      </section>
      <section class="content-section">
        <div class="section-heading"><div><p class="eyebrow">回看固定题目与资料依据</p><h2>错题回顾</h2></div>
          <el-radio-group v-model="reviewFilter" size="small"><el-radio-button value="attention">错题与未作答</el-radio-button><el-radio-button value="all">全部题目</el-radio-button></el-radio-group></div>
        <el-empty v-if="!reviewedQuestions.length" description="本次没有需要回顾的题目。" />
        <el-collapse v-else class="review-list">
          <el-collapse-item v-for="item in reviewedQuestions" :key="item.assessment_question_id" :name="item.assessment_question_id">
            <template #title><span class="review-title">第 {{ item.order_index + 1 }} 题 · {{ item.stem }}</span>
              <el-tag :type="item.selected_options.length === 0 ? 'info' : item.is_correct ? 'success' : 'danger'" size="small">
                {{ item.selected_options.length === 0 ? '未作答' : item.is_correct ? '答对' : '答错' }}
              </el-tag></template>
            <div class="review-body"><p><b>你的答案：</b>{{ answerText(item, item.selected_options) }}</p>
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
    </template>
  </main>
</template>

<style scoped>
.report-page { max-width: 1120px; margin: 0 auto; padding: 28px 28px 64px; color: var(--lp-text-primary, #243142); }
.back-link { margin-bottom: 12px; }.report-header,.section-heading,.performance-top { display:flex; justify-content:space-between; gap:24px; align-items:flex-start; }
.report-header { padding: 28px 0 24px; border-bottom: 1px solid var(--el-border-color-lighter); }.report-header h1 { margin: 4px 0 10px; font-size: 30px; }.report-header p { color: var(--lp-text-secondary, #667085); margin:0; }
.eyebrow { color: var(--el-color-primary); font-size:13px; font-weight:700; letter-spacing:.06em; }.overview-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:24px 0; }.overview-grid article,.performance-card { border:1px solid var(--el-border-color-lighter); border-radius:12px; background:#fff; }.overview-grid article { padding:18px; display:grid; gap:8px; }.overview-grid span,.policy-note { color:var(--lp-text-secondary,#667085); font-size:13px; }.overview-grid strong { font-size:23px; }.content-section { margin-top:40px; }.section-heading h2 { margin:4px 0; }.section-intro,.evidence-note { color:var(--lp-text-secondary,#667085); font-size:14px; }.performance-list { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }.performance-card { padding:18px; }.performance-card h3 { margin:0 0 4px; }.performance-card p { margin:0 0 14px; }.review-list { border-top:1px solid var(--el-border-color-lighter); }.review-title { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; margin-right:12px; }.review-body { line-height:1.7; max-width:850px; }.source-block { border-left:3px solid var(--el-color-primary-light-5); padding-left:12px; margin-top:16px; }.source-block ul { padding-left:18px; }.source-block small { display:block; color:var(--lp-text-secondary,#667085); }.unavailable { color:var(--el-color-warning); }.state-panel { max-width:640px; margin:70px auto; padding:28px; }.error-panel { text-align:center; } @media (max-width: 800px) { .overview-grid,.performance-list { grid-template-columns:1fr; }.report-header,.section-heading { flex-direction:column; }.report-page { padding:20px 16px 48px; } }
</style>
