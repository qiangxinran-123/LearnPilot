# LearnPilot

LearnPilot 是 LearnPilot 原型的持续演进版本：面向大学生管理课程资料、提取可追溯正文，并将资料转化为摘要、学习卡片、问答结果和课程知识模型。

当前代码基线为 **LearnPilot V1 / M3 Course Knowledge Model Final Acceptance**。M3-A 至 M3-E 已完成课程知识模型的数据基础、AI 抽取、归一化、关系生成和课程内可视化。旧版 LearnPilot V0.x 的 JSON 原型、原生前端和比赛材料仍保留用于追溯，但不再代表当前运行架构。

## 当前能力

- 使用 Vue 3、TypeScript、Vite、Pinia 和 Element Plus 提供首页、课程、诊断、学习、进展五个一级页面。
- 通过 FastAPI 提供课程 CRUD、资料上传/删除/搜索、分页正文、结构化摘要、学习卡片和单资料问答接口。
- 支持 TXT、MD、PDF、DOCX 资料；默认上传上限为 20 MiB。PPT/PPTX 当前未启用。
- 使用 SQLAlchemy 与 Alembic 持久化课程、资料、解析正文和 AI 产物；本地演示使用 SQLite，部署可配置 MySQL 8。
- AI 默认使用显式配置的 provider；`LLM_MODE=mock` 只用于本地验收，不会作为生产环境静默回退。
- M3-B 从已解析资料中提取带来源证据的候选知识点；M3-C 保守归一化并生成规范知识节点。
- M3-D 生成并验证 `CONTAINS` 层级与 `PREREQUISITE` 先修关系，保存关系依据。
- M3-E 将课程详情升级为学习工作台：默认学习概览、完整资料工具、知识层级树与辅助关系图、独立知识详情，以及可恢复的知识构建/更新状态。

M3 建立的是课程模型，不是学生模型。它不包含掌握度、学习进度、诊断、推荐、学习路径或导师代理，也不会把图坐标等展示状态写入领域数据。

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vite、Vue Router、Pinia、Element Plus、Axios |
| 后端 | FastAPI、Pydantic、SQLAlchemy、Alembic |
| 数据库 | SQLite（本地演示）、MySQL 8（目标部署） |
| 文档解析 | TXT、Markdown、PDF、DOCX |
| 质量检查 | pytest、Ruff、Vitest、vue-tsc、ESLint、Prettier |

## 快速启动

### 1. 后端

项目要求 Python 3.14 或更高版本。在仓库根目录执行：

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp -n .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/python -m uvicorn backend.main:app --reload
```

`.env.example` 提供显式的本地 SQLite 地址 `sqlite+pysqlite:///./learnpilot-demo.sqlite3`。`cp -n` 不会覆盖已有的私有 `.env`；真实数据库凭据和模型密钥只应写入被 Git 忽略的 `.env`。

启动后可访问：

- 应用/API 服务：<http://127.0.0.1:8000>
- Swagger 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

### 2. 前端开发服务器

项目支持 Node.js `>=22.12.0 <25`、npm `>=10`：

```bash
cd frontend
npm ci
npm run dev
```

Vite 会将 `/api/*` 和 `/health` 代理到 `http://127.0.0.1:8000`。运行 `npm run build` 后，FastAPI 会托管 `frontend/dist/` 并提供 SPA history fallback，同时保留 API 与健康检查路由。

## AI 配置

`.env.example` 默认使用 `LLM_MODE=provider`，但不包含密钥。真实模型调用至少需要在私有 `.env` 中配置：

```dotenv
LLM_MODE=provider
LLM_API_KEY=...
LLM_BASE_URL=...
LLM_MODEL=...
```

未完成 provider 配置时，AI 接口会返回 `AI_NOT_CONFIGURED`。仅做本地功能验收时可以显式设置 `LLM_MODE=mock`；响应会保留 mock 来源，不代表真实模型已经接通。摘要输入上限默认是 200000 字符，超过限制会返回 `AI_INPUT_TOO_LARGE`。

## 数据库与迁移

当前 Alembic 迁移链：

1. `0001_m1a_foundation`：用户、课程、资料和归属关系；
2. `0002_m2_course_material_ai`：完整解析正文、分段来源、摘要、卡片和 AI 审计字段；
3. `0003_m3a_knowledge_model`：知识节点、知识关系和可追溯来源；
4. `0004_m3b_knowledge_extraction`：抽取运行、候选知识点和候选来源；
5. `0005_m3c_canonicalization`：归一化运行、候选解析和节点生命周期；
6. `0006_m3d_relationships`：关系运行、关系证据和生成关系归属；
7. `0007_m3e_workspace_build_state`：课程级持久化构建任务、阶段、租约、资料快照和失败恢复状态。

旧 `backend/app/data/courses.json` 不会在启动时自动导入。先执行 dry-run，再决定是否写入目标数据库：

```bash
.venv/bin/python -m backend.scripts.import_legacy_json \
  --database-url "sqlite+pysqlite:///./learnpilot-demo.sqlite3" \
  --source backend/app/data/courses.json \
  --dry-run
```

确认结果后移除 `--dry-run`。导入器不会从 `.env` 猜测目标数据库地址；请显式传入并在操作前保留备份。

## API 概览

主要接口包括：

- `GET/POST /api/courses`
- `GET/PATCH/DELETE /api/courses/{course_id}`
- `GET/POST /api/courses/{course_id}/materials`
- `POST /api/courses/{course_id}/materials/upload`
- `GET/DELETE /api/materials/{material_id}`
- `GET /api/materials/{material_id}/content`
- `GET/POST /api/materials/{material_id}/summary`
- `GET/POST /api/materials/{material_id}/cards`
- `POST /api/materials/{material_id}/qa`
- `GET /api/courses/{course_id}/knowledge-model`
- `POST /api/courses/{course_id}/knowledge-model/build`
- `GET /api/courses/{course_id}/knowledge-model/build-status`
- `POST /api/courses/{course_id}/knowledge-model/build-jobs`
- `GET /api/courses/{course_id}/knowledge-nodes`
- `GET /api/courses/{course_id}/knowledge-nodes/{node_id}`
- `GET/POST /api/courses/{course_id}/materials/{material_id}/knowledge-extraction`
- `GET/POST /api/courses/{course_id}/knowledge-canonicalization`
- `GET/POST /api/courses/{course_id}/knowledge-relationships`

请求参数、响应边界和错误码见 [API 总览](docs/API_OVERVIEW.md)。

## M3 课程知识模型

完整处理链为：

```text
M2 MaterialContent 与解析分段
  → M3-B KnowledgeCandidate 与候选证据
  → M3-C KnowledgeNode 与 KnowledgeSource
  → M3-D CONTAINS / PREREQUISITE 与关系证据
  → M3-E 学习概览、知识详情、层级树/关系图与可靠构建状态
```

- 所有实体、运行记录和来源均限制在当前 owner 的同一课程内；
- 候选来源必须精确匹配真实解析分段，持久化摘录来自资料而非模型自由生成；
- 归一化优先避免错误合并，并保留候选到规范节点的解析记录；
- `CONTAINS` 被验证为允许多根的无环森林，`PREREQUISITE` 被独立验证为 DAG；
- 同一输入快照会复用成功运行，失败的重新生成不会替换已发布模型；
- 课程学习工作台只使用真实 canonical 节点和关系，不创建合成根节点，也不持久化布局坐标；
- 构建任务状态和资料快照保存在数据库中，刷新页面后仍可恢复；更新失败会恢复并保留此前已发布的可用知识模型。

`POST /api/courses/{course_id}/knowledge-model/build-jobs` 通过持久化任务按顺序编排既有 M3-B、M3-C、M3-D 服务，不引入新的推理算法。旧同步 `build` 接口继续保留兼容。

## 质量检查

后端：

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check backend
.venv/bin/ruff format --check backend
```

前端：

```bash
cd frontend
npm run typecheck
npm run lint
npm run test
npm run build
```

本次 M3-E 最终验证结果：后端 `146/146` 测试通过，Ruff lint 与格式检查通过；前端 typecheck、lint、Prettier、Vitest `62/62` 和生产构建通过。构建会提示懒加载 G6 vendor chunk 超过 500 kB，这是已记录的非阻塞体积提示。

## 项目结构

```text
learnpilot/
├── backend/
│   ├── alembic/                 # 0001 → … → 0007 数据库迁移
│   ├── app/
│   │   ├── ai/                  # provider/mock 适配与审计边界
│   │   ├── api/                 # 课程、资料、知识模型接口
│   │   ├── db/                  # 引擎、会话和 ORM 模型
│   │   ├── documents/           # 文档解析
│   │   ├── repositories/        # 持久化边界
│   │   ├── services/            # 课程、AI、知识模型服务
│   │   └── storage/             # 上传存储
│   ├── scripts/                 # 显式旧数据导入工具
│   └── tests/
├── frontend/
│   ├── src/                     # Vue 应用
│   └── legacy/                  # 旧原生前端，仅供参考
├── docs/
│   ├── architecture/            # 各里程碑架构说明
│   └── migration/               # 审计与实施报告
├── alembic.ini
├── pyproject.toml
└── requirements.txt
```

## 文档索引

- [API 总览](docs/API_OVERVIEW.md)
- [开发日志](docs/DEVELOPMENT_LOG.md)
- [M1-A 数据基础](docs/architecture/M1A_DATA_FOUNDATION.md)
- [M1-B 前端架构](docs/architecture/M1B_FRONTEND_ARCHITECTURE.md)
- [M2 课程与资料架构](docs/architecture/M2_COURSE_MATERIAL_ARCHITECTURE.md)
- [M3-A 知识模型基础](docs/architecture/M3A_KNOWLEDGE_MODEL_FOUNDATION.md)
- [M3-B AI 知识抽取](docs/architecture/M3B_AI_KNOWLEDGE_EXTRACTION.md)
- [M3-C 知识归一化](docs/architecture/M3C_KNOWLEDGE_CANONICALIZATION.md)
- [M3-D 知识关系](docs/architecture/M3D_KNOWLEDGE_RELATIONSHIPS.md)
- [M3-E 知识结构前端](docs/architecture/M3E_KNOWLEDGE_STRUCTURE_FRONTEND.md)
- [M3-E 课程学习工作台](docs/architecture/M3E_KNOWLEDGE_WORKSPACE.md)
- [M3-A 实施报告](docs/migration/M3A_IMPLEMENTATION_REPORT.md)
- [M3-E 实施报告](docs/migration/M3E_IMPLEMENTATION_REPORT.md)
- [M3 最终验收](docs/migration/M3_FINAL_ACCEPTANCE.md)
- [旧版比赛 Demo 脚本](docs/DEMO_SCRIPT.md)
- [旧版 V0.1 验收清单](docs/V0.1_ACCEPTANCE.md)

## 当前限制

- 尚无正式登录/多用户会话；当前通过 bootstrap user 保持数据归属边界。
- 仓库不包含真实模型密钥；真实 provider 验证依赖运行环境中的私有配置。
- MySQL 8 目标部署尚未在本次本地验证中执行，当前自动化测试使用隔离 SQLite。
- M3 的 provider 判断是受边界和来源校验约束的建议，不代表完整课程真理。
- 知识图是辅助探索界面，不支持图编辑、坐标持久化、导出或完整键盘图遍历；层级树和知识列表提供主要的可访问浏览路径。
- 诊断、学生掌握度、推荐和进展仍无真实领域数据，界面保持空状态。
