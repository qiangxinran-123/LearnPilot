# CampusAI 演示数据说明

默认数据文件为 `backend/app/data/courses.json`。数据用于比赛展示，不包含个人隐私和大文件。每门示例课程均至少包含两条课程资料，并预置解析结果、mock 摘要与复习卡片，打开首页即可演示完整学习流程。

## 推荐用户故事

1. 选择一门课程。
2. 点击一份已有资料，展示“已解析多少字”、摘要和复习卡片。
3. 上传一份 TXT 或 MD 资料。
4. 点击“生成学习包”。
5. 搜索一个知识点，点击命中结果复习。

## 示例课程与关键词

| 课程 | 推荐资料 | 推荐搜索词 | 适合展示 |
| --- | --- | --- | --- |
| Computer Organization / 计算机组成原理 | Cache Memory Notes | `cache`、`pipeline` | 文本预览、摘要、卡片、搜索 |
| Machine Learning / 机器学习 | Gradient Descent Notes | `gradient`、`classification` | 生成学习包主流程 |
| Data Structures / 数据结构 | Linked List Review | `linked list`、`breadth-first` | 课程切换与知识点搜索 |

搜索框按当前课程过滤。建议在搜索前先选择对应课程，能清楚展示学习范围。

## 演示前准备

可以准备一个小型 `.txt` 或 `.md` 文件用于上传。推荐内容是两三句包含上表关键词的课程笔记，便于上传后立即生成学习包并检索。

若不希望演示修改默认 JSON，使用临时数据文件运行：

```bash
cp backend/app/data/courses.json /tmp/campusai-demo-courses.json
CAMPUSAI_COURSE_DATA_FILE=/tmp/campusai-demo-courses.json bash scripts/start_dev.sh
```
