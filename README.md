# LearnPilot

**从课程资料出发，理解知识结构，发现学习薄弱点，规划下一步学习。**

LearnPilot 是一个面向课程学习的 AI 辅助学习系统。它将课程资料整理为可追溯的知识点与知识关系，结合诊断作答形成学习证据，再依据知识依赖和已有学习状态生成学习建议。

[快速开始](#快速开始) · [配置模型](#配置模型) · [项目结构](#项目结构)

## 功能

- **课程资料**：创建课程，上传并解析 TXT、Markdown、PDF、DOCX，浏览原文、摘要和学习卡片。
- **知识结构**：从资料中抽取知识点，组织层级与先修关系，并在知识地图中浏览关联及资料来源。
- **学习诊断**：根据合格题库组织测评，支持作答恢复、确定性评分、诊断报告和错题解析。
- **学习状态与建议**：从实际作答生成学习证据，估计知识掌握状态和置信度，结合先修关系生成可解释的学习计划。
- **学习与练习**：围绕学习计划查看资料、向 AI 导师提问并开展练习，结果可用于更新学习状态。
- **学习进展**：查看知识状态、已记录的学习历史和复习提示。

掌握度是基于已有证据的系统估计，并非经过教育测量学标定的真实掌握概率。证据不足时，相关知识点会保留待评估状态。

## 工作流程

~~~text
课程资料 → 文档解析 → 知识点与来源 → 层级及先修关系
                                      ↓
学习建议 ← 知识状态 ← 学习证据 ← 诊断与练习
~~~

模型参与资料理解、知识提取、题目生成和问答；评分、证据记录及学习状态计算由应用逻辑处理。模型生成内容需要结合原始资料核查。

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vite、Vue Router、Pinia、Element Plus、AntV G6 |
| 后端 | Python、FastAPI、Pydantic、SQLAlchemy、Alembic |
| 数据与文件 | SQLite、文件系统；数据库配置支持 MySQL |
| AI 接口 | OpenAI 兼容的 Chat Completions 接口，支持显式 mock 模式 |
| 测试与检查 | pytest、Ruff、Vitest、vue-tsc、ESLint |

## 快速开始

### 环境要求

- Linux 或 Windows 的 WSL；下方命令使用 Bash。Windows 原生运行流程尚未完整验证。
- Python 3.14 或更高版本；已验证 Python 3.14。
- Node.js >= 22.12.0 且 < 25，npm >= 10。
- Git、curl，以及安装依赖时可用的网络。

基础环境和依赖已就绪时，以下流程以约 10 分钟内启动为目标；首次安装依赖所需时间取决于网络。后端依赖及其版本见 [requirements.txt](requirements.txt)，前端依赖见 [frontend/package.json](frontend/package.json) 和 [frontend/package-lock.json](frontend/package-lock.json)。

### 安装

~~~bash
git clone https://github.com/qiangxinran-123/LearnPilot.git
cd LearnPilot

python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
(cd frontend && npm ci)
~~~

### 使用预置课程

~~~bash
bash scripts/start_demo.sh
~~~

脚本会创建独立的临时数据库和上传目录，加载一门预置课程并启动前后端。启动完成后访问 <http://127.0.0.1:15173>；保持终端运行，按 Ctrl+C 停止服务。

预置课程包含 1 份课程摘录、17 个知识节点、15 条知识关系和 10 道经历史审核的诊断题，可直接浏览知识结构和来源并开始首次诊断。每次运行脚本都会创建新的副本，不会覆盖现有开发数据库；副本路径会显示在终端中。

**该脚本固定使用 mock 模式，不调用真实模型。** 已有题库的首次诊断无需 API Key；要使用真实问答或生成能力，请按下方说明手动配置和启动。演示数据与来源说明见 [demo_data/README.md](demo_data/README.md)。

如默认端口被占用，可指定其他端口：

~~~bash
DEMO_BACKEND_PORT=18081 DEMO_FRONTEND_PORT=15174 bash scripts/start_demo.sh
~~~

## 配置模型

后端从项目根目录的私有 .env 文件和进程环境变量读取配置，进程环境变量优先。首次配置时复制模板：

~~~bash
cp -n .env.example .env
~~~

编辑 .env 中的以下项目：

~~~dotenv
# provider 使用真实模型；mock 使用模拟响应
LLM_MODE=provider
LLM_API_KEY=在本地填写密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash

# 知识抽取的单次输出上限，可按模型能力调整
KNOWLEDGE_EXTRACTION_MAX_OUTPUT_TOKENS=4096
~~~

上述地址和模型 ID 是 DeepSeek 配置示例；使用真实模型时，请自行申请并配置 API Key，费用由自己的服务商账户承担。实际可用性和模型权限以服务商及账户状态为准。LLM_MODE=mock 明确使用模拟输出，不代表真实模型已接通。真实密钥只保存在私有环境中，不应写入前端、代码仓库或日志。

数据库、上传目录、超时及其他选项见 [.env.example](.env.example)。在本地运行时常用：

| 变量 | 作用 |
| --- | --- |
| DATABASE_URL | 数据库连接地址；示例文件默认使用本地 SQLite |
| UPLOAD_ROOT | 上传资料的存储目录 |
| MAX_UPLOAD_BYTES | 单个上传文件大小上限 |
| LLM_MODE | 选择 provider 或 mock |
| LLM_API_KEY、LLM_BASE_URL、LLM_MODEL | 真实模型的服务端配置 |
| LLM_TIMEOUT_SECONDS、LLM_MAX_ATTEMPTS | 模型请求的超时与重试次数 |
| KNOWLEDGE_EXTRACTION_MAX_OUTPUT_TOKENS | 知识抽取的单次输出上限 |
| VITE_BACKEND_ORIGIN | 前端开发服务器的后端代理地址，默认 http://127.0.0.1:8000 |

## 手动启动

以下步骤适用于从一个新的空数据库开始。确认 .env 中的 DATABASE_URL 和 UPLOAD_ROOT 指向可写位置，并且不会覆盖已有数据；如需真实 AI，请先完成模型配置。

在仓库根目录启动后端：

~~~bash
.venv/bin/alembic upgrade head
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
~~~

另开终端启动前端：

~~~bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
~~~

- 应用：<http://127.0.0.1:5173>
- API 文档：<http://127.0.0.1:8000/docs>
- OpenAPI JSON：<http://127.0.0.1:8000/openapi.json>
- 健康检查：<http://127.0.0.1:8000/health>

空数据库不包含课程或题库。可在应用中创建课程、上传资料并构建知识结构，再准备和审核诊断题。真实模型调用需要有效的 provider 配置和网络。

如果需要使用预置课程同时调用真实模型，可以先运行 scripts/init_demo.py 创建独立副本，再按 [演示数据说明](demo_data/README.md) 设置 DATABASE_URL 和 UPLOAD_ROOT，并以 provider 模式手动启动。不要对打包的原始快照直接执行迁移或写入。

## 开发与测试

在项目根目录运行后端检查：

~~~bash
.venv/bin/python -m pytest
.venv/bin/ruff check backend
~~~

运行前端检查和生产构建：

~~~bash
cd frontend
npm run typecheck
npm run lint
npm run test
npm run build
~~~

测试不需要将真实密钥提交到仓库。使用模拟模型的测试结果不能代替真实外部模型调用验证。

## 项目结构

~~~text
LearnPilot/
├── backend/
│   ├── app/
│   │   ├── ai/              # 模型客户端与结构化输出
│   │   ├── api/             # API 路由
│   │   ├── db/              # 数据库会话与模型
│   │   ├── documents/       # 文档解析
│   │   ├── repositories/    # 数据访问
│   │   ├── services/        # 业务逻辑
│   │   └── storage/         # 文件存储
│   ├── alembic/             # 数据库迁移
│   └── tests/               # 后端测试
├── frontend/                # Vue 应用、前端测试及构建配置
├── demo_data/               # 预置课程及来源说明
├── scripts/                 # 演示数据初始化和启动脚本
├── docs/                    # API 和设计文档
├── .env.example             # 本地环境变量模板
└── requirements.txt         # Python 依赖
~~~

## 使用边界

- 普通本地模式使用固定的演示用户上下文，不等同于完整的多用户身份认证；不要将该模式直接作为公开多用户服务部署。
- 预置知识结构和题库来自历史处理结果；后续模型结果具有不确定性，应核查内容与引用。
- 项目依赖的第三方模型、网络和托管服务可能产生费用或出现不可用情况。部署前应配置访问控制、调用限制、数据持久化及备份。

更多接口信息见 [API 总览](docs/API_OVERVIEW.md)；实际请求参数以运行中的 API 文档为准。
