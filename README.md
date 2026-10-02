# LearnPilot（CampusAI）

LearnPilot 是 CampusAI 原型的持续演进版本：面向大学生管理课程资料、提取可追溯正文，并将资料转化为摘要、学习卡片、问答结果和课程知识模型。

当前代码基线为 **LearnPilot V1 / M3-A Knowledge Model Foundation**。旧版 CampusAI V0.x 的 JSON 原型、原生前端和比赛材料仍保留用于追溯，但不再代表当前运行架构。

## 当前能力

- 使用 Vue 3、TypeScript、Vite、Pinia 和 Element Plus 提供首页、课程、诊断、学习、进展五个一级页面。
- 通过 FastAPI 提供课程 CRUD、资料上传/删除/搜索、分页正文、结构化摘要、学习卡片和单资料问答接口。
- 支持 TXT、MD、PDF、DOCX 资料；默认上传上限为 20 MiB。PPT/PPTX 当前未启用。
- 使用 SQLAlchemy 与 Alembic 持久化课程、资料、解析正文和 AI 产物；本地演示使用 SQLite，部署可配置 MySQL 8。
- AI 默认使用显式配置的 provider；`LLM_MODE=mock` 只用于本地验收，不会作为生产环境静默回退。
- M3-A 增加课程知识节点、关系和来源的数据模型、完整性约束、仓储/服务层以及只读 API。

M3-A 只建立课程知识模型基础，不会自动抽取知识点，也不包含语义去重、层级/先修关系推断、学生掌握度、推荐或前端知识图谱。

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
3. `0003_m3a_knowledge_model`：知识节点、知识关系和可追溯来源。

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
- `GET /api/courses/{course_id}/knowledge-nodes/{node_id}`

请求参数、响应边界和错误码见 [API 总览](docs/API_OVERVIEW.md)。

## 知识模型边界

M3-A 将课程知识模型与未来的学生模型严格分离：

- `KnowledgeNode` 保存名称、规范化名称、描述、重要度和难度；
- `KnowledgeEdge` 仅定义 `contains` 和 `prerequisite` 两种有向关系；
- `KnowledgeSource` 必须指向同一课程资料中真实存在的解析分段引用；
- 数据库和服务层共同阻止自环、重复关系、跨课程关系和无效来源；
- 删除课程、节点或资料时按照明确的外键策略清理关联记录。

当前公开 API 只读取知识模型。写入方法保留在类型化服务层，供后续经过批准的抽取流程使用。

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

本次 M3-A 基线验证结果：后端 `93/93` 测试通过，Ruff lint 与格式检查通过；前端类型检查和源码 lint 通过。M3-A 未修改前端，完整 Vitest/构建结果及当前主包体积提示记录在 [M2 实施报告](docs/migration/M2_IMPLEMENTATION_REPORT.md)和 [M3-A 实施报告](docs/migration/M3A_IMPLEMENTATION_REPORT.md)。

## 项目结构

```text
campus-ai/
├── backend/
│   ├── alembic/                 # 0001 → 0002 → 0003 数据库迁移
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
- [M3-A 实施报告](docs/migration/M3A_IMPLEMENTATION_REPORT.md)
- [旧版比赛 Demo 脚本](docs/DEMO_SCRIPT.md)
- [旧版 V0.1 验收清单](docs/V0.1_ACCEPTANCE.md)

## 当前限制

- 尚无正式登录/多用户会话；当前通过 bootstrap user 保持数据归属边界。
- 真实 LLM smoke test 需要用户提供 provider 配置；仓库不包含真实密钥。
- MySQL 8 目标部署尚未在本次本地验证中执行，当前自动化测试使用隔离 SQLite。
- M3-A 不执行知识抽取或关系推断，前端也尚未展示知识图谱。
- 诊断、学生掌握度、推荐和进展仍无真实领域数据，界面保持空状态。
