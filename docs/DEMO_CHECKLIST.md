# LearnPilot 演示前检查清单

建议在比赛演示前至少完整走一遍。默认演示数据已经准备好，重点是确认服务、页面和关键交互都能稳定运行。

## 启动与页面

- [ ] 当前目录是 LearnPilot 项目根目录。
- [ ] .venv/bin/python 存在，依赖已安装。
- [ ] 执行 bash scripts/start_dev.sh 后没有启动错误。
- [ ] 打开 http://127.0.0.1:8000，能看到 LearnPilot 首页。
- [ ] 打开 http://127.0.0.1:8000/docs，Swagger 文档可访问。
- [ ] 页面课程数量显示为 3 门。

## 核心演示流程

- [ ] 课程列表中可以看到 Computer Organization、Machine Learning、Data Structures。
- [ ] 每门课程切换后都有至少 2 条资料。
- [ ] 点击资料后，右侧详情能看到标题、类型、文件名、文本状态和文本长度。
- [ ] 详情中能看到 text preview、mock AI 摘要和学习卡片。
- [ ] 搜索 cache，能找到 Cache Memory Notes。
- [ ] 搜索 gradient，能找到 Gradient Descent Notes。
- [ ] 搜索 linked list，能找到 Linked List Review。
- [ ] 点击搜索结果能定位到资料详情。
- [ ] 点击“返回课程资料”能恢复完整资料列表。
- [ ] 点击“生成摘要”，按钮显示处理中状态，完成后提示成功。
- [ ] 点击“生成学习卡片”，按钮显示处理中状态，完成后显示卡片数量。
- [ ] 如需演示上传，准备一个小型 .txt 或 .md 文件，并在选中课程后上传。

## 仓库与说明材料

- [ ] GitHub 页面可以打开，最新提交已经 push 到 origin/main。
- [ ] README 中的启动命令、首页地址和测试命令与当前环境一致。
- [ ] README 链接到 docs/DEMO_DATA.md 和 docs/DEMO_CHECKLIST.md。
- [ ] 比赛讲稿使用 docs/DEMO_SCRIPT.md，优先演示前端页面。
- [ ] 现场明确说明当前摘要和学习卡片是 mock AI，不是已接入真实大模型。

## 现场备用方案

如果前端页面临时出现问题，可以按以下顺序处理：

1. 刷新首页，确认服务仍运行在 8000 端口。
2. 打开 /health，确认返回 status 为 ok。
3. 打开 /docs，使用 GET /api/courses 和 GET /api/courses/{course_id}/materials 展示后端数据。
4. 通过 /docs 演示摘要、搜索和卡片接口，说明前端只是同一套 API 的演示入口。
5. 如果默认数据被现场操作修改，停止服务后执行 git restore backend/app/data/courses.json，再重新启动。
6. 更稳妥的现场方式是先复制 JSON 到临时路径，并设置 CAMPUSAI_COURSE_DATA_FILE 后再启动。

## 演示结束后

- [ ] 停止本地服务。
- [ ] 检查 git status，确认没有误提交上传文件或临时数据。
- [ ] 如使用了默认 JSON 并产生了演示修改，恢复默认演示数据。
