# -*- coding: utf-8 -*-
import os
import time
import glob 
import datetime
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

class RoosterScraper:
    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(self.driver, 15)
        self.download_dir = self._configurar_directorio()
        self.ultima_descarga_review = 0 

    def _configurar_directorio(self):
        directorio_base = Path(__file__).resolve().parent
        ruta_descargas = str(directorio_base / "data_plan_escacez")
        
        if not os.path.exists(ruta_descargas):
            os.makedirs(ruta_descargas)
            print(f"[SISTEMA] Carpeta creada: {ruta_descargas}")
        else:
            print(f"[SISTEMA] Carpeta de descargas detectada: {ruta_descargas}")

        self.driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": ruta_descargas
        })
        print("[SISTEMA] Ruta de descargas configurada exitosamente.")
        return ruta_descargas

    # =================================================================
    # FUNCION DE CLIC BLINDADO (SOLO PARA MENÚS Y CALENDARIOS)
    # =================================================================
    def _forzar_clic(self, elemento):
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elemento)
            time.sleep(0.5)
            elemento.click()
        except:
            self.driver.execute_script("""
                var el = arguments[0];
                el.scrollIntoView({block: 'center'});
                el.focus();
                var evDown = new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window});
                var evUp = new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window});
                var evClick = new MouseEvent('click', {bubbles: true, cancelable: true, view: window});
                var evChange = new Event('change', {bubbles: true});
                
                el.dispatchEvent(evDown);
                el.dispatchEvent(evUp);
                el.dispatchEvent(evClick);
                el.dispatchEvent(evChange);
                try { el.click(); } catch(e){}
            """, elemento)

    # =================================================================
    # FUNCIONES DE NAVEGACION AGRESIVA
    # =================================================================
    def _navegar_mes(self, anio_objetivo, mes_objetivo):
        MESES_ES = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
            "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }

        for _ in range(24):
            tiempo_limite = time.time() + 10
            texto = ""
            
            while time.time() < tiempo_limite:
                encabezados = self.driver.find_elements(By.XPATH, "//*[contains(@class, 'DatePickerTopBar-MonthYearSelectorToggle')]")
                for enc in reversed(encabezados):
                    try:
                        t = enc.text.strip() or enc.get_attribute("textContent").strip()
                        if t:
                            texto = t.lower()
                            break
                    except: pass
                if texto: break
                time.sleep(0.5)

            mes_actual = None
            anio_actual = None
            for token in texto.split():
                if token in MESES_ES:
                    mes_actual = MESES_ES[token]
                try:
                    val = int(token)
                    if 2000 <= val <= 2100:
                        anio_actual = val
                except ValueError: pass

            if mes_actual is None or anio_actual is None:
                raise Exception(f"[CAL] No se pudo interpretar el calendario: '{texto}'")

            if mes_actual == mes_objetivo and anio_actual == anio_objetivo:
                return

            if (anio_actual, mes_actual) < (anio_objetivo, mes_objetivo):
                xpath_btn = "//button[contains(@class, 'DatePickerTopBar-MonthNavigationButtonForward')]"
            else:
                xpath_btn = "//button[contains(@class, 'DatePickerTopBar-MonthNavigationButtonBackward')]"
            
            botones = self.driver.find_elements(By.XPATH, xpath_btn)
            for btn in reversed(botones):
                try:
                    self._forzar_clic(btn)
                    break
                except: pass
            time.sleep(0.5)

        raise Exception(f"[CAL] No se pudo navegar al mes {mes_objetivo}/{anio_objetivo}.")

    def _seleccionar_dia(self, dia, mes, anio):
        mes_dom = mes - 1
        xpath_dia = f"//div[contains(@class, 'DatePickerDaySelector-Day') and @data-day='{dia}' and @data-month='{mes_dom}' and @data-year='{anio}']"
        
        tiempo_limite = time.time() + 10
        exito = False
        
        while time.time() < tiempo_limite:
            elementos = self.driver.find_elements(By.XPATH, xpath_dia)
            for el in reversed(elementos):
                try:
                    self._forzar_clic(el)
                    exito = True
                    break
                except: pass
            
            if exito: break
            time.sleep(0.5)
            
        if not exito:
            raise Exception(f"No se pudo hacer clic en el dia {dia}.")
        time.sleep(0.5)

    # =================================================================
    # FUNCIONES DE ESPERA Y RENOMBRADO DINAMICO
    # =================================================================
    def _esperar_y_renombrar_review(self, ciudad, cantidad_anterior, fecha):
        fecha_str = fecha.replace('.', '_')
        nuevo_nombre = f"review-cl-{ciudad}-{fecha_str}.csv"
        ruta_nueva = os.path.join(self.download_dir, nuevo_nombre)

        # Usamos tiempo cronometrado real (90 segundos completos)
        tiempo_limite = time.time() + 90
        
        while time.time() < tiempo_limite:
            archivos_csv = glob.glob(os.path.join(self.download_dir, "*.csv"))
            
            archivos_candidatos = [f for f in archivos_csv if os.path.basename(f).startswith("review-") and "_" not in os.path.basename(f)]
            descargas_pendientes = glob.glob(os.path.join(self.download_dir, "*.crdownload"))
            
            if len(archivos_candidatos) > cantidad_anterior and not descargas_pendientes:
                ultimo_archivo = max(archivos_candidatos, key=os.path.getctime)
                try:
                    if os.path.exists(ruta_nueva):
                        os.remove(ruta_nueva)
                    os.rename(ultimo_archivo, ruta_nueva)
                    print(f"  [SISTEMA] Archivo etiquetado como: {nuevo_nombre}")
                    return True
                except PermissionError:
                    pass
                except Exception as e:
                    print(f"  [SISTEMA] Error al etiquetar archivo: {e}")
                    return False
                    
            time.sleep(0.5)
            
        return False

    def _esperar_y_renombrar_shift_trimming(self, ciudad, cantidad_anterior, fecha):
        tiempo_espera = 0
        fecha_str = fecha.replace('.', '_')
        nuevo_nombre = f"shifts-trimming-cl-{ciudad}-{fecha_str}.csv"
        ruta_nueva = os.path.join(self.download_dir, nuevo_nombre)

        while tiempo_espera < 15:
            archivos_csv = glob.glob(os.path.join(self.download_dir, "*.csv"))
            archivos_candidatos = [f for f in archivos_csv if "-cl-" not in os.path.basename(f)]
            descargas_pendientes = glob.glob(os.path.join(self.download_dir, "*.crdownload"))
            
            if len(archivos_candidatos) > cantidad_anterior and not descargas_pendientes:
                ultimo_archivo = max(archivos_candidatos, key=os.path.getctime)
                try:
                    if os.path.exists(ruta_nueva):
                        os.remove(ruta_nueva)
                    os.rename(ultimo_archivo, ruta_nueva)
                    print(f"  [SISTEMA] Archivo etiquetado como: {nuevo_nombre}")
                    return True
                except PermissionError:
                    pass
                except Exception as e:
                    print(f"  [SISTEMA] Error al etiquetar archivo: {e}")
                    return False
                    
            time.sleep(0.5)
            tiempo_espera += 1
            
        return False

    # =================================================================
    # PESTAÑA REVIEW (LOTE POR CIUDAD)
    # =================================================================
    def seleccionar_ciudad_review(self, ciudad_destino="Santiago"):
        print(f"[ROOSTER] Seleccionando ciudad en menu global: {ciudad_destino}...")
        
        for intento in range(3):
            try:
                caja_dropdown = self.wait.until(
                    EC.presence_of_element_located((By.XPATH, "//div[@data-testid='HeaderNavigationSelectorRoot']"))
                )
                self._forzar_clic(caja_dropdown)
                time.sleep(1)
                
                opcion_ciudad = WebDriverWait(self.driver, 4).until(
                    EC.presence_of_element_located((By.XPATH, f"//*[text()='{ciudad_destino}']"))
                )
                self._forzar_clic(opcion_ciudad)
                time.sleep(1)
                return
            except Exception as e:
                print(f"  [ROOSTER] Reintentando abrir menu de ciudad... ({intento+1}/3)")
                time.sleep(2)
                
        raise Exception(f"No se pudo seleccionar la ciudad {ciudad_destino}.")

    def configurar_fechas_review(self, fecha_inicio: str, fecha_fin: str):
        dia_i, mes_i, anio_i = (int(x) for x in fecha_inicio.split("."))
        dia_f, mes_f, anio_f = (int(x) for x in fecha_fin.split("."))

        self.driver.execute_script("window.scrollTo(0, 0);")
        try:
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
        except: pass
        time.sleep(1)

        calendario_abierto = False
        for intento in range(3):
            try:
                inputs_fecha = self.driver.find_elements(By.XPATH, "//input[@data-testid='TextInputInput']")
                for inp in inputs_fecha:
                    self._forzar_clic(inp)
                    time.sleep(1.5) 
            except Exception:
                pass

            encabezados = self.driver.find_elements(By.XPATH, "//*[contains(@class, 'DatePickerTopBar-MonthYearSelectorToggle')]")
            for enc in encabezados:
                t = enc.text.strip() or enc.get_attribute("textContent").strip()
                if t:
                    calendario_abierto = True
                    break
            
            if calendario_abierto:
                break
            else:
                print(f"  [ROOSTER] El calendario no se abrio. Reintentando apertura ({intento + 1}/3)...")
                time.sleep(2) 
        
        if not calendario_abierto:
            raise Exception("[CAL] No se pudo abrir el widget del calendario.")

        self._navegar_mes(anio_i, mes_i)
        self._seleccionar_dia(dia_i, mes_i, anio_i)
        if (anio_f, mes_f) != (anio_i, mes_i):
            self._navegar_mes(anio_f, mes_f)
        self._seleccionar_dia(dia_f, mes_f, anio_f)
        time.sleep(1)

        try:
            self.driver.execute_script("document.body.click();")
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
        except: pass
        time.sleep(0.5)

    def descargar_csv(self):
        tiempo_actual = time.time()
        tiempo_transcurrido = tiempo_actual - self.ultima_descarga_review
        
        if self.ultima_descarga_review > 0 and tiempo_transcurrido < 62:
            tiempo_espera = 62 - tiempo_transcurrido
            print(f"  [ROOSTER] Esperando {int(tiempo_espera)}s restantes del cooldown para la plataforma...")
            time.sleep(tiempo_espera)
            
        time.sleep(3)
        
        # NUEVO: Calculamos la cantidad exacta justo ANTES de hacer clic, después del cooldown
        archivos_csv = glob.glob(os.path.join(self.download_dir, "*.csv"))
        cantidad = len([f for f in archivos_csv if os.path.basename(f).startswith("review-") and "_" not in os.path.basename(f)])
        
        for intento in range(3):
            try:
                boton_exportar = self.wait.until(
                    EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Exportar a CSV')]"))
                )
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", boton_exportar)
                time.sleep(0.5)
                
                self.driver.execute_script("arguments[0].click();", boton_exportar)
                print("  [ROOSTER] Clic de descarga ejecutado.")
                
                self.ultima_descarga_review = time.time()
                return cantidad # Retornamos el conteo correcto
            except Exception as e:
                if "stale" in str(e).lower() or "not attached" in str(e).lower():
                    time.sleep(2)
                else:
                    raise e
        raise Exception("No se pudo hacer clic en exportacion.")

    def procesar_ciudad_fechas_review(self, ciudad, lista_fechas):
        print("\n" + "="*50)
        print(f"INICIANDO EXTRACCION (REVIEW) - CIUDAD: {ciudad}")
        print("="*50)
        
        try:
            self.driver.get("https://cl.us.logisticsbackoffice.com/dashboard/rooster/review")
            time.sleep(3)
            # Solo seteamos la resolución, NO maximizamos
            self.driver.set_window_size(1920, 1080)
            self.driver.refresh()
            time.sleep(5)
            self.seleccionar_ciudad_review(ciudad) 
        except Exception as e:
            print(f"[ROOSTER] Error inicial al cargar Review para {ciudad}: {e}")
            return
            
        for fecha in lista_fechas:
            try:
                print(f"\n[ROOSTER] Preparando extraccion para el {fecha}...")
                self.configurar_fechas_review(fecha, fecha)
                
                for intento in range(3):
                    try: self.driver.execute_script("document.body.click();")
                    except: pass
                    time.sleep(1)
                    
                    try:
                        # Obtenemos la cantidad directamente de la funcion de descarga
                        cantidad_anterior = self.descargar_csv()
                        exito = self._esperar_y_renombrar_review(ciudad, cantidad_anterior, fecha)
                        
                        if exito:
                            print(f"  [ROOSTER] Descarga confirmada para {fecha}.")
                            break
                        else:
                            print(f"  [ROOSTER] Archivo no detectado (Intento {intento + 1}).")
                    except Exception as e:
                        print(f"  [ROOSTER] Fallo en intento {intento + 1}: {e}")
                        time.sleep(1)
            except Exception as e:
                print(f"  [ROOSTER] Error critico en la fecha {fecha}: {e}")
                print("  [ROOSTER] Forzando F5 y saltando a la siguiente fecha...")
                self.driver.refresh()
                time.sleep(4)
                try: self.seleccionar_ciudad_review(ciudad)
                except: pass
        
        print(f"\n[ROOSTER] Flujo Review completado para {ciudad}.")

    # =================================================================
    # PESTAÑA SHIFT TRIMMING (LOTE POR CIUDAD)
    # =================================================================
    def procesar_ciudad_fechas_scheduler(self, ciudad, lista_fechas):
        print("\n" + "="*50)
        print(f"INICIANDO EXTRACCION (SHIFT TRIMMING) - CIUDAD: {ciudad}")
        print("="*50)

        try:
            self.driver.get("https://cl.us.logisticsbackoffice.com/dashboard/rooster/scheduler")
            time.sleep(3)
            # Solo seteamos la resolución, NO maximizamos
            self.driver.set_window_size(1920, 1080)
            self.driver.refresh()
            time.sleep(5)
            self.seleccionar_ciudad_review(ciudad)
        except Exception as e:
            print(f"[ROOSTER] Error inicial al cargar Scheduler para {ciudad}: {e}")
            return
            
        for fecha in lista_fechas:
            print(f"\n[ROOSTER] Preparando Shift Trimming para el {fecha}...")
            
            try:
                btn_bulk = self.wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Bulk actions')]")))
                self.driver.execute_script("arguments[0].click();", btn_bulk)
                time.sleep(1)
                
                btn_trimming = self.wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'MenuElement-Content') and contains(., 'Shift trimming')]")))
                self._forzar_clic(btn_trimming)
                time.sleep(2)

                input_sp = self.wait.until(EC.presence_of_element_located((By.XPATH, "//label[contains(., 'Starting points')]/ancestor::div[contains(@class, 'FormField-Root')]//input")))
                self._forzar_clic(input_sp)
                time.sleep(1)
                
                opcion_all = self.wait.until(EC.presence_of_element_located((By.XPATH, "//*[text()='Select all']")))
                self._forzar_clic(opcion_all)
                time.sleep(1)
                
                try:
                    self.driver.execute_script("document.body.click();")
                except: pass

                dia, mes, anio = (int(x) for x in fecha.split("."))
                
                input_start = self.wait.until(EC.presence_of_element_located((By.XPATH, "//label[contains(., 'Start date')]/ancestor::div[contains(@class, 'FormField-Root')]//input")))
                self._forzar_clic(input_start)
                time.sleep(1)
                
                self._navegar_mes(anio, mes)
                self._seleccionar_dia(dia, mes, anio)
                time.sleep(0.5)

                try: self.driver.execute_script("document.body.click();")
                except: pass
                time.sleep(1)

                input_end = self.wait.until(EC.presence_of_element_located((By.XPATH, "//label[contains(., 'End date')]/ancestor::div[contains(@class, 'FormField-Root')]//input")))
                self._forzar_clic(input_end)
                time.sleep(1)
                
                self._navegar_mes(anio, mes)
                self._seleccionar_dia(dia, mes, anio)
                time.sleep(0.5)

                radio_unassigned = self.wait.until(EC.presence_of_element_located((By.XPATH, "//label[.//div[contains(text(), 'Unassigned shifts')]]")))
                self._forzar_clic(radio_unassigned)
                time.sleep(1)

                btn_apply = self.wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Apply filters')]")))
                self.driver.execute_script("arguments[0].click();", btn_apply)
                time.sleep(4)

                descarga_exitosa = False
                for intento in range(2):
                    try:
                        btn_download = WebDriverWait(self.driver, 2).until(
                            EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Download CSV list of selected shifts')]"))
                        )
                        self.driver.execute_script("arguments[0].click();", btn_download)
                        print("  [ROOSTER] Descarga iniciada.")
                        
                        cantidad_anterior = len([f for f in glob.glob(os.path.join(self.download_dir, "*.csv")) if "-cl-" not in os.path.basename(f)])
                        
                        exito = self._esperar_y_renombrar_shift_trimming(ciudad, cantidad_anterior, fecha)
                        if exito:
                            print(f"  [ROOSTER] Descarga confirmada para {fecha}.")
                            descarga_exitosa = True
                            break
                    except Exception:
                        time.sleep(1)
                
                if not descarga_exitosa:
                    print(f"  [ROOSTER] Omitiendo {fecha}: Probablemente 0 turnos libres o descarga fallida.")

            except Exception as e:
                 print(f"  [ROOSTER] Falla especifica en fecha {fecha}: {e}")
                 print("  [ROOSTER] Forzando F5 y saltando a la siguiente fecha...")
                 self.driver.get("https://cl.us.logisticsbackoffice.com/dashboard/rooster/scheduler")
                 time.sleep(4)

        print(f"\n[ROOSTER] Flujo Shift Trimming completado para {ciudad}.")