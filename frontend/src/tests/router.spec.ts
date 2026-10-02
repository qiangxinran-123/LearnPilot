import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it } from 'vitest';

import { routes } from '@/router';

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
});
