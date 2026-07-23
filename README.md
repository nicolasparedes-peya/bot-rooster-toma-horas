# 🐓 Fillrate Pulse Bot (Rooster Scraper)

Bot de automatización con interfaz gráfica diseñado para extraer, procesar y consolidar métricas de turnos logísticos (horas tomadas y horas libres) desde la plataforma Rooster. Procesa grandes volúmenes de datos usando Selenium y Pandas, y los inyecta directamente en Google Cloud BigQuery.

## 🚀 Características Principales

- **Interfaz Gráfica (GUI):** Configuración visual e intuitiva mediante Tkinter para seleccionar ciudades, fechas, intervalos y duración del ciclo.
- **Scraping Robusto:** Navegación automatizada con Selenium, con manejo avanzado de errores, reintentos y descargas masivas (chunking).
- **Procesamiento de Datos:** Consolidación de múltiples archivos CSV, cálculo matemático de horas y deduplicación inteligente de `shift id` usando Pandas.
- **Integración con Google Cloud:** Cruce de zonas logísticas vía DWH y subida automatizada de tablas finales a BigQuery.
- **Prevención de Suspensión:** Módulo nativo de Windows (API `ctypes`) para evitar que el PC se suspenda durante ciclos de ejecución largos.

## 📁 Estructura del Proyecto

- `main.py`: Orquestador principal. Levanta la interfaz, administra las instancias de Chrome y gestiona los bucles de tiempo.
- `interfaz.py`: Módulo de la interfaz gráfica de usuario.
- `scrapper_review.py`: Bot encargado de extraer los datos de turnos asignados/tomados.
- `scrapper_shifts_trimming.py`: Bot encargado de extraer masivamente los turnos libres (Unassigned) y generar un consolidado diario.
- `bigquery_uploader.py`: Pipeline de datos. Lee los CSV, cruza la información, aplica lógicas de limpieza y sube los resultados a GCP.
- `prevent_sleep.py`: Utilidad para mantener activo el sistema operativo durante la ejecución.

## 🛠️ Requisitos Previos

1. **Python 3.8+** instalado.
2. **Google Chrome** instalado en su última versión.
3. **Google Cloud CLI (gcloud):** Necesario para la autenticación automática con BigQuery (Application Default Credentials).

## ⚙️ Instalación y Configuración

1. **Clonar el repositorio:**
   ```bash
   git clone <url-del-repositorio>
   cd bot_rooster_toma_horas
   ```

2. **Crear y activar un entorno virtual (Recomendado):**
   ```bash
   python -m venv venv
   # En Windows:
   venv\Scripts\activate
   # En Mac/Linux:
   source venv/bin/activate
   ```

3. **Instalar dependencias:**
   ```bash
   pip install pandas selenium google-cloud-bigquery tkcalendar Pillow
   ```

4. **Autenticarse en Google Cloud (Solo la primera vez):**
   ```bash
   gcloud auth application-default login
   ```

## 🖥️ Uso

Para iniciar el bot, simplemente ejecuta el orquestador principal desde tu terminal:

```bash
python main.py
```

Esto abrirá la ventana de configuración. Selecciona tus parámetros (ciudades, fechas, horas de ejecución, intervalo) y presiona **INICIAR**.

> **Nota sobre el primer inicio (Login):** Si es la primera vez que se ejecuta y la sesión ha caducado, la consola te dará 60 segundos para loguearte manualmente en Okta antes de comenzar la automatización.

## ⚠️ Notas de Desarrollo

- **Modo Pruebas:** Puedes activar `MODO_PRUEBA = True` en `main.py` para conectar el bot a una instancia de Chrome ya abierta en modo *debugging* (puerto 9222).
- **Modo Silencioso:** Activa `MODO_HEADLESS = True` en `main.py` para ejecutar el navegador en segundo plano sin interfaz gráfica (asegúrate de tener cookies válidas primero).