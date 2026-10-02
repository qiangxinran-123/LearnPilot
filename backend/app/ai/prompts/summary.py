PROMPT_VERSION = "summary_v1"


def messages(source: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是大学理工科课程资料整理助手。仅基于给定资料生成 JSON，字段必须是 "
                "overview、key_concepts、important_points、common_mistakes、review_suggestions。"
                "不要补充资料中不存在的事实。"
            ),
        },
        {"role": "user", "content": source},
    ]
