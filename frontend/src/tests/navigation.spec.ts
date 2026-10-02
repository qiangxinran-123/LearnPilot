import { describe, expect, it } from 'vitest';

import { navigationItems } from '@/components/navigation/navItems';

describe('sidebar navigation', () => {
  it('matches the five learner journey routes in order', () => {
    expect(navigationItems.map((item) => item.to)).toEqual([
      '/dashboard',
      '/courses',
      '/diagnose',
      '/learn',
      '/progress',
    ]);
    expect(navigationItems.map((item) => item.label)).toEqual([
      '首页',
      '课程',
      '诊断',
      '学习',
      '进展',
    ]);
  });
});
