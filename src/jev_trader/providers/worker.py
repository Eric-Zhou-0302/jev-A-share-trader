from __future__ import annotations

import contextlib
import io
import multiprocessing
import signal
import threading
import time

from jev_trader.models import AnalysisError


def _run(connection):
    # 将可能没有超时参数的第三方调用隔离，主进程可终止超时请求。
    # Ctrl+C 交给父进程统一暂停任务并关闭管道，避免子进程打印中断堆栈。
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    import akshare
    while True:
        try:
            function, kwargs = connection.recv()
        except EOFError:
            return
        if function is None:
            return
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = getattr(akshare, function)(**kwargs)
            connection.send((True, result))
        except Exception as exc:
            # 第三方异常可能带 URL 或请求头；只传递错误类型。
            connection.send((False, type(exc).__name__))


class AKWorker:
    def __init__(self, timeout: int, interval: float):
        self.timeout, self.interval = timeout, interval
        self.lock = threading.Lock()
        self.process = None
        self.connection = None
        self.last_call = 0.0

    def _start(self):
        context = multiprocessing.get_context("spawn")
        self.connection, child = context.Pipe()
        self.process = context.Process(target=_run, args=(child,), daemon=True)
        self.process.start()
        child.close()

    def _stop(self):
        if self.process:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=3)
            self.process = None
        if self.connection:
            self.connection.close()
            self.connection = None

    def call(self, function: str, **kwargs):
        with self.lock:
            if self.process is None or not self.process.is_alive():
                self._stop()
                self._start()
            time.sleep(max(0, self.interval - (time.monotonic() - self.last_call)))
            self.last_call = time.monotonic()
            try:
                self.connection.send((function, kwargs))
                if not self.connection.poll(self.timeout):
                    self._stop()
                    raise AnalysisError("data_timeout", "行情接口超时，请稍后重试。", "Market data request timed out; retry later.")
                ok, result = self.connection.recv()
                if not ok:
                    raise AnalysisError("data_unavailable", f"行情接口暂不可用（{function}：{result}）。", f"Market data unavailable ({function}: {result}).")
                return result
            except (EOFError, BrokenPipeError, OSError) as exc:
                self._stop()
                raise AnalysisError("data_unavailable", "行情数据进程中断，请重试。", "The market data worker stopped; retry the request.") from exc

    def close(self):
        with self.lock:
            if self.process and self.process.is_alive() and self.connection:
                try:
                    self.connection.send((None, {}))
                    self.process.join(timeout=3)
                except (OSError, EOFError):
                    pass
            self._stop()
