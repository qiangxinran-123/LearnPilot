# LearnPilot 传智杯 · 代码仓库与 Codex 开发记录

整理日期：2026-11-14（北京时间）。公开副本已将本机用户目录脱敏；Codex 内部链接仅供原作者定位，评委可直接阅读文本。

这份材料选取了 3 个核心功能迭代，共 20 轮开发对话。每条链保留用户需求、Codex 的可见回复，以及用户发现问题后如何约束下一轮修复。赛道选择、技术文档写作、其他项目和单独的推送闲聊未入选。交付物是从 Codex 聊天记录整理出的文本快照。

[LearnPilot 的 GitHub 仓库](https://github.com/qiangxinran-123/LearnPilot) · [本地 HEAD 的 34 条提交](Git_演进日志.tsv)

| Prompt 链 | 建议重点阅读 | 对应 Git 提交及代码证据 |
|---|---|---|
| [01 统一知识地图与点击回顶](01_知识地图_Prompt链.md) | 01.01–01.02 记录地图实现。01.04 是人工验收指出页面回顶并要求最小修复。01.05 记录滚轮、缩放和焦点导航的进一步调整。 | [1225bc5](https://github.com/qiangxinran-123/LearnPilot/commit/1225bc59fd87ff34470f48a4f90ea4659f455a3b)。重点见 `frontend/src/router/index.ts`、`frontend/src/components/knowledge/KnowledgeStructurePanel.vue`、`frontend/src/components/knowledge/KnowledgeFocusGraph.vue`。 |
| [02 诊断题库生成与审核入口](02_诊断题库_Prompt链.md) | 02.01–02.02 从 59 个知识节点、0 道合格题区分数据不足和算法错误。02.03–02.04 分步补上题库接口和前端审核。 | [6e7bda3](https://github.com/qiangxinran-123/LearnPilot/commit/6e7bda340f3d4205e24e86a1bf91c57f0c8c70be)。重点见 `backend/app/services/diagnostic_question_bank_service.py`、`frontend/src/components/diagnostic/QuestionBankPanel.vue`、`backend/tests/test_fix1_diagnostic_question_bank.py`。 |
| [03 动态诊断和自适应练习](03_动态诊断与练习_Prompt链.md) | 03.02 纠正局部修补，03.04–03.06 保留失败回溯和补丁验证，03.07–03.08 复核缺题后为何卡住，03.09–03.11 完成诊断补题并回到真实浏览器验证。 | [b9f01fb](https://github.com/qiangxinran-123/LearnPilot/commit/b9f01fbbf6a4d1e3713e333287f7c6465065bd74)。重点见 `backend/app/services/diagnostic_experience_service.py`、`backend/app/services/adaptive_practice_service.py`、`backend/tests/test_diagnostic_dynamic_api.py` 和 `backend/tests/test_practice_replenishment.py`。 |

## Git 演进与原聊天的对应关系

本地 HEAD 可追溯到 34 条提交。最早的 `61c96ac`（init FastAPI backend）只包含 `.gitignore` 和 `backend/main.py`。其后按 API、资料上传与解析、搜索、学习卡片、前端和 V1 里程碑逐步加入功能。提交日期、哈希和原始主题见 TSV。

上表按提交中实际出现的模块、测试和阶段报告定位。一个功能提交常包含多轮对话中的修改，尤其是 `6e7bda3` 和 `b9f01fb`；正文保留各轮原有的完成或未完成结论。03.11 的浏览器修复与 Fake Provider 业务验证分别记录，真实 DeepSeek 补题当时失败的具体原因未确定。

## 提交时核对

- 用未登录窗口或评审账号打开仓库与对应提交链接，确认可访问。当前材料核对了本地 Git 和既有推送记录，未独立确认评审权限。
- Markdown 可以直接阅读。若提交系统要求截图、录屏或原始导出文件，请从各链中的 Codex 聊天链接和回合时间定位，保留同一链的连续上下文。
- 源聊天里的本地路径、内部端口和开发用例为当时记录。向赛事方提交前复核对话内容的可公开范围。
