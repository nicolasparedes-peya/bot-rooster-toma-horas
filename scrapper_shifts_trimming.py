# -*- coding: utf-8 -*-
import os
import time
import glob 
from datetime import datetime
import pandas as pd
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

class ShiftsTrimmingScraper:
    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(self.driver, 15)
        self.download_dir = self._configurar_directorio()

    def _configurar_directorio(self):
        directorio_base = Path(__file__).resolve().parent
        ruta_descargas = str(directorio_base / "data_plan_escacez")
        
        if not os.path.exists(ruta_descargas):
            os.makedirs(ruta_descargas)
            print(f"[SISTEMA] Carpeta creada: {ruta_descargas}")

        self.driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": ruta_descargas
        })
        return ruta_descargas

    # =================================================================
    # FUNCIONES BASE Y DE ROBUSTEZ (CLICS Y REACT)
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

    def _clic_fuera_calendario(self):
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            ActionChains(self.driver).move_to_element_with_offset(body, 5, 5).click().perform()
        except: pass
        try: self.driver.execute_script("document.body.click();")
        except: pass
        try:
            self.driver.execute_script("""
                var el = document.elementFromPoint(10, 10) || document.body;
                var evClick = new MouseEvent('click', {bubbles: true, cancelable: true, view: window});
                el.dispatchEvent(evClick);
            """)
        except: pass
        try: ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
        except: pass
        time.sleep(1.5)

    def _navegar_mes(self, anio_objetivo, mes_objetivo):
        MESES_ES = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, 
            "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
            "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, 
            "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
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
                if token in MESES_ES: mes_actual = MESES_ES[token]
                try:
                    val = int(token)
                    if 2000 <= val <= 2100: anio_actual = val
                except ValueError: pass

            if mes_actual is None or anio_actual is None:
                raise Exception(f"[CAL] No se pudo interpretar el calendario: '{texto}'")
            if mes_actual == mes_objetivo and anio_actual == anio_objetivo:
                return

            xpath_btn = "//button[contains(@class, 'DatePickerTopBar-MonthNavigationButtonForward')]" if (anio_actual, mes_actual) < (anio_objetivo, mes_objetivo) else "//button[contains(@class, 'DatePickerTopBar-MonthNavigationButtonBackward')]"
            botones = self.driver.find_elements(By.XPATH, xpath_btn)
            for btn in reversed(botones):
                try:
                    self.driver.execute_script("arguments[0].click();", btn)
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
                    self.driver.execute_script("arguments[0].click();", el)
                    exito = True
                    break
                except: pass
            if exito: break
            time.sleep(0.5)
        if not exito:
            raise Exception(f"No se pudo hacer clic en el dia {dia}. Revisa si la fecha existe.")
        time.sleep(0.5)

    # =================================================================
    # FUNCIONES DE DETECCIÓN Y RENOMBRADO (SNAPSHOT)
    # =================================================================
    def _tomar_fotografia_archivos(self):
        foto = set()
        for f in glob.glob(os.path.join(self.download_dir, "*.csv")):
            try: foto.add((f, os.path.getmtime(f)))
            except: pass
        return foto

    def _esperar_y_renombrar_fragmento(self, sufijo_dia, archivos_previos):
        nuevo_nombre = f"shifts-trimming-cl-{sufijo_dia}.csv"
        ruta_nueva = os.path.join(self.download_dir, nuevo_nombre)
        tiempo_limite = time.time() + 120 

        while time.time() < tiempo_limite:
            archivos_actuales = self._tomar_fotografia_archivos()
            nuevos_archivos = archivos_actuales - archivos_previos
            
            descargas_pendientes = glob.glob(os.path.join(self.download_dir, "*.crdownload")) + glob.glob(os.path.join(self.download_dir, "*.tmp"))
            
            if nuevos_archivos and not descargas_pendientes:
                archivos_ordenados = sorted(list(nuevos_archivos), key=lambda x: x[1], reverse=True)
                ultimo_archivo = archivos_ordenados[0][0]
                try:
                    if os.path.exists(ruta_nueva): os.remove(ruta_nueva)
                    os.rename(ultimo_archivo, ruta_nueva)
                    print(f"  [SISTEMA] Archivo etiquetado como: {nuevo_nombre}")
                    return True, ruta_nueva
                except PermissionError: pass
                except Exception as e:
                    print(f"  [SISTEMA] Error al etiquetar archivo: {e}")
                    return False, None
            time.sleep(0.5)
        return False, None

    # =================================================================
    # FLUJO PRINCIPAL: SCHEDULER (SHIFT TRIMMING BATCH)
    # =================================================================
    def ejecutar_flujo_scheduler(self, ciudades: list, lista_fechas: list):
        print("\n" + "="*50)
        print(f"INICIANDO EXTRACCIÓN CONSOLIDADA (SHIFT TRIMMING)")
        print("="*50)

        try:
            self.driver.get("https://cl.us.logisticsbackoffice.com/dashboard/rooster/scheduler")
            self.driver.refresh()
            time.sleep(4)

            print("[ROOSTER] Abriendo menú de Shift trimming...")
            btn_bulk = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Bulk actions')]")))
            btn_bulk.click()
            time.sleep(1)
            
            btn_trimming = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'MenuElement-Content') and contains(., 'Shift trimming')]")))
            btn_trimming.click()
            time.sleep(2)

            # -------------------------------------------------------------
            # SELECCIÓN MÚLTIPLE DE CIUDADES EN EL MODAL
            # -------------------------------------------------------------
            print("[ROOSTER] Configurando ciudades...")

            input_cities = self.wait.until(EC.presence_of_element_located(
                (By.XPATH, "//label[contains(., 'Cities')]/ancestor::div[contains(@class, 'FormField-Root')]//input")
            ))
            self.driver.execute_script("arguments[0].click();", input_cities)
            time.sleep(1)

            # LIMITAMOS LA BÚSQUEDA SOLO AL MENÚ DESPLEGABLE PARA EVITAR CLICS EN LA TABLA DE FONDO
            xpath_dropdown = "//div[@data-testid='DropdownOptionListContainer']"

            try:
                # 1er Clic: Selecciona todo
                opcion_all_cities = self.wait.until(EC.presence_of_element_located((By.XPATH, f"{xpath_dropdown}//*[text()='Select all']")))
                self.driver.execute_script("arguments[0].click();", opcion_all_cities)
                time.sleep(0.5)
                
                # 2do Clic: Deselecciona todo (re-buscamos por si React actualiza el DOM)
                opcion_all_cities_2 = self.wait.until(EC.presence_of_element_located((By.XPATH, f"{xpath_dropdown}//*[text()='Select all']")))
                self.driver.execute_script("arguments[0].click();", opcion_all_cities_2)
                time.sleep(0.5)
            except Exception as e:
                print(f"  [ROOSTER] Advertencia en Select all: {e}")

            for ciudad in ciudades:
                try:
                    # Búsqueda estricta SOLO dentro de la lista de opciones
                    xpath_ciudad = f"{xpath_dropdown}//div[@data-testid='OptionListItem']//*[text()='{ciudad}']"
                    
                    opcion_ciudad = self.wait.until(EC.presence_of_element_located((By.XPATH, xpath_ciudad)))
                    # Lo centramos en pantalla para que la barra de búsqueda no lo tape
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", opcion_ciudad)
                    time.sleep(0.2)
                    self.driver.execute_script("arguments[0].click();", opcion_ciudad)
                    time.sleep(0.2)
                except Exception as e:
                    print(f"  [ROOSTER] Advertencia: No se pudo seleccionar la ciudad '{ciudad}'.")
            
            try:
                flecha_dropdown = self.driver.find_element(By.XPATH, "//label[contains(., 'Cities')]/ancestor::div[contains(@class, 'FormField-Root')]//div[@data-testid='ExpansionIndicatorRoot']")
                self.driver.execute_script("arguments[0].click();", flecha_dropdown)
            except Exception:
                self.driver.execute_script("document.body.click();")
            time.sleep(1)

            # -------------------------------------------------------------
            # STARTING POINTS
            # -------------------------------------------------------------
            input_starting_points = self.wait.until(EC.presence_of_element_located(
                (By.XPATH, "//label[contains(., 'Starting points')]/ancestor::div[contains(@class, 'FormField-Root')]//input")
            ))
            self.driver.execute_script("arguments[0].click();", input_starting_points)
            time.sleep(1)
            
            try:
                opcion_all_sp = self.wait.until(EC.presence_of_element_located((By.XPATH, "//*[text()='Select all']")))
                self.driver.execute_script("arguments[0].click();", opcion_all_sp)
                time.sleep(1)
            except: pass
            
            try: self.driver.execute_script("document.body.click();")
            except: pass

            # -------------------------------------------------------------
            # BUCLE DIARIO (CHUNKING)
            # -------------------------------------------------------------
            archivos_diarios = [] 

            for fecha_str in lista_fechas:
                print(f"\n[ROOSTER] Extrayendo fragmento de turnos del {fecha_str}...")
                dia, mes, anio = (int(x) for x in fecha_str.split("."))

                # --- START DATE ---
                input_start = self.wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//label[contains(., 'Start date')]/ancestor::div[contains(@class, 'FormField-Root')]//input")
                ))
                try: input_start.click()
                except: self.driver.execute_script("arguments[0].click();", input_start)
                time.sleep(1)
                
                self._navegar_mes(anio, mes)
                self._seleccionar_dia(dia, mes, anio)
                time.sleep(0.5)

                try: self.driver.execute_script("document.body.click();")
                except: pass
                time.sleep(1)

                # --- END DATE ---
                input_end = self.wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//label[contains(., 'End date')]/ancestor::div[contains(@class, 'FormField-Root')]//input")
                ))
                try: input_end.click()
                except: self.driver.execute_script("arguments[0].click();", input_end)
                time.sleep(1)
                
                self._navegar_mes(anio, mes)
                self._seleccionar_dia(dia, mes, anio)
                time.sleep(0.5)

                # --- UNASSIGNED SHIFTS Y APLICAR ---
                radio_unassigned = self.wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//label[.//div[contains(text(), 'Unassigned shifts')]]")
                ))
                self.driver.execute_script("arguments[0].scrollIntoView(true);", radio_unassigned)
                time.sleep(0.5)
                self.driver.execute_script("arguments[0].click();", radio_unassigned)
                time.sleep(1)

                btn_apply = self.wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//button[contains(., 'Apply filters')]")
                ))
                self.driver.execute_script("arguments[0].click();", btn_apply)
                time.sleep(10)

                # --- DESCARGA DEL FRAGMENTO DIARIO CON SNAPSHOT ---
                basura_crdownload = glob.glob(os.path.join(self.download_dir, "*.crdownload"))
                for archivo_basura in basura_crdownload:
                    try: os.remove(archivo_basura)
                    except: pass

                descarga_exitosa = False
                for intento in range(2):
                    try:
                        btn_download = WebDriverWait(self.driver, 2).until(
                            EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Download CSV list of selected shifts')]"))
                        )
                        
                        archivos_previos = self._tomar_fotografia_archivos()
                        self.driver.execute_script("arguments[0].click();", btn_download)
                        print(f"  [ROOSTER] Esperando descarga del fragmento (Intento {intento+1})...")
                        
                        sufijo_dia = f"Dia-{fecha_str.replace('.', '_')}"
                        exito, ruta_parcial = self._esperar_y_renombrar_fragmento(sufijo_dia, archivos_previos)
                        
                        if exito:
                            print(f"  [ROOSTER] Archivo diario descargado exitosamente.")
                            archivos_diarios.append(ruta_parcial)
                            descarga_exitosa = True
                            break
                        else:
                            print(f"  [ROOSTER] Archivo no detectado en el intento {intento + 1}.")
                    except Exception:
                        print(f"  [ROOSTER] Boton de descarga no disponible (Intento {intento+1}/2).")
                        time.sleep(1)

                if not descarga_exitosa:
                    print(f"  [ROOSTER] ADVERTENCIA: Falló la descarga del {fecha_str} o no hay turnos en ese dia.")

            # -------------------------------------------------------------
            # FUSIÓN DE ARCHIVOS (MERGE CON PANDAS)
            # -------------------------------------------------------------
            if not archivos_diarios:
                print("[ROOSTER] Error: No se logro descargar ningun fragmento diario.")
                return None

            print(f"\n[SISTEMA] Fusionando {len(archivos_diarios)} archivos diarios...")
            
            try:
                dataframes = [pd.read_csv(archivo) for archivo in archivos_diarios]
                df_consolidado = pd.concat(dataframes, ignore_index=True)

                hora_final = datetime.now().strftime("%H_%M_%S")
                ruta_consolidado = os.path.join(self.download_dir, f"shifts-trimming-cl-Consolidado-{hora_final}.csv")
                
                df_consolidado.to_csv(ruta_consolidado, index=False)
                print(f"[SISTEMA] Archivo consolidado maestro creado: {os.path.basename(ruta_consolidado)}")

                # Limpieza BLINDADA (Corregida): Borramos basura, pero respetamos el Review y el Consolidado
                todos_los_csv = glob.glob(os.path.join(self.download_dir, "*.csv"))
                for archivo_borrar in todos_los_csv:
                    nombre_archivo = os.path.basename(archivo_borrar)
                    
                    # Si NO es el consolidado nuevo, y NO es un archivo de review, lo eliminamos
                    if archivo_borrar != ruta_consolidado and not nombre_archivo.startswith("review-"):
                        try: os.remove(archivo_borrar)
                        except: pass

                return ruta_consolidado

            except Exception as e:
                print(f"[SISTEMA] Error critico al fusionar los CSV: {e}")
                return None

        except Exception as e:
            print(f"[ROOSTER] Error critico en el flujo Scheduler: {e}")
            return None