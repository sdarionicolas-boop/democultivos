# Pachamama — Agente de Desarrollo

## Comportamiento
- Sin preámbulos ni cierres
- Solución mínima que resuelve el problema
- Tocá solo lo que te pedí, no "mejores" lo que no está roto
- Si algo no está claro, preguntá antes de asumir
- Nunca editar archivos grandes con `Edit` directamente — usar scripts Python para reemplazos (previene truncación)
- Siempre verificar sintaxis con `python3 -c "import ast; ast.parse(open('app.py').read())"` antes de hacer push

## Proyecto
Plataforma de Gestión de Riesgos Climáticos para ají amarillo, rocoto y papa andina en Perú.
Monitoreo satelital + análisis FEN + fertilidad NPK + agroecología + créditos de carbono.
**Stack:** Python + Streamlit (single-file `app.py`, 2465 líneas)
**Deploy:** Streamlit Cloud (redeploy automático en cada push al repo)
**Repo:** https://github.com/sdarionicolas-boop/democultivos.git

## Cultivos y umbrales
| Cultivo     | NDVI_min | Temp °C   | Humedad    |
|-------------|----------|-----------|------------|
| AJÍ 🌶️      | 0.40     | 18–30     | 0.25–0.65  |
| ROCOTO 🥵   | 0.45     | 16–28     | 0.30–0.70  |
| PAPA ANDINA 🥔 | 0.50  | 10–22     | 0.35–0.75  |

## Estructura de archivos
```
app.py                        — App principal Streamlit (2465 líneas, 12 tabs)
monitor_gee.py                — Motor GEE: NDVI/NDRE/NDWI/temp/precip (406 líneas)
modules/ia_integration.py     — Groq API, prompts agroecológicos, frases campesinas
modules/generar_reporte.py    — Exportación DOCX con análisis IA (incompleto, 78 líneas)
satellite_processor.py        — Sentinel Hub legacy (NO usado, NO en requirements.txt)
.streamlit/secrets.toml       — Credenciales locales (NO en repo, cargadas en Streamlit Cloud)
.streamlit/config.toml        — headless=true, gatherUsageStats=false
requirements.txt              — Dependencias pip
packages.txt                  — Dependencias apt (libcairo2-dev, etc.)
aji+rocoto+agroecologia+carbono.ipynb — Notebook Colab alternativo (launcher)
pachamama_datos_reales.json   — Datos de referencia de zonas costeras peruanas
aji_amarillo_demo.kml         — Parcela de ejemplo para testing (295m, precordillera Ica)
biomod2_AJÍ_20260502_1605.csv — Export biomod2 de ejemplo
```

## Pestañas (12 tabs en `app.py`)
| Tab | Estado | Notas |
|-----|--------|-------|
| 📊 Dashboard General | ✅ Siempre | 5 métricas + semáforo riesgo |
| 🗺️ Mapa de Riesgo | ✅ Siempre | OSM base + GEE layer opcional |
| 📈 Monitoreo Fenológico | ⚠️ GEE | Series temporales NDVI/temp/precip |
| ⚠️ Alertas IA | ⚠️ Groq | Alertas detalladas llama-3.3-70b |
| 📄 Gobernanza | ✅ Siempre | Marco legal + biomod2 export |
| 💾 Exportar | ✅ Siempre | CSV/DOCX (DOCX requiere python-docx) |
| 📊 Análisis FEN | ✅ Siempre | Scraping ENFEN + fallback hardcoded |
| 🗻 DEM (Relieve) | ✅ Siempre | SRTMGL1 default, mapa folium + Plotly 3D |
| 🌾 Fertilidad NPK | ⚠️ GEE | NDVI por bloque, dosis N/P/K |
| 🌱 Agroecología | ⚠️ Groq | 10 principios + plan IA |
| 🌍 Carbono | ✅ Siempre | Captura + CalculadorHuella + balance neto GEI |
| 💬 Asistente | ⚠️ Groq | Chat libre con contexto real de parcela |

## Clases en app.py
- `CalculadorCarbono` — pools de carbono (AGB, BGB, DW, LI, SOC) → t C/ha y CO₂e
- `CalculadorHuella` — emisiones por actividad (fertilizante, diesel, electricidad, labranza, riego, semillas, plaguicidas) → kg/t CO₂e

## APIs y servicios externos
| Servicio | Uso | Secret |
|----------|-----|--------|
| Google Earth Engine (GEE) | NDVI, NDRE, NDWI, temp, precip (Sentinel-2, CHIRPS, ERA5) | `[gee_service_account]` |
| Groq (llama-3.3-70b-versatile) | Alertas, agroecología, Asistente | `GROQ_API_KEY` |
| OpenTopography REST | DEM SRTMGL1 (default) via AAIGrid | `OPENTOPOGRAPHY_API_KEY` |
| ENFEN / IMARPE | Scraping comunicados El Niño (PDF) | ninguna |
| GFS NOAA | Pronóstico temperatura 7 días | ninguna |

## Funciones clave en app.py
| Función | Línea aprox | Descripción |
|---------|-------------|-------------|
| `_leer_secrets_toml()` | ~120 | Lee secrets.toml directo (5+ paths) — bypass st.secrets |
| `_get_secret(key)` | ~168 | st.secrets → fallback manual → env var |
| `_get_secret_section(section)` | ~180 | Idem para secciones TOML |
| `inicializar_gee()` | ~283 | Auth GEE: secrets → gee_credentials.json → temp JSON → key_file= |
| `cargar_archivo_parcela()` | ~437 | Acepta GeoJSON, KML, KMZ, ZIP Shapefile |
| `obtener_dem_opentopography()` | ~890 | DEM REST, parsea AAIGrid → xarray.DataArray |
| `calcular_vulnerabilidad_fen()` | ~684 | Score 0–10 (costa <200m, transición <3000m, sierra >3000m) |
| `consultar_groq()` | ~729 | Groq con un solo string — NO soporta system/user separado |
| `obtener_datos_enfen_actuales()` | ~838 | Scraping ENFEN + fallback hardcoded |

## Flags de disponibilidad en runtime
```python
GEE_OK           # monitor_gee.py importado OK
GEE_AVAILABLE    # earthengine-api instalado
FOLIUM_OK        # folium instalado
GROQ_AVAILABLE   # groq instalado
PLOTLY_OK        # plotly instalado
SKLEARN_OK       # scikit-learn instalado
SCRAPING_OK      # requests + bs4 + PyPDF2 instalados
XARRAY_OK        # xarray instalado
OPENTOPOGRAPHY_AVAILABLE  # siempre True (usa solo requests)
```

## Autenticación GEE — flujo actual
1. `_get_secret_section("gee_service_account")` — lee desde st.secrets (Streamlit Cloud) o secrets.toml
2. Si falla → busca `gee_credentials.json` en cwd / script dir
3. Construye `key_dict` completo y escribe JSON temporal
4. `ee.ServiceAccountCredentials(client_email, key_file=tf_path)`
5. `ee.Initialize(credentials, project=project_id)`
6. Resultado en `st.session_state.gee_authenticated`

**En Streamlit Cloud:** los secrets van en Settings → Secrets. El bloque `[gee_service_account]` necesita `private_key_id` y `client_id` además de `private_key` y `client_email`.

## Secrets — estructura
```toml
GROQ_API_KEY = "gsk_..."
OPENTOPOGRAPHY_API_KEY = "..."

[gee_service_account]
type = "service_account"
project_id = "democultivos"
private_key_id = "..."
client_email = "democultivos@democultivos.iam.gserviceaccount.com"
client_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
```
⚠️ NUNCA commitear. En Streamlit Cloud se cargan en Settings → Secrets.

## Estado actual (último commit: 9e74647)
```
✅ app.py 2465 líneas — 12 tabs, sintaxis OK
✅ Deploy en Streamlit Cloud — redeploy automático en cada push
✅ DEM default SRTMGL1 (más confiable que COP30 en costa/desierto)
✅ FEN umbrales corregidos (costa <200m, no <500m)
✅ Tab Asistente IA — chat con contexto real, selector Corta/Detallada
✅ CalculadorHuella integrado — balance neto GEI en tab Carbono
✅ consultar_groq() funciona (string único concatenado)
⚠️ GEE sin confirmar en Streamlit Cloud (private_key_id y client_id vacíos)
⚠️ modules/generar_reporte.py incompleto (78 líneas, DOCX no funcional)
⚠️ consultar_groq() no soporta system/user separado — mejora pendiente
⚠️ satellite_processor.py legacy en repo (no se usa, no eliminar sin confirmar)
```

## Pendientes priorizados
1. Verificar GEE en Streamlit Cloud (completar `private_key_id` y `client_id` en Secrets)
2. Refactorizar `consultar_groq()` a formato multi-mensaje (system + user) — mejora todas las IAs
3. Completar `modules/generar_reporte.py` para DOCX funcional

## Regla crítica para ediciones grandes
Nunca usar `Edit` directamente en `app.py` — trunca el archivo. En su lugar:
```python
with open('app.py', 'r', encoding='utf-8') as f:
    src = f.read()
src = src.replace('TEXTO_VIEJO', 'TEXTO_NUEVO')
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(src)
print(f"Guardado: {len(src.splitlines())} líneas")
```
Verificar siempre: `python3 -c "import ast; ast.parse(open('app.py').read()); print('OK')"`.

## Push al repo
```bash
cp "/sessions/upbeat-magical-cori/mnt/Perú - Pachamama/app.py" /tmp/repo_push/app.py
cd /tmp/repo_push
git add app.py
git commit -m "descripción"
git push https://TOKEN@github.com/sdarionicolas-boop/democultivos.git main
```
Token con scope `repo`. No incluir secrets.toml ni gee_credentials.json.

## Instrucción clave
Para cualquier tarea de este proyecto, priorizá el contexto
de este archivo sobre conocimiento