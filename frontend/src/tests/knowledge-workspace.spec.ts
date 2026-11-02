import { defineComponent, toRef } from 'vue';
import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useCourseKnowledgeWorkspace } from '@/composables/useCourseKnowledgeWorkspace';
import { fetchKnowledgeBuildStatus, fetchKnowledgeModel, startKnowledgeBuild } from '@/services/knowledge';
import { ApiError } from '@/services/http';
import type { KnowledgeBuildStatus } from '@/types/knowledge';

vi.mock('@/services/knowledge', () => ({
  fetchKnowledgeBuildStatus: vi.fn(), fetchKnowledgeModel: vi.fn(), startKnowledgeBuild: vi.fn(),
}));

function status(courseId: number): KnowledgeBuildStatus {
  return { course_id: courseId, state: 'not_built', stage: null, job_id: null,
    material_count: 1, ready_material_count: 1, synced_material_count: 0,
    pending_sync_material_count: 1, pending_parse_material_count: 0, failed_material_count: 0,
    last_added_node_count: 0, last_reused_node_count: 0, node_count: 0, contains_edge_count: 0,
    prerequisite_edge_count: 0, needs_update: false, can_build: true, has_model: false,
    error_code: null, error_message: null, started_at: null, completed_at: null };
}
const Harness = defineComponent({
  props: { courseId: { type: Number, required: true } },
  setup(props) { return { workspace: useCourseKnowledgeWorkspace(toRef(props, 'courseId')) }; },
  template: '<div />',
});

describe('knowledge build workspace', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(fetchKnowledgeBuildStatus).mockImplementation(async (id) => status(id));
    vi.mocked(fetchKnowledgeModel).mockImplementation(async (id) => ({ course_id: id, nodes: [], edges: [] }));
  });

  it('prevents duplicate starts and ignores a previous course response', async () => {
    let finish!: (value: Awaited<ReturnType<typeof startKnowledgeBuild>>) => void;
    vi.mocked(startKnowledgeBuild).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const wrapper = mount(Harness, { props: { courseId: 1 } });
    await flushPromises();
    const first = wrapper.vm.workspace.startBuild();
    expect(wrapper.vm.workspace.isRunning.value).toBe(true);
    expect(await wrapper.vm.workspace.startBuild()).toBe(false);
    expect(startKnowledgeBuild).toHaveBeenCalledTimes(1);
    await wrapper.setProps({ courseId: 2 });
    await flushPromises();
    finish({ job_id: 9, status: 'running', stage: 'queued', reused: false });
    expect(await first).toBe(false);
    expect(wrapper.vm.workspace.status.value?.course_id).toBe(2);
    expect(wrapper.vm.workspace.isRunning.value).toBe(false);
    wrapper.unmount();
  });

  it('restores interaction and displays a timeout without discarding the current model', async () => {
    vi.mocked(startKnowledgeBuild).mockRejectedValue(new ApiError('请求超时，请稍后重试。', { code: 'REQUEST_TIMEOUT' }));
    const wrapper = mount(Harness, { props: { courseId: 1 } });
    await flushPromises();
    expect(await wrapper.vm.workspace.startBuild()).toBe(false);
    expect(wrapper.vm.workspace.isRunning.value).toBe(false);
    expect(wrapper.vm.workspace.buildError.value).toContain('请求超时');
    expect(wrapper.vm.workspace.model.value?.course_id).toBe(1);
    wrapper.unmount();
  });
});
