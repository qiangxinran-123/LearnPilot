import type { KnowledgeBuildStage, KnowledgeBuildStatus } from '@/types/knowledge';

export interface BuildPresentation {
  title: string;
  detail: string;
  tone: 'neutral' | 'active' | 'success' | 'warning' | 'error';
  action: string | null;
}

const stageLabels: Record<KnowledgeBuildStage, string> = {
  queued: '任务已排队',
  extracting: '正在抽取知识',
  canonicalizing: '正在规范化知识',
  relationships: '正在建立知识关系',
};

const LEGACY_CANDIDATE_LIMIT = 'The course exceeds the configured canonicalization candidate limit.';
const inputLimitMessages = new Set([
  'Material exceeds the configured knowledge extraction input limit.',
  'The course exceeds the configured relationship-generation node limit.',
  'Knowledge extraction exceeded the configured candidate limit.',
]);
const LIMIT_MESSAGE = '当前课程资料规模超过单次知识结构构建能力，请缩小课程资料范围后重试。';

/** Do not expose internal English exceptions or stack traces in the build UI. */
export function safeBuildError(message: string | null | undefined, fallback: string): string {
  if (message === LEGACY_CANDIDATE_LIMIT || (message && inputLimitMessages.has(message))) return LIMIT_MESSAGE;
  if (message && message.length <= 160 && /^[\u3400-\u9fff0-9，。！？、；：‘’“”（）《》\s]+$/.test(message)) return message;
  return fallback;
}

export function materialCoverageNote(status: KnowledgeBuildStatus): string {
  const notes: string[] = [];
  if (status.pending_parse_material_count > 0) notes.push(`${status.pending_parse_material_count} 份资料尚未完成解析`);
  if (status.failed_material_count > 0) notes.push(`${status.failed_material_count} 份资料解析失败`);
  return notes.length ? `${notes.join('，')}，未纳入本次知识结构。` : '';
}

export function runningBuildMessage(status: KnowledgeBuildStatus | null): string {
  const action = status?.has_model ? '正在更新课程知识结构，完成后会展示最新结果。' : '正在整理课程知识，首次生成需要分析课程资料。';
  const stage = status?.state === 'running' && status.stage ? `${stageLabels[status.stage]}。 ` : '';
  return `${action} ${stage}资料较多时可能需要更长时间。`;
}

export function presentBuildStatus(status: KnowledgeBuildStatus): BuildPresentation {
  switch (status.state) {
    case 'no_materials':
      return {
        title: '尚未上传资料',
        detail: '先上传课程讲义或笔记，再生成课程知识结构。',
        tone: 'neutral',
        action: null,
      };
    case 'not_ready':
      return {
        title: '资料尚不能用于构建',
        detail: '请确认至少一份资料已成功解析；解析失败的资料不会进入知识构建。',
        tone: 'warning',
        action: null,
      };
    case 'not_built':
      return {
        title: '尚未生成知识结构',
        detail: '课程资料已就绪，可主动生成可追溯的知识点与关系。',
        tone: 'neutral',
        action: '生成课程知识结构',
      };
    case 'running':
      return {
        title: status.has_model ? '正在更新课程知识结构' : '正在整理课程知识',
        detail: runningBuildMessage(status),
        tone: 'active',
        action: null,
      };
    case 'ready':
      return status.node_count > 0
        ? {
            title: '知识结构已构建',
            detail: '当前课程知识点和关系可供浏览。',
            tone: 'success',
            action: null,
          }
        : {
            title: '生成完成但没有知识点',
            detail: '本次构建未产生可展示的正式知识点。',
            tone: 'warning',
            action: status.can_build ? '生成课程知识结构' : null,
          };
    case 'update_available':
      return {
        title: '有新资料待更新',
        detail: '已有知识结构仍可浏览；更新将纳入新增或变更的资料。',
        tone: 'warning',
        action: '更新知识结构',
      };
    case 'failed':
      return {
        title: '最近一次构建失败',
        detail: safeBuildError(status.error_message, '知识结构构建未成功，请检查资料后重试。'),
        tone: 'error',
        action: status.can_build ? '重试生成' : null,
      };
    case 'update_failed':
      return {
        title: '最近一次更新失败',
        detail: `${safeBuildError(status.error_message, '知识结构更新未成功。')} 已有知识结构仍可查看。`,
        tone: 'error',
        action: status.can_build ? '重试更新' : null,
      };
  }
}
