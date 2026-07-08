# -*- coding: utf-8 -*-
import os
import pandas as pd
import datetime
from google.cloud import bigquery
from google.auth import default

def procesar_y_subir_lote(lista_archivos, numero_ciclo, fecha_medicion_fija, hora_medicion_fija):
    try:
        credentials, project = default()
        client = bigquery.Client(credentials=credentials, project='peya-chile')
    except Exception as e:
        print(f"[BIGQUERY] Error autenticando con Google Cloud: {e}")
        return

    # =================================================================
    # EXTRACCIÓN DE MAPEO DE ZONAS (DWH)
    # =================================================================
    print("[BIGQUERY] Extrayendo mapeo de zonas desde DWH...")
    try:
        query_zonas = """
            SELECT DISTINCT
                z.name AS zone_name,
                sp.name AS starting_point
            FROM `fulfillment-dwh-production.curated_data_shared.countries` coun 
            LEFT JOIN UNNEST(coun.cities) c
            LEFT JOIN UNNEST(c.zones) z
            LEFT JOIN UNNEST(z.starting_points) sp ON sp.is_active
            WHERE country_code='cl'
        """
        df_zonas = client.query(query_zonas).to_dataframe()
        df_zonas['starting_point'] = df_zonas['starting_point'].astype(str).str.strip()
        df_zonas = df_zonas.drop_duplicates(subset=['starting_point'])
    except Exception as e:
        print(f"[BIGQUERY] Advertencia: Error extrayendo zonas. Se subira sin zone_name.")
        df_zonas = pd.DataFrame(columns=['zone_name', 'starting_point'])

    df_review_list = []
    df_slots_list = []

    print("[BIGQUERY] Consolidando y deduplicando data en memoria...")
    
    for archivo in lista_archivos:
        nombre_fichero = os.path.basename(archivo)
        
        try:
            df = pd.read_csv(archivo)
            # Limpieza extrema de columnas: a minúsculas y sin espacios
            df.columns = df.columns.str.lower().str.strip() 
            if df.empty:
                continue
        except Exception:
            continue

        if nombre_fichero.startswith("review-cl-"):
            ciu = nombre_fichero.replace("review-cl-", "").split("-")[0].replace('.csv', '').title()
            df['ciudad_procesada'] = ciu
            df_review_list.append(df)

        elif nombre_fichero.startswith("shifts-trimming-cl-"):
            if 'city' in df.columns:
                df['ciudad_procesada'] = df['city'].astype(str).str.strip().str.title()
            elif 'city name' in df.columns:
                df['ciudad_procesada'] = df['city name'].astype(str).str.strip().str.title()
            else:
                df['ciudad_procesada'] = "Consolidado" 
            df_slots_list.append(df)

    registros_master = []

    # =================================================================
    # PRE-PROCESAMIENTO: CONSOLIDACIÓN INICIAL PARA COMPARAR
    # =================================================================
    df_rev_consolidado = pd.concat(df_review_list, ignore_index=True).drop_duplicates() if df_review_list else pd.DataFrame()
    df_slots_consolidado = pd.concat(df_slots_list, ignore_index=True).drop_duplicates() if df_slots_list else pd.DataFrame()

    # =================================================================
    # NUEVO: DEDUPLICACIÓN POR 'SHIFT ID' (Prioridad: Archivo Shifts)
    # =================================================================
    if not df_rev_consolidado.empty and not df_slots_consolidado.empty:
        if 'shift id' in df_rev_consolidado.columns and 'shift id' in df_slots_consolidado.columns:
            total_rev_antes = len(df_rev_consolidado)
            
            # Obtenemos todos los IDs únicos del archivo de Shifts
            ids_en_shifts = df_slots_consolidado['shift id'].dropna().unique()
            
            # Filtramos Review: nos quedamos SOLO con las filas cuyo 'shift id' NO está en Shifts (~)
            df_rev_consolidado = df_rev_consolidado[~df_rev_consolidado['shift id'].isin(ids_en_shifts)]
            
            duplicados_eliminados = total_rev_antes - len(df_rev_consolidado)
            if duplicados_eliminados > 0:
                print(f"[DEBUG] Se eliminaron {duplicados_eliminados} turnos de Review por estar duplicados en Shifts.")
        else:
            print("[DEBUG] No se encontró la columna 'shift id'. Se omite la deduplicación.")

    # =================================================================
    # PROCESAMIENTO: REVIEW (TURNOS TOMADOS)
    # =================================================================
    if not df_rev_consolidado.empty:
        print(f"[DEBUG] Procesando {len(df_rev_consolidado)} filas finales de Review en memoria.")

        col_sd, col_st = 'planned start date', 'planned start time'
        col_ed, col_et = 'planned end date', 'planned end time'
        col_sp = 'starting point'

        columnas_actuales = df_rev_consolidado.columns.tolist()
        columnas_necesarias = [col_sd, col_st, col_ed, col_et, col_sp]
        
        faltan = [col for col in columnas_necesarias if col not in columnas_actuales]
        
        if not faltan:
            df_rev_consolidado['start_dt'] = pd.to_datetime(df_rev_consolidado[col_sd] + ' ' + df_rev_consolidado[col_st], format='mixed')
            df_rev_consolidado['end_dt'] = pd.to_datetime(df_rev_consolidado[col_ed] + ' ' + df_rev_consolidado[col_et], format='mixed')

            filas_procesadas_review = 0
            for _, row in df_rev_consolidado.iterrows():
                start, end = row['start_dt'], row['end_dt']
                sp_actual = str(row[col_sp]).strip()
                ciudad = row['ciudad_procesada']
                
                curr = start
                while curr < end:
                    next_hour = curr.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
                    overlap_end = min(next_hour, end)
                    duration_hours = (overlap_end - curr).total_seconds() / 3600.0

                    registros_master.append({
                        'ciudad': ciudad,
                        'starting_point': sp_actual,
                        'fecha': curr.date(),
                        'hora': int(curr.hour),
                        'horas_trabajo': duration_hours,
                        'horas_no_tomadas': 0.0,
                        'slots_totales': 0.0,
                        'ciclo': int(numero_ciclo)
                    })
                    curr = overlap_end
                    filas_procesadas_review += 1
            print(f"[DEBUG] Se inyectaron {filas_procesadas_review} bloques horarios de Review.")
        else:
            print(f"[ERROR DEBUG] El archivo Review no se procesó. Faltan estas columnas: {faltan}")
            print(f"Columnas detectadas en el archivo: {columnas_actuales}")


    # =================================================================
    # PROCESAMIENTO: SHIFTS-TRIMMING (HORAS LIBRES / UNASSIGNED)
    # =================================================================
    if df_slots_list:
        df_slots_consolidado = pd.concat(df_slots_list, ignore_index=True)
        df_slots_consolidado = df_slots_consolidado.drop_duplicates()

        # Las nuevas columnas según el archivo consolidado
        col_sd, col_st = 'start date', 'start time (local)'
        col_ed, col_et = 'end date', 'end time (local)'
        col_sp, col_slots = 'starting point name', 'slots'

        if all(col in df_slots_consolidado.columns for col in [col_sd, col_st, col_ed, col_et, col_sp, col_slots]):
            df_slots_consolidado['start_dt'] = pd.to_datetime(df_slots_consolidado[col_sd] + ' ' + df_slots_consolidado[col_st], format='mixed')
            df_slots_consolidado['end_dt'] = pd.to_datetime(df_slots_consolidado[col_ed] + ' ' + df_slots_consolidado[col_et], format='mixed')

            for _, row in df_slots_consolidado.iterrows():
                start, end = row['start_dt'], row['end_dt']
                sp_actual = str(row[col_sp]).strip()
                slots_disponibles = float(row[col_slots])
                ciudad = row['ciudad_procesada']
                
                curr = start
                while curr < end:
                    next_hour = curr.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
                    overlap_end = min(next_hour, end)
                    
                    # Fracción de hora (ej. 30 min = 0.5)
                    duration_hours = (overlap_end - curr).total_seconds() / 3600.0

                    # Como filtramos por "Unassigned", todo el slot es una hora libre
                    horas_no_tomadas = duration_hours * slots_disponibles

                    # Inyectamos en lista maestra
                    registros_master.append({
                        'ciudad': ciudad,
                        'starting_point': sp_actual,
                        'fecha': curr.date(),
                        'hora': int(curr.hour),
                        'horas_trabajo': 0.0,            # El archivo shifts no trae horas tomadas
                        'horas_no_tomadas': horas_no_tomadas, 
                        'slots_totales': horas_no_tomadas,
                        'ciclo': int(numero_ciclo)
                    })
                    curr = overlap_end

    # =================================================================
    # AGRUPACIÓN GLOBAL Y CRUCE DE ZONAS
    # =================================================================
    if registros_master:
        print("[BIGQUERY] Agrupando datos cruzados y calculando metricas maestras...")
        df_agrupado = pd.DataFrame(registros_master)
        
        # Al agrupar, suma las horas_trabajo (Review) y las horas_no_tomadas (Shifts) por ciudad, SP, fecha y hora
        df_agrupado = df_agrupado.groupby(
            ['ciudad', 'starting_point', 'fecha', 'hora', 'ciclo'], 
            as_index=False
        )[['horas_trabajo', 'horas_no_tomadas', 'slots_totales']].sum()

        df_agrupado['starting_point'] = df_agrupado['starting_point'].astype(str).str.strip()
        df_agrupado = df_agrupado.merge(df_zonas, on='starting_point', how='left')

        df_agrupado['fecha'] = pd.to_datetime(df_agrupado['fecha']).dt.strftime('%Y-%m-%d')
        df_agrupado['hora'] = df_agrupado['hora'].astype(int)
        df_agrupado['ciclo'] = df_agrupado['ciclo'].astype(int)
        df_agrupado['fecha_medicion'] = fecha_medicion_fija
        df_agrupado['hora_medicion'] = hora_medicion_fija

        # -------------------------------------------------------------
        # CÁLCULO FINAL: horas_totales_live (Tomadas de Review + Libres de Shifts)
        # -------------------------------------------------------------
        df_agrupado['horas_totales_live'] = df_agrupado['horas_trabajo'] + df_agrupado['horas_no_tomadas']

        # Renombramos la columna para que coincida exactamente con tu nueva tabla en BigQuery
        df_agrupado.rename(columns={'horas_no_tomadas': 'horas_libres'}, inplace=True)

        # =================================================================
        # SUBIDA A BIGQUERY
        # =================================================================
        # Filtramos para no subir filas que sean puro cero
        df_rev_upload = df_agrupado[(df_agrupado['horas_trabajo'] > 0) | (df_agrupado['horas_totales_live'] > 0)].copy()
        
        if not df_rev_upload.empty:
            table_id_rev = "peya-chile.user_nicolas_paredes.velocidad_toma_horas"
            
            # Aseguramos que la lista de columnas tenga el nuevo nombre 'horas_libres'
            columnas_rev = ['ciudad', 'zone_name', 'starting_point', 'fecha', 'hora', 'ciclo', 'horas_trabajo', 'horas_libres', 'horas_totales_live', 'fecha_medicion', 'hora_medicion']
            df_rev_upload = df_rev_upload[[col for col in columnas_rev if col in df_rev_upload.columns]]

            try:
                # ¡REACTIVAMOS LA SUBIDA!
                job_config = bigquery.LoadJobConfig(
                    write_disposition="WRITE_APPEND",
                    schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION]
                )
                job = client.load_table_from_dataframe(df_rev_upload, table_id_rev, job_config=job_config)
                job.result()
                print(f"[BIGQUERY] Exito: Se subieron {len(df_rev_upload)} filas agrupadas a 'velocidad_toma_horas_prueba'.")
            except Exception as e:
                print(f"[BIGQUERY] Error subiendo Review: {e}")
