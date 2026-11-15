# LearnPilot — 面向课程知识结构的 AI 个性化学习系统

> 参赛 README 草稿，更新于 2026-11-15。根目录正式 README 未被覆盖。交付代码来自本地候选分支；使用 `git rev-parse HEAD` 核对版本。该候选版本尚未推送，远程地址不保证包含候选文件。

LearnPilot 将课程资料转换为带原文来源的知识节点和先修关系。学生完成诊断后，系统保存作答证据，计算知识状态，并根据知识依赖和当前证据给出学习建议。资料问答和知识建模支持调用外部大模型；预置知识结构、模拟内容和现场模型调用是不同的结果。

## 在线体验与材料

- 在线演示：**待部署，尚无经过验证的地址**。当前共享身份缺少服务端隔离和调用预算控制，不能直接向多名评委公开。
- 源码地址：[GitHub / LearnPilot](https://github.com/qiangxinran-123/LearnPilot)（来自本地 Git remote，评委访问权限未核实）。
- [检查时的代码基线](https://github.com/qiangxinran-123/LearnPilot/commit/b9f01fbbf6a4d1e3713e333287f7c6465065bd74)：不包含此后未提交的工作区内容。
- 视频：已有 4 分 40 秒本地功能预览，正式比赛视频待完成和核对。已有技术文档 PDF 为 13 页，形成于本轮修复前，提交前须与最终代码复核。本地 API 文档：服务启动后访问 `http://127.0.0.1:18080/docs`；OpenAPI JSON 位于 `http://127.0.0.1:18080/openapi.json`。

- AI 对话快照：见 `output/contest-evidence/README.md`；公开副本脱敏了本机用户目录，内部聊天链接不能保证评委访问。

## 本地预置课程快速体验

课程“计算机系统：Cache 与局部性（演示）”包括一份 375 字资料摘录、17 个知识节点、5 条层级关系、10 条先修关系和 10 道经历史审核的诊断题。首次诊断从合格题库中组成 8 道题。课程资料使用权由资料所有者确认；学科内容尚未经过独立系统评审。

建议依次查看：**课程 → 知识地图与来源 → 诊断 → 诊断报告 → 学习计划 → 学习进展**。无需登录或自己上传资料。每次启动产生独立副本；成绩和建议来自当前副本的作答，而非预置记录。

一键脚本使用明确的 **mock 模式**，并不调用真实 AI。已有题库的首次诊断无需 API Key；资料问答和新增生成在 mock 模式下不代表真实模型能力。真实模型配置见下文。

### Linux / WSL 一键启动

需要 Python 3.14、Node.js 22.12 至 24、npm 10 或更高、curl，以及已有的 Python 和前端依赖。本轮环境为 WSL Ubuntu、Python 3.14.4、Node 24.22.0、npm 11.19.1；原生 Windows 未作完整验证。首次下载依赖耗时取决于网络，不保证 10 分钟完成。

取得包含 `demo_data/` 和演示脚本的候选版本后，在项目根目录执行：

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
(cd frontend && npm ci)
bash scripts/start_demo.sh
```

启动完成后访问本机 <http://127.0.0.1:15173>，后端为 <http://127.0.0.1:18080>。保持终端开启，按 Ctrl+C 结束服务；脚本输出的 `/tmp/learnpilot-demo.*/session` 为本次副本，退出后保留，便于检查。重复运行会产生新副本，不覆盖开发数据库。需要更换端口时：

```bash
DEMO_BACKEND_PORT=18081 DEMO_FRONTEND_PORT=15174 bash scripts/start_demo.sh
```

脚本检查端口、依赖、资料完整性、健康接口、数据库课程和首次诊断准备状态，并通过前端代理检查课程。缺失依赖时输出安装提示，不自动修改系统环境。

**交付前提：** 检查取得的版本包含 `demo_data/`、`scripts/init_demo.py` 和 `scripts/start_demo.sh`；旧基线不包含这些文件。候选分支 `codex/learnpilot-contest-p0` 尚未推送，评委访问权限待验证。本轮已从本地候选提交克隆到新目录，使用新虚拟环境、独立 npm 缓存和网络安装依赖并完成浏览器诊断；尚未在另一台计算机验证。

## 环境、配置与技术栈

后端使用 FastAPI、Pydantic、SQLAlchemy 和 Alembic；前端使用 Vue 3、TypeScript、Vite、Pinia 和 Element Plus。本地使用 SQLite；演示资料保存在独立上传目录。依赖清单分别为 `requirements.txt` 和 `frontend/package-lock.json`。模型接口为 OpenAI 兼容的 Chat Completions JSON 模式。

后端从工作目录的私有 `.env` 和进程环境读取配置，进程环境优先。使用 `.env.example` 作为完整配置样例，**不要将真实密钥提交或放入前端变量**。一键脚本强制 mock，不读取模型密钥进行真实调用。手动运行可设置：

```dotenv
APP_ENV=development
DATABASE_URL=sqlite+pysqlite:////absolute/path/to/demo.sqlite3
UPLOAD_ROOT=/absolute/path/to/uploads
LEGACY_BOOTSTRAP_USER=legacy-bootstrap@learnpilot.local
LLM_MODE=provider
LLM_API_KEY=在本地私有配置中填写
LLM_BASE_URL=按服务商实际配置填写
LLM_MODEL=按服务商实际模型ID填写
LLM_MAX_ATTEMPTS=1
# 可选；仅在供应商支持 max_tokens 时设置
LLM_MAX_OUTPUT_TOKENS=1024
# 知识抽取专用上限，覆盖上面的通用输出上限
KNOWLEDGE_EXTRACTION_MAX_OUTPUT_TOKENS=4096
```

`DATABASE_URL` 为必需，上传目录应可写。真实模式需要服务商有效密钥、模型、地址和网络；费用及可用性由服务商决定。`LLM_MAX_OUTPUT_TOKENS` 仅限制普通单次输出；知识抽取单独使用 `KNOWLEDGE_EXTRACTION_MAX_OUTPUT_TOKENS`。二者都不是调用次数限制或费用上限。默认超时、输入长度、切片、重试和题库配置见 `.env.example` 与 `backend/app/core/settings.py`。前端默认使用 `/api`，开发代理由 `VITE_BACKEND_ORIGIN` 指定；不要在 `VITE_*` 中放密钥。

## 手动启动及真实 AI

下面创建新的演示副本；保留同一终端中输出的路径，不要指向现有开发数据：

```bash
RUN_PARENT="$(mktemp -d /tmp/learnpilot-manual.XXXXXXXX)"
.venv/bin/python scripts/init_demo.py --destination "$RUN_PARENT/session"
export DATABASE_URL="sqlite+pysqlite:///$RUN_PARENT/session/demo.sqlite3"
export UPLOAD_ROOT="$RUN_PARENT/session/uploads"
export LEGACY_BOOTSTRAP_USER=legacy-bootstrap@learnpilot.local
# 在私有 .env 中配置有效 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL
export LLM_MODE=provider
.venv/bin/alembic current
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

另开终端：

```bash
cd frontend
VITE_BACKEND_ORIGIN=http://127.0.0.1:8000 npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

本机访问 <http://127.0.0.1:5173>，API 文档为 <http://127.0.0.1:8000/docs>。这里使用已有演示快照；如需使用全新空数据库，从安全的新路径设置 `DATABASE_URL` 和 `UPLOAD_ROOT` 后运行 `.venv/bin/alembic upgrade head`。迁移操作应在副本或新数据库上执行。

2026-11-15 在独立副本中使用 `deepseek-flash`：1024 Token 抽取请求以 `finish_reason=length` 截断；使用抽取专用 4096 Token 上限后，真实抽取返回 18 个候选，18 个候选均关联输入资料。浏览器真实问答返回的 Cache 容量公式与原文一致，引用可点击查看资料。模型输出存在随机性，此次结果不保证其他输入必然成功。

## 从零创建课程

在独立空库或副本中创建课程，上传合法使用的 TXT、Markdown、PDF 或 DOCX，确认资料解析成功；执行知识抽取及知识结构构建并检查来源，准备和审核诊断题库，达到覆盖要求后开展诊断，查看报告和学习计划。首次建模、资料问答和模型生成依赖真实 provider 或明确选择 mock。模型输出非确定，需人工核查；补题等流程也可能再次调用模型。

首次诊断后不能保证进展页立即显示已评估掌握度：当前规则要求每个知识点至少 3 条独立证据。本次 8 道题覆盖 8 个知识点，报告可展示本次作答与错题，但进展页仍可能显示证据不足。

## 测试与验收

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_demo_initializer.py backend/tests/test_m2_llm_client.py
(cd frontend && npm run test)
(cd frontend && npm run build)
.venv/bin/ruff check backend/app/ai/client.py backend/app/core/settings.py backend/tests/test_m2_llm_client.py
```

上轮后端完整测试 510 项通过（2 条 SQLAlchemy 警告），前端 33 个测试文件、237 项测试通过；本轮受影响后端测试 60 项通过，资料页前端测试 7 项通过，生产构建和类型检查通过。浏览器在隔离副本中完成首次诊断，6/8 正确，写入 8 条学习证据并生成初步学习计划。进展页显示证据不足符合当前阈值。真实抽取和浏览器问答的条件与限制见本轮验收记录。

## 复现与使用边界

演示快照包含历史模型生成的知识结构及经审核题目，不是本次实时生成；历史学习记录已从快照中清除。新的作答和学习建议写入本次独立副本。代码逻辑与固定输入可检查，但外部模型响应、延迟及结果不能保证逐字一致。材料提供者授权在本项目使用；对外分发前仍应由发布者确认最终授权范围。

两个独立实例使用不同 SQLite 和上传目录，学习状态不会自然混合；这不是服务端身份认证。同一实例的接口缺少安全的多评委会话隔离，课程也缺少公共只读保护。当前没有每会话调用限额、统一速率限制或全局调用预算，不能安全公开真实模型服务。

## 常见问题

- **前端或后端启动失败：**检查 Python、Node、依赖及端口；启动脚本只适用于 Linux / WSL。不同实例需使用不同端口。
- **迁移失败或课程为空：**确认数据库 URL 指向预期副本、路径可写；新空库先执行 `alembic upgrade head`，演示快照按 `demo_data/README.md` 初始化。
- **前后端无法连接：**检查后端端口和 `VITE_BACKEND_ORIGIN`；`/health` 成功并不证明业务数据库可用。
- **AI 返回配置或服务错误：**核对私有 `.env` 的 provider、密钥、地址、模型、网络和服务商状态；不要把密钥写入日志。mock 与真实模型必须区分。
- **没有题库或进展无掌握度：**空库需要准备并审核题库；首次诊断仅提供有限证据，更多独立学习证据可能是必要条件。
- **Windows 原生环境：**命令采用 WSL/bash，PowerShell 原生流程尚未验证。

在工作区可用 `git rev-parse HEAD` 查看实际提交。将候选分支推送并确认访问权限之前，GitHub 远程仓库不能作为本候选版下载地址。

更多说明见 `demo_data/README.md`、`docs/API_OVERVIEW.md`、上轮记录 `output/CONTEST_ACCEPTANCE_20261115.md` 和本轮 `output/CONTEST_P0_REPORT_20261115.md`。
