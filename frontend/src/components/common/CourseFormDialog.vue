<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { CourseInput, CourseSummary } from '@/types/course';

const props = defineProps<{
  modelValue: boolean;
  course?: CourseSummary | null;
  submitting?: boolean;
}>();
const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  submit: [payload: CourseInput];
}>();
const form = ref<CourseInput>({
  name: '',
  description: '',
  category: null,
  learning_goal: null,
  target_date: null,
});
const validationMessage = ref('');
const isEditing = computed(() => Boolean(props.course));
const dialogTitle = computed(() => (isEditing.value ? '编辑课程' : '创建课程'));
function setForm(course: CourseSummary | null | undefined): void {
  form.value = {
    name: course?.name ?? '',
    description: course?.description ?? '',
    category: course?.category ?? course?.semester ?? null,
    learning_goal: course?.learning_goal ?? null,
    target_date: course?.target_date ?? null,
  };
  validationMessage.value = '';
}
watch(
  () => [props.modelValue, props.course] as const,
  ([visible, course]) => {
    if (visible) setForm(course);
  },
  { immediate: true },
);
function close(): void {
  if (!props.submitting) emit('update:modelValue', false);
}
function submit(): void {
  if (props.submitting) return;
  const name = form.value.name.trim();
  if (!name) {
    validationMessage.value = '请输入课程名称。';
    return;
  }
  if (name.length > 100) {
    validationMessage.value = '课程名称不能超过 100 个字符。';
    return;
  }
  if (!isEditing.value) {
    emit('submit', { name });
    return;
  }

  // Retain supplementary legacy fields while this focused editor exposes only a note.
  emit('submit', {
    name,
    description: form.value.description?.trim() || '',
    category: form.value.category?.trim() || null,
    learning_goal: form.value.learning_goal?.trim() || null,
    target_date: form.value.target_date || null,
  });
}
</script>
<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="min(560px, calc(100vw - 32px))"
    :close-on-click-modal="false"
    @close="close"
  >
    <form class="course-form" @submit.prevent="submit">
      <label class="form-field"
        ><span>课程名称 <em>*</em></span
        ><el-input v-model="form.name" maxlength="100" show-word-limit placeholder="例如：线性代数"
      /></label>
      <label v-if="isEditing" class="form-field course-form__note"
        ><span>课程备注（选填）</span
        ><el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          maxlength="2000"
          show-word-limit
          placeholder="记录这门课程的补充信息。"
      /></label>
      <p v-if="validationMessage" class="form-error" role="alert">{{ validationMessage }}</p>
    </form>
    <template #footer
      ><el-button :disabled="submitting" @click="close">取消</el-button
      ><el-button type="primary" :loading="submitting" @click="submit">{{
        isEditing ? '保存修改' : '创建课程'
      }}</el-button></template
    >
  </el-dialog>
</template>

<style scoped>
.course-form__note {
  margin-top: 0.2rem;
}
</style>
