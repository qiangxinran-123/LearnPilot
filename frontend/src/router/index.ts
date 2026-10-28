import {
  createRouter,
  createWebHistory,
  type RouteLocationNormalized,
  type RouteLocationResolvedGeneric,
  type RouteRecordRaw,
  type RouterScrollBehavior,
} from 'vue-router';
import AppLayout from '@/layouts/AppLayout.vue';

function sameQueryExceptNodeId(
  to: RouteLocationNormalized['query'],
  from: RouteLocationNormalized['query'],
): boolean {
  const keys = new Set([...Object.keys(to), ...Object.keys(from)]);
  keys.delete('nodeId');
  return [...keys].every((key) => JSON.stringify(to[key]) === JSON.stringify(from[key]));
}

export function isKnowledgeMapFocusChange(
  to: Pick<RouteLocationResolvedGeneric, 'name' | 'params' | 'query'>,
  from: Pick<RouteLocationResolvedGeneric, 'name' | 'params' | 'query'>,
): boolean {
  return (
    to.name === 'course-detail' &&
    from.name === 'course-detail' &&
    String(to.params.courseId) === String(from.params.courseId) &&
    to.query.tab === 'knowledge-structure' &&
    from.query.tab === 'knowledge-structure' &&
    to.query.nodeId !== from.query.nodeId &&
    sameQueryExceptNodeId(to.query, from.query)
  );
}

type ScrollRoute = Pick<RouteLocationResolvedGeneric, 'name' | 'params' | 'query'>;

export const scrollBehavior: (
  to: ScrollRoute,
  from: ScrollRoute,
  savedPosition: Parameters<RouterScrollBehavior>[2],
) => ReturnType<RouterScrollBehavior> = (to, from) =>
  isKnowledgeMapFocusChange(to, from) ? { left: window.scrollX, top: window.scrollY } : { top: 0 };

export const productRoutes: RouteRecordRaw[] = [
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { title: '首页', navLabel: '首页' },
  },
  {
    path: '/courses',
    name: 'courses',
    component: () => import('@/views/CoursesView.vue'),
    meta: { title: '课程', navLabel: '课程' },
  },
  {
    path: '/courses/:courseId',
    name: 'course-detail',
    component: () => import('@/views/CourseDetailView.vue'),
    meta: { title: '课程详情', navLabel: '课程' },
  },
  {
    path: '/courses/:courseId/knowledge/:nodeId',
    name: 'knowledge-detail',
    component: () => import('@/views/KnowledgeDetailView.vue'),
    meta: { title: '知识详情', navLabel: '课程' },
  },
  {
    path: '/courses/:courseId/materials/:materialId',
    name: 'material-detail',
    component: () => import('@/views/MaterialDetailView.vue'),
    meta: { title: '资料详情', navLabel: '课程' },
  },
  {
    path: '/diagnose',
    name: 'diagnose',
    component: () => import('@/views/DiagnoseView.vue'),
    meta: { title: '诊断', navLabel: '诊断' },
  },
  {
    path: '/diagnose/assessments/:assessmentId',
    name: 'diagnostic-assessment',
    component: () => import('@/views/DiagnosticAssessmentView.vue'),
    meta: { title: '诊断答题', navLabel: '诊断' },
  },
  {
    path: '/diagnose/assessments/:assessmentId/result',
    name: 'diagnostic-report',
    component: () => import('@/views/DiagnosticReportView.vue'),
    meta: { title: '诊断报告', navLabel: '诊断' },
  },
  {
    path: '/learn',
    name: 'learn',
    component: () => import('@/views/LearnView.vue'),
    meta: { title: '学习', navLabel: '学习' },
  },
  {
    path: '/learn/sessions/:sessionId',
    name: 'learning-session',
    component: () => import('@/views/LearningSessionView.vue'),
    meta: { title: '学习会话', navLabel: '学习' },
  },
  {
    path: '/progress',
    name: 'progress',
    component: () => import('@/views/ProgressView.vue'),
    meta: { title: '进展', navLabel: '进展' },
  },
];
export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', redirect: '/dashboard' },
      ...productRoutes,
      {
        path: ':pathMatch(.*)*',
        name: 'not-found',
        component: () => import('@/views/NotFoundView.vue'),
        meta: { title: '页面未找到' },
      },
    ],
  },
];
export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior,
});
router.afterEach((to) => {
  document.title = `${to.meta.title} · LearnPilot`;
});
