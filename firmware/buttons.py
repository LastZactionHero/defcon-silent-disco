"""
Debounced button reader for the badge's four active-low buttons.

Poll-based (call .poll() on a fixed cadence, e.g. every 20 ms).  Returns a
list of event strings.  Supports auto-repeat for held buttons (handy for
volume) via the `repeat` set.

Buttons are active-low with internal pull-ups: value()==0 means pressed.
"""

import time
from machine import Pin


class Buttons:
    def __init__(self, pin_map, debounce_ms=25, repeat_ms=180, repeat_after_ms=450):
        """
        pin_map: {event_name: gpio_number}
        repeat:  set of event_names that should auto-repeat while held
        """
        self._pins = {name: Pin(gp, Pin.IN, Pin.PULL_UP) for name, gp in pin_map.items()}
        self._stable = {name: 1 for name in pin_map}     # last debounced level
        self._raw = {name: 1 for name in pin_map}        # last raw level
        self._t_change = {name: 0 for name in pin_map}   # last raw transition (ms)
        self._t_repeat = {name: 0 for name in pin_map}   # next repeat time (ms)
        self.debounce_ms = debounce_ms
        self.repeat_ms = repeat_ms
        self.repeat_after_ms = repeat_after_ms
        self.repeat = set()

    def poll(self):
        events = []
        now = time.ticks_ms()
        for name, pin in self._pins.items():
            v = pin.value()
            # track raw transitions for debounce timing
            if v != self._raw[name]:
                self._raw[name] = v
                self._t_change[name] = now
            # accept a new stable level once it has held past debounce window
            if v != self._stable[name] and time.ticks_diff(now, self._t_change[name]) >= self.debounce_ms:
                self._stable[name] = v
                if v == 0:  # pressed (falling edge)
                    events.append(name)
                    self._t_repeat[name] = time.ticks_add(now, self.repeat_after_ms)
            # auto-repeat while held down
            if self._stable[name] == 0 and name in self.repeat:
                if time.ticks_diff(now, self._t_repeat[name]) >= 0:
                    events.append(name)
                    self._t_repeat[name] = time.ticks_add(now, self.repeat_ms)
        return events

    def pressed(self, name):
        """Instantaneous debounced state: True if currently held."""
        return self._stable.get(name, 1) == 0
