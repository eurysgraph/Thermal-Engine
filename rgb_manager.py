from openrgb import OpenRGBClient
from openrgb.utils import RGBColor

class RGBManager:
    def __init__(self):
        self.client = None
        self.active = False
        self.connect()

    def connect(self):
        try:
            self.client = OpenRGBClient("localhost", 6742)
            self.active = True
            print("[RGB Manager] Conectado exitosamente a OpenRGB")
        except:
            print("[RGB Manager] No se pudo conectar. ¿Está OpenRGB abierto?")
            self.active = False

    def update_by_temperature(self, temp):
        if not self.active or not self.client:
            return

        # Lógica de colores:
        if temp < 50:
            # Frío: Cian/Azul
            color = RGBColor(0, 255, 255) 
        elif temp < 75:
            # Tibio: Amarillo/Naranja
            color = RGBColor(255, 165, 0)
        else:
            # Caliente: Rojo
            color = RGBColor(255, 0, 0)

        # Aplicar a todos los dispositivos (RAM, Placa, Fans)
        for device in self.client.devices:
            device.set_color(color)