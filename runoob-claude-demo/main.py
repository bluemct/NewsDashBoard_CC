import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def add(a: float, b: float) -> float:
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("参数必须是数字类型")
    result = a + b
    logger.info("add(%s, %s) = %s", a, b, result)
    return result


if __name__ == "__main__":
    # 正常加法测试
    assert add(3, 5) == 8, "基本加法失败"
    assert add(-1, 1) == 0, "正负数加法失败"
    assert add(0.1, 0.2) == 0.1 + 0.2, "浮点数加法失败"

    # 错误类型测试
    try:
        add("1", 2)
    except TypeError as e:
        print(f"捕获到类型错误: {e}")

    print("所有测试通过d!")