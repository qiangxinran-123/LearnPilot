import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it } from 'vitest';

import CourseCard from '@/components/common/CourseCard.vue';

async function mountCard() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/courses', component: { template: '<div />' } },
      { path: '/courses/:courseId', name: 'course-detail', component: { template: '<div />' } },
    ],
  });
  await router.push('/courses');
  await router.isReady();

  return {
    router,
    wrapper: mount(CourseCard, {
      props: {
        course: {
          id: 7,
          name: '线性代数',
          description: '向量、矩阵与线性变换。',
          material_count: 2,
        },
      },
      global: { plugins: [router] },
    }),
  };
}

describe('CourseCard', () => {
  it('uses one semantic course link for the title, content, empty space, and entry hint', async () => {
    const { wrapper } = await mountCard();
    const link = wrapper.get('.course-card__primary-link');

    expect(link.element.tagName).toBe('A');
    expect(link.attributes('href')).toBe('/courses/7');
    expect(link.text()).toContain('线性代数');
    expect(link.text()).toContain('进入课程');
    expect(link.find('.course-card__content').exists()).toBe(true);
    expect(link.find('.course-card__footer').exists()).toBe(true);
  });

  it('navigates to the matching course when the card link is clicked', async () => {
    const { router, wrapper } = await mountCard();

    await wrapper.get('.course-card__primary-link').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe('/courses/7');
  });
});
