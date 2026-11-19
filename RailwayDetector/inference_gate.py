"""FIFO model access, with cancellable waiters and bounded per-task work."""
from collections import deque
from contextlib import contextmanager
import threading
import time

class FairInferenceGate:
    def __init__(self):
        self.condition=threading.Condition();self.waiters=deque();self.busy=False
    @contextmanager
    def hold(self,stop=None,cancelled=InterruptedError):
        token=object();started=time.monotonic()
        with self.condition:
            self.waiters.append(token)
            try:
                while self.busy or self.waiters[0] is not token:
                    if stop is not None and stop.is_set():raise cancelled('inference cancelled')
                    self.condition.wait(.05)
                if stop is not None and stop.is_set():raise cancelled('inference cancelled')
                self.busy=True
            finally:
                self.waiters.remove(token);self.condition.notify_all()
        try:yield time.monotonic()-started
        finally:
            with self.condition:self.busy=False;self.condition.notify_all()
