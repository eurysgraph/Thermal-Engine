import json
import os
import threading
import time
import random
from openrgb import OpenRGBClient
from openrgb.utils import RGBColor

class RGBManager:
    def __init__(self):
        self.config_file = "RGB_Config.json"
        self.client = None
        self.active = False
        
        # 1. PRIMERO definimos los valores por defecto (para que existan en memoria)
        self.current_mode = "static"
        self.colors = [RGBColor(0, 255, 255), RGBColor(255, 255, 255)] 
        self.anim_speed = 3

        # --- NUEVA CAPA: THERMAL REACTION OVERLAY ---
        self.thermal_overlay = {
            "enabled": False,
            "cpu": {
                "warn": 65, "crit": 80,
                "color_warn": [255, 165, 0], "color_crit": [255, 0, 0],
                "devices": [] # Lista de nombres exactos de OpenRGB
            },
            "gpu": {
                "warn": 55, "crit": 75,
                "color_warn": [255, 165, 0], "color_crit": [255, 0, 0],
                "devices": []
            }
        }
        
        # Diccionario para saber qué dispositivos están "secuestrados" por el calor ahora mismo
        self.active_thermal_alerts = {} # ej: {"ASUS TUF Motherboard": RGBColor(255,0,0)}

        # Estados de animación
        self.led_states = {}
        self.anim_thread = None       
        self.stop_anim_flag = threading.Event()
        
        # 5. Finalmente, cargamos el JSON (que puede sobreescribir lo anterior) y conectamos
        self.load_config()
        self.connect()

    def connect(self):
        """Intenta conectar con el servidor de OpenRGB."""
        try:
            self.client = OpenRGBClient("localhost", 6742)
            self.active = True
            print("[RGB Manager] Conectado exitosamente a OpenRGB")
            
            # --- NUEVO: Poner todo en modo directo UNA SOLA VEZ ---
            for device in self.client.devices:
                try:
                    if 'direct' in [m.name.lower() for m in device.modes]:
                        device.set_mode('direct')
                except:
                    pass
            
            # Variable para evitar enviar el mismo color 100 veces por segundo
            self.last_applied_color = None
            self.set_mode(self.current_mode) # Reiniciar la animación base
            
            # Aplicar estado inicial
            # if self.current_mode == "static" and self.colors:
            #     self._apply_color_to_all(self.colors[0])
            # elif self.current_mode in ["starry_night", "rain"]:
            #     self._start_animation_thread()
                
        except Exception as e:
            print(f"[RGB Manager] No se pudo conectar. ¿Está OpenRGB abierto? Error: {e}")
            self.active = False

    def get_device_names(self):
        """NUEVO: Devuelve una lista con los nombres de los dispositivos detectados."""
        if not self.active or not self.client:
            return []
        return [device.name for device in self.client.devices]
    
    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    self.current_mode = data.get("mode", "static")
                    self.anim_speed = data.get("speed", 3) # Cargamos la velocidad
                    # loaded_colors = data.get("colors", [[0, 255, 255]])
                    self.colors = [RGBColor(*c) for c in data.get("colors", [[0, 255, 255]])]

                    # Cargar la capa térmica si existe
                    if "thermal_overlay" in data:
                        self.thermal_overlay = data["thermal_overlay"]

            except Exception as e:
                print(f"[RGB Manager] Error al cargar JSON: {e}")

    def save_config(self):
        try:
            data = {
                "mode": self.current_mode,
                "speed": self.anim_speed, # Guardamos la velocidad
                "colors": [[c.red, c.green, c.blue] for c in self.colors],
                "thermal_overlay": self.thermal_overlay # Guardar configuración térmica
            }
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[RGB Manager] Error al guardar JSON: {e}")
    
    # --- NUEVA LÓGICA TÉRMICA COMO CAPA SUPERIOR ---
    def evaluate_thermal_state(self, current_temps):
        """
        Esta función debe ser llamada desde tu bucle principal de main_window.py
        current_temps debe ser un diccionario: {'cpu': 60.5, 'gpu': 45.0}
        """
        if not self.active or not self.thermal_overlay["enabled"]:
            self.active_thermal_alerts.clear() # Si se apaga, liberar dispositivos
            return

        new_alerts = {}

        # Evaluar CPU
        cpu_t = current_temps.get('cpu', 0)
        cpu_cfg = self.thermal_overlay['cpu']
        if cpu_t >= cpu_cfg['crit']:
            color = RGBColor(*cpu_cfg['color_crit'])
            for dev in cpu_cfg['devices']: new_alerts[dev] = color
        elif cpu_t >= cpu_cfg['warn']:
            color = RGBColor(*cpu_cfg['color_warn'])
            for dev in cpu_cfg['devices']: new_alerts[dev] = color

        # Evaluar GPU (Sobreescribirá a la CPU si comparten dispositivos)
        gpu_t = current_temps.get('gpu', 0)
        gpu_cfg = self.thermal_overlay['gpu']
        if gpu_t >= gpu_cfg['crit']:
            color = RGBColor(*gpu_cfg['color_crit'])
            for dev in gpu_cfg['devices']: new_alerts[dev] = color
        elif gpu_t >= gpu_cfg['warn']:
            color = RGBColor(*gpu_cfg['color_warn'])
            for dev in gpu_cfg['devices']: new_alerts[dev] = color

        self.active_thermal_alerts = new_alerts

        # Si estamos en modo estático o apagado, forzar repintado para aplicar la alerta
        if self.current_mode in ["static", "off"]:
            self._apply_static_with_alerts()

    def is_device_hijacked(self, device_name):
        """Comprueba si un dispositivo está bajo una alerta térmica."""
        return device_name in self.active_thermal_alerts
    
    # --- LÓGICA DE APLICACIÓN CON ESCUDO TÉRMICO ---
    def _apply_static_with_alerts(self):
        """Aplica colores estáticos respetando las alertas térmicas."""
        if not self.client: return
        base_color = self.colors[0] if self.colors and self.current_mode == "static" else RGBColor(0,0,0)
        
        for device in self.client.devices:
            # Si el dispositivo está en alerta, pintarlo de rojo/naranja. Si no, color base.
            target_color = self.active_thermal_alerts.get(device.name, base_color)
            try: device.set_color(target_color)
            except: pass

    def set_speed(self, level):
        """Ajusta el nivel de velocidad (1 a 5) y guarda la configuración."""
        self.anim_speed = max(1, min(5, level))
        self.save_config()

    def set_mode(self, new_mode):
        """Cambia entre modo térmico, estático y animaciones de forma segura."""
        if not self.active or new_mode == self.current_mode:
            return 

        self.current_mode = new_mode
        print(f"[RGB Manager] Cambiando modo a: {self.current_mode}")
        self.save_config()

        # 1. Si había una animación corriendo, la detenemos
        if self.anim_thread and self.anim_thread.is_alive():
            self.stop_anim_flag.set() 
            self.anim_thread.join()   

        # 2. Iniciar animaciones si es necesario
        if self.current_mode in ["starry_night", "rain"]:
            self._start_animation_thread()
            
        # 3. Si es estático, aplicar el Color 1 inmediatamente
        elif self.current_mode == "static":
            color = self.colors[0] if self.colors else RGBColor(0, 255, 255)
            self._apply_color_to_all(color)
            
        # 4. Si es apagado, enviar color negro
        elif self.current_mode == "off":
            self._apply_color_to_all(RGBColor(0, 0, 0))

    def interpolate_color(self, color1, color2, factor):
        """Calcula el color intermedio entre color1 y color2."""
        r = int(color1.red + (color2.red - color1.red) * factor)
        g = int(color1.green + (color2.green - color1.green) * factor)
        b = int(color1.blue + (color2.blue - color1.blue) * factor)
        return RGBColor(r, g, b)
    
    def _fade_to_color(self, start_color, end_color, steps=10, delay_ms=20):
        """Hace una transición suave entre dos colores."""
        for step in range(1, steps + 1):
            factor = step / steps
            intermediate_color = self.interpolate_color(start_color, end_color, factor)
            self._apply_color_to_all(intermediate_color)
            time.sleep(delay_ms / 1000.0)
            
        self.current_thermal_color = end_color
    
    def update_by_temperature(self, temp):
        if not self.active or not self.client or self.current_mode != "thermal":
            return

        # 1. Determinar el color OBJETIVO
        if temp < 50:
            target_color = RGBColor(0, 255, 255) # Cian
        elif temp < 75:
            target_color = RGBColor(255, 165, 0) # Naranja
        else:
            target_color = RGBColor(255, 0, 0)   # Rojo

        # 2. Si el objetivo cambió, iniciamos la transición (en un pequeño hilo o bucle corto)
        if target_color != self.target_thermal_color:
            self.target_thermal_color = target_color
            self._fade_to_color(self.current_thermal_color, target_color)

    def _apply_color_to_all(self, color):
        """Aplica un color sólido a todos los dispositivos de forma simultánea."""
        if not self.client: 
            return
            
        # --- NUEVO ESCUDO: No saturar si el color no ha cambiado ---
        if hasattr(self, 'last_applied_color') and self.last_applied_color:
            if (self.last_applied_color.red == color.red and 
                self.last_applied_color.green == color.green and 
                self.last_applied_color.blue == color.blue):
                return # El color es idéntico, no hacemos nada
                
        try:
            for device in self.client.devices:
                # ¡AQUÍ BORRAMOS EL DEVICE.SET_MODE! Solo enviamos color.
                device.set_color(color)
                
            self.last_applied_color = color # Guardamos memoria del último color
        except Exception as e:
            print(f"[RGB Manager] Error al aplicar color: {e}")
            pass

    # --- ZONA DE ANIMACIONES (HILOS) ---

    def _start_animation_thread(self):
        """Inicia el hilo secundario para evitar lag en la UI."""
        self.stop_anim_flag.clear() 
        self.anim_thread = threading.Thread(target=self._animation_loop, daemon=True)
        self.anim_thread.start() 

    def _animation_loop(self):
        """Bucle de animación con velocidad variable."""
        while not self.stop_anim_flag.is_set():
            # Mapeamos los niveles 1-5 a FPS (5=Lento, 25=Muy Rápido)
            # Nivel 1: 5 FPS | Nivel 3: 15 FPS | Nivel 5: 25 FPS
            fps = self.anim_speed * 5
            delay = 1.0 / fps

            if self.current_mode == "starry_night":
                self._anim_starry_night()
            elif self.current_mode == "rain":
                self._anim_rain()

            time.sleep(delay)

    def _anim_starry_night(self):
        bg_color = self.colors[0] if len(self.colors) > 0 else RGBColor(0, 0, 50)
        star_color = self.colors[1] if len(self.colors) > 1 else RGBColor(255, 255, 255)

        for device in self.client.devices:
            
            # ---> NUEVO ESCUDO: Si el dispositivo está caliente, IGNORAR ANIMACIÓN
            if self.is_device_hijacked(device.name):
                try: device.set_color(self.active_thermal_alerts[device.name])
                except: pass
                continue # Saltar al siguiente dispositivo

            num_leds = len(device.leds)
            if num_leds == 0: continue
            
            # Inicializar el estado de este dispositivo si no existe
            dev_id = device.name # O un identificador único
            if dev_id not in getattr(self, 'led_states', {}):
                if not hasattr(self, 'led_states'): self.led_states = {}
                self.led_states[dev_id] = [bg_color for _ in range(num_leds)]

            current_frame_colors = self.led_states[dev_id]
            
            # 1. ATENUAR las estrellas existentes gradualmente hacia el color de fondo
            fade_speed = 0.1 # Qué tan rápido desaparecen (0.0 a 1.0)
            for i in range(num_leds):
                if current_frame_colors[i] != bg_color:
                    current_frame_colors[i] = self.interpolate_color(current_frame_colors[i], bg_color, fade_speed)

            # 2. ENCENDER nuevas estrellas ocasionalmente
            # Ajusta la probabilidad de que nazca una nueva estrella
            if random.random() < 0.2: # 20% de probabilidad por fotograma
                rand_idx = random.randint(0, num_leds - 1)
                current_frame_colors[rand_idx] = star_color
            
            try:
                device.set_colors(current_frame_colors)
                # Actualizar el estado guardado
                self.led_states[dev_id] = current_frame_colors
            except Exception as e:
                #print(f"Error en fotograma: {e}") # Descomentar para debuggear
                pass

    def _anim_rain(self):
        """Renderiza un fotograma de lluvia con gotas que caen y dejan estela."""
        # Colores definidos por el usuario en la interfaz
        bg_color = self.colors[0] if len(self.colors) > 0 else RGBColor(0, 0, 20)
        drop_color = self.colors[1] if len(self.colors) > 1 else RGBColor(0, 255, 255)
        
        # Diccionario independiente para guardar las gotas de este efecto
        if not hasattr(self, 'rain_states'):
            self.rain_states = {}

        for device in self.client.devices:
            
            # ---> NUEVO ESCUDO: Si el dispositivo está caliente, IGNORAR ANIMACIÓN
            if self.is_device_hijacked(device.name):
                try: device.set_color(self.active_thermal_alerts[device.name])
                except: pass
                continue # Saltar al siguiente dispositivo

            num_leds = len(device.leds)
            if num_leds == 0: continue
            
            dev_id = device.name
            
            # Inicializamos el dispositivo si es la primera vez que entra a la lluvia
            if dev_id not in self.rain_states:
                self.rain_states[dev_id] = {
                    'colors': [bg_color for _ in range(num_leds)], # Estado de cada LED
                    'drops': [] # Lista de posiciones actuales de las gotas
                }

            state = self.rain_states[dev_id]
            current_frame_colors = state['colors']
            
            # 1. LA ESTELA: Desvanecer todos los LEDs encendidos hacia el color de fondo
            fade_speed = 0.25 # Ajusta esto: más alto = estela más corta, más bajo = estela más larga
            for i in range(num_leds):
                if current_frame_colors[i] != bg_color:
                    current_frame_colors[i] = self.interpolate_color(current_frame_colors[i], bg_color, fade_speed)

            # 2. CAÍDA: Mover las gotas existentes una posición hacia adelante
            new_drops = []
            for drop_idx in state['drops']:
                next_idx = drop_idx + 1 # La gota avanza al siguiente LED
                
                # Si la gota aún no se sale de la tira de LEDs, la mantenemos
                if next_idx < num_leds:
                    new_drops.append(next_idx)
                    # Pintamos la "cabeza" de la gota con brillo máximo
                    current_frame_colors[next_idx] = drop_color 

            # 3. NACIMIENTO: Crear nuevas gotas de forma aleatoria al inicio (LED 0)
            # Para evitar que se llene de gotas, la probabilidad es baja (10%)
            if random.random() < 0.1: 
                # Evitamos crear una gota si el primer LED ya está encendido
                if 0 not in new_drops:
                    new_drops.append(0)
                    current_frame_colors[0] = drop_color

            # Guardamos las nuevas posiciones de las gotas para el siguiente fotograma
            state['drops'] = new_drops

            try:
                # Enviamos la tira de colores procesada al dispositivo
                device.set_colors(current_frame_colors)
            except:
                pass

# ¡Instancia global vital para que no dé errores de importación!
rgb_engine = RGBManager()