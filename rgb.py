from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QColorDialog, QFrame,
    QSlider, QGroupBox, QCheckBox, QTabWidget, QSpinBox, QScrollArea
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt

from rgb_manager import rgb_engine
from openrgb.utils import RGBColor

class RGBControlPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.mode_color_counts = {
            "static": 1,
            "breathing": 1,
            "strobe": 1,
            "starry_night": 2,
            "rain": 2,
            "rainbow": 0, 
            "color_wave": 2,
            "off": 0
        }

        self.mode_names = {
            "static": "Estático (Color Base)",
            "breathing": "Respiración",
            "strobe": "Estroboscopico",
            "starry_night": "Noche Estrellada",
            "rain": "Lluvia de Colores",
            "rainbow": "Arcoíris Clásico",
            "color_wave": "Ola de Colores (Custom)",
            "off": "Apagado"
        }

        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(10)

        # --- SECCIÓN 1: ESTADO ---
        self.status_container = QWidget()
        status_layout = QHBoxLayout(self.status_container)
        status_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_status_icon = QLabel("⬤") 
        self.lbl_status_text = QLabel("Verificando servidor...")
        status_layout.addWidget(self.lbl_status_icon)
        status_layout.addWidget(self.lbl_status_text)
        status_layout.addStretch()
        main_layout.addWidget(self.status_container)
        self.update_status_display() 

        # --- SECCIÓN 2: ANIMACIÓN BASE ---
        base_group = QGroupBox("Animación Base (Fondo)")
        base_layout = QVBoxLayout(base_group)

        # Modo
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Efecto:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems([
            "Estático (Color Base)",
            "Respiración",
            "Estroboscopico",
            "Noche Estrellada",
            "Lluvia de Colores",
            "Arcoíris Clásico",
            "Ola de Colores (Custom)",
            "Apagado"])
        self.combo_mode.currentIndexChanged.connect(self.on_mode_changed)
        mode_layout.addWidget(self.combo_mode)
        base_layout.addLayout(mode_layout)

        # Velocidad
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Velocidad:"))
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(1, 5)
        self.slider_speed.setValue(rgb_engine.anim_speed)
        self.slider_speed.valueChanged.connect(lambda v: rgb_engine.set_speed(v))
        speed_layout.addWidget(self.slider_speed)
        base_layout.addLayout(speed_layout)

        # Contenedor de colores dinámicos
        self.colors_group = QWidget()
        self.colors_layout = QVBoxLayout(self.colors_group)
        self.colors_layout.setContentsMargins(0,0,0,0)
        base_layout.addWidget(self.colors_group)

        main_layout.addWidget(base_group)

        # --- SECCIÓN 3: CAPA DE REACCIÓN TÉRMICA (NUEVO) ---
        thermal_group = QGroupBox("Capa de Reacción Térmica (Prioridad Alta)")
        thermal_group.setCheckable(True)
        thermal_group.setChecked(rgb_engine.thermal_overlay["enabled"])
        thermal_group.toggled.connect(self.on_thermal_toggled)
        thermal_layout = QVBoxLayout(thermal_group)

        # Pestañas para CPU y GPU
        self.thermal_tabs = QTabWidget()
        
        # Crear la pestaña de CPU y GPU usando nuestra función constructora
        self.tab_cpu = self._create_sensor_tab("cpu", "CPU")
        self.tab_gpu = self._create_sensor_tab("gpu", "GPU")
        
        self.thermal_tabs.addTab(self.tab_cpu, "Sensor CPU")
        self.thermal_tabs.addTab(self.tab_gpu, "Sensor GPU")
        
        thermal_layout.addWidget(self.thermal_tabs)
        main_layout.addWidget(thermal_group)

        # Sincronización inicial
        main_layout.addStretch()
        display_name = self.mode_names.get(rgb_engine.current_mode, "Estático (Color Base)")
        index = self.combo_mode.findText(display_name)
        if index >= 0: self.combo_mode.setCurrentIndex(index)
        self.refresh_color_pickers()

    # ==========================================
    # CONSTRUCTOR DE PESTAÑAS TÉRMICAS
    # ==========================================
    def _create_sensor_tab(self, sensor_key, title):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 10, 5, 5)
        
        cfg = rgb_engine.thermal_overlay[sensor_key]

        # --- Controles de Temperatura y Color (se mantienen igual) ---
        warn_layout = QHBoxLayout()
        warn_layout.addWidget(QLabel("Advertencia:"))
        sp_warn = QSpinBox()
        sp_warn.setRange(30, 105); sp_warn.setSuffix(" °C"); sp_warn.setValue(cfg["warn"])
        sp_warn.valueChanged.connect(lambda v, k=sensor_key: self.update_thermal_val(k, "warn", v))
        warn_layout.addWidget(sp_warn)
        
        btn_warn = QPushButton(); btn_warn.setFixedSize(30, 20)
        self.set_btn_color(btn_warn, cfg["color_warn"])
        btn_warn.clicked.connect(lambda _, k=sensor_key, b=btn_warn: self.pick_thermal_color(k, "color_warn", b))
        warn_layout.addWidget(btn_warn)
        layout.addLayout(warn_layout)

        crit_layout = QHBoxLayout()
        crit_layout.addWidget(QLabel("Crítico:"))
        sp_crit = QSpinBox()
        sp_crit.setRange(30, 115); sp_crit.setSuffix(" °C"); sp_crit.setValue(cfg["crit"])
        sp_crit.valueChanged.connect(lambda v, k=sensor_key: self.update_thermal_val(k, "crit", v))
        crit_layout.addWidget(sp_crit)
        
        btn_crit = QPushButton(); btn_crit.setFixedSize(30, 20)
        self.set_btn_color(btn_crit, cfg["color_crit"])
        btn_crit.clicked.connect(lambda _, k=sensor_key, b=btn_crit: self.pick_thermal_color(k, "color_crit", b))
        crit_layout.addWidget(btn_crit)
        layout.addLayout(crit_layout)

        # Añadir selector de modo para Warning
        warn_mode_layout = QHBoxLayout()
        warn_mode_layout.addWidget(QLabel("Modo Adv:"))
        cb_warn = QComboBox()
        cb_warn.addItems(["fijo", "breathing", "strobe"])
        cb_warn.setCurrentText(cfg.get("warn_mode", "fijo"))
        cb_warn.currentTextChanged.connect(lambda v, k=sensor_key: self.update_thermal_val(k, "warn_mode", v))
        warn_mode_layout.addWidget(cb_warn)
        layout.addLayout(warn_mode_layout)

        # Añadir selector de modo para Crit
        crit_mode_layout = QHBoxLayout()
        crit_mode_layout.addWidget(QLabel("Modo Crit:"))
        cb_crit = QComboBox()
        cb_crit.addItems(["fijo", "breathing", "strobe"])
        cb_crit.setCurrentText(cfg.get("crit_mode", "strobe"))
        cb_crit.currentTextChanged.connect(lambda v, k=sensor_key: self.update_thermal_val(k, "crit_mode", v))
        crit_mode_layout.addWidget(cb_crit)
        layout.addLayout(crit_mode_layout)

        # --- NUEVA SECCIÓN DE DISPOSITIVOS CON CHECKBOXES ---
        layout.addWidget(QLabel("Aplicar Reacción Térmica en:"))
        
        # Usamos un ScrollArea por si la lista es larga
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(120)
        
        container = QWidget()
        check_layout = QVBoxLayout(container)
        check_layout.setSpacing(2)
        
        available_devices = rgb_engine.get_device_names()
        
        for dev_name in available_devices:
            cb = QCheckBox(dev_name)
            # Verificar si este dispositivo ya estaba en la lista guardada
            if dev_name in cfg["devices"]:
                cb.setChecked(True)
            
            # Conectamos el cambio de estado directamente
            cb.toggled.connect(lambda checked, d=dev_name, s=sensor_key: self.on_device_check_toggled(s, d, checked))
            check_layout.addWidget(cb)
        
        check_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        return tab

    # ==========================================
    # LÓGICA DE EVENTOS (NUEVOS Y ANTIGUOS)
    # ==========================================

    def on_device_check_toggled(self, sensor_key, device_name, is_checked):
        """Maneja la adición o eliminación de dispositivos mediante checkboxes."""
        current_devices = rgb_engine.thermal_overlay[sensor_key]["devices"]
        
        if is_checked:
            if device_name not in current_devices:
                current_devices.append(device_name)
        else:
            if device_name in current_devices:
                current_devices.remove(device_name)
        
        # Guardamos el cambio en el JSON inmediatamente
        rgb_engine.save_config()
    
    def update_status_display(self):
        if rgb_engine.active:
            self.lbl_status_icon.setStyleSheet("color: #00FF00;") 
            self.lbl_status_text.setText("OpenRGB: Conectado")
        else:
            self.lbl_status_icon.setStyleSheet("color: #FF0000;") 
            self.lbl_status_text.setText("OpenRGB: Desconectado")

    def on_mode_changed(self, index):
        modes = ["static", "breathing", "strobe", "starry_night", "rain", "rainbow", "color_wave", "off"]
        if index < len(modes):
            rgb_engine.set_mode(modes[index])
            self.refresh_color_pickers()

    def refresh_color_pickers(self):
        for i in reversed(range(self.colors_layout.count())): 
            widget = self.colors_layout.itemAt(i).widget()
            if widget: widget.setParent(None)

        mode = rgb_engine.current_mode
        num_colors = self.mode_color_counts.get(mode, 0)

        # --- NUEVO: Selector de Sub-modo para Arcoíris ---
        if mode == "rainbow":
            sub_layout = QHBoxLayout()
            sub_layout.addWidget(QLabel("Tipo de Arcoíris:"))
            combo_sub = QComboBox()
            combo_sub.addItems(["Ola (Wave)", "Ciclo (Cycle)", "Personalizado (Custom)"])
            
            # Sincronizar con el valor actual del motor
            mapping = {"wave": 0, "cycle": 1, "custom": 2}
            combo_sub.setCurrentIndex(mapping.get(rgb_engine.rainbow_submode, 0))
            
            combo_sub.currentIndexChanged.connect(self.on_rainbow_submode_changed)
            sub_layout.addWidget(combo_sub)
            
            w_sub = QWidget()
            w_sub.setLayout(sub_layout)
            self.colors_layout.addWidget(w_sub)

        # --- Lógica de colores (Solo si no es arcoíris automático) ---
        # Si es rainbow 'custom' usamos 2 colores, si es 'cycle/wave' usamos 0.
        num_colors = self.mode_color_counts.get(mode, 0)
        if mode == "rainbow" and rgb_engine.rainbow_submode != "custom":
            num_colors = 0

        for i in range(num_colors):
            h_layout = QHBoxLayout()
            label = QLabel(f"Color {i+1}:")
            if i >= len(rgb_engine.colors): rgb_engine.colors.append(RGBColor(255, 255, 255))
            current_rgb = rgb_engine.colors[i]
            
            btn = QPushButton()
            btn.setFixedSize(40, 25)
            self.set_btn_color(btn, [current_rgb.red, current_rgb.green, current_rgb.blue])
            btn.clicked.connect(lambda checked, idx=i: self.on_change_specific_color(idx))
            
            h_layout.addWidget(label)
            h_layout.addWidget(btn)
            h_layout.addStretch()
            
            w = QWidget()
            w.setLayout(h_layout)
            self.colors_layout.addWidget(w)

    def on_change_specific_color(self, index):
        current = rgb_engine.colors[index]
        new_color = QColorDialog.getColor(QColor(current.red, current.green, current.blue), self)
        if new_color.isValid():
            rgb_engine.colors[index] = RGBColor(new_color.red(), new_color.green(), new_color.blue())
            rgb_engine.save_config()
            if rgb_engine.current_mode == "static":
                rgb_engine._apply_static_with_alerts()
            self.refresh_color_pickers()

    def on_rainbow_submode_changed(self, index):
        mapping = {0: "wave", 1: "cycle", 2: "custom"}
        rgb_engine.rainbow_submode = mapping.get(index, "wave")
        rgb_engine.save_config()
        # Refrescar para mostrar/ocultar los botones de colores
        self.refresh_color_pickers()

    # --- MÉTODOS DE LA CAPA TÉRMICA ---
    def on_thermal_toggled(self, is_checked):
        """Activa o desactiva la reacción térmica."""
        rgb_engine.thermal_overlay["enabled"] = is_checked
        rgb_engine.save_config()

    def update_thermal_val(self, sensor, key, value):
        """Guarda los cambios de temperatura (warn o crit) en el JSON."""
        rgb_engine.thermal_overlay[sensor][key] = value
        rgb_engine.save_config()

    def update_thermal_devices(self, sensor, list_widget):
        """Guarda qué dispositivos se seleccionaron para CPU o GPU."""
        selected_items = list_widget.selectedItems()
        selected_names = [item.text() for item in selected_items]
        rgb_engine.thermal_overlay[sensor]["devices"] = selected_names
        rgb_engine.save_config()

    def pick_thermal_color(self, sensor, color_key, button_widget):
        """Abre la paleta para cambiar el color de advertencia o crítico."""
        curr_rgb = rgb_engine.thermal_overlay[sensor][color_key]
        new_color = QColorDialog.getColor(QColor(curr_rgb[0], curr_rgb[1], curr_rgb[2]), self)
        
        if new_color.isValid():
            r, g, b = new_color.red(), new_color.green(), new_color.blue()
            rgb_engine.thermal_overlay[sensor][color_key] = [r, g, b]
            self.set_btn_color(button_widget, [r, g, b])
            rgb_engine.save_config()

    def set_btn_color(self, btn, rgb_list):
        """Helper para pintar botones con CSS."""
        btn.setStyleSheet(f"background-color: rgb({rgb_list[0]}, {rgb_list[1]}, {rgb_list[2]}); border: 1px solid #555;")

    # def sync_ui_with_engine(self):
    #     """Sincroniza la interfaz visual si el motor cambió desde afuera (ej. Tray Icon)."""
    #     # 1. Buscar cuál es el nombre visible del modo actual
    #     display_name = self.mode_names.get(rgb_engine.current_mode, "Estático (Color Base)")
    #     index = self.combo_mode.findText(display_name)
        
    #     if index >= 0:
    #         # 2. Bloqueamos las señales temporalmente para que cambiar el texto
    #         # no dispare on_mode_changed y cree un bucle infinito.
    #         self.combo_mode.blockSignals(True)
    #         self.combo_mode.setCurrentIndex(index)
    #         self.combo_mode.blockSignals(False)
            
    #     # 3. Forzar el redibujado de los botones de color
    #     self.refresh_color_pickers()