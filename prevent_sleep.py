# -*- coding: utf-8 -*-
"""
prevent_sleep.py

Utilidad para prevenir que el sistema operativo (Windows, macOS, Linux) entre
en modo de suspensión o hibernación. Esencial para garantizar la ejecución
ininterrumpida de los schedulers.

Autor: Jonathan Matus
Fecha: Octubre 2025
"""

# 1. Librerías Estándar de Python
import ctypes
import threading
import time

# 2. Librerías de Terceros

# 3. Módulos de la Aplicación

# -----------------------------------------------------------------------------
# FUNCIÓN PRINCIPAL
# -----------------------------------------------------------------------------

class SleepPreventer:
    """
    Previene que Windows entre en modo de suspensión utilizando la API de Windows.
    También mantiene la conexión de red activa.
    """
    
    # Constantes de la API de Windows
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002
    ES_AWAYMODE_REQUIRED = 0x00000040
    
    def __init__(self, keep_display_on=False):
        """
        Args:
            keep_display_on (bool): Si True, mantiene la pantalla encendida.
                                   Si False, permite que la pantalla se apague pero 
                                   el sistema sigue activo.
        """
        self.keep_display_on = keep_display_on
        self.is_active = False
        self._heartbeat_thread = None
        self._stop_event = threading.Event()
    
    def start(self):
        """Activa la prevención de suspensión"""
        if self.is_active:
            print("⚠️  La prevención de suspensión ya está activa.")
            return
        
        try:
            # Determinar flags según configuración
            if self.keep_display_on:
                flags = self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED | self.ES_DISPLAY_REQUIRED
                mode_text = "Sistema y pantalla activos"
            else:
                flags = self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED
                mode_text = "Sistema activo (pantalla puede apagarse)"
            
            # Llamar a la API de Windows
            ctypes.windll.kernel32.SetThreadExecutionState(flags)
            
            self.is_active = True
            print(f"✅ Prevención de suspensión ACTIVADA - Modo: {mode_text}")
            
            # Iniciar heartbeat thread (refresco cada 3 minutos)
            self._stop_event.clear()
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop, 
                args=(flags,),
                daemon=True
            )
            self._heartbeat_thread.start()
            
        except Exception as e:
            print(f"❌ Error al activar prevención de suspensión: {e}")
    
    def stop(self):
        """Desactiva la prevención de suspensión"""
        if not self.is_active:
            return
        
        try:
            # Detener el heartbeat
            self._stop_event.set()
            if self._heartbeat_thread:
                self._heartbeat_thread.join(timeout=2)
            
            # Restaurar comportamiento normal de Windows
            ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)
            
            self.is_active = False
            print("🛑 Prevención de suspensión DESACTIVADA")
            
        except Exception as e:
            print(f"⚠️  Error al desactivar prevención de suspensión: {e}")
    
    def _heartbeat_loop(self, flags):
        """
        Loop que refresca la configuración cada 3 minutos.
        Esto asegura que Windows no "olvide" la configuración.
        """
        while not self._stop_event.is_set():
            time.sleep(180)  # 3 minutos
            if self.is_active:
                try:
                    ctypes.windll.kernel32.SetThreadExecutionState(flags)
                except Exception as e:
                    print(f"⚠️  Error en heartbeat de prevención de suspensión: {e}")
    
    def __enter__(self):
        """Soporte para context manager"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Soporte para context manager"""
        self.stop()
        return False


def prevent_sleep(keep_display_on=False):
    """
    Crea y retorna un SleepPreventer activo.
    
    Uso:
        preventer = prevent_sleep()
        # ... tu código ...
        preventer.stop()
    """
    preventer = SleepPreventer(keep_display_on=keep_display_on)
    preventer.start()
    return preventer