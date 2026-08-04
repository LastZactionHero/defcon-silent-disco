"""Host-side shim: import the REAL firmware modules on desktop CPython.

Stubs just enough of MicroPython (machine, micropython, time.ticks_*) that
disco/irsync/wavplayer import unchanged.  Time is a controllable fake so tests
can simulate ISR timing exactly.

Usage:
    from hostshim import fw          # fw.disco, fw.irsync, fw.wavplayer, ...
    from hostshim import clock       # clock.us = 12345 ; advances ticks_us()
"""
import sys
import os
import time
import types
import builtins

_FW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _FW)


class _Clock:
    """Settable time source backing time.ticks_us/ms."""
    def __init__(self):
        self.us = 0

    @property
    def ms(self):
        return self.us // 1000

    @ms.setter
    def ms(self, v):
        self.us = v * 1000


clock = _Clock()

time.ticks_us = lambda: clock.us
time.ticks_ms = lambda: clock.us // 1000
time.ticks_diff = lambda a, b: a - b
time.ticks_add = lambda a, b: a + b
time.sleep_us = lambda us: None
time.sleep_ms = lambda ms: None

for _t in ("ptr8", "ptr16", "ptr32", "uint"):
    setattr(builtins, _t, int)


class Pin:
    IN = 0; OUT = 1; PULL_UP = 2; PULL_DOWN = 3
    IRQ_RISING = 1; IRQ_FALLING = 2
    MONO = 0; STEREO = 1; TX = 2

    def __init__(self, *a, **k):
        self._value = 1

    def value(self, *a):
        if a:
            self._value = a[0]
            return None
        return self._value

    def irq(self, *a, **k):
        pass


class _Anything:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


class _Mem:
    def __init__(self):
        self.data = {}

    def __getitem__(self, k):
        return self.data.get(k, 0)

    def __setitem__(self, k, v):
        self.data[k] = v


_machine = types.ModuleType("machine")
_machine.Pin = Pin
_machine.PWM = _Anything
_machine.SPI = _Anything
_machine.I2S = Pin          # class attrs MONO/STEREO/TX; never instantiated in tests
_machine.mem32 = _Mem()
_machine.freq = lambda *a: 276_000_000
_machine.reset = lambda: (_ for _ in ()).throw(SystemExit("machine.reset"))
_machine.unique_id = lambda: b"\x00" * 8
_machine.bootloader = lambda: None
sys.modules["machine"] = _machine

_mp = types.ModuleType("micropython")
_mp.const = lambda x: x
_mp.viper = lambda f: f
_mp.native = lambda f: f
_mp.alloc_emergency_exception_buf = lambda n: None
sys.modules["micropython"] = _mp


class _FW_NS:
    """Lazy namespace: fw.disco etc. import on first touch."""
    def __getattr__(self, name):
        mod = __import__(name)
        setattr(self, name, mod)
        return mod


fw = _FW_NS()
