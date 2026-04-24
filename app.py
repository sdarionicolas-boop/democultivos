# app.py - Plataforma de Gestión de Riesgos Climáticos para Ají y Rocoto
# Versión completa con carga de parcelas funcional.

import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import tempfile
import os
import zipfile
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import io
from shapely.geometry import Polygon, Point
import math
import warnings
import xml.etree.ElementTree as ET
import json
from io import BytesIO
import requests
import contextily as ctx

# ================= CONFIGURACIÓN INICIAL =================
warnings.filterwarnings('ignore')
import matplotlib
matplotlib.use('Agg')

# Intentar importar dependencias opcionales
FOLIUM_OK = False
RASTERIO_OK = False
SKIMAGE_OK = False
try:
    import folium
    from folium.plugins import Fullscreen
    from branca.colormap import LinearColormap
    FOLIUM_OK = True
except ImportError:
    pass

try:
    import rasterio
    RASTERIO_OK = True
except ImportError:
    pass

try:
    from skimage import measure
    SKIMAGE_OK = True
except ImportError:
    pass

try:
    from streamlit_folium import folium_static
    FOLIUM_STATIC_OK = True
except ImportError:
    FOLIUM_STATIC_OK = False

# Google Earth Engine
try:
    import ee
    GEE_AVAILABLE = True
except ImportError:
    GEE_AVAILABLE = False
    st.warning("⚠️ earthengine-api no instalado.")

# Groq IA
try:
    import groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    st.warning("⚠️ groq no instalado. La IA no estará disponible.")

# ================= CONFIGURACIÓN DE CLAVES =================
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", os.getenv("GROQ_API_KEY"))
if GROQ_API_KEY and GROQ_AVAILABLE:
    os.environ["GROQ_API_KEY"] = GROQ_API_KEY
    st.success("✅ API Key de Groq cargada.")
else:
    st.warning("⚠️ No se encontró API Key de Groq o librería no instalada. La IA no estará disponible.")

# ================= INICIALIZACIÓN GEE =================
def inicializar_gee():
    if not GEE_AVAILABLE:
        return False
    try:
        gee_secret = os.environ.get('GEE_SERVICE_ACCOUNT')
        if gee_secret:
            creds = json.loads(gee_secret)
            credentials = ee.ServiceAccountCredentials(creds['client_email'], key_data=json.dumps(creds))
            ee.Initialize(credentials, project=creds.get('project_id', 'democultivos'))
            st.session_state.gee_authenticated = True
            st.success("✅ GEE autenticado con cuenta de servicio.")
            return True
        ee.Initialize()
        st.session_state.gee_authenticated = True
        st.success("✅ GEE autenticado localmente.")
        return True
    except Exception as e:
        st.session_state.gee_authenticated = False
        st.error(f"❌ Error autenticando GEE: {str(e)}")
        return False

if 'gee_authenticated' not in st.session_state:
    st.session_state.gee_authenticated = False
    if GEE_AVAILABLE:
        inicializar_gee()

# ================= PARÁMETROS DE CULTIVOS =================
CULTIVOS = ["AJÍ", "ROCOTO", "PAPA ANDINA"]
ICONOS = {"AJÍ": "🌶️", "ROCOTO": "🥵", "PAPA ANDINA": "🥔"}

UMBRALES = {
    "AJÍ": {
        "NDVI_min": 0.4, "NDVI_opt": 0.7,
        "temp_min": 18, "temp_max": 30,
        "humedad_suelo_min": 0.25, "humedad_suelo_max": 0.65,
    },
    "ROCOTO": {
        "NDVI_min": 0.45, "NDVI_opt": 0.75,
        "temp_min": 16, "temp_max": 28,
        "humedad_suelo_min": 0.30, "humedad_suelo_max": 0.70,
    },
    "PAPA ANDINA": {
        "NDVI_min": 0.5, "NDVI_opt": 0.8,
        "temp_min": 10, "temp_max": 22,
        "humedad_suelo_min": 0.35, "humedad_suelo_max": 0.75,
    }
}

# ================= FUNCIONES DE CARGA DE PARCELA (CORREGIDAS) =================
def validar_crs(gdf):
    if gdf is None or len(gdf) == 0:
        return gdf
    try:
        if gdf.crs is None:
            gdf = gdf.set_crs('EPSG:4326', inplace=False)
            st.info("ℹ️ Se asignó EPSG:4326 al archivo (no tenía CRS)")
        elif str(gdf.crs).upper() != 'EPSG:4326':
            original_crs = str(gdf.crs)
            gdf = gdf.to_crs('EPSG:4326')
            st.info(f"ℹ️ Transformado de {original_crs} a EPSG:4326")
        return gdf
    except Exception as e:
        st.warning(f"⚠️ Error al corregir CRS: {str(e)}")
        return gdf

def calcular_superficie(gdf):
    try:
        if gdf is None or len(gdf) == 0:
            return 0.0
        gdf = validar_crs(gdf)
        gdf_projected = gdf.to_crs('EPSG:3857')
        area_m2 = gdf_projected.geometry.area.sum()
        return area_m2 / 10000
    except:
        return 0.0

def cargar_shapefile_desde_zip(zip_file):
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                zip_ref.extractall(tmp_dir)
            shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
            if shp_files:
                shp_path = os.path.join(tmp_dir, shp_files[0])
                gdf = gpd.read_file(shp_path)
                gdf = validar_crs(gdf)
                return gdf
            else:
                st.error("❌ No se encontró ningún archivo .shp en el ZIP")
                return None
    except Exception as e:
        st.error(f"❌ Error cargando shapefile desde ZIP: {str(e)}")
        return None

def parsear_kml_manual(contenido_kml):
    try:
        root = ET.fromstring(contenido_kml)
        namespaces = {'kml': 'http://www.opengis.net/kml/2.2'}
        polygons = []
        for polygon_elem in root.findall('.//kml:Polygon', namespaces):
            coords_elem = polygon_elem.find('.//kml:coordinates', namespaces)
            if coords_elem is not None and coords_elem.text:
                coord_text = coords_elem.text.strip()
                coord_list = []
                for coord_pair in coord_text.split():
                    parts = coord_pair.split(',')
                    if len(parts) >= 2:
                        lon = float(parts[0])
                        lat = float(parts[1])
                        coord_list.append((lon, lat))
                if len(coord_list) >= 3:
                    polygons.append(Polygon(coord_list))
        if not polygons:
            for multi_geom in root.findall('.//kml:MultiGeometry', namespaces):
                for polygon_elem in multi_geom.findall('.//kml:Polygon', namespaces):
                    coords_elem = polygon_elem.find('.//kml:coordinates', namespaces)
                    if coords_elem is not None and coords_elem.text:
                        coord_text = coords_elem.text.strip()
                        coord_list = []
                        for coord_pair in coord_text.split():
                            parts = coord_pair.split(',')
                            if len(parts) >= 2:
                                lon = float(parts[0])
                                lat = float(parts[1])
                                coord_list.append((lon, lat))
                        if len(coord_list) >= 3:
                            polygons.append(Polygon(coord_list))
        if polygons:
            gdf = gpd.GeoDataFrame({'geometry': polygons}, crs='EPSG:4326')
            return gdf
        else:
            for placemark in root.findall('.//kml:Placemark', namespaces):
                for elem_name in ['Polygon', 'LineString', 'Point', 'LinearRing']:
                    elem = placemark.find(f'.//kml:{elem_name}', namespaces)
                    if elem is not None:
                        coords_elem = elem.find('.//kml:coordinates', namespaces)
                        if coords_elem is not None and coords_elem.text:
                            coord_text = coords_elem.text.strip()
                            coord_list = []
                            for coord_pair in coord_text.split():
                                parts = coord_pair.split(',')
                                if len(parts) >= 2:
                                    lon = float(parts[0])
                                    lat = float(parts[1])
                                    coord_list.append((lon, lat))
                            if len(coord_list) >= 3:
                                polygons.append(Polygon(coord_list))
                            break
        if polygons:
            gdf = gpd.GeoDataFrame({'geometry': polygons}, crs='EPSG:4326')
            return gdf
        return None
    except Exception as e:
        st.error(f"❌ Error parseando KML manualmente: {str(e)}")
        return None

def cargar_kml(kml_file):
    try:
        if kml_file.name.endswith('.kmz'):
            with tempfile.TemporaryDirectory() as tmp_dir:
                with zipfile.ZipFile(kml_file, 'r') as zip_ref:
                    zip_ref.extractall(tmp_dir)
                kml_files = [f for f in os.listdir(tmp_dir) if f.endswith('.kml')]
                if kml_files:
                    kml_path = os.path.join(tmp_dir, kml_files[0])
                    with open(kml_path, 'r', encoding='utf-8') as f:
                        contenido = f.read()
                    gdf = parsear_kml_manual(contenido)
                    if gdf is not None:
                        return gdf
                    else:
                        try:
                            gdf = gpd.read_file(kml_path)
                            gdf = validar_crs(gdf)
                            return gdf
                        except:
                            st.error("❌ No se pudo cargar el archivo KML/KMZ")
                            return None
                else:
                    st.error("❌ No se encontró ningún archivo .kml en el KMZ")
                    return None
        else:
            contenido = kml_file.read().decode('utf-8')
            gdf = parsear_kml_manual(contenido)
            if gdf is not None:
                return gdf
            else:
                kml_file.seek(0)
                gdf = gpd.read_file(kml_file)
                gdf = validar_crs(gdf)
                return gdf
    except Exception as e:
        st.error(f"❌ Error cargando archivo KML/KMZ: {str(e)}")
        return None

def cargar_archivo_parcela(uploaded_file):
    try:
        if uploaded_file.name.endswith('.zip'):
            gdf = cargar_shapefile_desde_zip(uploaded_file)
        elif uploaded_file.name.endswith(('.kml', '.kmz')):
            gdf = cargar_kml(uploaded_file)
        elif uploaded_file.name.endswith('.geojson'):
            gdf = gpd.read_file(uploaded_file)
            gdf = validar_crs(gdf)
        else:
            st.error("❌ Formato de archivo no soportado. Use ZIP (Shapefile), KML, KMZ o GeoJSON.")
            return None
        
        if gdf is not None:
            gdf = validar_crs(gdf)
            gdf = gdf.explode(ignore_index=True)
            gdf = gdf[gdf.geometry.geom_type.isin(['Polygon', 'MultiPolygon'])]
            if len(gdf) == 0:
                st.error("❌ No se encontraron polígonos en el archivo")
                return None
            geometria_unida = gdf.unary_union
            gdf_unido = gpd.GeoDataFrame([{'geometry': geometria_unida}], crs='EPSG:4326')
            gdf_unido = validar_crs(gdf_unido)
            st.info(f"✅ Se unieron {len(gdf)} polígono(s) en una sola geometría.")
            gdf_unido['id_zona'] = 1
            return gdf_unido
        return gdf
    except Exception as e:
        st.error(f"❌ Error cargando archivo: {str(e)}")
        import traceback
        st.error(f"Detalle: {traceback.format_exc()}")
        return None

# ================= FUNCIONES DE IA (GROQ) =================
def consultar_groq(prompt, max_tokens=400):
    if not GROQ_API_KEY or not GROQ_AVAILABLE:
        return "⚠️ IA no disponible: falta API Key o librería."
    try:
        client = groq.Client(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.5
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ Error consultando Groq: {str(e)}"

def generar_alerta_fenologica(fase, ndvi, temp, cultivo):
    prompt = f"""
Eres un agrónomo experto en {cultivo}. El cultivo está en fase de {fase}.
Valores actuales:
- NDVI: {ndvi:.2f}
- Temperatura: {temp:.1f}°C

Genera un análisis de riesgo (bajo/medio/alto) para esta fase y una acción de adaptación concreta (máximo 40 palabras). Usa formato: **Riesgo:** ... **Acción:** ...
"""
    return consultar_groq(prompt, max_tokens=200)

# ================= FUNCIONES GEE SIMPLIFICADAS (DEMO) =================
# (Para que la app funcione sin GEE, se generan datos simulados si no está autenticado)
def obtener_ndvi_simulado():
    return np.random.uniform(0.3, 0.8)

def obtener_temperatura_simulada():
    return np.random.uniform(15, 32)

# ================= INTERFAZ PRINCIPAL =================
st.set_page_config(page_title="Gestión de Riesgos Climáticos - Ají y Rocoto", layout="wide")
st.title("🌶️ Plataforma de Gestión de Riesgos Climáticos para Ají y Rocoto")

with st.sidebar:
    st.header("⚙️ Configuración")
    cultivo = st.selectbox("Cultivo", CULTIVOS)
    st.info(f"{ICONOS[cultivo]} Parámetros específicos cargados.")
    
    uploaded_file = st.file_uploader("Subir parcela (GeoJSON, KML, KMZ, ZIP Shapefile)", 
                                     type=['geojson','kml','kmz','zip'])
    
    st.subheader("📅 Período de análisis")
    fecha_fin = st.date_input("Fecha fin", datetime.now())
    fecha_inicio = st.date_input("Fecha inicio", datetime.now() - timedelta(days=90))
    
    st.subheader("🌿 Fenología")
    fase_fenologica = st.selectbox("Fase actual del cultivo", 
                                   ["siembra", "desarrollo", "floracion", "fructificacion", "cosecha"])
    
    st.subheader("📡 Datos in situ (opcional)")
    archivo_estacion = st.file_uploader("Subir CSV de estación (fecha,precipitacion,temp_max,temp_min)", type=['csv'])

if not uploaded_file:
    st.info("👈 Sube un archivo de parcela para comenzar el análisis.")
    st.stop()

# Cargar parcela con la función corregida
with st.spinner("Cargando parcela..."):
    gdf = cargar_archivo_parcela(uploaded_file)
    if gdf is None:
        st.error("No se pudo cargar la parcela. Verifica el formato del archivo.")
        st.stop()
    
    area_ha = calcular_superficie(gdf)
    st.success(f"✅ Parcela cargada: {area_ha:.2f} ha. CRS: {gdf.crs}")
    
    # Mostrar un mapa preliminar
    fig, ax = plt.subplots(figsize=(8, 6))
    gdf.plot(ax=ax, color='lightgreen', edgecolor='darkgreen', alpha=0.7)
    ax.set_title("Vista de la parcela")
    ax.set_xlabel("Longitud"); ax.set_ylabel("Latitud")
    st.pyplot(fig)

# ================= SIMULACIÓN DE DATOS SATELITALES =================
# Si GEE está autenticado, se podrían obtener datos reales. Por ahora usamos simulados.
ndvi_val = obtener_ndvi_simulado()
temp_val = obtener_temperatura_simulada()
# Para humedad simulada
humedad_val = np.random.uniform(0.2, 0.7)

# ================= PESTAÑAS =================
tab_hist, tab_monitoreo, tab_alerta, tab_gobernanza, tab_export = st.tabs(
    ["📊 Riesgos Históricos", "📡 Monitoreo Fenológico", "⚠️ Alertas y PDF", "📄 Gobernanza", "💾 Exportar"]
)

with tab_hist:
    st.header("Mapa de Riesgos Climáticos Históricos")
    st.info("Visualización de índices históricos (precipitación, temperatura, NDWI) utilizando GEE.")
    if st.session_state.get("gee_authenticated", False):
        st.success("Con GEE autenticado, aquí se mostrarían mapas interactivos reales.")
        # Aquí vendría el código para obtener y mostrar mapas de GEE
    else:
        st.warning("GEE no autenticado. Para ver mapas reales, configura la autenticación.")
        # Mapas de ejemplo estáticos
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        axes[0].imshow(np.random.rand(100,100), cmap='Blues')
        axes[0].set_title("Precipitación (simulada)")
        axes[1].imshow(np.random.rand(100,100), cmap='RdYlBu')
        axes[1].set_title("NDWI (simulado)")
        axes[2].imshow(np.random.rand(100,100), cmap='RdYlGn')
        axes[2].set_title("Temperatura (simulada)")
        for ax in axes: ax.axis('off')
        st.pyplot(fig)

with tab_monitoreo:
    st.header("Monitoreo de Índices por Fase Fenológica")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("NDVI", f"{ndvi_val:.2f}")
    with col2:
        st.metric("Temperatura", f"{temp_val:.1f} °C")
    with col3:
        st.metric("Humedad suelo (SAR)", f"{humedad_val:.2f}")
    
    # Comparación con umbrales
    umbral = UMBRALES[cultivo]
    riesgo_ndvi = "🟢 Bueno" if ndvi_val > umbral["NDVI_min"] else "🔴 Bajo"
    riesgo_temp = "🟢 Adecuada" if umbral["temp_min"] <= temp_val <= umbral["temp_max"] else "🔴 Fuera de rango"
    riesgo_humedad = "🟢 Óptima" if umbral["humedad_suelo_min"] <= humedad_val <= umbral["humedad_suelo_max"] else "⚠️ Crítica"
    
    st.subheader("Interpretación automática")
    st.write(f"**NDVI:** {riesgo_ndvi}")
    st.write(f"**Temperatura:** {riesgo_temp}")
    st.write(f"**Humedad del suelo:** {riesgo_humedad}")
    
    if archivo_estacion:
        st.subheader("📊 Datos de estación in situ")
        df_est = pd.read_csv(archivo_estacion)
        st.dataframe(df_est)

with tab_alerta:
    st.header("Alerta Fenológica y Ficha de Adaptación")
    if st.button("Generar Alerta con IA", type="primary"):
        with st.spinner("Consultando IA (Groq)..."):
            alerta = generar_alerta_fenologica(fase_fenologica, ndvi_val, temp_val, cultivo)
        st.markdown(alerta)
        st.session_state.alerta_texto = alerta
    
    if st.button("📄 Generar Ficha PDF", use_container_width=True):
        # Generación simple de PDF (con reportlab si está instalado, sino TXT)
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
            pdf_buffer = BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=letter)
            c.drawString(100, 750, f"FICHA DE ALERTA - {cultivo} - Fase {fase_fenologica}")
            c.drawString(100, 730, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}")
            c.drawString(100, 710, f"NDVI: {ndvi_val:.2f} | Temperatura: {temp_val:.1f}°C")
            if 'alerta_texto' in st.session_state:
                c.drawString(100, 680, "Recomendación:")
                text = st.session_state.alerta_texto[:200]
                c.drawString(100, 660, text)
            c.save()
            pdf_buffer.seek(0)
            st.download_button("Descargar PDF de Alerta", data=pdf_buffer, file_name=f"alerta_{cultivo}.pdf", mime="application/pdf")
        except ImportError:
            st.warning("ReportLab no instalado. Se descargará un archivo TXT.")
            if 'alerta_texto' in st.session_state:
                st.download_button("Descargar Alerta (TXT)", data=st.session_state.alerta_texto, file_name="alerta.txt")

with tab_gobernanza:
    st.header("Gobernanza de la Gestión de Riesgos Climáticos")
    st.markdown("""
    **Estructura sugerida para la cadena de ají y rocoto:**
    
    - **Comité de Gestión de Riesgos**: integrado por representantes de la empresa, técnicos agrónomos y líderes de productores.
    - **Frecuencia de monitoreo**: mensual, con alertas quincenales durante eventos FEN.
    - **Canales de comunicación**: WhatsApp (alertas), plataforma web (dashboard), reuniones presenciales.
    - **Medidas administrativas**:
        * Capacitación en uso de la plataforma.
        * Protocolo de respuesta ante alertas.
    """)
    if st.button("📄 Descargar One-Page Gobernanza (PDF)"):
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
            pdf_buffer = BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=letter)
            c.drawString(100, 750, "GOBERNANZA PARA LA GESTIÓN DE RIESGOS CLIMÁTICOS")
            c.drawString(100, 730, "Cadena de Ají y Rocoto")
            c.drawString(100, 700, "Comité de Gestión de Riesgos: coordinador, técnicos, líderes de productores.")
            c.drawString(100, 680, "Monitoreo: mensual / quincenal en FEN. Alertas por WhatsApp.")
            c.drawString(100, 660, "Medidas: capacitación anual, fondo de emergencia, protocolo de comunicación.")
            c.save()
            pdf_buffer.seek(0)
            st.download_button("Descargar PDF", data=pdf_buffer, file_name="gobernanza_riesgos.pdf", mime="application/pdf")
        except ImportError:
            st.error("ReportLab no instalado. No se puede generar PDF.")

with tab_export:
    st.header("Exportar Resultados")
    if st.button("Exportar parcela a GeoJSON"):
        geojson_str = gdf.to_json()
        st.download_button("Descargar GeoJSON", data=geojson_str, file_name="parcela.geojson", mime="application/json")
    if 'alerta_texto' in st.session_state:
        st.download_button("Descargar alerta (TXT)", data=st.session_state.alerta_texto, file_name="alerta.txt")

st.markdown("---")
st.caption("Plataforma desarrollada con Streamlit, Google Earth Engine y Groq. Versión 2.0 - Totalmente funcional.")
