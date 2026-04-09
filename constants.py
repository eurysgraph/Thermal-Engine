"""
Constants and configuration for Thermal Engine.
"""

from PySide6.QtCore import Qt

# Display dimensions
DISPLAY_WIDTH = 1280
DISPLAY_HEIGHT = 480
PREVIEW_SCALE = 0.5

# Base element types available in the editor
_BASE_ELEMENT_TYPES = [
    "circle_gauge", "bar_gauge", "text", "rectangle",
    "clock", "analog_clock", "image",
]

ELEMENT_TYPES = _BASE_ELEMENT_TYPES.copy()

def register_custom_element_types(custom_types):
    global ELEMENT_TYPES
    ELEMENT_TYPES = _BASE_ELEMENT_TYPES + list(custom_types)

# Categorías y variables unificadas (Los IDs deben ser iguales a sensors.py)
DATA_SOURCES_CATEGORIZED = {
    "General": [
        ("static", "Static Text (None)", "static", ""),
    ],
    # ----------------------------------------------
    "CPU": [
        ("cpu_percent", "CPU Usage", "percent", "%"),
        ("cpu_temp", "CPU Temp", "temp", "°C"),
        ("cpu_power", "CPU Power", "power", " W"),
        ("cpu_clock", "CPU Clock", "clock", " MHz"),
        ("cpu_fan", "CPU Fan", "speed", " RPM"),
        ("aio_pump", "AIO Pump", "speed", " RPM"),
    ],
    # ----------------------------------------------
    "GPU": [
        ("gpu_percent", "GPU Usage", "percent", "%"),
        ("gpu_temp", "GPU Temp", "temp", "°C"),
        ("gpu_clock", "GPU Clock", "clock", " MHz"),
        ("gpu_power", "GPU Power", "power", " W"),
        ("gpu_fan", "GPU Fan", "speed", " RPM"),
    ],
    # ----------------------------------------------
    "Memory": [
        ("ram_percent", "RAM Usage", "percent", "%"),
        ("ram_used", "RAM Used", "size", " GB"),
        ("ram_available", "RAM Available", "size", " GB"),
    ],
    # ----------------------------------------------
    "Network": [
        ("net_upload", "Upload Speed", "net_speed", " MB/s"),
        ("net_download", "Download Speed", "net_speed", " MB/s"),
    ],
    # ----------------------------------------------
    "System Fans": [
        (f"sys_fan_{i}", f"Sys Fan {i}", "speed", " RPM") for i in range(1, 7)
    ]
}

# Lookup for source units (Usado por main_window.py para dibujar)
SOURCE_UNITS = {}
for category, sources in DATA_SOURCES_CATEGORIZED.items():
    for source_id, name, unit_type, unit_symbol in sources:
        SOURCE_UNITS[source_id] = {
            "name": name,
            "type": unit_type,
            "symbol": unit_symbol
        }

# Lista plana para compatibilidad con código anterior
DATA_SOURCES = list(SOURCE_UNITS.keys())

# Default properties
DEFAULT_ELEMENT_PROPS = {
    "circle_gauge": {"radius": 120, "x": 200, "y": 240, "text": "GAUGE"},
    "bar_gauge": {"width": 300, "height": 30, "x": 100, "y": 100, "text": "BAR"},
    "text": {"x": 100, "y": 100, "text": "TEXT", "size": 24, "color": "#ffffff"},
    "rectangle": {"width": 100, "height": 100, "x": 100, "y": 100, "color": "#ff0000"},
}

def get_value_with_unit(value, source, temp_hide_unit=False):
    """Función centralizada de formateo (Sin decimales en fans/clocks)."""
    if value is None: value = 0
    unit_info = SOURCE_UNITS.get(source, {"symbol": "", "type": "percent"})
    symbol = unit_info["symbol"]
    u_type = unit_info["type"]

    # --- CAMBIO AQUÍ: Permitimos 1 decimal para la RAM y la Red ---
    fmt = ".1f" if u_type in ["size", "net_speed"] else ".0f"
    
    if u_type == "temp" and temp_hide_unit:
        return f"{value:{fmt}}"
    return f"{value:{fmt}}{symbol}"