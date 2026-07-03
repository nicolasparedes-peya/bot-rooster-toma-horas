# -*- coding: utf-8 -*-
import time
import datetime
import glob
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from interfaz import iniciar_interfaz
from scrapper_rooster import RoosterScraper
from bigquery_uploader import procesar_y_subir_lote

# =================================================================
# CONFIGURACION GLOBAL
# =================================================================
MODO_PRUEBA = True      # True: Se conecta a un Chrome ya abierto en el puerto 9222.
MODO_HEADLESS = False   # True: Ejecuta Chrome 100% invisible (Requiere MODO_PRUEBA = False).

def limpiar_y_subir_archivos_en_lote(scraper, num_ciclo_actual, fecha_medicion_fija, hora_medicion_fija):
    archivos_locales = glob.glob(os.path.join(scraper.download_dir, "*.csv"))
    
    if not archivos_locales:
        print("\n[INFO] No hay archivos CSV descargados para subir a BigQuery en este ciclo.")
        return

    print(f"\n[BIGQUERY] Consolidando {len(archivos_locales)} archivos locales para subir en lote...")
    
    procesar_y_subir_lote(archivos_locales, num_ciclo_actual, fecha_medicion_fija, hora_medicion_fija)
    
    for archivo in archivos_locales:
        try:
            os.remove(archivo)
        except:
            pass

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

    print("\n" + "="*50)
    print(f"DATOS: {len(lista_ciudades)} ciudades seleccionadas | {len(lista_fechas)} dias a analizar")
    print(f"CONFIGURACION: Duracion {horas}h | Descargas cada {intervalo} min ({total_ciclos} ciclos totales)")
    print("="*50)

    print("[SISTEMA] Iniciando Chrome...")
    try:
        chrome_options = Options()
        
        # --- FLAGS ANTI-SUSPENSION EN SEGUNDO PLANO ---
        # Mantienen activo el motor de Chrome aunque la ventana este minimizada
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        
        if MODO_HEADLESS and not MODO_PRUEBA:
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--disable-gpu")
            print("[INFO] MODO HEADLESS ACTIVADO. Chrome correra de forma invisible.")
        
        if MODO_PRUEBA:
            print("[INFO] MODO PRUEBA ACTIVADO. Conectando a navegador existente en el puerto 9222...")
            chrome_options.debugger_address = "127.0.0.1:9222"
            driver = webdriver.Chrome(options=chrome_options)
            driver.maximize_window()
        else:
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            driver = webdriver.Chrome(options=chrome_options)
            
            driver.get("https://cl.us.logisticsbackoffice.com/dashboard/rooster/review")
            
            if not MODO_HEADLESS:
                print("\n[ATENCION] TIENES 60 SEGUNDOS PARA INICIAR SESION EN OKTA...")
                time.sleep(60)
                
                # Minimizar ventana para no interrumpir al usuario
                print("\n[INFO] Minimizando Chrome. Puedes seguir usando tu computadora...")
                driver.minimize_window()
            else:
                print("\n[INFO] Esperando carga inicial de la plataforma en modo invisible...")
                time.sleep(15)

        scraper = RoosterScraper(driver)

        archivos_viejos = glob.glob(os.path.join(scraper.download_dir, "*.csv"))
        if archivos_viejos:
            for f in archivos_viejos:
                try: os.remove(f)
                except: pass
        
        for ciclo in range(total_ciclos):
            num_ciclo_actual = ciclo + 1
            
            ahora_ciclo = datetime.datetime.now()
            fecha_medicion_fija = ahora_ciclo.strftime("%Y-%m-%d")
            hora_medicion_fija = ahora_ciclo.strftime("%H:%M:%S")

            print(f"\n" + "*"*50)
            print(f"INICIANDO CICLO {num_ciclo_actual} DE {total_ciclos} (Hora de ciclo: {hora_medicion_fija})")
            print("*"*50)
            
            print("\n[INFO] Iniciando procesamiento de REVIEW...")
            for ciudad in lista_ciudades:
                scraper.procesar_ciudad_fechas_review(ciudad, lista_fechas)

            # (PAUSADO PARA TESTEO)
            # print("\n[INFO] Cambiando a modulo SHIFT TRIMMING...")
            # for ciudad in lista_ciudades:
            #     scraper.procesar_ciudad_fechas_scheduler(ciudad, lista_fechas)

            limpiar_y_subir_archivos_en_lote(scraper, num_ciclo_actual, fecha_medicion_fija, hora_medicion_fija)

            if ciclo < total_ciclos - 1: 
                print(f"\n[INFO] Ciclo {num_ciclo_actual} terminado. Iniciando espera interactiva de {intervalo} minutos...")
                
                minutos_transcurridos = 0
                while minutos_transcurridos < intervalo:
                    time.sleep(60)
                    minutos_transcurridos += 1
                    
                    # Refresh estricto cada 5 minutos
                    if minutos_transcurridos % 5 == 0 and minutos_transcurridos < intervalo:
                        try:
                            driver.refresh()
                            print(f"  [SISTEMA] Keep-Alive: Refrescando navegador ({minutos_transcurridos}/{intervalo} min) para mantener sesion activa...")
                        except Exception:
                            pass

        print("\n[PROCESO TERMINADO] El programa ha finalizado exitosamente todas sus tareas.")
        
        if not MODO_PRUEBA:
            driver.quit()
        
    except KeyboardInterrupt:
        print("\n" + "="*50)
        print("[INFO] PROCESO DETENIDO MANUALMENTE.")
        print("="*50)
        if not MODO_PRUEBA:
            try: driver.quit()
            except: pass
    except Exception as e:
        print(f"\n[ERROR CRITICO] El proceso fallo: {e}")
        if not MODO_PRUEBA:
            try: driver.quit()
            except: pass

if __name__ == "__main__":
    main()