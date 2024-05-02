from micropython import const
from ._events import Events


_DEFAULT_TOUCH_ROTATION_TABLE = (0b000, 0b101, 0b110, 0b011)

SWAP_XY = const(0b001)
REVERSE_X = const(0b010)
REVERSE_Y = const(0b100)


class Devices:
    UNKNOWN = const(-1)  # Unknown device
    MULTI = const(0x00)  # Multi-device - all events in Events.types unless specified
    TOUCH = const( 0x01)  # MOUSEBUTTONDOWN when touched, MOUSEMOTION when moved, MOUSEBUTTONUP when released
    ENCODER = const(0x02)  # MOUSEWHEEL events when turned, MOUSEBUTTONDOWN when pressed
    KEYPAD = const(0x03)  # KEYDOWN and KEYUP events when keys are pressed or released
    JOYSTICK = const(0x04)  # Joystick Events (not implemented)

    @staticmethod
    def create(type, *args, **kwargs):
        if type == Devices.MULTI:
            return MultiDevice(*args, **kwargs)
        if type == Devices.TOUCH:
            return TouchDevice(*args, **kwargs)
        elif type == Devices.ENCODER:
            return EncoderDevice(*args, **kwargs)
        elif type == Devices.KEYPAD:
            return KeypadDevice(*args, **kwargs)
        elif type == Devices.JOYSTICK:
            return JoystickDevice(*args, **kwargs)
        else:
            raise ValueError("Unknown device type")


class _Device:
    type = Devices.UNKNOWN

    def __init__(self, read, data=None, read2=None, data2=None, *, display=None):
        self._read = read
        self._data = data
        self._read2 = read2 if read2 else lambda: None
        self._data2 = data2
        self._display = display

        self._state = None
        self._user_data = None  # Can be set and retrieved by apps such as lv_mpdisplay
        self._read_cb = None  # Read callback - can be set by apps such as lv_mpdisplay

    def set_read_cb(self, callback):
        if callable(callback):
            self._read_cb = callback
        else:
            raise ValueError("callback must be callable")

    def read_cb(self, *args):
        """
        Used by lv_mpdisplay or other applications to call the saved _read_cb with the current reading
        and optional arguments.
        """
        if self._read_cb:
            self._read_cb(self.read(), *args)

    @property
    def user_data(self):
        return self._user_data

    @user_data.setter
    def user_data(self, value):
        self._user_data = value

    @property
    def display(self):
        return self._display

    @display.setter
    def display(self, disp):
        self._display = disp
        if disp is not None and self.type == Devices.TOUCH:
            self.rotation = disp.rotation


class MultiDevice(_Device):
    type = Devices.MULTI

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._data is None:
            self._data = Events.types

    def read(self):
        if (event := self._read()) is not None:
            if event.type in self._data:
                return event
        return None


class TouchDevice(_Device):
    """
    Only reports mouse button 1.
    """

    type = Devices.TOUCH

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._data is None:  # self._data is a rotation table
            self._data = _DEFAULT_TOUCH_ROTATION_TABLE

        self.rotation = self._display.rotation if self._display else 0

    @property
    def rotation(self):
        return self._rotation

    @rotation.setter
    def rotation(self, value):
        self._rotation = value % 360

        # _mask is an integer from 0 to 7 (or 0b001 to 0b111, 3 bits)
        # Currently, bit 2 = invert_y, bit 1 is invert_x and bit 0 is swap_xy, but that may change.
        self._mask = self._data[self._rotation // 90]

    def read(self):
        # _read should return None, a point as a tuple (x, y), a point as a list [x, y] or
        # a tuple / list of points ((x1, y1), (x2, y2)), [(x1, y1), (x2, y2)], ([x1, y1], [x2, y2]),
        # or [[x1, y1], [x2, y2]].  If it doesn't, create a wrapper around your driver's read function
        # and set touch_callback to that wrapper, or subclass TouchDriver and override .get_touched()
        # with your own logic.  A point tuple/list may have additional values other than x and y that
        # are ignored.  x and y must come first.  Some multi-touch drivers may return extra data such
        # as the index of the touch point (1st, 2nd, etc).  Only the first point in the list will be
        # used and any extra data in that point will be ignored.

        try:  # If called too quickly, the touch driver may raise OSError: [Errno 116] ETIMEDOUT
            touched = self._read()
        except OSError:
            return None
        if touched:
            last_pos = self._state
            # If it looks like a point, use it, otherwise get the first point out of the list / tuple
            (x, y, *_) = touched if isinstance(touched[0], int) else touched[0]

            if self._mask & SWAP_XY:
                x, y = y, x
            if self._mask & REVERSE_X:
                x = self._display.width - x - 1
            if self._mask & REVERSE_Y:
                y = self._display.height - y - 1
            self._state = (x, y)
            if last_pos is not None:
                last_x, last_y = last_pos
                return Events.Motion(
                    Events.MOUSEMOTION,
                    self._state,
                    (x - last_x, y - last_y),
                    (1, 0, 0),
                    False,
                    None,
                )
            else:
                return Events.Button(Events.MOUSEBUTTONDOWN, self._state, 1, False, None)
        elif self._state is not None:
            last_pos = self._state
            self._state = None
            return Events.Button(Events.MOUSEBUTTONUP, last_pos, 1, False, None)
        return None


class EncoderDevice(_Device):
    type = Devices.ENCODER

    def __init__(self, *args, **kwargs):
        """
        self._data is the mouse button number to report for the switch.
        Default is 2 (middle mouse button).  If the mouse button number is even,
        the wheel will report vertical (y) movement.  If the mouse button number is odd,
        the wheel will report horizontal (x) movement.  This corresponds to a typical mouse
        wheel being button 2 and the wheel moving vertically.  It also correponds to
        scrolling horizontally on a touchpad with two-finger scrolling and using the right button.
        """
        super().__init__(*args, **kwargs)
        self._state = (0, False)  # (position, pressed)
        self._data = self._data if self._data else 2  # Default to middle mouse button

    def read(self):
        # _read should return a running total of steps turned.  For instance, if the current
        # position is 800 and it is moved 5 right then 3 left, the callback should return 802.
        # The event returned will have the delta, 2 in this example.
        # _read2 should also be callable and return truthy if the switch is pressed,
        # falsy if it is not.
        last_pos, last_pressed = self._state
        pressed = self._read2()
        if pressed != last_pressed:
            self._state = (last_pos, pressed)
            return Events.Button(
                Events.MOUSEBUTTONDOWN if pressed else Events.MOUSEBUTTONUP,
                (0, 0),
                self._data,
                False,
                None,
            )

        pos = self._read()
        if pos != last_pos:
            steps = pos - last_pos
            self._state = (pos, last_pressed)
            if self._data % 2 == 0:
                return Events.Wheel(Events.MOUSEWHEEL, False, 0, steps, 0, steps, False, None)
            return Events.Wheel(Events.MOUSEWHEEL, False, steps, 0, steps, 0, False, None)
        return None


class KeypadDevice(_Device):
    type = Devices.KEYPAD

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._state = set()

    def read(self):
        # _read should return a list, tuple or set of keys pressed or None if no keys are pressed.
        # The keys should be integers representing the key code.  The callback should return
        # all keys currently pressed.  If a key is held down, it should be returned in every call to
        # the callback until it is released.
        # For example, see https://github.com/adafruit/Adafruit_CircuitPython_MatrixKeypad
        keys = set(self._read())
        released = self._state - keys
        if released:
            key = released.pop()
            self._state.remove(key)
            return Events.Key(Events.KEYUP, chr(key), key, 0, 0)
        pressed = keys - self._state
        if pressed:
            key = pressed.pop()
            self._state.add(key)
            return Events.Key(Events.KEYDOWN, chr(key), key, 0, 0)
        return None


class JoystickDevice(_Device):
    type = Devices.JOYSTICK

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def read(self):
        raise NotImplementedError("JoystickDevice.read() not implemented")
