# LearnPilot — M3 Final Acceptance

## 1. 验收基线

- 验收基线：当前 `main` 工作区，保留所有既有未提交修改；本轮未执行 Git 清理、还原、提交或推送。
- 本轮未修改知识抽取、规范化、关系推断、Provider 或数据库业务逻辑。
- 浏览器使用隔离 SQLite 数据库 `/tmp/learnpilot-e1e-20261014-1337.sqlite3` 与 `LLM_MODE=mock`，未触碰用户运行数据库。

## 2. 验收结果

| 验收组 | 结果 | 验证依据 | 遗留问题 |
|---|---|---|---|
| 课程管理 | PASS | 课程卡片测试、课程概览测试、真实卡片进入课程 | 创建/删除未在真实浏览器执行，已由隔离自动化覆盖 |
| 课程资料与 M2 | PASS | 后端 M2 测试、前端资料相关测试、课程资料入口回归 | DeepSeek 本轮未重测 |
| 课程知识模型 | PASS | M3-A～M3-D 后端测试、真实课程 7 节点/5 层级/6 先修关系 | 隔离课程来源记录为空，来源空状态实测 |
| 知识构建与更新 | PASS | M3-E 构建与状态测试、后端回归 | 未对真实课程执行付费重建 |
| 学习概览 | PASS | `CourseOverview` 测试与真实课程默认页浏览器验证 | 无 |
| 知识详情 | PASS | 详情组件测试与真实详情/返回地图验证 | 来源证据展开在自动化测试覆盖，浏览器使用无来源空状态 |
| 统一知识地图 | PASS | 地图适配、树、聚焦图测试与真实地图验证 | 无 |
| 地图交互 | PASS | 87 个前端测试；真实滚轮、缩放、平移、焦点和 URL 验证 | 触控板硬件未直接测试 |
| 边界与安全 | PASS | 课程隔离、无效关系、空状态、来源空状态、375px 检查；敏感信息扫描 | 无 P0/P1 |
| 工程质量 | PASS | 后端、前端、迁移、diff 检查全部通过 | Vite 保留既有大 chunk 警告 |

## 3. 自动化检查

- Backend pytest：**146 passed**。
- Ruff lint：**PASS**。
- Ruff format check：**105 files already formatted**。
- Frontend Vitest：**15 files / 87 tests passed**。
- TypeScript `vue-tsc --noEmit`：**PASS**。
- Production build `vue-tsc -b && vite build`：**PASS**，1744 modules transformed。
- ESLint：**PASS**。
- Prettier check：**PASS**。
- `git diff --check`：**PASS**。
- Alembic：隔离 SQLite 从 `0001_m1a_foundation` 升级至 `0007_m3e_workspace_build_state`：**PASS**。
- 敏感信息及运行文件扫描：**PASS**；未发现密钥、数据库运行文件、上传目录或构建产物进入 Git。

验收期间发现生产 build 的两个类型兼容问题：知识结构 query 的 `delete` 类型和 Router resolved location 类型不一致，已做最小类型修复并重新通过全量测试与构建。首次跨 WSL 文件系统执行前端测试和构建出现超时/`EBADF`，重试后通过，属于执行环境 I/O 时延，不是功能失败。

## 4. 浏览器流程

- Flow A：课程列表整卡进入 `/courses/1`；默认选中“学习概览”；三个学习入口和真实统计可见。
- Flow B：知识地图进入详情；详情显示真实概念、前置/后续、主题归属；返回地图恢复 `nodeId=4`。当前隔离课程无来源记录，页面显示真实来源空状态。
- Flow C：左侧节点聚焦、中央节点聚焦、URL 同步、页面滚动保持、图谱滚轮滚动网页且不缩放、`+` 缩放、空白画布平移均通过。
- Flow D：刷新恢复焦点；375px 视口下 `clientWidth=scrollWidth=375`，无水平溢出。
- 浏览器最终控制台：0 errors / 0 warnings。

## 5. Provider 与数据安全

- DeepSeek：**Previously verified — not rerun in this acceptance**。本轮没有重复付费调用。
- 浏览器验收使用隔离课程与显式 Mock 模式；未把 Mock 结果冒充真实 Provider。
- 未执行破坏性课程删除、知识重建或真实用户数据修改。

## 6. 缺陷分级与结论

- P0：0
- P1：0
- P2：Vite 既有单 chunk 大于 500 kB 的构建警告；不阻断 M3 核心流程。
- 最终结论：**PASS**。
- M3 建议：**可以进入 M4**。进入前仍建议将生产构建的 bundle warning 作为独立性能技术债处理，不作为 M3 阻断项。
