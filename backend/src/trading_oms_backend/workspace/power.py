"""Windows sleep inhibition is scoped to the engine's owning thread."""

import ctypes
import os


class SleepGuard:
    def __init__(self):
        self.active = False

    def set(self, required):
        if required == self.active:
            return
        if os.name == "nt":
            api = ctypes.WinDLL("kernel32", use_last_error=True)
            api.SetThreadExecutionState.argtypes = [ctypes.c_uint32]
            api.SetThreadExecutionState.restype = ctypes.c_uint32
            if not api.SetThreadExecutionState(0x80000001 if required else 0x80000000):
                raise ValueError(
                    "Windows could not prevent sleep while the trading engine is active."
                )
        self.active = required
