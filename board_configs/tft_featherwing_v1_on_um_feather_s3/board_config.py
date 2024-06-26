""" 3.5" TFT Featherwing V1 on Unexpected Maker Feather S3 """

from lcd_bus import SPIBus
from hx8357 import HX8357
from machine import Pin
# from stmpe610 import STMPE610_SPI # TODO: port from https://github.com/adafruit/Adafruit_CircuitPython_STMPE610


display_bus = SPIBus(
    dc=3,
    cs=1,
    mosi=35,
    miso=37,
    sclk=36,
    host=1,
    tx_only=True,
    freq=60_000_000,
    spi_mode=0,
    cmd_bits=8,
    param_bits=8,
    lsb_first=False,
    dc_low_on_data=False,
    cs_high_active=False,
)

display_drv = HX8357(
    display_bus,
    width=320,
    height=480,
    colstart=0,
    rowstart=0,
    rotation=0,
    mirrored=True,
    color_depth=16,
    bgr=True,
    reverse_bytes_in_word=True,
    invert=True,
    brightness=1.0,
    backlight_pin=None,
    backlight_on_high=True,
    reset_pin=None,
    reset_high=True,
    power_pin=None,
    power_on_high=True,
)

# Note Touch_CS = 38
