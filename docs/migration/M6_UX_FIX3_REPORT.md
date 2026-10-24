# M6-UX-FIX-3 课程级诊断题生成与入口重构

## 目标与原架构

原有 M4 题目生成器按单个知识节点构建受控课程上下文，执行结构化 LLM 生成、Pydantic 校验、答案与来源校验、PRIMARY 节点关联校验、重复检测和事务保存。FIX-1 在课程详情页提供了逐节点生成、人工审核与题库 readiness 查询。

本轮没有重写生成器、组卷器或审核规则，而是在既有 `DiagnosticQuestionBankService` 中增加课程级有界编排，并将普通用户入口移动到诊断页。

## 实际修改

- `backend/app/services/diagnostic_question_bank_service.py`
  - 增加课程级准备方法与课程级进程内互斥锁。
  - 直接复用 `AssessmentAssemblyService.preview_question_bank` 获取当前必需覆盖节点。
  - 跳过已有 VALIDATED 或 PENDING 题目的节点。
  - 单次最多规划 4 个节点，并按当前题库分布确定性补齐题型与难度。
  - 每个节点继续调用既有 M4 生成器，生成结果保持 PENDING，等待人工审核。
  - 准确返回成功、失败与待审核数量；部分成功不伪装为全部成功。
- `backend/app/api/diagnostics.py`
  - 新增 `POST /api/diagnostics/courses/{course_id}/questions/prepare`。
- `backend/app/schemas/question_generation.py`
  - 增加课程级准备结果和逐节点失败 DTO。
- `backend/tests/test_fix1_diagnostic_question_bank.py`
  - 覆盖课程级缺失规划、PENDING 保存、重复请求保护、部分失败保留及路由注册。
- `frontend/src/services/diagnostics.ts`、`frontend/src/types/diagnostic.ts`
  - 增加与后端一致的课程级准备调用和类型。
- `frontend/src/components/diagnostic/QuestionBankPanel.vue`
  - 从逐节点生成界面改为课程级题库工作区。
  - 展示服务端有效题量、核心节点覆盖、尚未覆盖和待审核数量。
  - 一次用户确认只发送一个课程级准备请求；无自动重试、无假进度。
  - 保留完整人工审核流程，审核后重新读取服务端 readiness。
- `frontend/src/views/DiagnoseView.vue`
  - 增加左侧课程选择、右侧诊断工作区。
  - FIX-2 未完成 Attempt 的“继续作答”保持最高优先级。
  - 课程切换以 keyed 组件和请求版本隔离旧响应。
- `frontend/src/views/CourseDetailView.vue`
  - 移除普通用户逐节点生成入口，课程资料和知识结构功能不变。
- `frontend/src/tests/question-bank-panel.spec.ts`、`frontend/src/tests/diagnose-view.spec.ts`
  - 更新课程级确认、防重复、部分状态、审核刷新、课程切换与草稿优先级测试。

## 覆盖规划与调用边界

1. 规划范围由现有组卷预览的 `required_nodes` 唯一确定，前端不复制排序算法。
2. VALIDATED 题计入覆盖；PENDING 与 REJECTED 不计入可诊断题量。
3. 已有 VALIDATED 或 PENDING 的目标节点不会无条件重复生成。
4. 单次课程级操作最多处理 4 个节点，避免无界模型费用。
5. 当前底层生成器使用单节点受控上下文，因此课程级服务在后端串行编排受限批次，而不是由前端循环调用公开逐节点 API。
6. 题型和题目难度根据当前题库数量采用稳定的最少使用优先顺序；不把知识节点难度直接等同于题目难度。
7. 生成题保持 PENDING。人工审核仍会重新验证来源、PRIMARY 关联、题目质量和重复性，只有 VALIDATED 题可进入组卷。

## 数据保护

- 新增题目不修改 Assessment、Response、Learning Evidence、Mastery 或 LearningPlan。
- 已开始的 Attempt 使用既有 `AssessmentQuestion.question_snapshot` 和固定顺序恢复，新题只影响后续新建诊断。
- 课程及知识节点归属继续由既有 owner/course 校验保证。
- 未增加数据库表或字段，没有新增 migration。
- 未实现多知识点综合题。当前评分契约以单个 PRIMARY 节点为准，避免扩大 M4 评分范围。

## 验证结果

- 后端针对性：`14 passed`。
- 后端完整回归：`354 passed`。
- 前端针对性：`12 passed`。
- 前端完整回归：`130 passed`。
- Ruff lint：PASS。
- Ruff format check：PASS。
- TypeScript：PASS。
- ESLint：PASS。
- Production build：PASS（仅存在既有 bundle size warning）。
- Alembic：单一 head `0013_m6_learning_plans`；本轮无迁移，未改动数据库。
- `git diff --check`：PASS。
- 真实 LLM 调用：0；自动化测试全部使用脚本化替身。
- 浏览器人工验收：NOT VERIFIED。本轮没有调用真实 Provider，也没有污染用户课程数据。

## 已知限制与 FIX-4 边界

- 课程级准备是同步、有界批次；若真实 Provider 在实际资料上耗时过长，界面会如实显示错误并由用户手动刷新，不会自动重试。
- 进程内锁避免单进程并发重复规划，但不是跨进程 exactly-once 基础设施；数据库级内容去重仍是最终保护。
- readiness 会随已审核题量按原组卷规则变化，用户可能需要多次“补充诊断题 → 审核”。
- FIX-4 才处理新增资料检测、知识模型增量更新、节点合并/映射、题目受影响分析和版本迁移；本轮未进入这些范围。

## 结论

M6-UX-FIX-3 的代码与自动化验收通过。真实 Provider 的浏览器从零准备、补充及人工审核流程仍需在隔离测试课程中由用户执行一次人工验收。
