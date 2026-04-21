import json
import os
import threading
import time
import random
import math
import colorsys # <--- AÑADE ESTO AQUÍ ARRIBA
from openrgb import OpenRGBClient
from openrgb.utils import RGBColor

class RGBManager:
    def __init__(self):
        self.config_file = "RGB_Config.json"
        self.client = None
        self.active = False
        
        # 1. Valores por defecto
        self.current_mode = "static"
        self.colors = [RGBColor(0, 255, 255), RGBColor(255, 255, 255)]
        self.rainbow_submode = "wave" # 'cycle', 'wave', o 'custom' 
        self.anim_speed = 3
        self.frame_count = 0
        self.device_dividers = {
            "ASUS Aura DRAM": 3, 
            "Corsair Vengeance RGB": 3,
            "Corsair Vengeance Pro RGB": 2
        }

        # --- NUEVO: Lista de dispositivos a invertir ---
        # Pon aquí parte del nombre de tu RAM (ignorará mayúsculas)
        self.device_reverse = ["Corsair Vengeance", "DRAM"]

        self.thermal_overlay = {
            "enabled": False,
            "cpu": {
                "warn": 65, "warn_mode": "fixed", "color_warn": [255, 165, 0],
                "crit": 80, "crit_mode": "strobe", "color_crit": [255, 0, 0],
                "devices": []
            },
            "gpu": {
                "warn": 55, "warn_mode": "fixed", "color_warn": [255, 165, 0],
                "crit": 75, "crit_mode": "strobe", "color_crit": [255, 0, 0],
                "devices": []
            }
        }

        # Guardaremos el modo activo por dispositivo para el overlay
        self.active_thermal_modes = {} # Ej: {"RAM": "strobe"}
        
        self.active_thermal_alerts = {}
        self.current_thermal_color = self.colors[0]
        self.target_thermal_color = self.colors[0]
        self.led_states = {}
        self.last_applied_color = None

        self.anim_thread = None       
        self.stop_anim_flag = threading.Event() 

       # --- NUEVAS MEMORIAS DE ESTABILIDAD ---
        self.current_thermal_states = {'cpu': 'none', 'gpu': 'none'} # Evita el rebote de temperatura
        self.last_device_colors = {} # Escudo anti-spam para el hardware

        # 2. Cargar y Conectar
        self.load_config()
        self.connect()

    def connect(self):
        try:
            self.client = OpenRGBClient("localhost", 6742)
            self.active = True
            print("[RGB Manager] Conectado exitosamente a OpenRGB")
            
            for device in self.client.devices:
                try:
                    if 'direct' in [m.name.lower() for m in device.modes]:
                        device.set_mode('direct')
                except: pass
            
            # FORZAR APLICACIÓN INICIAL: ignoramos la validación de duplicados para el arranque
            actual_mode = self.current_mode
            self.current_mode = None 
            self.set_mode(actual_mode)
                
        except Exception as e:
            print(f"[RGB Manager] Fallo de conexión: {e}")
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
                    self.anim_speed = data.get("speed", 3)
                    self.rainbow_submode = data.get("rainbow_submode", "wave")
                    # Cargamos los divisores del JSON, pero los fusionamos con los que escribimos en __init__
                    loaded_dividers = data.get("device_dividers", {})
                    for key, value in loaded_dividers.items():
                        self.device_dividers[key] = value
                    
                    # --- NUEVO: Cargar invertidos ---
                    loaded_reverse = data.get("device_reverse", [])
                    # Fusionamos sin duplicados
                    self.device_reverse = list(set(self.device_reverse + loaded_reverse))

                    # Carga segura de colores: asegurar que se conviertan a RGBColor
                    raw_colors = data.get("colors", [[0, 255, 255]])
                    self.colors = [RGBColor(c[0], c[1], c[2]) for c in raw_colors]
                    
                    if "thermal_overlay" in data:
                        self.thermal_overlay = data["thermal_overlay"]
                print("[RGB Manager] Configuración cargada correctamente.")
            except Exception as e:
                print(f"[RGB Manager] Error al cargar JSON: {e}")

    def save_config(self):
        try:
            # Aseguramos que solo guardamos valores nativos de Python en el JSON
            color_data = []
            for c in self.colors:
                if isinstance(c, RGBColor):
                    color_data.append([c.red, c.green, c.blue])
                else:
                    color_data.append([0, 255, 255])

            data = {
                "mode": self.current_mode,
                "speed": self.anim_speed,
                "device_dividers": self.device_dividers,
                "device_reverse": self.device_reverse,
                "colors": color_data,
                "rainbow_submode": self.rainbow_submode,
                "thermal_overlay": self.thermal_overlay
            }
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[RGB Manager] Error crítico al guardar JSON: {e}")
    
    # --- NUEVA LÓGICA TÉRMICA COMO CAPA SUPERIOR ---
    def evaluate_thermal_state(self, current_temps):
        if not self.active or not self.thermal_overlay["enabled"]:
            self.active_thermal_alerts.clear()
            self.active_thermal_modes.clear()
            self.current_thermal_states = {'cpu': 'none', 'gpu': 'none'}
            
            if self.current_mode in ["static", "off"]:
                if self.anim_thread and self.anim_thread.is_alive():
                    self.stop_anim_flag.set()
                    self.anim_thread.join()
                self._apply_static_with_alerts()
            return

        new_alerts = {}
        new_modes = {}

        for sensor in ['cpu', 'gpu']:
            temp = current_temps.get(sensor, -1)
            if temp < 0: continue # Ignoramos lecturas falsas/vacías del sensor
            
            cfg = self.thermal_overlay[sensor]
            current_state = self.current_thermal_states.get(sensor, 'none')
            
            # --- LÓGICA DE HISTÉRESIS (2 GRADOS DE MARGEN) ---
            if temp >= cfg['crit']:
                new_state = 'crit'
            elif temp >= cfg['warn']:
                # Si estaba en crit, lo mantenemos hasta que baje bien
                if current_state == 'crit' and temp > cfg['crit'] - 2:
                    new_state = 'crit'
                else:
                    new_state = 'warn'
            else:
                # Si estaba en warn, lo mantenemos hasta que baje bien
                if current_state == 'warn' and temp > cfg['warn'] - 2:
                    new_state = 'warn'
                elif current_state == 'crit' and temp > cfg['crit'] - 2:
                    new_state = 'crit'
                else:
                    new_state = 'none'

            self.current_thermal_states[sensor] = new_state

            # Asignar colores según el estado estable
            if new_state == 'crit':
                for dev in cfg['devices']:
                    new_alerts[dev] = RGBColor(*cfg['color_crit'])
                    new_modes[dev] = cfg.get('crit_mode', 'strobe')
            elif new_state == 'warn':
                for dev in cfg['devices']:
                    new_alerts[dev] = RGBColor(*cfg['color_warn'])
                    new_modes[dev] = cfg.get('warn_mode', 'fijo')

        self.active_thermal_alerts = new_alerts
        self.active_thermal_modes = new_modes

        requires_animation = any(m in ["breathing", "strobe"] for m in new_modes.values())
        
        if requires_animation:
            if not self.anim_thread or not self.anim_thread.is_alive():
                self.stop_anim_flag.clear()
                self.anim_thread = threading.Thread(target=self._animation_loop, daemon=True)
                self.anim_thread.start()
        else:
            if self.current_mode in ["static", "off"]:
                if self.anim_thread and self.anim_thread.is_alive():
                    self.stop_anim_flag.set()
                    self.anim_thread.join()
                self._apply_static_with_alerts()

    def is_device_hijacked(self, device_name):
        """Comprueba si un dispositivo está bajo una alerta térmica."""
        return device_name in self.active_thermal_alerts
    
    def _get_effect_color(self, mode, color, speed_multiplier=1.0):
        """Calcula el color resultante según el efecto (respiración, strobe, fijo)."""
        t = time.time() * speed_multiplier
        
        if mode == "strobe":
            # Parpadeo rápido (encendido/apagado)
            return color if (int(t * 10) % 2 == 0) else RGBColor(0, 0, 0)
            
        elif mode == "breathing":
            # Oscilación suave usando seno
            brightness = (math.sin(t * 3) + 1) / 2 # Valor entre 0 y 1
            return RGBColor(
                int(color.red * brightness),
                int(color.green * brightness),
                int(color.blue * brightness)
            )
            
        return color # "fixed" devuelve el color original
    
    def _safe_set_color(self, device, color):
            """Envía el color solo si es diferente al último enviado, evitando colapsar el USB."""
            last_col = self.last_device_colors.get(device.name)
            if last_col and last_col.red == color.red and last_col.green == color.green and last_col.blue == color.blue:
                return # El color es idéntico, la PC respira tranquila
                
            try:
                device.set_color(color)
                self.last_device_colors[device.name] = color
            except:
                pass
                
    # --- LÓGICA DE APLICACIÓN CON ESCUDO TÉRMICO ---
    def _apply_static_with_alerts(self):
        if not self.client: return
        base_color = self.colors[0] if self.colors and self.current_mode == "static" else RGBColor(0,0,0)
        
        for device in self.client.devices:
            target_color = self.active_thermal_alerts.get(device.name, base_color)
            self._safe_set_color(device, target_color) # Usamos el método seguro

    def _apply_color_to_all_with_shield(self, color):
        for device in self.client.devices:
            if not self.is_device_hijacked(device.name):
                self._safe_set_color(device, color) # Usamos el método seguro

    def set_speed(self, level):
        """Ajusta el nivel de velocidad (1 a 5) y guarda la configuración."""
        self.anim_speed = max(1, min(5, level))
        self.save_config()

    def set_mode(self, new_mode):
        if not self.active or (new_mode == self.current_mode and self.anim_thread and self.anim_thread.is_alive()):
            return 

        self.current_mode = new_mode
        self.save_config()

        # Detener hilos previos
        if self.anim_thread and self.anim_thread.is_alive():
            self.stop_anim_flag.set()
            self.anim_thread.join()

        if self.current_mode in ["starry_night", "rain", "breathing", "strobe", "rainbow", "color_wave"]:
            self.stop_anim_flag.clear()
            self.anim_thread = threading.Thread(target=self._animation_loop, daemon=True)
            self.anim_thread.start()
        elif self.current_mode == "static":
            self._apply_static_with_alerts()
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

            self.frame_count += 1
            # IMPORTANTE: Al aplicar colores a los dispositivos:
            # 1. CAPA SUPERIOR: Evaluar Thermal Reaction
            if self.thermal_overlay.get("enabled", False) and self.active_thermal_alerts:
                for device in self.client.devices:
                    if self.is_device_hijacked(device.name):
                        target_color = self.active_thermal_alerts[device.name]
                        target_mode = self.active_thermal_modes.get(device.name, "fijo")
                        
                        final_color = self._get_effect_color(target_mode, target_color)
                        # USAMOS EL MÉTODO SEGURO AQUÍ TAMBIÉN
                        self._safe_set_color(device, final_color)
                        try:
                            device.set_color(final_color)
                        except:
                            pass

            # 2. CAPA BASE: Llamar a las funciones separadas
            if self.current_mode == "starry_night":
                self._anim_starry_night()
            elif self.current_mode == "rain":
                self._anim_rain()
            elif self.current_mode == "breathing":
                self._anim_breathing()
            elif self.current_mode == "strobe":
                self._anim_strobe()
            elif self.current_mode == "rainbow":
                self._anim_rainbow()
            elif self.current_mode == "color_wave":
                self._anim_color_wave()

            time.sleep(delay)

    def _anim_starry_night(self):
        bg_color = self.colors[0] if len(self.colors) > 0 else RGBColor(0, 0, 50)
        star_color = self.colors[1] if len(self.colors) > 1 else RGBColor(255, 255, 255)

        for device in self.client.devices:
            
            # ---> NUEVO ESCUDO: Si el dispositivo está caliente, IGNORAR ANIMACIÓN
            if self.is_device_hijacked(device.name):
                continue # ¡NO HACER NADA MÁS! Solo saltar al siguiente

            # ---> NUEVO FRENO DE VELOCIDAD (Búsqueda Inteligente) <---
            divider = 1
            for dev_key, dev_val in self.device_dividers.items():
                if dev_key.lower() in device.name.lower(): # Coincidencia parcial
                    divider = dev_val
                    break
            
            if self.frame_count % divider != 0:
                continue # Saltamos este fotograma

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
                continue # ¡NO HACER NADA MÁS! Solo saltar al siguiente

            # ---> NUEVO FRENO DE VELOCIDAD (Búsqueda Inteligente) <---
            divider = 1
            for dev_key, dev_val in self.device_dividers.items():
                if dev_key.lower() in device.name.lower(): # Coincidencia parcial
                    divider = dev_val
                    break
            
            if self.frame_count % divider != 0:
                continue # Saltamos este fotograma

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

            # --- NUEVO: Lógica de Inversión ---
            # Hacemos una copia de la lista de colores para no arruinar la matemática interna
            colors_to_send = list(current_frame_colors)
            
            # Buscamos si este dispositivo está en nuestra lista de invertidos
            for rev_name in self.device_reverse:
                if rev_name.lower() in device.name.lower():
                    colors_to_send.reverse() # ¡Volteamos la lista de colores al revés!
                    break

            try:
                # Enviamos la lista (normal o volteada) al hardware
                device.set_colors(colors_to_send)
            except:
                pass

    def _anim_breathing(self):
        """Efecto de respiración como animación base separada."""
        color_base = self.colors[0] if len(self.colors) > 0 else RGBColor(0, 255, 255)
        color_con_efecto = self._get_effect_color("breathing", color_base)
        self._apply_color_to_all_with_shield(color_con_efecto)

    def _anim_strobe(self):
        """Efecto estroboscópico como animación base separada."""
        color_base = self.colors[0] if len(self.colors) > 0 else RGBColor(255, 0, 0)
        color_con_efecto = self._get_effect_color("strobe", color_base)
        self._apply_color_to_all_with_shield(color_con_efecto)

    # ---------------------------------------------------------
    # LA FUNCIÓN MAESTRA (EL JEFE)
    # ---------------------------------------------------------
    def _anim_rainbow(self):
        """Función maestra que decide qué arcoíris ejecutar."""
        if self.rainbow_submode == "cycle":
            self._anim_rainbow_cycle()
        elif self.rainbow_submode == "wave":
            self._anim_rainbow_wave()
        elif self.rainbow_submode == "custom":
            self._anim_color_wave()

    # ---------------------------------------------------------
    # LOS 3 TRABAJADORES (LA MATEMÁTICA REAL)
    # ---------------------------------------------------------
    def _anim_rainbow_cycle(self):
        """Todos los LEDs cambian de color al mismo tiempo."""
        time_offset = self.frame_count * 0.01
        hue = time_offset % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        color = RGBColor(int(r * 255), int(g * 255), int(b * 255))
        
        # Usamos nuestro método seguro
        self._apply_color_to_all_with_shield(color)


    def _anim_rainbow_wave(self):
        """El espectro viaja como una ola por los dispositivos."""
        time_offset = self.frame_count * 0.05 
        ancho_ola = 0.08 
        
        for device in self.client.devices:
            if self.is_device_hijacked(device.name): continue
            num_leds = len(device.leds)
            if num_leds == 0: continue
            
            divider = 1
            for dev_key, dev_val in self.device_dividers.items():
                if dev_key.lower() in device.name.lower(): divider = dev_val; break
            if self.frame_count % divider != 0: continue 

            frame_colors = []
            for i in range(num_leds):
                hue = (time_offset + (i * ancho_ola)) % 1.0
                r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                frame_colors.append(RGBColor(int(r * 255), int(g * 255), int(b * 255)))

            colors_to_send = list(frame_colors)
            for rev_name in self.device_reverse:
                if rev_name.lower() in device.name.lower():
                    colors_to_send.reverse()
                    break

            try: device.set_colors(colors_to_send)
            except: pass

    def _anim_color_wave(self):
        """Ola personalizada usando los 2 colores del usuario."""
        c1 = self.colors[0] if len(self.colors) > 0 else RGBColor(255, 0, 0)
        c2 = self.colors[1] if len(self.colors) > 1 else RGBColor(0, 0, 255)
        
        time_offset = self.frame_count * 0.15
        
        for device in self.client.devices:
            if self.is_device_hijacked(device.name): continue
            num_leds = len(device.leds)
            if num_leds == 0: continue
            
            divider = 1
            for dev_key, dev_val in self.device_dividers.items():
                if dev_key.lower() in device.name.lower(): divider = dev_val; break
            if self.frame_count % divider != 0: continue

            frame_colors = []
            for i in range(num_leds):
                import math # Aseguramos que math esté disponible
                factor = (math.sin(time_offset + (i * 0.5)) + 1) / 2
                
                r = int(c1.red + (c2.red - c1.red) * factor)
                g = int(c1.green + (c2.green - c1.green) * factor)
                b = int(c1.blue + (c2.blue - c1.blue) * factor)
                frame_colors.append(RGBColor(r, g, b))

            colors_to_send = list(frame_colors)
            for rev_name in self.device_reverse:
                if rev_name.lower() in device.name.lower():
                    colors_to_send.reverse()
                    break

            try: device.set_colors(colors_to_send)
            except: pass

# ¡Instancia global vital para que no dé errores de importación!
rgb_engine = RGBManager()