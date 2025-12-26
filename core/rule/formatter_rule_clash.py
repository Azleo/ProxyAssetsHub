# core/rule/formatter_rule_clash.py

DIR_NAME = "Clash"
COMMENT_SYMBOL = "#"
FILE_EXTENSION = "yaml"

# 定义三个桶的类型归属
TYPE_BUCKETS = {
    "DOMAIN": ["DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-WILDCARD"],
    "IP": ["IP-CIDR", "IP-CIDR6", "GEOIP", "SRC-IP-CIDR"],
    # 其他未列出的类型（如 PROCESS-NAME）会自动落入 Classical
}

# 映射到 Clash 的具体关键词
CLASH_MAPPING = {
    "DOMAIN": "DOMAIN",
    "DOMAIN-SUFFIX": "DOMAIN-SUFFIX",
    "DOMAIN-KEYWORD": "DOMAIN-KEYWORD",
    "DOMAIN-WILDCARD": "DOMAIN-SUFFIX", # 兼容处理
    "IP-CIDR": "IP-CIDR",
    "IP-CIDR6": "IP-CIDR6",
    "GEOIP": "GEOIP",
    "SRC-IP-CIDR": "SRC-IP-CIDR",
    "PROCESS-NAME": "PROCESS-NAME",
    "DST-PORT": "DST-PORT",
    "SRC-PORT": "SRC-PORT"
}

def format_rules(
    rules: list[str], policy_tag: str = "Default", header_lines: list[str] = None
) -> dict:
    """
    返回一个字典，键为分类后缀（如 'Domain'），值为格式化后的规则列表。
    """
    
    # 初始化三个桶的数据结构
    # 每个桶都先预装好头部信息
    buckets = {
        "Domain": [],
        "IP": [],
        "Classical": []
    }
    
    # 预生成头部 (Payload声明 + 自定义注释)
    common_headers = ["payload:"]
    if header_lines:
        for header in header_lines:
            common_headers.append(f"  {COMMENT_SYMBOL} {header}")
            
    # 将头部填入每个桶
    for key in buckets:
        buckets[key].extend(common_headers)

    # 标记桶是否真的有数据（除去头部）
    has_data = {
        "Domain": False,
        "IP": False,
        "Classical": False
    }

    for line in rules:
        if "," not in line:
            continue

        parts = line.split(",", 1)
        std_type = parts[0].strip().upper()
        value = parts[1].strip()

        # 获取 Clash 类型
        if std_type not in CLASH_MAPPING:
            continue
        clash_type = CLASH_MAPPING[std_type]
        
        final_line = f"  - {clash_type},{value}"

        # 分拣逻辑
        if std_type in TYPE_BUCKETS["DOMAIN"]:
            buckets["Domain"].append(final_line)
            has_data["Domain"] = True
        elif std_type in TYPE_BUCKETS["IP"]:
            buckets["IP"].append(final_line)
            has_data["IP"] = True
        else:
            # 既不是域名也不是IP，丢进 Classical 垃圾桶
            buckets["Classical"].append(final_line)
            has_data["Classical"] = True

    # 清理空桶
    # 如果某个桶只有头部（没有实际规则），就把它删掉，防止生成空文件
    final_output = {}
    for key, content_list in buckets.items():
        if has_data[key]:
            final_output[key] = content_list

    return final_output