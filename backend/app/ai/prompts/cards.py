PROMPT_VERSION = "cards_v3"


def messages(source: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "仅基于给定课程资料生成 JSON：{cards:[{question,answer,knowledge_hint,source_reference}]}。"
                "生成 5 到 10 张简洁学习卡片，不得引入资料之外的知识。"
                "source_reference 只能逐字复制资料方括号内的真实标签文字，返回值本身不要包含方括号；"
                "无法确定来源时必须返回 null，绝不创建新的来源标签。"
            ),
        },
        {"role": "user", "content": source},
    ]
