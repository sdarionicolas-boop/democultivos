# agroia_gee.py — Motor GEE corregido por AgroIA
# Reemplaza las funciones de obtener_serie_temporal_* en app.py de BioMap
# Autor: Darío Nicolás Sánchez Leguizamón

import ee
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta


def _get_imagen_limpia(geom, fecha_fin, dias=30, nube_max=30):
    fecha_inicio = fecha_fin - timedelta(days=dias)
    col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
           .filterBounds(geom)
           .filterDate(fecha_inicio.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d'))
           .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', nube_max))
           .sort('CLOUDY_PIXEL_PERCENTAGE'))
    if col.size().getInfo() == 0:
        fecha_inicio = fecha_fin - timedelta(days=90)
        col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
               .filterBounds(geom)
               .filterDate(fecha_inicio.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d'))
               .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 70))
               .sort('CLOUDY_PIXEL_PERCENTAGE'))
    return col.first()


def _gdf_to_ee_geom(gdf):
    geom = gdf.geometry.iloc[0]
    if geom.geom_type == 'MultiPolygon':
        coords = [[[c[0], c[1]] for c in poly.exterior.coords] for poly in geom.geoms]
        return ee.Geometry.MultiPolygon(coords)
    else:
        coords = [[c[0], c[1]] for c in geom.exterior.coords]
        return ee.Geometry.Polygon(coords)


def obtener_ndvi_actual(gdf, fecha_fin=None):
    """NDVI actual. Reemplaza np.random.uniform(0.3, 0.8)"""
    if fecha_fin is None:
        fecha_fin = datetime.now()
    geom = _gdf_to_ee_geom(gdf)
    img = _get_imagen_limpia(geom, fecha_fin)
    val = img.normalizedDifference(['B8', 'B4']).reduceRegion(
        ee.Reducer.mean(), geom, 10, bestEffort=True).get('nd').getInfo()
    return round(val, 3) if val is not None else 0.5


def obtener_ndwi_actual(gdf, fecha_fin=None):
    """NDWI actual (0-1). Reemplaza np.random.uniform(0.2, 0.7)"""
    if fecha_fin is None:
        fecha_fin = datetime.now()
    geom = _gdf_to_ee_geom(gdf)
    img = _get_imagen_limpia(geom, fecha_fin)
    val = img.normalizedDifference(['B3', 'B8']).reduceRegion(
        ee.Reducer.mean(), geom, 10, bestEffort=True).get('nd').getInfo()
    val_norm = (val + 1) / 2 if val is not None else None
    return round(val_norm, 3) if val_norm is not None else 0.4


def obtener_ndre_actual(gdf, fecha_fin=None):
    """NDRE actual — estado nutricional (clorofila). Banda 20m."""
    if fecha_fin is None:
        fecha_fin = datetime.now()
    geom = _gdf_to_ee_geom(gdf)
    img = _get_imagen_limpia(geom, fecha_fin)
    val = img.normalizedDifference(['B8A', 'B5']).reduceRegion(
        ee.Reducer.mean(), geom, 20, bestEffort=True).get('nd').getInfo()
    return round(val, 3) if val is not None else None


def obtener_temperatura_actual(gdf, fecha_fin=None):
    """Temperatura media °C NASA POWER. Reemplaza np.random.uniform(15, 32)"""
    if fecha_fin is None:
        fecha_fin = datetime.now() - timedelta(days=2)
    centroide = gdf.geometry.iloc[0].centroid
    fecha_inicio = fecha_fin - timedelta(days=7)
    url = (
        f"https://power.larc.nasa.gov/api/temporal/daily/point"
        f"?parameters=T2M&community=AG"
        f"&longitude={centroide.x}&latitude={centroide.y}"
        f"&start={fecha_inicio.strftime('%Y%m%d')}"
        f"&end={fecha_fin.strftime('%Y%m%d')}"
        f"&format=JSON"
    )
    try:
        r = requests.get(url, timeout=15)
        temps = list(r.json()['properties']['parameter']['T2M'].values())
        temps_validos = [t for t in temps if t != -999]
        return round(np.mean(temps_validos), 1) if temps_validos else 20.0
    except:
        return 20.0


def obtener_precipitacion_actual(gdf, fecha_fin=None, dias=30):
    """Precipitación acumulada mm CHIRPS. Reemplaza np.random.uniform(0, 20)"""
    if fecha_fin is None:
        fecha_fin = datetime.now()
    geom = _gdf_to_ee_geom(gdf)
    fecha_inicio = fecha_fin - timedelta(days=dias)
    col = (ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
           .filterBounds(geom)
           .filterDate(fecha_inicio.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d'))
           .select('precipitation'))
    if col.size().getInfo() == 0:
        return 0.0
    stats = col.sum().reduceRegion(ee.Reducer.mean(), geom, 5000, bestEffort=True).getInfo()
    val = stats.get('precipitation', None)
    return round(val, 1) if val is not None else 0.0


def obtener_serie_temporal_ndvi(gdf, start_date, end_date):
    """Serie temporal NDVI corregida."""
    geom = _gdf_to_ee_geom(gdf)
    col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
           .filterBounds(geom)
           .filterDate(start_date, end_date)
           .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)))
    def ndvi_mean(img):
        val = img.normalizedDifference(['B8', 'B4']).reduceRegion(
            ee.Reducer.mean(), geom, 10, bestEffort=True).get('nd')
        return ee.Feature(None, {'date': img.date().millis(), 'ndvi': val})
    fc = col.map(ndvi_mean).filter(ee.Filter.notNull(['ndvi']))
    rows = fc.getInfo()['features']
    df = pd.DataFrame([f['properties'] for f in rows])
    if df.empty:
        return pd.DataFrame(columns=['date', 'ndvi'])
    df['date'] = pd.to_datetime(df['date'], unit='ms')
    df['ndvi'] = pd.to_numeric(df['ndvi'], errors='coerce')
    return df.dropna().sort_values('date').reset_index(drop=True)


def obtener_serie_temporal_temperatura(gdf, start_date, end_date):
    """Serie temporal temperatura corregida."""
    geom = _gdf_to_ee_geom(gdf)
    geom_era5 = geom.buffer(15000)
    col = (ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR')
           .filterBounds(geom_era5)
           .filterDate(start_date, end_date)
           .select('temperature_2m'))
    def temp_mean(img):
        val = img.reduceRegion(ee.Reducer.mean(), geom_era5, 11132, bestEffort=True).get('temperature_2m')
        return ee.Feature(None, {'date': img.date().millis(), 'temp': val})
    fc = col.map(temp_mean).filter(ee.Filter.notNull(['temp']))
    rows = fc.getInfo()['features']
    df = pd.DataFrame([f['properties'] for f in rows])
    if df.empty:
        return pd.DataFrame(columns=['date', 'temp'])
    df['date'] = pd.to_datetime(df['date'], unit='ms')
    df['temp'] = pd.to_numeric(df['temp'], errors='coerce') - 273.15
    return df.dropna().sort_values('date').reset_index(drop=True)


def obtener_serie_temporal_precipitacion(gdf, start_date, end_date):
    """Serie temporal precipitación corregida."""
    geom = _gdf_to_ee_geom(gdf)
    col = (ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
           .filterBounds(geom)
           .filterDate(start_date, end_date)
           .select('precipitation'))
    def precip_mean(img):
        val = img.reduceRegion(ee.Reducer.mean(), geom, 5000, bestEffort=True).get('precipitation')
        return ee.Feature(None, {'date': img.date().millis(), 'precip': val})
    fc = col.map(precip_mean).filter(ee.Filter.notNull(['precip']))
    rows = fc.getInfo()['features']
    df = pd.DataFrame([f['properties'] for f in rows])
    if df.empty:
        return pd.DataFrame(columns=['date', 'precip'])
    df['date'] = pd.to_datetime(df['date'], unit='ms')
    df['precip'] = pd.to_numeric(df['precip'], errors='coerce')
    return df.dropna().sort_values('date').reset_index(drop=True)
