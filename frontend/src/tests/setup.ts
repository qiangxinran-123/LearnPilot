import ElementPlus from 'element-plus';
import { config } from '@vue/test-utils';

config.global.plugins = [ElementPlus];

class ResizeObserverMock {
  public observe(): void {}

  public disconnect(): void {}
}

Object.defineProperty(globalThis, 'ResizeObserver', {
  writable: true,
  value: ResizeObserverMock,
});
