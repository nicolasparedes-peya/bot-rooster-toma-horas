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

    registros_review = []
    registros_slots = []

    # =================================================================
    # PROCESAMIENTO LOGICA REVIEW
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

                    # Asignamos la fecha y hora exactas en la que ocurre esta fracción del turno
                    fecha_real = curr.date()
                    hora_real = int(curr.hour)

                    registros_review.append({
                        'ciudad': ciudad,
                        'starting_point': sp_actual,
                        'fecha': fecha_real,
                        'hora': hora_real,
                        'horas_trabajo': duration_hours,
                        'ciclo': int(numero_ciclo)
                    })
                    curr = overlap_end

    # =================================================================
    # PROCESAMIENTO LOGICA SHIFTS-TRIMMING
    # =================================================================
    if df_slots_list:
        df_slots_consolidado = pd.concat(df_slots_list, ignore_index=True)
        df_slots_consolidado = df_slots_consolidado.drop_duplicates()

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
                    duration_hours = (overlap_end - curr).total_seconds() / 3600.0

                    slots_ponderados = duration_hours * slots_disponibles
                    
                    # Asignamos la fecha y hora exactas en la que ocurre esta fracción de slots
                    fecha_real = curr.date()
                    hora_real = int(curr.hour)

                    registros_slots.append({
                        'ciudad': ciudad,
                        'starting_point': sp_actual,
                        'fecha': fecha_real,
                        'hora': hora_real,
                        'slots_totales': slots_ponderados,
                        'ciclo': int(numero_ciclo)
                    })
                    curr = overlap_end

    # =================================================================
    # SUBIDA AGRUPADA A BIGQUERY - TABLA REVIEW
    # =================================================================
    if registros_review:
        table_id_rev = "peya-chile.user_nicolas_paredes.velocidad_toma_horas"
        df_final_rev = pd.DataFrame(registros_review)
        df_final_rev = df_final_rev.groupby(
            ['ciudad', 'starting_point', 'fecha', 'hora', 'ciclo'], 
            as_index=False
        )['horas_trabajo'].sum()

        df_final_rev['starting_point'] = df_final_rev['starting_point'].astype(str).str.strip()
        df_final_rev = df_final_rev.merge(df_zonas, on='starting_point', how='left')

        df_final_rev['fecha'] = pd.to_datetime(df_final_rev['fecha']).dt.strftime('%Y-%m-%d')
        df_final_rev['hora'] = df_final_rev['hora'].astype(int)
        df_final_rev['ciclo'] = df_final_rev['ciclo'].astype(int)
        df_final_rev['fecha_medicion'] = fecha_medicion_fija
        df_final_rev['hora_medicion'] = hora_medicion_fija

        columnas_finales = ['ciudad', 'zone_name', 'starting_point', 'fecha', 'hora', 'ciclo', 'horas_trabajo', 'fecha_medicion', 'hora_medicion']
        df_final_rev = df_final_rev[[col for col in columnas_finales if col in df_final_rev.columns]]

        try:
            job_config = bigquery.LoadJobConfig(
                write_disposition="WRITE_APPEND",
                schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION]
            )
            job = client.load_table_from_dataframe(df_final_rev, table_id_rev, job_config=job_config)
            job.result()
            print(f"[BIGQUERY] Exito: Se subieron {len(df_final_rev)} filas agrupadas a 'velocidad_toma_horas'.")
        except Exception as e:
            print(f"[BIGQUERY] Error subiendo Review: {e}")

    # =================================================================
    # SUBIDA AGRUPADA A BIGQUERY - TABLA SHIFTS TRIMMING
    # =================================================================
    if registros_slots:
        table_id_slots = "peya-chile.user_nicolas_paredes.fillrate_pulse"
        df_final_slots = pd.DataFrame(registros_slots)
        df_final_slots = df_final_slots.groupby(
            ['ciudad', 'starting_point', 'fecha', 'hora', 'ciclo'], 
            as_index=False
        )['slots_totales'].sum()

        df_final_slots['starting_point'] = df_final_slots['starting_point'].astype(str).str.strip()
        df_final_slots = df_final_slots.merge(df_zonas, on='starting_point', how='left')

        df_final_slots['fecha'] = pd.to_datetime(df_final_slots['fecha']).dt.strftime('%Y-%m-%d')
        df_final_slots['hora'] = df_final_slots['hora'].astype(int)
        df_final_slots['ciclo'] = df_final_slots['ciclo'].astype(int)
        df_final_slots['fecha_medicion'] = fecha_medicion_fija
        df_final_slots['hora_medicion'] = hora_medicion_fija

        columnas_finales_slots = ['ciudad', 'zone_name', 'starting_point', 'fecha', 'hora', 'ciclo', 'slots_totales', 'fecha_medicion', 'hora_medicion']
        df_final_slots = df_final_slots[[col for col in columnas_finales_slots if col in df_final_slots.columns]]

        try:
            job_config = bigquery.LoadJobConfig(
                write_disposition="WRITE_APPEND",
                schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION]
            )
            job = client.load_table_from_dataframe(df_final_slots, table_id_slots, job_config=job_config)
            job.result()
            print(f"[BIGQUERY] Exito: Se subieron {len(df_final_slots)} filas agrupadas a 'fillrate_pulse'.")
        except Exception as e:
            print(f"[BIGQUERY] Error subiendo Shift Trimming: {e}")