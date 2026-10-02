import { defineComponent } from 'vue';
import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import MaterialUploadDialog from '@/components/common/MaterialUploadDialog.vue';
import { uploadMaterial } from '@/services/materials';
import type { Material } from '@/types/course';

vi.mock('@/services/materials', () => ({
  uploadMaterial: vi.fn(),
}));

const mockedUploadMaterial = vi.mocked(uploadMaterial);

const DialogStub = defineComponent({
  props: ['modelValue'],
  template: '<section v-if="modelValue"><slot /><slot name="footer" /></section>',
});
const ButtonStub = defineComponent({
  props: ['disabled'],
  emits: ['click'],
  template: '<button :disabled="disabled" type="button" @click="$emit(\'click\')"><slot /></button>',
});
const IconStub = defineComponent({ template: '<span><slot /></span>' });

const parsedMaterial: Material = {
  id: 4,
  course_id: 2,
  title: 'lecture',
  type: 'PDF',
  summary: '',
  original_filename: 'lecture.pdf',
  size_bytes: 24,
  storage_status: 'STORED',
  text_preview: '缓存是高速存储器。',
  text_length: 10,
  extracted: true,
  extraction_status: 'SUCCESS',
  page_count: 1,
};

function mountUploadDialog() {
  return mount(MaterialUploadDialog, {
    props: { modelValue: true, courseId: 2 },
    global: {
      stubs: {
        'el-dialog': DialogStub,
        'el-button': ButtonStub,
        'el-icon': IconStub,
      },
    },
  });
}

function selectFile(wrapper: ReturnType<typeof mountUploadDialog>, file: File): Promise<void> {
  const input = wrapper.get('input[type="file"]');
  Object.defineProperty(input.element, 'files', {
    configurable: true,
    value: [file],
  });
  return input.trigger('change');
}

describe('MaterialUploadDialog', () => {
  beforeEach(() => {
    mockedUploadMaterial.mockReset();
  });

  it('rejects unsupported files before any API call', async () => {
    const wrapper = mountUploadDialog();

    await selectFile(wrapper, new File(['image'], 'diagram.png', { type: 'image/png' }));

    expect(wrapper.text()).toContain('仅支持 TXT、MD、PDF 和 DOCX 文件。');
    expect(mockedUploadMaterial).not.toHaveBeenCalled();
  });

  it('shows upload completion after the material API returns a parsed file', async () => {
    mockedUploadMaterial.mockResolvedValue(parsedMaterial);
    const wrapper = mountUploadDialog();

    await selectFile(wrapper, new File(['缓存是高速存储器。'], 'lecture.txt', { type: 'text/plain' }));
    const uploadButton = wrapper.findAll('button').find((button) => button.text().includes('上传并解析'));
    await uploadButton?.trigger('click');
    await flushPromises();

    expect(mockedUploadMaterial).toHaveBeenCalledWith(2, expect.any(File));
    expect(wrapper.text()).toContain('资料已上传并解析完成。');
    expect(wrapper.emitted('complete')?.[0]).toEqual([parsedMaterial]);
  });
});
