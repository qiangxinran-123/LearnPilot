# UX-FIX-4 知识图谱可靠性与操作反馈

状态：PARTIAL。已复现并修复一个明确的规模边界，但没有原始人工验收课程的资料规模或失败日志，不能证明该边界就是原始故障的唯一原因；未执行真实 Provider 联调。

## 复现与根因

使用隔离 SQLite、已有夹具和可控模型输出，修改前分别验证 1 份、20 份及 201 份资料的规范化。前两种通过；201 份资料产生 402 条原始候选但只有 2 个不同知识点，默认原始候选上限为 200 个不同知识点上限的两倍（400），因此在规范化快照阶段明确失败，模型未调用。大资料分块及关系失败后旧模型恢复的现有测试也通过。该合成条件是可验证的故障，并非原始现场故障已被确认的证据。

失败阶段：规范化前的候选快照检查。影响模块为 M3 规范化配置、候选合并和构建状态展示；主要风险是允许更多来源增加数据库读取及持久化时间。

## 实际修改

- backend/app/core/settings.py：原始候选独立配置，默认上限 1000；不同知识点仍限制为默认 200，不取消资源边界。
- backend/app/services/knowledge_canonicalization_service.py：使用独立上限；模型语义判断只需要已有代表 ID，不再把每个精确重复候选 ID 放入模型上下文。候选、来源和归并记录仍完整保存，未更换去重或关系算法。
- backend/app/ai/errors.py、knowledge_extraction_service.py、knowledge_canonicalization_service.py、knowledge_relationship_service.py：保留原有阶段错误码，同时给超时、限流、认证和未配置提供安全反馈；不输出 Provider 原始错误内容。
- backend/app/services/course_knowledge_build_job_service.py：失败日志记录课程、任务、真实阶段和错误码，不记录资料或密钥。
- frontend/src/components/knowledge/buildStatus.ts、CourseOverview.vue、KnowledgeStructurePanel.vue、frontend/src/views/CourseDetailView.vue：区分首次生成与更新的等待说明，真实阶段仍来自后端；显示未解析或解析失败的资料数，运行时保留禁用的生成按钮，显示启动和状态轮询失败。
- 测试：backend/tests/test_m3_fix_candidate_limit.py、test_m3b_knowledge_extraction.py；frontend/src/tests/course-overview.spec.ts、knowledge-build-status.spec.ts、knowledge-structure-panel.spec.ts、knowledge-workspace.spec.ts。

## 覆盖、边界与失败策略

现有提取按每份成功解析且非空的资料执行；单份默认最多 200000 字符，分块大小默认 800 字符、相邻块有 120 字符有意重叠，批次上下文默认最多 12000 字符。每个分块按现有流程处理一次；新增多批测试验证独立资料段不遗漏、不重复。模型重试沿用现有有界配置，默认两次；不重试认证失败。未解析或解析失败的资料由已有状态计数，并在界面说明未纳入。

201 份资料、402 条重复候选的隔离测试在修复后得到 2 个节点、402 个归并记录，两个节点均保留全部来源。候选超限仍明确失败；实际不同知识点上限默认 200，关系生成节点上限默认 120，不能声称支持无限规模。最终关系失败时沿用现有检查点恢复机制；浏览器的超限更新失败验证旧图谱仍可读。

## 验证

- 后端完整回归：461/461 通过；完整回归后补充的分批覆盖测试单独 1/1 通过。先前 M3 相关定向测试 51/51 通过。
- 前端最终完整回归：230/230 通过；TypeScript、ESLint、生产构建通过。Ruff lint、format check 和 git diff --check 通过。
- 隔离浏览器明确使用 Mock Provider：1 份与 4 份已解析资料首次生成成功；生成时展示等待说明、按钮禁用且仅发一次请求。四份资料均有知识来源记录。加入一份超限资料后更新失败，旧图谱和错误提示保留；模拟启动请求失败也显示在知识地图页。延迟旧课程响应后切换课程未串状态。1440、1280、1024 像素检查无页面横向溢出；1024 像素截图检查错误及旧图谱布局。
- 真实 Provider：NOT REQUIRED，本轮未进行付费调用，也未检查或展示用户密钥；Mock 结果不能证明真实 Provider 的响应质量或性能。既有 Vue 测试事件警告和构建大包提示仍在。

## 剩余限制

未取得原始失败现场和日志，无法确定当时是否由上述边界、Provider、资料解析或其他阶段触发；因此问题 11 的原始故障保持未完全验证，UX-FIX-4 为 PARTIAL。更大规模仍受明确上限及处理时间约束；未新增迁移、依赖、任务平台或其他阶段功能。
