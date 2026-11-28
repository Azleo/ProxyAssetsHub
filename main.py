# /main.py

# 程序入口。
# 这里只做两件事：读命令行参数、决定日志详略，然后把活交给 Manager。
# 呈现方式（终端还是 CI 格式）由日志模块自己判断，不再需要命令行开关。

import argparse
import sys
import traceback

from core.constants import LOG_LEVEL_DEBUG, LOG_LEVEL_INFO
from core.manager import Manager


def parse_args():
    """
    定义并解析命令行参数。

    只保留一个开关：
      --debug  输出更详细的信息（每个源的明细、被丢弃的样例等）
    不加就是默认级别，够看结果。
    """
    parser = argparse.ArgumentParser(description="ProxyAssetsHub - 代理引用资源聚合")
    parser.add_argument("--debug", action="store_true", help="输出详细调试信息")
    return parser.parse_args()


def main():
    """
    程序主入口。

    返回退出码：有任务失败就是 1，否则 0。
    这样 CI 能靠退出码判断这次运行到底成没成，而不是只看到一行日志。
    """
    args = parse_args()

    # 详略由参数决定；呈现方式由环境决定（CI 里自动切格式）
    level = LOG_LEVEL_DEBUG if args.debug else LOG_LEVEL_INFO

    manager = Manager(level=level)
    try:
        records = manager.run()
    except Exception:  # noqa: BLE001 - 未预料的错误也要让 CI 看到
        traceback.print_exc()
        return 1

    # 一个任务都没跑（例如配置目录不存在）同样是异常状态：
    # 这时候"没有失败"只是因为什么都没做，不能算成功。
    if not records:
        return 1

    failed = [r for r in records if r["state"] == "失败"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
