# core/rule/processor_rule.py

# ======================================================================
# 模块名称：规则处理器（清洗 + 去重 + 过滤 + 排序）
#
# 这是"解析"阶段的唯一入口：喂给它原始行，它交回标准规则和统计数字。
#
# 内部按顺序做四件事，所以"M 条规则怎么变成 N 条"可以在一个文件里
# 从头读到尾：
#
#     第一步 清洗：逐行把各种来源格式拆成统一的两栏（类型 / 值）
#                  —— 这一步入不了标准格式的，计入 invalid
#     第二步 去重：类型和值都相同才算重复；源内重复计入 dup_src，
#                  与手动规则重复计入 dup_vip
#     第三步 过滤：命中黑名单/关键词的计入 filtered
#     第四步 排序：按规则类型的优先级排列，手动追加的规则置顶
#
# 这里交出去的是"类型 + 值"两栏，不是拼好的字符串。这样做的原因：
#   各客户端的写法不同（类型名、策略名位置、参数、文件形态都不同），
#   如果在这里就拼成一行字，formatter 又得把字拆开，每加一个客户端就要重拆一遍。
#
# 职责边界：
#   负责：物理杂质剥离、语义标准化、类型识别、去重、过滤、排序
#   不负责：客户端语法适配（那是 formatter 的事，包括类型改名和参数）
#
# 核心原则：高保真。对非域名类规则不做跨语义映射，宁可丢弃也不猜。
# 上游数据被定义为"受约束的有序杂乱"，所以对主流格式精确处理，
# 对极端模糊格式直接丢弃。
# ======================================================================

import ipaddress
from collections import namedtuple

from core.constants import DEFAULT_PRIORITY, RULE_TYPE_PRIORITY

# ======================================================================
# 数据形态：一条规则在程序内部的统一表示
# ======================================================================

# 两栏：类型 / 值
#   类型：标准化后的名称，例如 DOMAIN-SUFFIX
#   值  ：规范化后的内容，例如 google.com
#
# 为什么只保留两栏：
#   原始数据的第三段及以后，在不同来源里可能是策略名、参数，或者两者混写，
#   位置和含义都不固定。而策略名我们用不上（每个规则集的策略由配置决定），
#   参数（例如 no-resolve）只跟"类型"有关，不跟"单条规则"有关，
#   由各客户端自己按类型决定加不加。
#   所以中间数据只留类型和值，最小、最稳，也不会因为策略名不同把同一条规则算成两条。
#
# 用 namedtuple 的两个理由：可以直接放进 set 做去重（可哈希），
# 且比每条文一个 dict 省内存——最大的合集有 29 万条。
Rule = namedtuple("Rule", "type value")


# ======================================================================
# 第一步：清洗（逐行标准化）
# ======================================================================

# --- 配置层：标准化定义 (Global Configuration) ---

# 内部标准类型白名单：只有属于或映射到此集合的规则才被视为有效
SUPPORTED_TYPES = {
    "DOMAIN",
    "DOMAIN-SUFFIX",
    "DOMAIN-KEYWORD",
    "DOMAIN-WILDCARD",
    "IP-CIDR",
    "IP-CIDR6",
    "IP-ASN",
    "GEOIP",
    "PROCESS-NAME",
    "USER-AGENT",
}

# 类型映射表：用于将不同生态的“同义词”统一为内部标准名称
# 仅做语义明确、业界共识度高的映射，严禁跨层级猜测
TYPE_MAPPING = {
    "HOST": "DOMAIN",
    "HOST-SUFFIX": "DOMAIN-SUFFIX",
    "HOST-WILDCARD": "DOMAIN-WILDCARD",
    "HOST-KEYWORD": "DOMAIN-KEYWORD",
    "IP6-CIDR": "IP-CIDR6",
    "ASN": "IP-ASN",
}

# 需要把“值”统一成小写的类型。
# 域名本身不区分大小写，IPv6 的十六进制也不区分，统一小写能让去重更准。
# 其余类型不能动：
#   USER-AGENT / PROCESS-NAME —— 大小写有含义
#   IP-ASN / GEOIP           —— AS1234、CN 这类大写是惯例，改小写可能不被客户端识别
LOWERCASE_TYPES = {
    "DOMAIN",
    "DOMAIN-SUFFIX",
    "DOMAIN-KEYWORD",
    "DOMAIN-WILDCARD",
    "IP-CIDR6",
}

# ======================================================================
# 公共入口：流水线主控 (Main Pipeline)
# ======================================================================


# 解析一行之后的状态。
# 区分"跳过"和"丢弃"是本模块的重要职责：
#   跳过 —— 这一行本来就不是分流规则（空行、注释、网页元素隐藏规则），
#           数量多少都正常，不该和"错误"混在一起统计，否则真正的问题会被淹没。
#   丢弃 —— 这一行是规则，但我们不要它（类型不支持、值为空、格式认不出）。
SKIP = "skip"
UNSUPPORTED = "unsupported"
EMPTY_VALUE = "empty"
UNRECOGNIZED = "unrecognized"

# 每种丢弃原因最多留几条原始样例，用来在调试时直接看到"丢的是什么"
DROP_SAMPLE_LIMIT = 3


def _parse_line(line: str) -> tuple[Rule | None, str]:
    """
    解析一行，返回 (规则, 状态)。

    状态为 SKIP 表示这行不是分流规则；其它非空状态表示被丢弃，并说明原因。
    """
    if not line:
        return None, SKIP

    # 1. 物理层预处理 (Physical Pre-processing)
    # 解决：注释、YAML包装符号、成对引号等物理形态干扰
    content = _strip_layer(line)
    if not content:
        return None, SKIP

    # 2. 分类路由层 (Routing Layer)
    # 解决：根据内容特征，将规则分发到对应的解析处理器。
    # 大小写统一放在各自的处理器里做：必须先知道类型，才知道这个值该不该转小写。
    if "," in content:
        return _handle_standard_format(content)

    return _handle_compatibility_format(content)


def clean_rule_line(line: str) -> Rule | None:
    """单行清洗入口：只要解析结果，不管原因。"""
    rule, _ = _parse_line(line)
    return rule


# ======================================================================
# 第一阶段：原子处理逻辑 (Atomic Logic)
# ======================================================================


def _strip_layer(line: str) -> str | None:
    """
    【物理剥离层】
    剥离规则外围的“壳”，不涉及对规则内容的理解。
    """
    # 1. 处理行内注释
    # 解决：去除 # 及其之后的内容，仅保留有效载荷
    if "#" in line:
        line = line.split("#", 1)[0]
    # 注意：这里把 // 一律当注释截断。分流规则本身不会含 //，
    # 但如果将来支持 URL 类类型（值里带 https://），网址会被切断，
    # 届时需要改成"只认行首的 //"，而不是任意位置的。
    if "//" in line:
        line = line.split("//", 1)[0]

    # 2. 处理 AdBlock 风格整行注释
    # 特征：以 ! 开头。直接判定为无效行
    if line.strip().startswith("!"):
        return None

    content = line.strip()

    # 3. 剔除 YAML 列表前缀
    # 特征：以 "- " 开头。解决从 YAML 格式源提取内容的问题
    if content.startswith("- "):
        content = content[2:].strip()

    # 4. 剥离成对引号
    # 解决：部分 YAML 数据或字符串化规则自带的包裹引号
    # 采用循环确保剥离所有对称的壳 (如 "'example.com'" -> example.com)
    while len(content) >= 2 and (
        (content[0] == '"' and content[-1] == '"')
        or (content[0] == "'" and content[-1] == "'")
    ):
        content = content[1:-1].strip()

    # 5. 剩下的空内容一律丢弃。
    # 注意：AdBlock 的网页元素隐藏规则（##、#@# 开头）在上一步按 # 截断时
    # 已经变成空字符串了，这里不需要再单独判断它们。
    if not content:
        return None

    return content


def _normalize_value(rule_type: str, value: str) -> str:
    """
    【标准化层】
    按类型把"值"整理成各家客户端都能直接用的形式。

    这一步是通用的：所有客户端共用同一份规范值，
    各自的差异（类型名、参数、文件形态）留给 formatter 处理。
    """
    # 域名不区分大小写；IPv6 的十六进制也不区分，统一小写能让去重更准
    if rule_type in LOWERCASE_TYPES:
        value = value.lower()
        # 移除域名末尾多余的点 (FQDN 规范化)
        # 解决：例如 "google.com." 与 "google.com" 语义等价，需统一。
        # 但 DOMAIN-KEYWORD 要排除：它做的是子串匹配，点属于关键词本身，
        # 例如 ".zooplus." 要求 zooplus 前后都有点，去掉尾点会放宽匹配范围。
        if rule_type != "DOMAIN-KEYWORD" and value.endswith("."):
            value = value.rstrip(".")
        return value

    # 国家代码统一大写，各家都写 CN、US
    if rule_type == "GEOIP":
        return value.upper()

    # ASN 统一成纯数字：AS 前缀可写可不写，不带前缀是更通用的写法
    if rule_type == "IP-ASN":
        value = value.upper()
        value = value.removeprefix("AS")
        return value

    return value


def _handle_standard_format(line: str) -> tuple[Rule | None, str]:
    """
    【处理器】解析带逗号的标准格式 (TYPE,VALUE,备注...)

    第三段及以后一律丢弃：那些内容在不同来源里可能是策略名、参数，
    或者两者混写，位置也不固定。策略名由配置决定，参数由客户端按类型决定，
    所以这里不需要保留。
    """
    # 调用方已经确认过这行含逗号，所以切出来至少两段
    parts = [p.strip() for p in line.split(",")]

    # 1. 提取并映射规则类型
    raw_type = parts[0].upper()
    value = parts[1]

    # 2. 兼容性转换
    # 解决：部分规则集将 DOMAIN 写作 FULL 的情况
    if raw_type == "FULL":
        raw_type = "DOMAIN"

    final_type = TYPE_MAPPING.get(raw_type, raw_type)

    # 3. 类型是否在我们的支持范围内
    # DOMAIN-SET / RULE-SET 涉及外部文件引用，无法作为单条规则处理；
    # SRC-PORT 这类端口规则目前也不支持。
    if final_type in {"DOMAIN-SET", "RULE-SET", "URL-REGEX"}:
        return None, UNSUPPORTED
    if final_type not in SUPPORTED_TYPES:
        return None, UNSUPPORTED

    # 4. 类型合法，但核心内容 (value) 为空
    if not value:
        return None, EMPTY_VALUE

    return Rule(final_type, _normalize_value(final_type, value)), "ok"


def _is_ipv4(text: str) -> bool:
    """判断一段文本是不是合法的 IPv4 地址（用标准库校验，顺带挡住 999.999.999.999）。"""
    try:
        ipaddress.IPv4Address(text)
    except ValueError:
        return False
    return True


def _handle_compatibility_format(line: str) -> tuple[Rule | None, str]:
    """
    【处理器】解析不带逗号的兼容格式 (推断解析)

    这一层推断出来的类型都自带明确语义，不需要额外信息。
    什么特征都匹配不上时，归为"认不出"，而不是"跳过"——
    能走到这里说明它不像注释、不像空行，只是我们解析不了。
    """
    # ------------------------------------------------------------------
    # 1. IP / CIDR 判定
    # 用标准库校验，而不是"看字符像不像"：
    #   - abc:def 这种不是地址的东西不会被当成 IPv6
    #   - "10.0.0.0/8 192.168.0.0/16" 这种两段拼在一起的行不会被当成一条规则
    # 单个地址也走这里（等同于 /32 或 /128），保持和源数据一致的写法。
    # ------------------------------------------------------------------
    try:
        network = ipaddress.ip_network(line, strict=False)
    except ValueError:
        pass
    else:
        rule_type = "IP-CIDR6" if network.version == 6 else "IP-CIDR"
        return Rule(rule_type, _normalize_value(rule_type, line)), "ok"

    # ------------------------------------------------------------------
    # 2. Hosts 规则判定
    # 特征：空格分成两段，前一段是 IPv4，后一段是域名
    # 必须排在纯 IP 判定之后：hosts 行整行不是合法 IP，会落到这里。
    # 第二段要是 IP 就不是 hosts（"10.0.0.1 10.0.0.2" 这种不是任何正常格式）。
    # ------------------------------------------------------------------
    parts = line.split()
    if (
        len(parts) == 2
        and _is_ipv4(parts[0])
        and "." in parts[1]
        and not _is_ipv4(parts[1])
    ):
        return Rule("DOMAIN", _normalize_value("DOMAIN", parts[1])), "ok"

    # ------------------------------------------------------------------
    # 3. AdBlock / 简写后缀判定
    # 特征：以 ||, ., +., *. 等前缀开头
    # ------------------------------------------------------------------
    if line.startswith("||"):
        # 剥离前缀并截断 AdBlock 的修饰符 (^, $)
        content = line[2:].split("^", 1)[0].split("$", 1)[0]
        if content:
            return Rule("DOMAIN-SUFFIX", _normalize_value("DOMAIN-SUFFIX", content)), "ok"

    if line.startswith((".", "+.", "*.")):
        content = line.lstrip("+*.")
        if content:
            return Rule("DOMAIN-SUFFIX", _normalize_value("DOMAIN-SUFFIX", content)), "ok"

    # ------------------------------------------------------------------
    # 4. 纯域名兜底处理
    # 特征：包含点，且不含路径符号(/)或空格
    # ------------------------------------------------------------------
    # 这里故意分两层：先看它像不像域名，再看是不是纯数字。
    # 合并成一个长条件会看不出这个层次，所以保留嵌套。
    if "." in line and "/" not in line and " " not in line:  # noqa: SIM102
        # 纯数字加点只可能是写错的 IP（999.999.999.999），不可能是域名
        if not line.replace(".", "").isdigit():
            return Rule(
                "DOMAIN-SUFFIX", _normalize_value("DOMAIN-SUFFIX", line)
            ), "ok"

    return None, UNRECOGNIZED


# ======================================================================
# 第二 ~ 四步：去重、过滤、排序（对整批规则操作）
# ======================================================================

def get_sort_key(rule: Rule):
    """
    排序辅助函数。
    规则越重要（优先级数字越小），排得越靠前。
    优先级相同时按 类型 -> 值 依次比较，保证每次运行顺序一致。
    """
    priority = RULE_TYPE_PRIORITY.get(rule.type, DEFAULT_PRIORITY)
    return (priority, rule.type, rule.value)


def process_rules(cfg: dict, raw_rules: list[str]) -> tuple[list[Rule], dict]:
    """
    [规则处理器]
    负责规则的 清洗 -> 去重 -> 过滤 -> 排序。

    返回: (清洗后的规则列表, 统计数据字典)
    """
    # 记录原始数据量
    count_raw_download = len(raw_rules)

    # 初始化各种计数器
    # 空行和注释行不算"错误"，单独记在 skip 里；
    # 只有"是规则但没能用上"的才计入 drop，并按原因分类留样例。
    count_skip = 0
    count_drop = 0
    # 字典顺序即日志里的展示顺序：类型不支持最常见，空值最少见
    drop_detail = {UNSUPPORTED: 0, UNRECOGNIZED: 0, EMPTY_VALUE: 0}
    drop_samples = {UNSUPPORTED: [], UNRECOGNIZED: [], EMPTY_VALUE: []}
    count_vip_dupe = 0
    count_source_dupe = 0
    count_filtered = 0

    # 1. 加载“忽略规则” (黑名单)
    ignored_set = set()
    for item in cfg.get("filters", {}).get("ignored_rules", []):
        rule = clean_rule_line(item)
        if rule:
            ignored_set.add(rule)

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
        rule = clean_rule_line(item)
        if rule:
            vip_set.add(rule)

    count_vip_added = len(vip_set)

    # 3. 处理下载的规则
    common_set = set()

    for line in raw_rules:
        rule, status = _parse_line(line)

        # 不是规则的输入（空行、注释）：直接跳过，不计入任何"丢弃"
        if status == SKIP:
            count_skip += 1
            continue

        # 是规则但我们不要：计入丢弃，并留几条样例备查
        if status != "ok":
            count_drop += 1
            drop_detail[status] = drop_detail.get(status, 0) + 1
            samples = drop_samples.setdefault(status, [])
            if len(samples) < DROP_SAMPLE_LIMIT:
                samples.append(line.strip())
            continue

        # 优先级检查：如果 VIP 里已经有了，跳过
        if rule in vip_set:
            count_vip_dupe += 1
            continue

        # 去重检查：如果普通池里已经有了，跳过
        if rule in common_set:
            count_source_dupe += 1
            continue

        # 过滤检查
        is_filtered = False
        if rule in ignored_set:
            is_filtered = True
        else:
            # 关键词匹配的对象是"类型,值"，与改造前的整行一致
            haystack = f"{rule.type},{rule.value}".lower()

            hit_exclude = any(kw in haystack for kw in exclude_keywords)
            hit_include = any(kw in haystack for kw in include_keywords)

            # 两种情况要过滤：
            #   命中排除词        —— 黑名单
            #   配了白名单却没命中 —— 不在保留范围内
            if hit_exclude or (include_keywords and not hit_include):
                is_filtered = True

        if is_filtered:
            count_filtered += 1
            continue

        # 通过所有检查，加入集合
        common_set.add(rule)

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
        "skip": count_skip,
        "drop": count_drop,
        "drop_detail": drop_detail,
        "drop_samples": drop_samples,
        "vip": count_vip_added,
        "dup_vip": count_vip_dupe,
        "dup_src": count_source_dupe,
        "filtered": count_filtered,
        "total": total_count,
    }

    return final_result, stats
