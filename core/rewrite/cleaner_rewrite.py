# core/rewrite/cleaner_rewrite.py


def clean_rewrite_line(line: str) -> str | None:
    """
    重写规则的极简清洗
    """
    # 检查输入是否为空
    if not line:
        return None
        
    # 去除字符串两端的空白字符（包括空格、制表符、换行符等）
    return line.strip()