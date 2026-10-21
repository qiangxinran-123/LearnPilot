<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  ArrowLeft,
  Delete,
  Document,
  EditPen,
  FolderAdd,
  Plus,
  UploadFilled,
} from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';

import CourseFormDialog from '@/components/common/CourseFormDialog.vue';
import MaterialUploadDialog from '@/components/common/MaterialUploadDialog.vue';
import CourseOverview from '@/components/knowledge/CourseOverview.vue';
import { presentBuildStatus } from '@/components/knowledge/buildStatus';
import ErrorState from '@/components/feedback/ErrorState.vue';
import LoadingBlock from '@/components/feedback/LoadingBlock.vue';
import { useCourseKnowledgeWorkspace } from '@/composables/useCourseKnowledgeWorkspace';
import { deleteCourse, fetchCourse, updateCourse } from '@/services/courses';
import { normalizeApiError } from '@/services/http';
import { fetchMaterials } from '@/services/materials';
import type { CourseInput, CourseSummary, Material } from '@/types/course';

const KnowledgeStructurePanel = defineAsyncComponent(
  () => import('@/components/knowledge/KnowledgeStructurePanel.vue'),
);

const route = useRoute();
const router = useRouter();
const courseId = computed(() => Number(route.params.courseId));
const course = ref<CourseSummary | null>(null);
const materials = ref<Material[]>([]);
const state = ref<'loading' | 'ready' | 'error'>('loading');
const errorMessage = ref('');
const isEditDialogOpen = ref(false);
const isUploadDialogOpen = ref(false);
const isSavingCourse = ref(false);
const isDeletingCourse = ref(false);
const overview = ref<InstanceType<typeof CourseOverview>>();
const activeTab = computed<'overview' | 'materials' | 'knowledge-structure'>({
  get() {
    return route.query.tab === 'materials' || route.query.tab === 'knowledge-structure'
      ? route.query.tab
      : 'overview';
  },
  set(tab) {
    void router.push({
      name: 'course-detail',
      params: { courseId: courseId.value },
      query: tab === 'overview' ? {} : { tab },
    });
  },
});
const hasValidCourseId = computed(() => Number.isInteger(courseId.value) && courseId.value > 0);
const knowledge = useCourseKnowledgeWorkspace(courseId);
const buildPresentation = computed(() =>
  knowledge.status.value ? presentBuildStatus(knowledge.status.value) : null,
);
let courseRequest = 0;

function materialStatusLabel(material: Material): string {
  const labels: Record<string, string> = {
    SUCCESS: '已完成',
    EMPTY_CONTENT: '内容为空',
    DECODE_ERROR: '无法读取文本',
    PARSE_FAILED: '解析失败',
    UNSUPPORTED_FORMAT: '暂不支持',
    NOT_REQUESTED: '等待解析',
    LEGACY_CONTENT_PARTIAL: '旧版内容不完整',
    LEGACY_CONTENT_UNAVAILABLE: '旧版内容未保存',
  };
  return labels[material.extraction_status] ?? material.extraction_status;
}
function formatBytes(value: number): string {
  return value < 1024 ? `${value} B` : `${Math.ceil(value / 1024)} KB`;
}
function formatDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? null
    : new Intl.DateTimeFormat('zh-CN', {
        year: 'numeric',
        month: 'numeric',
        day: 'numeric',
      }).format(date);
}
async function loadCourse(): Promise<void> {
  const request = ++courseRequest;
  const requestedCourseId = courseId.value;
  if (!hasValidCourseId.value) {
    errorMessage.value = '课程地址无效。';
    state.value = 'error';
    return;
  }
  state.value = 'loading';
  errorMessage.value = '';
  try {
    const [courseResponse, materialResponse] = await Promise.all([
      fetchCourse(requestedCourseId),
      fetchMaterials(requestedCourseId),
    ]);
    if (request !== courseRequest || requestedCourseId !== courseId.value) return;
    course.value = courseResponse;
    materials.value = materialResponse.materials;
    state.value = 'ready';
  } catch (error: unknown) {
    if (request !== courseRequest || requestedCourseId !== courseId.value) return;
    state.value = 'error';
    errorMessage.value = normalizeApiError(error).message;
  }
}
async function saveCourse(payload: CourseInput): Promise<void> {
  if (!course.value) return;
  isSavingCourse.value = true;
  try {
    course.value = await updateCourse(course.value.id, payload);
    isEditDialogOpen.value = false;
    ElMessage.success('课程信息已保存。');
  } catch (error: unknown) {
    ElMessage.error(normalizeApiError(error).message);
  } finally {
    isSavingCourse.value = false;
  }
}
async function removeCourse(): Promise<void> {
  if (!course.value) return;
  isDeletingCourse.value = true;
  try {
    await deleteCourse(course.value.id);
    ElMessage.success('课程及其资料已删除。');
    await router.push('/courses');
  } catch (error: unknown) {
    ElMessage.error(normalizeApiError(error).message);
  } finally {
    isDeletingCourse.value = false;
  }
}
function handleMaterialUploaded(material: Material): void {
  const existingIndex = materials.value.findIndex((item) => item.id === material.id);
  if (existingIndex >= 0) materials.value.splice(existingIndex, 1, material);
  else materials.value.push(material);
  isUploadDialogOpen.value = false;
  void knowledge.refreshStatus();
}
function openMaterial(material: Material): void {
  void router.push(`/courses/${courseId.value}/materials/${material.id}`);
}
async function handleBuild(): Promise<void> {
  const accepted = await knowledge.startBuild();
  if (accepted) ElMessage.info('知识结构构建已开始，可稍后返回查看真实进度。');
}
watch(
  () => knowledge.status.value?.completed_at,
  (completedAt, previous) => {
    if (completedAt && completedAt !== previous) overview.value?.refreshList();
  },
);
watch(
  courseId,
  () => {
    courseRequest += 1;
    course.value = null;
    materials.value = [];
    void loadCourse();
  },
  { immediate: true },
);
</script>

<template>
  <section class="page-view course-workspace">
    <button class="back-link" type="button" @click="router.push('/courses')">
      <el-icon aria-hidden="true"><ArrowLeft /></el-icon>返回课程
    </button>
    <LoadingBlock v-if="state === 'loading'" />
    <ErrorState
      v-else-if="state === 'error'"
      title="课程加载失败"
      :message="errorMessage"
      @retry="loadCourse"
    />
    <template v-else-if="course">
      <header class="course-workspace__header">
        <div>
          <p v-if="course.category" class="eyebrow">{{ course.category }}</p>
          <h1>{{ course.name }}</h1>
          <p v-if="course.description">{{ course.description }}</p>
          <p v-if="course.learning_goal" class="course-workspace__goal">
            学习目标：{{ course.learning_goal }}
          </p>
          <p v-if="formatDate(course.target_date)" class="course-workspace__date">
            目标日期：{{ formatDate(course.target_date) }}
          </p>
          <p
            v-if="buildPresentation"
            class="course-workspace__build-label"
            :class="`course-workspace__build-label--${buildPresentation.tone}`"
            role="status"
          >
            {{ buildPresentation.title }}
          </p>
        </div>
        <div class="course-workspace__actions">
          <el-button plain @click="isEditDialogOpen = true"
            ><el-icon><EditPen /></el-icon>编辑课程</el-button
          >
          <el-popconfirm
            width="312"
            title="删除课程将同时删除课程下的资料记录和相关本地文件，此操作无法撤销。"
            confirm-button-text="确认删除"
            cancel-button-text="取消"
            @confirm="removeCourse"
          >
            <template #reference
              ><el-button type="danger" plain :loading="isDeletingCourse"
                ><el-icon><Delete /></el-icon>删除课程</el-button
              ></template
            >
          </el-popconfirm>
        </div>
      </header>

      <el-tabs v-model="activeTab" class="course-workspace__tabs">
        <el-tab-pane label="学习概览" name="overview">
          <CourseOverview
            ref="overview"
            :course-id="courseId"
            :materials="materials"
            :status="knowledge.status.value"
            :status-state="knowledge.statusState.value"
            :status-error="knowledge.statusError.value"
            :build-error="knowledge.buildError.value"
            :is-running="knowledge.isRunning.value"
            @materials="activeTab = 'materials'"
            @structure="activeTab = 'knowledge-structure'"
            @upload="isUploadDialogOpen = true"
            @build="handleBuild"
          />
        </el-tab-pane>
        <el-tab-pane label="课程资料" name="materials" lazy>
          <section class="materials-section" aria-labelledby="materials-heading">
            <div class="section-heading">
              <div>
                <h2 id="materials-heading">课程资料</h2>
                <p>上传后会安全存储并解析文本；AI 工具只基于当前资料生成结果。</p>
              </div>
              <el-button type="primary" @click="isUploadDialogOpen = true"
                ><el-icon><UploadFilled /></el-icon>上传资料</el-button
              >
            </div>
            <section v-if="materials.length" class="material-list" aria-label="课程资料列表">
              <article v-for="material in materials" :key="material.id" class="material-row">
                <div class="material-row__icon" aria-hidden="true">
                  <el-icon><Document /></el-icon>
                </div>
                <div class="material-row__content">
                  <h3>{{ material.title }}</h3>
                  <p>
                    {{ material.original_filename || material.filename || '未命名资料'
                    }}<span v-if="material.size_bytes">
                      · {{ formatBytes(material.size_bytes) }}</span
                    ><span v-if="formatDate(material.created_at)">
                      · {{ formatDate(material.created_at) }}</span
                    >
                  </p>
                  <p v-if="material.extraction_status === 'SUCCESS'" class="material-row__tools">
                    打开资料，可生成摘要、制作学习卡片，并针对内容提问。
                  </p>
                </div>
                <el-tag
                  :type="
                    material.extraction_status === 'SUCCESS'
                      ? 'success'
                      : material.extraction_status === 'PARSE_FAILED'
                        ? 'danger'
                        : 'info'
                  "
                  effect="plain"
                  >{{ materialStatusLabel(material) }}</el-tag
                >
                <el-button plain @click="openMaterial(material)">查看资料与学习工具</el-button>
              </article>
            </section>
            <section v-else class="materials-empty">
              <div class="materials-empty__icon" aria-hidden="true">
                <el-icon><FolderAdd /></el-icon>
              </div>
              <div>
                <h3>还没有课程资料</h3>
                <p>上传课程讲义、教材或笔记后，LearnPilot 可以帮助你整理和理解学习内容。</p>
              </div>
              <el-button type="primary" @click="isUploadDialogOpen = true"
                ><el-icon><Plus /></el-icon>上传资料</el-button
              >
            </section>
          </section>
        </el-tab-pane>
        <el-tab-pane label="知识结构" name="knowledge-structure" lazy>
          <KnowledgeStructurePanel
            v-if="activeTab === 'knowledge-structure'"
            :course-id="courseId"
            :materials="materials"
            :model="knowledge.model.value"
            :model-state="knowledge.modelState.value"
            :model-error="knowledge.modelError.value"
            :status="knowledge.status.value"
            :is-running="knowledge.isRunning.value"
            @retry="knowledge.refreshModel()"
            @build="handleBuild"
          />
        </el-tab-pane>
      </el-tabs>
    </template>
    <CourseFormDialog
      v-model="isEditDialogOpen"
      :course="course"
      :submitting="isSavingCourse"
      @submit="saveCourse"
    />
    <MaterialUploadDialog
      v-model="isUploadDialogOpen"
      :course-id="courseId"
      @complete="handleMaterialUploaded"
    />
  </section>
</template>

<style scoped>
.course-workspace__build-label {
  display: inline-flex;
  margin-top: 1rem !important;
  padding: 0.28rem 0.65rem;
  border: 1px solid #d8e4f2;
  border-radius: 999px;
  color: #36597d !important;
  background: #f4f8fd;
  font-size: 0.76rem;
  font-weight: 650;
}
.course-workspace__build-label--success {
  border-color: #cde8d6;
  color: #287548 !important;
  background: #f1fbf5;
}
.course-workspace__build-label--warning {
  border-color: #ebdfbe;
  color: #8b681d !important;
  background: #fffbef;
}
.course-workspace__build-label--error {
  border-color: #edcfca;
  color: #a44239 !important;
  background: #fff6f4;
}
.course-workspace__build-label--active {
  border-color: #bcd5f4;
  color: #285da3 !important;
  background: #edf5ff;
}
.course-workspace__tabs {
  margin-top: 1rem;
  padding: 0.25rem 1.25rem 1.25rem;
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-lg);
  background: var(--lp-surface);
  box-shadow: var(--lp-shadow-sm);
}
.course-workspace__tabs :deep(.el-tabs__header) {
  margin-bottom: 0.9rem;
}
.course-workspace__tabs :deep(.el-tabs__item) {
  height: 47px;
  font-weight: 600;
}
@media (max-width: 767px) {
  .course-workspace__tabs {
    padding: 0.2rem 0.8rem 1rem;
  }
  .course-workspace__tabs :deep(.el-tabs__item) {
    padding: 0 0.55rem;
    font-size: 0.82rem;
  }
}
</style>
