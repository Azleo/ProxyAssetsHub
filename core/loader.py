# core/loader.py

# ======================================================================
# 模块说明：配置加载
#
# 职责：把 configs/<阶段>/ 下的配置文件读成"任务列表"。
#
# 边界约定（和其他模块一致）：
#   - 输入：阶段名（例如 "rule"）
#   - 输出：(配置列表, 问题列表)
#   - 不打印任何东西，也不直接操作日志。出了问题就记一条"问题"，
#     文案由日志模块按 code 渲染，怎么显示、显示在哪由 manager 决定。
# ======================================================================

import os

import yaml

# 通用配置里允许出现的字段。
# 只有这两项是"所有规则集都可能一致"的；sources / filters 属于每个任务自己的事，
# 放进通用配置容易造成难以排查的全局影响，因此明确不允许。
DEFAULTS_ALLOWED_KEYS = ("formats", "enabled")


def _problem(level: str, code: str, scope: str = "", **params) -> dict:
    """
    构造一条问题记录。

    level：error / warn / debug
    code ：文案字典里的键（例如 YAML_ERR），具体怎么说由日志模块决定
    scope：出问题的对象（文件名、路径等）
    params：填充文案模板用的参数
    """
    return {"level": level, "code": code, "scope": scope, "params": params}


# ======================================================================
# 单个配置文件的读取与校验
# ======================================================================


def _load_single_config(path: str, problems: list) -> dict | None:
    """读取并解析单个 YAML 文件。失败时返回 None 并记一条问题。"""
    name = os.path.basename(path)

    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        if not cfg:
            problems.append(_problem("error", "CONFIG_EMPTY", name))
            return None

        # 根节点必须是字典。写成列表或单个值（例如误加了一个 "- "）时，
        # 后面每个字段的读取都会抛异常，进而拖垮整批加载，所以在这里就拦下。
        if not isinstance(cfg, dict):
            problems.append(_problem("error", "CONFIG_NOT_DICT", name))
            return None

        return cfg

    except yaml.YAMLError as e:
        problems.append(_problem("error", "YAML_ERR", name, detail=e))
        return None
    except Exception as e:  # noqa: BLE001 - 单个配置读失败不影响其它配置
        problems.append(_problem("error", "LOAD_ERR", name, detail=e))
        return None


def _check_field_types(cfg: dict, filename: str, problems: list) -> bool:
    """
    检查关键字段的类型，类型不对返回 False。

    为什么要专门做这一步：后面每个环节都默认这些字段是对的，
    类型错了不会当场报错，而是走到某个奇怪的地方才崩，或者更糟——
    悄悄算出错误结果（例如把 formats 写成字符串，会被拆成单个字符）。
    """
    # 顶层字段该是什么类型
    for key, expect, code in (
        ("formats", list, "FORMATS_NOT_LIST"),
        ("custom_headers", dict, "CUSTOM_HEADERS_NOT_DICT"),
        ("filters", dict, "FILTERS_NOT_DICT"),
    ):
        # 值为空表示"没写"，交给通用配置补齐，不算错误
        if cfg.get(key) is not None and not isinstance(cfg[key], expect):
            problems.append(_problem("error", code, filename))
            return False

    # formats 里的每一项必须是字符串
    formats = cfg.get("formats") or []
    if not all(isinstance(item, str) for item in formats):
        problems.append(_problem("error", "FORMATS_ITEM_NOT_STR", filename))
        return False

    # filters 下面这几项必须是列表，写成字符串会被逐字符遍历
    filters = cfg.get("filters") or {}
    for key in ("ignored_rules", "extra_rules", "exclude_keywords", "include_keywords"):
        if filters.get(key) is not None and not isinstance(filters[key], list):
            problems.append(_problem("error", "FILTER_ITEM_NOT_LIST", filename, key=key))
            return False

    # 这两个字段会变成文件名和规则行的一部分，必须是字符串
    for key in ("collection", "policy"):
        if cfg.get(key) is not None and not isinstance(cfg[key], str):
            problems.append(_problem("error", "IDENT_NOT_STR", filename, key=key))
            return False

    return True


def _preprocess_config(cfg: dict, problems: list) -> dict | None:
    """
    校验并补齐配置的必填项。

    返回 None 表示这个配置不该继续处理（被禁用、或者写法有错）。
    """
    filename = cfg.get("__filename__", "UnknownFile")

    # 0. 类型不对就别往下走了，硬着头皮跑只会得到更难查的错
    if not _check_field_types(cfg, filename, problems):
        return None

    # 1. 名称：没写就用文件名补上
    if not cfg.get("name"):
        problems.append(_problem("warn", "NAME_NOT_SET", filename))
        cfg["name"] = os.path.splitext(filename)[0]

    # 2. 启用开关：默认启用，只有明确写 false 才跳过。
    #    没写（None）和 true 都继续；其余值视为配置写错，报 error 而不是静默禁用——
    #    静默禁用会让人以为"明明开了却不跑"，还查不出原因。
    raw_enabled = cfg.get("enabled")
    if raw_enabled is True or raw_enabled is None:
        pass
    elif raw_enabled is False:
        problems.append(_problem("debug", "CONFIG_DISABLED", filename))
        return None
    elif isinstance(raw_enabled, str):
        problems.append(
            _problem("error", "ENABLED_TYPE_ERR", filename, value=raw_enabled)
        )
        return None
    else:
        problems.append(_problem("error", "ENABLED_UNKNOWN", filename))
        return None

    # 3. 规则集标识与策略名
    # collection: 规则集标识，用于文件名、README 和日志。没写就用配置文件名（去掉 .yaml），
    #             同一目录下的文件名不会重复，所以默认值天然唯一。
    # policy    : 策略名，目前只有 Quantumult X 的规则行会用到。没写就跟随 collection。
    if not cfg.get("collection"):
        cfg["collection"] = os.path.splitext(filename)[0]
    if not cfg.get("policy"):
        cfg["policy"] = cfg["collection"]

    # 4. 输出格式名统一小写（配置里可能写成 QuAnTuMuLtX）
    cfg["formats"] = [fmt.lower() for fmt in cfg.get("formats", [])]

    # 5. 自定义头部里的格式名也统一小写
    standardized_headers = {}
    for fmt, headers in cfg.get("custom_headers", {}).items():
        standardized_headers[fmt.lower()] = headers
    cfg["custom_headers"] = standardized_headers

    # 6. 校验来源列表
    raw_sources = cfg.get("sources", [])
    if raw_sources is None or not isinstance(raw_sources, list):
        problems.append(_problem("error", "SOURCES_NOT_LIST", filename))
        return None

    valid_sources = []
    for item in raw_sources:
        if isinstance(item, str) and item.strip():
            valid_sources.append(item.strip())

    if not valid_sources:
        problems.append(_problem("error", "SOURCES_EMPTY", filename))
        return None

    cfg["sources"] = valid_sources
    return cfg


def _build_formats_data(cfg: dict) -> dict:
    """把"输出格式"展开成每种格式需要的参数（策略名、自定义头部）。"""
    formats_data = {}
    for fmt in cfg.get("formats", []):
        header_data = cfg.get("custom_headers", {}).get(fmt, {})
        formats_data[fmt] = {
            "policy": cfg["policy"],
            "header_lines": header_data.get("header_lines", []),
        }
    cfg["formats_data"] = formats_data
    return cfg


# ======================================================================
# 通用配置的读取与合并
# ======================================================================


def _load_defaults(subdir: str, problems: list, project_root: str) -> dict:
    """
    读取该阶段的通用配置（configs/defaults_<阶段>.yaml）。

    文件不存在时返回空字典，表示没有任何默认值（这是正常状态，不算问题）。
    """
    path = os.path.join(project_root, "configs", f"defaults_{subdir}.yaml")
    name = os.path.basename(path)

    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        problems.append(_problem("error", "YAML_ERR", name, detail=e))
        return {}
    except Exception as e:  # noqa: BLE001
        problems.append(_problem("error", "LOAD_ERR", name, detail=e))
        return {}

    # 空文件视为"没有默认值"，不当成错误
    if not raw:
        return {}

    if not isinstance(raw, dict):
        problems.append(_problem("error", "DEFAULTS_NOT_DICT", name))
        return {}

    # 白名单过滤：不认识的字段直接忽略并告警，避免默认值文件自己写错却毫无反应
    defaults = {}
    for key, value in raw.items():
        if key in DEFAULTS_ALLOWED_KEYS:
            defaults[key] = value
        else:
            problems.append(_problem("warn", "DEFAULTS_KEY_IGNORED", name, key=key))
    return defaults


def _apply_defaults(cfg: dict, defaults: dict) -> dict:
    """
    把通用配置里"该配置没写"的字段补上。

    注意：判断依据是"字段是否存在"，不是"值是否为空"。
    所以配置里写 formats: [] 表示"这个规则集不要任何输出"，不会被通用配置盖掉。
    """
    for key, value in defaults.items():
        if key not in cfg:
            cfg[key] = value
    return cfg


# ======================================================================
# 主加载函数
# ======================================================================


def load_all_configs(
    subdir: str = "rule", project_root: str | None = None
) -> tuple[list[dict], list[dict]]:
    """
    读取某个阶段下的全部配置。

    返回 (配置列表, 问题列表)。目录结构即输出结构：
    configs/rule/AI/x.yaml 会输出到 rule/<客户端>/AI/ 下面。

    project_root 是项目根目录。writer、reporter 都靠这个参数定位，
    这里也用同一个口径，避免"在别的目录下运行就找不到配置"。
    不传时退回当前工作目录，保持对旧调用方式兼容。
    """
    root = project_root or os.getcwd()
    configs_dir = os.path.join(root, "configs", subdir)
    prepared_configs = []
    problems = []

    if not os.path.exists(configs_dir):
        # 配置目录不存在意味着一个任务都跑不了，是错误而不是提示：
        # 否则程序会输出"0 个任务、全部正常"，看起来像成功。
        problems.append(_problem("error", "DIR_NOT_FOUND", "", path=configs_dir))
        return prepared_configs, problems

    # 通用配置只读取一次，供本阶段所有配置共用
    defaults = _load_defaults(subdir, problems, root)

    # 先把所有配置文件收集起来并排序。
    # os.walk 的遍历顺序取决于文件系统，不排序的话每次运行的任务顺序都可能不同，
    # 连带的产物顺序、日志顺序、README 顺序都会跟着变，git 里会看到大量无意义改动。
    candidates = []
    # 循环变量不能叫 root：函数开头已经用 root 表示项目根目录，
    # 同名会把它就地覆盖，循环结束后再读 root 拿到的是最后一个子目录。
    for dirpath, _dirs, files in os.walk(configs_dir):
        for file in files:
            # 只认 .yaml：避免同一份配置用两个扩展名时被重复读取
            if file.endswith(".yaml"):
                candidates.append(os.path.join(dirpath, file))
    candidates.sort()

    for path in candidates:
        file_dir = os.path.dirname(path)
        file = os.path.basename(path)

        rel_dir = os.path.relpath(file_dir, configs_dir)
        sub_path = "" if rel_dir == "." else rel_dir

        # 单个配置出任何意外都只影响它自己：记一条问题，继续下一个。
        # 这是最后一道保险——上面的类型检查已经覆盖了已知的坑，
        # 但配置格式千变万化，不能因为一个文件写错就让整批任务都不跑。
        try:
            cfg = _load_single_config(path, problems)
            if not cfg:
                continue

            # 先用通用配置补齐"这份配置没写"的字段
            cfg = _apply_defaults(cfg, defaults)

            cfg["__filename__"] = file
            cfg["__sub_path__"] = sub_path

            cfg = _preprocess_config(cfg, problems)
            if cfg:
                cfg = _build_formats_data(cfg)
                prepared_configs.append(cfg)
        except Exception as error:  # noqa: BLE001 - 单个配置出错不该拖垮整批
            problems.append(_problem("error", "CONFIG_CRASH", file, detail=error))

    return prepared_configs, problems
