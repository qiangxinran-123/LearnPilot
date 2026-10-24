import type {
  LearningTaskType,
  LearningPlanLevel,
  RecommendationAvailabilityStatus,
  RecommendationReasonCode,
} from '@/types/learningPlan';

const reasonLabels: Record<RecommendationReasonCode, string> = {
  knowledge_gap: '当前掌握状态显示这个知识点仍有补强空间。',
  low_mastery: '当前掌握度较低，适合优先巩固。',
  prerequisite_gap: '后续目标受到前置知识影响，建议先学习这里。',
  prerequisite_for_other_nodes: '掌握这个知识点有助于继续学习后续内容。',
  high_course_importance: '该内容在当前课程中的重要程度较高。',
  review_needed: '已有复习风险数据表明现在适合进行巩固。',
  insufficient_evidence: '现有学习依据有限，建议在学习过程中继续确认。',
  neutral_course_importance: '课程重要度暂无独立数据，本次未作倾向性判断。',
  neutral_review_risk: '复习风险暂无独立数据，本次未作倾向性判断。',
  no_eligible_candidate: '当前没有满足推荐条件的知识点。',
  all_mastered: '当前知识点整体掌握良好。',
  invalid_prerequisite_graph: '部分前置关系异常，系统已避免使用相关节点。',
};

const taskTypeLabels: Record<LearningTaskType, string> = {
  concept_review: '概念理解',
  example_walkthrough: '示例分析',
  targeted_practice: '针对性练习',
};

export function recommendationReasonLabel(code: RecommendationReasonCode): string {
  return reasonLabels[code];
}

export function learningTaskTypeLabel(type: LearningTaskType): string {
  return taskTypeLabels[type];
}

export interface PlanLevelPresentation {
  title: string;
  description: string;
  generateLabel: string;
}

const planLevelPresentations: Record<LearningPlanLevel, PlanLevelPresentation> = {
  personalized: {
    title: '个性化学习计划',
    description: '根据你的诊断表现、知识掌握情况和课程知识关系，为你推荐下一步学习内容。',
    generateLabel: '生成个性化计划',
  },
  preliminary: {
    title: '初步学习建议',
    description: '当前诊断证据仍然有限，以下建议将随着后续测评与学习记录逐步完善。',
    generateLabel: '生成初步学习建议',
  },
  foundational: {
    title: '基础学习路线',
    description: '当前尚无充分的个人诊断数据。以下路线根据课程知识结构和前置依赖生成。',
    generateLabel: '生成基础学习路线',
  },
};

export function planLevelPresentation(level: LearningPlanLevel | null): PlanLevelPresentation | null {
  return level ? planLevelPresentations[level] : null;
}

export interface UnavailablePresentation {
  title: string;
  description: string;
  actionLabel?: string;
  actionTo?: string;
}

export function unavailablePresentation(
  status: RecommendationAvailabilityStatus | null,
  courseId: number | null,
  businessCode: string | null,
): UnavailablePresentation {
  if (businessCode === 'KNOWLEDGE_MODEL_NOT_FOUND' || status === 'invalid_context') {
    return {
      title: '课程知识结构尚未准备好',
      description: '当前课程还没有可用于制定计划的知识结构，请先完成课程准备。',
      actionLabel: courseId ? '前往课程准备' : undefined,
      actionTo: courseId ? `/courses/${courseId}?tab=knowledge-structure` : undefined,
    };
  }
  if (status === 'needs_initial_diagnostic') {
    return {
      title: '先完成一次学习诊断',
      description: '完成一次学习诊断后，LearnPilot 才能为你制定个性化学习计划。',
      actionLabel: '前往诊断',
      actionTo: courseId ? `/diagnose?courseId=${courseId}` : '/diagnose',
    };
  }
  if (status === 'needs_prerequisite_assessment' || status === 'no_eligible_candidate') {
    return {
      title: '当前学习依据还不充分',
      description: '现有掌握状态或前置知识证据不足，完成诊断后再查看学习建议。',
      actionLabel: '前往诊断',
      actionTo: courseId ? `/diagnose?courseId=${courseId}` : '/diagnose',
    };
  }
  if (status === 'all_mastered') {
    return {
      title: '当前暂无优先补强内容',
      description: '当前暂无需要优先补强的知识点。',
    };
  }
  return {
    title: '暂时没有可执行的学习计划',
    description: '服务端当前没有返回可执行的推荐，请稍后重新查看。',
  };
}
