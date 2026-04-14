"""
Sensor monitoring using LibreHardwareMonitorLib.dll
Centralizado como única fuente de datos para el proyecto.
"""

import os
import threading
import time
import clr

# Carga de DLL de Libre Hardware Monitor
try:
    clr.AddReference(r"dll\LibreHardwareMonitorLib")
    from LibreHardwareMonitor.Hardware import Computer
except Exception as e:
    print(f"[Sensors] Error cargando DLL: {e}")

_latest_sensor_data = {
    # --- CPU
    "cpu_usage": 0, "cpu_temp": 0, "cpu_power": 0, "cpu_clocks": [],
    # --- GPU
    "gpu_usage": 0, "gpu_temp": 0, "gpu_fan": 0, "gpu_power": 0, "gpu_clocks": [], # 🔥 Corregido: decía cpu_usage aquí
    # --- Super I/o
    "aio_pump": 0, "ram_usage": 0, "ram_used": 0, "ram_available": 0,
    "net_download": 0, "net_upload": 0, "system_fans": []
}

_sensor_data_lock = threading.Lock()
_sensor_thread_running = False
_sensor_thread = None
_time_loop = 1
_pc_instance = None

def init_sensors():
    """Inicializa la DLL y arranca el hilo de recolección."""
    global _sensor_thread_running, _sensor_thread, _pc_instance
    if _sensor_thread_running: 
        return
    
    try:
        _pc_instance = Computer()
        _pc_instance.IsCpuEnabled = True
        _pc_instance.IsGpuEnabled = True
        _pc_instance.IsMemoryEnabled = True
        _pc_instance.IsMotherboardEnabled = True
        _pc_instance.IsNetworkEnabled = True
        _pc_instance.Open()
        
        _sensor_thread_running = True
        _sensor_thread = threading.Thread(target=_update_loop, daemon=True)
        _sensor_thread.start()
        print("[Sensors] Monitoreo LHM iniciado correctamente.")
    except Exception as e:
        print(f"[Sensors] Fallo al iniciar LHM: {e}")

def _update_loop():
    """Hilo en segundo plano que actualiza _latest_sensor_data."""
    global _latest_sensor_data, _pc_instance
    
    while _sensor_thread_running:
        if _pc_instance is None:
            time.sleep(1)
            continue
            
        temp_data = _latest_sensor_data.copy()
        
        # 🔥 CRÍTICO: Limpiar TODAS las listas dinámicas aquí para evitar NameErrors y duplicados
        temp_data["system_fans"] = [] 
        temp_data["cpu_clocks"] = [] 
        temp_data["gpu_clocks"] = [] 
        temp_data["net_upload"] = 0
        temp_data["net_download"] = 0

        try:
            def extract_sensors(hardware_item):
                hardware_item.Update()
                hw_type = str(hardware_item.HardwareType)
                
                for sensor in hardware_item.Sensors:
                    sensor_type = str(sensor.SensorType)
                    name = str(sensor.Name).lower()
                    val = sensor.Value or 0

                    # --- CPU ---
                    if hw_type == 'Cpu':
                        if sensor_type == 'Temperature':
                            if 'package' in name or 'tctl' in name or 'tctl/tdie' in name:
                                temp_data["cpu_temp"] = val
                            elif temp_data.get("cpu_temp", 0) == 0 and 'core' in name:
                                temp_data["cpu_temp"] = val

                        elif sensor_type == 'Load' and 'total' in name:
                            temp_data["cpu_usage"] = val

                        elif sensor_type == 'Power' and 'package' in name:
                            temp_data["cpu_power"] = val

                        elif sensor_type == 'Clock':
                            temp_data["cpu_clocks"].append({
                                "name": sensor.Name,
                                "value": val
                            })

                    # --- GPU ---
                    elif 'Gpu' in hw_type:
                        if sensor_type == 'Temperature' and 'core' in name:
                            temp_data["gpu_temp"] = val

                        elif sensor_type == 'Load' and 'core' in name:
                            temp_data["gpu_usage"] = val

                        elif sensor_type == 'Power':
                            temp_data["gpu_power"] = val

                        elif sensor_type == 'Fan':
                            temp_data["gpu_fan"] = val

                        elif sensor_type == 'Clock':
                            temp_data["gpu_clocks"].append({
                                "name": sensor.Name,
                                "value": val
                            })
                            
                    # --- RAM ---
                    elif hw_type == 'Memory':
                        if sensor_type == 'Load':
                            temp_data["ram_usage"] = val
                        elif sensor_type == 'Data' and 'used' in name:
                            temp_data["ram_used"] = val
                        elif sensor_type == 'Data' and 'available' in name:
                            temp_data["ram_available"] = val

                    # --- MOTHERBOARD & SUPER I/O (Ventiladores) ---
                    elif hw_type in ['Motherboard', 'SuperIO']:
                        if sensor_type == 'Fan':
                            temp_data["system_fans"].append({
                                "name": str(sensor.Name), 
                                "value": val
                            })
                                
                    # --- NETWORK (Red) ---
                    elif hw_type == 'Network':
                        if sensor_type == 'Throughput':
                            mb_s = val / 1048576.0
                            if 'upload' in name:
                                temp_data["net_upload"] += mb_s
                            elif 'download' in name:
                                temp_data["net_download"] += mb_s

                for sub_hw in hardware_item.SubHardware:
                    extract_sensors(sub_hw)

            for hardware in _pc_instance.Hardware:
                extract_sensors(hardware)

        except Exception as e:
            pass 

        with _sensor_data_lock:
            _latest_sensor_data = temp_data
            
        time.sleep(_time_loop)

def get_cached_sensors():
    """Devuelve una copia segura de los datos actuales. Usar en la UI."""
    with _sensor_data_lock:
        return _latest_sensor_data.copy()

def stop_sensors():
    """Detiene el hilo y libera la DLL."""
    global _sensor_thread_running, _pc_instance
    print("[Sensors] Deteniendo monitoreo...")
    _sensor_thread_running = False
    if _pc_instance:
        _pc_instance.Close()
        _pc_instance = None


# --- NUEVA FUNCIÓN DE DEBUG ---
def debug_print_sensors():
    data = get_cached_sensors()
    
    import os 
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print("=== DEBUG DE SENSORES (LHM) ===")
    for key, value in data.items():
        # Ignoramos las listas para imprimirlas bonito más abajo
        if key not in ["system_fans", "cpu_clocks", "gpu_clocks"]:
            val_seguro = value if value is not None else 0
            status = "✅" if val_seguro > 0 else "❌"
            print(f"{status} {key.ljust(20)}: {value}")
    
    print("\n--- RELOJES DE CPU ---")
    for clock in data.get("cpu_clocks", []):
        print(f"⏱️ {clock['name'].ljust(15)}: {clock['value']:.1f} MHz")
        
    print("\n--- RELOJES DE GPU ---")
    for clock in data.get("gpu_clocks", []):
        print(f"⏱️ {clock['name'].ljust(15)}: {clock['value']:.1f} MHz")

    print("\n--- VENTILADORES DEL SISTEMA ---")
    sys_fans = data.get("system_fans", [])
    if sys_fans:
        for fan in sys_fans:
            print(f"💨 {fan['name'].ljust(15)}: {fan['value']} RPM")
    else:
        print("❌ No se detectaron ventiladores de sistema extra.")
    print("================================")


class SensorManager:
    def __init__(self):
        self.critical_sensors = ["cpu_temp", "gpu_temp"]
        self.max_retries = 5  # 5 intentos x 3 segundos = 15 segundos máximo de espera
        self.retry_delay = 3 

    def check_system_readiness(self):
        """
        Scans for sensors. Returns an empty list if all are found.
        Returns a list of missing sensor names if the timeout is reached.
        """
        print("[SensorManager] Starting sensor validation sequence...")
        
        for attempt in range(1, self.max_retries + 1):
            current_readings = get_cached_sensors() 
            failed_sensors = []
            
            for sensor in self.critical_sensors:
                value = current_readings.get(sensor, 0)
                if value is None or value <= 0:
                    failed_sensors.append(sensor)
            
            if not failed_sensors:
                print(f"[SensorManager] Success: All critical sensors are online.")
                return [] # Retorna lista vacía (Todo bien)
            
            print(f"[SensorManager] Attempt {attempt}/{self.max_retries}: Waiting for {failed_sensors}...")
            if attempt < self.max_retries:
                time.sleep(self.retry_delay)
        
        # Si el bucle termina, significa que se agotó el tiempo y faltan sensores
        self.report_initialization_error(failed_sensors)
        return failed_sensors # Retorna los que fallaron

    def report_initialization_error(self, failed_sensors):
        error_message = f"Timeout reached. Missing sensors: {', '.join(failed_sensors)}"
        print(f"[SensorManager] WARNING: {error_message}")


# --- PRUEBA DIRECTA ---
if __name__ == "__main__":
    print("[Test] Arrancando prueba de sensores...")
    init_sensors() # Quitamos el 'if'
    
    # Damos 2 segundos para que la DLL despierte y lea la placa base
    import time
    time.sleep(_time_loop) 
    
    try:
        while True:
            debug_print_sensors()
            time.sleep(_time_loop)
    except KeyboardInterrupt:
        print("\n[Test] Prueba cancelada por el usuario.")
        stop_sensors()