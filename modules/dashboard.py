# dashboard_pdf.py - Genera un PDF con el tablero de control de tu finca
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np
from fpdf import FPDF
import tempfile
import os
from datetime import datetime

# ================== DATOS SIMULADOS (CÁMBIALOS POR LOS TUYOS) ==================
# Simulamos un GeoDataFrame como el que usas en tu sistema
data = {
    'Zona': ['Zona 1', 'Zona 2', 'Zona 3'],
    'Area_ha': [10, 15, 8],
    'NPK': [65, 45, 85],
    'MO_%': [3.5, 2.8, 4.2],
    'Humedad': [45, 38, 52],
    'NDVI': [0.62, 0.55, 0.70],
    'Rend_sin_fert': [2500, 2200, 2800],
    'Rend_con_fert': [3200, 2900, 3500],
    'Costo_total': [1200, 1500, 1000],
}
df = pd.DataFrame(data)

# Promedios generales (para tarjetas)
totales = {
    'npk_prom': df['NPK'].mean(),
    'mo_prom': df['MO_%'].mean(),
    'humedad_prom': df['Humedad'].mean(),
    'rend_sin_prom': df['Rend_sin_fert'].mean(),
    'rend_con_prom': df['Rend_con_fert'].mean(),
    'costo_total': df['Costo_total'].sum(),
}

# ================== FUNCIÓN PARA CREAR GRÁFICOS ==================
def crear_grafico_barras(df, x_col, y_col, titulo, color='#2E86AB', unidad=''):
    fig, ax = plt.subplots(figsize=(5, 3))
    bars = ax.bar(df[x_col], df[y_col], color=color)
    ax.set_title(titulo, fontsize=12, fontweight='bold')
    ax.set_ylabel(unidad)
    ax.set_xlabel('')
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                f'{height:.0f}', ha='center', va='bottom', fontsize=9)
    plt.tight_layout()
    return fig

def crear_grafico_comparativo(df, zonas, col1, col2, titulo):
    fig, ax = plt.subplots(figsize=(5, 3))
    x = np.arange(len(zonas))
    width = 0.35
    bars1 = ax.bar(x - width/2, df[col1], width, label='Sin fertilizante', color='#E6A817')
    bars2 = ax.bar(x + width/2, df[col2], width, label='Con fertilizante', color='#4C9A2A')
    ax.set_title(titulo, fontsize=12, fontweight='bold')
    ax.set_ylabel('kg/ha')
    ax.set_xticks(x)
    ax.set_xticklabels(zonas)
    ax.legend()
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 20,
                    f'{height:.0f}', ha='center', va='bottom', fontsize=8)
    plt.tight_layout()
    return fig

# ================== GENERAR GRÁFICOS ==================
# 1. Fertilidad NPK por zona
fig_npk = crear_grafico_barras(df, 'Zona', 'NPK', 'Fertilidad (NPK)', '#2E86AB', 'Índice')

# 2. Materia orgánica por zona
fig_mo = crear_grafico_barras(df, 'Zona', 'MO_%', 'Materia Orgánica (%)', '#A23B72', '%')

# 3. Comparativa rendimiento
fig_rend = crear_grafico_comparativo(df, df['Zona'], 'Rend_sin_fert', 'Rend_con_fert', 'Rendimiento con/sin fertilizante')

# 4. Humedad del suelo
fig_humedad = crear_grafico_barras(df, 'Zona', 'Humedad', 'Humedad del suelo (%)', '#55A868', '%')

# Guardar imágenes temporales
temp_dir = tempfile.mkdtemp()
path_npk = os.path.join(temp_dir, 'npk.png')
path_mo = os.path.join(temp_dir, 'mo.png')
path_rend = os.path.join(temp_dir, 'rend.png')
path_humedad = os.path.join(temp_dir, 'humedad.png')
fig_npk.savefig(path_npk, dpi=150, bbox_inches='tight')
fig_mo.savefig(path_mo, dpi=150, bbox_inches='tight')
fig_rend.savefig(path_rend, dpi=150, bbox_inches='tight')
fig_humedad.savefig(path_humedad, dpi=150, bbox_inches='tight')
plt.close('all')

# ================== CREAR PDF CON FPDF ==================
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.set_text_color(0, 100, 0)
        self.cell(0, 10, 'TABLERO DE CONTROL - MI FINCA', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, f'Generado: {datetime.now().strftime("%d/%m/%Y")}', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

    def tarjeta(self, titulo, valor, unidad, color_fondo=(240,240,240)):
        self.set_fill_color(*color_fondo)
        self.rect(self.get_x(), self.get_y(), 45, 30, 'F')
        self.set_font('Arial', 'B', 10)
        self.set_text_color(0,0,0)
        self.cell(45, 8, titulo, 0, 1, 'C')
        self.set_font('Arial', 'B', 16)
        self.set_text_color(0,150,0)
        self.cell(45, 12, f'{valor}{unidad}', 0, 1, 'C')
        self.ln(2)

pdf = PDF('P', 'mm', 'Letter')
pdf.add_page()
pdf.set_auto_page_break(auto=True, margin=15)

# ============= FILA DE TARJETAS (KPIs) =============
pdf.set_font('Arial', 'B', 12)
pdf.cell(0, 8, 'INDICADORES CLAVE', 0, 1, 'L')
pdf.ln(2)

# Posiciones manuales para 4 tarjetas
x_ini = pdf.get_x()
y_ini = pdf.get_y()
pdf.set_xy(x_ini, y_ini)
pdf.tarjeta('Fertilidad NPK', f'{totales["npk_prom"]:.0f}', '', (230,255,230))
pdf.set_xy(x_ini + 48, y_ini)
pdf.tarjeta('Materia Orgánica', f'{totales["mo_prom"]:.1f}', '%', (255,255,200))
pdf.set_xy(x_ini + 96, y_ini)
pdf.tarjeta('Humedad suelo', f'{totales["humedad_prom"]:.0f}', '%', (200,230,255))
pdf.set_xy(x_ini + 144, y_ini)
pdf.tarjeta('Gasto fertilizante', f'${totales["costo_total"]:,.0f}', '', (255,220,220))

pdf.ln(35)

# ============= GRÁFICOS (2 columnas) =============
# Primera fila de gráficos
pdf.image(path_npk, x=15, y=pdf.get_y(), w=85)
pdf.image(path_mo, x=105, y=pdf.get_y(), w=85)
pdf.ln(60)

# Segunda fila
pdf.image(path_rend, x=15, y=pdf.get_y(), w=85)
pdf.image(path_humedad, x=105, y=pdf.get_y(), w=85)
pdf.ln(60)

# ============= RECOMENDACIÓN CORTA DE IA =============
pdf.set_font('Arial', 'B', 11)
pdf.set_text_color(0,0,0)
pdf.cell(0, 8, '💡 RECOMENDACIÓN DE LA IA (breve)', 0, 1, 'L')
pdf.set_font('Arial', '', 10)
pdf.set_text_color(60,60,60)
# Simulamos una frase muy corta (ni siquiera llamamos a Groq para ahorrar texto)
recomendacion = "Sube la materia orgánica (está baja) con compost y rastrojos. Ahorrarás dinero y tendrás más humedad."
pdf.multi_cell(0, 5, recomendacion)
pdf.ln(5)

# ============= PIE =============
pdf.set_font('Arial', 'I', 8)
pdf.set_text_color(128)
pdf.cell(0, 5, 'Los gráficos comparan las zonas de tu finca. Tus datos reales se pueden actualizar fácilmente.', 0, 1, 'C')

# Guardar PDF
pdf_output = "tablero_finca.pdf"
pdf.output(pdf_output)
print(f"✅ PDF generado: {pdf_output}")
print(f"📁 Ruta: {os.path.abspath(pdf_output)}")

# Limpiar imágenes temporales
for f in [path_npk, path_mo, path_rend, path_humedad]:
    os.remove(f)
os.rmdir(temp_dir)
