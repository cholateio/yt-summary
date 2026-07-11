"""執行期進度輸出。

一律寫 stderr——stdout 留給最終的用量摘要與產物路徑,pipe 出去不會被污染。
非 TTY(重導向到檔案)時不用 \\r 覆寫,改印獨立行,避免 log 檔塞滿控制字元。
"""
from __future__ import annotations

import sys
import threading


class Reporter:
    """步驟式進度:step() 開一行,progress() 就地更新計數,ok()/warn() 收尾。"""

    def __init__(self, total_steps: int = 0, stream=None, enabled: bool = True,
                 isatty: bool | None = None):
        self._total = total_steps
        self._stream = sys.stderr if stream is None else stream
        self._enabled = enabled
        self._tty = self._stream.isatty() if isatty is None else isatty
        self._lock = threading.Lock()  # M5 由多個 worker thread 同時回報
        self._n = 0
        self._label = ""
        self._numbered = True
        self._open = False  # 目前這行印了前綴但還沒收尾

    def set_total(self, total_steps: int) -> None:
        """總步數 full/quick 不同,而 mode 要抓到片長才知道——故總數延後設定。"""
        self._total = total_steps

    def _write(self, s: str) -> None:
        self._stream.write(s)
        self._stream.flush()

    def _prefix(self) -> str:
        if not self._numbered:
            return f"{self._label}… "
        return f"[{self._n}/{self._total}] {self._label}… "

    def begin(self, label: str) -> None:
        """不編號的前導行(抓 metadata——它決定了後面有幾步)。"""
        if not self._enabled:
            return
        with self._lock:
            self._label = label
            self._numbered = False
            self._open = True
            self._write(self._prefix())

    def step(self, label: str) -> None:
        if not self._enabled:
            return
        with self._lock:
            self._n += 1
            self._label = label
            self._numbered = True
            self._open = True
            self._write(self._prefix())

    def progress(self, done: int, total: int) -> None:
        """步驟內的計數(M5 逐段完成)。非 TTY 時跳過,最終計數由 ok() 帶出。"""
        if not self._enabled or not self._tty:
            return
        with self._lock:
            if self._open:
                self._write(f"\r{self._prefix()}{done}/{total}\033[K")

    def ok(self, detail: str = "") -> None:
        if not self._enabled:
            return
        with self._lock:
            tail = f"✓{(' ' + detail) if detail else ''}"
            if self._open and self._tty:
                self._write(f"\r{self._prefix()}{tail}\033[K\n")
            elif self._open:
                self._write(f"{tail}\n")
            else:
                self._write(f"      {tail}\n")  # 前面被 warn 換過行,對齊縮排
            self._open = False

    def warn(self, msg: str) -> None:
        """即時警告(LLM 重試、單段失敗)——不再只躺在 run.log 裡。"""
        if not self._enabled:
            return
        with self._lock:
            if self._open:
                self._write("\n")  # 把未收尾的步驟行斷掉,警告獨立成行
                self._open = False
            self._write(f"      ⚠ {msg}\n")

    def close_line(self) -> None:
        """例外中止時把未收尾的步驟行斷掉,錯誤訊息才不會黏在後面。"""
        if not self._enabled:
            return
        with self._lock:
            if self._open:
                self._write("\n")
                self._open = False
