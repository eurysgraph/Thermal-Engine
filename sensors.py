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

# Fuente única de verdad. Los nombres DEBEN coincidir con constants.py
_latest_sensor_data = {
    "cpu_percent": 0, "cpu_temp": 0, "cpu_power": 0, "cpu_fan": 0,
    "gpu_percent": 0, "gpu_temp": 0, "gpu_fan": 0, "gpu_power": 0,
    "aio_pump": 0, "ram_percent": 0, "ram_used": 0, "ram_available": 0,
    "net_download": 0, "net_upload": 0, "system_fans": []
}

_sensor_data_lock = threading.Lock()
_sensor_thread_running = False
_sensor_thread = None
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
        # Limpiamos la lista de ventiladores y network en cada ciclo para que no se dupliquen
        temp_data["system_fans"] = [] 
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
                            # Cubre Intel ('package') y AMD ('tctl', 'tdie', 'ccd')
                            if 'package' in name or 'tctl' in name or 'ccd' in name:
                                temp_data["cpu_temp"] = val
                            # Fallback de seguridad si tiene otro nombre raro
                            elif temp_data.get("cpu_temp", 0) == 0 and 'core' in name:
                                temp_data["cpu_temp"] = val
                                
                        elif sensor_type == 'Load' and 'total' in name:
                            temp_data["cpu_percent"] = val
                        elif sensor_type == 'Power' and 'package' in name:
                            temp_data["cpu_power"] = val

                    # --- GPU ---
                    elif 'Gpu' in hw_type:
                        if sensor_type == 'Temperature' and 'core' in name:
                            temp_data["gpu_temp"] = val
                        elif sensor_type == 'Load' and 'core' in name:
                            temp_data["gpu_percent"] = val
                        elif sensor_type == 'Power': 
                            temp_data["gpu_power"] = val
                        elif sensor_type == 'Fan':
                            temp_data["gpu_fan"] = val
                            
                    # --- RAM ---
                    elif hw_type == 'Memory':
                        if sensor_type == 'Load':
                            temp_data["ram_percent"] = val
                        elif sensor_type == 'Data' and 'used' in name:
                            temp_data["ram_used"] = val
                        elif sensor_type == 'Data' and 'available' in name:
                            temp_data["ram_available"] = val

                    # --- MOTHERBOARD & SUPER I/O (Ventiladores) ---
                    elif hw_type in ['Motherboard', 'SuperIO']:
                        if sensor_type == 'Fan':
                            if 'pump' in name or 'aio' in name or 'opt' in name:
                                temp_data["aio_pump"] = val
                            elif 'cpu' in name:
                                temp_data["cpu_fan"] = val
                            else:
                                # Cualquier otro ventilador va a la lista de sistema
                                temp_data["system_fans"].append({
                                    "name": str(sensor.Name), 
                                    "value": val
                                })
                    # --- NETWORK (Red) ---
                    elif hw_type == 'Network':
                        if sensor_type == 'Throughput':
                            # LHM devuelve Bytes/s. Dividimos entre (1024 * 1024) para obtener MB/s
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
            
        time.sleep(1)

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
    # """Imprime todas las variables actuales para verificar lecturas."""
    data = get_cached_sensors()
    
    # Importar os aquí por si no estaba arriba
    import os 
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print("=== DEBUG DE SENSORES (LHM) ===")
    for key, value in data.items():
        if key != "system_fans":
            # Protegemos contra valores 'None'
            val_seguro = value if value is not None else 0
            status = "✅" if val_seguro > 0 else "❌"
            print(f"{status} {key.ljust(20)}: {value}")
    
    print("\n--- VENTILADORES DEL SISTEMA ---")
    # Usamos .get() para que no de error si la llave no existe
    sys_fans = data.get("system_fans") 
    if sys_fans:
        for fan in sys_fans:
            print(f"✅ {fan['name'].ljust(20)}: {fan['value']} RPM")
    else:
        print("❌ No se detectaron ventiladores agrupados en 'system_fans'")
    print("================================")

# --- PRUEBA DIRECTA ---
if __name__ == "__main__":
    print("[Test] Arrancando prueba de sensores...")
    init_sensors() # Quitamos el 'if'
    
    # Damos 2 segundos para que la DLL despierte y lea la placa base
    import time
    time.sleep(2) 
    
    try:
        while True:
            debug_print_sensors()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Test] Prueba cancelada por el usuario.")
        stop_sensors()