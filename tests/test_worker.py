import os
import signal

from jev_trader.providers.worker import AKWorker


def test_interrupt_is_owned_by_parent_and_worker_closes_cleanly():
    worker = AKWorker(timeout=15, interval=.1)
    try:
        # 只调用本地模块目录，不访问任何行情网络接口。
        assert "stock_zh_a_hist" in worker.call("__dir__")
        process = worker.process
        os.kill(process.pid, signal.SIGINT)
        assert "stock_zh_a_hist" in worker.call("__dir__")
        assert worker.process is process
    finally:
        worker.close()
    assert not process.is_alive()
