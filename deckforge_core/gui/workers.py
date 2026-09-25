"""Background execution for the GUI.

Every long call (learning a pack, planning and rendering a deck) runs on a
:class:`Task` thread so the window keeps repainting. The callable receives a
``report(percent, message)`` callback and its return value arrives on the
``succeeded`` signal, delivered back on the GUI thread by Qt.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal

TaskFn = Callable[..., Any]


class Task(QThread):
    """Run one callable off the GUI thread and report progress as it goes.

    The callable is invoked as ``fn(*args, progress=report, **kwargs)``: every
    task function therefore takes a ``progress`` keyword that it can hand to the
    model layer.
    """

    progressed = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: TaskFn, *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def report(self, percent: int, message: str) -> None:
        self.progressed.emit(int(percent), str(message))

    def run(self) -> None:  # pragma: no cover - exercised through TaskRunner
        try:
            result = self._fn(*self._args, progress=self.report, **self._kwargs)
        except Exception as exc:
            detail = str(exc) or exc.__class__.__name__
            self.failed.emit(detail)
            return
        self.succeeded.emit(result)


class TaskRunner(QObject):
    """Runs one :class:`Task` at a time and keeps it alive for the owner.

    The window holds a runner per page; it disables the page's controls while
    busy and reports failures through ``on_error`` instead of a traceback.
    """

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._task: Optional[Task] = None

    @property
    def busy(self) -> bool:
        return self._task is not None

    def start(
        self,
        fn: TaskFn,
        *args: Any,
        on_progress: Optional[Callable[[int, str], None]] = None,
        on_success: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_finished: Optional[Callable[[], None]] = None,
        **kwargs: Any,
    ) -> bool:
        """Start ``fn`` unless a task is already running. Returns True if started."""
        if self.busy:
            return False
        task = Task(fn, *args, **kwargs)
        task.progressed.connect(on_progress or (lambda _percent, _message: None))
        task.succeeded.connect(on_success or (lambda _result: None))
        task.failed.connect(on_error or (lambda _message: None))
        task.finished.connect(on_finished or (lambda: None))
        task.finished.connect(self._forget)
        self._task = task
        task.start()
        return True

    def _forget(self) -> None:
        self._task = None
