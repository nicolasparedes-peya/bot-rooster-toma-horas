# -*- coding: utf-8 -*-
"""
interfaz.py - Interfaz grafica compacta con Checkboxes para Fillrate Pulse
"""
import tkinter as tk
from tkinter import messagebox
from tkcalendar import DateEntry
from PIL import Image, ImageTk
import os

# Lista oficial de ciudades
CIUDADES_DISPONIBLES = [
    "Antofagasta", "Arica", "Buin", "Calama", "Castro", "Chillan", 
    "Concepcion", "Copiapo", "Coyhaique", "Curico", "Iquique", 
    "La serena", "Linares", "Los angeles", "Maitencillo", "Melipilla", 
    "Osorno", "Ovalle", "Penaflor", "Pucon", "Puerto montt", 
    "Puerto varas", "Punta arenas", "Quillota", "Rancagua", 
    "San antonio", "San felipe  los andes", "San fernando", 
    "Santa cruz", "Santiago", "Talca", "Temuco", "Valdivia", 
    "Vallenar", "Villarrica", "Vina del mar"
]

def iniciar_interfaz():
    datos = {"ciudades": [], "inicio": None, "fin": None, "horas": None, "intervalo": None}

    # Paleta de colores Peya
    COLOR_PEYA = "#F90050"
    BG_COLOR = "#FFFFFF"
    TEXT_COLOR = "#333333"
    
    FONT_TITLE = ("Segoe UI", 14, "bold")
    FONT_LABEL = ("Segoe UI", 9, "bold")
    FONT_ENTRY = ("Segoe UI", 10)
    FONT_CHECK = ("Segoe UI", 9)

    ventana = tk.Tk()
    ventana.title("Fillrate Pulse - Configuracion")
    
    # --- CENTRADO MATEMÁTICO EXACTO ---
    ancho_ventana = 430
    alto_ventana = 580
    
    # Obtenemos las dimensiones reales de la pantalla del usuario
    ancho_pantalla = ventana.winfo_screenwidth()
    alto_pantalla = ventana.winfo_screenheight()
    
    # Calculamos las coordenadas X e Y para el centro absoluto
    pos_x = int((ancho_pantalla / 2) - (ancho_ventana / 2))
    pos_y = int((alto_pantalla / 2) - (alto_ventana / 2))
    
    ventana.geometry(f"{ancho_ventana}x{alto_ventana}+{pos_x}+{pos_y}")
    # -----------------------------------

    ventana.config(bg=BG_COLOR, padx=20, pady=10)
    ventana.resizable(False, False)

    # Diccionario para guardar el estado de cada ciudad
    dict_variables_ciudades = {}

    def al_enviar():
        ciudades_seleccionadas = [ciudad for ciudad, var in dict_variables_ciudades.items() if var.get() == 1]
        
        inicio = entry_inicio.get().strip()
        fin = entry_fin.get().strip()
        horas_str = entry_horas.get().strip()
        intervalo_str = entry_intervalo.get().strip()

        if not ciudades_seleccionadas or not inicio or not fin or not horas_str or not intervalo_str:
            messagebox.showwarning("Faltan datos", "Por favor, completa los campos y selecciona al menos una ciudad.")
            return

        try:
            datos["horas"] = int(horas_str)
            datos["intervalo"] = int(intervalo_str)
        except ValueError:
            messagebox.showerror("Error", "Las horas y el intervalo deben ser numeros enteros.")
            return

        datos["ciudades"] = ciudades_seleccionadas
        datos["inicio"] = inicio
        datos["fin"] = fin
        ventana.destroy()

    def seleccionar_todas():
        for var in dict_variables_ciudades.values():
            var.set(1)

    def deseleccionar_todas():
        for var in dict_variables_ciudades.values():
            var.set(0)

    # --- LOGO COMPACTO ---
    ruta_logo = os.path.join(os.path.dirname(__file__), "logo.png")
    if os.path.exists(ruta_logo):
        try:
            img = Image.open(ruta_logo)
            img.thumbnail((100, 60), Image.Resampling.LANCZOS)
            logo_peya = ImageTk.PhotoImage(img)
            label_logo = tk.Label(ventana, image=logo_peya, bg=BG_COLOR)
            label_logo.image = logo_peya 
            label_logo.pack(pady=(0, 2))
        except: pass

    tk.Label(ventana, text="Fillrate Pulse", font=FONT_TITLE, fg=COLOR_PEYA, bg=BG_COLOR).pack(pady=(0, 5))

    frame_form = tk.Frame(ventana, bg=BG_COLOR)
    frame_form.pack(fill="both", expand=True)

    # --- CIUDADES CON CHECKBOXES Y SCROLL COMPACTO ---
    tk.Label(frame_form, text="Ciudades a analizar:", font=FONT_LABEL, fg=TEXT_COLOR, bg=BG_COLOR).pack(anchor="w")
    
    frame_ctrl_ciudades = tk.Frame(frame_form, bg=BG_COLOR)
    frame_ctrl_ciudades.pack(fill="x", pady=(2, 2))
    tk.Button(frame_ctrl_ciudades, text="Seleccionar Todas", font=("Segoe UI", 8), command=seleccionar_todas, cursor="hand2").pack(side="left", padx=(0, 5))
    tk.Button(frame_ctrl_ciudades, text="Limpiar", font=("Segoe UI", 8), command=deseleccionar_todas, cursor="hand2").pack(side="left")

    frame_canvas = tk.Frame(frame_form, bg=BG_COLOR, bd=1, relief="solid")
    frame_canvas.pack(fill="x", pady=(0, 5))

    canvas = tk.Canvas(frame_canvas, bg=BG_COLOR, highlightthickness=0, height=95)
    scrollbar = tk.Scrollbar(frame_canvas, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas, bg=BG_COLOR)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    for ciudad in CIUDADES_DISPONIBLES:
        var = tk.IntVar()
        dict_variables_ciudades[ciudad] = var
        cb = tk.Checkbutton(
            scrollable_frame, 
            text=ciudad, 
            variable=var, 
            font=FONT_CHECK, 
            bg=BG_COLOR, 
            activebackground=BG_COLOR,
            fg=TEXT_COLOR,
            cursor="hand2"
        )
        cb.pack(anchor="w", padx=5)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # Vinculación del scroll de ratón
    def scroll_raton(event):
        if event.delta:
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        elif getattr(event, 'num', None) == 4:
            canvas.yview_scroll(-1, "units")
        elif getattr(event, 'num', None) == 5:
            canvas.yview_scroll(1, "units")

    canvas.bind_all("<MouseWheel>", scroll_raton)
    canvas.bind_all("<Button-4>", scroll_raton)
    canvas.bind_all("<Button-5>", scroll_raton)

    # --- FORMULARIO CON CORRECCIÓN DE CALENDARIO ---
    tk.Label(frame_form, text="Fecha de Inicio:", font=FONT_LABEL, fg=TEXT_COLOR, bg=BG_COLOR).pack(anchor="w")
    # Agregado state="readonly" para evitar el bloqueo de la navegación de meses
    entry_inicio = DateEntry(frame_form, width=35, background=COLOR_PEYA, foreground='white', borderwidth=2, font=FONT_ENTRY, date_pattern='dd.mm.yyyy', state="readonly")
    entry_inicio.pack(pady=(2, 6))

    tk.Label(frame_form, text="Fecha de Fin:", font=FONT_LABEL, fg=TEXT_COLOR, bg=BG_COLOR).pack(anchor="w")
    # Agregado state="readonly" para evitar el bloqueo de la navegación de meses
    entry_fin = DateEntry(frame_form, width=35, background=COLOR_PEYA, foreground='white', borderwidth=2, font=FONT_ENTRY, date_pattern='dd.mm.yyyy', state="readonly")
    entry_fin.pack(pady=(2, 6))

    tk.Label(frame_form, text="Horas seguidas a ejecutar:", font=FONT_LABEL, fg=TEXT_COLOR, bg=BG_COLOR).pack(anchor="w")
    entry_horas = tk.Entry(frame_form, font=FONT_ENTRY, width=38, relief="solid", bd=1)
    entry_horas.insert(0, "5")
    entry_horas.pack(pady=(2, 6))

    tk.Label(frame_form, text="Intervalo de descarga (minutos):", font=FONT_LABEL, fg=TEXT_COLOR, bg=BG_COLOR).pack(anchor="w")
    entry_intervalo = tk.Entry(frame_form, font=FONT_ENTRY, width=38, relief="solid", bd=1)
    entry_intervalo.insert(0, "15")
    entry_intervalo.pack(pady=(2, 10))

    # --- BOTON INICIAR ---
    btn_iniciar = tk.Button(ventana, text="INICIAR FILLRATE PULSE", bg=COLOR_PEYA, fg="white", font=("Segoe UI", 11, "bold"), relief="flat", cursor="hand2", pady=6, command=al_enviar)
    btn_iniciar.pack(fill="x", side="bottom", pady=(5, 0))

    ventana.mainloop()

    return datos["ciudades"], datos["inicio"], datos["fin"], datos["horas"], datos["intervalo"]