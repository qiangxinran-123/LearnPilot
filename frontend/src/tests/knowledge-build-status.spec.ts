import { describe, expect, it } from 'vitest';

import { presentBuildStatus } from '@/components/knowledge/buildStatus';
import type { KnowledgeBuildState, KnowledgeBuildStatus } from '@/types/knowledge';

function status(
  state: KnowledgeBuildState,
  overrides: Partial<KnowledgeBuildStatus> = {},
): KnowledgeBuildStatus {
  return {
    course_id: 7,
    state,
    stage: null,
    job_id: null,
    material_count: 1,
    ready_material_count: 1,
    node_count: 0,
    contains_edge_count: 0,
    prerequisite_edge_count: 0,
    needs_update: false,
    can_build: true,
    has_model: false,
    error_code: null,
    error_message: null,
    started_at: null,
    completed_at: null,
    ...overrides,
  };
}

describe('presentBuildStatus', () => {
  it.each([
    ['no_materials', '尚未上传资料', null],
    ['not_ready', '资料尚不能用于构建', null],
    ['not_built', '尚未生成知识结构', '生成课程知识结构'],
    ['running', '知识结构构建中', null],
    ['ready', '知识结构已构建', null],
    ['update_available', '有新资料待更新', '更新知识结构'],
    ['failed', '最近一次构建失败', '重试生成'],
    ['update_failed', '最近一次更新失败', '重试更新'],
  ] as const)('renders the %s business state without invented progress', (state, title, action) => {
    const presentation = presentBuildStatus(
      status(state, { node_count: state === 'ready' || state === 'update_available' ? 3 : 0 }),
    );

    expect(presentation.title).toBe(title);
    expect(presentation.action).toBe(action);
    expect(`${presentation.title} ${presentation.detail}`).not.toMatch(/\d+%|掌握度|学习进度/);
  });

  it('names only the actual running stage, without claiming percentage progress', () => {
    expect(presentBuildStatus(status('running', { stage: 'extracting' })).detail).toBe(
      '正在抽取知识',
    );
    expect(presentBuildStatus(status('running', { stage: 'canonicalizing' })).detail).toBe(
      '正在规范化知识',
    );
    expect(presentBuildStatus(status('running', { stage: 'relationships' })).detail).toBe(
      '正在建立知识关系',
    );
  });

  it('does not claim success for a ready state with zero canonical nodes', () => {
    const presentation = presentBuildStatus(status('ready'));

    expect(presentation.title).toBe('尚未生成知识结构');
    expect(presentation.action).toBe('生成课程知识结构');
  });

  it('states that an update failure preserves the existing model and respects build eligibility', () => {
    const presentation = presentBuildStatus(
      status('update_failed', {
        node_count: 5,
        has_model: true,
        can_build: false,
        error_message: '关系推断失败',
      }),
    );

    expect(presentation.detail).toBe('关系推断失败');
    expect(presentation.action).toBeNull();
    expect(presentation.title).toBe('最近一次更新失败');
  });
});
