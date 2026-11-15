# LearnPilot V1 参赛验收记录（2026-11-15）

## 结论与范围

本次复用现有演示快照，未覆盖开发数据库、正式 README，也未部署或推送。检查基线为 Git commit `b9f01fbbf6a4d1e3713e333287f7c6465065bd74`，本轮文件尚未提交。评委在隔离的本地环境中可以完成一次预置课程诊断和初步学习建议；**远程仓库尚无本轮完整交付文件，真实知识抽取未通过，在线多评委认证与调用限制缺失，因此整体仍有交付阻断，不能宣称可以安全公开或完成全部验收。**

环境：WSL Ubuntu，Python 3.14.4，Node 24.22.0，npm 11.19.1。浏览器为本地已有 Chromium，经 Playwright 操作。浏览器控制台曾记录 1 条 404 资源错误；未见其阻断所验收流程，尚未进一步定位。Windows 原生环境及全新网络依赖安装未验证。

## 阶段一：浏览器和数据验证

使用 `scripts/start_demo.sh` 在独立 SQLite / uploads 副本启动前后端。结果：

| 操作 | 实际结果 | 主要接口 |
| --- | --- | --- |
| 进入课程 | 直接出现“计算机系统：Cache 与局部性（演示）”，课程概览显示 1 份资料、17 个节点和 15 条关系 | `GET /api/courses` |
| 知识结构 | 浏览知识地图，定位“Cache容量参数”；结构 API 返回 17 个 nodes、15 个 edges | `GET /api/courses/1/knowledge-model` |
| 来源 | 节点 7 页面显示课程摘录及已核验原文；接口中的 375 字 excerpt 和 300 字原文片段均能在资料正文中找到 | `GET /api/courses/1/knowledge-nodes/7`、`GET /api/materials/1/content` |
| 首次诊断 | readiness 可开始；逐题选首项，页面保存 8/8，提交得 6/8、75%；报告列出空间局部性和 Cache 容量参数两项错题相关观察 | `/api/diagnostics/courses/1/readiness`、assessment 创建、作答及提交接口 |
| 学习证据 | 副本数据库实际有 8 条 learning_evidence 和 8 条 mastery_history | `GET /api/courses/1/mastery` |
| 学习计划 | 页面点击生成后显示初步学习建议，当前目标为“局部性原理”，包含 2 项任务；并提示证据有限 | `POST /api/courses/1/learning-plan/generate` |
| 进展 | 浏览器显示 0/14 已评估、暂无足够学习数据，而非展示确定掌握度 | `GET /api/courses/1/progress/overview` |

诊断覆盖 8 个知识点，但每个节点证据不足；`backend/app/services/mastery_config.py` 当前要求至少 3 条独立证据。未降低阈值或伪造结果。截图：`output/contest_evidence/knowledge-map.png`、`knowledge-source.png`、`diagnostic-report.png`、`learning-plan.png`、`progress.png`。自动化没有对所有 15 条关系逐条进行视觉检查，也未以真实 provider 在浏览器中提交问答。

## 阶段二：真实模型

当前配置读取代码为 `backend/app/core/settings.py` 和 `backend/app/ai/client.py`。OpenAI-compatible 客户端使用 Chat Completions、temperature 0.2、JSON object 响应；默认超时 45 秒、最多 2 次尝试，按服务端响应解析并校验 Pydantic 结构。失败有认证、限流、连接、超时和格式等错误分类。

本轮在另一个隔离副本启用 provider，读取既有私有配置，不打印密钥。两项测试各设置最多 1 次尝试、最多 1024 输出 Token，实际模型 ID 为 `deepseek-flash`；源资料 375 字。

1. `POST /api/materials/1/qa`，问题为“Cache”：HTTP 200，返回 `grounded=true`、provider `openai-compatible`、`material_qa_v1` 和 1 条引用。完成 provider 请求与问答结构解析；本次未保存回答全文，不能据此宣称人工完成内容正确性审校。
2. 新建独立测试课程并上传同一授权资料，调用知识抽取：HTTP 422，`KNOWLEDGE_EXTRACTION_INVALID_OUTPUT`。本次结构化抽取未通过；由于未保存原始响应，不能认定具体原因，也不能把它算作成功。未进行第三次模型请求。

新增可选 `LLM_MAX_OUTPUT_TOKENS`，设置时传递 `max_tokens`，默认不传以保持原行为。测试覆盖显式上限与默认行为。此配置仅约束单次输出，不限制访问次数、输入费用或总体账单。出错行为另由现有 mock 单元测试覆盖，不能代替真实供应商故障测试。真实问答的前端展示尚未验证。

## 阶段三：隔离与安全

服务通过配置的 `LEGACY_BOOTSTRAP_USER` 查找固定用户；课程按 owner 读取，学习证据和知识状态也关联该用户。课程、资料、诊断等接口未提供可验证的评委身份：无凭据请求实例 A 的 `GET /api/diagnostics/assessments/1` 返回 200。课程详情也显示编辑、删除入口。由此不能将当前实例视为安全的多用户服务。

本次验证两个同时运行、不同端口和不同 SQLite / 上传目录的本地实例：

- A 浏览器完成 8 题并生成计划；B 尚未作答时，A 有 1 次诊断、8 条学习证据、8 条掌握历史；B 同类记录均为 0。
- B 独立开始诊断，初始已答 0，选每题最后一项，提交 0/8，独立生成学习计划 HTTP 200；此后两个副本各有 1 次诊断和 8 条各自的学习证据。
- A、B 均能读取同一个预置课程内容，但它们是两份副本，不是共享只读数据库。B 原本没有 A 的 assessment，返回 404；这只是数据库分离，**不是**越权拒绝测试。
- 由于客户端可直接访问同一实例接口，未通过同一服务器多评委隔离和越权拒绝要求。没有实现安全匿名会话、只读公共课程、每会话限额、统一速率限制或全局调用预算。禁止直接将现有共享用户服务公开。

## 阶段四：启动与测试

`scripts/start_demo.sh` 新建唯一临时副本，校验依赖、资源、端口、数据库课程、诊断 readiness 和前端代理；端口已占用时实际拒绝启动。脚本强制 `LLM_MODE=mock` 并清空模型字段，避免继承开发者密钥；退出时停止其启动的前后端进程，保留独立数据供检查。

通过 `git archive HEAD` 加上当前未提交的演示数据、脚本及客户端改动组装源码副本，复用现有虚拟环境和 node_modules 的软链接：本地启动、代理课程读取和首次诊断 readiness 通过，停止后端口关闭。运行该检查的外层 PowerShell 到 WSL 管道末尾发生多余 CR 命令错误，外层进程退出码为 1；上述业务与关闭结果有各自输出，**不把该整条命令记为完全通过**。未验证全新环境中下载和安装依赖，也未证明仅从远程基线克隆即可运行。

- 后端演示初始化与模型客户端：`pytest -q -p no:cacheprovider backend/tests/test_demo_initializer.py backend/tests/test_m2_llm_client.py`，26 passed。
- 前端 `npm run test`：33 个文件、237 个测试通过；测试运行有 Vue 事件参数警告。
- 前端 `npm run lint` 通过；`npm run build -- --outDir /tmp/learnpilot-contest-build-20261115`（含类型检查）通过，Vite 提示主 chunk 大于 500 kB。
- 本轮涉及的 Python 文件 Ruff 和启动脚本 `bash -n` 通过。
- 全量后端：隔离配置下运行 `pytest -q -p no:cacheprovider backend/tests`，510 passed，2 条 SQLAlchemy identity map 警告，耗时 467.99 秒。

## 最小在线部署准备

在身份隔离和预算控制完成前不得部署为公开多评委体验。最低方案可使用单机 HTTPS 反向代理托管前端静态资源并转发 FastAPI，SQLite 与 uploads 放持久卷、备份恢复并使用单写入约束，密钥仅放服务端私有环境，配置进程重启及脱敏日志。评委隔离可采用服务端认证的短期演示会话加共享课程只读权限；若改造范围过大，采用每评委独立实例并配合访问控制。两者都需验证越权拒绝、重置和删除权限。加每会话次数、速率和全局预算，并在供应商端设置实际费用上限；应用层限制不能保证账单上限。未创建部署配置或公网资源，以上是待完成设计而非已部署能力。

## 工作区与后续事项

- P0：当前 `demo_data/`、`scripts/init_demo.py`、`scripts/start_demo.sh` 等为未跟踪文件；确认内容后纳入交付版本并验证评委访问权限，重新在干净机器安装运行。
- P0：真实知识抽取失败；查明结构不匹配或输出截断原因，限定费用后复测；真实问答需前端及内容准确性验收。
- P0（在线）：补齐服务端身份绑定、课程保护与越权拒绝，或提供受保护的独立实例；实现调用限额、速率控制和全局预算，并进行双评委安全验收。
- P1：实际部署及 HTTPS、持久化、恢复、日志、供应商费用上限；补充可访问的演示地址与视频。
- P1：让演示说明清楚解释首次诊断后知识状态为何仍是证据不足；补充实际模型结果的人工审查。
- P2：定位浏览器控制台的 404，评估前端大 chunk 和测试告警；验证 Windows 原生支持。

历史演示资料授权来自用户对既有文件所有权及使用许可的明确确认；详细来源与快照内容见 `demo_data/README.md`。
