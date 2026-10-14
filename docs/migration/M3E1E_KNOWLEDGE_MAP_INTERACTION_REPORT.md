# M3-E.1-E Knowledge Map Interaction Report

## 1. 原滚轮问题的真实原因

- 当前统一知识地图实际挂载的是 DOM 聚焦关系图 `KnowledgeFocusGraph`，不是遗留的 G6 全量图。
- 遗留 `KnowledgeGraph` 仍配置了 G6 `zoom-canvas`，这是仓库中唯一会消费滚轮并缩放图谱的行为；本阶段已移除该行为，避免组件未来复用时再次拦截网页滚动。
- 当前聚焦图原先没有独立的视图控制和平移边界。修复后不注册 `wheel` 监听，不调用 `preventDefault()` 或 `stopPropagation()` 处理滚轮；仅在空白画布的活动拖动过程中阻止默认 pointer 行为。
- C 阶段滚动 Hotfix 的同课程 `nodeId` 路由滚动保持逻辑继续沿用，本阶段未修改 URL 同步策略。

## 2. 修复方案

- 聚焦关系图新增 50%～200% 的显式缩放状态，步长 15%。
- 仅通过放大、缩小按钮改变缩放；滚轮和触控板普通滚动继续交给外层网页。
- “适应画布”按当前可见内容和容器尺寸计算比例，保留 32px 安全边距，并且不会把小图放大到 100% 以上。
- “恢复默认视图”恢复 100% 缩放和零平移，因此与“适应画布”语义不同。
- 空白区域使用 pointer capture 进行临时平移；知识节点、链接和按钮不会启动平移。
- 焦点节点切换后重新适应当前直接关系，但不改变网页滚动位置、路由规则或左侧导航状态。
- ResizeObserver 先同步初始化尺寸，再只对真实尺寸变化执行适应，避免延迟回调覆盖用户刚完成的缩放。

## 3. 工具栏与画布交互

- 工具栏使用原生 `button`，具有 `aria-label`、`title`、disabled、focus-visible 和真实缩放百分比。
- Enter 有显式处理；Space 保留原生按钮行为。
- 放大/缩小达到边界后按钮禁用。
- 画布平移只更新组件内 translate，不修改 `focusNodeId`、URL 或知识关系数据。
- 节点点击继续只触发地图聚焦，不进入知识详情。

## 4. 修改文件

- `frontend/src/components/knowledge/KnowledgeFocusGraph.vue`
- `frontend/src/components/knowledge/KnowledgeGraph.vue`
- `frontend/src/tests/knowledge-focus-graph.spec.ts`
- `docs/migration/M3E1E_KNOWLEDGE_MAP_INTERACTION_REPORT.md`

未修改后端、API、数据库、知识模型、AI 工作流、构建编排或依赖。

## 5. 路由与焦点状态影响

- 保留 `nodeId` query 参数、刷新恢复、同课程焦点替换和详情返回。
- 左侧导航、中央关系图、知识预览继续共享 `KnowledgeStructurePanel` 的唯一焦点状态。
- 连续切换焦点时不回顶；左侧已展开目录不会被折叠。
- 缩放和平移不触发请求、不修改路由、不重建课程知识数据。

## 6. 自动化测试

执行日期：2026-10-14。

| 检查             | 结果                                                                   |
| ---------------- | ---------------------------------------------------------------------- |
| Frontend Vitest  | PASS — 87/87，15 个测试文件                                            |
| TypeScript       | PASS — `vue-tsc --noEmit`                                              |
| ESLint           | PASS — 0 warnings                                                      |
| Prettier         | PASS                                                                   |
| Production build | PASS — 1,744 modules transformed                                       |
| 受影响测试       | PASS — 滚轮不拦截、缩放边界、适应/重置、平移、节点聚焦、URL 与资源清理 |

生产构建仍有既有的大 chunk 提示，本阶段没有新增依赖或扩大初始图谱依赖。

## 7. 浏览器实际验证

状态：PASS。

使用本地真实前后端、`/tmp` 隔离 SQLite 数据库和真实 canonical/CONTAINS/PREREQUISITE 记录验证：

- 图谱空白区滚轮：网页从 `scrollY=120` 滚动到 `260`，缩放保持 89%。
- 图谱节点上滚轮：网页从 `scrollY=300` 滚动到 `200`，缩放保持 89%。
- 工具栏：放大、缩小、适应画布和恢复默认视图均生效；适应与重置结果不同。
- 空白区拖动：内部 transform 从零平移变为 `translate(45px, 25px)`，URL 和焦点保持不变。
- 连续点击左侧“向量 / 矩阵运算 / 线性变换”及右侧关联节点：网页始终保持 `scrollY=380`，URL、预览和选中节点同步更新。
- 刷新 `nodeId=5` 后恢复“特征值与特征向量”；进入详情并点击“在知识地图中查看”后返回同一焦点。
- 375px 视口：页面 `scrollWidth === clientWidth === 360`，无横向溢出；图谱区域滚轮正常滚动网页，工具栏位于视口内。
- 浏览器中直接分派 KeyboardEvent 验证 Enter 缩放从 88% 更新到 103%；自动化单元测试同时覆盖该键盘监听。

浏览器控制台仅有既有的 `favicon.ico` 404，以及隔离验收数据未创建关系推断 run 时被前端安全处理的 409；均与本阶段交互修改无关。

## 8. 未完成或受限事项

- 当前统一地图是 C 阶段确定的 DOM 聚焦图，不是全量 G6 Canvas；本阶段没有重新引入旧双视图或重构图形技术栈。
- 未验证真实硬件触控板的双指手势；已通过浏览器 wheel 输入和 `touch-action: pan-y` 验证同等网页滚动路径。
- 不保存跨页面的历史缩放和平移，返回地图时按当前焦点恢复默认适应视角，符合本阶段约定。

## 9. 最终状态

**COMPLETE**
