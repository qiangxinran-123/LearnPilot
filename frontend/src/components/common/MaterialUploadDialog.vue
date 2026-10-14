<script setup lang="ts">
import { computed, ref } from 'vue';
import { DocumentAdd, UploadFilled } from '@element-plus/icons-vue';
import { normalizeApiError } from '@/services/http';
import { uploadMaterial } from '@/services/materials';
import type { Material } from '@/types/course';

const props = defineProps<{ modelValue: boolean; courseId: number }>();
const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  complete: [material: Material];
}>();
const selectedFile = ref<File | null>(null);
const input = ref<HTMLInputElement | null>(null);
const state = ref<'idle' | 'uploading' | 'success' | 'error'>('idle');
const message = ref('');
const isBusy = computed(() => state.value === 'uploading');
const acceptedExtensions = ['.txt', '.md', '.pdf', '.docx'];
const maxBytes = 20 * 1024 * 1024;
function reset(): void {
  selectedFile.value = null;
  state.value = 'idle';
  message.value = '';
  if (input.value) input.value.value = '';
}
function close(): void {
  if (!isBusy.value) {
    reset();
    emit('update:modelValue', false);
  }
}
function chooseFile(): void {
  input.value?.click();
}
function applyFile(file: File | undefined): void {
  if (!file) return;
  const extension = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`;
  if (!acceptedExtensions.includes(extension)) {
    selectedFile.value = null;
    message.value = '仅支持 TXT、MD、PDF 和 DOCX 文件。';
    state.value = 'error';
    return;
  }
  if (file.size === 0) {
    selectedFile.value = null;
    message.value = '不能上传空文件。';
    state.value = 'error';
    return;
  }
  if (file.size > maxBytes) {
    selectedFile.value = null;
    message.value = '文件不能超过 20 MB。';
    state.value = 'error';
    return;
  }
  selectedFile.value = file;
  state.value = 'idle';
  message.value = '';
}
function onInputChange(event: Event): void {
  applyFile((event.target as HTMLInputElement).files?.[0]);
}
function onDrop(event: DragEvent): void {
  event.preventDefault();
  applyFile(event.dataTransfer?.files[0]);
}
async function upload(): Promise<void> {
  if (!selectedFile.value) {
    message.value = '请先选择一个资料文件。';
    state.value = 'error';
    return;
  }
  state.value = 'uploading';
  message.value = '正在上传并解析资料…';
  try {
    const material = await uploadMaterial(props.courseId, selectedFile.value);
    state.value = 'success';
    message.value =
      material.extraction_status === 'SUCCESS'
        ? '资料已上传并解析完成。'
        : '文件已保存，但暂时无法读取其中的文本。';
    emit('complete', material);
  } catch (error: unknown) {
    state.value = 'error';
    message.value = normalizeApiError(error).message;
  }
}
</script>
<template>
  <el-dialog
    :model-value="modelValue"
    title="上传课程资料"
    width="min(560px, calc(100vw - 32px))"
    :close-on-click-modal="false"
    @close="close"
  >
    <section class="upload-dialog">
      <input
        ref="input"
        class="visually-hidden"
        type="file"
        accept=".txt,.md,.pdf,.docx"
        @change="onInputChange"
      />
      <button
        class="upload-dropzone"
        type="button"
        :disabled="isBusy"
        @click="chooseFile"
        @dragover.prevent
        @drop="onDrop"
      >
        <el-icon aria-hidden="true"><UploadFilled /></el-icon
        ><strong>{{ selectedFile ? selectedFile.name : '点击选择或拖拽资料到这里' }}</strong
        ><span>支持 TXT、MD、PDF、DOCX，单个文件不超过 20 MB</span>
      </button>
      <div v-if="selectedFile" class="upload-file-row">
        <el-icon aria-hidden="true"><DocumentAdd /></el-icon><span>{{ selectedFile.name }}</span
        ><small>{{ Math.ceil(selectedFile.size / 1024) }} KB</small>
      </div>
      <p v-if="message" :class="['upload-message', `upload-message--${state}`]" role="status">
        {{ message }}
      </p>
    </section>
    <template #footer
      ><el-button :disabled="isBusy" @click="close">{{
        state === 'success' ? '完成' : '取消'
      }}</el-button
      ><el-button
        type="primary"
        :loading="isBusy"
        :disabled="!selectedFile || state === 'success'"
        @click="upload"
        >{{ isBusy ? '正在上传' : '上传并解析' }}</el-button
      ></template
    >
  </el-dialog>
</template>
