# LearnPilot 分阶段开发日志

本日志同时记录当前 LearnPilot V1 里程碑和早期 V0.1 原型演进。M8 和后续 UX-FIX 专项已完成，项目以 90% 进入 M9；M9-A 完成后为 91%，下方 V0.1 阶段表仅用于历史追溯。

## LearnPilot V1 里程碑

| 里程碑 | 目标 | 已实现边界 | 验证与状态 |
| --- | --- | --- | --- |
| M0 | 迁移审计 | 盘点原型资产、能力矩阵和技术债，明确 JSON/原生前端迁移范围。 | 审计文档已保存于 `docs/migration/`。 |
| M1-A | 关系型数据基础 | 引入 SQLAlchemy、Alembic、owner 归属、课程/资料表、显式旧 JSON 导入器和 SQLite 真实迁移测试。 | 迁移与回归测试通过；见 [M1-A 数据基础](architecture/M1A_DATA_FOUNDATION.md)。 |
| M1-B | Vue 前端架构 | 将活动前端迁移至 Vue 3 + TypeScript + Vite，提供五个一级路由、真实课程列表和诚实空状态。 | 类型检查、lint、测试和生产构建记录见 [M1-B 报告](migration/M1B_FRONTEND_REPORT.md)。 |
| M2 | 课程与资料闭环 | 支持课程 CRUD、TXT/MD/PDF/DOCX 上传解析、完整正文持久化、结构化摘要、学习卡片和单资料问答。 | SQLite、后端、前端及浏览器流程已验证；真实 provider 和 MySQL 8 尚未 smoke test。 |
| M3-A | 知识模型基础 | 增加课程知识节点、关系、资料来源、数据库约束、仓储/服务层和两个只读 API。 | 阶段回归 `93/93`；见 [M3-A 报告](migration/M3A_IMPLEMENTATION_REPORT.md)。 |
| M3-B | AI 知识抽取 | 从已解析资料的有界分段中生成候选知识点，严格校验引用并持久化运行与候选来源。 | 阶段回归 `110/110`，真实 DeepSeek smoke 通过。 |
| M3-C | 知识归一化 | 先确定性精确分组，再保守判断语义同一性，生成活动规范节点并传播来源证据。 | 阶段回归 `125/125`，跨资料归一化 smoke 通过。 |
| M3-D | 知识关系 | 生成并验证 `CONTAINS` 无环森林和 `PREREQUISITE` DAG，保存运行与关系证据。 | SQLite 约束、幂等、失败保留和真实 provider smoke 通过。 |
| M3-E | 知识结构前端 | 在课程详情中增加懒加载知识结构图、关系筛选、节点/边证据抽屉和课程级构建入口。 | 后端 `139/139`、前端 `31/31`、typecheck/lint/build 与浏览器验收通过。 |
| M4 | 学习诊断 | 知识点题目生成与审核、组卷、可恢复作答、确定性评分和诊断报告。 | 见 [M4 最终验收](migration/M4_FINAL_ACCEPTANCE_REPORT.md)。 |
| M5 | 学生知识状态 | 从已提交诊断生成 Learning Evidence，并计算可解释的 Mastery/Confidence。 | 见 [M5 最终验收](migration/M5_FINAL_ACCEPTANCE_REPORT.md)。 |
| M6 | 推荐与学习计划 | 先修约束推荐、计划持久化与复用、首页/学习页展示；补充课程级诊断题准备和资料同步流程。 | 阶段报告最近一次回归：后端 `359/359`、前端 `143/143`；见 [M6 实施报告](migration/M6_IMPLEMENTATION_REPORT.md) 和 [体验完善](migration/M6_UX_FIX_5_REPORT.md)。 |
| M7 | 学习执行与反馈 | 可恢复学习会话、来源资料、AI 导师、自适应练习、证据结算和掌握/推荐刷新。 | 验收报告记录后端 `410/410`、前端 `181/181`，迁移、浏览器流程和真实 provider 验证通过；见 [M7 最终验收](migration/M7_6_FINAL_ACCEPTANCE_REPORT.md)。 |
| M8 | 进展分析 | 课程总览、知识点比较、掌握趋势、学习历史及复习风险提示；后续完善学习诊断体验与证据去重。 | 2026-11-02 用户确认 M8-5 完成、最终验收通过；联合回归记录后端 485/485、前端 232/232。仓库暂未找到独立 M8-5 验收报告；见 [实施报告](migration/M8_IMPLEMENTATION_REPORT.md)、[联合回归](migration/UX_FIX_FINAL_ACCEPTANCE.md)与 [M9 规划交接](migration/M9_PLANNING_HANDOFF.md)。 |

M3 完成 Course Knowledge Model，M4/M5 在其上形成诊断证据与学生知识状态，M6 据此生成推荐和学习计划，M7 将练习结果转为证据并刷新掌握状态。M3 边界见 [M3 最终验收](migration/M3_FINAL_ACCEPTANCE.md)。

## LearnPilot V0.1 历史原型阶段

LearnPilot V0.1 从最小 FastAPI 后端逐步发展为“资料上传、文本处理、搜索和复习辅助”JSON 原型。每个阶段以可运行接口和可验证结果为边界。

| 阶段 | 阶段目标 | 完成内容 | 验收方式 | 项目价值 |
| --- | --- | --- | --- | --- |
| 阶段 1 | FastAPI 最小后端 | 创建 FastAPI 应用入口和基础问候接口。 | 启动服务后可以访问基础接口。 | 建立可运行的后端起点。 |
| 阶段 2 | 后端基础结构 | 增加配置、路由聚合、健康检查和项目状态接口。 | `GET /health` 返回服务正常状态。 | 形成清晰的应用骨架。 |
| 阶段 3 | 课程资料模拟接口 | 增加课程列表、课程详情和资料列表接口，并使用示例数据。 | 通过 HTTP 获取课程和资料列表。 | 验证学习资料管理的核心领域流程。 |
| 阶段 4 | Pydantic 数据模型 | 使用 Pydantic 定义课程、资料和响应模型。 | FastAPI 自动校验请求并生成 API 文档。 | 提升接口一致性和可维护性。 |
| 阶段 5 | 新增资料接口 | 增加为指定课程创建 JSON 资料的接口。 | 成功创建资料；课程不存在时返回 `404`。 | 完成第一条资料写入流程。 |
| 阶段 6/7 | JSON 读取与持久化写回 | 将课程和资料迁移到 `courses.json`，新增安全写回逻辑。 | 新增资料后重启服务，资料仍然存在。 | 从临时状态升级为轻量持久化存储。 |
| 阶段 8 | 文件上传接口 | 支持常见课程资料格式上传，按课程保存到本地目录。 | 上传文件和资料元数据均能保存。 | 将真实学习文件接入资料管理流程。 |
| 阶段 9 | 资料文本提取 | 对 `.txt`、`.md` 提取正文，保存预览、字符数和状态。 | 上传文本文件后 GET 接口可读到提取字段。 | 为后续 AI 处理准备结构化文本。 |
| 阶段 10 | mock AI 摘要 | 增加本地 mock 摘要服务和 `POST /api/materials/{material_id}/summary`。 | 有文本时生成摘要并持久化；无文本和未知资料返回明确错误。 | 在不依赖 API Key 的情况下演示 AI 服务边界。 |
| 阶段 11 | 资料搜索 | 支持按标题、摘要、文件名、提取文本和 mock 摘要搜索，并支持课程过滤。 | 验证大小写不敏感匹配、空结果和参数错误。 | 让资料数量增长后仍然容易查找。 |
| 阶段 12 | 学习复习卡片生成 | 增加本地 mock card generator，生成并保存复习卡片。 | 生成 3 张卡片；重复生成覆盖旧卡片而不重复追加。 | 将资料内容转化为可复习的学习产物。 |
| 阶段 13 | 项目文档与比赛材料 | 完善 README、API 总览、开发日志和 Demo 讲稿。 | 文档与已测试 API 能力一致。 | 便于比赛评审、现场演示和简历展示。 |
| 阶段 14 | 最终验收与发布准备 | 检查仓库卫生、补充 `.gitignore`、核对文档并记录验收清单。 | 测试通过，仓库不包含运行时缓存和真实上传文件。 | 将 V0.1 整理为可交付、可展示的版本。 |

## V0.1 验收方式说明

测试使用临时 JSON 数据文件和临时上传目录启动真实 Uvicorn 服务，再通过 HTTP 请求验证公开 API。这种方式既验证接口行为，也验证持久化和服务重启场景，不会污染 `backend/app/data/courses.json`。

```bash
wsl -d Ubuntu --cd /home/qxrrr/projects/learnpilot \
.venv/bin/python -m unittest backend.tests.test_courses_api
```

## 版本定位

LearnPilot V0.1 是后端导向的比赛原型，其摘要和卡片使用本地 mock 规则。当前 LearnPilot V1 已迁移到关系数据库、Vue 前端和可配置的模型 provider，并完成课程知识模型、诊断、学生知识状态、推荐与 M7 学习执行闭环。M8 进展分析与后续 UX-FIX 已完成；M9 的真实模型质量评测与交付准备尚待执行。

## M9-A — 基线审计与评测协议冻结（2026-11-03）

M9-A1 完成 21 个能力分组代表性证据、15 项 UX-FIX 与 6 条关键调用链核对；M9-A2 冻结 AI 评测协议、可靠性与 UX 计划及执行清单。历史测试数量不作为本次测试结果。发布摘要见 [M9 阶段更新](M9_OVERVIEW.md)。

M9-A COMPLETE，项目进度 91%；M9-B 可在用户确认后开始数据准备，正式评分须先完成来源授权、隔离样本、人工金标准、双人复核及实际 HTTP 调用限额。M9-A 未执行真实 Provider 批量评测。保留原始大资料故障 NOT REPRODUCED、独立 M8-5 报告缺失但用户确认完成、Evidence 保守去重与历史数据边界。未更改业务代码、数据库 Schema、Prompt 或历史测试统计。


## 2026-11-07 — M9-D' 产品体验与演示验收

用户确认 M9-C' 完成和本轮浏览器体验通过。隔离浏览器验证真实课程数据、诊断提交、知识图谱、推荐会话、练习和进度历史；历史真实 Tutor 记录可读取。本轮没有实时付费模型调用。

修复题库新增同节点练习题后诊断覆盖目标不必要增长导致无法开始的问题：保留至少 8 题和必要核心节点覆盖，选择最大可满足目标并优先覆盖必需节点；相应测试明确更新。修复无新 Evidence 时错误声称重新计算的学习反馈。最终后端 487 passed（2 条既有 SQLAlchemy 警告），前端 233 passed，TypeScript、ESLint、Ruff、隔离构建与 SQLite alembic check 通过；真实浏览器用户确认与自动化证据分别记录。

M9-D' COMPLETE，LearnPilot V1 96%，M10 READY / NOT STARTED。正式系统性 AI 评测、原预算守卫与原大资料事故仍为 DEFERRED / NOT REPRODUCED。有限安全扫描为 PARTIAL；内部授权课程摘录未随公开提交发布。详见 [M9 阶段更新](M9_OVERVIEW.md)。
