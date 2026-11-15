# 02 诊断题库从空库排查到生成与审核入口

> 公开副本对本机用户目录作了脱敏；其余内容沿用原记录。

关注从你报告“59 个核心节点、0 道合格题”，到 Codex 区分空库与组卷缺陷，再到你分两轮要求接入正式后端接口及前端人工审核。

以下按时间保留所选轮次的用户 Prompt 和 Codex 可见消息。界面自动附加的浏览器上下文已剔除，正文按原文保留，换行统一为 LF。原对话中的链接、测试状态和用语均反映当时的记录。

时间采用北京时间。单轮如因中断没有最终答复，将保留原可见过程消息并注明。为方便定位，每轮列出来源聊天和回合 ID。

## 02.01 · 2026-10-22 14:18:36

来源：LearnPilot V1 — M6-修复 · [在 Codex 打开](codex://threads/01a16242-c402-7120-8185-3ce1ee73a526)

回合 ID：`01a16242-efc0-7270-bf05-d7ff326747f2`

**用户 Prompt**

请对 LearnPilot V1 当前“计算机系统”课程的诊断题库不足问题进行只读排查。

浏览器目前显示：

- 课程：计算机系统
- 核心知识节点：59
- 合格诊断题：0
- 已覆盖知识节点：0/59
- 提示：当前课程的诊断题目尚不充足

要求：

1. 读取 M4 诊断模块的真实代码，明确什么条件下题目会被视为“合格诊断题”，以及诊断启动所要求的最低数量和知识点覆盖规则。
2. 检查当前应用实际连接的数据库，确认“计算机系统”课程下诊断题总数、各状态数量、校验通过数量、具有有效知识节点关联及来源证据的数量。只输出统计，不输出用户隐私信息。
3. 确认 59 个知识节点是否属于当前选中的课程，以及题目与课程、知识节点的关联是否正确。
4. 检查课程页面是否已有诊断题生成、导入、审核或发布入口，说明正常用户应该如何补充题库。
5. 检查当前提示是正常的题库不足拦截，还是数据读取、状态筛选或关联错误。
6. 单独确认历史诊断结果的读取是否被“当前题库不足”错误阻断；如果存在已完成诊断记录，应能独立查看历史结果。
7. 不创建、修改或删除任何题目、诊断记录、Mastery、Learning Evidence 或数据库文件。
8. 不降低题库门槛，不使用 Mock 数据，不执行付费 LLM 调用，不修改代码。
9. 不执行全量测试，不进行 Git 提交或推送。

最终输出：

- 根本原因及对应代码位置
- 当前题库各状态的实际统计
- 最低可启动诊断的条件
- 当前是否存在历史已完成诊断
- 是否属于 Bug
- 最小解决步骤
- 是否会影响 M6 浏览器人工验收

只读排查完成后停止，等待我的确认。

**Codex 过程消息**

我会按只读方式沿三条线核对：M4 的合格题与组卷规则、当前运行服务实际连接的数据库统计、前端现有题库补充入口及历史报告路由。不会调用任何生成接口，也不会写入数据库或运行全量测试。

**Codex 过程消息**

代码层面的判定链已经明确：只有 `validated` 题目才进入候选，随后还要通过题目快照结构校验、具备来源引用、且恰好关联一个当前课程内的有效核心知识节点（`primary`）。现在我会对实际 SQLite 文件做只读 URI 查询，只输出聚合计数和关联完整性。

**Codex 过程消息**

我再补两项只读证据：题目生成服务最终写入的状态，以及当前课程是否已有 M5/M6 状态可支撑正向人工验收。之后直接给出结论，不运行测试也不改动任何数据。

**Codex 最终答复**

只读排查结论：当前提示是正常的题库不足拦截，不是数据读取、状态筛选或知识节点关联 Bug。实际原因是当前应用数据库中没有任何诊断题。

## 根本原因

当前连接的 SQLite 数据库 `learnpilot-demo.sqlite3` 中：

- “计算机系统”课程存在 59 个知识节点。
- 59 个节点全部属于该课程，且均为有效节点。
- 诊断题表全库记录数为 0。
- 因此不存在可通过筛选的题目、知识点关联或来源证据。
- 后端正确返回 `QUESTION_BANK_INSUFFICIENT`，前端据此显示“当前课程的诊断题目尚不充足”。

主要判定位置：

- 最低题量、组卷和覆盖判断：[assessment_assembly_service.py](/home/<redacted>/projects/campus-ai/backend/app/services/assessment_assembly_service.py:60)
- 合格题筛选规则：[assessment_assembly_service.py](/home/<redacted>/projects/campus-ai/backend/app/services/assessment_assembly_service.py:257)
- 数据库仅读取当前课程 `VALIDATED` 题目：[question_repository.py](/home/<redacted>/projects/campus-ai/backend/app/repositories/question_repository.py:63)
- 题目内容、答案、来源及关联快照校验：[diagnostic_domain_service.py](/home/<redacted>/projects/campus-ai/backend/app/services/diagnostic_domain_service.py:324)
- 题目 Schema 约束：[diagnostic.py](/home/<redacted>/projects/campus-ai/backend/app/schemas/diagnostic.py:18)

## 当前实际统计

| 项目 | 数量 |
|---|---:|
| 当前课程知识节点 | 59 |
| 当前课程有效知识节点 | 59 |
| 属于其他课程的节点 | 0 |
| 诊断题总数 | 0 |
| `PENDING` | 0 |
| `VALIDATED` | 0 |
| `REJECTED` | 0 |
| 校验通过且具有来源证据 | 0 |
| 具有任意知识节点关联 | 0 |
| 关联当前课程有效节点 | 0 |
| 满足完整合格规则的题目 | 0 |
| 无效、跨课程或失效节点关联 | 0 |
| 已覆盖核心节点 | 0/59 |

实际 readiness 响应：

- 状态：`question_bank_insufficient`
- `can_start`: `false`
- 可用题目：0
- 最低要求：8
- 原因码：`QUESTION_BANK_INSUFFICIENT`

## 最低可启动诊断的条件

最低需要 8 道合格题。单道题必须同时满足：

1. `validation_status == VALIDATED`。
2. 归属当前课程。
3. 题干、选项、正确答案、解析、难度等 Schema 校验通过。
4. 至少有一条有效来源证据 `source_refs`。
5. 恰好有一个 `PRIMARY` 知识节点关联。
6. 该节点属于当前课程、处于有效状态，并属于核心节点集合。
7. 题干非空，且不与已选择题目规范化重复。

覆盖规则不是要求一次覆盖全部 59 个节点。对 59 个核心节点：

- 推荐组卷上限为 20 题。
- 实际目标题量受可用合格题数量限制，但不得低于 8。
- 目标题量为多少，就必须覆盖排序后的对应数量核心节点。
- 核心节点按照重要度及稳定 ID 顺序确定，避免随机结果。

因此，最低可启动情形是至少 8 道合格题，并覆盖规则要求的前 8 个核心节点。

## 历史诊断结果

当前数据库统计：

- 诊断记录总数：0
- 已提交诊断：0
- 当前不存在历史已完成诊断结果。

代码上，历史结果读取没有被 readiness 拦截：

- 历史列表直接读取 assessment：[diagnostic_experience_service.py](/home/<redacted>/projects/campus-ai/backend/app/services/diagnostic_experience_service.py:155)
- 已提交结果直接构建报告：[diagnostic_experience_service.py](/home/<redacted>/projects/campus-ai/backend/app/services/diagnostic_experience_service.py:189)
- 对应 API：[diagnostics.py](/home/<redacted>/projects/campus-ai/backend/app/api/diagnostics.py:57)
- 前端历史记录独立加载：[DiagnoseView.vue](/home/<redacted>/projects/campus-ai/frontend/src/views/DiagnoseView.vue:57)

因此，若将来存在已完成记录，即使当前题库不足，历史结果仍应可以独立查看。当前看不到历史结果只是因为数据库中确实没有记录。

## 是否属于 Bug

- 题库不足提示：不是 Bug。
- 状态筛选：正常。
- 课程和节点隔离：正常。
- 历史结果读取：未被错误阻断。
- 数据本身：题库为空。
- 产品能力缺口：当前课程页面没有面向普通用户的诊断题生成、导入、审核或发布入口。

后端存在内部题目生成服务，但会调用 LLM，且当前没有发现对应的普通用户 API/UI 工作流。本次没有调用它。

## 最小解决步骤

1. 通过经授权的题库管理流程，为“计算机系统”准备至少 8 道真实诊断题。
2. 每题补齐有效课程归属、来源证据和一个当前课程核心节点的 `PRIMARY` 关联。
3. 完成内容校验和审核，将题目置为 `VALIDATED`。
4. 确保这些题目覆盖组卷规则要求的核心节点。
5. 重新读取 readiness；无需降低门槛，也不应直接修改数据库。
6. 若需让普通用户自行补充题库，需要后续提供最小的生成/导入/审核入口；当前 UI 无此能力。

## 对 M6 浏览器人工验收的影响

有影响：

- 可以验收“尚未诊断/无有效推荐”的负向状态和引导是否正确。
- 无法从当前数据库通过正常 UI 完成“诊断 → M5 Mastery → M6 推荐与学习计划”的正向链路。
- 因而 Dashboard/Learn 的 `AVAILABLE` 推荐计划正向场景不能依靠当前题库重新产生真实数据。
- 这不属于 M6 推荐算法缺陷，而是 M4 真实题库为空造成的验收数据前置条件不足。

本次仅进行了只读查询和代码检查，没有修改题目、诊断记录、Mastery、Learning Evidence、数据库文件或代码。

---

## 02.02 · 2026-10-22 14:29:04

来源：LearnPilot V1 — M6-修复 · [在 Codex 打开](codex://threads/01a16242-c402-7120-8185-3ce1ee73a526)

回合 ID：`01a1624c-845c-7cd3-babb-9afa4fa65e38`

**用户 Prompt**

# LearnPilot V1 — M4 Diagnostic Question Bank Recovery Assessment

当前 M6 已通过自动化验收，项目进度保持 72%。

当前浏览器人工验收发现：“计算机系统”课程有 59 个有效知识节点，但实际 SQLite 数据库中诊断题总数为 0，导致无法启动初始诊断，也无法通过正常用户流程生成 M5 Mastery 和 M6 推荐结果。

本轮目标：以最小改动成本，确认并恢复真实诊断题库的生成与使用能力，为 M6 浏览器人工验收提供真实业务数据。

请先审查，不要直接修改代码。

## 1. 检查已有 M4 题目生成服务

定位：

- LLM 题目生成逻辑
- Question Schema
- source_refs 生成与校验
- PRIMARY KnowledgeNode 关联
- PENDING / VALIDATED / REJECTED 状态流转
- 题目去重
- Question Repository
- Assessment Assembly Service

判断现有服务能否根据“计算机系统”课程的真实资料和知识节点生成符合 M4 规则的诊断题。

## 2. 核实课程数据前置条件

只读检查：

- 当前课程已解析材料数量
- 可供题目生成的有效文本段落数量
- 59 个核心知识节点与资料来源的关联
- 组卷规则要求的前 8 个核心知识节点
- 这些节点是否有足够的来源材料生成有效诊断题

不要假设所有节点都有足够资料支持题目生成。

## 3. 评估现有题目生成流程

确认是否存在可复用的正式 Service / API。

如果已有完整服务：

优先直接复用。

如果缺少 API 或 UI：

只提出最小的接口和交互补充方案。

不得重新实现第二套 Question Generator。

## 4. 明确题目验证边界

确认：

- 哪些条件能够自动验证
- 哪些条件需要人工确认
- 是否允许自动转为 VALIDATED
- 如何避免 AI 生成无依据题目
- 如何防止生成重复题目
- 如何避免不必要的真实 LLM 调用费用

不得通过直接修改数据库绕开业务校验。

## 5. 提出最小可执行方案

优先考虑：

A. 已有正式接口足以生成并验证题目：不改代码。

B. 后端完整但没有普通用户入口：仅增加必要 API/UI。

C. 后端流程存在真实缺陷：只修复缺陷并增加对应测试。

不得扩大到 M7，也不得修改 M5/M6 核心算法。

## 6. 安全约束

- 不修改现有课程资料。
- 不删除或重建数据库。
- 不改变现有 59 个知识节点。
- 不伪造题目来源或答案。
- 不手动写入 Mastery 或 Learning Evidence。
- 本轮不实际调用付费 LLM。
- 不执行大规模全量回归测试。
- 保留所有未提交 Git 修改。
- 不 commit、不 push。

## 7. 最终输出

请报告：

1. 已有 Question Generator 是否可用。
2. 当前课程的资料是否足够支持生成合格题目。
3. 最低 8 道题所需知识节点的实际数据条件。
4. 是否需要人工审核。
5. 是否必须修改代码。
6. 最小需要修改的文件及职责。
7. 必要的最小测试。
8. 实际生成题目可能产生的 LLM 成本和调用次数风险。
9. 如何完成“诊断 → M5 Mastery → M6 Learning Plan”的真实浏览器验收。

完成方案分析后停止，等待用户确认，不要实施。

**Codex 过程消息**

我会只读审查现有 M4 生成链、状态流转和课程资料覆盖，重点验证“前 8 个核心节点是否真的有可引用材料”。本轮不会调用 LLM、写数据库、改代码或运行全量测试。

**Codex 过程消息**

初步确认生成器不是空壳：它会先锁定课程所有权、知识模型状态和可解析来源，再调用结构化 LLM，并对来源引用、节点对齐、质量和重复题干进行批次级校验。接下来核实它保存为何种状态、是否有正式 API，以及前 8 个节点的真实资料覆盖。

**Codex 过程消息**

资料侧已经满足“可调用生成器”的硬前置：2 份材料均解析成功，共 552 个带来源标识的有效文本段；59/59 核心节点都有可验证来源，前 8 个也全部覆盖。不过其中若干节点的材料较短，因此“能生成”不等于“无需人工判断教学质量”。我再核对当前 provider 是否已配置（仅输出布尔状态和模型名，不读取密钥内容），用于评估调用次数与费用风险。

**Codex 最终答复**

审查结论：属于方案 B。现有 Question Generator 后端能力完整且可复用，课程资料也满足硬性生成条件；真正缺失的是正式 API、题库查看/审核入口和课程页面交互。无需重写生成器，但若要求普通用户完成题库恢复，必须做最小 API/UI 补充。

本轮未修改代码、数据库或课程资料，未调用 LLM，也未运行测试。

## 1. 已有 Question Generator 是否可用

可用，且不是空壳实现。

核心入口位于 [diagnostic_question_generation.py](/home/<redacted>/projects/campus-ai/backend/app/services/diagnostic_question_generation.py:78)，现有流程包括：

1. 校验课程存在及用户归属。
2. 校验目标节点属于当前课程。
3. 要求知识模型状态为 `success`。
4. 从 `KnowledgeSource + Material + MaterialContent` 提取可验证资料。
5. 将资料限制在最多 12,000 字符的受控上下文内。
6. 调用结构化 LLM。
7. 校验题型、难度、节点 ID 和来源引用。
8. 校验题干、选项、答案、解析。
9. 检测课程内及节点内重复题目。
10. 在同一事务内保存题目及 `PRIMARY` 节点关系。

关键代码：

- 真实来源准备：[diagnostic_question_generation.py](/home/<redacted>/projects/campus-ai/backend/app/services/diagnostic_question_generation.py:228)
- 来源引用解析：[diagnostic_question_generation.py](/home/<redacted>/projects/campus-ai/backend/app/services/diagnostic_question_generation.py:275)
- 生成结果校验：[diagnostic_question_generation.py](/home/<redacted>/projects/campus-ai/backend/app/services/diagnostic_question_generation.py:327)
- 去重规则：[diagnostic_question_quality.py](/home/<redacted>/projects/campus-ai/backend/app/services/diagnostic_question_quality.py:41)
- 题目与节点原子保存：[diagnostic_question_generation.py](/home/<redacted>/projects/campus-ai/backend/app/services/diagnostic_question_generation.py:402)
- `PRIMARY` 关联：[diagnostic_question_generation.py](/home/<redacted>/projects/campus-ai/backend/app/services/diagnostic_question_generation.py:463)

现有测试已经覆盖结构化生成、来源伪造、跨课程节点、重复题、回滚、Provider 重试和提示注入等风险，位于 [test_m4b_question_generation.py](/home/<redacted>/projects/campus-ai/backend/tests/test_m4b_question_generation.py:346)。

## 2. 当前课程资料是否足够

从代码硬性条件看，足够启动生成；从教学质量角度看，仍需检查实际输出。

当前课程只读统计：

| 项目 | 实际数量 |
|---|---:|
| 已上传材料 | 2 |
| 解析成功材料 | 2 |
| 解析正文总字符 | 28,302 |
| 非空文本段 | 552 |
| 带有效来源标识的文本段 | 552 |
| 有效知识节点 | 59 |
| 核心知识节点 | 59 |
| `KnowledgeSource` 关联 | 125 |
| 具有可验证来源的核心节点 | 59/59 |

两份材料分别为：

- `ICS期末机考复习提纲_老师范围修订版`：27,280 字符、528 个有效段落。
- `Attacklab`：1,022 字符、24 个有效段落。

所有 59 个核心节点均能通过生成器现有 `_verified_sources()` 校验。

但部分节点来源较短。例如“小端法”“整数溢出”“x86-64 有效地址”的已关联摘录总量分别约为 64、64、61 个字符。它们包含明确事实，足以生成一条基础概念题，但不适合一次生成多道复杂或高难度题。

结论：

- 生成最低 8 道、每节点一道基础题：资料基本足够。
- 为每个节点批量生成多题：部分节点资料不足以支持高质量多样化题目。
- 自动校验通过不等于教学内容必然正确。

## 3. 最低 8 道题所需节点条件

组卷规则位于 [assessment_assembly_service.py](/home/<redacted>/projects/campus-ai/backend/app/services/assessment_assembly_service.py:60)。

核心节点按“重要度优先、节点 ID 稳定排序”。当前前 8 个节点为：

| 顺序 | ID | 知识节点 | 可验证来源数 |
|---:|---:|---|---:|
| 1 | 2 | 小端法（小端序） | 2 |
| 2 | 3 | 位级运算与逻辑运算 | 3 |
| 3 | 4 | 补码表示 | 4 |
| 4 | 5 | 有符号与无符号转换 | 5 |
| 5 | 6 | 整数溢出 | 2 |
| 6 | 7 | x86-64 有效地址 | 1 |
| 7 | 8 | 条件码 | 5 |
| 8 | 10 | 过程调用约定 | 6 |

这 8 个节点全部具有当前生成器认可的真实来源。

最低恢复方案必须满足：

- 每个节点至少生成一题。
- 共计正好或至少 8 道 `VALIDATED` 题。
- 每题只有一个有效 `PRIMARY` 节点关联。
- 每题来源引用必须能解析回对应材料段落。
- 题目 Schema 和确定性质量校验通过。
- 题干不重复。

一个容易忽略的边界：如果生成了第 9 道题，组卷目标会变成 9，便要求覆盖前 9 个核心节点。因此不应先在前 8 个节点中重复生成额外题目。最小恢复应严格“一节点一题，依序覆盖前 8 个节点”。

## 4. 验证边界与人工审核

### 当前可以自动验证

- 请求参数、题型、难度和数量。
- 课程及用户归属。
- 知识模型是否完成。
- 节点是否属于当前课程且有效。
- 来源材料和来源标识是否真实存在。
- LLM 是否引用了允许范围外的材料或节点。
- 选项结构、正确答案键和题型语义。
- 题干、选项、解析的最低质量约束。
- 精确重复和相似重复。
- 保存题目与节点关联的事务一致性。

生成提示也明确禁止外部知识、虚构页码和来源，见 [diagnostic_questions.py](/home/<redacted>/projects/campus-ai/backend/app/ai/prompts/diagnostic_questions.py:7)。

### 自动验证无法可靠保证

- 标准答案在学科语义上一定正确。
- 干扰项是否合理且没有歧义。
- 难度标签是否准确。
- 题目是否真正具有诊断区分度。
- 短资料片段是否支持复杂推理。
- 资料中已有旧题是否值得直接复用或改写。

质量验证器自身也明确说明它不是教育正确性判定器，见 [diagnostic_question_quality.py](/home/<redacted>/projects/campus-ai/backend/app/services/diagnostic_question_quality.py:22)。

### 状态流转现状

模型定义了：

- `PENDING`
- `VALIDATED`
- `REJECTED`

见 [diagnostic.py](/home/<redacted>/projects/campus-ai/backend/app/models/diagnostic.py:16)。

但当前生成器会在自动校验成功后直接保存为 `VALIDATED`，见 [diagnostic_question_generation.py](/home/<redacted>/projects/campus-ai/backend/app/services/diagnostic_question_generation.py:439)。

没有发现正式的题目列表、人工审核、拒绝或发布 API/UI。因此：

- 技术上允许自动转为 `VALIDATED`。
- 当前代码不强制人工审核。
- 为科研竞赛浏览器验收，至少应人工抽查这 8 道真实输出。
- 若要求正式题库质量闭环，应让生成题先进入 `PENDING`，人工确认后转为 `VALIDATED`；这会比单纯恢复验收数据增加少量后端和 UI 工作。

## 5. 是否必须修改代码

分情况：

- 直接从 Python 内部调用现有 Service：生成器本身不用修改，但这不是普通用户流程。
- 现有 Provider Smoke 脚本不能直接使用：它只操作临时数据库，见 [m4b_provider_smoke.py](/home/<redacted>/projects/campus-ai/backend/scripts/m4b_provider_smoke.py:99)。
- 通过浏览器让普通用户恢复题库：必须补充最小 API/UI。

因此推荐方案是 B：

> 保留现有生成器，只补充显式、受控、用户主动触发的题库准备接口和课程页入口。

不需要修改 M3、M5、M6 算法或数据库结构。

## 6. 最小修改文件及职责

建议的最小范围：

- [diagnostics.py](/home/<redacted>/projects/campus-ai/backend/app/api/diagnostics.py)
  - 增加当前课程题库准备状态查询。
  - 增加单节点、单批次的显式生成入口。
  - 映射现有 `DiagnosticQuestionGenerationError`。
  - 不在 GET 中触发生成。

- [question_generation.py](/home/<redacted>/projects/campus-ai/backend/app/schemas/question_generation.py)
  - 增加 API 请求和安全响应 DTO。
  - 返回接受数量、目标节点、Provider/模型标识和 readiness，不暴露密钥或内部上下文。

- [diagnostics.ts](/home/<redacted>/projects/campus-ai/frontend/src/services/diagnostics.ts)
  - 封装题库状态查询和用户主动生成请求。

- [diagnostic.ts](/home/<redacted>/projects/campus-ai/frontend/src/types/diagnostic.ts)
  - 增加严格 TypeScript 契约。

- [CourseDetailView.vue](/home/<redacted>/projects/campus-ai/frontend/src/views/CourseDetailView.vue)
  - 增加轻量“诊断题库准备”区域。
  - 显示已有题数、覆盖数、待覆盖节点及来源是否充足。
  - 只有明确点击才调用生成。
  - 显示真实 LLM 调用和费用提示。
  - 禁止页面加载时自动生成。

如决定强制人工审核，还需增加：

- 后端题目列表及 `PENDING → VALIDATED/REJECTED` 接口。
- 课程页最小审核列表。
- 将生成器保存状态由 `VALIDATED` 调整为 `PENDING`。

这部分不是恢复 M6 浏览器验收的绝对最小项，但是真正题库发布流程更稳妥的选择。

## 7. 必要的最小测试

不需要全量回归。建议只增加：

后端 API 测试：

- 未配置 Provider 时不写入题目。
- 无来源节点不调用 Provider。
- 跨课程节点被拒绝。
- 单次用户操作只触发一次生成。
- 成功后题目、来源和 `PRIMARY` 关联正确。
- Provider/校验失败不产生半成品。
- 重复调用不会插入重复题。
- 题库达到 8 题且覆盖前 8 节点后 readiness 变为 `ready`。
- 第 9 题未覆盖第 9 节点时仍正确拦截。

前端测试：

- 页面只展示状态时不调用生成 POST。
- 用户确认后 POST 恰好一次。
- 请求期间禁用重复点击。
- Provider 失败时保留可重试状态。
- 成功后刷新真实题数和覆盖数。
- 不自动启动诊断，不写 Mastery/Evidence。

现有生成器单元测试无需重复编写，只运行受影响的 M4B/M4D 测试即可。

## 8. LLM 调用次数与成本风险

当前非敏感配置：

- `LLM_MODE=provider`
- Provider 已配置
- 模型：`deepseek-flash`
- 每次最多生成 4 题
- 每次最多尝试 2 次
- 上下文上限：12,000 字符

由于一次 Service 调用只能针对一个知识节点，而最低组卷必须覆盖 8 个不同节点：

- 最少调用次数：8 次。
- 若每次都发生一次可重试失败：最多 16 次 Provider 请求。
- 不建议为单个节点一次生成多题；它不能增加覆盖，而且可能使目标题量上升、反而要求覆盖更多节点。
- 推荐每次只生成 1 题，成功后立即刷新 readiness，再处理下一个节点。

仓库没有记录 Provider 单价，也没有可靠的 token 计费统计；`deepseek-flash` 也可能是当前 Provider 的模型别名。因此不能从代码诚实给出具体人民币金额。

成本控制措施：

- 页面加载和 GET 永远不触发 LLM。
- 必须用户二次确认。
- 已覆盖节点默认不再生成。
- 一次仅生成一题。
- 达到 `ready` 后立即停止。
- 展示预计调用次数。
- 不自动重试整批节点。
- 保存 Provider 返回的模型和 prompt 版本用于审计。

本轮实际 LLM 调用数为 0。

## 9. 完成真实浏览器验收的路径

建议流程：

1. 补充最小题库状态 API 和用户主动生成入口。
2. 在课程页展示前 8 个核心节点及其真实来源准备状态。
3. 用户逐节点生成一题，共 8 次成功生成。
4. 人工检查题干、选项、答案、解析和来源。
5. 如采用审核流，确认后转为 `VALIDATED`。
6. readiness 达到：
   - 合格题目 8
   - 覆盖节点 8
   - `can_start=true`
7. 在诊断页启动初始诊断。
8. 真实作答并提交。
9. 由现有 M5 流程生成 Learning Evidence 和 Mastery。
10. 在 Dashboard/Learn 中由现有 M6 服务生成并展示 Learning Plan。
11. 核对推荐节点、理由和任务均来自真实诊断链路。

最终判断：

- Question Generator：可用。
- 课程硬性资料条件：满足。
- 自动校验：完整但不是学科正确性保证。
- 普通用户入口：缺失。
- 是否要重写生成器：不需要。
- 是否必须改代码才能走浏览器正常流程：需要最小 API/UI 补充。
- 推荐实施方案：B。

---

## 02.03 · 2026-10-22 17:57:53

来源：LearnPilot V1 — M6-修复 · [在 Codex 打开](codex://threads/01a16242-c402-7120-8185-3ce1ee73a526)

回合 ID：`01a1630b-b2ed-7e70-a70f-fe6b58254915`

**用户 Prompt**

# LearnPilot V1 — FIX-1 Diagnostic Question Bank Backend Recovery

## 0. 角色与目标

你现在作为 LearnPilot V1 项目的 Senior Backend Engineer、AI Application Engineer 和 Software Architect，完成诊断题库业务闭环的第一阶段修复。

项目定位：

**面向大学理工科课程的 AI 学习诊断与个性化学习系统。**

项目采用：

**企业级工程规范 + 科研竞赛级实现复杂度。**

当前状态：

- M0–M6 已完成开发和核心自动化验收。
- LearnPilot V1 当前进度保持 72%。
- M7 尚未开始。
- M6 浏览器人工验收发现当前课程缺少真实诊断题。
- 已通过只读审查确认：M4 Question Generator 后端能力已经完整实现。
- 当前缺失的是正式题库生成 API、题库查询 API、人工审核 API。
- 本次不需要重新开发 Question Generator。

FIX-1 的唯一目标：

**复用现有 M4 题目生成与验证能力，建立安全、可控的诊断题生成、查看、人工审核和发布流程，让普通用户能够通过后续 FIX-2 前端入口准备可用于初始诊断的真实题库。**

本阶段只修改必要的后端代码和相关测试、文档。

完成后停止，不进入 FIX-2 或 M7。

---

# 1. 已确认的代码资产

首先重新读取真实仓库，确认以下模块仍然存在及其当前实现。

核心生成服务：

`backend/app/services/diagnostic_question_generation.py`

主要职责：

- 课程与用户归属检查。
- 知识节点有效性检查。
- 课程知识模型状态检查。
- KnowledgeSource 与 MaterialContent 来源读取。
- 受控上下文构建。
- 结构化 LLM 生成。
- 题型、答案、解析、难度等 Schema 校验。
- 来源引用校验。
- 重复题目检测。
- 题目及 PRIMARY 知识节点关系的事务保存。

现有质量验证：

`backend/app/services/diagnostic_question_quality.py`

现有 Repository：

`backend/app/repositories/question_repository.py`

现有诊断领域服务：

`backend/app/services/diagnostic_domain_service.py`

现有组卷服务：

`backend/app/services/assessment_assembly_service.py`

现有 API：

`backend/app/api/diagnostics.py`

现有 Schema：

`backend/app/schemas/diagnostic.py`

可能新增 API DTO 的位置：

`backend/app/schemas/question_generation.py`

已有测试：

`backend/tests/test_m4b_question_generation.py`

注意：

上述路径来自此前审查结果。

执行前必须检查真实文件和现有代码。

如实际实现有变化，以当前仓库为准。

禁止根据历史描述直接覆盖代码。

---

# 2. 当前真实业务问题

当前 SQLite 数据库：

`learnpilot-demo.sqlite3`

“计算机系统”课程：

- 59 个有效核心知识节点。
- 2 份已解析课程资料。
- 59/59 个核心节点存在可验证来源。
- 诊断题总数为 0。
- 无已完成诊断记录。
- readiness 为 `question_bank_insufficient`。
- 最低需要 8 道合格诊断题。

当前组卷要求：

- 题目必须属于当前课程。
- 题目状态必须为 `VALIDATED`。
- 必须具有真实有效的 `source_refs`。
- 必须有且只有一个有效 PRIMARY 知识节点关联。
- 必须满足题目 Schema 和内容质量约束。
- 必须覆盖当前组卷算法所要求的核心节点。
- 题干不得重复。

重要：

**至少 8 道题不意味着任意 8 道题即可启动诊断。**

对于当前课程，必须覆盖按现有组卷规则排序的前 8 个核心节点。

而且当题目总量增加时，目标题量和覆盖要求可能随之提高。

不得通过修改组卷门槛绕过该限制。

---

# 3. FIX-1 严格范围

## 必须完成

1. 题库准备状态查询接口。
2. 用户主动触发的单节点题目生成接口。
3. 当前课程题目查询接口。
4. 待审核题目查询。
5. 题目人工审核通过接口。
6. 题目人工拒绝接口。
7. `PENDING → VALIDATED / REJECTED` 状态流转。
8. 生成题目与原有验证规则兼容。
9. 审核后的 readiness 自动反映真实状态。
10. 必要的 API / Service / Repository 测试。
11. 必要的数据库迁移检查。
12. FIX-1 实现及验收报告。

## 明确禁止

- 重新实现 LLM Question Generator。
- 重新实现题目 Schema。
- 重新实现来源解析。
- 重写去重算法。
- 修改 M3 Knowledge Graph。
- 修改 M4 Assessment Assembly 组卷策略。
- 修改 M5 Mastery。
- 修改 Learning Evidence。
- 修改 M6 Recommendation Engine。
- 修改 LearningPlan。
- 开发 FIX-2 前端页面。
- 修改 Vue UI。
- 实现 M7 Learning Session。
- 引入 RAG、Agent 或 MCP。
- 引入 Redis、Celery、消息队列。
- 添加复杂 RBAC 或企业审核后台。
- 直接修改 SQLite 题库数据。
- 降低题库最低数量或覆盖门槛。

---

# 4. Git 与数据安全

开始前执行：

```bash
git status --short --branch
git branch --show-current
git diff --check
```

记录：

- 当前分支。
- 当前 HEAD。
- 未提交修改。
- 未跟踪文件。
- 本轮修改前的工程基线。

当前仓库可能存在用户尚未提交的 M4–M6 工作。

禁止：

```bash
git reset --hard
git clean -fd
git restore .
git checkout .
git stash
```

未经授权不得：

- commit
- push
- merge
- rebase
- tag
- switch branch

不得覆盖现有用户文件。

不得清空、重建或替换当前数据库。

所有新增测试使用隔离测试数据库。

---

# 5. 关键架构原则

采用既有分层：

```text
FastAPI Router
       ↓
Question Bank Service
       ↓
Existing Question Generator / Quality Validator
       ↓
Question Repository
       ↓
SQLAlchemy
       ↓
SQLite
```

如果现有 Service 已经可以承担新业务，不必新增 QuestionBankService。

只在职责确实需要时增加最小 Service。

禁止出现第二套：

- 题目生成逻辑。
- 来源验证逻辑。
- 题目去重逻辑。
- PRIMARY 关系检查逻辑。

Router 只负责：

- 请求解析。
- 调用业务服务。
- 返回安全响应。
- 映射业务异常。

不得在 Router 中直接编写数据库查询、题目验证或状态流转规则。

---

# 6. 题目生命周期设计

正式用户流程必须采用：

```text
用户主动请求生成
        ↓
LLM 生成候选题
        ↓
原有结构与来源校验
        ↓
PENDING
        ↓
用户人工审核
       /   \
      /     \
VALIDATED  REJECTED
      |
      ↓
参与诊断组卷
```

核心约束：

**自动校验通过不等于教学内容已经经过人工确认。**

因此 FIX-1 正式 API 生成的题目必须先进入 `PENDING`。

只有审核通过才能转为 `VALIDATED`。

审核拒绝则转为 `REJECTED`。

`PENDING` 和 `REJECTED` 不得进入诊断组卷。

---

# 7. 兼容既有生成器

目前生成器可能在结构验证后直接保存为：

`VALIDATED`

不能全局粗暴替换为 `PENDING`。

先检查：

- 所有生成器调用方。
- 已有测试。
- 内部 Smoke Test。
- 现有状态校验逻辑。
- Repository 写入方式。

推荐通过一个明确、受约束的生成策略或参数，使正式用户流程保存为 `PENDING`。

例如概念上：

```python
generation_service.generate(
    ...,
    initial_status=QuestionValidationStatus.PENDING,
)
```

这仅是示意，不要求使用相同函数签名。

具体实现以实际架构为准。

要求：

1. 正式 API 只允许生成待审核题目。
2. 现有内部调用语义不得意外改变。
3. 不允许前端请求自行指定 `VALIDATED`。
4. 不允许用户通过请求字段绕过审核。
5. 不允许为兼容旧测试而破坏正式审核机制。

如果需要兼容旧的直接验证行为，应限制在明确的既有内部调用路径，记录其使用边界；绝不能通过公开 API 暴露自动发布能力。

优先选择改动量最小、职责最清晰的方案。

---

# 8. 题库准备状态 API

首先检查当前 readiness API 是否已经完整提供：

- 当前合格题数。
- 最低题数。
- 核心节点数。
- 已覆盖节点数。
- `can_start`。
- `reason_code`。
- 目标节点列表或可推导的覆盖需求。

如果当前接口已满足要求：

直接复用。

不要重复新建第二个 readiness API。

如缺少题库准备信息，可以新增轻量查询接口。

建议路径：

```http
GET /api/courses/{course_id}/diagnostic-question-bank
```

最终路径应符合现有 API 命名规范。

响应至少支持：

```json
{
  "course_id": 1,
  "validated_count": 0,
  "pending_count": 0,
  "rejected_count": 0,
  "covered_core_nodes": 0,
  "total_core_nodes": 59,
  "minimum_required": 8,
  "can_start": false,
  "required_nodes": []
}
```

以上为响应结构示例，不代表真实数据。

`required_nodes` 应来自现有组卷规则，而非在新接口中复制一套排序算法。

重要：

GET 请求必须是只读操作。

禁止：

- 自动生成题目。
- 自动调用 LLM。
- 自动审核。
- 修改 readiness。
- 修改数据库状态。

---

# 9. 生成题目 API

增加正式用户主动触发接口。

建议：

```http
POST /api/courses/{course_id}/diagnostic-questions/generate
```

请求 DTO 推荐包含：

```json
{
  "knowledge_node_id": 2,
  "count": 1
}
```

要求：

- 当前课程存在。
- 用户具有当前课程的访问权限。
- 知识模型状态有效。
- 目标节点属于当前课程。
- 目标节点有可验证资料来源。
- 不允许跨课程节点。
- 不接受客户端指定来源文本或虚构 source_refs。
- 不接受客户端传入验证状态。
- 不接受客户端指定正确答案。
- 不接受客户端指定模型密钥或任意 Provider URL。
- 复用已有 Question Generator。
- 使用真实 Provider 时不得静默回退 Mock。

FIX-1 正式用户入口建议固定：

`count = 1`

如果既有生成器支持更多题目，不需要删除内部能力。

公开接口只开放当前最小需求。

---

# 10. 生成成本控制

真实 LLM 调用必须由 POST 显式触发。

禁止：

- 页面查询自动生成。
- readiness 查询自动生成。
- 列表查询自动生成。
- 服务启动自动生成。
- 请求失败后无界重试。

复用当前 Provider：

- Timeout。
- Retry。
- Structured Output。
- Prompt Version。
- Error Mapping。

不得新增 Provider Adapter。

当前模型为：

`deepseek-flash`

但不得硬编码模型名称到业务逻辑。

使用现有配置。

建议单次仅生成一题。

对当前 59 节点课程，第一轮只需要满足前 8 节点的覆盖要求。

不要新增全课程一键批量生成接口。

---

# 11. 重复请求与幂等性

必须处理：

- 用户重复点击。
- 已存在 PENDING 题目。
- 已存在 VALIDATED 题目。
- Provider 超时后用户重试。
- 相同节点重复生成。
- 并发请求。

优先复用原有重复检测和事务保护。

要求：

1. 不得生成内容完全相同的重复题。
2. 如果已有待审核题，应优先引导审核，而不是继续生成。
3. 已覆盖节点不应被默认重复生成。
4. 不得在失败后保存半成品。
5. 并发生成不得产生违反唯一性或状态约束的数据。

注意：

不需要建设企业级任务队列或分布式锁。

采用当前 SQLite/SQLAlchemy 能支持的最小正确策略。

如果无法在当前架构中严格保证网络级 exactly-once，不得声称实现了 exactly-once；应明确描述实际的数据库幂等与重复保护边界。

---

# 12. 题目查询 API

新增或复用：

```http
GET /api/courses/{course_id}/diagnostic-questions
```

支持最小筛选：

```text
status=PENDING
status=VALIDATED
status=REJECTED
```

并支持不指定状态时读取当前课程题目。

API 返回字段至少包括：

- question_id
- course_id
- knowledge_node_id
- knowledge_node_name
- question_type
- difficulty
- stem
- options
- correct_answer
- explanation
- source_refs
- validation_status
- created_at

根据当前 Schema 实际命名调整。

这是**题库审核管理接口**，可以返回标准答案。

但必须严格区分：

**题库审核接口与学生诊断作答接口。**

未提交诊断时，学生作答接口绝不能泄漏正确答案或解析。

当前 V1 是单用户 Demo，因此可通过现有明确的题库管理边界访问审核接口，不要求引入完整 RBAC；但不得将该接口设计成无需任何授权边界、可跨课程枚举答案的公共资源。

---

# 13. 审核通过 API

建议：

```http
POST /api/courses/{course_id}/diagnostic-questions/{question_id}/approve
```

或者符合当前 REST 规范的 PATCH。

审核前必须重新验证：

1. Question 存在。
2. Question 属于当前课程。
3. 用户具有对应课程的管理权限。
4. Question 当前为 PENDING。
5. 题目内容仍符合 Schema。
6. source_refs 仍指向有效材料来源。
7. PRIMARY KnowledgeNode 属于当前课程。
8. 知识节点仍处于有效状态。
9. 知识模型及来源快照未发生不兼容变化。
10. 不存在应当阻止发布的重复题。

全部满足后：

```text
PENDING → VALIDATED
```

必须通过数据库事务完成。

不得只相信题目生成时已经验证的旧状态。

审核成功后，应能通过已有 readiness 服务读取到最新题库状态。

不要新增第二套 readiness 计算逻辑。

---

# 14. 审核拒绝 API

建议：

```http
POST /api/courses/{course_id}/diagnostic-questions/{question_id}/reject
```

当前状态：

`PENDING`

允许转为：

`REJECTED`

要求：

- 检查课程归属。
- 检查题目归属。
- 检查当前状态。
- 正确处理重复拒绝。
- 不删除原始题目。
- 不删除已有来源信息。
- 不影响其他题目。
- 不修改现有诊断结果。

是否增加拒绝原因字段，应根据现有 Model 判断。

如果需要新增字段才可支持拒绝原因，而本阶段并非必要，可以暂不实现自由文本原因。

避免无意义数据库迁移。

---

# 15. 审核状态机

正式支持：

```text
PENDING
  ├── approve → VALIDATED
  └── reject  → REJECTED
```

本阶段不实现：

```text
VALIDATED → PENDING
VALIDATED → REJECTED
REJECTED → VALIDATED
```

除非当前领域模型已明确支持且确有必要。

不实现复杂的版本审核工作流。

非法状态转移应返回明确的业务错误，例如：

`QUESTION_INVALID_STATE`

状态转移必须稳定、可测试。

---

# 16. 题库 readiness 一致性

FIX-1 必须与现有 Assessment Assembly Service 保持一致。

严禁：

- 新接口按 8 题直接判 READY。
- 忽略核心知识节点覆盖要求。
- 将 PENDING 计入合格题。
- 将 REJECTED 计入合格题。
- 将无有效 PRIMARY 关联题目计入合格题。
- 将失效来源题目计入合格题。

所有 readiness 必须直接复用现有组卷逻辑。

重点验证：

**场景 A**

前 8 个核心节点分别有一条合格 VALIDATED 题。

预期：

```text
validated_count = 8
covered_required_nodes = 8
can_start = true
```

前提是现有组卷规则其他条件全部满足。

**场景 B**

仅前 7 个节点被覆盖，第 8 个节点没有合格题。

预期：

```text
can_start = false
```

**场景 C**

已经覆盖前 8 个节点，但其中某题仍为 PENDING。

预期：

```text
can_start = false
```

**场景 D**

如果总合格题数增加到 9，而第 9 个必需节点尚未覆盖：

仍应遵守现有组卷规则。

不得因为曾经 READY 就错误保持 READY。

---

# 17. 安全与异常处理

沿用已有错误结构。

至少区分：

- COURSE_NOT_FOUND
- KNOWLEDGE_NODE_NOT_FOUND
- QUESTION_NOT_FOUND
- QUESTION_INVALID_STATE
- QUESTION_GENERATION_FAILED
- QUESTION_SOURCE_INVALID
- QUESTION_DUPLICATE
- QUESTION_BANK_INSUFFICIENT
- AI_NOT_CONFIGURED
- AI_PROVIDER_ERROR

具体错误码优先复用已有定义。

不得为了此次修复新增大量语义重复的错误码。

要求：

- 不泄漏 API Key。
- 不泄漏完整 Provider 请求。
- 不泄漏内部 Prompt。
- 不返回数据库异常堆栈。
- 不泄漏服务器绝对路径。
- 不允许跨课程修改题目。
- 不允许请求绕过人工审核。

---

# 18. API Schema

所有新增请求和响应必须使用 Pydantic Schema。

严禁：

```python
dict[str, Any]
```

承担全部业务契约。

必要 DTO 可以放在：

`backend/app/schemas/question_generation.py`

但必须避免重复定义已有 Question Schema。

建议区分：

- QuestionGenerationRequest
- QuestionGenerationResponse
- QuestionReviewResponse
- QuestionBankItemResponse
- QuestionBankReadinessResponse

实际类型名称由当前代码风格决定。

所有字段必须有清晰约束。

---

# 19. 数据库规则

优先复用当前 Question Model。

已存在：

- PENDING
- VALIDATED
- REJECTED

因此原则上不需要新增表。

如果只需调整生成时初始状态与审核更新逻辑：

优先不新增 Alembic Migration。

只有在真实 Schema 修改不可避免时才创建迁移。

不得修改已应用的旧 Migration。

不得直接写 SQL 手动插入测试题到用户数据库。

---

# 20. 必要测试范围

本轮不能省略核心测试，但不需要重新测试全部 M0–M6 业务。

优先复用已有：

`test_m4b_question_generation.py`

及当前 M4 Diagnostic API 测试。

仅补充本次新增接口及状态流转测试。

## 20.1 生成 API

至少验证：

T01：正常单节点生成成功，结果为 PENDING。

T02：Provider 未配置时不创建题目。

T03：跨课程节点被拒绝。

T04：无有效来源节点不调用 Provider。

T05：LLM 校验失败不产生半成品。

T06：重复题目不会被重复保存。

T07：同一节点存在待审核题时，不无意义重复生成。

## 20.2 查询 API

T08：仅返回当前课程题目。

T09：PENDING / VALIDATED / REJECTED 筛选正确。

T10：审核接口返回正确答案，但现有学生诊断接口仍不泄漏答案。

## 20.3 审核 API

T11：PENDING → VALIDATED 成功。

T12：PENDING → REJECTED 成功。

T13：非法状态转移被拒绝。

T14：跨课程审核被拒绝。

T15：来源失效时审核通过被拒绝。

T16：PRIMARY 关联无效时审核通过被拒绝。

## 20.4 Readiness

T17：8 道 VALIDATED 题覆盖前 8 个核心节点后 READY。

T18：PENDING 题不计入 READY。

T19：第 9 个必需节点未覆盖时遵循原组卷规则。

## 20.5 回归

T20：现有 M4 题目生成测试继续通过。

T21：现有诊断组卷和诊断结果读取测试继续通过。

T22：M5/M6 相关读取契约未被破坏。

已有测试如果已经覆盖某项，可以复用，不要重复编写。

禁止为提高测试数量而新增无意义测试。

---

# 21. Mock 与真实 Provider

自动化测试必须使用隔离数据库和 Mock LLM Client。

不得在 pytest 中调用真实付费 DeepSeek API。

本轮不需要真实生成当前课程的 8 道题。

正式真实生成属于后续 FIX-2 交互完成后的人工验收步骤。

若需要验证生成接口与真实 Provider 的配置兼容性：

只进行不发起付费请求的配置检查。

不得使用自动 Mock 结果冒充真实用户题库。

---

# 22. 必要工程质量检查

按项目现有命令执行。

至少包括：

Backend：

```bash
pytest
ruff check backend
ruff format --check backend
```

如果项目实际执行目录不同，应以配置文件为准。

前端不在本轮修改范围。

因此无需重新运行完整前端测试和生产构建，除非后端 API 改动实际影响已有前端契约。

必须检查：

```bash
git diff --check
git status --short
git diff --stat
```

确保：

- 没有覆盖用户已有修改。
- 没有修改 Vue 代码。
- 没有修改 M5/M6 算法。
- 没有泄漏密钥。
- 没有引入无关依赖。
- 没有修改用户真实数据库。
- 没有修改上传资料。

---

# 23. 文档要求

新增或更新：

`docs/migration/FIX1_DIAGNOSTIC_QUESTION_BANK_REPORT.md`

内容至少包括：

1. 本次修复目标。
2. 实际复用的已有代码。
3. 实际新增或修改的后端文件。
4. 题目状态流转。
5. 新增 API 契约。
6. 审核与发布规则。
7. 题库 readiness 复用方式。
8. 新增测试。
9. 回归测试结果。
10. 已知限制。
11. FIX-2 前端对接说明。

如果项目已有相关架构文档：

只补充必要章节。

不要重复创建另一套大型架构报告。

---

# 24. FIX-1 验收标准

只有以下全部满足，FIX-1 才能判定 COMPLETE。

AC-01：复用现有 Question Generator。

AC-02：正式生成 API 可用。

AC-03：正式生成结果默认 PENDING。

AC-04：题目查询 API 可用。

AC-05：状态筛选正确。

AC-06：审核通过 API 可用。

AC-07：审核拒绝 API 可用。

AC-08：非法状态流转被拒绝。

AC-09：跨课程访问受到限制。

AC-10：真实来源和 PRIMARY 关联校验有效。

AC-11：PENDING/REJECTED 不参与诊断组卷。

AC-12：VALIDATED 题遵守原有 readiness 规则。

AC-13：重复生成受到限制。

AC-14：生成与审核失败不会留下不一致数据。

AC-15：现有 M4 生成与诊断功能没有回归。

AC-16：M5/M6 相关契约没有被破坏。

AC-17：必要后端测试全部通过。

AC-18：Ruff lint/format 通过。

AC-19：git diff --check 通过。

AC-20：没有进入 FIX-2 或 M7。

---

# 25. 最终终端汇报

完成后按以下格式输出：

==================================================
LearnPilot V1 — FIX-1 Diagnostic Question Bank
==================================================

Existing Generator Reused:
YES / NO

Generation API:
PASS / FAIL

Question Listing API:
PASS / FAIL

Pending Review Flow:
PASS / FAIL

Approve API:
PASS / FAIL

Reject API:
PASS / FAIL

State Transition Validation:
PASS / FAIL

Source Reference Validation:
PASS / FAIL

PRIMARY KnowledgeNode Validation:
PASS / FAIL

Cross-Course Isolation:
PASS / FAIL

Duplicate Generation Protection:
PASS / FAIL

Readiness Compatibility:
PASS / FAIL

Legacy M4 Compatibility:
PASS / FAIL

M5/M6 Contract Safety:
PASS / FAIL

New Tests:
<passed>/<total>

Backend Regression:
<passed>/<total>

Ruff Lint:
PASS / FAIL

Ruff Format:
PASS / FAIL

Database Migration:
NOT REQUIRED / PASS / FAIL

Git Diff Check:
PASS / FAIL

User Data Preserved:
YES / NO

Real LLM Calls:
0

Frontend Modified:
NO

FIX-2 Readiness:
READY / NOT READY

FIX-1 Status:
COMPLETE / NOT COMPLETE

LearnPilot V1 Progress:
72%

Report:
docs/migration/FIX1_DIAGNOSTIC_QUESTION_BANK_REPORT.md

==================================================

---

# 26. 停止条件

如果 FIX-1 全部通过：

输出：

FIX-1 = COMPLETE

FIX-2 = READY

随后立即停止。

不得继续：

- 开发题库管理前端。
- 自动生成当前课程的诊断题。
- 调用真实 LLM。
- 修改诊断结果。
- 修改 Mastery。
- 修改 Learning Evidence。
- 修改 M6 Recommendation。
- 进入 M7。

如果 FIX-1 尚未通过：

输出：

FIX-1 = NOT COMPLETE

并明确列出：

- 阻塞项。
- 具体原因。
- 涉及文件。
- 已执行的最小修复。
- 剩余修复建议。
- 测试结果。

不得声称已完成。

---

# 27. 最终工程原则

Preserve existing verified behavior.

Reuse before implementing.

Do not create a second Question Generator.

Generated does not mean academically validated.

Only reviewed questions may enter formal diagnosis through the new user workflow.

Course ownership is mandatory.

Never trust client-provided validation status.

Never trust client-provided source references.

Do not bypass prerequisite question-bank coverage rules.

Do not modify M5 Mastery or M6 Recommendation.

No real paid LLM calls during automated tests.

No unnecessary infrastructure.

No unrelated refactoring.

No destructive Git operations.

No fabricated PASS.

**本轮最终目标：以最小必要后端改动，完成真实诊断题库生成、查询和人工审核的可复用接口，为 FIX-2 前端用户操作入口提供稳定、准确、安全的业务能力。**

**Codex 过程消息**

我将按 FIX-1 边界实施：先复核 Git 基线、仓库规则和 M4 现状，再以现有生成器为唯一生成路径补充后端题库服务/API、状态流转、测试与报告。不会修改前端、真实数据库或调用真实 LLM。

**Codex 过程消息**

实现方案已收敛：保留内部生成器默认 `VALIDATED` 语义以兼容既有调用；新增一个仅供正式题库 API 使用的受控 `initial_status=PENDING` 参数，并由新的题库服务固定传入，客户端不能指定状态。审核时会重新执行 Schema、质量、来源、唯一 PRIMARY、节点有效性和重复题校验，再用条件更新完成状态迁移。无需数据库迁移。

**Codex 过程消息**

工作区位于 WSL 重解析路径，内置补丁工具无法直接写入该路径。我会改用 WSL 内的补丁应用方式执行同一份最小 diff；不会暂存、提交或改写历史。

**Codex 过程消息**

后端闭环已落到现有 `/api/diagnostics` 路由下：只读 readiness、按状态查询、显式单节点生成、approve、reject。生成 API 固定一题并强制 `PENDING`；GET 不触发生成。现在先做静态检查和针对性测试前的快速导入验证，修正任何契约问题。

**Codex 过程消息**

新增 11 个 FIX-1 测试已通过，覆盖正式生成必为 PENDING、重复待审阻断、列表筛选、答案仅在审核接口返回、批准/拒绝状态机、来源和 PRIMARY 复核、跨课程隔离，以及第 8/第 9 题覆盖边界。接下来运行 M4 关键回归和 M5/M6 读取契约，再处理文档与全量质量检查。

**Codex 过程消息**

FIX-1 专项测试现为 12/12 通过；M4–M6 关键回归此前为 155/155 通过。状态流转和 readiness 使用同一组卷策略，未新增表。现在执行要求的后端全量测试、Ruff 和 Alembic 空库升级验证；这些操作只使用隔离测试数据库。

**Codex 过程消息**

全量后端回归为 347/347 通过，Ruff lint/format 通过，空库 Alembic 从 0001 升级至 0013 head 成功。未新增 migration。接下来只补充 FIX-1 报告并做最终 diff/状态/敏感信息检查。

**Codex 过程消息**

实现与核心回归已完成；我现在做最后一轮只读核验：代码风格、差异完整性、真实数据库未被改写，以及工作区中本轮改动与既有未提交内容的边界。

**Codex 过程消息**

最终核验结果正常：后端代码检查通过，现有数据库仍保持题目、诊断、掌握度和学习证据均为原始计数，本轮没有写入真实业务数据，也未发现凭据模式。接下来只整理验收记录并输出最终结论。

**Codex 最终答复**

FIX-1 已完成。复用了原有 M4 Question Generator，没有修改前端、真实数据库、M5/M6 算法，也未调用真实 LLM。

实际修改：

- [diagnostics.py](/home/<redacted>/projects/campus-ai/backend/app/api/diagnostics.py)：新增题库查询、生成、审核通过和拒绝接口。
- [diagnostic_question_bank_service.py](/home/<redacted>/projects/campus-ai/backend/app/services/diagnostic_question_bank_service.py)：题库业务编排、状态流转及审核时重新校验。
- [diagnostic_question_generation.py](/home/<redacted>/projects/campus-ai/backend/app/services/diagnostic_question_generation.py)：支持受控的初始状态；旧调用仍默认 `VALIDATED`，正式 API 固定生成 `PENDING`。
- [question_repository.py](/home/<redacted>/projects/campus-ai/backend/app/repositories/question_repository.py)：课程隔离查询、状态筛选和条件状态转换。
- [assessment_assembly_service.py](/home/<redacted>/projects/campus-ai/backend/app/services/assessment_assembly_service.py)：公开复用原组卷规则的 readiness 预览，不改变门槛。
- [question_generation.py](/home/<redacted>/projects/campus-ai/backend/app/schemas/question_generation.py)：新增严格的请求及响应 DTO。
- [test_fix1_diagnostic_question_bank.py](/home/<redacted>/projects/campus-ai/backend/tests/test_fix1_diagnostic_question_bank.py)：新增 12 项 FIX-1 测试。
- [FIX1_DIAGNOSTIC_QUESTION_BANK_REPORT.md](/home/<redacted>/projects/campus-ai/docs/migration/FIX1_DIAGNOSTIC_QUESTION_BANK_REPORT.md)：实施及验收报告。

验证结果：

```text
==================================================
LearnPilot V1 — FIX-1 Diagnostic Question Bank
==================================================

Existing Generator Reused: YES
Generation API: PASS
Question Listing API: PASS
Pending Review Flow: PASS
Approve API: PASS
Reject API: PASS
State Transition Validation: PASS
Source Reference Validation: PASS
PRIMARY KnowledgeNode Validation: PASS
Cross-Course Isolation: PASS
Duplicate Generation Protection: PASS
Readiness Compatibility: PASS
Legacy M4 Compatibility: PASS
M5/M6 Contract Safety: PASS

New Tests: 12/12
Backend Regression: 347/347
Ruff Lint: PASS
Ruff Format: PASS
Database Migration: NOT REQUIRED
Git Diff Check: PASS
User Data Preserved: YES
Real LLM Calls: 0
Frontend Modified: NO

FIX-2 Readiness: READY
FIX-1 Status: COMPLETE
LearnPilot V1 Progress: 72%
==================================================
```

当前分支为 `main`，HEAD 为 `0a21c38ae9f52a549d38a78c9fcc3852fe2871b5`。既有未提交工作全部保留，未执行 commit、push 或破坏性 Git 操作。

重复生成保护采用数据库状态检查、条件状态转换和进程内节点锁；适合当前单实例 SQLite 部署，但不宣称跨进程 exactly-once。

**FIX-1 = COMPLETE**
**FIX-2 = READY**

---

## 02.04 · 2026-10-22 18:35:14

来源：LearnPilot V1 — M6-修复 · [在 Codex 打开](codex://threads/01a16242-c402-7120-8185-3ce1ee73a526)

回合 ID：`01a1632d-e2cd-7d93-8958-e3d0ee511e25`

**用户 Prompt**

# LearnPilot V1 — FIX-2 Diagnostic Question Bank UI & Review Integration

你现在作为 LearnPilot V1 的 Senior Frontend Engineer、AI Product Engineer 和 Software QA Engineer，继续执行 M4–M6 浏览器人工验收所需的最小业务闭环修复。

当前状态：

- M0–M5：COMPLETE
- M6-1～M6-5：COMPLETE
- M6 进度：72%
- FIX-1：后端题库准备与审核 API 已实现并通过验收
- FIX-2：当前待开发
- M7：尚未开始

本阶段完成后，LearnPilot V1 正式开发进度仍为 72%，不额外增加进度百分比。

本轮目标：

**复用 FIX-1 正式 API，为普通用户建立最小、清晰、安全的诊断题库生成、查看、人工审核和 readiness 更新交互，使用户能够通过浏览器完成题库准备，并进入已有的 M4 诊断流程。**

遵循：

企业级代码规范 + 科研竞赛级实现复杂度。

最小必要修改，不重复开发，不扩大业务范围。

---

## 一、不可违反的两项核心原则

### 原则 1：前端不得直接修改真实题目状态

题目的状态流转只能通过 FIX-1 已实现的正式 API 完成。

例如：

PENDING → VALIDATED

PENDING → REJECTED

必须由后端负责：

- 校验当前题目状态
- 校验课程归属
- 校验用户操作权限
- 重新执行必要的题目有效性检查
- 校验 source_refs
- 校验 PRIMARY KnowledgeNode 关联
- 执行数据库事务
- 返回最终状态

前端只能：

1. 展示服务端返回的当前状态。
2. 在用户点击审核按钮后发起正式 API 请求。
3. 等待服务端响应。
4. 使用服务端返回值或重新 GET 的结果更新页面。

**禁止直接修改本地题目对象并把它当作审核成功。**

可以展示独立的“审核提交中”Loading 状态，但不得乐观更新真实 `validation_status`。

如果后端审核失败，题目必须继续显示服务端原有状态。

### 原则 2：绝不自动批量调用 DeepSeek

禁止：

- 页面加载自动生成题目
- 页面刷新自动生成题目
- 循环遍历知识节点自动生成题目
- 一键生成 8 道题
- 一键补齐题库
- 自动重试整批节点
- 审核通过后自动生成下一节点题目
- readiness 未达标时自动触发生成
- 为了达到题量而自动重复生成同一节点题目

本阶段只允许：

**用户明确选择一个知识节点 → 点击生成 → 确认真实 LLM 调用 → 生成一道题 → 人工审核 → 刷新 readiness。**

下一道题必须再次由用户主动触发。

即使当前课程距离最低要求还差 8 道，也不得自动生成。

---

## 二、开始前必须检查真实仓库

不要根据历史 Prompt 猜测 FIX-1 的 API 契约。

首先读取：

1. FIX-1 实际代码变更。
2. FIX-1 开发与验收报告（如存在）。
3. 当前 FastAPI OpenAPI Schema。
4. 现有 diagnostics Router。
5. FIX-1 新增的请求、响应 DTO。
6. Question Generator 的正式 Service 调用方式。
7. Question Repository。
8. 审核状态流转及错误码。
9. 前端 `diagnostics.ts`。
10. 前端 `diagnostic.ts`。
11. `CourseDetailView.vue`。
12. `DiagnoseView.vue`。
13. M6 前端当前代码和测试基线。

确认实际存在的：

- 题库 readiness 查询 API
- 题目列表 API
- 单节点生成 API
- 审核通过 API
- 拒绝题目 API
- 状态刷新 API 或对应 readiness GET

记录其：

Method、Path、Request Schema、Response Schema、Error Codes。

**所有接口路径和字段以 FIX-1 真实代码为准。不得擅自发明一套新 API。**

如果 FIX-1 缺少完成关键交互所必需的接口：

先确认是否已有等价能力。

确实缺失时，记录阻塞项；不得自行开发第二套后端题库管理接口。

---

## 三、Git 安全

开发前执行：

git status --short --branch
git branch --show-current
git diff --check

记录现有工作区状态。

当前可能存在未提交的 M4–M6、FIX-1 修改。

必须完整保护。

禁止：

git reset --hard
git clean -fd
git restore .
git checkout .
git stash

未经用户授权：

不得 commit、push、merge、rebase、tag 或切换分支。

---

# 四、FIX-2 的正式开发范围

原则上只修改前端必要文件。

优先：

frontend/src/services/diagnostics.ts

frontend/src/types/diagnostic.ts

frontend/src/views/CourseDetailView.vue

如已有组件结构要求，可在 Course Feature 中新增少量必要组件。

允许新增：

- 题库准备状态组件
- 待审核题目组件
- 题目审核 Dialog / Drawer

但是不得为了拆分而建立大型组件系统。

`DiagnoseView.vue` 原则上保持不变。

只有确实需要调整“题库已准备好”的引导或跳转行为时，才允许进行最小修改。

不得修改：

- M3 Knowledge Graph
- M4 Diagnostic Core
- M5 Mastery
- M6 Recommendation Engine
- M6 LearningPlan
- LLM Provider Adapter
- Question Generator
- FIX-1 正式审核逻辑

---

# 五、UI 结构：课程详情增加“诊断题库准备”区域

在现有 Course Detail 中增加一个清晰、独立但不过度突出的区域：

**诊断题库准备**

不要新增一级导航。

不要建立复杂题库后台。

不要把题库管理和诊断答题混到同一个页面。

建议界面结构：

诊断题库准备

当前合格题：0 / 最低 8 题

当前覆盖：0 / 59 个核心知识节点

状态：尚未满足诊断要求

说明：需要为指定核心知识节点准备经过审核的诊断题。

下方：

待覆盖知识节点列表

每个节点展示：

- 知识节点名称
- 节点 ID（仅在必要时）
- 是否已有合格诊断题
- 当前待审核题目数量（若 API 提供）
- 来源是否充足（若 API 提供）
- 生成一道题的操作入口

不要显示未经服务端确认的状态。

---

# 六、题库 readiness 展示

所有 readiness 数值必须来自 FIX-1 正式 API。

至少展示：

- 当前合格题目数
- 最低所需题目数
- 当前核心知识节点覆盖数
- 核心知识节点总数
- can_start
- reason_code 或当前阻塞原因

如果 FIX-1 提供目标覆盖节点、待覆盖节点或下一建议节点：

直接复用服务端结果。

不要在前端自行重新实现 M4 的组卷排序算法。

特别注意：

当前“计算机系统”课程有 59 个核心节点，但最低 8 题不代表要求覆盖全部 59 个节点。

界面不得误导用户认为：

“必须完成 59 道题才能开始诊断”。

文案建议：

“当前已有 0 道合格题，开始诊断至少需要 8 道，并满足对应知识点覆盖要求。”

实际数字以 API 为准。

---

# 七、知识节点列表及生成规则

当前初始恢复场景为：

计算机系统课程

前 8 个目标核心节点：

1. 小端法（小端序）
2. 位级运算与逻辑运算
3. 补码表示
4. 有符号与无符号转换
5. 整数溢出
6. x86-64 有效地址
7. 条件码
8. 过程调用约定

注意：

以上仅为已知审查基线，不得把这些节点名称或 ID 写死进前端。

必须根据后端当前目标节点数据动态渲染。

如果 FIX-1 未提供待覆盖节点列表，检查是否存在可复用的课程知识节点接口，并由服务端已有 readiness/组卷规则确定当前目标节点。

不得自行按名称或 ID 猜测排序。

默认只允许对尚未覆盖、且没有待审核题目的目标节点生成题目。

如果已有 PENDING：

优先展示待审核题目。

如果已有 VALIDATED：

默认禁用重复生成。

如果已有 REJECTED：

根据 FIX-1 正式接口规则允许用户再次手动生成。

---

# 八、生成题目的用户交互

点击：

“生成一道题”

后不得立即发送模型请求。

必须先弹出确认 Dialog。

文案应明确：

“将基于当前知识点关联的课程资料调用真实 AI 生成 1 道诊断题。此操作可能产生模型调用费用，生成后仍需人工审核。”

Dialog 至少包含：

- 当前知识节点名称
- 生成数量：1 道，固定
- 真实模型调用提示
- 取消按钮
- 确认生成按钮

不提供：

- 批量数量输入框
- 一键补齐
- 自动生成剩余题目
- 自动审核选项

只有用户明确点击确认，才能调用 FIX-1 生成 API。

---

# 九、API 请求次数与防重复

单次生成操作必须满足：

1. 用户主动点击生成。
2. 弹出确认 Dialog。
3. 用户点击确认。
4. 发起一次生成 API 请求。
5. 等待请求结果。
6. 更新题目列表。
7. 显示待审核题目。
8. 不自动生成下一题。

前端必须有同步的请求锁或等价状态保护。

请求进行中：

- 禁用当前生成按钮
- 禁用确认按钮的重复提交
- 显示“正在生成诊断题”
- 不允许同一节点重复发送请求

关闭 Dialog、重复点击或页面重新渲染均不得造成重复 POST。

不要对付费生成 POST 设置前端自动重试。

如果网络超时且无法确认服务端是否已成功写入：

**不要立即重新调用生成。**

应先刷新题目列表和 readiness，确认是否已有新题目，再由用户决定下一步。

---

# 十、生成结果展示

生成成功后，必须使用 API 返回的真实题目数据。

不能构造 Mock 题目。

如果题目状态为 PENDING：

显示：

“待审核”

并提供：

“查看并审核”

如果 FIX-1 采用其他正式状态命名：

以实际契约为准。

若生成失败：

显示后端返回的明确错误。

例如：

- 当前节点来源不足
- 当前题目已存在
- AI Provider 未配置
- AI 请求失败
- AI 输出不符合 Schema
- 生成题目与现有题目重复

错误提示应简洁、对普通用户友好。

不要展示堆栈、Prompt 或 Provider 内部敏感信息。

---

# 十一、题目人工审核 UI

使用现有 Element Plus / LearnPilot 视觉规范实现轻量审核 Dialog 或 Drawer。

必须完整展示：

- 关联知识点
- 题目类型
- 题目难度
- 题干
- 选项
- 正确答案
- 答案解析
- 来源材料
- 来源定位或引用

如果题目类型为单选、多选或判断：

按照真实题型展示。

不要只显示：

“这道题是否正确？”

审核者必须能够看到答案与来源，以判断题目是否存在学科错误。

不得显示不存在的来源页码。

若 FIX-1 的 API 未返回可供核查的完整内容：

不允许前端编造。

必须报告该阻塞项。

---

# 十二、审核操作

审核界面提供：

“审核通过”

“拒绝题目”

以及：

“关闭”

三类操作。

点击审核通过：

调用 FIX-1 正式审核 API。

点击拒绝：

调用 FIX-1 正式拒绝 API。

审核状态不得直接由前端修改。

禁止：

question.validation_status = 'VALIDATED'

然后只更新页面。

必须等待服务端结果。

请求过程中：

- 禁用审核按钮
- 显示“正在提交审核”
- 防止重复请求
- 不允许同时提交通过和拒绝

审核失败：

- 保留原有状态
- 展示真实错误提示
- 允许安全重试
- 不得假装通过

审核成功：

- 刷新正式题目列表
- 刷新 readiness
- 根据后端结果显示最终状态
- 不自动生成下一题

---

# 十三、审核与来源的安全边界

前端只是人工审核入口。

后端仍是唯一可信业务边界。

不要在前端实现：

- 题目最终合法性判定
- source_refs 权威验证
- PRIMARY 关联事务
- 状态直接持久化
- 跨课程权限规则

如果审核 API 返回题目来源失效、知识节点已变化或状态冲突：

展示明确错误。

必要时提示：

“题目或来源状态已发生变化，请刷新后重新检查。”

不得绕过后端重新验证。

---

# 十四、审核后刷新 readiness

这是 FIX-2 的核心闭环。

每次成功审核后，必须重新获取真实 readiness。

例如：

生成一道题

→ PENDING

→ 用户审核通过

→ 后端返回 VALIDATED

→ 重新 GET readiness

→ 合格题数增加

→ 对应知识节点覆盖状态更新

但不能仅通过前端将计数加一。

必须以服务端返回值为准。

如果题目被拒绝：

合格题数不得增加。

如果返回 readiness 仍未满足：

继续显示待覆盖节点。

但绝不自动生成下一题。

---

# 十五、达到 READY 后的行为

当服务端返回：

can_start = true

或等价 READY 状态时：

界面显示：

“诊断题库已准备完成，可以开始学习诊断。”

提供：

“前往诊断”

按钮。

点击后跳转到现有 Diagnose 页面。

如果当前 Diagnose 页面支持课程 ID 路由参数或 Query：

按既有路由契约传递当前课程。

如果已有统一选课状态：

复用现有状态。

不要另建第二套课程选择机制。

跳转不能自动提交诊断，也不能自动生成其他题目。

原有 Diagnose 页面仍通过自己的 readiness 检查决定是否允许开始诊断。

---

# 十六、空状态与失败状态

必须处理：

1. 题库完全为空。
2. 有 PENDING 题目。
3. 部分题目 VALIDATED。
4. 存在 REJECTED 题目。
5. 题库已 READY。
6. 课程没有知识模型。
7. 当前节点没有可用来源。
8. Provider 配置缺失。
9. 请求超时。
10. 审核发生状态冲突。
11. readiness GET 失败。

各状态都应该有明确的用户提示和下一步操作。

不要只有“加载失败”。

对于模型请求失败或未知结果：

不得自动再次调用付费接口。

---

# 十七、UX 设计要求

延续 LearnPilot 已有设计语言：

Calm Academic Intelligence。

要求：

- 简体中文
- 视觉简洁
- 信息层级明确
- 不引入新的一级导航
- 不使用功能宫格
- 不新增复杂后台管理界面
- 优先复用现有组件
- 题库状态与生成操作放在同一区域
- 审核 Dialog 信息完整但不拥挤
- 避免大量不必要的确认弹窗

生成操作需要二次确认。

审核操作可根据风险使用现有确认行为，但不要层层弹窗。

如果当前环境中已有 frontend-design Skill，可以读取并用于这一小块界面的布局、层级和交互优化。

Skill 不得扩大开发范围或引入大量新依赖。

---

# 十八、API 与类型要求

所有请求必须走现有：

frontend/src/services/diagnostics.ts

或已有统一 API Service。

不得在 Vue 模板和页面逻辑中散落 axios 请求。

新增 TypeScript 类型应与 FIX-1 Pydantic Schema 一致。

禁止使用 any 绕过类型检查。

不得重复定义已有的：

Question
ValidationStatus
Readiness
KnowledgeNode

等公共类型。

优先复用已存在的类型。

---

# 十九、测试策略：只测新增交互

FIX-1 已通过后端验收。

本轮不重新编写后端题目生成、来源验证和事务处理测试。

重点使用 Vitest / Vue Test Utils，Mock HTTP API 验证前端交互。

至少覆盖以下用例。

### T01 — 只读加载

打开 Course Detail：

- 可以获取 readiness
- 可以获取题目列表
- 不发送生成 POST
- 不发送审核 POST

### T02 — 生成确认

用户点击生成按钮：

- 只打开确认 Dialog
- 此时不调用 LLM 生成 API

点击“确认生成”后：

- 只发送一次 POST
- 固定生成数量为 1
- 目标节点 ID 正确

### T03 — 防重复

生成请求未结束时：

- 禁用重复点击
- 不产生第二个 POST

### T04 — 生成成功

服务端返回 PENDING：

- 显示待审核
- 可以打开审核界面
- 不自动生成下一题

### T05 — 生成失败

API 返回错误或超时：

- 显示错误
- 不伪造题目
- 不自动重试付费 POST
- 用户可以刷新状态

### T06 — 审核通过

点击“审核通过”：

- 调用 FIX-1 正式审核 API
- 调用次数为 1
- 等待服务端返回
- 成功后刷新题目及 readiness
- 不提前在前端把状态改为 VALIDATED

### T07 — 审核拒绝

点击“拒绝题目”：

- 调用正式拒绝 API
- 服务端返回 REJECTED 后更新界面
- 不增加合格题数

### T08 — 审核失败

如果审核返回冲突或失败：

- 保留原状态
- 显示错误
- 支持刷新
- 不出现乐观成功提示

### T09 — readiness 更新

审核通过后：

- 根据真实 API 返回更新合格题数和覆盖数
- 不直接在前端加一
- 未 READY 时不自动生成下一题

### T10 — READY 跳转

当后端返回 can_start=true：

- 显示前往诊断
- 点击后进入已有 Diagnose 页面
- 当前课程选择正确
- 不自动创建诊断记录
- 不调用题目生成 API

### T11 — 状态与空态

验证：

- loading
- empty
- error
- PENDING
- VALIDATED
- REJECTED
- READY

至少覆盖影响主要交互的关键状态。

如果部分测试已经存在且覆盖相同逻辑：

复用，不重复开发。

---

# 二十、避免不必要的测试

本轮不要求：

- 再次逐项测试 347 个后端业务用例
- 重新测试 Question Generator 的所有 LLM 规则
- 重新测试 M3 Knowledge Graph
- 重新测试 M4 Assessment 组卷算法
- 重新测试 M5 Mastery 计算
- 重新测试 M6 Recommendation Engine
- 真实调用 8 次 DeepSeek
- 进行大规模 AI 质量评测
- 建立完整 Playwright E2E 自动化
- 进行数据库迁移压力测试

本轮前端开发测试必须使用 Mock HTTP，不产生真实付费调用。

已有完整后端测试可以在最终集成验收时运行一次，以确认无回归，但不需要围绕所有旧业务重新设计测试用例。

---

# 二十一、工程验证

完成代码后，必须执行：

Frontend：

npm run typecheck
npm run lint
npm run test
npm run build

以上从 frontend 目录执行。

必须：

0 failed。

Backend：

如果本轮完全没有修改 backend：

不需要重新运行全部 347 项后端测试。

如果涉及必要后端兼容修复：

先运行受影响的 FIX-1 / M4 测试，再执行必要回归。

无论如何，不得删除或弱化已有测试。

Git：

git diff --check

必须 PASS。

检查：

- 没有 secret
- 没有无关文件修改
- 没有新增 M7 功能
- 没有覆盖用户已有工作
- 没有真实测试数据误入仓库

---

# 二十二、浏览器验收

如果当前环境具备可用浏览器：

只需验证以下核心路径：

打开“计算机系统”课程

→ 查看真实 readiness

→ 选择一个待覆盖知识节点

→ 打开生成确认 Dialog

→ 取消后确认没有 POST

→ 查看已有 PENDING 测试题（如存在）

→ 审核后刷新 readiness

→ READY 时跳转 Diagnose

不得为了验证浏览器交互而自动连续调用真实 DeepSeek。

若没有 PENDING 测试题或 READY 数据：

可以通过隔离测试环境的 Mock API 验证对应 UI。

不得在真实数据库中伪造题目状态。

如果浏览器不可用：

记录：

BROWSER_CHECK = NOT VERIFIED

不得伪装 PASS。

浏览器不可用不阻塞已通过的自动化前端测试，但最终用户人工验收仍应单独完成。

---

# 二十三、文档与交付

尽量只更新已有 FIX-1 / M4 相关文档。

若需要新增报告：

docs/migration/FIX2_DIAGNOSTIC_QUESTION_BANK_UI.md

报告必须包括：

1. 实际修改文件。
2. 复用的 FIX-1 API。
3. 题库 readiness 展示。
4. 题目生成交互。
5. 人工审核流程。
6. 禁止自动批量调用的具体实现。
7. API 请求次数控制。
8. 错误、超时与冲突处理。
9. 测试用例及结果。
10. 浏览器验收状态。
11. 对 M4–M6 原有功能的影响。
12. 遗留问题。

不要生成大量重复的架构文档。

---

# 二十四、FIX-2 最终验收标准

只有以下条件全部满足，FIX-2 才算完成：

AC-01：Course Detail 存在清晰的诊断题库准备区域。

AC-02：题库数量和覆盖率全部来自后端。

AC-03：目标知识节点由真实 API 提供或基于已有正式契约读取，不硬编码。

AC-04：页面加载、刷新不调用生成 POST。

AC-05：生成必须用户主动触发并确认。

AC-06：单次只生成一个节点的一道题。

AC-07：不存在自动批量生成流程。

AC-08：生成中重复点击不会产生多次 POST。

AC-09：生成成功后展示服务端真实 PENDING 题目。

AC-10：审核界面完整展示题目、答案、解析和来源。

AC-11：审核通过只调用 FIX-1 正式 API。

AC-12：审核拒绝只调用 FIX-1 正式 API。

AC-13：前端不乐观修改 validation_status。

AC-14：审核失败时不会显示虚假成功。

AC-15：审核成功后刷新题库列表及 readiness。

AC-16：合格题目数不由前端自行计算增加。

AC-17：READY 状态支持跳转现有 Diagnose 页面。

AC-18：跳转后选中课程正确。

AC-19：Loading / Empty / Error / Retry 状态完整。

AC-20：TypeScript 类型与后端契约一致。

AC-21：新增关键交互测试通过。

AC-22：Frontend typecheck、lint、test、build 全部通过。

AC-23：git diff --check 通过。

AC-24：未修改 M5/M6 业务逻辑。

AC-25：未提前开发 M7。

AC-26：没有真实 LLM 自动调用或无授权付费请求。

AC-27：用户已有 Git 修改全部保留。

---

# 二十五、最终终端汇报格式

==================================================
LearnPilot V1 — FIX-2 Frontend Acceptance
==================================================

FIX-1 API Contract Reused:
PASS / FAIL

Question Bank Readiness UI:
PASS / FAIL

Knowledge Node Selection:
PASS / FAIL

Generation Confirmation:
PASS / FAIL

One Node One Question:
PASS / FAIL

Automatic Batch Generation:
NO / YES

Generation POST Count Control:
PASS / FAIL

Pending Question Display:
PASS / FAIL

Question Review Detail:
PASS / FAIL

Approve Via Official API:
PASS / FAIL

Reject Via Official API:
PASS / FAIL

Frontend Direct State Mutation:
NO / YES

Review Failure Handling:
PASS / FAIL

Readiness Refresh:
PASS / FAIL

READY Navigation:
PASS / FAIL

Loading / Empty / Error:
PASS / FAIL

Frontend Tests:
<passed>/<total>

TypeScript:
PASS / FAIL

ESLint:
PASS / FAIL

Production Build:
PASS / FAIL

Backend Changed:
NO / YES

Backend Regression:
NOT REQUIRED / PASS / FAIL

Real LLM Calls:
0

Browser Verification:
PASS / NOT VERIFIED / FAIL

Git Diff Check:
PASS / FAIL

Scope Violation:
NO / YES

FIX-2 Status:
COMPLETE / NOT COMPLETE

M6 Status:
COMPLETE

LearnPilot V1 Project Progress:
72%

M7 Readiness:
READY / BLOCKED BY INTEGRATION ISSUE

Report:
docs/migration/FIX2_DIAGNOSTIC_QUESTION_BANK_UI.md

==================================================

---

# 二十六、停止条件

如果 FIX-2 完成：

立即停止。

不要开始实际批量生成诊断题。

不要自动调用 DeepSeek 生成 8 道题。

不要自动进行人工审核。

不要启动新的诊断记录。

不要修改 M5 Mastery。

不要执行 M6 推荐重新计算。

不要进入 M7。

向用户报告：

FIX-2 = COMPLETE

并给出下一步浏览器人工验收操作建议。

如果 FIX-2 未完成：

报告具体阻塞项、对应代码位置、最小修复建议和需要重新执行的测试。

禁止扩大工作范围。

---

# 最终工程原则

1. Frontend is not the authority for question validation.
2. All review transitions go through FIX-1 official APIs.
3. Generation requires explicit user confirmation.
4. One node, one question, one user action.
5. No automatic batch generation.
6. No optimistic validation status updates.
7. Server readiness is the single source of truth.
8. Paid LLM operations must never retry automatically from the UI.
9. Reuse existing M4/FIX-1 functionality.
10. Preserve M5/M6 correctness.
11. Keep changes minimal and test the new interactions only.
12. Competition-grade engineering, not production SaaS infrastructure.

最终目标：

**以最小前端改动，将 FIX-1 的正式诊断题库生成与审核 API 转化为普通用户真正可操作的产品界面，使用户能够逐节点准备合格诊断题，最终通过正常业务流程完成初始诊断，并为 M5/M6 的真实浏览器验收提供数据前置条件。**

**Codex 过程消息**

我会先以 FIX-1 的真实路由和 DTO 为准核对契约，再检查课程详情页、现有前端服务与测试结构。现有未提交的 M4–M6/FIX-1 工作会原样保留；本轮只处理必要的前端文件和报告。

**Codex 过程消息**

契约核对完成：FIX-1 已提供完整的 readiness、列表、单题生成、通过和拒绝接口，且管理列表包含答案、解析和来源，无后端缺口。本轮会新增一个课程详情内的轻量题库面板，并扩展现有诊断类型与服务；不会改动后端或 Diagnose 核心流程。

**Codex 过程消息**

工作区位于 WSL 的 UNC 路径，内置补丁工具被重解析点限制拒绝访问。我会改用带精确匹配校验的本地文本更新方式；每次替换都会在原片段不匹配时立即失败，避免覆盖既有改动。

**Codex 过程消息**

当前 WSL 环境没有 Linux Node，可用依赖安装在桌面应用的工作区运行时中。我会读取该运行时路径，并使用现有依赖执行格式化与前端验证，不安装任何新包。

**Codex 过程消息**

前端类型检查已通过。首次运行 Vitest 时发现当前依赖目录安装的是 Linux 可选二进制，而桌面运行时提供的是 Windows Node，二者平台不匹配；我会先只读查找项目此前使用的 Linux Node 运行时，避免重装或清理依赖。

**Codex 过程消息**

核心交互测试已通过（8/8），包括确认前零 POST、生成中防重复、审核失败不乐观更新、审核后重新读取 readiness，以及 READY 跳转携带课程。现在执行前端全量回归，检查新增面板是否影响现有课程详情和 M6 页面。

**Codex 过程消息**

全量前端回归已通过：23 个测试文件、124 项测试全部成功。现有诊断答题测试仍有两条历史 Vue 事件警告，但没有失败，且与 FIX-2 无关；题库面板测试没有警告。现在继续生产构建和最终差异检查。

**Codex 过程消息**

自动化质量门已全部通过。当前还具备浏览器检查能力，因此我会使用已安装的计算机操作规范，仅验证课程详情、生成确认弹窗和取消路径；不会确认生成、不会调用 DeepSeek，也不会修改真实数据库。

**Codex 过程消息**

浏览器辅助进程连续两次初始化失败，因此按工具恢复规则停止 UI 操作，记录 `BROWSER_CHECK = NOT VERIFIED`；没有打开生成确认、更没有触发真实模型请求。自动化前端测试已覆盖同一交互路径，这不影响 FIX-2 代码验收，但真实浏览器人工验收仍需你随后完成。

**Codex 最终答复**

FIX-2 已完成，项目进度保持 72%。

主要改动：

- [QuestionBankPanel.vue](/home/<redacted>/projects/campus-ai/frontend/src/components/diagnostic/QuestionBankPanel.vue)：readiness、逐节点生成确认、题目详情及人工审核。
- [diagnostics.ts](/home/<redacted>/projects/campus-ai/frontend/src/services/diagnostics.ts)：复用 FIX-1 正式 API。
- [diagnostic.ts](/home/<redacted>/projects/campus-ai/frontend/src/types/diagnostic.ts)：补充严格 TypeScript 契约。
- [CourseDetailView.vue](/home/<redacted>/projects/campus-ai/frontend/src/views/CourseDetailView.vue)：接入诊断题库准备区域。
- [question-bank-panel.spec.ts](/home/<redacted>/projects/campus-ai/frontend/src/tests/question-bank-panel.spec.ts)：新增 8 项关键交互测试。
- [FIX2_DIAGNOSTIC_QUESTION_BANK_UI.md](/home/<redacted>/projects/campus-ai/docs/migration/FIX2_DIAGNOSTIC_QUESTION_BANK_UI.md)：实施与验收报告。

验收结果：

```text
FIX-1 API Contract Reused: PASS
Question Bank Readiness UI: PASS
Knowledge Node Selection: PASS
Generation Confirmation: PASS
One Node One Question: PASS
Automatic Batch Generation: NO
Generation POST Count Control: PASS
Pending Question Display: PASS
Question Review Detail: PASS
Approve / Reject Via Official API: PASS
Frontend Direct State Mutation: NO
Review Failure Handling: PASS
Readiness Refresh: PASS
READY Navigation: PASS
Loading / Empty / Error: PASS

Frontend Tests: 124/124
TypeScript: PASS
ESLint: PASS
Production Build: PASS
Backend Changed: NO
Backend Regression: NOT REQUIRED
Real LLM Calls: 0
Browser Verification: NOT VERIFIED
Git Diff Check: PASS
Scope Violation: NO

FIX-2 Status: COMPLETE
M6 Status: COMPLETE
LearnPilot V1 Progress: 72%
M7 Readiness: READY
```

浏览器辅助进程初始化失败两次，因此未虚报浏览器验收通过，也未触发任何生成请求。

下一步人工验收建议：

1. 打开“计算机系统”课程详情。
2. 查看“诊断题库准备”区域的真实数量及目标节点。
3. 点击“生成一道题”，检查确认弹窗后先取消。
4. 再按需确认生成一题并人工审核。
5. 审核后确认 readiness 从服务端更新。
6. 达到 READY 后点击“前往诊断”。

没有自动生成题目、调用 DeepSeek、创建诊断记录或修改 Mastery/Evidence。所有既有未提交工作均已保留。

---
