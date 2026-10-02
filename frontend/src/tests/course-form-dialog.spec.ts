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
  template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
});
const ButtonStub = defineComponent({
  props: ['disabled'],
  template: '<button :disabled="disabled" type="button" @click="$emit(\'click\')"><slot /></button>',
});

function mountDialog() {
  return mount(CourseFormDialog, {
    props: { modelValue: true },
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

  it('emits a trimmed, typed course payload', async () => {
    const wrapper = mountDialog();
    const inputs = wrapper.findAll('input');

    await inputs[0]!.setValue('  计算机系统基础  ');
    await inputs[1]!.setValue('计算机科学');
    await inputs[2]!.setValue('缓存与虚拟内存。');
    await inputs[3]!.setValue('理解系统层次结构。');
    await inputs[4]!.setValue('2026-10-01');
    await wrapper.get('form').trigger('submit');

    expect(wrapper.emitted('submit')).toEqual([
      [
        {
          name: '计算机系统基础',
          category: '计算机科学',
          description: '缓存与虚拟内存。',
          learning_goal: '理解系统层次结构。',
          target_date: '2026-10-01',
        },
      ],
    ]);
  });
});
