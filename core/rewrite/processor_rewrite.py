# core/rewrite/processor_rewrite.py

# ======================================================================
# 模块名称：重写处理器（清洗 + 去重 + 过滤 + 排序）
#
# 和 rule 阶段的 processor 保持同一个结构：对原始数据的所有处理都在
# 这个文件里完成，喂给它原始行，它交回可以写进产物的行和统计数字。
# 调用方（manager）不需要知道内部做了几步。
#
# 当前状态：**占位实现**。只去掉空行，其余原样返回，不做任何语义处理。
#
# 真正实现时要做的事（按 QX / Loon 的重写语法）：
#     1. 识别每条规则属于哪种类型（URL 重写 / Header 重写 / 脚本 / MITM）
#     2. 按类型校验语法，写错的行计入 invalid
#     3. 去重、按配置过滤、必要时排序
# ======================================================================


def process_rewrites(cfg: dict, raw_rules: list[str]) -> tuple[list[str], dict]:
    """
    [重写处理器]

    返回: (处理后的规则行, 统计数据字典)

    统计字段和 rule 阶段保持同一套口径，日志模块才能用同一套模板渲染：
        source / skip / drop / drop_detail / filtered / dup_src / dup_vip / vip / total
    现在没有丢弃和过滤，这几项恒为 0。
    """
    result = []
    count_skip = 0

    for line in raw_rules:
        # 唯一的处理：去掉首尾空白，空行跳过
        text = line.strip()
        if not text:
            count_skip += 1
            continue
        result.append(text)

    stats = {
        "source": len(raw_rules),
        "skip": count_skip,
        "drop": 0,
        "drop_detail": {},
        "drop_samples": {},
        "filtered": 0,
        "dup_src": 0,
        "dup_vip": 0,
        "vip": 0,
        "total": len(result),
    }

    return result, stats
