# dashboard.py - Tablero de control visual para campesinos
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from modules.ia_integration import preparar_resumen_zonas, generar_analisis_fertilidad, generar_analisis_ndvi_ndre, generar_analisis_riesgo_hidrico, generar_analisis_costos, generar_recomendaciones_integradas

# ================== CONFIGURACIÓN DE LA PÁGINA ==================
st.set_page_config(
    page_title="Mi Tablero de la Finca",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ================== ESTILO PERSONALIZADO (Solo texto, sin CSS visual) ==================
# Se omite CSS personalizado para mantener la compatibilidad y simplicidad

# ================== TÍTULO PRINCIPAL ==================
st.title("🌾 Tablero de Control de mi Finca")
st.markdown("---")

# ================== SIMULACIÓN DE DATOS DE ENTRADA ==================
# Aquí debes reemplazar 'gdf_completo' con tu GeoDataFrame real que viene de tu sistema
# Este es un ejemplo SIMULADO para que el código funcione de inmediato
@st.cache_data
def cargar_datos_ejemplo():
    datos = {
        'id_zona': ['Zona 1', 'Zona 2', 'Zona 3'],
        'area_ha': [10, 15, 8],
        'fert_npk_actual': [65, 45, 85],
        'fert_ndvi': [0.62, 0.55, 0.70],
        'fert_ndre': [0.55, 0.48, 0.62],
        'fert_materia_organica': [3.5, 2.8, 4.2],
        'fert_humedad_suelo': [45, 38, 52],
        'rec_N': [80, 60, 90],
        'rec_P': [75, 55, 85],
        'rec_K': [70, 50, 80],
        'costo_costo_total': [1200, 1500, 1000],
        'proy_rendimiento_sin_fert': [2500, 2200, 2800],
        'proy_rendimiento_con_fert': [3200, 2900, 3500],
        'proy_incremento_esperado': [28, 32, 25],
        'textura_suelo': ['Franco', 'Franco arcilloso', 'Franco arenoso'],
        'arena': [40, 30, 60],
        'limo': [40, 40, 30],
        'arcilla': [20, 30, 10]
    }
    df = pd.DataFrame(datos)
    # Simulamos un GeoDataFrame simple (solo para que el código funcione)
    import geopandas as gpd
    from shapely.geometry import Point
    geometry = [Point(0,0), Point(1,1), Point(2,2)]
    gdf = gpd.GeoDataFrame(df, geometry=geometry)
    return gdf

gdf_completo = cargar_datos_ejemplo()
cultivo = "Maíz"  # Puedes cambiar el cultivo aquí o hacer que el usuario lo seleccione

# ================== PREPARAR DATOS ==================
with st.spinner("Analizando los datos de tu tierra..."):
    df_resumen, stats = preparar_resumen_zonas(gdf_completo, cultivo, max_zonas=3)

# ================== FILA 1: TARJETAS DE INDICADORES CLAVE ==================
st.header("📊 1. Indicadores Clave de un Vistazo")

col1, col2, col3, col4 = st.columns(4)

# Función para asignar color según valor
def asignar_color(valor, umbral_bajo=40, umbral_alto=70):
    if valor < umbral_bajo:
        return "🔴"  # Rojo
    elif valor > umbral_alto:
        return "🟢"  # Verde
    else:
        return "🟡"  # Amarillo

with col1:
    npk = stats['npk_prom']
    color_npk = asignar_color(npk)
    st.metric(label="🌱 Fertilidad del Suelo (NPK)", value=f"{npk:.0f}", delta=color_npk)
    st.caption("NPK: Comida rápida para la planta")
    
with col2:
    mo = stats['mo_prom']
    color_mo = asignar_color(mo, umbral_bajo=2, umbral_alto=4)
    st.metric(label="🐛 Materia Orgánica", value=f"{mo:.1f}%", delta=color_mo)
    st.caption("MO: Salud y esponjosidad de la tierra")
    
with col3:
    ndvi = stats['ndvi_prom']
    color_ndvi = asignar_color(ndvi*100, umbral_bajo=50, umbral_alto=70)
    st.metric(label="🍃 Vigor del Cultivo (NDVI)", value=f"{ndvi:.2f}", delta=color_ndvi)
    st.caption("NDVI: Qué tan verde y crecido está")
    
with col4:
    humedad = stats['humedad_prom']
    color_humedad = asignar_color(humedad, umbral_bajo=30, umbral_alto=60)
    st.metric(label="💧 Humedad del Suelo", value=f"{humedad:.0f}%", delta=color_humedad)
    st.caption("Humedad: Agua disponible en la tierra")

st.markdown("---")

# ================== FILA 2: GRÁFICOS ==================
st.header("📈 2. Comparación de tus Zonas")

col1, col2 = st.columns(2)

with col1:
    # Gráfico de barras: Fertilidad NPK por zona
    fig_npk = px.bar(
        df_resumen, 
        x='Zona', 
        y='NPK', 
        title="Fertilidad (NPK) por Zona",
        labels={'NPK': 'Índice de Fertilidad', 'Zona': ''},
        color='NPK',
        color_continuous_scale=['red', 'yellow', 'green'],
        text='NPK'
    )
    fig_npk.update_traces(texttemplate='%{text:.0f}', textposition='outside')
    fig_npk.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig_npk, use_container_width=True)
    
    st.caption("🔴 Bajo  🟡 Medio  🟢 Alto")
    
with col2:
    # Gráfico de barras: Materia Orgánica por zona
    fig_mo = px.bar(
        df_resumen, 
        x='Zona', 
        y='MO_%', 
        title="Materia Orgánica (%) por Zona",
        labels={'MO_%': 'Materia Orgánica (%)', 'Zona': ''},
        color='MO_%',
        color_continuous_scale=['red', 'yellow', 'green'],
        text='MO_%'
    )
    fig_mo.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
    fig_mo.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig_mo, use_container_width=True)
    
    st.caption("🔴 Baja (<2%)  🟡 Media (2-4%)  🟢 Alta (>4%)")

st.markdown("---")

# ================== FILA 3: MÁS GRÁFICOS ==================
col1, col2 = st.columns(2)

with col1:
    # Gráfico de indicadores NDVI y NDRE
    indicadores = df_resumen[['Zona', 'NDVI', 'NDRE']].melt(id_vars='Zona', var_name='Indicador', value_name='Valor')
    fig_ndvi = px.bar(
        indicadores, 
        x='Zona', 
        y='Valor', 
        color='Indicador',
        barmode='group',
        title="Vigor (NDVI) y Nitrógeno (NDRE)",
        labels={'Valor': 'Índice', 'Zona': ''},
        color_discrete_map={'NDVI': '#2E86AB', 'NDRE': '#A23B72'}
    )
    fig_ndvi.update_layout(height=400)
    st.plotly_chart(fig_ndvi, use_container_width=True)
    
    st.caption("NDVI = Qué tan verde está | NDRE = Cuánto nitrógeno tiene la hoja")
    
with col2:
    # Gráfico de rendimiento (con y sin fertilizante)
    rendimiento = df_resumen[['Zona', 'Rend_sin_fert', 'Rend_con_fert']].melt(id_vars='Zona', var_name='Tipo', value_name='Rendimiento')
    rendimiento['Tipo'] = rendimiento['Tipo'].map({'Rend_sin_fert': 'Sin fertilizante', 'Rend_con_fert': 'Con fertilizante'})
    fig_rend = px.bar(
        rendimiento, 
        x='Zona', 
        y='Rendimiento', 
        color='Tipo',
        barmode='group',
        title="Rendimiento (kg/ha) con y sin fertilizante",
        labels={'Rendimiento': 'Kilogramos por hectárea', 'Zona': ''},
        color_discrete_map={'Sin fertilizante': '#E6A817', 'Con fertilizante': '#4C9A2A'}
    )
    fig_rend.update_layout(height=400)
    st.plotly_chart(fig_rend, use_container_width=True)
    
    st.caption("Comparativa: cuánto más produce tu tierra con fertilizante")

st.markdown("---")

# ================== FILA 4: RESUMEN DE COSTOS ==================
st.header("💰 3. Gastos y Ahorros")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="💵 Costo total en fertilizantes", value=f"${stats['costo_total']:,.0f}", delta=None)
    st.caption("Lo que gastas ahora en química")
    
with col2:
    incremento = stats['inc_prom']
    color_inc = "🟢" if incremento > 25 else "🟡"
    st.metric(label="📈 Aumento de cosecha con fertilizante", value=f"{incremento:.0f}%", delta=color_inc)
    st.caption("Cuánto más cosechas por usar química")
    
with col3:
    ahorro = stats['costo_total'] * 0.4  # Estimación: ahorro del 40%
    st.metric(label="🤑 Ahorro potencial", value=f"${ahorro:,.0f}", delta="👍 Bueno")
    st.caption("Lo que podrías ahorrar usando abonos orgánicos")

st.markdown("---")

# ================== FILA 5: RECOMENDACIONES (FÁCIL DE LEER) ==================
st.header("🧠 4. ¿Qué puedes hacer para mejorar tu tierra?")

with st.expander("🌱 Abre aquí para ver las recomendaciones claras", expanded=True):
    st.markdown("""
    **Basado en tus datos, esto es lo que te recomendamos:**
    
    1. **La materia orgánica está baja** → Esto hace que tu tierra esté cansada y retenga poca agua.
       - ✅ **Qué hacer:** Deja los rastrojos (tallos de la cosecha) picados en la tierra. 
       - ✅ Si puedes, siembra **frijol o abono verde** entre los cultivos para poner nitrógeno gratis.
       
    2. **La humedad del suelo es baja** → A tus plantas les falta agua.
       - ✅ **Qué hacer:** Pon cobertura de paja sobre la tierra para que la humedad dure más.
       - ✅ También puedes hacer **canales o curvas a nivel** para que el agua no se escape.
       
    3. **Gastas mucho en fertilizante** → Y no estás ganando lo suficiente.
       - ✅ **Qué hacer:** Empieza a hacer tu propio **compost** con restos de cocina y basura del campo.
       - ✅ En un año, podrías **reemplazar la mitad de la química** y ahorrar dinero.
    """)

st.markdown("---")

# ================== FILA 6: ANÁLISIS AVANZADO (OPCIONAL) ==================
st.header("🔬 5. Análisis más detallado (si quieres profundizar)")

with st.spinner("Consultando al agrónomo virtual..."):
    tab1, tab2, tab3, tab4 = st.tabs(["🌾 Fertilidad", "👁️ Vigor del cultivo", "💧 Agua", "💰 Costos/Economía"])
    
    with tab1:
        st.subheader("Análisis de Fertilidad")
        respuesta_fertilidad = generar_analisis_fertilidad(df_resumen, stats, cultivo)
        st.write(respuesta_fertilidad)
        
    with tab2:
        st.subheader("Análisis de Vigor y Nitrógeno")
        respuesta_ndvi = generar_analisis_ndvi_ndre(df_resumen, stats, cultivo)
        st.write(respuesta_ndvi)
        
    with tab3:
        st.subheader("Análisis del Agua en tu Tierra")
        respuesta_hidrico = generar_analisis_riesgo_hidrico(df_resumen, stats, cultivo)
        st.write(respuesta_hidrico)
        
    with tab4:
        st.subheader("Análisis de Costos y Ahorros")
        respuesta_costos = generar_analisis_costos(df_resumen, stats, cultivo)
        st.write(respuesta_costos)

st.markdown("---")
st.info(
    """
    **¿Cómo usar este tablero?**  
    - Los colores 🟢🟡🔴 te ayudan a ver de un vistazo qué está bien y qué necesita atención.  
    - Los gráficos comparan las diferentes zonas de tu finca.  
    - Las recomendaciones prácticas están escritas para que las entiendas fácilmente.
    
    **Recuerda:** Este análisis es una guía. La mejor decisión siempre la tomas tú, conociendo tu tierra día a día.
    """
)
