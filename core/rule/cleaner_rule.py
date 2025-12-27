# core/rule/cleaner_rule.py

# ======================================================================
# 模块名称：规则清洗与标准化器 (Rule Cleaner & Normalizer)
# ======================================================================
# 【1. 模块设计意图 (Design Intent)】
#
#    本模块是规则处理流水线中的核心“提纯”阶段。其唯一目标是将来自不同
#    上游源的规则，统一转换为项目内部使用的标准格式 (TYPE,VALUE)。
#
# 【2. 职责边界 (Clear Boundaries)】
#
#    - 负责：物理杂质剥离、基础语义标准化、规则类型识别、去重前置准备。
#    - 不负责：具体软件适配（如 QX/Clash 特有语法）、参数生成（如 no-resolve）。
#    - 核心原则：高保真。对非域名类规则禁止跨语义映射，确保数据真实性。
#
# 【3. 现实前提 (Context)】
#
#    上游数据被定义为“受约束的有序杂乱”，主要来自成熟规则集。因此模块
#    采用“流水线”结构，对主流格式进行精准打击，对极端模糊格式直接丢弃。
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

# ======================================================================
# 公共入口：流水线主控 (Main Pipeline)
# ======================================================================


def clean_rule_line(line: str) -> str | None:
    """
    单行规则清洗入口。通过分层处理，逐步将原始文本提纯为标准规则。
    """
    if not line:
        return None

    # 1. 物理层预处理 (Physical Pre-processing)
    # 解决：注释、YAML包装符号、成对引号等物理形态干扰
    raw_content = _strip_layer(line)
    if not raw_content:
        return None

    # 2. 语义标准化层 (Semantic Normalization)
    # 解决：大小写不一、FQDN尾点冗余等基础一致性问题
    norm_content = _normalize_layer(raw_content)

    # 3. 分类路由层 (Routing Layer)
    # 解决：根据内容特征，将规则分发到对应的解析处理器
    if "," in norm_content:
        return _handle_standard_format(norm_content)

    return _handle_compatibility_format(norm_content)


# ======================================================================
# 第一阶段：原子处理逻辑 (Atomic Logic)
# ======================================================================


def _strip_layer(line: str) -> str | None:
    """
    【物理剥离层】
    剥离规则外围的“壳”，不涉及对规则内容的理解。
    """
    # 1. 处理行内注释 (Shell/YAML 风格)
    # 解决：去除 # 及其之后的内容，仅保留有效载荷
    if "#" in line:
        line = line.split("#", 1)[0]

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

    # 5. 丢弃 AdBlock 网页元素隐藏规则
    # 特征：以 ## 或 #@# 开头。这些不属于分流规则，必须丢弃
    if not content or content.startswith("##") or content.startswith("#@#"):
        return None

    return content


def _normalize_layer(content: str) -> str:
    """
    【标准化层】
    对规则载荷进行格式修剪，提高去重准确性。
    """
    # 1. 统一转小写
    # 解决：域名不区分大小写，统一小写是去重的前提
    content = content.lower()

    # 2. 移除域名末尾多余的点 (FQDN 规范化)
    # 解决：例如 "google.com." 与 "google.com" 语义等价，需统一
    if content.endswith("."):
        content = content.rstrip(".")

    return content


def _handle_standard_format(line: str) -> str | None:
    """
    【处理器】解析带逗号的标准格式 (TYPE,VALUE,...)
    """
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 2:
        return None

    # 1. 提取并映射规则类型
    raw_type = parts[0].upper()
    value = parts[1]

    # 2. 兼容性转换
    # 解决：部分规则集将 DOMAIN 写作 FULL 的情况
    if raw_type == "FULL":
        raw_type = "DOMAIN"

    final_type = TYPE_MAPPING.get(raw_type, raw_type)

    # 3. 过滤不支持的高级或动态类型
    # 解决：DOMAIN-SET 等涉及外部引用的类型无法作为单条规则处理
    if final_type in {"DOMAIN-SET", "RULE-SET", "URL-REGEX"}:
        return None

    # 4. 白名单校验
    # 解决：确保类型合法且核心内容 (value) 不为空
    if final_type not in SUPPORTED_TYPES or not value:
        return None

    return f"{final_type},{value}"


def _handle_compatibility_format(line: str) -> str | None:
    """
    【处理器】解析不带逗号的兼容格式 (推断解析)
    """
    # ------------------------------------------------------------------
    # 1. IPv6 规则判定 (优先处理)
    # 特征：包含冒号。允许字母开头（如 2001::）
    # ------------------------------------------------------------------
    if ":" in line:
        if all(c in "0123456789abcdef./: " for c in line):
            return f"IP-CIDR6,{line}"

    # ------------------------------------------------------------------
    # 2. IPv4 / Hosts 规则判定
    # 特征：以数字开头且包含点
    # ------------------------------------------------------------------
    if line[0].isdigit() and "." in line:
        if all(c in "0123456789./ " for c in line):
            # 处理 Hosts 格式 (如 127.0.0.1 example.com)
            parts = line.split()
            if len(parts) >= 2:
                return f"DOMAIN,{parts[-1]}"
            # 纯 IP 或 CIDR 格式
            return f"IP-CIDR,{line}"

    # ------------------------------------------------------------------
    # 3. AdBlock / 简写后缀判定
    # 特征：以 ||, ., +., *. 等前缀开头
    # ------------------------------------------------------------------
    if line.startswith("||"):
        # 剥离前缀并截断 AdBlock 的修饰符 (^, $)
        content = line[2:].split("^", 1)[0].split("$", 1)[0]
        if content:
            return f"DOMAIN-SUFFIX,{content}"

    if line.startswith((".", "+.", "*.")):
        content = line.lstrip("+*.")
        if content:
            return f"DOMAIN-SUFFIX,{content}"

    # ------------------------------------------------------------------
    # 4. 纯域名兜底处理
    # 特征：包含点，且不含路径符号(/)或空格
    # ------------------------------------------------------------------
    if "." in line and "/" not in line and " " not in line:
        return f"DOMAIN-SUFFIX,{line}"

    return None
