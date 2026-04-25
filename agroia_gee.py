# app.py - Plataforma de Gestión de Riesgos Climáticos para Ají y Rocoto
# Versión avanzada con dashboard, gráficos temporales, alertas IA mejoradas.
# Incluye mapas de calor para NDVI, NDRE, Temperatura, Precipitación y NDWI.

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
from PIL import Image

from agroia_gee import (
    obtener_ndvi_actual, obtener_ndwi_actual, obtener_ndre_actual,
    obtener_temperatura_actual, obtener_precipitacion_actual,
    obtener_serie_temporal_ndvi, obtener_serie_temporal_temperatura,
    obtener_serie_temporal_precipitacion
)
# ================= CONFIGURACIÓN INICIAL =================
warnings.filterwarnings('ignore')
import matplotlib
matplotlib.use('Agg')

# ================= DEPENDENCIAS OPCIONALES =================
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
    from rasterio.transform import from_origin
    from rasterio.crs import CRS
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

# ================= GOOGLE EARTH ENGINE =================
try:
    import ee
    GEE_AVAILABLE = True
except ImportError:
    GEE_AVAILABLE = False
    st.warning("⚠️ earthengine-api no instalado. Ejecuta: pip install earthengine-api")

# ================= GROQ IA =================
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    st.warning("⚠️ groq no instalado. Ejecuta: pip install groq")

# ================= LECTURA DE SECRETS =================
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", os.getenv("GROQ_API_KEY", ""))
if GROQ_API_KEY and GROQ_AVAILABLE:
    os.environ["GROQ_API_KEY"] = GROQ_API_KEY
    st.success("✅ API Key de Groq cargada correctamente.")
else:
    st.warning("⚠️ No se encontró API Key de Groq o librería no instalada. La IA no estará disponible.")

# ================= INICIALIZACIÓN DE GEE =================
def inicializar_gee():
    if not GEE_AVAILABLE:
        return False
    if 'gee_service_account' in st.secrets:
        try:
            creds = st.secrets["gee_service_account"]
            credentials = ee.ServiceAccountCredentials(
                creds['client_email'],
                key_data=creds['private_key']
            )
            ee.Initialize(credentials, project=creds.get('project_id', 'democultivos'))
            st.session_state.gee_authenticated = True
            st.success("✅ GEE autenticado con cuenta de servicio.")
            return True
        except Exception as e:
            st.error(f"❌ Error con cuenta de servicio: {e}")
    try:
        ee.Initialize()
        st.session_state.gee_authenticated = True
        st.success("✅ GEE autenticado localmente.")
        return True
    except Exception as e:
        st.session_state.gee_authenticated = False
        st.error(f"❌ Error autenticando GEE: {e}")
        return False

if 'gee_authenticated' not in st.session_state:
    st.session_state.gee_authenticated = False
    if GEE_AVAILABLE:
        inicializar_gee()

# ================= FUNCIONES DE CARGA DE PARCELA =================
def validar_crs(gdf):
    if gdf is None or len(gdf) == 0:
        return gdf
    try:
        if gdf.crs is None:
            gdf = gdf.set_crs('EPSG:4326', inplace=False)
        elif str(gdf.crs).upper() != 'EPSG:4326':
            gdf = gdf.to_crs('EPSG:4326')
        return gdf
    except:
        return gdf

def calcular_superficie(gdf):
    try:
        gdf_proj = gdf.to_crs('EPSG:3857')
        area_m2 = gdf_proj.geometry.area.sum()
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
                st.error("❌ No se encontró archivo .shp en el ZIP")
                return None
    except Exception as e:
        st.error(f"❌ Error cargando ZIP: {e}")
        return None

def parsear_kml_manual(contenido_kml):
    try:
        root = ET.fromstring(contenido_kml)
        namespaces = {'kml': 'http://www.opengis.net/kml/2.2'}
        polygons = []
        for polygon_elem in root.findall('.//kml:Polygon', namespaces):
            coords_elem = polygon_elem.find('.//kml:coordinates', namespaces)
            if coords_elem is not None and coords_elem.text:
                coords = []
                for coord_pair in coords_elem.text.strip().split():
                    parts = coord_pair.split(',')
                    if len(parts) >= 2:
                        coords.append((float(parts[0]), float(parts[1])))
                if len(coords) >= 3:
                    polygons.append(Polygon(coords))
        if polygons:
            return gpd.GeoDataFrame({'geometry': polygons}, crs='EPSG:4326')
        return None
    except:
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
            contenido = kml_file.read().decode('utf-8')
            gdf = parsear_kml_manual(contenido)
            if gdf is not None:
                return gdf
        kml_file.seek(0)
        gdf = gpd.read_file(kml_file)
        gdf = validar_crs(gdf)
        return gdf
    except Exception as e:
        st.error(f"❌ Error cargando KML/KMZ: {e}")
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
            st.error("Formato no soportado. Use ZIP, KML, KMZ o GeoJSON.")
            return None
        if gdf is not None:
            gdf = validar_crs(gdf)
            gdf = gdf.explode(ignore_index=True)
            gdf = gdf[gdf.geometry.geom_type.isin(['Polygon', 'MultiPolygon'])]
            if len(gdf) == 0:
                st.error("No se encontraron polígonos.")
                return None
            geom_unida = gdf.unary_union
            gdf_unido = gpd.GeoDataFrame({'geometry': [geom_unida]}, crs='EPSG:4326')
            st.info(f"✅ Se unieron {len(gdf)} polígonos.")
            return gdf_unido
        return None
    except Exception as e:
        st.error(f"❌ Error cargando archivo: {e}")
        return None


# ================= NUEVAS FUNCIONES PARA MAPAS DE CALOR (NDVI, NDRE, TEMP, PRECIP, NDWI) =================
def obtener_imagen_gee_thumbnail(gdf, image_func, vis_params, dimensions='600x600'):
    """Helper: genera una URL de miniatura de GEE para el área de la parcela."""
    if not st.session_state.get('gee_authenticated', False):
        return None
    try:
        bounds = gdf.total_bounds
        region = ee.Geometry.Rectangle([bounds[0], bounds[1], bounds[2], bounds[3]])
        image = image_func(region)
        url = image.getThumbURL({
            'region': region,
            'dimensions': dimensions,
            'format': 'png',
            'min': vis_params.get('min', 0),
            'max': vis_params.get('max', 1),
            'palette': vis_params.get('palette', ['blue', 'green', 'red'])
        })
        return url
    except Exception as e:
        st.warning(f"Error generando thumbnail: {e}")
        return None

def mapa_ndvi(gdf, fecha):
    """Genera URL de mapa de calor NDVI (Sentinel-2) en la fecha más cercana disponible."""
    def build_image(region):
        collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filterBounds(region) \
            .filterDate(fecha.strftime('%Y-%m-%d'), (fecha + timedelta(days=30)).strftime('%Y-%m-%d')) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)) \
            .sort('CLOUDY_PIXEL_PERCENTAGE')
        image = collection.first()
        ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
        return ndvi.clip(region)
    return obtener_imagen_gee_thumbnail(gdf, build_image, {'min': -0.2, 'max': 0.8, 'palette': ['red', 'yellow', 'green']})

def mapa_ndre(gdf, fecha):
    """Genera URL de mapa de calor NDRE (Sentinel-2). NDRE = (B8A - B5) / (B8A + B5)"""
    def build_image(region):
        collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filterBounds(region) \
            .filterDate(fecha.strftime('%Y-%m-%d'), (fecha + timedelta(days=30)).strftime('%Y-%m-%d')) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)) \
            .sort('CLOUDY_PIXEL_PERCENTAGE')
        image = collection.first()
        ndre = image.normalizedDifference(['B8A', 'B5']).rename('NDRE')
        return ndre.clip(region)
    return obtener_imagen_gee_thumbnail(gdf, build_image, {'min': -0.2, 'max': 0.8, 'palette': ['red', 'yellow', 'green']})

def mapa_temperatura(gdf, fecha):
    """Mapa de temperatura superficial (ERA5-Land) para la fecha."""
    def build_image(region):
        collection = ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR') \
            .filterBounds(region) \
            .filterDate(fecha.strftime('%Y-%m-%d'), (fecha + timedelta(days=1)).strftime('%Y-%m-%d')) \
            .select('temperature_2m')
        image = collection.first()
        temp_c = image.subtract(273.15).rename('temp_c')
        return temp_c.clip(region)
    return obtener_imagen_gee_thumbnail(gdf, build_image, {'min': -5, 'max': 40, 'palette': ['blue', 'cyan', 'yellow', 'red']})

def mapa_precipitacion(gdf, fecha):
    """Mapa de precipitación diaria (CHIRPS)"""
    def build_image(region):
        collection = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY') \
            .filterBounds(region) \
            .filterDate(fecha.strftime('%Y-%m-%d'), (fecha + timedelta(days=1)).strftime('%Y-%m-%d')) \
            .select('precipitation')
        image = collection.first()
        return image.clip(region)
    return obtener_imagen_gee_thumbnail(gdf, build_image, {'min': 0, 'max': 50, 'palette': ['white', 'lightblue', 'blue', 'darkblue']})

def mapa_ndwi(gdf, fecha):
    """Mapa NDWI (Green-NIR)/(Green+NIR) para Sentinel-2."""
    def build_image(region):
        collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filterBounds(region) \
            .filterDate(fecha.strftime('%Y-%m-%d'), (fecha + timedelta(days=30)).strftime('%Y-%m-%d')) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)) \
            .sort('CLOUDY_PIXEL_PERCENTAGE')
        image = collection.first()
        ndwi = image.normalizedDifference(['B3', 'B8']).rename('NDWI')
        return ndwi.clip(region)
    return obtener_imagen_gee_thumbnail(gdf, build_image, {'min': -0.5, 'max': 0.5, 'palette': ['brown', 'white', 'blue']})

# ================= FUNCIONES DE IA MEJORADAS =================
def consultar_groq(prompt, max_tokens=600, model="llama-3.3-70b-versatile"):
    if not GROQ_API_KEY or not GROQ_AVAILABLE:
        return "⚠️ IA no disponible."
    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.5
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ Error: {str(e)}"

def generar_alerta_detallada(fase, ndvi, temp, precip_actual, humedad, cultivo, umbrales):
    prompt = f"""
Eres un agrónomo experto en {cultivo}. Genera una alerta agronómica detallada usando estos datos:

- Fase fenológica: {fase}
- NDVI actual: {ndvi:.2f} (umbral mínimo {umbrales['NDVI_min']:.2f})
- Temperatura: {temp:.1f}°C (rango óptimo {umbrales['temp_min']:.0f}-{umbrales['temp_max']:.0f}°C)
- Precipitación reciente (mm): {precip_actual:.1f}
- Humedad del suelo (índice SAR): {humedad:.2f} (rango óptimo {umbrales['humedad_min']:.2f}-{umbrales['humedad_max']:.2f})

Instrucciones:
1. Evalúa el nivel de riesgo para esta fase (CRÍTICO / ALTO / MEDIO / BAJO).
2. Explica las causas principales (estrés hídrico, térmico, nutricional, etc.).
3. Proporciona 3 recomendaciones concretas y accionables para el productor (riego, fertilización, protección, ajuste de fechas).
4. Si hay riesgo de helada o golpe de calor, menciónalo.
5. Formato claro, conciso, máximo 250 palabras.
"""
    return consultar_groq(prompt, max_tokens=600)

# ================= PARÁMETROS DE CULTIVOS =================
CULTIVOS = ["AJÍ", "ROCOTO", "PAPA ANDINA"]
ICONOS = {"AJÍ": "🌶️", "ROCOTO": "🥵", "PAPA ANDINA": "🥔"}
UMBRALES = {
    "AJÍ": {"NDVI_min": 0.4, "temp_min": 18, "temp_max": 30, "humedad_min": 0.25, "humedad_max": 0.65},
    "ROCOTO": {"NDVI_min": 0.45, "temp_min": 16, "temp_max": 28, "humedad_min": 0.30, "humedad_max": 0.70},
    "PAPA ANDINA": {"NDVI_min": 0.5, "temp_min": 10, "temp_max": 22, "humedad_min": 0.35, "humedad_max": 0.75}
}

# ================= INTERFAZ PRINCIPAL =================
st.set_page_config(page_title="Gestión de Riesgos Climáticos - Ají y Rocoto", layout="wide")
st.title("🌶️ Plataforma de Gestión de Riesgos Climáticos para Ají y Rocoto")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    cultivo = st.selectbox("Cultivo", CULTIVOS)
    st.info(f"{ICONOS[cultivo]} Parámetros específicos cargados.")
    uploaded_file = st.file_uploader("Subir parcela (GeoJSON, KML, KMZ, ZIP Shapefile)", type=['geojson','kml','kmz','zip'])
    fecha_fin = st.date_input("Fecha fin", datetime.now())
    fecha_inicio = st.date_input("Fecha inicio", datetime.now() - timedelta(days=90))
    fase_fenologica = st.selectbox("Fase actual del cultivo", ["siembra", "desarrollo", "floracion", "fructificacion", "cosecha"])
    usar_gee = st.checkbox("Usar GEE (si autenticado)", value=True)
    st.markdown("---")
    st.caption("📊 Datos satelitales: Sentinel-2, CHIRPS, ERA5-Land")

if not uploaded_file:
    st.info("👈 Sube un archivo de parcela para comenzar el análisis.")
    st.stop()

# Cargar parcela
with st.spinner("Cargando parcela..."):
    gdf = cargar_archivo_parcela(uploaded_file)
    if gdf is None:
        st.error("No se pudo cargar la parcela.")
        st.stop()
    area_ha = calcular_superficie(gdf)
    st.success(f"✅ Parcela cargada: {area_ha:.2f} ha, CRS EPSG:4326")

ndvi_val      = obtener_ndvi_actual(gdf)
humedad_val   = obtener_ndwi_actual(gdf)
ndre_val      = obtener_ndre_actual(gdf)
temp_val      = obtener_temperatura_actual(gdf)
precip_actual = obtener_precipitacion_actual(gdf)


if st.session_state.get("gee_authenticated", False) and usar_gee:
    with st.spinner("Descargando series temporales desde GEE..."):
        df_ndvi = obtener_serie_temporal_ndvi(gdf, fecha_inicio.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d'))
        df_precip = obtener_serie_temporal_precipitacion(gdf, fecha_inicio.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d'))
        df_temp = obtener_serie_temporal_temperatura(gdf, fecha_inicio.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d'))
        if not df_ndvi.empty:
            ndvi_val = df_ndvi['ndvi'].iloc[-1]
        if not df_temp.empty:
            temp_val = df_temp['temp'].iloc[-1]
        if not df_precip.empty:
            precip_actual = df_precip['precip'].iloc[-1]
else:
    df_ndvi = pd.DataFrame()
    df_temp = pd.DataFrame()
    df_precip = pd.DataFrame()
    st.info("Series temporales no disponibles. GEE no autenticado."))

# ================= PESTAÑAS =================
tab_dashboard, tab_hist, tab_monitoreo, tab_alerta, tab_gobernanza, tab_export = st.tabs(
    ["📊 Dashboard General", "🗺️ Mapas de Riesgo", "📈 Monitoreo Fenológico", "⚠️ Alertas IA", "📄 Gobernanza", "💾 Exportar"]
)

# ================= DASHBOARD GENERAL =================
with tab_dashboard:
    st.header("Dashboard de Indicadores Clave")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🌱 NDVI actual", f"{ndvi_val:.2f}", delta=f"{ndvi_val - UMBRALES[cultivo]['NDVI_min']:.2f}" if ndvi_val > UMBRALES[cultivo]['NDVI_min'] else "crítico")
    with col2:
        st.metric("🌡️ Temperatura", f"{temp_val:.1f} °C", delta="óptima" if UMBRALES[cultivo]['temp_min'] <= temp_val <= UMBRALES[cultivo]['temp_max'] else "alerta")
    with col3:
        st.metric("💧 Humedad suelo", f"{humedad_val:.2f}", delta="normal" if UMBRALES[cultivo]['humedad_min'] <= humedad_val <= UMBRALES[cultivo]['humedad_max'] else "crítica")
    with col4:
        st.metric("📅 Fase fenológica", fase_fenologica.capitalize(), help="Etapa actual del cultivo")
    
    st.subheader("Evolución de Índices en el Período Seleccionado")
    if not df_ndvi.empty and not df_temp.empty and not df_precip.empty:
        fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
        axes[0].plot(df_ndvi['date'], df_ndvi['ndvi'], 'g-', linewidth=2)
        axes[0].axhline(UMBRALES[cultivo]['NDVI_min'], color='red', linestyle='--', label=f"Umbral mínimo {UMBRALES[cultivo]['NDVI_min']}")
        axes[0].set_ylabel('NDVI')
        axes[0].legend()
        axes[0].grid(True)
        axes[1].plot(df_temp['date'], df_temp['temp'], 'r-', linewidth=2)
        axes[1].axhline(UMBRALES[cultivo]['temp_min'], color='blue', linestyle='--', label=f"Mín {UMBRALES[cultivo]['temp_min']}°C")
        axes[1].axhline(UMBRALES[cultivo]['temp_max'], color='orange', linestyle='--', label=f"Máx {UMBRALES[cultivo]['temp_max']}°C")
        axes[1].set_ylabel('Temperatura (°C)')
        axes[1].legend()
        axes[1].grid(True)
        axes[2].bar(df_precip['date'], df_precip['precip'], color='cyan', alpha=0.7)
        axes[2].set_ylabel('Precipitación (mm)')
        axes[2].set_xlabel('Fecha')
        axes[2].grid(True)
        plt.tight_layout()
        st.pyplot(fig)
    else:
        st.info("No hay suficientes datos históricos para mostrar tendencias. Activa GEE o selecciona un período más amplio.")
        fechas = pd.date_range(start=fecha_inicio, end=fecha_fin, freq='D')
        ndvi_sim = np.random.uniform(0.3, 0.8, len(fechas))
        temp_sim = np.random.uniform(15, 32, len(fechas))
        precip_sim = np.random.exponential(5, len(fechas))
        fig, axes = plt.subplots(3,1,figsize=(12,10))
        axes[0].plot(fechas, ndvi_sim, 'g-')
        axes[0].set_ylabel('NDVI simulado')
        axes[1].plot(fechas, temp_sim, 'r-')
        axes[1].set_ylabel('Temperatura sim. (°C)')
        axes[2].bar(fechas, precip_sim, color='cyan')
        axes[2].set_ylabel('Precipitación sim. (mm)')
        st.pyplot(fig)
    
    st.subheader("Estadísticas del Período")
    if not df_ndvi.empty:
        df_stats = pd.DataFrame({
            'Variable': ['NDVI', 'Temperatura (°C)', 'Precipitación (mm/día)'],
            'Promedio': [df_ndvi['ndvi'].mean(), df_temp['temp'].mean(), df_precip['precip'].mean()],
            'Mínimo': [df_ndvi['ndvi'].min(), df_temp['temp'].min(), df_precip['precip'].min()],
            'Máximo': [df_ndvi['ndvi'].max(), df_temp['temp'].max(), df_precip['precip'].max()],
        })
        st.dataframe(df_stats.round(2))
    else:
        st.info("Ejecuta con GEE autenticado para obtener estadísticas reales.")

# ================= MAPAS DE RIESGO (CALOR) CON NDVI, NDRE, TEMP, PRECIP, NDWI =================
with tab_hist:
    st.header("Mapas de Riesgo Climático (Heatmaps)")
    st.markdown("Visualización de NDVI, NDRE, Temperatura, Precipitación y NDWI sobre la parcela.")
    
    use_gee_maps = st.session_state.get("gee_authenticated", False) and usar_gee
    if use_gee_maps:
        with st.spinner("Generando mapas desde GEE..."):
            url_ndvi = mapa_ndvi(gdf, fecha_fin)
            url_ndre = mapa_ndre(gdf, fecha_fin)
            url_temp = mapa_temperatura(gdf, fecha_fin)
            url_precip = mapa_precipitacion(gdf, fecha_fin)
            url_ndwi = mapa_ndwi(gdf, fecha_fin)
    else:
        st.warning("GEE no autenticado o no seleccionado. Mostrando mapas simulados (simulación aleatoria).")
        url_ndvi = url_ndre = url_temp = url_precip = url_ndwi = None
    
    # Mostrar en una cuadrícula de 2x3 (5 mapas, el último espacio vacío o combinado)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("🌿 NDVI")
        if url_ndvi:
            st.image(url_ndvi, caption="NDVI (verde = mayor vigor)", use_container_width=True)
        else:
            fig, ax = plt.subplots(figsize=(4,4))
            data = np.random.rand(100,100)
            im = ax.imshow(data, cmap='RdYlGn', vmin=-0.2, vmax=0.8)
            ax.set_title("NDVI simulado")
            plt.colorbar(im, ax=ax, fraction=0.046)
            st.pyplot(fig)
        
        st.subheader("🌡️ Temperatura")
        if url_temp:
            st.image(url_temp, caption="Temperatura superficial (°C)", use_container_width=True)
        else:
            fig, ax = plt.subplots(figsize=(4,4))
            data = np.random.rand(100,100)*40 - 5
            im = ax.imshow(data, cmap='RdYlBu_r', vmin=-5, vmax=40)
            ax.set_title("Temperatura simulada")
            plt.colorbar(im, ax=ax, fraction=0.046)
            st.pyplot(fig)
    
    with col2:
        st.subheader("🌱 NDRE")
        if url_ndre:
            st.image(url_ndre, caption="NDRE (sensibilidad a clorofila)", use_container_width=True)
        else:
            fig, ax = plt.subplots(figsize=(4,4))
            data = np.random.rand(100,100)
            im = ax.imshow(data, cmap='RdYlGn', vmin=-0.2, vmax=0.8)
            ax.set_title("NDRE simulado")
            plt.colorbar(im, ax=ax, fraction=0.046)
            st.pyplot(fig)
        
        st.subheader("💧 Precipitación")
        if url_precip:
            st.image(url_precip, caption="Precipitación diaria (mm)", use_container_width=True)
        else:
            fig, ax = plt.subplots(figsize=(4,4))
            data = np.random.rand(100,100)*50
            im = ax.imshow(data, cmap='Blues', vmin=0, vmax=50)
            ax.set_title("Precipitación simulada")
            plt.colorbar(im, ax=ax, fraction=0.046)
            st.pyplot(fig)
    
    with col3:
        st.subheader("💧 NDWI")
        if url_ndwi:
            st.image(url_ndwi, caption="NDWI (contenido de agua)", use_container_width=True)
        else:
            fig, ax = plt.subplots(figsize=(4,4))
            data = np.random.rand(100,100)*1 - 0.5
            im = ax.imshow(data, cmap='Blues', vmin=-0.5, vmax=0.5)
            ax.set_title("NDWI simulado")
            plt.colorbar(im, ax=ax, fraction=0.046)
            st.pyplot(fig)
        
        st.markdown("### ℹ️ Nota")
        st.info("Los mapas de calor se generan a partir de la imagen satelital más reciente disponible en el área de la parcela. Si GEE no está autenticado, se muestran simulaciones aleatorias.")

# ================= MONITOREO FENOLÓGICO CON GRÁFICOS =================
with tab_monitoreo:
    st.header("Monitoreo Detallado por Fase Fenológica")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Indicadores Actuales")
        st.metric("NDVI", f"{ndvi_val:.2f}")
        st.metric("Temperatura", f"{temp_val:.1f} °C")
        st.metric("Humedad suelo", f"{humedad_val:.2f}")
        st.metric("Precipitación reciente", f"{precip_actual:.1f} mm")
    with col2:
        st.subheader("Comparativa con Umbrales")
        umbral = UMBRALES[cultivo]
        st.write(f"**NDVI:** {'🟢' if ndvi_val > umbral['NDVI_min'] else '🔴'} Mínimo {umbral['NDVI_min']}")
        st.write(f"**Temperatura:** {'🟢' if umbral['temp_min'] <= temp_val <= umbral['temp_max'] else '🔴'} Rango {umbral['temp_min']}-{umbral['temp_max']} °C")
        st.write(f"**Humedad:** {'🟢' if umbral['humedad_min'] <= humedad_val <= umbral['humedad_max'] else '🔴'} Rango {umbral['humedad_min']:.2f}-{umbral['humedad_max']:.2f}")
    
    st.subheader("Evolución de NDVI en los últimos 30 días")
    if not df_ndvi.empty:
        df_reciente = df_ndvi[df_ndvi['date'] >= (datetime.now() - timedelta(days=30))]
        fig, ax = plt.subplots(figsize=(10,4))
        ax.plot(df_reciente['date'], df_reciente['ndvi'], 'g-o', markersize=3)
        ax.axhline(umbral['NDVI_min'], color='red', linestyle='--', label='Umbral mínimo')
        ax.set_ylabel('NDVI')
        ax.set_title('Tendencia de vigor del cultivo')
        ax.legend()
        st.pyplot(fig)
    else:
        st.info("Datos insuficientes. Con GEE autenticado se mostrará la evolución real.")

# ================= ALERTAS IA =================
with tab_alerta:
    st.header("Alerta Fenológica Avanzada con IA")
    if st.button("🤖 Generar Alerta Detallada", type="primary", use_container_width=True):
        with st.spinner("Consultando IA (Groq) con modelo actualizado..."):
            alerta = generar_alerta_detallada(
                fase_fenologica, ndvi_val, temp_val, precip_actual, humedad_val, cultivo, UMBRALES[cultivo]
            )
        st.markdown("### 📋 Resultado del análisis")
        st.markdown(alerta)
        st.session_state.alerta_texto = alerta
        st.download_button("📥 Descargar Alerta (TXT)", data=alerta, file_name=f"alerta_{cultivo}_{datetime.now().strftime('%Y%m%d')}.txt")
    if 'alerta_texto' in st.session_state:
        st.markdown("---")
        st.subheader("Última alerta generada")
        st.info(st.session_state.alerta_texto)

# ================= GOBERNANZA Y EXPORTACIÓN =================
with tab_gobernanza:
    st.header("Gobernanza de la Gestión de Riesgos Climáticos")
    st.markdown("""
    **Estructura sugerida para la cadena de ají y rocoto:**
    - **Comité de Gestión de Riesgos**: empresa, técnicos, líderes de productores.
    - **Frecuencia de monitoreo**: mensual, con alertas quincenales durante eventos FEN.
    - **Canales de comunicación**: WhatsApp, plataforma web, reuniones.
    - **Medidas administrativas**: capacitación, protocolo de respuesta, fondo de emergencia.
    """)
    if st.button("📄 Descargar One-Page Gobernanza (PDF)"):
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
            pdf_buffer = BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=letter)
            c.drawString(100, 750, "GOBERNANZA PARA LA GESTIÓN DE RIESGOS CLIMÁTICOS")
            c.drawString(100, 730, "Cadena de Ají y Rocoto")
            c.drawString(100, 700, "Comité: coordinador, técnicos, líderes de productores.")
            c.drawString(100, 680, "Monitoreo: mensual / quincenal en FEN. Alertas por WhatsApp.")
            c.drawString(100, 660, "Medidas: capacitación anual, fondo de emergencia, protocolo de comunicación.")
            c.save()
            pdf_buffer.seek(0)
            st.download_button("Descargar PDF", data=pdf_buffer, file_name="gobernanza_riesgos.pdf", mime="application/pdf")
        except ImportError:
            st.error("ReportLab no instalado. No se puede generar PDF.")

with tab_export:
    st.header("Exportar Resultados")
    if st.button("📁 Exportar parcela a GeoJSON"):
        geojson_str = gdf.to_json()
        st.download_button("Descargar GeoJSON", data=geojson_str, file_name="parcela.geojson", mime="application/json")
    if st.button("📊 Exportar dashboard a PNG"):
        st.info("Funcionalidad avanzada: se pueden guardar los gráficos individualmente.")
    if not df_ndvi.empty:
        csv_ndvi = df_ndvi.to_csv(index=False)
        st.download_button("📈 Descargar serie NDVI (CSV)", data=csv_ndvi, file_name="ndvi_serie.csv")
    if not df_temp.empty:
        csv_temp = df_temp.to_csv(index=False)
        st.download_button("🌡️ Descargar serie Temperatura (CSV)", data=csv_temp, file_name="temperatura_serie.csv")
    if not df_precip.empty:
        csv_precip = df_precip.to_csv(index=False)
        st.download_button("💧 Descargar serie Precipitación (CSV)", data=csv_precip, file_name="precipitacion_serie.csv")

st.markdown("---")
st.caption("Plataforma avanzada con IA (Groq Llama 3.3), GEE y dashboard interactivo. Versión 4.0 - Mapas de calor NDVI y NDRE integrados.")
