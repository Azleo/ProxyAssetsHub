# /main.py

# 引入核心管理类 Manager。
# 这个类通常是整个程序的“总指挥”，负责调度和协调程序的主要工作流程。
from core.manager import Manager

# 引入 Python 标准库中的 argparse 模块。
# 它的作用是处理命令行参数，让我们可以通过终端给程序传递指令（比如：python main.py --debug）。
import argparse

# 从项目的常量定义文件中引入日志相关的配置常量。
# 将这些值定义在一个单独的文件中（constants.py），可以避免在代码中到处手写字符串或数字，
# 方便后续统一修改和管理。
from core.constants import (
    LOG_LEVEL_DEFAULT,
    LOG_LEVEL_INFO,
    LOG_LEVEL_DEBUG,
    LOG_STYLE_HUMAN,
    LOG_STYLE_CI,
)


def parse_args():
    """
    函数功能：定义并解析命令行参数。

    这个函数会告诉程序：我们支持接收哪些命令行指令（比如 --debug, --info）。
    当用户运行程序时，它负责把用户输入的指令转化为代码可以理解的变量。

    :return: 返回一个包含所有参数值的对象 (Namespace)。
    """
    # 创建一个参数解析器对象。
    # description 参数用来在用户查看帮助（输入 --help）时，显示一段简短的程序介绍。
    parser = argparse.ArgumentParser(description="ProxyAssetsHub - 代理引用资源聚合")

    # --- 下面定义日志等级相关的参数 ---

    # 添加 --debug 参数。
    # action="store_true" 的意思是：这是一个开关。
    # 如果用户输入了 --debug，变量就是 True；如果没输，变量就是 False。
    # 這是最高级别的日志，通常用于开发人员排查代码的底层问题。
    parser.add_argument(
        "--debug", action="store_true", help="开启调试模式 (显示底层细节)"
    )

    # 添加 --info 参数。
    # 同样是一个开关。
    # 这是一个中等级别的日志，用于让用户看到程序运行的详细进度和统计信息。
    parser.add_argument(
        "--info", action="store_true", help="显示详细统计 (显示处理过程)"
    )

    # --- 下面定义日志风格相关的参数 ---

    # 添加 --ci 参数。
    # CI (Continuous Integration) 通常指自动化流水线环境。
    # 开启后，日志输出会去掉花哨的颜色或特殊排版，方便在 GitHub Actions 等系统中查看。
    parser.add_argument(
        "--ci", action="store_true", help="启用 CI 机器模式 (无装饰/GitHub格式)"
    )

    # 执行解析操作。
    # 系统会检查用户在命令行实际输入了什么，并把结果打包返回。
    return parser.parse_args()


def calculate_config(args):
    """
    函数功能：计算配置逻辑。

    根据用户输入的参数（args），决定程序最终应该使用什么样的日志等级和风格。
    这里包含了参数优先级的判断逻辑。

    :param args: parse_args 函数返回的参数对象。
    :return: 返回一个元组 (level, style)，分别代表日志等级和日志风格。
    """

    # 1. 确定日志风格 (Style)
    # 这是一个三元表达式（简写的 if-else）。
    # 逻辑是：如果用户开启了 --ci 模式，就用 CI 风格；否则默认使用适合人类阅读的 Human 风格。
    style = LOG_STYLE_CI if args.ci else LOG_STYLE_HUMAN

    # 2. 确定日志等级 (Level)
    # 这里使用 if-elif-else 结构来确保只有一个等级生效，并且设定了优先级。
    # 优先级：Debug (最高) > Info (中等) > Default (默认)。

    if args.debug:
        # 如果用户加了 --debug，无论有没有加 --info，都强制使用最高等级的 DEBUG 模式。
        level = LOG_LEVEL_DEBUG
    elif args.info:
        # 如果没开 debug，但是开了 --info，则使用 INFO 模式。
        level = LOG_LEVEL_INFO
    else:
        # 如果用户什么开关都没加，就使用最安静的默认模式。
        level = LOG_LEVEL_DEFAULT

    # 将计算好的等级和风格返回给调用者。
    return level, style


def main():
    """
    函数功能：程序的主入口。

    这是整个脚本开始执行逻辑的地方，它像一个剧本的开端，
    按顺序调用上面的函数来完成准备工作，最后启动核心功能。
    """
    # 第一步：获取用户在命令行输入的参数。
    # 比如用户输入了：python main.py --info
    args = parse_args()

    # 第二步：根据参数计算最终的配置。
    # 比如根据上面的输入，这里会得到 level=INFO, style=HUMAN。
    level, style = calculate_config(args)

    # 第三步：初始化核心管理器 (Manager)。
    # 我们把计算好的日志等级和风格传递给 Manager，
    # 这样 Manager 在后续工作中就知道该怎么输出日志了。
    manager = Manager(level=level, style=style)

    # 第四步：启动程序。
    # 调用 manager 的 run 方法，正式开始执行程序的核心业务逻辑（比如抓取规则、聚合数据等）。
    manager.run()


# 这是一个标准的 Python 惯用写法。
# 它的作用是判断当前文件是被直接运行的，还是被当作模块导入的。
# 只有当你在终端直接运行 `python main.py` 时，if 下面的代码才会执行。
if __name__ == "__main__":
    main()
