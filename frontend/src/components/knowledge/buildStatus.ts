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
        title: '知识结构构建中',
        detail: status.stage ? stageLabels[status.stage] : '正在处理课程资料',
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
            title: '尚未生成知识结构',
            detail: '当前没有可展示的正式知识点。',
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
        detail: status.error_message || '原有数据未被当作成功结果，请检查后重试。',
        tone: 'error',
        action: status.can_build ? '重试生成' : null,
      };
    case 'update_failed':
      return {
        title: '最近一次更新失败',
        detail: status.error_message || '旧版知识结构仍可使用，可安全重试更新。',
        tone: 'error',
        action: status.can_build ? '重试更新' : null,
      };
  }
}
