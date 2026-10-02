import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';
import AppLayout from '@/layouts/AppLayout.vue';
export const productRoutes: RouteRecordRaw[] = [
  { path: '/dashboard', name: 'dashboard', component: () => import('@/views/DashboardView.vue'), meta: { title: '首页', navLabel: '首页' } },
  { path: '/courses', name: 'courses', component: () => import('@/views/CoursesView.vue'), meta: { title: '课程', navLabel: '课程' } },
  { path: '/courses/:courseId', name: 'course-detail', component: () => import('@/views/CourseDetailView.vue'), meta: { title: '课程详情', navLabel: '课程' } },
  { path: '/courses/:courseId/materials/:materialId', name: 'material-detail', component: () => import('@/views/MaterialDetailView.vue'), meta: { title: '资料详情', navLabel: '课程' } },
  { path: '/diagnose', name: 'diagnose', component: () => import('@/views/DiagnoseView.vue'), meta: { title: '诊断', navLabel: '诊断' } },
  { path: '/learn', name: 'learn', component: () => import('@/views/LearnView.vue'), meta: { title: '学习', navLabel: '学习' } },
  { path: '/progress', name: 'progress', component: () => import('@/views/ProgressView.vue'), meta: { title: '进展', navLabel: '进展' } },
];
export const routes: RouteRecordRaw[] = [{ path: '/', component: AppLayout, children: [{ path: '', redirect: '/dashboard' }, ...productRoutes, { path: ':pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue'), meta: { title: '页面未找到' } }] }];
export const router = createRouter({ history: createWebHistory(), routes, scrollBehavior: () => ({ top: 0 }) });
router.afterEach((to) => { document.title = `${to.meta.title} · LearnPilot`; });
