# UX-FIX-1 验收记录

状态：**COMPLETE**（UX-FIX-1 核心验收）。跨 Session 长期复习证据语义仍未定义，见下方非阻塞限制；不声称已实现全局 Evidence 去重。

## 根因和修复

原 Session 将概念资料放在所有阶段之前，概念和示例分别靠多次点击推进；M7 逐题分配，前端却把上限 5 当作总题数；结算只给出 M6 的单个目标，可能再次指向当前节点；Learn 曾无条件打开课程内任一活跃 Session，可能与卡片目标不一致。

现在在一个 Session 页面按概念、练习、反馈推进。开始练习时按现有契约保存概念和示例状态，Tutor 示例能力保留；返回概念不销毁练习状态。完成条件仍由 M7 判断，按真实已完成题数和动态题序显示，不虚构分母，无题明确提示。反馈显示真实统计和作答详情。Learn 的推荐卡片只恢复目标一致的活跃 Session，其他活跃 Session 保留独立入口。返回时保留课程及当前连续流程上下文。

完成的 Session Detail 额外返回 `practice_attempts`，从已提交练习快照和回答读取题干、答案、对错和解释；仅在完成时提供，并校验 Session 所有者、课程归属和练习 assessment 的所有者、课程及类型。刷新后无需重新提交。

新增只读 Session continuation 查询，按 M6 已解析的合法 frontier 排除本轮已完成目标，再使用原有排序键选择；原始推荐排序公式、前置判断和 M5 算法不变。排除列表由路由保存并在返回 Learn 恢复同一会话时传回；无合适候选时结束本轮。M6 本身的个性化或结构性候选范围仍然决定可用目标，不强行推荐范围以外的节点。

## 修改文件

- 后端：`backend/app/api/learning_sessions.py`、`backend/app/schemas/learning_session.py`、`backend/app/services/learning_session_service.py`、`backend/app/services/recommendation_engine.py`。
- 前端：`frontend/src/views/LearnView.vue`、`LearningSessionView.vue`、`components/learning/PracticePanel.vue`、`LearningSummary.vue`、`services/learningSessions.ts`、`types/learningSession.ts`。
- 测试：`backend/tests/test_m6_2_recommendation_engine.py`、`test_m7_5_settlement.py`；`frontend/src/tests/learning-session-view.spec.ts`、`learning-summary.spec.ts`、`learning-plan-views.spec.ts`、`practice-panel.spec.ts`。

## 跨 Session Evidence 只读审查

- 同一源题可由 `assessment_questions.question_id` 关联，快照中也有 `source_question_id` 和 `source_question_version`；源题删除后外键可置空，历史快照仍保存源题 ID 与版本。应同时考虑用户、课程、历史知识节点与题目版本；题干相似不等于同题。
- Evidence 唯一约束是 `source_type + source_question_snapshot_id + historical_knowledge_node_ref + evidence_schema_version`。抽取时的 snapshot ID 是每次 assessment 的题目快照 ID，不是源题 ID。Mastery 独立性身份也包含 assessment、快照和 response ID，因此不同 Session 重做同一源题会形成不同的独立证据；fingerprint 也包含这些 ID。
- 同一请求重试：相同快照和相同答案复用已有 Response，结算依据已有 Evidence 身份复用；答案不一致被锁定。立即重练和间隔复习：现有代码没有明确间隔或复习策略，都会作为不同 assessment 记录，不能仅凭 ID 确定教育意义上的独立性。
- 任何按源题过滤、降权或设定冷却期的策略都会改变输入 M5 的证据集合或权重，即使不修改计算公式，也会影响 Mastery、独立证据数、assessment 数和 Confidence；fingerprint、MasteryHistory 曲线及状态新鲜度可能随之变化。M8 的完成事件直接读取已完成 Session，保留 Session 时事件本身仍在，但掌握历史点和显示语义可能改变。
- 可考虑在 M7 选题层对近期同源题限制再次分配，保留显式复习入口；不改 M5 算法或已有 Evidence 身份，但单题题库可能因此无题，且无法阻止其他入口或冷却期外的重复证据。若要允许复习同时不让其计入独立证据，则需要另定计入规则和持久化/回放语义，不能声称完全不影响 M5 或 M8。
- 建议先确认同题身份是否包含版本、冷却间隔、显式重练与间隔复习是否计入 Mastery/Confidence、历史是否回算或仅前向生效，再设计事务并发、防绕过、历史兼容、课程用户隔离及 M5/M8 回归测试。本轮未实施这些变更。

## 验证

- 后端：pytest 453 passed；Ruff check 和 format check 通过。
- 前端：Vitest 213 passed；TypeScript、ESLint、生产构建通过。构建有大包警告；部分已有测试输出 Vue 事件警告。
- 浏览器使用 demo 数据库副本和仓库测试夹具，不修改原数据库。单题“补码表示”提交错误答案、结算、刷新并恢复题干/答案/解析；查到 1 个提交和 1 条 Evidence。多题夹具完成 5 题，前几题提交不提前结算，反馈为 5 题、3 对、2 错；无题节点显示空状态；返回概念保留作答。另用隔离测试记录验证下一节点、浏览器后退及未完成会话复用，并验证返回 Learn 后课程与流程参数保留。无题页面在 1440、1280、1024 宽度检查无水平溢出。
- 上一轮浏览器验收未覆盖全部关键路径；本轮最终验收见下节。自动化测试不能证明跨 Session 全局防刷。

## 最终验证与收尾

- **自动重复分配：未在现有正常流程发现缺陷。** 本 Session 已分配的源题按 `question_id` 排除；相同答案重试复用响应。继续学习排除本轮完成的节点，M7 只选择目标节点的主关联题；题目快照要求恰好一个主知识点。测试中原节点的源题为 4、5、1、2、3，下一节点首次选题为 12。未添加跨 Session 的源题全局排除，用户主动重新学习仍可重做原题。
- **本轮实际代码修改：最小前端修复。** 浏览器复现单题提交后立即刷新时，后端确认题库耗尽并完成练习，但页面未刷新 Session 状态，结算入口缺失。`PracticePanel.vue` 在恢复练习后通知父页面刷新状态；重新复测后可直接结算。未修改后端产品逻辑。
- **新增测试：2 项。** 后端单题组合测试检查重试、重复读取、结算、无下一目标及主动重学；前端测试检查恢复练习完成后通知刷新。定向 pytest **8/8**、定向 Vitest **42/42**；Ruff、TypeScript、ESLint、构建通过。没有重跑全量套件；构建仍有大包警告。
- **1280px 浏览器 Case A–D：PASS。** 单题“补码表示”概念、真实第 1 题、作答、结算和刷新详情通过，隔离数据库有 1 个 Response 和 1 条 Evidence；另用“小端法”验证提交后立即刷新可显示结算入口。五题夹具依序提交并得到 5 题、3 对、2 错，恢复过程中不提前结算，隔离数据库有 5 个 Response 和 5 条 Evidence。无题节点有明确提示并可返回 Learn。已验证课程保留、未完成 Session 恢复、浏览器后退、切换不同目标以及没有下一目标时结束。
- **1440px、1024px：PASS。** 对实际练习和反馈页面检查题目、选项、步骤、返回入口及布局，无水平溢出；不在每个宽度重复写入业务数据。
- **仅人工进一步验证的边界：** 网络故障及并发条件下的实际浏览器交互、课程资料或题目主关联在连续学习中发生变化时的端到端表现，未在本轮浏览器中模拟；同次重试、归属和前置约束由定向自动化测试覆盖。原始数据库和用户记录未修改。
- **剩余非阻塞限制：** 跨 Session 长期复习的证据独立性与权重尚无产品语义，重复主动练习可生成新的 Evidence；自动继续只按本轮节点过滤，不是跨 Session 的全局源题去重。
