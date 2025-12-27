# core/rule/formatter_rule_clash.py

# ----------------------------------------------------------------------
# 模块元数据常量
# ----------------------------------------------------------------------
DIR_NAME = "Clash"
COMMENT_SYMBOL = "#"
FILE_EXTENSION = "yaml"

# ----------------------------------------------------------------------
# 规则分类桶 (Buckets) 定义
# ----------------------------------------------------------------------
# 这里定义了哪些“标准规则类型”应该被归入“Domain”文件或“IP”文件。
# 注意：任何未在此字典中明确列出的类型，都会自动被归类到 "Classical" 桶中。
TYPE_BUCKETS = {
    "DOMAIN": ["DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-WILDCARD"],
    "IP": ["IP-CIDR", "IP-CIDR6", "GEOIP", "SRC-IP-CIDR", "IP-ASN"],
}

# ----------------------------------------------------------------------
# 类型映射表
# ----------------------------------------------------------------------
# 将项目的“标准类型”映射为 Clash 配置文件支持的“关键词”。
CLASH_MAPPING = {
    "DOMAIN": "DOMAIN",
    "DOMAIN-SUFFIX": "DOMAIN-SUFFIX",
    "DOMAIN-KEYWORD": "DOMAIN-KEYWORD",
    "DOMAIN-WILDCARD": "DOMAIN-SUFFIX",  # 兼容处理
    "IP-CIDR": "IP-CIDR",
    "IP-CIDR6": "IP-CIDR6",
    "GEOIP": "GEOIP",
    "SRC-IP-CIDR": "SRC-IP-CIDR",
    "PROCESS-NAME": "PROCESS-NAME",
    "DST-PORT": "DST-PORT",
    "SRC-PORT": "SRC-PORT",
    "IP-ASN": "IP-ASN",
    "PROCESS-NAME": "PROCESS-NAME",
}


def format_rules(
    rules: list[str], policy_tag: str = "Default", header_lines: list[str] = None
) -> dict:
    """
    将标准规则列表格式化为 Clash 的 YAML 格式。
    
    返回:
        dict: 包含三个分类的字典。
              Key: "Domain", "IP", "Classical"
              Value: 规则内容列表
    """

    # 初始化三个桶的数据结构
    # 每个桶都先预装好头部信息
    # 这里的 Key (Domain, IP, Classical) 对应生成文件名的后缀
    buckets = {"Domain": [], "IP": [], "Classical": []}

    # 1. 准备头部信息
    # Clash 规则集文件通常需要以 'payload:' 开头
    common_headers = ["payload:"]
    # 如果用户配置了自定义头部（如 license 信息），追加到这里
    if header_lines:
        for header in header_lines:
            common_headers.append(f"  {COMMENT_SYMBOL} {header}")

    # 将通用的头部信息预先填入每个桶中
    for key in buckets:
        buckets[key].extend(common_headers)

    # 标记桶是否真的有数据（除去头部）
    has_data = {"Domain": False, "IP": False, "Classical": False}

    # 2. 遍历并处理每条规则
    for line in rules:
        # 简单校验：必须包含逗号
        if "," not in line:
            continue

        parts = line.split(",", 1)
        std_type = parts[0].strip().upper()
        value = parts[1].strip()

        # 检查是否支持该类型
        if std_type not in CLASH_MAPPING:
            continue
        # 获取 Clash 对应的规则类型关键词
        clash_type = CLASH_MAPPING[std_type]

        # 特殊处理：为 IP-CIDR 类规则添加 ",no-resolve" 参数
        # 这可以防止 Clash 为了匹配 IP 规则而发起不必要的 DNS 解析
        suffix_param = ""
        if clash_type in ["IP-CIDR", "IP-CIDR6"]:
            suffix_param = ",no-resolve"
        # [注意] IP-ASN 通常不需要强制加 no-resolve，视具体需求而定，这里保持原样不加。

        # 拼装最终的一行规则 (Clash YAML 列表项格式)
        # 例如: "  - DOMAIN-SUFFIX,google.com"
        final_line = f"  - {clash_type},{value}{suffix_param}"

        # 3. 分桶逻辑 (Routing)
        if std_type in TYPE_BUCKETS["DOMAIN"]:
            buckets["Domain"].append(final_line)
            has_data["Domain"] = True
        elif std_type in TYPE_BUCKETS["IP"]:
            # 包含了 IP-CIDR, GEOIP, IP-ASN 等
            buckets["IP"].append(final_line)
            has_data["IP"] = True
        else:
            # 所有其他类型（如 PROCESS-NAME）都放入 Classical 桶
            buckets["Classical"].append(final_line)
            has_data["Classical"] = True

    # 4. 准备返回结果
    final_output = {}

    # 强制输出列表
    # 定义必须生成文件的分类。即使没有数据，也会生成仅含头部的占位文件。
    # 这样 Manager/Writer 就会收到三个任务，生成 _Domain.yaml, _IP.yaml, _Classical.yaml
    MANDATORY_TYPES = ["Domain", "IP", "Classical"]

    for key, content_list in buckets.items():
        # 只要 Key 在强制列表中，或者确实有数据，就添加到输出结果
        if key in MANDATORY_TYPES or has_data[key]:
            final_output[key] = content_list

    return final_output
