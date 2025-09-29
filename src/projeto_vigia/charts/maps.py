import streamlit as st
import pydeck as pdk
import pandas as pd

def _risk_to_rgb(r):
    """
    Mapeia RiscoFogo ∈ [0,1] para cor do amarelo ao vermelho:
    0 -> amarelo (255, 215, 0)
    1 -> vermelho (220, 20, 60)
    Nulo -> cinza claro (fallback)
    """
    if pd.isna(r):
        return [180,180,180]
    r = max(0.0, min(1.0, float(r)))
    yellow = (255, 215, 0)
    red = (220, 20, 60)
    return [int(yellow[i] + (red[i]-yellow[i])*r) for i in range(3)]

def simple_map(df: pd.DataFrame):
    if df.empty:
        st.info("Sem dados para mapear.")
        return

    dff = df[["lat","lon","RiscoFogo","FRP","estado_nome","municipio_nome","Bioma","Precipitacao","DiaSemChuva"]].copy()
    dff["color"] = dff["RiscoFogo"].apply(_risk_to_rgb)

    frp = dff["FRP"].clip(lower=0.0)
    frp_norm = (frp - frp.min()) / (frp.max() - frp.min() + 1e-9)
    dff["radius"] = 300 + (frp_norm * 1700)

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=dff,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius="radius",
        pickable=True,
        opacity=0.6,
        radius_min_pixels=3,
        radius_max_pixels=100,
    )
    view_state = pdk.ViewState(latitude=dff["lat"].mean(), longitude=dff["lon"].mean(), zoom=4)
    tooltip = {
        "html": "<b>{municipio_nome}/{estado_nome}</b><br/>Bioma: {Bioma}<br/>Risco: {RiscoFogo}<br/>FRP: {FRP}<br/>Chuva(d): {DiaSemChuva} | Prec(mm): {Precipitacao}",
        "style": {"backgroundColor": "black", "color": "white"}
    }
    r = pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip, map_style=None)
    st.pydeck_chart(r)

    # Legenda simples (amarelo -> vermelho)
    st.markdown("""
    <div style="padding:6px; border:1px solid #444; display:inline-block; border-radius:6px; background:#222; color:#ddd;">
      <b>Legenda (Risco de Fogo)</b>&nbsp;&nbsp;
      <span style="display:inline-block; width:14px; height:14px; background:rgb(255,215,0);"></span> 0 &nbsp;→&nbsp;
      <span style="display:inline-block; width:14px; height:14px; background:rgb(220,20,60);"></span> 1
      &nbsp;&nbsp;<small>(cor do marcador)</small>
    </div>
    """, unsafe_allow_html=True)
