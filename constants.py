"""
Constants and configuration for Thermal Engine.
"""

from PySide6.QtCore import Qt

from sensors import get_cached_sensors

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



def get_data_sources_categorized():
    """
    Construye las opciones del menú basándose en el hardware REAL
    capturado por Libre Hardware Monitor en sensors.py.
    Estructura: (ID_interno, Nombre_a_mostrar, Tipo_de_dato, Unidad)
    """
    # 1. Leer los datos reales actuales
    data = get_cached_sensors()
    
    # 2. Construir la base con los sensores que SIEMPRE tienen un solo valor
    sources = {
        "General": [
            ("static", "Static Text (None)", "static", ""),
        ],
        "CPU": [
            ("cpu_usage", "CPU Usage", "percent", "%"),
            ("cpu_temp", "CPU Temp", "temp", "°C"),
            ("cpu_power", "CPU Power", "power", " W"),
        ],
        "GPU": [
            ("gpu_usage", "GPU Usage", "percent", "%"), 
            ("gpu_temp", "GPU Temp", "temp", "°C"),
            ("gpu_power", "GPU Power", "power", " W"),
            ("gpu_fan", "GPU Fan", "speed", " RPM"),
        ],
        "Memory": [
            ("ram_usage", "RAM Usage", "percent", "%"),
            ("ram_used", "RAM Used", "size", " GB"),
            ("ram_available", "RAM Available", "size", " GB"),
        ],
        "Network": [
            ("net_upload", "Upload Speed", "net_speed", " MB/s"),
            ("net_download", "Download Speed", "net_speed", " MB/s"),
        ],
        "System Fans": []
    }

    # 3. INYECCIÓN DINÁMICA: Añadir los arrays con sus NOMBRES REALES
    
    # --- Relojes de CPU ---
    for i, clock in enumerate(data.get("cpu_clocks", [])):
        sources["CPU"].append(
            # ID: cpu_clock_0 | Nombre Real: "Clock: Core #1"
            (f"cpu_clock_{i}", f"Clock: {clock['name']}", "clock", " MHz")
        )

    # --- Relojes de GPU ---
    for i, clock in enumerate(data.get("gpu_clocks", [])):
        sources["GPU"].append(
            # ID: gpu_clock_0 | Nombre Real: "Clock: GPU Core"
            (f"gpu_clock_{i}", f"Clock: {clock['name']}", "clock", " MHz")
        )

    # --- Ventiladores del Sistema ---
    for i, fan in enumerate(data.get("system_fans", [])):
        sources["System Fans"].append(
            # ID: sys_fan_0 | Nombre Real: "Fan: Chassis Fan 1"
            (f"sys_fan_{i}", f"Fan: {fan['name']}", "speed", " RPM")
        )

    # 4. Limpieza: Si la PC no tiene ventiladores de sistema extra, borramos la categoría
    if not sources["System Fans"]:
        del sources["System Fans"]

    return sources


# ==========================================
# SOURCE UNITS (Diccionario Inteligente)
# ==========================================

class _SmartUnitsDict(dict):
    """
    Actúa como un diccionario normal, pero devuelve la estructura completa
    {"symbol": " unidad", "type": "tipo_de_dato"} que canvas.py espera recibir.
    """
    def get(self, key, default=None):
        if default is None:
            default = {"symbol": "", "type": "static"}
            
        if not key: return default
        if "clock" in key: return {"symbol": " MHz", "type": "clock"}
        if "fan" in key or "pump" in key: return {"symbol": " RPM", "type": "speed"}
        
        return super().get(key, default)

    def __getitem__(self, key):
        if not key: return {"symbol": "", "type": "static"}
        if "clock" in key: return {"symbol": " MHz", "type": "clock"}
        if "fan" in key or "pump" in key: return {"symbol": " RPM", "type": "speed"}
        
        return super().__getitem__(key)

# Inicializamos el diccionario con los valores y tipos originales
SOURCE_UNITS = _SmartUnitsDict({
    "cpu_usage": {"symbol": "%", "type": "percent"}, 
    "cpu_temp": {"symbol": "°C", "type": "temp"}, 
    "cpu_power": {"symbol": " W", "type": "power"}, 
    "gpu_usage": {"symbol": "%", "type": "percent"}, 
    "gpu_temp": {"symbol": "°C", "type": "temp"}, 
    "gpu_power": {"symbol": " W", "type": "power"}, 
    "ram_usage": {"symbol": "%", "type": "percent"}, 
    "ram_used": {"symbol": " GB", "type": "size"}, 
    "ram_available": {"symbol": " GB", "type": "size"},
    "net_upload": {"symbol": " MB/s", "type": "net_speed"}, 
    "net_download": {"symbol": " MB/s", "type": "net_speed"},
    "static": {"symbol": "", "type": "static"}
})

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