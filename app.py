import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import plotly.graph_objects as go
from datetime import datetime

# Configuración de la página
st.set_page_config(page_title="Simulador de Trading", layout="wide")
st.title("📈 Simulador de Trading Multimoneda (Paper Trading)")

# Inicializar Variables de Sesión (Session State)
if "libro_ordenes" not in st.session_state:
    st.session_state.libro_ordenes = []
if "pnl_diario" not in st.session_state:
    st.session_state.pnl_diario = 0.0

# ==========================================
# 1. BARRA LATERAL: CONFIGURACIÓN GENERAL
# ==========================================
st.sidebar.header("⚙️ Parámetros de Trading")

# Seleccionar Monedas
monedas_opciones = {
    "Bitcoin (BTC)": "BTC-USD",
    "Ethereum (ETH)": "ETH-USD",
    "Solana (SOL)": "SOL-USD",
    "USD Coin (USDC)": "USDC-USD"
}
monedas_seleccionadas = st.sidebar.multiselect(
    "Selecciona las monedas a seguir:",
    options=list(monedas_opciones.keys()),
    default=["Bitcoin (BTC)", "Ethereum (ETH)", "Solana (SOL)"]
)

# Tamaño del Trade
monto_trade = st.sidebar.number_input("Tamaño del Trade ($ USD):", min_value=10.0, value=100.0, step=10.0)

# Modo de Operación
modo_automatico = st.sidebar.toggle("🤖 Modo Automático", value=False)
st.sidebar.caption(f"Modo actual: {'**AUTOMÁTICO**' if modo_automatico else '**MANUAL**'}")

# Configuración de Bracket
st.sidebar.subheader("🎯 Configuración Bracket")
pct_tp = st.sidebar.number_input("Take Profit (%)", min_value=0.1, value=2.0, step=0.1) / 100
pct_sl = st.sidebar.number_input("Stop Loss (%)", min_value=0.1, value=1.0, step=0.1) / 100

# ==========================================
# 2. FUNCIONES DE PROCESAMIENTO Y ANÁLISIS
# ==========================================
def obtener_y_analizar_datos(ticker):
    # Cargar datos de 5 minutos
    df = yf.download(ticker, period="5d", interval="5m", progress=False)
    if df.empty:
        return None, False, 0.0, {}

    # Limpiar encabezados si yfinance devuelve MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # 1. RSI 14
    df['RSI'] = ta.momentum.rsi(df['Close'], window=14)
    
    # 2. MACD (12, 26, 9)
    macd_obj = ta.trend.MACD(df['Close'], window_slow=26, window_fast=12, window_sign=9)
    df['MACD'] = macd_obj.macd()
    df['MACD_SIGNAL'] = macd_obj.macd_signal()
    
    # 3. Bandas de Bollinger (20, 2)
    bollinger_obj = ta.volatility.BollingerBands(df['Close'], window=20, window_dev=2)
    df['BBL'] = bollinger_obj.bollinger_lband()
    df['BBM'] = bollinger_obj.bollinger_mavg()
    df['BBH'] = bollinger_obj.bollinger_hband()

    # Evaluar condiciones en la última vela cerrada (-1) y la previa (-2)
    rsi_val = df['RSI'].iloc[-1]
    
    # Regla 1: RSI <= 27
    cond_rsi = rsi_val <= 27
    
    # Regla 2: MACD cruza hacia arriba la Signal Line
    cond_macd = (df['MACD'].iloc[-2] < df['MACD_SIGNAL'].iloc[-2]) and (df['MACD'].iloc[-1] > df['MACD_SIGNAL'].iloc[-1])
    
    # Regla 3: Toca/Rompe debajo de Bollinger Inferior y la supera hacia arriba
    cond_bb = (df['Close'].iloc[-2] < df['BBL'].iloc[-2]) and (df['Close'].iloc[-1] > df['BBL'].iloc[-1])

    # Regla 2 de 3 Indicadores
    conteo_indicadores = sum([cond_rsi, cond_macd, cond_bb])
    disparo_entrada = conteo_indicadores >= 2
    
    precio_actual = df['Close'].iloc[-1]
    
    metricas = {
        "RSI": (rsi_val, cond_rsi),
        "MACD Cross": (df['MACD'].iloc[-1], cond_macd),
        "BB Rebote": (df['BBL'].iloc[-1], cond_bb),
        "Conteo": conteo_indicadores
    }

    return df, disparo_entrada, precio_actual, metricas

def ejecutar_compra(moneda, precio_entrada):
    precio_tp = precio_entrada * (1 + pct_tp)
    precio_sl = precio_entrada * (1 - pct_sl)
    
    nueva_orden = {
        "ID": len(st.session_state.libro_ordenes) + 1,
        "Hora": datetime.now().strftime("%H:%M:%S"),
        "Moneda": moneda,
        "Monto USD": monto_trade,
        "Precio Entrada": precio_entrada,
        "Take Profit": precio_tp,
        "Stop Loss": precio_sl,
        "Estado": "ABIERTA",
        "P&L USD": 0.0
    }
    st.session_state.libro_ordenes.append(nueva_orden)

def construir_grafico_velas(df, nombre_moneda):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name=nombre_moneda
    ))
    fig.add_trace(go.Scatter(x=df.index, y=df['BBH'], line=dict(color='rgba(150,150,150,0.5)', width=1), name='BB Superior'))
    fig.add_trace(go.Scatter(x=df.index, y=df['BBM'], line=dict(color='rgba(100,100,255,0.5)', width=1), name='BB Media'))
    fig.add_trace(go.Scatter(x=df.index, y=df['BBL'], line=dict(color='rgba(150,150,150,0.5)', width=1), name='BB Inferior'))
    fig.update_layout(
        height=350,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_rangeslider_visible=False,
        showlegend=False
    )
    return fig

# ==========================================
# 3. MONITOREO EN TIEMPO REAL Y PANTALLA
# ==========================================
st.button("🔄 Actualizar Mercado")

if not monedas_seleccionadas:
    st.warning("Selecciona al menos una moneda en la barra lateral para comenzar.")
else:
    cols = st.columns(len(monedas_seleccionadas))
    
    for idx, nombre_moneda in enumerate(monedas_seleccionadas):
        ticker = monedas_opciones[nombre_moneda]
        df, señal_disparada, precio_actual, metricas = obtener_y_analizar_datos(ticker)
        
        with cols[idx]:
            st.subheader(nombre_moneda)
            if df is not None:
                st.metric("Precio Actual", f"${precio_actual:,.2f}")
                
                # Desglose de Indicadores
                st.write(f"**RSI (<=27):** {metricas['RSI'][0]:.1f} {'✅' if metricas['RSI'][1] else '❌'}")
                st.write(f"**MACD Cruce Alcista:** {'✅' if metricas['MACD Cross'][1] else '❌'}")
                st.write(f"**Bollinger Rebote:** {'✅' if metricas['BB Rebote'][1] else '❌'}")
                st.caption(f"Indicadores cumplidos: **{metricas['Conteo']}/3**")

                # Gráfico de velas con Bandas de Bollinger
                st.plotly_chart(construir_grafico_velas(df, nombre_moneda), use_container_width=True, key=f"chart_{ticker}")

                # Evaluación de Entradas
                if señal_disparada:
                    st.success("🚨 ¡SEÑAL DE ENTRADA DETECTADA!")
                    if modo_automatico:
                        ordenes_abiertas = [o for o in st.session_state.libro_ordenes if o['Moneda'] == nombre_moneda and o['Estado'] == 'ABIERTA']
                        if not ordenes_abiertas:
                            ejecutar_compra(nombre_moneda, precio_actual)
                            st.info("🤖 Orden ejecutada automáticamente.")
                    else:
                        if st.button(f"🛒 Ejecutar Compra ({nombre_moneda})", key=f"btn_{ticker}"):
                            ejecutar_compra(nombre_moneda, precio_actual)
                            st.success("Orden enviada manualmente.")
                else:
                    st.info("Sin señal de entrada.")

                # Evaluar posiciones abiertas para simular Take Profit / Stop Loss
                for orden in st.session_state.libro_ordenes:
                    if orden['Moneda'] == nombre_moneda and orden['Estado'] == 'ABIERTA':
                        if precio_actual >= orden['Take Profit']:
                            orden['Estado'] = 'CERRADA (TP)'
                            orden['P&L USD'] = monto_trade * pct_tp
                            st.session_state.pnl_diario += orden['P&L USD']
                        elif precio_actual <= orden['Stop Loss']:
                            orden['Estado'] = 'CERRADA (SL)'
                            orden['P&L USD'] = - (monto_trade * pct_sl)
                            st.session_state.pnl_diario += orden['P&L USD']

# ==========================================
# 4. LIBRO DE EJECUCIONES Y P&L
# ==========================================
st.divider()
st.header("📋 Libro de Ejecuciones y P&L Diario")

m1, m2 = st.columns(2)
m1.metric("P&L Acumulado del Día", f"${st.session_state.pnl_diario:,.2f} USD")
m2.metric("Total de Trades Registrados", len(st.session_state.libro_ordenes))

if st.session_state.libro_ordenes:
    df_libro = pd.DataFrame(st.session_state.libro_ordenes)
    st.dataframe(df_libro, use_container_width=True)
else:
    st.write("Aún no hay ejecuciones registradas en la sesión.")
