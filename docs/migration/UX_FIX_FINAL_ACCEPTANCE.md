# UX-FIX-1～5 联合验收

结论：**NOT COMPLETE**；M9 尚未具备继续条件。本次未修改 M5、M6、M7 核心算法或跨 Session 证据语义，未新增依赖或迁移。下表区分本轮执行和此前阶段的浏览器证据。

| 问题 | 阶段与处理 | 自动化及浏览器证据 | 状态 |
| --- | --- | --- | --- |
| 01 推荐解释 | UX-FIX-5 移除两个独立说明区，保留推荐数据 | 本轮前端测试及 Learn 浏览器检查 | PASS |
| 02 学习任务 | UX-FIX-1 使用实际学习行为，但跨 Session 同源题可产生独立证据 | 本轮隔离浏览器和只读数据库核对发现重复源题独立计入；权重语义未获授权修改 | FAIL |
| 03 学习步骤和数量 | UX-FIX-1 单页流程、动态题量 | 本轮浏览器完成 5 题；单题、无题及恢复沿用 UX-FIX-1 既有浏览器记录和本轮完整测试 | PASS |
| 04 重复推荐 | UX-FIX-1/5 本轮完成后不自动重开相同目标，保留主动复习 | 本轮浏览器复现返回后再次显示相同推荐；修复后验证结束状态及无自动新建；定向测试通过 | PASS |
| 05 诊断历史 | UX-FIX-2 隔离正式诊断和练习 | 本轮浏览器显示 1 条正式诊断而非 2 条学习记录；完整测试通过 | PASS |
| 06 学习历史弹窗 | UX-FIX-3 复用历史列表 | 本轮浏览器打开关闭弹窗，保留课程和时间筛选 | PASS |
| 07 判断题 | UX-FIX-2 中文选项及原提交值 | 完整测试通过；不同宽度视觉与评分沿用 UX-FIX-2 已记录的浏览器验收，本轮未重新操作 | PASS |
| 08 Progress 图表布局 | UX-FIX-3 趋势靠前、比较限量 | 本轮浏览器及完整测试；原统计和风险区保留 | PASS |
| 09 批量审核 | UX-FIX-2 复用单题审核并反馈部分失败 | 本轮完整测试通过；合法、异常和部分失败的浏览器操作沿用 UX-FIX-2 报告。本轮从生成到正式诊断未通过 Mock 生成环节 | PASS |
| 10 课程选择器 | UX-FIX-5 复用课程上下文并统一入口 | 本轮相关测试及不同宽度页面检查 | PASS |
| 11 大量资料建模 | UX-FIX-4 修复可复现的 201 份资料候选数边界 | 既有隔离测试覆盖 201 份资料；本轮两份资料 Mock 生成成功。原始现场日志缺失，不能证明原故障已解决 | NOT VERIFIED |
| 12 AI 等待反馈 | UX-FIX-4 保留真实状态、错误及禁用操作 | 本轮隔离 Mock 浏览器看到等待和完成；失败及旧图谱保留沿用 UX-FIX-4 记录 | PASS |
| 13 产品文案 | UX-FIX-5 精简有关一级页面说明 | 本轮完整前端测试及页面检查 | PASS |
| 14 学习导航 | UX-FIX-1/5 保持课程及完成上下文 | 本轮浏览器从完成反馈返回 Learn，保留课程且不自动新建 Session；相关测试通过 | PASS |
| 15 页面密度 | UX-FIX-3/5 精简历史和重复内容 | 本轮五个一级页面在 1440、1280、1024、768px 检查无横向溢出，并检查部分截图 | PASS |

## 本轮修改

Learn 移除独立推荐理由和前置依据面板，不删除推荐依据或 prerequisite 数据；精简 Dashboard、Course、Diagnose、Learn、Progress 文案及间距，复用课程选择器。

本轮隔离验收复现完成 Session 后返回 Learn 原推荐重新出现。完成 Session 的返回链接携带当前节点；若后端仍推荐该节点，页面展示本轮结束，并保留主动重新学习入口。推荐排序和长期掌握度未改变。

本轮修改 frontend/src/views 下 DashboardView、CoursesView、DiagnoseView、LearnView、LearningSessionView、ProgressView，frontend/src/tests 下 diagnose-view、learning-plan-views、learning-session-view 测试，以及本报告。其他既有工作区修改保留。

## 本轮工程验证

- 完整 Backend pytest：462/462 PASS；完整 Frontend Vitest：232/232 PASS。相关前端定向测试 34/34 PASS；另一次包含 Progress 的定向测试 47/47 PASS。计数不相加。
- TypeScript、ESLint、生产构建、Ruff lint 与格式检查：PASS。构建保留既有大包提示。
- Alembic 在隔离 SQLite 上 upgrade head 和 current：PASS（0019_m8_mastery_history）；alembic check：FAIL，检测到既有 knowledge candidates/nodes 索引及 users email 唯一性定义与 metadata 不一致。未新增迁移，需先区分实际结构差异和 SQLite 反射差异。
- Git diff check：PASS（修正一处空白后）。密钥检查仅针对新增差异和未跟踪文本做启发式扫描，不读取 .env，不等同完整专业密钥审计。

## 浏览器与限制

- 学习：隔离课程实际完成概念、5 道练习和反馈、Evidence/Mastery 展示及返回；同源题跨 Session 证据问题使可信度验收失败。0/1 题及刷新恢复沿用 UX-FIX-1 先前记录。
- 诊断：本轮验证正式诊断历史与练习分离。隔离 Mock 生成请求返回生成 0、失败 1，故本轮“生成 → 批量审核 → 正式诊断”整体 NOT VERIFIED；不将 Mock 能力不足视为真实 Provider 结果。批量审核、异常题和部分失败已有 UX-FIX-2 阶段浏览器记录。
- Progress：浏览器查看趋势、风险、历史弹窗及状态保留。
- 知识生成：隔离课程上传两份自制资料，Mock 模式看到等待并生成图谱；这不是原始大资料场景或真实 Provider 验证。之前的规模测试与限制见 UX-FIX-4 报告。
- 桌面和窄屏：本轮五个一级页面按四个宽度检查横向溢出并查看部分截图；判断题专项视觉沿用此前记录，不能将全部业务流程等同于本轮在每个尺寸重新验收。

## 阻塞项与后续方案

1. **跨 Session 证据身份未定义**：隔离课程两次学习的源题分别为 [8,1,2,3,4] 和 [5,6,7,8,1]，重复源题 8、1 在不同快照下产生独立 Evidence。当前只确认重复被独立记录；掌握度变化还受到其他新题影响，不能把全部变化归因于重复题。需产品确认如何区分请求重试、立即重复练习与间隔复习，并决定源题 ID/版本的去重或权重语义；这会影响 M5 输入、Confidence 和 M8 历史解释。现有自动继续过滤不能保证主动复习不重复计分。本轮依照既有授权未修改证据身份、指纹、算法或数据库。
2. **Alembic 一致性检查失败**：先只读核对索引、唯一约束及 SQLite 反射差异，再提出最小修复；不能仅凭自动生成结果追加迁移。
3. **原始大资料故障与完整诊断生成流程未验证**：需要原故障的不含密钥日志、资料规模或可复现隔离样本；诊断完整流程需要合法隔离生成数据或可用 Provider。不得将 Mock 成功视为真实 Provider 成功。

UX-FIX 总体 **NOT COMPLETE**；M9 **NOT READY**。M8-4 历史报告记录 89.5%，M8 最终验收未确认，不提升至 90% 或 96%。


## FIX-A 跨 Session 证据可信度（本轮）

- **身份链**：题库 Question 的 ID 和 content_version 被复制到每次 AssessmentQuestion 不可变快照的 source_question_id、source_question_version。每个快照有独立 ID，Response 的唯一约束是一份快照一个真实作答。Evidence 原唯一身份由来源类型、快照 ID、历史知识点和证据 schema 版本构成，原先不能跨快照识别同源题。M5 对已保存 Evidence 生成指纹并计算掌握度与置信度；M8 学习历史按已完成 Session 读取。
- **复现**：隔离单题测试中相同请求重试复用 Response；两次 Session 的两份 Response 在修复前生成两条有效 Evidence，证明问题不只是作答记录数量。此前隔离多题验收也观察到不同快照引用相同源题。
- **修复**：结算时，复用不可变快照中的源题 ID 和版本，按用户、课程、历史知识点查询已有 Evidence；相同来源及版本的后续作答保留 Response、评分和 Session，跳过新增 Evidence。不同源题或新内容版本正常进入原链路。同一 Session 原有请求重试机制不变。所有重复题无新增 Evidence 时不刷新 Mastery；已有且有效的掌握度可原样反馈。
- **并发**：原结算事务先执行 Session 条件写，SQLite 写锁和支持行锁数据库的 Course 行锁串行化同课程 Session 结算；同次作答的 Response 唯一约束和原有重试处理保留。并发测试覆盖同一作答及同一 Session 结算；不声称与其他独立诊断写入入口之间有新的全局原子唯一约束。
- **Fingerprint、快照和历史**：不改指纹或 M5 算法；无新 Evidence 时有效集合和指纹不变，不因重复题刷新历史快照，真实完成事件仍在 M8 历史。新 Evidence 使用现有刷新和快照机制。
- **兼容边界**：不删除、回填或重算旧 Evidence 和快照；原有历史重复 Evidence 仍可被 M5 读取，未来遇到新有效题目时可能按原规则一起参与计算。系统没有可靠的即时与间隔复习标识，V1 保守地将同源同版本后续作答都视为非独立证据；这不否认间隔复习价值。不同 ID 的等价题没有可靠现有等价标识，不做内容或语义猜测。诊断入口后续生成 Evidence 的身份语义未改变。
- **验证**：相关定向测试 48/48 PASS（包括原修复测试、M7、M8 历史与 M6 回归）；Ruff check 与 format PASS。完整后端回归 469/469 PASS；git diff --check PASS。未修改前端、API 契约、数据库模型或迁移，无真实模型调用。
- 原有 FIX-B Alembic 一致性、VERIFY-C 诊断完整流程、VERIFY-D 原始大资料故障仍未解决；本轮不处理。

FIX-A 状态：**COMPLETE**（仅针对后续 M7 练习证据写入；上述历史、间隔复习及跨入口并发限制仍适用）。UX-FIX 总体仍为 **NOT COMPLETE**，M9 **NOT READY**。


## FIX-B — Alembic Schema Consistency

初始隔离空库 upgrade head 成功，alembic check 失败。三方比对的差异如下：

| 对象 | 历史迁移及 SQLite 实际结构 | 原 ORM 声明 | 分类与处理 |
| --- | --- | --- | --- |
| users.email | 0001 建立 uq_users_email 唯一约束及 ix_users_email 非唯一索引；SQLite 分别反射为唯一约束与普通索引 | unique=True 与 index=True 生成唯一索引 ix_users_email | 元数据与历史结构不一致；声明独立唯一约束及非唯一索引，保持原业务唯一性 |
| knowledge_candidates(id, course_id) | 0005 创建名为 uq_knowledge_candidates_id_course 的显式复合唯一索引，供复合引用使用 | 同名 UniqueConstraint | 索引与约束对象种类不一致，唯一语义一致；模型改为显式唯一索引，不移除索引或改变外键 |
| knowledge_nodes(course_id, is_active) | 0005 创建 ix_knowledge_nodes_course_active 非唯一索引 | 未声明该索引 | 元数据遗漏历史索引；模型补充非唯一索引 |

原因是模型元数据与现有迁移的对象声明不一致，而非数据库缺失业务唯一约束；SQLite 索引和隐式唯一约束可分别正确反射。未改 Alembic 配置、未忽略任何对象、未更改已应用迁移，未新增迁移、表重建或数据迁移。

- 新隔离空库 upgrade head、alembic check、再次 upgrade head：PASS；原复现库更新模型后 check 也通过。
- 隔离旧库从 0018 升级到 0019：PASS；预先写入的用户、课程、知识节点及外键检查通过，数据保留。
- 真实漂移检测：分别在两个隔离库删除知识节点非唯一索引、候选复合唯一索引，alembic check 均准确失败；未关闭全局比较。
- 写入行为：不同用户可写入、相同邮箱被拒绝，非法课程外键被拒绝；目标索引的列与唯一性经 Inspector 检查。FIX-A 及相关知识索引定向回归合计 27/27 PASS。
- Ruff check 和 format：PASS；完整后端回归 473/473 PASS；git diff --check PASS。前端及 API 契约未变，无需运行前端检查。
- 密钥检查仅为新增差异的启发式模式扫描，未读取 .env；结果为零匹配，不等同完整安全审计。正式用户数据库未检查或更改。

FIX-B 状态：**COMPLETE**。VERIFY-C、VERIFY-D 仍未完成；UX-FIX 总体 **NOT COMPLETE**，M9 **NOT READY**。


## VERIFY-C — Diagnosis Flow

状态：**NOT COMPLETE**。正式诊断链路在隔离浏览器和仓库已有脚本化测试适配器下已走通，但内置 ExplicitMockLLMClient 仍不支持诊断题输出，因此不能声称系统自带 Mock 的生成能力已通过，也没有验证真实 Provider。

- 原始 0 题、1 项失败：REPRODUCED。合法隔离课程有已成功构建的知识节点及可解析来源；使用 LLM_MODE=mock 时，ExplicitMockLLMClient 对 DiagnosticQuestionGenerationOutput 没有对应分支，返回摘要形状而缺少 questions，Pydantic 校验失败。生成服务的通用异常分支将其映射为 QUESTION_GENERATION_FAILED。属于内置 Mock 适配器与诊断输出契约不匹配，不证明真实 Provider 或数据库写入失败。本轮没有修改生产代码或虚构模型输出。
- 隔离数据：临时 SQLite、测试用户、两门用户隔离课程及额外一门同用户测试课程；使用已有 seed_foundation 的知识节点和真实来源夹具。正式浏览器生成使用现有 ScriptedLLMClient，仅替代模型响应；真实生成服务仍执行结构、来源、关联和去重校验并持久化待审核题。7 道已有合法待审题、1 道结构异常题和本轮生成的 1 道判断题组成题库。
- 浏览器生成与审核：页面从 0/8 可用题显示真实缺口；正式准备接口生成并保存 1 题，题库共 9 题。资格预览识别 8 道可确认、1 道需检查。模拟单个审核请求 500 后页面显示 7 道确认、2 道未确认；解除拦截后通过原逐题审核确认余下合法题，达到 8 道可用、2/2 知识点覆盖，异常题仍待审核。结构校验不保证学科正确。
- 正式诊断：浏览器逐题保存并提交 8 题，故意答错 1 题得到 7/8；刷新后结果保留，重复提交返回同一结果。第二次诊断先验证未完成状态与历史区分，恢复后全部答对得到 8/8。包含生成的判断题及单选题；判断题在 1440、1024、768 像素实际 DOM 检查为正确/错误且无页面横向溢出，视觉截图沿用 UX-FIX-2 既有验收。
- 历史及 Evidence：第一次诊断后完成独立 M7 练习，浏览器最近诊断只显示正式诊断，M8 历史分别包含诊断与学习事件；切换另一门隔离课程历史为空，切回后记录恢复。只读核对第一次诊断后为 8 条诊断 Evidence、5 条练习 Response；这 5 道练习均已有同源证据，FIX-A 不新增练习 Evidence，未凭空产生 Mastery Snapshot。
- 定向测试：本轮后端 88/88 PASS，覆盖生成、异常来源/结构、审核、评分、正式 HTTP 诊断、归属和 FIX-A；Ruff lint 与 format PASS。当前源码未修改，完整后端 473/473 PASS 引自刚完成的 FIX-B 工作区基线，并非本轮重跑；前端 232/232 为更早 UX-FIX 验收基线，本轮未重跑。git diff --check PASS。
- 真实 Provider：NOT VERIFIED，未调用付费模型。除内置 Mock 无诊断题输出外，练习全为重复证据时现有学习反馈文案仍称已重新计算掌握度，而 FIX-A 实际跳过重算；这是本轮范围外的文案限制，未擅自修改。未修改 Schema、迁移、M5/M6/FIX-A 逻辑或用户数据。

剩余：为内置 Mock 设计符合诊断契约、不伪造来源和不靠重复题凑数的行为，并在相同隔离流程重新验证；VERIFY-D 仍未开始。UX-FIX 总体 NOT COMPLETE，M9 NOT READY。


### VERIFY-C 中断后续接

此前保存在临时目录的验收数据库和浏览器会话在中断后已不存在；本次重新建立继续验收所需的隔离数据库和题库，未重跑此前通过的自动化测试。新夹具使用覆盖淘汰对象、访问后更新、访问序列、时间戳、FIFO 对比和最近访问顺序等不同细节的自制题目，并由正式审核服务确认；再通过既有脚本化测试适配器生成 1 道有来源的判断题，异常题保持待审核。浏览器实际开始 8 题诊断、逐题保存，故意答错 1 题，真实评分为 7/8。原先的完整回归 473/473 和定向测试 88/88 均为此前结果，未在本次续接重跑。

内置 ExplicitMockLLMClient 对诊断生成仍不支持，真实 Provider 仍 NOT VERIFIED；本次没有修改业务代码，VERIFY-C 保持 NOT COMPLETE。


## VERIFY-C-FIX — 内置 Mock 诊断生成

原问题为 ExplicitMockLLMClient 没有诊断题分支，诊断输出被当成摘要结构生成，缺少 questions。现仅在 operation 为 diagnostic_question_generation 且 Schema 为 DiagnosticQuestionGenerationOutput 时启用分支；其他 Mock 与真实 Provider 路径保持原样。

Mock 使用现有正式提示中的目标节点 ID、题型、难度和已提供的资料引用，不虚构节点或资料 ID。单选、判断、多选均返回标有“模拟题”的资料原文核对题；此类题只用于测试流程，不证明学科质量。每次只支持生成一题；多题请求、来源缺失或原文不足时明确返回 AI_INVALID_OUTPUT，不复制题目或放宽生成服务的数量与质量校验。由于提示格式或原文不足等情况可能无法构造合法题目，Mock 不保证支持任意资料。

隔离测试复用 test_m4b_question_generation 的课程、节点及材料来源夹具，验证正式诊断生成服务、题库准备、持久化、资格预览与审核：两个知识点各产生一题并审核通过，诊断仍按真实规则提示 2/8 可用。另验证三种题型的 Schema、来源、选项、确定性，及无效来源和多题请求失败；与既有其他 Mock 任务测试一起运行。未修改真实 Provider、诊断服务、数据库或前端。

定向回归：46/46 PASS；补充批量准备后的 Mock 测试 9/9 PASS（两次有重叠）。Ruff lint 与 format PASS。完整后端回归 482/482 PASS；git diff --check PASS。此前脚本化适配器浏览器诊断验收不重复执行。真实 DeepSeek Provider：NOT VERIFIED。

VERIFY-C-FIX：**COMPLETE**；VERIFY-C Diagnosis Flow：**COMPLETE**（限核心链路及内置/脚本化 Mock 验收）。真实 DeepSeek Provider：**NOT VERIFIED**。VERIFY-D 仍未完成，UX-FIX 总体 NOT COMPLETE，M9 NOT READY。


## VERIFY-D — Large Material Knowledge Generation

状态：**COMPLETE WITH LIMITATIONS**。原始人工验收课程的资料和日志不可用，原始故障未精确复现，根因 NOT DETERMINED；不得将此前复现的候选上限归因于原始现场。真实 Provider 未调用。

- 代表性隔离样本：6 份通过真实 DOCX 解析器的自制资料、21,963 个文本字符；4 个跨文档共享概念加 6 个文档独有概念。按测试配置分成 102 个文本块和 18 个提取批次（上下文上限 2,000 字符、分块 400 字符、重叠 50 字符）；未声称这是默认配置的生产吞吐。
- 使用现有脚本化 LLM 接口及真实提取、规范化、关系和编排服务。比较独立分块序列与实际逐批请求内容、顺序和边界；6 份已解析资料均参与，最终 10 个不同知识点、54 条来源，包含 1 条 contains 和 1 条 prerequisite，边端点和引用有效。新增数据库会话重读通过；1 份未解析资料按既有状态不纳入该六份。
- 异常：在更新资料的第二个提取批次注入超时，服务明确报失败，旧节点及边保持；重试成功，随后重复构建复用结果而不再调用模型。另验证解析失败资料独立计数、模拟写入失败后候选事务回滚和失败状态。既有测试覆盖不合法引用、结构、所有权、旧图谱恢复及原 201 份资料/402 候选的合成边界。边更新的同一测试会话持有旧对象，SQLite 重用边 ID 时产生 2 条 SQLAlchemy identity-map 警告；新会话重读和断言通过，未据此声称其他数据库并发行为已验证。
- 定向后端：已有相关组合 63/63 PASS；最终补强后的新增代表性及异常测试 3/3 PASS（与组合中 1 项重叠）。本轮无业务代码修改，完整后端 482/482 为上一阶段相同业务源码基线，本轮未重跑。Ruff lint/format PASS。
- 前端：本轮定向 Vitest 48/48 PASS；实际浏览器加载、重复点击、超限失败、旧图谱保留及 1440/1280/1024 布局复用 UX-FIX-4 已记录的浏览器验收，本轮未重新进行浏览器验收。未修改前端或 API，TypeScript、ESLint 和 Build 不适用。
- 限制：脚本化输出验证了现有服务可正确处理给定候选和关系，不证明模型的语义提取、所有资料必然生成节点或真实 Provider 在更大规模下的时延和可靠性。默认单资料输入、候选和关系节点仍受既有上限约束。未新增业务代码、迁移或依赖。

UX-FIX Overall 和 M9 Continuation Readiness 均待下一阶段最终验收，本轮不进入 M9。


## FINAL-ACCEPTANCE — UX-FIX Joint Regression

结论：**UX-FIX COMPLETE；M9 CONTINUATION READY**，仅表示可以继续 M9，不代表 M9 已完成。真实 Provider 质量、原始大资料故障及历史证据限制见下。

- 最终仓库：WSL /home/qxrrr/projects/campus-ai，分支 main，HEAD 91c34e4c0597c82bab5a0a172cb8079fdcdac7ec，领先 origin/main 1 次提交。验收源码指纹 SHA-256 为 18544ee8705a1bf18b3532e53ac43678c8527c6c0cf0b9586872024122d1507b，范围为 backend/app、backend/tests、backend/alembic 和 frontend/src 的已跟踪及未跟踪文件，共 352 个；不包括文档和环境配置。
- 初始工作区包含此前 UX-FIX、FIX-A/B/C/D 的未提交修改和未跟踪测试与报告；本轮保留这些修改，仅追加本报告。最终状态仍包含这些既有修改，未提交、推送、切换或重置。正式用户数据库未访问或修改。

| 问题 | 本轮代码/测试及复用的实际浏览器证据 | 结果 |
| --- | --- | --- |
| 01 推荐解释 | Learn 当前代码和完整前端测试；UX-FIX-5 浏览器记录 | PASS |
| 02 学习任务 | 学习流程组件与 M7 全量测试；UX-FIX-1 浏览器记录 | PASS |
| 03 步骤与题量 | M7 单题、多题、空题及组件回归；UX-FIX-1 浏览器 Case A–D | PASS |
| 04 重复推荐和证据 | FIX-A 当前源码与隔离定向测试包含于本轮全量；UX-FIX-5 返回流程浏览器记录 | PASS |
| 05 诊断历史 | 诊断 API/组件回归；VERIFY-C 浏览器及隔离数据库记录 | PASS |
| 06 历史弹窗 | Progress 组件回归；UX-FIX-3 与联合验收浏览器记录 | PASS |
| 07 判断题 | 判断题组件和评分回归；UX-FIX-2 浏览器视觉记录 | PASS |
| 08 Progress 图表 | Progress 测试及 UX-FIX-3 浏览器记录 | PASS |
| 09 批量审核 | 题库与结构校验回归；VERIFY-C 浏览器部分失败和重试记录 | PASS |
| 10 课程切换 | 课程切换及旧请求隔离测试；UX-FIX-5 浏览器记录 | PASS |
| 11 大资料建模 | VERIFY-D 代表性服务测试本轮随全量重跑；原始故障未复现，真实 Provider 未验收 | PASS WITH LIMITATIONS |
| 12 耗时反馈 | 知识构建状态组件测试；UX-FIX-4 浏览器成功与失败记录 | PASS |
| 13 产品文案 | 一级页面组件测试及 UX-FIX-5 浏览器记录；学习反馈文案有非阻塞限制 | PASS |
| 14 学习导航 | 会话和课程上下文测试；UX-FIX-1/5 及 VERIFY-C 浏览器记录 | PASS |
| 15 页面密度 | Progress 与 Learn 组件测试；UX-FIX-5 四宽度浏览器记录 | PASS |

FIX-A、FIX-B、VERIFY-C：PASS；VERIFY-D：PASS WITH LIMITATIONS。学习、诊断、Progress、Mock 知识构建流程由本轮自动化回归及此前隔离浏览器证据共同支持。此前浏览器包含 UX-FIX-1 的 0/1/多题，VERIFY-C 的正式诊断 7/8 与历史隔离，UX-FIX-3 的历史弹窗，UX-FIX-4 的生成等待和失败，以及 UX-FIX-5 的 1440、1280、1024、768px 页面检查。本轮未重新运行浏览器交互；历史结论不能代替真实 Provider 验收。

本轮实际执行：后端 pytest 485/485 PASS，前端 Vitest 232/232 PASS；Ruff lint/format、TypeScript、ESLint、生产构建、隔离 SQLite Alembic upgrade head/check 和 git diff --check 均 PASS。旧库升级与主动制造漂移检测复用 FIX-B 专项证据。现有 Vue 测试事件警告、大包提示，以及 VERIFY-D 同一测试会话两条 SQLAlchemy identity-map 警告未导致测试或新会话数据校验失败。

阻塞 P0：NONE。阻塞 P1：NONE。非阻塞限制：同源同版本复习采用保守证据策略，旧的重复 Evidence 未追溯清理；重复练习无新增证据时学习反馈文案仍可能说重新计算；VERIFY-D 原始故障 NOT REPRODUCED、根因 NOT DETERMINED；Mock 与脚本化适配器结果不证明真实 DeepSeek 诊断生成或大资料质量和性能。M8-4 历史记录的项目进度为 89.5%，M8 最终验收未确认，本轮不提升项目百分比。

M9 后续验收：受控真实 DeepSeek 诊断题质量、多资料知识提取质量与性能、长耗时与失败恢复，以及最终用户体验和比赛展示。不得把本次 READY 解读为 M9 COMPLETE。
