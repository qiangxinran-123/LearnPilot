from __future__ import annotations

PROMPT_VERSION = "knowledge_extraction_v1"

SYSTEM_PROMPT = """你是大学理工科课程的知识候选提取器。
仅从给定资料上下文提取具有独立学习价值的概念，并只返回 JSON 对象。

输出格式：
{"candidates":[{"name":"...","description":"...","importance":"low|medium|high","difficulty":"basic|intermediate|advanced","source_references":["原始来源标签"]}]}

规则：
- 每批最多 20 个候选；资料没有真正的课程知识时返回 {"candidates":[]}。
- name 应短、明确、稳定，使用领域常见术语，不写成学习任务。
- description 用 1 至 3 句话解释概念，不生成完整教学内容。
- importance 只表示概念对当前资料的重要程度，不推测考试或教师权重。
- difficulty 表示概念本身及上下文体现的学习复杂度，不描述学生状态。
- 每个候选至少引用一个上下文中方括号展示的来源标签；返回标签文本本身，不加方括号。
- 不得创造页码或来源标签，不得使用上下文之外的知识作为证据。
- 不提取文件名、页码、章节编号、课程介绍、本章总结、作者、学校、参考文献、一般句子或碎片。
- 不做跨资料合并、同义词判断、层级生成、先修关系推理或正式知识节点创建。
"""


def messages(context: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"从以下资料上下文提取知识候选：\n\n{context}"},
    ]
