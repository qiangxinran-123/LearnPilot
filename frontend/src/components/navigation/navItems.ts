import {
  Collection,
  Compass,
  DataAnalysis,
  HomeFilled,
  TrendCharts,
} from '@element-plus/icons-vue';
import type { Component } from 'vue';

export interface NavigationItem {
  to: string;
  label: string;
  icon: Component;
}

export const navigationItems: NavigationItem[] = [
  { to: '/dashboard', label: '首页', icon: HomeFilled },
  { to: '/courses', label: '课程', icon: Collection },
  { to: '/diagnose', label: '诊断', icon: DataAnalysis },
  { to: '/learn', label: '学习', icon: Compass },
  { to: '/progress', label: '进展', icon: TrendCharts },
];
