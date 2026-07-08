# -*- coding: utf-8 -*-
import time
import datetime
import glob
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from interfaz import iniciar_interfaz
from scrapper_review import ReviewScraper
from scrapper_shifts_trimming import ShiftsTrimmingScraper
from bigquery_uploader import procesar_y_subir_lote
from prevent_sleep import SleepPreventer

# =================================================================
# CONFIGURACION GLOBAL
# =================================================================
MODO_PRUEBA = False       # True: Se conecta a Chrome en el puerto 9222 y maximiza la ventana
MODO_HEADLESS = False    # True: Ejecuta Chrome 100% invisible.

def limpiar_y_subir_archivos_en_lote(download_dir, num_ciclo_actual, fecha_medicion_fija, hora_medicion_fija):
    archivos_locales = glob.glob(os.path.join(download_dir, "*.csv"))
    
    if not archivos_locales:
        print("\n[INFO] No hay archivos CSV descargados para subir a BigQuery en este ciclo.")
        return

    print(f"\n[BIGQUERY] Consolidando {len(archivos_locales)} archivos locales para subir en lote...")
    procesar_y_subir_lote(archivos_locales, num_ciclo_actual, fecha_medicion_fija, hora_medicion_fija)
    
    for archivo in archivos_locales:
        try: os.remove(archivo)
        except: pass

def main():
    print("[SISTEMA] Levantando interfaz...")
    lista_ciudades, fecha_inicio, fecha_fin, horas, intervalo = iniciar_interfaz()

    if not lista_ciudades or not fecha_inicio or not fecha_fin or not horas or not intervalo:
        print("[INFO] Operacion cancelada por el usuario o faltaron datos.")
        return

    fecha_start_dt = datetime.datetime.strptime(fecha_inicio, "%d.%m.%Y")
    fecha_end_dt = datetime.datetime.strptime(fecha_fin, "%d.%m.%Y")
    
    lista_fechas = []
    fecha_curr = fecha_start_dt
    while fecha_curr <= fecha_end_dt:
        lista_fechas.append(fecha_curr.strftime("%d.%m.%Y"))
        fecha_curr += datetime.timedelta(days=1)

    total_ciclos = int((horas * 60) / intervalo)
    if total_ciclos < 1: 
        total_ciclos = 1

    carpeta_perfil = os.path.join(os.getcwd(), "perfil_chrome_bot")

    print("\n" + "="*50)
    print(f"DATOS: {len(lista_ciudades)} ciudades seleccionadas | {len(lista_fechas)} dias a analizar")
    print(f"CONFIGURACION: Duracion {horas}h | Descargas cada {intervalo} min ({total_ciclos} ciclos totales)")
    print(f"ESTRATEGIA: Ejecucion Efimera adaptada para MODO_PRUEBA")
    print("="*50)

    # =================================================================
    # INICIO DE PREVENCION DE SUSPENSION
    # =================================================================
    preventer = SleepPreventer(keep_display_on=False)
    preventer.start()

    try:
        for ciclo in range(total_ciclos):
            num_ciclo_actual = ciclo + 1
            ahora_ciclo = datetime.datetime.now()
            fecha_medicion_fija = ahora_ciclo.strftime("%Y-%m-%d")
            hora_medicion_fija = ahora_ciclo.strftime("%H:%M:%S")

            print(f"\n" + "*"*50)
            print(f"INICIANDO CICLO {num_ciclo_actual} DE {total_ciclos} (Hora de ciclo: {hora_medicion_fija})")
            print("*"*50)

            print("[SISTEMA] Iniciando instancia de Chrome para este ciclo...")
            driver = None
            try:
                chrome_options = Options()
                
                chrome_options.add_argument("--disable-background-timer-throttling")
                chrome_options.add_argument("--disable-backgrounding-occluded-windows")
                chrome_options.add_argument("--disable-renderer-backgrounding")
                
                if MODO_PRUEBA:
                    print("[INFO] MODO PRUEBA ACTIVADO. Conectando a navegador existente en el puerto 9222...")
                    chrome_options.debugger_address = "127.0.0.1:9222"
                    driver = webdriver.Chrome(options=chrome_options)
                    driver.maximize_window()
                else:
                    chrome_options.add_argument("--window-size=1920,1080")
                    chrome_options.add_argument(f"user-data-dir={carpeta_perfil}")
                    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                    
                    if MODO_HEADLESS:
                        chrome_options.add_argument("--headless=new")
                        chrome_options.add_argument("--disable-gpu")
                        
                    driver = webdriver.Chrome(options=chrome_options)
                    driver.get("https://cl.us.logisticsbackoffice.com/dashboard/rooster/review")
                    
                    print("[INFO] Verificando estado de sesion...")
                    time.sleep(6) 
                    
                    url_actual = driver.current_url.lower()
                    if "okta" in url_actual or "login" in url_actual:
                        if MODO_HEADLESS:
                            print("\n[ERROR] Okta pide login pero estas en modo Headless. Apaga el modo Headless para el primer logueo.")
                            driver.quit()
                            return
                        else:
                            print("\n[ATENCION] PANTALLA DE LOGIN DETECTADA. Tienes 60 segundos para ingresar tus datos...")
                            time.sleep(60)
                    else:
                        print("  [SISTEMA] Sesion valida detectada. Saltando login.")

                    if not MODO_HEADLESS:
                        driver.minimize_window()

                # Instanciamos los nuevos scrapers
                scraper_rev = ReviewScraper(driver)
                scraper_shift = ShiftsTrimmingScraper(driver)

                # Limpieza previa
                archivos_viejos = glob.glob(os.path.join(scraper_rev.download_dir, "*.csv"))
                for f in archivos_viejos:
                    try: os.remove(f)
                    except: pass
                
                # FLUJO REVIEW (Individual por ciudad)
                print("\n[INFO] Iniciando procesamiento de REVIEW...")
                for ciudad in lista_ciudades:
                    scraper_rev.procesar_ciudad_fechas_review(ciudad, lista_fechas)

                # FLUJO SHIFTS (Masivo y consolidado)
                print("\n[INFO] Iniciando procesamiento de SHIFT TRIMMING (Lote masivo)...")
                scraper_shift.ejecutar_flujo_scheduler(lista_ciudades, lista_fechas)
                # PRUEBASSSSSSSSSSSSS
                limpiar_y_subir_archivos_en_lote(scraper_rev.download_dir, num_ciclo_actual, fecha_medicion_fija, hora_medicion_fija)

                print("[SISTEMA] Tareas del ciclo completadas.")
                
                if not MODO_PRUEBA:
                    print("[SISTEMA] Cerrando navegador y liberando memoria RAM...")
                    driver.quit()
                else:
                    print("[SISTEMA] Modo prueba activo: Se mantiene la ventana abierta.")

                if ciclo < total_ciclos - 1: 
                    print(f"\n[INFO] Ciclo {num_ciclo_actual} finalizado exitosamente. El bot dormira profundamente por {intervalo} minutos.")
                    time.sleep(intervalo * 60)

            except KeyboardInterrupt:
                print("\n" + "="*50)
                print("[INFO] PROCESO DETENIDO MANUALMENTE.")
                print("="*50)
                if driver and not MODO_PRUEBA:
                    try: driver.quit()
                    except: pass
                break
            except Exception as e:
                print(f"\n[ERROR CRITICO] El ciclo {num_ciclo_actual} fallo: {e}")
                if driver and not MODO_PRUEBA:
                    try: driver.quit()
                    except: pass
                
                if ciclo < total_ciclos - 1:
                    print("[SISTEMA] Intentando recuperar en el proximo ciclo en 60 segundos...")
                    time.sleep(60)

        print("\n[PROCESO TERMINADO] El programa ha finalizado todas sus tareas programadas.")

    finally:
        preventer.stop()

if __name__ == "__main__":
    main()