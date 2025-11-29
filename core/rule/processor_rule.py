# core/rule/processor_rule.py

from core.rule.cleaner_rule import clean_rule_line
from core.constants import RULE_TYPE_PRIORITY, DEFAULT_PRIORITY


def get_sort_key(line):
    """
    排序辅助函数。
    规则越重要（优先级数字越小），排得越靠前。
    """
    if "," in line:
        rule_type = line.split(",")[0].strip().upper()
        priority = RULE_TYPE_PRIORITY.get(rule_type, DEFAULT_PRIORITY)
    else:
        priority = DEFAULT_PRIORITY
    return (priority, line)


def process_rules(cfg: dict, raw_rules: list[str]) -> tuple[list[str], dict]:
    """
    [规则处理器]
    负责规则的 清洗 -> 去重 -> 过滤 -> 排序。

    返回: (清洗后的规则列表, 统计数据字典)
    """
    # 记录原始数据量
    count_raw_download = len(raw_rules)

    # 初始化各种计数器
    count_invalid = 0
    count_vip_dupe = 0
    count_source_dupe = 0
    count_filtered = 0

    # 1. 加载“忽略规则” (黑名单)
    ignored_set = set()
    for item in cfg.get("filters", {}).get("ignored_rules", []):
        clean_item = clean_rule_line(item)
        if clean_item:
            ignored_set.add(clean_item)

    # 加载关键词过滤配置
    exclude_keywords = [
        k.lower() for k in cfg.get("filters", {}).get("exclude_keywords", [])
    ]
    include_keywords = [
        k.lower() for k in cfg.get("filters", {}).get("include_keywords", [])
    ]

    # 2. 加载“VIP 规则” (最高优先级，手动添加)
    vip_set = set()
    raw_extra = cfg.get("filters", {}).get("extra_rules", [])

    for item in raw_extra:
        clean_item = clean_rule_line(item)
        if clean_item:
            vip_set.add(clean_item)

    count_vip_added = len(vip_set)

    # 3. 处理下载的规则
    common_set = set()

    for line in raw_rules:
        clean_line = clean_rule_line(line)
        if not clean_line:
            count_invalid += 1
            continue

        # 优先级检查：如果 VIP 里已经有了，跳过
        if clean_line in vip_set:
            count_vip_dupe += 1
            continue

        # 去重检查：如果普通池里已经有了，跳过
        if clean_line in common_set:
            count_source_dupe += 1
            continue

        # 过滤检查
        is_filtered = False
        if clean_line in ignored_set:
            is_filtered = True
        else:
            line_lower = clean_line.lower()
            # 排除关键词
            if any(kw in line_lower for kw in exclude_keywords):
                is_filtered = True
            # 包含关键词
            elif include_keywords:
                if not any(kw in line_lower for kw in include_keywords):
                    is_filtered = True

        if is_filtered:
            count_filtered += 1
            continue

        # 通过所有检查，加入集合
        common_set.add(clean_line)

    # 4. 排序合并
    vip_list = list(vip_set)
    common_list = list(common_set)

    vip_list.sort(key=get_sort_key)
    common_list.sort(key=get_sort_key)

    final_result = vip_list + common_list
    total_count = len(final_result)

    # 5. 生成统计报告 (这里的 key 对应 Logger.KEYS 里的翻译)
    stats = {
        "source": count_raw_download,
        "vip": count_vip_added,
        "invalid": count_invalid,
        "dup_vip": count_vip_dupe,
        "dup_src": count_source_dupe,
        "filtered": count_filtered,
        "total": total_count,
    }

    return final_result, stats
