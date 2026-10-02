PROMPT_VERSION = "material_qa_v1"


def messages(question: str, context: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你只可依据提供的资料片段回答。返回 JSON，字段为 answer、sufficient_evidence、references。"
                "references 必须只包含实际使用的资料片段标签，不得编造来源。"
                "若片段没有足够信息，answer 必须明确说明当前资料中没有足够信息回答，"
                "并将 sufficient_evidence 设为 false，references 设为空数组。不要使用常识补全。"
            ),
        },
        {"role": "user", "content": f"问题：{question}\n\n资料片段：\n{context}"},
    ]
