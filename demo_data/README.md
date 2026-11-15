# LearnPilot 预置演示课程

## 内容与来源

演示课程「计算机系统：Cache 与局部性（演示）」包含 1 份课程摘录（375 字）、17 个知识节点、5 条层级边、10 条先修边和 10 道已审核诊断题。第一次诊断准备状态为 ready，可直接创建 8 道题。

资料来自项目原有的计算机系统课程复习提纲摘录，用户在 2026-11-15 明确确认以前使用的文件为其所有并允许使用。摘录 SHA-256：4b138a42b0cb2f3db0d8dac47edf2b7a34e4d6160cd291ff5b2ae13930c6b689。发布前如需独立的书面来源声明，请由资料权利人提供。

历史知识候选、规范化及关系由 DeepSeek 真实调用生成，保存原始 provider、model 和 prompt_version；题目经历史人工审核和部分修订。演示快照来自原有隔离测试数据库的副本，不包含新增伪造的模型调用。课程文本、节点、先修语义和题目的全面学科正确性尚未经过独立系统评审；请按演示资料使用。

副本清除诊断、作答、证据、掌握状态、推荐、学习会话和导师消息，使用固定的本地演示身份。所有保留数据均位于 demo.sqlite3 和 uploads 中。manifest.json 是完整性校验，不能证明内容质量或授权。

## 初始化

在已安装项目 Python 依赖的 Linux / WSL 仓库根目录运行。目标必须为不存在的新目录，父目录必须已存在：

~~~bash
.venv/bin/python scripts/init_demo.py --destination /tmp/learnpilot-demo-evaluator-1
export DATABASE_URL=sqlite+pysqlite:////tmp/learnpilot-demo-evaluator-1/demo.sqlite3
export UPLOAD_ROOT=/tmp/learnpilot-demo-evaluator-1/uploads
export LEGACY_BOOTSTRAP_USER=legacy-bootstrap@learnpilot.local
export LLM_MODE=mock
.venv/bin/alembic current
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
~~~

另开终端在 frontend 运行 npm run dev，通过 http://127.0.0.1:5173 访问。环境变量在对应 shell 生效；请使用初始化命令输出的绝对路径。快照版本为 0019_m8_mastery_history，若代码迁移链更新，先在副本中核对兼容性并迁移，不要直接迁移打包快照。

重复使用相同目标只提示已初始化，保留现有答题记录。需要新的干净状态时选择新的目标目录。不同评委使用独立数据库和上传目录，并分别启动对应服务；当前系统没有正式多用户登录。目标目录已存在且不是已识别的演示副本时会拒绝执行。初始化中断时保留新目录供检查，不会覆盖已有目录。

课程和已准备题库的首次诊断无需真实 AI；若再次诊断或练习题不足，可能触发模型补题。LLM_MODE=mock 的生成结果仅为模拟，真实问答与新增生成需要独立配置 provider。

## 验证记录（2026-11-15）

- 只读审查历史数据库 revision 0019、外键违规 0，原始上传哈希与历史预检一致。
- 清理后的快照 SQLite integrity_check 和 foreign_key_check 通过，常见密钥、手机号和私人目录模式扫描为 0；邮箱命中仅为本地演示身份。有限模式扫描不等于完整安全审计。
- 独立临时副本 API 返回：课程 1、资料正文 375 字、知识点 17、关系 15、节点 3 来源 1；诊断 readiness 为 ready、覆盖 8 节点、合格题 10。
- 在空学习状态下通过真实本地 HTTP 创建并开始诊断，8 道均选择首个选项后提交，6/8 正确，生成 8 条 Evidence；读取 17 个知识点状态并生成 preliminary 计划。诊断结果和 8 条作答仅写入临时验收副本。
- 新目录初始化成功；第二次运行保留数据库哈希；无关既有目录被拒绝；两个全新目标数据库初始哈希一致。
- 完整浏览器人工操作和跨版本升级未在本轮执行。历史源文件属于用户授权材料；公开前可按实际发布方式再次确认授权范围。真实模型未在本轮调用。

正式 README 和生产部署未修改。

- 新增自动化回归：backend/tests/test_demo_initializer.py，2 passed；Ruff 检查通过。节点 3 返回的来源原文片段与资料正文匹配。