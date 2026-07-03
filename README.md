# Bot de Extracción y Carga - Fillrate Pulse

Este proyecto automatiza la extracción de datos de turnos desde Rooster (PedidosYa) y los consolida directamente en Google BigQuery de forma agrupada por hora y starting point.

## Prerrequisitos del Sistema

Antes de ejecutar la aplicación, asegúrese de cumplir con los siguientes requisitos en su sistema local:

1. **Python 3.9 o superior** instalado y añadido al PATH del sistema.
2. **Google Chrome** instalado (versión actualizada).
3. **Credenciales de Google Cloud Platform (GCP)** con permisos de escritura en el dataset `peya-chile.user_nicolas_paredes`.

## Instrucciones de Instalación

1. Descargue y extraiga la carpeta del proyecto en su computadora.
2. Abra una terminal (CMD, PowerShell o Terminal de macOS) y navegue hasta la carpeta del proyecto:
   cd .../fillrate_pulse_bot
3. Istalar dependencias: pip install -r requirements.txt
4. 