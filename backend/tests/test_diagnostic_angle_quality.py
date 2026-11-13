from backend.app.services.diagnostic_question_quality import question_angle, same_question_angle


def test_twos_complement_range_paraphrases_are_not_new_questions():
    old = "对于 8 位补码表示，下列哪一组最小值和最大值是正确的？"
    reordered = "对于 w=8 的补码表示，其可表示的整数范围是（ ）。"
    assert question_angle(old) == "表示范围"
    assert same_question_angle(old, reordered)
    assert not same_question_angle(old, "对于 16 位补码表示，整数范围是什么？")
    assert not same_question_angle(old, "补码加法何时发生溢出？")


def test_unrecognized_topics_are_not_automatically_classified():
    assert question_angle("Cache 的映射方式是什么？") is None
    assert same_question_angle("Cache 的映射方式是什么？", "什么是 Cache 的映射方式？")


def test_reordered_long_question_is_rejected_even_without_a_topic_classifier():
    assert same_question_angle(
        "在直接映射缓存中主存块会映射到哪一个缓存行", "主存块在直接映射缓存中会映射到哪一个缓存行"
    )
