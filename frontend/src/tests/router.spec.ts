import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it } from 'vitest';

import { isKnowledgeMapFocusChange, routes, scrollBehavior } from '@/router';

const mainPaths = ['/dashboard', '/courses', '/diagnose', '/learn', '/progress'];

describe('product router', () => {
  it('registers and resolves all five primary pages', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes });

    for (const path of mainPaths) {
      await router.push(path);
      expect(router.currentRoute.value.path).toBe(path);
      expect(router.currentRoute.value.meta.title).toBeTruthy();
      expect(router.currentRoute.value.meta.navLabel).toBeTruthy();
    }
  });

  it('resolves an unknown path to the not-found route', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes });

    await router.push('/route-that-does-not-exist');

    expect(router.currentRoute.value.name).toBe('not-found');
  });

  it('keeps the learning session workspace under the Learning navigation label', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes });
    await router.push('/learn/sessions/42');
    expect(router.currentRoute.value.name).toBe('learning-session');
    expect(router.currentRoute.value.meta.navLabel).toBe('学习');
  });

  it('preserves page scroll only for node focus changes inside the same course knowledge map', () => {
    const router = createRouter({ history: createMemoryHistory(), routes });
    const from = router.resolve('/courses/7?tab=knowledge-structure&nodeId=1');
    const nextNode = router.resolve('/courses/7?tab=knowledge-structure&nodeId=2');
    const otherTab = router.resolve('/courses/7?tab=materials&nodeId=2');
    const otherCourse = router.resolve('/courses/8?tab=knowledge-structure&nodeId=2');

    expect(isKnowledgeMapFocusChange(nextNode, from)).toBe(true);
    expect(scrollBehavior(nextNode, from, null)).toEqual({
      left: window.scrollX,
      top: window.scrollY,
    });
    expect(isKnowledgeMapFocusChange(otherTab, from)).toBe(false);
    expect(scrollBehavior(otherTab, from, null)).toEqual({ top: 0 });
    expect(isKnowledgeMapFocusChange(otherCourse, from)).toBe(false);
  });
});
