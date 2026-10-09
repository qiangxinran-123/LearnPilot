# LearnPilot API 总览

本文以当前 LearnPilot V1 / M3 最终验收代码为准。

- 本地 Base URL：`http://127.0.0.1:8000`
- Swagger UI：`GET /docs`
- OpenAPI JSON：`GET /openapi.json`

服务启动前必须配置 `DATABASE_URL` 并执行 Alembic 迁移。当前没有正式登录接口；所有课程数据通过配置的 bootstrap user 隔离，不能视为完整的多用户认证方案。

## 系统接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api` | 返回应用名称、版本和欢迎信息。 |
| GET | `/health` | 返回 `status: ok` 和服务名称。 |
| GET | `/api/project/status` | 返回当前项目阶段元数据。 |

当 `frontend/dist/` 存在时，FastAPI 会托管生产前端并对公开 SPA 路径提供 history fallback。`/api/*`、`/health`、`/docs` 和 `/openapi.json` 不会被 SPA fallback 覆盖。

## 课程接口

| 方法 | 路径 | 请求 | 成功响应 | 常见失败 |
| --- | --- | --- | --- | --- |
| GET | `/api/courses` | 无 | `200`，返回 `count` 和 `courses`。 | 数据库错误返回 `500`。 |
| POST | `/api/courses` | `CourseCreate` JSON | `201`，返回新课程。 | 校验失败返回 `422`。 |
| GET | `/api/courses/{course_id}` | 路径参数 | `200`，返回课程。 | 不存在或不属于当前 owner 返回 `404`。 |
| PATCH | `/api/courses/{course_id}` | `CourseUpdate` JSON | `200`，返回更新后的课程。 | 不存在返回 `404`；校验失败返回 `422`。 |
| DELETE | `/api/courses/{course_id}` | 路径参数 | `200`，返回 `{"id": ..., "deleted": true}`。 | 不存在返回 `404`；存储清理失败返回 `STORAGE_FAILURE`。 |

课程创建字段：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `name` | string | 必填，去除首尾空白，1–100 字符。 |
| `description` | string | 可选，最长 2000 字符。 |
| `category` | string/null | 可选，最长 120 字符。 |
| `learning_goal` | string/null | 可选，最长 1000 字符。 |
| `target_date` | date/null | 可选，ISO 日期。 |

`PATCH` 使用相同字段并只更新实际传入的值。课程响应还包含 `id`、时间戳、`material_count`，以及为旧客户端保留的 `semester` 兼容字段。

## 课程资料接口

| 方法 | 路径 | 请求 | 成功响应 | 常见失败 |
| --- | --- | --- | --- | --- |
| GET | `/api/courses/{course_id}/materials` | 路径参数 | `200`，返回课程资料列表。 | 课程不存在返回 `404`。 |
| POST | `/api/courses/{course_id}/materials` | `title`、`type`、`summary` JSON | `201`，创建不含上传文件的资料记录。 | 课程不存在返回 `404`；校验失败返回 `422`。 |
| POST | `/api/courses/{course_id}/materials/upload` | multipart 字段 `file` | `201`，保存、解析并返回资料。 | 文件名/类型错误返回 `400`；过大返回 `413`；存储错误返回 `500`。 |
| GET | `/api/materials/search` | 必填 `q`，可选 `course_id` | `200`，返回当前 owner 范围内的匹配资料。 | 空查询返回 `EMPTY_SEARCH_QUERY`；未知课程返回 `404`。 |
| GET | `/api/materials/{material_id}` | 路径参数 | `200`，返回资料元数据和处理状态。 | 不存在返回 `404`。 |
| DELETE | `/api/materials/{material_id}` | 路径参数 | `200`，返回删除确认。 | 不存在返回 `404`；存储错误返回 `STORAGE_FAILURE`。 |
| GET | `/api/materials/{material_id}/content` | 可选 `offset`、`limit` | `200`，返回分页正文和解析器元数据。 | 未解析返回 `MATERIAL_NOT_PARSED`；不存在返回 `404`。 |

上传规则：

- 支持 `.txt`、`.md`、`.pdf`、`.docx`；
- 默认最大文件大小为 20 MiB，可通过 `MAX_UPLOAD_BYTES` 调整；
- 文件写入 `UPLOAD_ROOT`，数据库保存稳定 storage key，不暴露任意本地路径；
- 正文、分段来源、内容哈希、解析器名称/版本和页数持久化在数据库；
- 旧版只有截断预览或缺失正文的资料必须重新上传原文件，不能伪装成完整解析结果。

正文分页参数：

- `offset`：默认 `0`，必须大于等于 `0`；
- `limit`：默认 `12000`，允许 `500–20000`；
- 响应包含 `total_length`、`has_more`、`page_count`、`parser_name` 和 `parser_version`。

## 摘要、卡片与资料问答

| 方法 | 路径 | 请求 | 成功响应 | 常见失败 |
| --- | --- | --- | --- | --- |
| GET | `/api/materials/{material_id}/summary` | 路径参数 | `200`，返回已保存的结构化摘要；尚未生成时摘要为空。 | 资料不存在返回 `404`。 |
| POST | `/api/materials/{material_id}/summary` | 路径参数 | `200`，生成、审计并保存结构化摘要。 | 未解析、未配置 AI、输入过大或 provider 失败。 |
| GET | `/api/materials/{material_id}/cards` | 路径参数 | `200`，返回已保存卡片；尚未生成时列表为空。 | 资料不存在返回 `404`。 |
| POST | `/api/materials/{material_id}/cards` | 路径参数 | `200`，生成并保存学习卡片。 | 未解析、未配置 AI 或 provider 失败。 |
| POST | `/api/materials/{material_id}/qa` | `{"question": "..."}` | `200`，返回回答、来源引用、grounded 状态和模型审计字段。 | 问题校验、资料解析或 AI 调用失败。 |

结构化摘要包含：

- `overview`；
- `key_concepts`；
- `important_points`；
- `common_mistakes`；
- `review_suggestions`；
- provider、model、prompt version 和生成/更新时间。

学习卡片包含问题、答案、知识提示、资料来源引用、顺序和模型来源。重复生成会替换该资料现有卡片，不会无界追加。

AI 运行边界：

- `LLM_MODE=provider` 是默认模式，需要 `LLM_API_KEY`、`LLM_BASE_URL` 和 `LLM_MODEL`；
- provider 未配置时返回 `AI_NOT_CONFIGURED`；
- 显式 `LLM_MODE=mock` 仅用于本地测试，响应保留 mock 来源；
- 限流返回 HTTP `429`；超时和 provider 暂时错误返回 `503`；其他可预期 AI 错误返回 `400`；
- 默认摘要输入上限为 200000 字符，超过时返回 `AI_INPUT_TOO_LARGE`。

## M3 课程知识模型接口

| 方法 | 路径 | 作用 | 成功响应 |
| --- | --- | --- | --- |
| GET | `/api/courses/{course_id}/knowledge-model` | 读取当前已发布课程知识模型。 | `200`，返回 `course_id`、活动节点和当前关系。 |
| POST | `/api/courses/{course_id}/knowledge-model/build` | 按顺序编排资料抽取、课程归一化和关系生成。 | `200`，返回资料/节点/两类关系数量及 `reused`。 |
| GET | `/api/courses/{course_id}/knowledge-nodes/{node_id}` | 读取节点、资料来源和相关关系。 | `200`，返回 `node`、`sources`、`related_edges`。 |
| POST | `/api/courses/{course_id}/materials/{material_id}/knowledge-extraction` | 对一份已解析资料执行 M3-B 候选抽取。 | `200`，返回抽取运行、候选及 `reused`。 |
| GET | `/api/courses/{course_id}/materials/{material_id}/knowledge-extraction` | 读取该资料当前成功抽取结果。 | `200`，返回运行和候选。 |
| POST | `/api/courses/{course_id}/knowledge-canonicalization` | 对当前候选执行 M3-C 课程级归一化。 | `200`，返回运行、规范节点、候选解析及 `reused`。 |
| GET | `/api/courses/{course_id}/knowledge-canonicalization` | 读取当前成功归一化结果。 | `200`，返回运行、节点和解析记录。 |
| POST | `/api/courses/{course_id}/knowledge-relationships` | 对活动规范节点执行 M3-D 关系生成。 | `200`，返回运行、`contains_edges`、`prerequisite_edges` 和 `reused`。 |
| GET | `/api/courses/{course_id}/knowledge-relationships` | 读取当前成功关系运行。 | `200`，返回两类关系及其证据。 |

三个阶段 POST 接口接受可选 JSON `{"regenerate": true}`。默认 `false` 时，相同的资料内容、候选/节点快照、模型、prompt 和配置版本会复用当前成功运行；显式重新生成会创建新的尝试，但失败不会覆盖已发布结果。课程级 `build` 无请求体，并始终使用各阶段既有的幂等策略。

处理链：

```text
MaterialContent + parser segments
  -> M3-B KnowledgeCandidate + KnowledgeCandidateSource
  -> M3-C KnowledgeNode + KnowledgeSource
  -> M3-D CONTAINS / PREREQUISITE + KnowledgeEdgeEvidence
  -> M3-E course-local visualization
```

核心约束：

- M3-B 只产生候选，不直接产生规范节点；候选引用必须存在于实际发送给 provider 的资料分段中；
- M3-C 先做确定性精确归一化，再对受限候选组进行保守语义判断，并保存每个候选的解析结果；
- M3-D 将 `source -> CONTAINS -> target` 定义为父概念到子概念，将 `source -> PREREQUISITE -> target` 定义为先修到依赖概念；
- `CONTAINS` 必须形成允许多根、每个子节点最多一个直接父节点的无环森林；`PREREQUISITE` 必须独立形成 DAG；
- 来源引用必须精确匹配同一课程 `MaterialContent.segments` 中真实存在的 `source_reference`；模型不能提供持久化摘录正文；
- 所有读写都受 owner、课程、资料和当前运行边界约束，不公开其他课程的存在。

阶段错误映射：

- 输入/前置状态未就绪：HTTP `409`，错误码以 `_NOT_READY` 结尾；
- provider 结构或关系验证失败：HTTP `422`，错误码以 `_INVALID_OUTPUT` 或 `_INVALID_REFERENCE` 结尾；
- provider/阶段执行失败：HTTP `502`，错误码以 `_FAILED` 结尾；
- 课程、资料或节点不存在/不属于当前 owner：HTTP `404`。

## 统一错误格式

可预期错误统一返回：

```json
{
  "error": {
    "code": "MATERIAL_NOT_PARSED",
    "message": "Material content is unavailable."
  },
  "detail": "Material content is unavailable."
}
```

- 请求校验失败：HTTP `422`，错误码 `VALIDATION_ERROR`；
- 未找到资源：HTTP `404`，错误码通常为 `NOT_FOUND` 或领域专用错误码；
- 未处理异常：HTTP `500`，错误码 `INTERNAL_ERROR`，详细异常只写入服务日志。

## 持久化与删除语义

- 删除课程会级联删除其资料、解析正文、AI 产物、知识节点、关系和来源，并清理关联上传文件；
- 删除资料会删除其解析正文、AI 产物和知识来源，但保留已经存在的知识节点；
- 删除知识节点会删除其入边、出边和来源；
- SQLite 运行时显式启用外键；迁移与测试同时验证数据库级约束；
- 旧 JSON 数据只通过显式、可重复运行的导入器迁移，应用启动不会隐式修改它。

更详细的设计与验证边界见：

- [M2 课程与资料架构](architecture/M2_COURSE_MATERIAL_ARCHITECTURE.md)
- [M2 实施报告](migration/M2_IMPLEMENTATION_REPORT.md)
- [M3-A 知识模型基础](architecture/M3A_KNOWLEDGE_MODEL_FOUNDATION.md)
- [M3-B AI 知识抽取](architecture/M3B_AI_KNOWLEDGE_EXTRACTION.md)
- [M3-C 知识归一化](architecture/M3C_KNOWLEDGE_CANONICALIZATION.md)
- [M3-D 知识关系](architecture/M3D_KNOWLEDGE_RELATIONSHIPS.md)
- [M3-E 知识结构前端](architecture/M3E_KNOWLEDGE_STRUCTURE_FRONTEND.md)
- [M3-A 实施报告](migration/M3A_IMPLEMENTATION_REPORT.md)
- [M3 最终验收](migration/M3_FINAL_ACCEPTANCE.md)
