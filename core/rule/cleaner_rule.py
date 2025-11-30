# core/rule/cleaner_rule.py

# ----------------------------------------------------------------------
# 类型映射表 (Type Mapping)
# 将不同软件或格式的规则类型名称，统一映射为项目内部的标准名称。
# ----------------------------------------------------------------------
TYPE_MAPPING = {
    # --- 标准化映射 ---
    "HOST": "DOMAIN",
    "HOST-SUFFIX": "DOMAIN-SUFFIX",
    "HOST-WILDCARD": "DOMAIN-WILDCARD",
    "HOST-KEYWORD": "DOMAIN-KEYWORD",
    # IP 类规则的统一：
    # 将 IP6-CIDR 统一映射为更常见的 IP-CIDR6 格式。
    "IP6-CIDR": "IP-CIDR6",
    "IP-CIDR6": "IP-CIDR6",
    "PROCESS-NAME": "USER-AGENT",
}


def clean_rule_line(line: str) -> str | None:
    """
    规则清洗与标准化主入口

    该函数负责接收任意格式的原始文本行，经过清洗、识别和转换，
    最终输出统一格式的 "TYPE,value" 字符串。

    支持处理的格式包括：
    1. 标准格式 (Quantumult X, Loon, Surge)
    2. AdBlock 格式 (||example.com^, !注释)
    3. Hosts 格式 (127.0.0.1 example.com)
    4. 纯域名/纯IP 格式
    5. 各种缩写变体 (如 .example.com)
    """

    # --- 第一阶段：强力预处理 ---

    # 1. 基础空检查
    # 如果输入行为空，直接返回 None
    if not line:
        return None

    # 2. 处理 Shell/YAML 风格注释
    # 如果包含 '#'，只保留 '#' 之前的内容
    # 例如 "DOMAIN,google.com # 备注" 经过此步后只剩下 "DOMAIN,google.com "
    if "#" in line:
        line = line.split("#")[0]

    # 3. 处理 AdBlock 风格注释
    # AdBlock 格式通常使用 '!' 作为注释开头。
    # 必须在去除空格前检查，或者检查去除空格后的首字符。
    # 为了避免误判 URL 中的参数（如 id=!123），我们只检查整行是否以 '!' 开头。
    if line.strip().startswith("!"):
        return None

    # 4. 去除首尾空格
    # 去除字符串两端的空格
    line = line.strip()

    # 5. 二次空检查
    # 如果清洗后变为空字符串，则视为无效行
    if not line:
        return None

    # 6. 剔除不支持的规则类型 (防污染)
    # AdBlock 列表常包含网页元素隐藏规则 (Cosmetic Rules)，通常以 ## 或 #@# 开头。
    # 这些规则用于隐藏网页上的广告图片/DIV，不属于网络分流规则，必须丢弃。
    if line.startswith("##") or line.startswith("#@#"):
        return None

    # 7. 去除 YAML 列表符号
    # 有些源文件是 YAML 格式，规则前带有 "- "，需要去除。
    if line.startswith("- "):
        line = line[2:].strip()

    # --- 第二阶段：路由分发 ---

    # 8. 判定是否为“标准格式”
    # 如果行内包含逗号，通常意味着它已经具备 "TYPE,Value" 的结构。
    if "," in line:
        return _handle_standard_format(line)

    # 9. 判定是否为“兼容格式”
    # 如果不含逗号，说明是简写或特殊格式，进入兼容性推断逻辑。
    return _handle_compatibility_format(line)


def _handle_standard_format(line: str) -> str | None:
    """
    处理器：处理带逗号的标准格式。
    例如: "DOMAIN-SUFFIX,google.com,Proxy"
    """

    # 1. 分割字符串
    parts = line.split(",")

    # 2. 长度检查
    # 标准规则至少需要包含类型(Type)和值(Value)两部分
    if len(parts) < 2:
        return None

    # 3. 提取并清洗字段
    # 类型转大写 (如 domain -> DOMAIN)
    raw_type = parts[0].strip().upper()
    # 值转小写 (域名不区分大小写，统一小写有助于去重)
    value_part = parts[1].strip().lower()

    # 4. 兼容 Clash 的特殊写法
    # Clash 有时使用 FULL:example.com 表示精确匹配
    if raw_type == "FULL":
        raw_type = "DOMAIN"

    # 5. 类型映射
    # 将原始类型转换为项目内部标准类型
    final_type = TYPE_MAPPING.get(raw_type, raw_type)

    # 6. 有效性检查
    # 确保类型和值均存在
    if not final_type or not value_part:
        return None

    # 7. 过滤不支持的高级类型
    # DOMAIN-SET/RULE-SET 是引用外部文件，无法转换为单条规则。
    # URL-REGEX 是正则匹配，跨软件兼容性差，且容易导致性能问题，暂不处理。
    if final_type in ["DOMAIN-SET", "RULE-SET", "URL-REGEX"]:
        return None

    # 8. 返回标准化结果
    # 重新拼装，丢弃原有的策略组(Proxy)或参数(no-resolve)，只保留核心规则。
    return f"{final_type},{value_part}"


def _handle_compatibility_format(line: str) -> str | None:
    """
    处理器：处理不带逗号的各种变体格式。
    按顺序尝试匹配，一旦匹配成功立即返回。
    """

    # 为了方便匹配，统一转换为小写副本
    line_lower = line.lower()

    # -------------------------------------------------------
    # 场景 1: Hosts 文件格式
    # 特征: 以 127.0.0.1 或 0.0.0.0 开头，后面跟域名
    # 示例: "127.0.0.1 ad.google.com"
    # -------------------------------------------------------
    if line_lower.startswith(("127.0.0.1", "0.0.0.0")):
        # 使用默认空白字符分割
        parts = line_lower.split()
        # 确保至少有 IP 和 域名 两部分
        if len(parts) >= 2:
            # 取最后一部分作为域名，并视为精确匹配 (DOMAIN)
            return f"DOMAIN,{parts[-1].strip()}"

    # -------------------------------------------------------
    # 场景 2: AdBlock / EasyList 格式
    # 特征: 以 || 开头，可能包含 ^ 或 $ 等修饰符
    # 示例: "||example.com^" 或 "||example.com^$third-party"
    # -------------------------------------------------------
    if line_lower.startswith("||"):
        # 去掉开头的 ||
        content = line_lower[2:]

        # 截断结尾的符号
        # AdBlock 使用 ^ 作为分隔符，使用 $ 作为选项分隔符
        for char in ["^", "$"]:
            if char in content:
                content = content.split(char)[0]

        content = content.strip()
        if content:
            # AdBlock 的 || 含义为匹配域名及其子域名，对应 DOMAIN-SUFFIX
            return f"DOMAIN-SUFFIX,{content}"

    # -------------------------------------------------------
    # 场景 3: 点号缩写格式 (Dnsmasq/SmartDNS)
    # 特征: 以 . 开头
    # 示例: ".youku.com"
    # -------------------------------------------------------
    if line_lower.startswith("."):
        # 去除开头的点
        content = line_lower.lstrip(".").strip()
        if content:
            # 这种写法通常表示包含子域名，对应 DOMAIN-SUFFIX
            return f"DOMAIN-SUFFIX,{content}"

    # -------------------------------------------------------
    # 场景 4: 纯 IP 或 CIDR 格式
    # 特征: 以数字开头，包含点(IPv4)或冒号(IPv6)
    # 示例: "1.2.3.4", "192.168.1.0/24"
    # -------------------------------------------------------
    if line_lower[0].isdigit():
        # 定义合法的 IP 字符集合 (数字, 点, 斜杠, 冒号)
        valid_ip_chars = set("0123456789./:")

        # 检查是否所有字符都合法，且不包含非法字母
        if all(c in valid_ip_chars for c in line_lower):
            # 如果包含冒号，判定为 IPv6
            if ":" in line_lower:
                return f"IP-CIDR6,{line_lower}"
            # 否则判定为 IPv4
            # 即使没有 / (如 1.1.1.1)，我们也统一标记为 IP-CIDR，
            # 大多数代理软件能自动处理不带掩码的单 IP。
            return f"IP-CIDR,{line_lower}"

    # -------------------------------------------------------
    # 场景 5: 纯域名格式 (兜底策略)
    # 特征: 包含点，不含空格，不含路径符号(/)
    # 示例: "google.com"
    # -------------------------------------------------------
    if "." in line_lower and "/" not in line_lower:
        # 排除类似 "Ver 1.0" 这种中间带空格的非域名文本
        if " " not in line_lower:
            # 对于纯域名，默认采用后缀匹配，这是最安全的策略
            return f"DOMAIN-SUFFIX,{line_lower}"

    # 如果以上所有尝试都失败，则判定为无法识别的格式
    return None
