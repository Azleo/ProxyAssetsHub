# core/rule/formatter_rule_clash.py

# ----------------------------------------------------------------------
# 模块元数据常量
# 定义输出文件相关的基本信息，供 Writer 模块使用。
# ----------------------------------------------------------------------

# 必需常量：输出规则存放的子目录名称
DIR_NAME = "Clash"
# 必需常量：文件中使用的注释符号
COMMENT_SYMBOL = "#"
# 必需常量：输出文件的默认扩展名
FILE_EXTENSION = "yaml"

# ----------------------------------------------------------------------
# 文件分桶
# 将规则按类型分到三个文件里。这是 Clash 的组织方式，不属于规则转换：
#   Domain    域名类
#   IP        IP 类
#   Classical 其余类型
# ----------------------------------------------------------------------
TYPE_BUCKETS = {
    "DOMAIN": ["DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-WILDCARD"],
    "IP": ["IP-CIDR", "IP-CIDR6", "GEOIP", "IP-ASN"],
}

# 三个文件的固定顺序与后缀
BUCKET_NAMES = ("Domain", "IP", "Classical")

# Clash 不支持的规则类型：遇到就跳过，不写进产物。
# 单独列成常量而不是散在循环里，将来发现新的不支持类型，加一行就行。
UNSUPPORTED_TYPES = {"USER-AGENT"}


def _bucket_of(rule_type: str) -> str:
    """按规则类型决定它进哪个文件。认不出的类型一律放进 Classical。"""
    for name in ("DOMAIN", "IP"):
        if rule_type in TYPE_BUCKETS[name]:
            return "Domain" if name == "DOMAIN" else "IP"
    return "Classical"


def format_rules(
    rules: list[tuple[str, str]],
    collection: str,
    policy: str = "Default",
    header_lines: list[str] | None = None,
) -> list[dict]:
    """
    将标准格式的规则列表转换为 Clash 的 YAML 列表项。

    Clash 的规则写法是 YAML 列表项：  - 规则类型,规则值
    并按类型分成三个文件（Domain / IP / Classical），即使某个文件没内容也照常输出，
    避免订阅地址失效。

    注意：这里**不做任何类型转换，也不追加任何参数**（例如 no-resolve），
    内部的标准类型名和值直接写进产物。真正做适配时，在这两个地方补：
      - 类型名不一致  -> 加一张映射表
      - 需要追加参数  -> 在拼行时补
    其它模块都不用动。

    参数:
        rules (List[tuple]): 经过处理和排序的规则，每项是 (类型, 值) 两栏。
        collection (str): 规则集标识，用于拼文件名。
        policy (str): 策略名。Clash 的规则行里不写策略，这里保留参数只为和其它翻译器接口一致。
        header_lines (List[str] | None): 用户在配置中定义的额外头部注释行。

    返回:
        文件清单（列表），固定三项，每项描述一个要写出的文件：
        {"dir": 目录, "filename": 文件名, "content": 内容行, "header": 是否写标准头部, "comment": 注释符}
    """
    # Clash 的规则集文件是 YAML 列表，必须以 payload: 开头，三个文件都要有
    buckets = {name: ["payload:"] for name in BUCKET_NAMES}
    rule_counts = {name: 0 for name in BUCKET_NAMES}

    # 1. 处理用户自定义头部：缩进两格，三个文件都要带上
    if header_lines:
        for header in header_lines:
            header_line = f"  {COMMENT_SYMBOL} {header}"
            for name in BUCKET_NAMES:
                buckets[name].append(header_line)

    # 2. 处理规则内容：按类型分桶，类型和值原样拼成 YAML 列表项
    for rule in rules:
        # 这个客户端不认的类型直接跳过，别把用不了的东西写进产物
        if rule.type in UNSUPPORTED_TYPES:
            continue

        name = _bucket_of(rule.type)
        buckets[name].append(f"  - {rule.type},{rule.value}")
        rule_counts[name] += 1

    # 3. 返回文件清单
    return [
        {
            "dir": DIR_NAME,
            "filename": f"{collection}_{name}.{FILE_EXTENSION}",
            "content": buckets[name],
            "rule_count": rule_counts[name],
            "header": True,
            "comment": COMMENT_SYMBOL,
        }
        for name in BUCKET_NAMES
    ]
