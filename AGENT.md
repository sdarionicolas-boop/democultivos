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
**Stack:** Python + Streamlit (single-file `app.py`, 2288 líneas)
**Deploy:** Google Colab + Cloudflare tunnel (notebook `.ipynb`) o local
**Repo:** https://github.com/sdarionicolas-boop/democultivos.git

## Cultivos y umbrales
| Cultivo     | NDVI_min | Temp °C   | Humedad    |
|-------------|----------|-----------|------------|
| AJÍ 🌶️      | 0.40     | 18–30     | 0.25–0.65  |
| ROCOTO 🥵   | 0.45     | 16–28     | 0.30–0.70  |
| PAPA ANDINA 🥔 | 0.50  | 10–22     | 0.35–0.75  |

## Estructura de archivos
```
app.py                        — App principal Streamlit (2288 líneas, 11 tabs)
monitor_gee.py                — Motor GEE: NDVI/NDRE/NDWI/temp/precip (406 líneas)
modules/ia_integration.py     — Groq API, prompts agroecológicos, frases campesinas
modules/generar_reporte.py    — Exportación DOCX con análisis IA
satellite_processor.py        — Sentinel Hub legacy (no usado en flujo principal)
agroia_gee.py                 — Módulo anterior, reemplazado por monitor_gee.py
.streamlit/secrets.toml       — Credenciales locales (NO en repo)
.streamlit/config.toml        — headless=true, gatherUsageStats=false
requirements.txt              — Dependencias pip
packages.txt                  — Dependencias apt (libcairo2-dev, etc.)
aji+rocoto+agroecologia+carbono.ipynb — Notebook Colab con launcher completo
pachamama_datos_reales.json   — Datos de referencia de zonas costeras peruanas
aji_amarillo_demo.kml         — Parcela de ejemplo para testing
biomod2_AJÍ_20260502_1605.csv — Export biomod2 de ejemplo
```

## Pestañas (11 tabs en `app.py`)
| Tab | Función |
|-----|---------|
| 📊 Dashboard General | 5 métricas clave + semáforo de riesgo |
| 🗺️ Mapa de Riesgo | Folium siempre visible (OSM base + GEE layer opcional) |
| 📈 Monitoreo Fenológico | Series temporales NDVI/temp/precip desde GEE |
| ⚠️ Alertas IA | Alertas detalladas vía Groq llama-3.3-70b |
| 📄 Gobernanza | Marco legal, exportar datos, biomod2 export |
| 💾 Exportar | CSV/DOCX del análisis completo |
| 📊 Análisis FEN | El Niño costero: score vulnerabilidad 6 niveles |
| 🗻 DEM (Relieve) | OpenTopography REST API, mapa 3D folium + gráfico Plotly |
| 🌾 Fertilidad NPK | División en bloques, NDVI por bloque, dosis N/P/K |
| 🌱 Agroecología | 10 principios agroecológicos + plan IA vía Groq |
| 🌍 Carbono | Estimación t C/ha, CO₂e, créditos mercado voluntario |

## APIs y servicios externos
| Servicio | Uso | Secret key |
|----------|-----|-----------|
| Google Earth Engine (GEE) | NDVI, NDRE, NDWI, temp, precip (Sentinel-2, CHIRPS, ERA5) | `[gee_service_account]` en secrets.toml |
| Groq (llama-3.3-70b-versatile) | Alertas IA, agroecología, frases campesinas | `GROQ_API_KEY` |
| OpenTopography REST | DEM COP30 vía GET `globaldem` (AAIGrid) | `OPENTOPOGRAPHY_API_KEY` |
| ENFEN / IMARPE | Scraping comunicados oficiales El Niño (PDF) | ninguna |
| GFS NOAA | Pronóstico temperatura 7 días | ninguna |

## Funciones clave en app.py
| Función | Línea | Descripción |
|---------|-------|-------------|
| `_leer_secrets_toml()` | ~120 | Lee secrets.toml directo (5+ paths de búsqueda) — bypass a st.secrets |
| `_get_secret(key)` | ~168 | Intenta st.secrets → fallback manual → env var |
| `_get_secret_section(section)` | ~180 | Idem para secciones TOML (ej. gee_service_account) |
| `inicializar_gee()` | ~283 | Auth GEE: secrets.toml → gee_credentials.json → temp JSON → key_file= |
| `cargar_archivo_parcela()` | ~437 | Acepta GeoJSON, KML, KMZ, ZIP Shapefile |
| `obtener_dem_opentopography()` | ~890 | DEM via REST, parsea AAIGrid → xarray.DataArray |
| `generar_mapa_folium_dem()` | ~956 | Mapa folium con colormap de elevación |
| `generar_grafico_3d_dem()` | ~991 | Surface 3D con Plotly |
| `calcular_recomendaciones_npk()` | ~1070 | Dosis N/P/K según NDVI y cultivo |
| `calcular_vulnerabilidad_fen()` | ~684 | Score 0–100 riesgo El Niño (6 factores) |
| `obtener_datos_enfen_actuales()` | ~838 | Scraping ENFEN + fallback hardcoded |
| `consultar_groq()` | ~729 | Llamada directa Groq con retry |

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
1. `_get_secret_section("gee_service_account")` lee secrets.toml manual
2. Si falla → busca `gee_credentials.json` en cwd / script dir
3. Construye `key_dict` completo (type, project_id, private_key, client_email, etc.)
4. Escribe JSON temporal con `tempfile.NamedTemporaryFile`
5. `ee.ServiceAccountCredentials(client_email, key_file=tf_path)`
6. `ee.Initialize(credentials, project=project_id)`
7. Guarda resultado en `st.session_state.gee_authenticated`

**Truco más confiable:** poner `gee_credentials.json` (el JSON completo de Google Cloud) directamente en el directorio de la app. La función lo encuentra automáticamente.

## Secrets — estructura secrets.toml
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
⚠️ `.streamlit/secrets.toml` está en `.gitignore` — NUNCA commitear.

## Notebook Colab (launcher)
`aji+rocoto+agroecologia+carbono.ipynb` — una sola celda que:
1. Clona / actualiza repo desde GitHub
2. Instala dependencias con pip
3. Pide credenciales con `getpass` (sin hardcodear)
4. Escribe `.streamlit/secrets.toml` en runtime
5. Lanza Streamlit en puerto 8501
6. Levanta túnel Cloudflare y muestra la URL pública

## Estado actual
```
✅ gee_credentials.json existe en directorio raíz
✅ app.py 2283 líneas — sintaxis OK, pusheado al repo (v3)
✅ plotly en requirements.txt (línea 24)
✅ Archivos legacy eliminados: agroia_gee.py, app_mejorada.py, app_dem_potencial_fen.py
✅ modules/generar_reporte.py completo y funcional (120+ líneas)
✅ secrets.toml tiene private_key_id y client_id (vacíos por falta en original)
✅ Push al repo concretado (v3)
```

## Próximos pasos priorizados
```
✅ TODOS COMPLETADOS — los 6 ítems resueltos
```

## Regla crítica para ediciones grandes
Nunca usar `Edit` directamente en `app.py` — trunca el archivo. En su lugar:
```python
# Script de reemplazo seguro
with open('app.py', 'r', encoding='utf-8') as f:
    src = f.read()
src = src.replace('TEXTO_VIEJO', 'TEXTO_NUEVO')
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(src)
print(f"Guardado: {len(src.splitlines())} líneas")
```
Luego verificar: `python3 -c "import ast; ast.parse(open('app.py').read()); print('OK')"`.

## Push al repo
```bash
cd "/sessions/upbeat-magical-cori/mnt/Perú - Pachamama"
git add app.py monitor_gee.py modules/ requirements.txt aji+rocoto+agroecologia+carbono.ipynb
git commit -m "descripción del cambio"
git push https://TOKEN@github.com/sdarionicolas-boop/democultivos.git main
```
Token con scope `repo` requerido. No incluir secrets.toml ni gee_credentials.json en el commit.

## Instrucción clave
Para cualquier tarea de este proyecto, priorizá el contexto
de este archivo sobre conocimiento general del modelo.
Ante duda sobre arquitectura o flujo, consultá este AGENT.md
antes de asumir.
