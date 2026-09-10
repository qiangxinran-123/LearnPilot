# CampusAI

CampusAI 是一个帮助大学生把课程资料快速整理成摘要、复习卡片和可搜索知识库的 AI 学习助手。

CampusAI is a FastAPI-based study assistant that turns course materials into searchable summaries and review cards.

> 当前版本使用本地规则实现的 mock AI 摘要和 mock 学习卡片生成，不调用真实外部大模型 API，也不依赖 API Key。

## 产品主流程

CampusAI V0.3 将前端体验收束为一条明确的学习闭环：

```text
选择课程 → 上传资料 → 生成学习包 → 搜索复习
```

学生不需要理解文本提取、摘要接口或卡片接口等技术概念。上传 TXT 或 MD 资料后，页面会显示“已解析多少字”；选中资料后点击“生成学习包”，系统会依次生成摘要和复习卡片；最后可在当前课程资料中搜索知识点。

## 项目状态

- 当前版本：`V0.3 产品主流程重构阶段`
- 后端：FastAPI、Pydantic、本地 JSON 持久化、unittest 集成测试
- 前端：原生 HTML、CSS、JavaScript，由 FastAPI 直接托管
- 当前 AI：本地 mock AI 原型，不是已经接入真实 LLM 的产品
- 不使用 Vue、React、构建工具或外部 CDN

推荐 GitHub 仓库描述：

```text
CampusAI：面向大学生的 AI 学习资料管理与复习辅助平台 | FastAPI-based AI study assistant for students
```

## 核心能力

- 选择课程并查看课程资料
- 上传 `.txt`、`.md` 等课程资料，文件和资料记录写回本地 JSON
- 自动提取 TXT、MD 的正文，展示文本预览与解析字数
- 生成并持久化 mock AI 摘要
- 生成并持久化 mock 学习复习卡片
- 以标题、文件名、资料说明、正文预览和 AI 摘要搜索知识点
- 服务重启后仍可读取资料、摘要和卡片结果

## API 概览

| 功能 | API | 说明 |
| --- | --- | --- |
| 课程列表 | `GET /api/courses` | 获取课程 |
| 课程资料 | `GET /api/courses/{course_id}/materials` | 获取一门课的资料 |
| 文件上传 | `POST /api/courses/{course_id}/materials/upload` | 上传并登记课程资料 |
| mock 摘要 | `POST /api/materials/{material_id}/summary` | 生成并保存本地摘要 |
| 资料搜索 | `GET /api/materials/search?q={keyword}&course_id={optional}` | 搜索资料，不修改 JSON |
| 学习卡片 | `POST /api/materials/{material_id}/cards` | 生成并保存 mock 复习卡片 |

完整说明见 [API 总览](docs/API_OVERVIEW.md)。

## 项目结构

```text
campus-ai/
├── backend/
│   ├── main.py
│   ├── app/
│   │   ├── api/                 # 课程、资料和处理接口
│   │   ├── schemas/             # Pydantic 模型
│   │   ├── services/            # 持久化、提取、摘要、卡片服务
│   │   └── data/courses.json    # 默认演示数据
│   └── tests/test_courses_api.py
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── docs/
├── scripts/start_dev.sh
└── requirements.txt
```

## 快速启动

在项目根目录执行：

```bash
bash scripts/start_dev.sh
```

启动后打开：

- 前端学习工作台：[http://127.0.0.1:8000](http://127.0.0.1:8000)
- FastAPI API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

也可以手动启动：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

## 前端演示

1. 打开首页，从左侧选择一门课程。
2. 查看当前课程下的学习资料；点击资料卡片进入学习包详情。
3. 选择 TXT 或 MD 文件，上传到当前课程。
4. 点击“生成学习包”，等待摘要和复习卡片生成。
5. 在“搜索知识点”中输入 `cache`、`gradient` 或 `linked list`，点击结果查看资料详情。

页面没有额外前端服务和构建步骤。文本提取、摘要和卡片均使用既有后端 API；`/docs` 保留用于查看接口。

## 运行测试

```bash
wsl -d Ubuntu --cd /home/qxrrr/projects/campus-ai \
.venv/bin/python -m unittest backend.tests.test_courses_api
```

测试覆盖课程与资料、JSON 持久化、文件上传、文本提取、mock 摘要、搜索和学习卡片接口。

## 当前 mock AI 能力与限制

- mock 摘要根据已提取文本生成简短摘要。
- mock 卡片优先使用 AI 摘要，其次使用正文预览和资料说明。
- 重复生成会更新原资料，不会无限新增重复卡片。
- 尚未接入真实 LLM、RAG、向量数据库、数据库或用户登录。
- PDF、PPT、Word 可上传，但当前只自动提取 TXT、MD 的正文。

## 演示与文档

- [比赛 Demo 脚本](docs/DEMO_SCRIPT.md)
- [演示数据说明](docs/DEMO_DATA.md)
- [演示前检查清单](docs/DEMO_CHECKLIST.md)
- [API 总览](docs/API_OVERVIEW.md)
- [分阶段开发日志](docs/DEVELOPMENT_LOG.md)
- [V0.1 最终验收清单](docs/V0.1_ACCEPTANCE.md)

## 后续规划

- 使用真实 LLM 替换 mock AI 服务
- 接入 Embedding、RAG 和向量数据库
- 支持 PDF、PowerPoint、Word 正文提取
- 增加数据库、用户资料归属和协作能力
- 继续完善学生端复习体验
