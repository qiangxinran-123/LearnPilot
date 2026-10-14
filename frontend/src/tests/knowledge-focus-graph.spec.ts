import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import KnowledgeFocusGraph from '@/components/knowledge/KnowledgeFocusGraph.vue';
import type { KnowledgeFocusData } from '@/components/knowledge/knowledgeMapAdapter';
import type { KnowledgeNode } from '@/types/knowledge';

function node(id: number): KnowledgeNode {
  return {
    id,
    course_id: 7,
    name: `知识点 ${id}`,
    normalized_name: `知识点 ${id}`,
    description: `知识点 ${id} 的说明`,
    importance: 'medium',
    difficulty: 'basic',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

function focusData(): KnowledgeFocusData {
  return {
    focusNode: node(1),
    prerequisiteNodes: Array.from({ length: 7 }, (_, index) => node(index + 2)),
    dependentNodes: [node(20)],
    prerequisiteEdges: [],
    dependentEdges: [],
    ignoredEdgeIds: [],
  };
}

function pointerEvent(
  type: string,
  values: { pointerId: number; button?: number; clientX: number; clientY: number },
): Event {
  const event = new Event(type, { bubbles: true, cancelable: true });
  for (const [key, value] of Object.entries(values)) {
    Object.defineProperty(event, key, { configurable: true, value });
  }
  return event;
}

describe('KnowledgeFocusGraph', () => {
  it('emits a focus change instead of navigating when a neighboring node is clicked', async () => {
    const wrapper = mount(KnowledgeFocusGraph, { props: { data: focusData() } });
    await wrapper.find('.focus-node--before').trigger('click');
    expect(wrapper.emitted('focus')).toEqual([[2]]);
    expect(wrapper.find('a').exists()).toBe(false);
  });

  it('makes every high-degree neighbor available through an explicit expansion', async () => {
    const wrapper = mount(KnowledgeFocusGraph, { props: { data: focusData(), initialLimit: 5 } });
    expect(wrapper.findAll('.focus-node--before')).toHaveLength(5);
    expect(wrapper.text()).toContain('查看其余 2 个前置知识');
    await wrapper.find('.focus-graph__more').trigger('click');
    expect(wrapper.findAll('.focus-node--before')).toHaveLength(7);
  });

  it('leaves wheel events available to the outer page without changing graph scale', () => {
    const wrapper = mount(KnowledgeFocusGraph, { props: { data: focusData() } });
    const viewport = wrapper.find('[data-testid="knowledge-focus-viewport"]');
    const wheel = new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: 120 });

    viewport.element.dispatchEvent(wheel);

    expect(wheel.defaultPrevented).toBe(false);
    expect(wrapper.find('.focus-graph__scale').text()).toBe('100%');
  });

  it('zooms only through explicit controls and enforces scale limits', async () => {
    const keyboardWrapper = mount(KnowledgeFocusGraph, { props: { data: focusData() } });
    const keyboardZoomIn = keyboardWrapper.find('button[aria-label="放大知识关系图"]');

    keyboardZoomIn.element.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }),
    );
    await keyboardWrapper.vm.$nextTick();
    expect(keyboardWrapper.find('.focus-graph__scale').text()).toBe('115%');
    keyboardWrapper.unmount();

    const wrapper = mount(KnowledgeFocusGraph, { props: { data: focusData() } });
    const zoomIn = wrapper.find('button[aria-label="放大知识关系图"]');
    const zoomOut = wrapper.find('button[aria-label="缩小知识关系图"]');

    for (let index = 0; index < 8; index += 1) await zoomIn.trigger('click');
    expect(wrapper.find('.focus-graph__scale').text()).toBe('200%');
    expect(zoomIn.attributes('disabled')).toBeDefined();

    for (let index = 0; index < 12; index += 1) await zoomOut.trigger('click');
    expect(wrapper.find('.focus-graph__scale').text()).toBe('50%');
    expect(zoomOut.attributes('disabled')).toBeDefined();
  });

  it('fits visible content and keeps reset as a distinct default-view action', async () => {
    const wrapper = mount(KnowledgeFocusGraph, { props: { data: focusData() } });
    const viewport = wrapper.find('[data-testid="knowledge-focus-viewport"]').element;
    const canvas = wrapper.find('.focus-graph__columns').element;
    Object.defineProperties(viewport, {
      clientWidth: { configurable: true, value: 600 },
      clientHeight: { configurable: true, value: 400 },
    });
    Object.defineProperties(canvas, {
      scrollWidth: { configurable: true, value: 1200 },
      scrollHeight: { configurable: true, value: 600 },
    });

    await wrapper.find('button[aria-label="适应知识关系图画布"]').trigger('click');
    expect(wrapper.find('.focus-graph__scale').text()).toBe('50%');
    await wrapper.find('button[aria-label="恢复知识关系图默认视图"]').trigger('click');
    expect(wrapper.find('.focus-graph__scale').text()).toBe('100%');
    expect(wrapper.find('.focus-graph__columns').attributes('style')).toContain(
      'translate(0px, 0px) scale(1)',
    );
  });

  it('pans from empty canvas without changing focus and cleans up on unmount', async () => {
    const disconnect = vi.spyOn(ResizeObserver.prototype, 'disconnect');
    const wrapper = mount(KnowledgeFocusGraph, { props: { data: focusData() } });
    const viewport = wrapper.find('[data-testid="knowledge-focus-viewport"]').element;
    viewport.dispatchEvent(
      pointerEvent('pointerdown', { pointerId: 3, button: 0, clientX: 10, clientY: 15 }),
    );
    const move = pointerEvent('pointermove', {
      pointerId: 3,
      clientX: 35,
      clientY: 45,
    });
    viewport.dispatchEvent(move);
    viewport.dispatchEvent(pointerEvent('pointerup', { pointerId: 3, clientX: 35, clientY: 45 }));
    await wrapper.vm.$nextTick();

    expect(move.defaultPrevented).toBe(true);
    expect(wrapper.find('.focus-graph__columns').attributes('style')).toContain(
      'translate(25px, 30px) scale(1)',
    );
    expect(wrapper.emitted('focus')).toBeUndefined();
    wrapper.unmount();
    expect(disconnect).toHaveBeenCalledTimes(1);
    disconnect.mockRestore();
  });
});
