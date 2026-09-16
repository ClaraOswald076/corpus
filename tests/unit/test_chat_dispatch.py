import time

from src.api.routes.chat import _extract_dispatch_targets


def test_single_dispatch_block_extracts_full_name():
    msg = "[任务分派] 启动「官网改版」 发送至：**张三**"
    assert _extract_dispatch_targets(msg) == ["张三"]


def test_plain_text_tail_extracts_full_name():
    msg = "[任务分派] 启动「巡检」 发送至：安全审计员"
    assert _extract_dispatch_targets(msg) == ["安全审计员"]


def test_bold_tail_with_trailing_text_stops_at_close():
    msg = "[任务分派] 启动「巡检」 发送至：**数据工程师** 请查收"
    assert _extract_dispatch_targets(msg) == ["数据工程师"]


def test_multiple_blocks_pair_within_block():
    msg = "[任务分派]A 启动「a」 发送至：**张三** [任务分派]B 启动「b」 发送至：**李四**"
    assert _extract_dispatch_targets(msg) == ["张三", "李四"]


def test_block_without_tail_does_not_reach_into_next_block():
    # 无尾标的块不跨块吸附下一个块的尾标
    msg = "[任务分派]A 一大段没有尾标的内容 [任务分派]B 发送至：**李四**"
    assert _extract_dispatch_targets(msg) == ["李四"]


def test_adversarial_message_is_linear():
    # 60KB 全 marker 无尾标：旧正则二次方回溯会冻结事件循环十几秒
    msg = "[任务分派]" * 10000
    t0 = time.perf_counter()
    assert _extract_dispatch_targets(msg) == []
    assert time.perf_counter() - t0 < 1.0
