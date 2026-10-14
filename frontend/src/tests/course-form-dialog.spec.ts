import { defineComponent } from 'vue';
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import CourseFormDialog from '@/components/common/CourseFormDialog.vue';

const DialogStub = defineComponent({
  props: ['modelValue'],
  template: '<section v-if="modelValue"><slot /><slot name="footer" /></section>',
});
const InputStub = defineComponent({
  props: ['modelValue'],
  emits: ['update:modelValue'],
  template:
    '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
});
const ButtonStub = defineComponent({
  props: ['disabled'],
  template:
    '<button :disabled="disabled" type="button" @click="$emit(\'click\')"><slot /></button>',
});

function mountDialog(
  course?: {
    id: number;
    name: string;
    description: string;
    category?: string | null;
    learning_goal?: string | null;
    target_date?: string | null;
  },
  submitting = false,
) {
  return mount(CourseFormDialog, {
    props: { modelValue: true, course, submitting },
    global: {
      stubs: {
        'el-dialog': DialogStub,
        'el-input': InputStub,
        'el-date-picker': InputStub,
        'el-button': ButtonStub,
      },
    },
  });
}

describe('CourseFormDialog', () => {
  it('validates a required course name before submission', async () => {
    const wrapper = mountDialog();

    await wrapper.get('form').trigger('submit');

    expect(wrapper.text()).toContain('请输入课程名称。');
    expect(wrapper.emitted('submit')).toBeUndefined();
  });

  it('creates a course with only a trimmed name', async () => {
    const wrapper = mountDialog();
    const inputs = wrapper.findAll('input');

    await inputs[0]!.setValue('  计算机系统基础  ');
    await wrapper.get('form').trigger('submit');

    expect(wrapper.text()).not.toContain('课程简介');
    expect(wrapper.text()).not.toContain('课程备注');
    expect(wrapper.emitted('submit')).toEqual([
      [
        {
          name: '计算机系统基础',
        },
      ],
    ]);
  });

  it('edits an optional note without clearing legacy course fields', async () => {
    const wrapper = mountDialog({
      id: 7,
      name: '线性代数',
      description: '原有备注',
      category: '数学',
      learning_goal: '掌握线性变换',
      target_date: '2026-10-01',
    });
    const inputs = wrapper.findAll('input');

    expect(wrapper.text()).toContain('课程备注（选填）');
    await inputs[0]!.setValue('  高等代数  ');
    await inputs[1]!.setValue('  更新后的备注  ');
    await wrapper.get('form').trigger('submit');

    expect(wrapper.emitted('submit')).toEqual([
      [
        {
          name: '高等代数',
          description: '更新后的备注',
          category: '数学',
          learning_goal: '掌握线性变换',
          target_date: '2026-10-01',
        },
      ],
    ]);
  });

  it('preserves an explicit empty note so the user can clear it', async () => {
    const wrapper = mountDialog({ id: 7, name: '线性代数', description: '原有备注' });
    const inputs = wrapper.findAll('input');

    await inputs[1]!.setValue('');
    await wrapper.get('form').trigger('submit');

    expect(wrapper.emitted('submit')).toEqual([
      [
        {
          name: '线性代数',
          description: '',
          category: null,
          learning_goal: null,
          target_date: null,
        },
      ],
    ]);
  });

  it('does not emit a second submission while the parent request is pending', async () => {
    const wrapper = mountDialog(undefined, true);
    await wrapper.find('input').setValue('离散数学');

    await wrapper.get('form').trigger('submit');

    expect(wrapper.emitted('submit')).toBeUndefined();
  });
});
