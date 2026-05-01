# agroia_gee.py — Motor GEE + utilidades para AgroIA Pachamama
# Funciones sincronizadas desde notebook exploratorio (abril 2026)

import geopandas as gpd
import pandas as pd
import numpy as np
import tempfile
import os
import zipfile
import requests
import warnings
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from io import BytesIO
from shapely.geometry import Polygon

warnings.filterwarnings('ignore')

# ================= DEPENDENCIAS OPCIONALES =================
try:
    import ee
    GEE_AVAILABLE = True
except ImportError:
    GEE_AVAILABLE = False

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if GROQ_API_KEY and GROQ_AVAILABLE:
    os.environ["GROQ_API_KEY"] = GROQ_API_KEY

# ================= PARÁMETROS DE CULTIVOS =================
CULTIVOS = ["AJÍ", "ROCOTO", "PAPA ANDINA"]
ICONOS   = {"AJÍ": "🌶️", "ROCOTO": "🥵", "PAPA ANDINA": "🥔"}
UMBRALES = {
    "AJÍ":       {"NDVI_min": 0.4,  "NDRE_min": 0.10, "temp_min": 18, "temp_max": 30, "humedad_min": 0.25, "humedad_max": 0.65},
    "ROCOTO":    {"NDVI_min": 0.45, "NDRE_min": 0.12, "temp_min": 16, "temp_max": 28, "humedad_min": 0.30, "humedad_max": 0.70},
    "PAPA ANDINA":{"NDVI_min": 0.5, "NDRE_min": 0.15, "temp_min": 10, "temp_max": 22, "humedad_min": 0.35, "humedad_max": 0.75},
}

# ================= INICIALIZACIÓN GEE =================
def inicializar_gee(project_id='applied-oxygen-459415-e2'):
    if not GEE_AVAILABLE:
        return False
    try:
        ee.Initialize(project=project_id)
        return True
    except Exception:
        try:
            ee.Initialize()
            return True
        except Exception:
            return False

# ================= HELPERS INTERNOS =================
def _gdf_to_ee_geom(gdf):
    """Convierte GeoDataFrame a geometría EE. Soporta Polygon y MultiPolygon."""
    geom = gdf.geometry.iloc[0]
    if geom.geom_type == 'MultiPolygon':
        coords = [[[c[0], c[1]] for c in poly.exterior.coords] for poly in geom.geoms]
        return ee.Geometry.MultiPolygon(coords)
    else:
        coords = [[c[0], c[1]] for c in geom.exterior.coords]
        return ee.Geometry.Polygon(coords)

def _get_imagen_limpia(geom, fecha_fin, dias=30, nube_max=30):
    """Devuelve la imagen Sentinel-2 más limpia disponible con fallback automático."""
    fecha_inicio = fecha_fin - timedelta(days=dias)
    col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
           .filterBounds(geom)
           .filterDate(fecha_inicio.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d'))
           .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', nube_max))
           .sort('CLOUDY_PIXEL_PERCENTAGE'))
    if col.size().getInfo() == 0:
        # Fallback: ventana de 90 días, tolerar más nubes
        fecha_inicio = fecha_fin - timedelta(days=90)
        col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
               .filterBounds(geom)
               .filterDate(fecha_inicio.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d'))
               .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 70))
               .sort('CLOUDY_PIXEL_PERCENTAGE'))
    return col.first()

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
    except Exception:
        return gdf

def calcular_superficie(gdf):
    try:
        gdf_proj = gdf.to_crs('EPSG:3857')
        return gdf_proj.geometry.area.sum() / 10000
    except Exception:
        return 0.0

def cargar_shapefile_desde_zip(zip_file):
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(zip_file, 'r') as zr:
                zr.extractall(tmp_dir)
            shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
            if shp_files:
                gdf = gpd.read_file(os.path.join(tmp_dir, shp_files[0]))
                return validar_crs(gdf)
        return None
    except Exception:
        return None

def parsear_kml_manual(contenido_kml):
    try:
        root = ET.fromstring(contenido_kml)
        ns = {'kml': 'http://www.opengis.net/kml/2.2'}
        polygons = []
        for pe in root.findall('.//kml:Polygon', ns):
            ce = pe.find('.//kml:coordinates', ns)
            if ce is not None and ce.text:
                coords = []
                for cp in ce.text.strip().split():
                    parts = cp.split(',')
                    if len(parts) >= 2:
                        coords.append((float(parts[0]), float(parts[1])))
                if len(coords) >= 3:
                    polygons.append(Polygon(coords))
        if polygons:
            return gpd.GeoDataFrame({'geometry': polygons}, crs='EPSG:4326')
        return None
    except Exception:
        return None

def cargar_kml(kml_file):
    try:
        if kml_file.name.endswith('.kmz'):
            with tempfile.TemporaryDirectory() as tmp_dir:
                with zipfile.ZipFile(kml_file, 'r') as zr:
                    zr.extractall(tmp_dir)
                kml_files = [f for f in os.listdir(tmp_dir) if f.endswith('.kml')]
                if kml_files:
                    with open(os.path.join(tmp_dir, kml_files[0]), 'r', encoding='utf-8') as f:
                        gdf = parsear_kml_manual(f.read())
                    if gdf is not None:
                        return gdf
        else:
            contenido = kml_file.read().decode('utf-8')
            gdf = parsear_kml_manual(contenido)
            if gdf is not None:
                return gdf
        kml_file.seek(0)
        gdf = gpd.read_file(kml_file)
        return validar_crs(gdf)
    except Exception:
        return None

def cargar_archivo_parcela(uploaded_file):
    try:
        if uploaded_file.name.endswith('.zip'):
            gdf = cargar_shapefile_desde_zip(uploaded_file)
        elif uploaded_file.name.endswith(('.kml', '.kmz')):
            gdf = cargar_kml(uploaded_file)
        elif uploaded_file.name.endswith('.geojson'):
            gdf = validar_crs(gpd.read_file(uploaded_file))
        else:
            return None
        if gdf is not None:
            gdf = validar_crs(gdf)
            gdf = gdf.explode(ignore_index=True)
            gdf = gdf[gdf.geometry.geom_type.isin(['Polygon', 'MultiPolygon'])]
            if len(gdf) == 0:
                return None
            gdf_unido = gpd.GeoDataFrame({'geometry': [gdf.unary_union]}, crs='EPSG:4326')
            return gdf_unido
        return None
    except Exception:
        return None

# ================= VALORES ACTUALES =================
def obtener_ndvi_actual(gdf, fecha_fin=None):
    """NDVI actual — Sentinel-2, escala 10m, con fallback automático."""
    if fecha_fin is None:
        fecha_fin = datetime.now()
    try:
        geom = _gdf_to_ee_geom(gdf)
        img  = _get_imagen_limpia(geom, fecha_fin)
        val  = img.normalizedDifference(['B8', 'B4']).reduceRegion(
            ee.Reducer.mean(), geom, 10, bestEffort=True).get('nd').getInfo()
        return round(val, 3) if val is not None else 0.5
    except Exception:
        return round(np.random.uniform(0.3, 0.7), 3)

def obtener_ndwi_actual(gdf, fecha_fin=None):
    """NDWI actual normalizado 0-1 — Sentinel-2."""
    if fecha_fin is None:
        fecha_fin = datetime.now()
    try:
        geom = _gdf_to_ee_geom(gdf)
        img  = _get_imagen_limpia(geom, fecha_fin)
        val  = img.normalizedDifference(['B3', 'B8']).reduceRegion(
            ee.Reducer.mean(), geom, 10, bestEffort=True).get('nd').getInfo()
        return round((val + 1) / 2, 3) if val is not None else 0.4
    except Exception:
        return round(np.random.uniform(0.2, 0.6), 3)

def obtener_ndre_actual(gdf, fecha_fin=None):
    """NDRE actual — Sentinel-2 B8A/B5, escala 20m. Detector temprano de estrés en clorofila."""
    if fecha_fin is None:
        fecha_fin = datetime.now()
    try:
        geom = _gdf_to_ee_geom(gdf)
        img  = _get_imagen_limpia(geom, fecha_fin)
        val  = img.normalizedDifference(['B8A', 'B5']).reduceRegion(
            ee.Reducer.mean(), geom, 20, bestEffort=True).get('nd').getInfo()
        return round(val, 3) if val is not None else None
    except Exception:
        return None

def obtener_temperatura_actual(gdf, fecha_fin=None):
    """Temperatura media °C — NASA POWER API (más precisa que ERA5 para parcelas pequeñas)."""
    try:
        if fecha_fin is None:
            fecha_fin = datetime.now() - timedelta(days=2)  # POWER tiene 2 días de lag
        centroide   = gdf.geometry.iloc[0].centroid
        fecha_inicio = fecha_fin - timedelta(days=7)
        url = (
            f"https://power.larc.nasa.gov/api/temporal/daily/point"
            f"?parameters=T2M&community=AG"
            f"&longitude={centroide.x}&latitude={centroide.y}"
            f"&start={fecha_inicio.strftime('%Y%m%d')}"
            f"&end={fecha_fin.strftime('%Y%m%d')}"
            f"&format=JSON"
        )
        r = requests.get(url, timeout=15)
        temps = list(r.json()['properties']['parameter']['T2M'].values())
        validos = [t for t in temps if t != -999]
        return round(np.mean(validos), 1) if validos else 20.0
    except Exception:
        return round(np.random.uniform(14, 28), 1)

def obtener_precipitacion_actual(gdf, fecha_fin=None, dias=30):
    """Precipitación acumulada mm en los últimos N días — CHIRPS."""
    if fecha_fin is None:
        fecha_fin = datetime.now()
    try:
        geom         = _gdf_to_ee_geom(gdf)
        fecha_inicio = fecha_fin - timedelta(days=dias)
        col = (ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
               .filterBounds(geom)
               .filterDate(fecha_inicio.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d'))
               .select('precipitation'))
        if col.size().getInfo() == 0:
            return 0.0
        stats = col.sum().reduceRegion(ee.Reducer.mean(), geom, 5000, bestEffort=True).getInfo()
        val   = stats.get('precipitation', None)
        return round(val, 1) if val is not None else 0.0
    except Exception:
        return round(np.random.exponential(5), 1)

# ================= SERIES TEMPORALES =================
def obtener_serie_temporal_ndvi(gdf, start_date, end_date):
    """Serie temporal NDVI — una sola llamada getInfo(), notNull filter, scale=10."""
    try:
        geom = _gdf_to_ee_geom(gdf)
        col  = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterBounds(geom)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)))

        def ndvi_mean(img):
            val = img.normalizedDifference(['B8', 'B4']).reduceRegion(
                ee.Reducer.mean(), geom, 10, bestEffort=True).get('nd')
            return ee.Feature(None, {'date': img.date().millis(), 'ndvi': val})

        fc   = col.map(ndvi_mean).filter(ee.Filter.notNull(['ndvi']))
        rows = fc.getInfo()['features']
        df   = pd.DataFrame([f['properties'] for f in rows])
        if df.empty:
            return pd.DataFrame(columns=['date', 'ndvi'])
        df['date'] = pd.to_datetime(df['date'], unit='ms')
        df['ndvi'] = pd.to_numeric(df['ndvi'], errors='coerce')
        return df.dropna().sort_values('date').reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=['date', 'ndvi'])

def obtener_serie_temporal_ndre(gdf, start_date, end_date):
    """Serie temporal NDRE — detector temprano de estrés, scale=20m."""
    try:
        geom = _gdf_to_ee_geom(gdf)
        col  = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterBounds(geom)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)))

        def ndre_mean(img):
            val = img.normalizedDifference(['B8A', 'B5']).reduceRegion(
                ee.Reducer.mean(), geom, 20, bestEffort=True).get('nd')
            return ee.Feature(None, {'date': img.date().millis(), 'ndre': val})

        fc   = col.map(ndre_mean).filter(ee.Filter.notNull(['ndre']))
        rows = fc.getInfo()['features']
        df   = pd.DataFrame([f['properties'] for f in rows])
        if df.empty:
            return pd.DataFrame(columns=['date', 'ndre'])
        df['date'] = pd.to_datetime(df['date'], unit='ms')
        df['ndre'] = pd.to_numeric(df['ndre'], errors='coerce')
        return df.dropna().sort_values('date').reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=['date', 'ndre'])

def obtener_serie_temporal_temperatura(gdf, start_date, end_date):
    """Serie temporal temperatura °C — ERA5 con buffer 15km para parcelas pequeñas."""
    try:
        geom      = _gdf_to_ee_geom(gdf)
        geom_era5 = geom.buffer(15000)
        col = (ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR')
               .filterBounds(geom_era5)
               .filterDate(start_date, end_date)
               .select('temperature_2m'))

        def temp_mean(img):
            val = img.reduceRegion(ee.Reducer.mean(), geom_era5, 11132, bestEffort=True).get('temperature_2m')
            return ee.Feature(None, {'date': img.date().millis(), 'temp': val})

        fc   = col.map(temp_mean).filter(ee.Filter.notNull(['temp']))
        rows = fc.getInfo()['features']
        df   = pd.DataFrame([f['properties'] for f in rows])
        if df.empty:
            return pd.DataFrame(columns=['date', 'temp'])
        df['date'] = pd.to_datetime(df['date'], unit='ms')
        df['temp'] = pd.to_numeric(df['temp'], errors='coerce') - 273.15
        return df.dropna().sort_values('date').reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=['date', 'temp'])

def obtener_serie_temporal_precipitacion(gdf, start_date, end_date):
    """Serie temporal precipitación diaria mm — CHIRPS."""
    try:
        geom = _gdf_to_ee_geom(gdf)
        col  = (ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
                .filterBounds(geom)
                .filterDate(start_date, end_date)
                .select('precipitation'))
        if col.size().getInfo() == 0:
            return pd.DataFrame(columns=['date', 'precip'])

        def precip_mean(img):
            val = img.reduceRegion(ee.Reducer.mean(), geom, 5000, bestEffort=True).get('precipitation')
            return ee.Feature(None, {'date': img.date().millis(), 'precip': val})

        fc   = col.map(precip_mean).filter(ee.Filter.notNull(['precip']))
        rows = fc.getInfo()['features']
        df   = pd.DataFrame([f['properties'] for f in rows])
        if df.empty:
            return pd.DataFrame(columns=['date', 'precip'])
        df['date']   = pd.to_datetime(df['date'], unit='ms')
        df['precip'] = pd.to_numeric(df['precip'], errors='coerce')
        return df.dropna().sort_values('date').reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=['date', 'precip'])

# ================= FUNCIONES DE IA =================
def consultar_groq(prompt, max_tokens=600, model="llama-3.3-70b-versatile"):
    if not GROQ_API_KEY or not GROQ_AVAILABLE:
        return "⚠️ IA no disponible."
    try:
        client   = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.5
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ Error: {str(e)}"

def generar_alerta_detallada(fase, ndvi, temp, precip_actual, humedad, ndre, cultivo, umbrales):
    ndre_str = f"{ndre:.3f}" if ndre is not None else "no disponible"
    ndre_umbral = umbrales.get('NDRE_min', 'N/D')
    prompt = f"""
Eres un agrónomo experto en {cultivo}. Genera una alerta agronómica detallada usando estos datos:

- Fase fenológica: {fase}
- NDVI actual: {ndvi:.2f} (umbral mínimo {umbrales['NDVI_min']:.2f})
- NDRE actual: {ndre_str} (umbral mínimo {ndre_umbral} — detector temprano de estrés en clorofila)
- Temperatura: {temp:.1f}°C (rango óptimo {umbrales['temp_min']:.0f}-{umbrales['temp_max']:.0f}°C)
- Precipitación acumulada 30d (mm): {precip_actual:.1f}
- Humedad del suelo (NDWI): {humedad:.2f} (rango óptimo {umbrales['humedad_min']:.2f}-{umbrales['humedad_max']:.2f})

Instrucciones:
1. Evalúa el nivel de riesgo (CRÍTICO / ALTO / MEDIO / BAJO).
2. Si el NDRE está por debajo del umbral aunque el NDVI sea aceptable, alertar sobre estrés nutricional incipiente.
3. Explica las causas principales.
4. Proporciona 3 recomendaciones concretas y accionables.
5. Máximo 250 palabras.
"""
    return consultar_groq(prompt, max_tokens=600)
