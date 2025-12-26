# core/rule/formatter_rule_clash.py

# ----------------------------------------------------------------------
# 模块元数据常量
# ----------------------------------------------------------------------

DIR_NAME = "Clash"       # 输出目录名称
COMMENT_SYMBOL = "#"     # YAML 注释符号
FILE_EXTENSION = "yaml"  # Clash 规则集文件扩展名

# ----------------------------------------------------------------------
# 规则类型映射表
# ----------------------------------------------------------------------
CLASH_MAPPING = {
    # 域名类
    "DOMAIN": "DOMAIN",
    "DOMAIN-SUFFIX": "DOMAIN-SUFFIX",
    "DOMAIN-KEYWORD": "DOMAIN-KEYWORD",
    # 兼容性处理：通配符在 Meta 内核可用，这里映射为后缀或保留
    "DOMAIN-WILDCARD": "DOMAIN-SUFFIX", 

    # IP 类
    "IP-CIDR": "IP-CIDR",
    "IP-CIDR6": "IP-CIDR6",
    "GEOIP": "GEOIP",
    
    # 进程名 (Windows/Linux/Mac)
    "PROCESS-NAME": "PROCESS-NAME",
    "SRC-IP-CIDR": "SRC-IP-CIDR",
}

def format_rules(
    rules: list[str], policy_tag: str = "Default", header_lines: list[str] = None
) -> list[str]:
    """
    将标准格式的规则列表转换为 Clash Rule Provider (Payload) 格式。
    """
    formatted = []
    
    # 1. 写入 YAML 必需的头部 payload 声明
    formatted.append("payload:")
    
    # 2. 处理用户自定义头部 (作为注释插入，注意缩进)
    if header_lines:
        for header in header_lines:
            formatted.append(f"  {COMMENT_SYMBOL} {header}")

    # 3. 处理规则内容
    for line in rules:
        if "," not in line:
            continue

        parts = line.split(",", 1)
        std_type = parts[0].strip().upper()
        value = parts[1].strip()

        # 过滤 Clash 不支持的规则类型 (如 USER-AGENT)
        if std_type not in CLASH_MAPPING:
            continue

        clash_type = CLASH_MAPPING[std_type]
        
        # Clash Payload 格式: 缩进 + 短横线 + 空格 + 类型 + 逗号 + 值
        # 示例: "  - DOMAIN-SUFFIX,google.com"
        final_line = f"  - {clash_type},{value}"
        
        formatted.append(final_line)

    return formatted