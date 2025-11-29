# core/rule/cleaner_rule.py

# ----------------------------------------------------------------------
# 类型映射表 (Type Mapping)
# 将某些软件特有的规则类型名称（Key）统一转换为业界通用的标准名称（Value）。
# ----------------------------------------------------------------------
TYPE_MAPPING = {
    # 域名类规则的统一：
    # 将 HOST 开头的规则类型统一映射为 DOMAIN 开头，以实现标准化。
    "HOST": "DOMAIN",
    "HOST-SUFFIX": "DOMAIN-SUFFIX",
    "HOST-WILDCARD": "DOMAIN-WILDCARD",
    "HOST-KEYWORD": "DOMAIN-KEYWORD",
    # IP 类规则的统一：
    # 将 IP6-CIDR 统一映射为更常见的 IP-CIDR6 格式。
    "IP6-CIDR": "IP-CIDR6",
}


def clean_rule_line(line: str) -> str | None:
    """
    单行规则清洗与标准化工 (Cleaner)。

    该函数将一行原始规则文本转换为统一、标准的格式 "TYPE,value"，同时过滤掉无效行。

    处理逻辑：
    1. 去除行内注释（# 后面的内容）。
    2. 基础清洗（去除首尾空格、YAML 列表符号等）。
    3. 严格格式检查（必须含有逗号作为分隔符）。
    4. 规则类型归一化（如 HOST -> DOMAIN）。
    5. 规则值标准化（统一转为小写）。
    6. 去除参数并重组（只保留 TYPE 和 VALUE，丢弃 no-resolve 等后缀）。

    参数:
        line (str): 一条原始的规则文本行。

    返回:
        str: 标准化后的规则字符串 "TYPE,value"。
        None: 如果该行是无效行或被过滤。
    """
    # 1. 检查输入是否为空
    if not line:
        return None

    # 1. 去除行内注释
    # 如果行中包含 #，只保留 # 之前的部分
    # 例如 "DOMAIN,google.com # 备注" 经过此步后只剩下 "DOMAIN,google.com "
    if "#" in line:
        line = line.split("#")[0]

    # 2. 基础去空
    # 去除字符串两端的空格
    line = line.strip()

    # 3. 排除无效行 (第一轮检查)
    # 如果去除空格后内容为空，则视为无效行
    if not line:
        return None

    # 去除 YAML 列表符号 "- "，因为有些规则是直接写在 YAML 列表下的
    if line.startswith("- "):
        line = line[2:].strip()

    # 排除疑似 YAML 键名：如果以冒号结尾但没有逗号，很可能是 YAML 结构中的键名，不是规则
    if line.endswith(":") and "," not in line:
        return None

    # -------------------------------------------------------
    # 核心标准化逻辑
    # -------------------------------------------------------

    # 必须包含逗号：规则必须由 "类型,值" 组成
    if "," not in line:
        return None

    # 按逗号分割规则为多个部分
    parts = line.split(",")

    # 必须至少有两部分 (TYPE, VALUE)
    if len(parts) < 2:
        return None

    # A. 提取并归一化类型 (TYPE)
    # 提取第一部分（类型），去除空格，并转换为大写
    raw_type = parts[0].strip().upper()
    # 查表进行映射，如果原始类型不在 TYPE_MAPPING 中，则保留原始类型
    final_type = TYPE_MAPPING.get(raw_type, raw_type)

    # B. 提取并标准化值 (VALUE)
    # 提取第二部分（值），去除空格，并转换为小写（域名或关键词通常不区分大小写）
    value_part = parts[1].strip().lower()

    # C. 完整性检查
    # 检查类型和值是否为空
    if not final_type or not value_part:
        return None

    # D. 重新拼装
    # 只使用清洗后的类型和值，丢弃 parts[2] 及之后的所有内容，实现“去参”
    return f"{final_type},{value_part}"
