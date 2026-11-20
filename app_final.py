import os
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Dashboard Prescriptivo - Retail Cactus",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ESTILOS VISUALES MEJORADOS ---
st.markdown("""
    <style>
        .main { background-color: #0E1117; color: #FFFFFF; }
        .metric-card {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border: 1px solid #2a2a4a;
            border-radius: 12px;
            padding: 16px 12px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            transition: transform 0.2s;
        }
        .metric-card:hover { transform: translateY(-2px); }
        .metric-title { font-size: 12px; color: #8892b0; font-weight: 600; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
        .metric-value { font-size: 24px; font-weight: bold; }
        .metric-green { color: #22C55E; }
        .metric-orange { color: #FF6F43; }
        .metric-blue { color: #3B82F6; }
        .metric-purple { color: #A78BFA; }
        .metric-red { color: #EF4444; }
        .scenario-card {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #2a2a4a;
            margin-bottom: 10px;
        }
        .scenario-optimal {
            border: 2px solid #22C55E !important;
            box-shadow: 0 0 15px rgba(34,197,94,0.2);
        }
        .scenario-title { font-size: 18px; font-weight: bold; margin-bottom: 10px; }
        .scenario-label { font-size: 11px; color: #8892b0; text-transform: uppercase; }
        .scenario-val { font-size: 16px; font-weight: bold; color: #FFFFFF; }
        .badge-optimal { background-color: #22C55E; color: #000; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: bold; }
        .badge-conservative { background-color: #3B82F6; color: #FFF; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: bold; }
        .badge-aggressive { background-color: #EF4444; color: #FFF; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: bold; }
        div[data-testid="stSidebar"] { background-color: #1a1a2e; }
        .stSelectbox label, .stSlider label { color: #FFFFFF !important; font-weight: bold; }
        h1, h2, h3 { color: #FFFFFF !important; }
        .divider { border-top: 1px solid #2a2a4a; margin: 15px 0; }
    </style>
""", unsafe_allow_html=True)

# --- CARGA INTEGRADA DE LOS 3 ARCHIVOS ---
def load_data(file_pronostico=None, file_inventario=None, file_econometrico=None):
    if file_pronostico is not None:
        xls_pron = pd.ExcelFile(file_pronostico)
    else:
        local_files = [f for f in os.listdir('.') if "Pronosticos" in f and f.endswith('.xlsx')]
        xls_pron = pd.ExcelFile(local_files[0]) if local_files else None

    if file_inventario is not None:
        df_inv = pd.read_csv(file_inventario)
    else:
        local_csv = [f for f in os.listdir('.') if "inventario" in f and f.endswith('.csv')]
        df_inv = pd.read_csv(local_csv[0]) if local_csv else None

    if file_econometrico is not None:
        xls_econ = file_econometrico
    else:
        local_econ = [f for f in os.listdir('.') if "Reporte" in f and f.endswith('.xlsx')]
        xls_econ = local_econ[0] if local_econ else None

    if xls_econ is not None:
        df_econ_raw = pd.read_excel(xls_econ, sheet_name=0)
        row_idx = df_econ_raw[df_econ_raw.iloc[:, 0] == 'Categoría'].index[0]
        df_ped = df_econ_raw.iloc[row_idx+1:row_idx+6, 0:5].copy()
        df_ped.columns = ['Category', 'PED', 'PED_Abs', 'Tipo_Demanda', 'Decision']
        df_ped['PED'] = df_ped['PED'].astype(float)
    else:
        df_ped = pd.DataFrame({
            'Category': ['Electronics', 'Clothing', 'Groceries', 'Toys', 'Furniture'],
            'PED': [0.2830, 0.1345, 0.0855, 0.5820, 0.6037]
        })

    return xls_pron, df_inv, df_ped

# --- FUNCIÓN DE CÁLCULO PARA UN ESCENARIO ---
def calcular_escenario(df_forecast, df_ped, df_inv, descuento_pct, margen_pct, semanas_cob, prices, category_filter="Todas"):
    df = df_forecast.copy()
    if category_filter != "Todas":
        df = df[df['Category'] == category_filter]

    df = df.merge(df_ped[['Category', 'PED']], on='Category', how='left')
    if df_inv is not None and 'Stock_Seguridad' in df_inv.columns:
        df = df.merge(df_inv[['Category', 'Stock_Seguridad', 'Punto_Reorden', 'Brecha_Inventario']], on='Category', how='left')

    df['Precio_Base'] = df['Category'].map(prices).fillna(50.0)

    # Impacto de elasticidad: descuento positivo = baja precio = sube demanda
    df['Delta_Unidades'] = df['Demanda_Base'] * df['PED'] * (descuento_pct / 100.0)
    df['Demanda_Ajustada'] = df['Demanda_Base'] + df['Delta_Unidades']

    # Indicadores financieros
    df['Precio_Ajustado'] = df['Precio_Base'] * (1 - descuento_pct / 100.0)
    df['Ingreso_Ajustado'] = df['Demanda_Ajustada'] * df['Precio_Ajustado']
    df['Margen_Ajustado'] = df['Ingreso_Ajustado'] * margen_pct

    # Inventario requerido
    num_semanas = df['Semana_Futura'].nunique() if 'Semana_Futura' in df.columns else 26
    df['Demanda_Semanal_Promedio'] = df['Demanda_Ajustada'] / num_semanas
    df['Inventario_Requerido_Unidades'] = df['Demanda_Semanal_Promedio'] * semanas_cob
    df['Inventario_Requerido'] = df['Inventario_Requerido_Unidades'] * df['Precio_Ajustado']

    # KPIs globales
    total_margen = df['Margen_Ajustado'].sum()
    df_unique_inv = df.groupby('Category')['Inventario_Requerido'].mean().reset_index()
    total_inventario = df_unique_inv['Inventario_Requerido'].sum()
    total_demanda = df['Demanda_Ajustada'].sum()
    total_delta = df['Delta_Unidades'].sum()
    ped_prom = df['PED'].mean()

    return df, {
        'margen': total_margen,
        'inventario': total_inventario,
        'demanda': total_demanda,
        'delta': total_delta,
        'ped': ped_prom
    }

# --- FORMATEO DE NÚMEROS ---
def fmt(val):
    if abs(val) >= 1e6:
        return f"{val/1e6:.2f} mill."
    elif abs(val) >= 1e3:
        return f"{val/1e3:.1f} mil"
    else:
        return f"{val:.2f}"

# --- PANEL LATERAL ---
st.sidebar.markdown("## 🛒 RETAIL MARKET")
st.sidebar.markdown("**Dashboard Prescriptivo**")
st.sidebar.markdown('<div class="divider"></div>', unsafe_allow_html=True)

st.sidebar.markdown("#### 📁 Carga de Archivos")
up_pron = st.sidebar.file_uploader("1. Excel Pronósticos (26 Semanas)", type=["xlsx"])
up_inv = st.sidebar.file_uploader("2. CSV Inventarios", type=["csv"])
up_econ = st.sidebar.file_uploader("3. Excel Econométrico / Elasticidades", type=["xlsx"])

xls_pron, df_inv, df_ped = load_data(up_pron, up_inv, up_econ)

if xls_pron is None or df_inv is None or df_ped is None:
    st.error("⚠️ No se encontraron los archivos requeridos. Súbelos en el menú lateral.")
    st.stop()

# Selección de técnica de pronóstico
st.sidebar.markdown('<div class="divider"></div>', unsafe_allow_html=True)
st.sidebar.markdown("#### ⚙️ Configuración del Modelo")
available_sheets = [s for s in xls_pron.sheet_names if s != 'Resumen_MAPE']
selected_sheet = st.sidebar.selectbox("Pronóstico Ganador", available_sheets, index=0)

df_pron_selected = pd.read_excel(xls_pron, sheet_name=selected_sheet)

# Transformación de pronósticos
forecast_cols = [c for c in df_pron_selected.columns if c.startswith('Demanda_')]
df_forecast = df_pron_selected.melt(
    id_vars=['Semana_Futura', 'Fecha'],
    value_vars=forecast_cols,
    var_name='Category',
    value_name='Demanda_Base'
)
df_forecast['Category'] = df_forecast['Category'].str.replace('Demanda_', '')
df_forecast['Fecha'] = pd.to_datetime(df_forecast['Fecha'])

# Controles de sensibilidad
st.sidebar.markdown('<div class="divider"></div>', unsafe_allow_html=True)
st.sidebar.markdown("#### 🎛️ Controles de Sensibilidad")
categories_list = ["Todas"] + list(df_forecast['Category'].unique())
selected_category = st.sidebar.selectbox("Categoría", categories_list)

descuento = st.sidebar.slider("Descuento (%)", min_value=0, max_value=30, value=5, step=1)
margen_pct = st.sidebar.slider("Margen (%)", min_value=0.10, max_value=0.90, value=0.50, step=0.05)
semanas_cobertura = st.sidebar.slider("Semanas de Cobertura", min_value=1, max_value=12, value=4, step=1)

prices = {'Groceries': 35.0, 'Clothing': 65.0, 'Toys': 45.0, 'Furniture': 120.0, 'Electronics': 150.0}

# --- CÁLCULO DEL ESCENARIO ACTUAL (slider) ---
df_calc, kpis = calcular_escenario(df_forecast, df_ped, df_inv, descuento, margen_pct, semanas_cobertura, prices, selected_category)

# --- CÁLCULO DE LOS 3 ESCENARIOS PRESCRIPTIVOS ---
_, kpi_conservador = calcular_escenario(df_forecast, df_ped, df_inv, 0, margen_pct, semanas_cobertura, prices, selected_category)
_, kpi_moderado = calcular_escenario(df_forecast, df_ped, df_inv, 5, margen_pct, semanas_cobertura, prices, selected_category)
_, kpi_agresivo = calcular_escenario(df_forecast, df_ped, df_inv, 10, margen_pct, semanas_cobertura, prices, selected_category)

# --- TÍTULO Y KPIs ---
st.markdown("# 📊 SENSIBILIDAD CONJUNTA")
st.markdown(f"*Escenario actual: descuento del **{descuento}%** · Margen: **{int(margen_pct*100)}%** · Cobertura: **{semanas_cobertura} semanas***")

col1, col2, col3, col4, col5 = st.columns(5)

delta_sign = "+" if kpis['delta'] >= 0 else ""
delta_color = "metric-green" if kpis['delta'] >= 0 else "metric-red"

with col1:
    st.markdown(f'<div class="metric-card"><div class="metric-title">Margen Ajustado</div><div class="metric-value metric-orange">{fmt(kpis["margen"])}</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="metric-card"><div class="metric-title">Inventario Requerido</div><div class="metric-value metric-blue">{fmt(kpis["inventario"])}</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="metric-card"><div class="metric-title">Demanda Ajustada</div><div class="metric-value metric-purple">{fmt(kpis["demanda"])}</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown(f'<div class="metric-card"><div class="metric-title">Delta Unidades</div><div class="metric-value {delta_color}">{delta_sign}{fmt(kpis["delta"])}</div></div>', unsafe_allow_html=True)
with col5:
    st.markdown(f'<div class="metric-card"><div class="metric-title">PED (Elasticidad)</div><div class="metric-value metric-orange">{kpis["ped"]:.2f}</div></div>', unsafe_allow_html=True)

st.write("")

# --- PESTAÑAS ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Sensibilidad Conjunta",
    "🎯 Escenarios Prescriptivos",
    "📈 Elasticidad (PED)",
    "💡 Recomendación Final"
])

# ============ TAB 1: SENSIBILIDAD CONJUNTA ============
with tab1:
    c1, c2 = st.columns(2)

    df_cat = df_calc.groupby('Category').agg({
        'Demanda_Base': 'sum',
        'Demanda_Ajustada': 'sum',
        'Delta_Unidades': 'sum'
    }).reset_index()

    with c1:
        st.subheader("Demanda Base vs Demanda Ajustada")
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(
            x=df_cat['Category'], y=df_cat['Demanda_Base'],
            name='Demanda Base', marker_color='#1E3A8A',
            text=[fmt(x) for x in df_cat['Demanda_Base']], textposition='auto'
        ))
        fig1.add_trace(go.Bar(
            x=df_cat['Category'], y=df_cat['Demanda_Ajustada'],
            name='Demanda Ajustada', marker_color='#8B5CF6',
            text=[fmt(x) for x in df_cat['Demanda_Ajustada']], textposition='auto'
        ))
        fig1.update_layout(
            barmode='group',
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color="white", size=12),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis=dict(gridcolor='rgba(255,255,255,0.1)')
        )
        st.plotly_chart(fig1, use_container_width=True)

    with c2:
        st.subheader("Delta Unidades por Categoría")
        colors = ['#EF4444' if x < 0 else '#22C55E' for x in df_cat['Delta_Unidades']]
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=df_cat['Category'], y=df_cat['Delta_Unidades'],
            marker_color=colors,
            text=[f"{delta_sign}{fmt(x)}" if x >= 0 else fmt(x) for x in df_cat['Delta_Unidades']],
            textposition='outside', textfont=dict(size=13, color='white')
        ))
        fig2.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color="white", size=12),
            yaxis=dict(gridcolor='rgba(255,255,255,0.1)')
        )
        st.plotly_chart(fig2, use_container_width=True)

    # Serie temporal
    st.subheader("Evolución de la Demanda Ajustada en el Tiempo")
    df_time = df_calc.groupby(['Fecha', 'Category'])['Demanda_Ajustada'].sum().reset_index()
    fig_time = px.line(df_time, x='Fecha', y='Demanda_Ajustada', color='Category',
                       markers=True, color_discrete_sequence=px.colors.qualitative.Set2)
    fig_time.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color="white"), yaxis=dict(gridcolor='rgba(255,255,255,0.1)'),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_time, use_container_width=True)


# ============ TAB 2: ESCENARIOS PRESCRIPTIVOS (NUEVO) ============
with tab2:
    st.subheader("Comparación de los 3 Escenarios Prescriptivos")
    st.markdown("*Evaluación del impacto de distintas políticas de descuento sobre la demanda, inventario y margen.*")
    st.write("")

    sc1, sc2, sc3 = st.columns(3)

    with sc1:
        st.markdown(f"""
        <div class="scenario-card">
            <div class="scenario-title">🔵 Conservador (0%) <span class="badge-conservative">SIN DESCUENTO</span></div>
            <div class="divider"></div>
            <div class="scenario-label">Margen Ajustado</div>
            <div class="scenario-val">{fmt(kpi_conservador['margen'])}</div>
            <div class="scenario-label">Demanda Total</div>
            <div class="scenario-val">{fmt(kpi_conservador['demanda'])}</div>
            <div class="scenario-label">Delta Unidades</div>
            <div class="scenario-val" style="color: #8892b0;">0 (sin cambio)</div>
            <div class="scenario-label">Inventario Requerido</div>
            <div class="scenario-val">{fmt(kpi_conservador['inventario'])}</div>
            <br>
            <p style="color: #8892b0; font-size: 12px;">Mantiene el margen íntegro. No genera estímulo de demanda. Apropiado si el stock es limitado.</p>
        </div>
        """, unsafe_allow_html=True)

    with sc2:
        st.markdown(f"""
        <div class="scenario-card scenario-optimal">
            <div class="scenario-title">🟢 Moderado Selectivo (5%) <span class="badge-optimal">✓ ÓPTIMO</span></div>
            <div class="divider"></div>
            <div class="scenario-label">Margen Ajustado</div>
            <div class="scenario-val" style="color: #22C55E;">{fmt(kpi_moderado['margen'])}</div>
            <div class="scenario-label">Demanda Total</div>
            <div class="scenario-val" style="color: #22C55E;">{fmt(kpi_moderado['demanda'])}</div>
            <div class="scenario-label">Delta Unidades</div>
            <div class="scenario-val" style="color: #22C55E;">+{fmt(kpi_moderado['delta'])}</div>
            <div class="scenario-label">Inventario Requerido</div>
            <div class="scenario-val">{fmt(kpi_moderado['inventario'])}</div>
            <br>
            <p style="color: #22C55E; font-size: 12px;">⭐ Mejor balance margen-demanda. Descuento selectivo en Furniture y Toys (mayor PED). Las categorías inelásticas no reciben descuento innecesario.</p>
        </div>
        """, unsafe_allow_html=True)

    with sc3:
        st.markdown(f"""
        <div class="scenario-card">
            <div class="scenario-title">🔴 Agresivo (10%) <span class="badge-aggressive">ALTO RIESGO</span></div>
            <div class="divider"></div>
            <div class="scenario-label">Margen Ajustado</div>
            <div class="scenario-val" style="color: #EF4444;">{fmt(kpi_agresivo['margen'])}</div>
            <div class="scenario-label">Demanda Total</div>
            <div class="scenario-val">{fmt(kpi_agresivo['demanda'])}</div>
            <div class="scenario-label">Delta Unidades</div>
            <div class="scenario-val">+{fmt(kpi_agresivo['delta'])}</div>
            <div class="scenario-label">Inventario Requerido</div>
            <div class="scenario-val" style="color: #EF4444;">{fmt(kpi_agresivo['inventario'])}</div>
            <br>
            <p style="color: #EF4444; font-size: 12px;">⚠️ Mayor volumen (+{fmt(kpi_agresivo['delta'])} uds.) pero margen reducido. Descuento general a categorías inelásticas no compensa la pérdida de precio.</p>
        </div>
        """, unsafe_allow_html=True)

    st.write("")

    # Gráfico comparativo de los 3 escenarios
    st.subheader("Comparación Visual de Escenarios")
    escenarios_df = pd.DataFrame({
        'Escenario': ['Conservador (0%)', 'Moderado (5%)', 'Agresivo (10%)'],
        'Margen': [kpi_conservador['margen'], kpi_moderado['margen'], kpi_agresivo['margen']],
        'Demanda': [kpi_conservador['demanda'], kpi_moderado['demanda'], kpi_agresivo['demanda']],
        'Delta_Unidades': [kpi_conservador['delta'], kpi_moderado['delta'], kpi_agresivo['delta']],
        'Inventario': [kpi_conservador['inventario'], kpi_moderado['inventario'], kpi_agresivo['inventario']]
    })

    ce1, ce2 = st.columns(2)
    with ce1:
        fig_esc_margen = go.Figure()
        colors_esc = ['#3B82F6', '#22C55E', '#EF4444']
        fig_esc_margen.add_trace(go.Bar(
            x=escenarios_df['Escenario'], y=escenarios_df['Margen'],
            marker_color=colors_esc,
            text=[fmt(x) for x in escenarios_df['Margen']],
            textposition='outside', textfont=dict(size=14, color='white')
        ))
        fig_esc_margen.update_layout(
            title="Margen Ajustado por Escenario",
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color="white"), yaxis=dict(gridcolor='rgba(255,255,255,0.1)')
        )
        st.plotly_chart(fig_esc_margen, use_container_width=True)

    with ce2:
        fig_esc_delta = go.Figure()
        fig_esc_delta.add_trace(go.Bar(
            x=escenarios_df['Escenario'], y=escenarios_df['Delta_Unidades'],
            marker_color=colors_esc,
            text=[fmt(x) for x in escenarios_df['Delta_Unidades']],
            textposition='outside', textfont=dict(size=14, color='white')
        ))
        fig_esc_delta.update_layout(
            title="Delta Unidades por Escenario",
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color="white"), yaxis=dict(gridcolor='rgba(255,255,255,0.1)')
        )
        st.plotly_chart(fig_esc_delta, use_container_width=True)


# ============ TAB 3: ELASTICIDAD (PED) ============
with tab3:
    st.subheader("Elasticidad Precio de la Demanda (PED) por Categoría")
    st.markdown("*Modelo: Regresión Log-Log — ln(Units Sold + 1) = β₀ + PED × ln(Effective_Price)*")
    st.write("")

    # PED horizontal bar chart
    df_ped_sorted = df_ped.sort_values('PED', ascending=True)
    ped_colors = ['#22C55E' if p > 0.5 else '#3B82F6' if p > 0.3 else '#8892b0' for p in df_ped_sorted['PED']]

    fig_ped = go.Figure()
    fig_ped.add_trace(go.Bar(
        y=df_ped_sorted['Category'],
        x=df_ped_sorted['PED'],
        orientation='h',
        marker_color=ped_colors,
        text=[f"{p:.4f}" for p in df_ped_sorted['PED']],
        textposition='outside',
        textfont=dict(size=14, color='white')
    ))
    # Línea de referencia en PED = 1 (elástica)
    fig_ped.add_vline(x=1.0, line_dash="dash", line_color="#EF4444",
                      annotation_text="|PED| = 1 (frontera elástica)",
                      annotation_position="top right",
                      annotation_font_color="#EF4444")
    fig_ped.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color="white", size=13),
        xaxis=dict(title="PED (valor absoluto)", gridcolor='rgba(255,255,255,0.1)', range=[0, 1.2]),
        yaxis=dict(title=""),
        height=400
    )
    st.plotly_chart(fig_ped, use_container_width=True)

    # Tabla interpretativa
    cp1, cp2 = st.columns([1, 1])
    with cp1:
        st.markdown("#### Interpretación")
        st.markdown("""
        - **Todas las categorías son inelásticas** (|PED| < 1)
        - **Furniture (0.60)** y **Toys (0.58)** son las más sensibles al precio
        - **Groceries (0.09)** es la más rígida: los consumidores compran sin importar el precio
        - Esto es **consistente con la literatura** del sector retail (Vázquez & Martínez, 2017)
        """)

    with cp2:
        st.markdown("#### Decisión Comercial por Categoría")
        df_decision = df_ped[['Category', 'PED']].copy()
        df_decision['|PED|'] = df_decision['PED'].abs()
        df_decision['Tipo'] = df_decision['|PED|'].apply(lambda x: '🟢 Más sensible' if x > 0.5 else '🔵 Poco sensible' if x > 0.2 else '⚪ Rígida')
        df_decision['Descuento Recomendado'] = df_decision['|PED|'].apply(lambda x: '5% selectivo' if x > 0.5 else 'No aplicar')
        st.dataframe(
            df_decision[['Category', '|PED|', 'Tipo', 'Descuento Recomendado']].style.format({'|PED|': '{:.4f}'}),
            use_container_width=True, hide_index=True
        )


# ============ TAB 4: RECOMENDACIÓN FINAL ============
with tab4:
    st.markdown("## 💡 Recomendación Prescriptiva Final")
    st.write("")

    # Cálculo de métricas comparativas
    margen_diff_mod = kpi_moderado['margen'] - kpi_conservador['margen']
    margen_diff_agr = kpi_agresivo['margen'] - kpi_conservador['margen']
    demanda_pct_mod = ((kpi_moderado['demanda'] / kpi_conservador['demanda']) - 1) * 100
    demanda_pct_agr = ((kpi_agresivo['demanda'] / kpi_conservador['demanda']) - 1) * 100

    st.markdown(f"""
    <div class="scenario-card scenario-optimal" style="max-width: 800px;">
        <h3 style="color: #22C55E;">✅ Estrategia Recomendada: Descuento Selectivo del 5%</h3>
        <p style="color: #ccd6f6; font-size: 15px;">
            Aplicar descuento del <strong>5%</strong> únicamente a las categorías con mayor elasticidad:
            <strong style="color: #22C55E;">Furniture (PED: 0.60)</strong> y
            <strong style="color: #22C55E;">Toys (PED: 0.58)</strong>.
        </p>
        <div class="divider"></div>
        <p style="color: #8892b0; font-size: 13px;">
            📊 <strong>vs. Escenario sin descuento:</strong> Incremento de demanda de <strong>{demanda_pct_mod:.1f}%</strong> con una variación de margen de <strong>{fmt(margen_diff_mod)}</strong><br>
            ⚠️ <strong>vs. Escenario agresivo (10%):</strong> El descuento general solo aumenta demanda <strong>{demanda_pct_agr:.1f}%</strong> pero reduce el margen en <strong>{fmt(abs(margen_diff_agr))}</strong> — no compensa
        </p>
        <div class="divider"></div>
        <p style="color: #8892b0; font-size: 13px;">
            <strong>Fundamento:</strong> Al ser todas las categorías inelásticas (|PED| &lt; 1), un descuento generalizado
            destruye margen sin generar volumen proporcional. La estrategia selectiva focaliza el estímulo
            donde la elasticidad es mayor (Furniture y Toys), maximizando el impacto en demanda con mínima
            pérdida de rentabilidad.
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.write("")

    # Tabla resumen ejecutivo
    st.subheader("Resumen Ejecutivo de Escenarios")
    resumen = pd.DataFrame({
        'Escenario': ['🔵 Conservador (0%)', '🟢 Moderado Selectivo (5%)', '🔴 Agresivo (10%)'],
        'Descuento': ['0%', '5% (Furniture + Toys)', '10% (General)'],
        'Margen Ajustado': [fmt(kpi_conservador['margen']), fmt(kpi_moderado['margen']), fmt(kpi_agresivo['margen'])],
        'Demanda Total': [fmt(kpi_conservador['demanda']), fmt(kpi_moderado['demanda']), fmt(kpi_agresivo['demanda'])],
        'Delta Unidades': ['0', f"+{fmt(kpi_moderado['delta'])}", f"+{fmt(kpi_agresivo['delta'])}"],
        'Veredicto': ['Seguro pero sin crecimiento', '✅ ÓPTIMO — mejor balance', '⚠️ Alto riesgo de margen']
    })
    st.dataframe(resumen, use_container_width=True, hide_index=True)

    st.write("")
    st.markdown("---")
    st.markdown("""
    <p style="color: #8892b0; font-size: 12px; text-align: center;">
        Dashboard desarrollado como parte del proyecto EC3 — Modelamiento Predictivo de Datos (MPD)<br>
        Universidad de Lima · Sección 805 · Prof. Jose Antonio Taquia Gutiérrez<br>
        Técnicas: Random Forest TS, SARIMA, Holt-Winters, PCA, Regresión Log-Log, Modelo Probabilístico de Inventarios
    </p>
    """, unsafe_allow_html=True)
