# core/rewrite/processor_rewrite.py

from core.rewrite.cleaner_rewrite import clean_rewrite_line


def process_rewrites(cfg: dict, raw_rules: list[str]) -> tuple[list[str], dict]:
    """
    [重写处理器]
    逻辑比规则处理器简单，只做基本的清洗。

    返回: (清洗后的规则列表, 统计数据字典)
    """
    final_result = []
    count_raw = len(raw_rules)
    count_valid = 0

    for line in raw_rules:
        # 调用简单的清洗函数
        clean_line = clean_rewrite_line(line)
        if clean_line:
            final_result.append(clean_line)
            count_valid += 1

    # 生成统计报告
    stats = {"source": count_raw, "valid": count_valid}

    return final_result, stats
