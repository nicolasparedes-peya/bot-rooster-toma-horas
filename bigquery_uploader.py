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
        print(f"[BIGQUERY] Advertencia: Error extrayendo zonas. Se subira sin zone_name. Error: {e}")
        df_zonas = pd.DataFrame(columns=['zone_name', 'starting_point'])

    df_review_list = []
    df_slots_list = []

    print("[BIGQUERY] Consolidando y deduplicando data en memoria...")
    
    for archivo in lista_archivos:
        nombre_fichero = os.path.basename(archivo)
        
        try:
            df = pd.read_csv(archivo)
            df.columns = df.columns.str.strip()
            if df.empty:
                continue
        except Exception:
            continue

        if nombre_fichero.startswith("review-cl-"):
            ciu = nombre_fichero.replace("review-cl-", "").split("-")[0].replace('.csv', '').title()
            df['ciudad_procesada'] = ciu
            df_review_list.append(df)

        elif nombre_fichero.startswith("shifts-trimming-cl-"):
            ciu = nombre_fichero.replace("shifts-trimming-cl-", "").split("-")[0].replace('.csv', '').title()
            df['ciudad_procesada'] = ciu
            df_slots_list.append(df)

    registros_master = []

    # =================================================================
    # PROCESAMIENTO: REVIEW (TURNOS TOMADOS)
    # =================================================================
    if df_review_list:
        df_rev_consolidado = pd.concat(df_review_list, ignore_index=True)
        df_rev_consolidado = df_rev_consolidado.drop_duplicates()

        col_sd, col_st = 'planned start date', 'planned start time'
        col_ed, col_et = 'planned end date', 'planned end time'
        col_sp = 'starting point'

        if all(col in df_rev_consolidado.columns for col in [col_sd, col_st, col_ed, col_et, col_sp]):
            df_rev_consolidado['start_dt'] = pd.to_datetime(df_rev_consolidado[col_sd] + ' ' + df_rev_consolidado[col_st], format='mixed')
            df_rev_consolidado['end_dt'] = pd.to_datetime(df_rev_consolidado[col_ed] + ' ' + df_rev_consolidado[col_et], format='mixed')

            for _, row in df_rev_consolidado.iterrows():
                start, end = row['start_dt'], row['end_dt']
                sp_actual = str(row[col_sp]).strip()
                ciudad = row['ciudad_procesada']
                
                curr = start
                while curr < end:
                    next_hour = curr.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
                    overlap_end = min(next_hour, end)
                    duration_hours = (overlap_end - curr).total_seconds() / 3600.0

                    # Inyectamos en lista maestra
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

    # =================================================================
    # PROCESAMIENTO: SHIFTS-TRIMMING (DISPONIBILIDAD Y NO TOMADOS)
    # =================================================================
    if df_slots_list:
        df_slots_consolidado = pd.concat(df_slots_list, ignore_index=True)
        df_slots_consolidado = df_slots_consolidado.drop_duplicates()

        col_sd, col_st = 'start date', 'start time (local)'
        col_ed, col_et = 'end date', 'end time (local)'
        col_sp, col_slots = 'starting point name', 'slots'
        col_employee = 'employee id'

        has_employee = col_employee in df_slots_consolidado.columns

        if all(col in df_slots_consolidado.columns for col in [col_sd, col_st, col_ed, col_et, col_sp, col_slots]):
            df_slots_consolidado['start_dt'] = pd.to_datetime(df_slots_consolidado[col_sd] + ' ' + df_slots_consolidado[col_st], format='mixed')
            df_slots_consolidado['end_dt'] = pd.to_datetime(df_slots_consolidado[col_ed] + ' ' + df_slots_consolidado[col_et], format='mixed')

            for _, row in df_slots_consolidado.iterrows():
                start, end = row['start_dt'], row['end_dt']
                sp_actual = str(row[col_sp]).strip()
                slots_disponibles = float(row[col_slots])
                ciudad = row['ciudad_procesada']
                
                # Identificamos si es un turno NO TOMADO (vacío)
                is_untaken = False
                if has_employee:
                    is_untaken = pd.isna(row[col_employee])
                
                curr = start
                while curr < end:
                    next_hour = curr.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
                    overlap_end = min(next_hour, end)
                    duration_hours = (overlap_end - curr).total_seconds() / 3600.0

                    slots_ponderados = duration_hours * slots_disponibles
                    horas_no_tomadas = slots_ponderados if is_untaken else 0.0

                    # Inyectamos en lista maestra
                    registros_master.append({
                        'ciudad': ciudad,
                        'starting_point': sp_actual,
                        'fecha': curr.date(),
                        'hora': int(curr.hour),
                        'horas_trabajo': 0.0,
                        'horas_no_tomadas': horas_no_tomadas,
                        'slots_totales': slots_ponderados,
                        'ciclo': int(numero_ciclo)
                    })
                    curr = overlap_end

    # =================================================================
    # AGRUPACIÓN GLOBAL Y CRUCE DE ZONAS
    # =================================================================
    if registros_master:
        print("[BIGQUERY] Agrupando datos cruzados y calculando metricas maestras...")
        df_agrupado = pd.DataFrame(registros_master)
        
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
        # CÁLCULO FINAL: horas_totales_live (Tomados de Review + No tomados de Shifts)
        # -------------------------------------------------------------
        df_agrupado['horas_totales_live'] = df_agrupado['horas_trabajo'] + df_agrupado['horas_no_tomadas']

        # =================================================================
        # SUBIDA A BIGQUERY - TABLA 1: velocidad_toma_horas
        # =================================================================
        # Filtramos para no subir filas que son puro cero en ambas métricas
        df_rev_upload = df_agrupado[(df_agrupado['horas_trabajo'] > 0) | (df_agrupado['horas_totales_live'] > 0)].copy()
        
        if not df_rev_upload.empty:
            table_id_rev = "peya-chile.user_nicolas_paredes.velocidad_toma_horas"
            columnas_rev = ['ciudad', 'zone_name', 'starting_point', 'fecha', 'hora', 'ciclo', 'horas_trabajo', 'horas_totales_live', 'fecha_medicion', 'hora_medicion']
            df_rev_upload = df_rev_upload[[col for col in columnas_rev if col in df_rev_upload.columns]]

            try:
                job_config = bigquery.LoadJobConfig(
                    write_disposition="WRITE_APPEND",
                    schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION]
                )
                job = client.load_table_from_dataframe(df_rev_upload, table_id_rev, job_config=job_config)
                job.result()
                print(f"[BIGQUERY] Exito: Se subieron {len(df_rev_upload)} filas agrupadas a 'velocidad_toma_horas'.")
            except Exception as e:
                print(f"[BIGQUERY] Error subiendo Review: {e}")
