# src/projeto_vigia/charts/maps.py
from __future__ import annotations
import streamlit as st
import pydeck as pdk
import pandas as pd

from ..core.settings import get_settings
from ..ui.compat import kw_for

def _risk_to_rgb(r):
    """
    Mapeia RiscoFogo ∈ [0,1] para cor do amarelo ao vermelho:
    0 -> amarelo (255, 215, 0)
    1 -> vermelho (220, 20, 60)
    Nulo -> cinza claro (fallback)
    """
    S = get_settings()
    
    if pd.isna(r):
        return [180,180,180]
    r = max(0.0, min(1.0, float(r)))
    yellow = S.MAP_RISK_YELLOW
    red = S.MAP_RISK_RED
    return [int(yellow[i] + (red[i]-yellow[i])*r) for i in range(3)]

def simple_map(df: pd.DataFrame):
    S = get_settings()
    
    if df.empty:
        st.info("Sem dados para mapear.")
        return

    dff = df[["lat","lon","RiscoFogo","FRP","estado_nome","municipio_nome","Bioma","Precipitacao","DiaSemChuva"]].copy()
    dff["color"] = dff["RiscoFogo"].apply(_risk_to_rgb)

    frp = dff["FRP"].clip(lower=0.0)
    frp_norm = (frp - frp.min()) / (frp.max() - frp.min() + 1e-9)
    dff["radius"] = S.MAP_RADIUS_MIN_M + frp_norm * (S.MAP_RADIUS_MAX_M - S.MAP_RADIUS_MIN_M)

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

def hex_map(df: pd.DataFrame):
    """Agrega no cliente em hexágonos 3D (elevação ~ contagem/peso)."""    
    S = get_settings()

    if df.empty:
        st.info("Sem dados para mapear.")
        return

    dff = df[["lat","lon","FRP"]].dropna(subset=["lat","lon"]).copy()
    view = pdk.ViewState(latitude=dff["lat"].mean(), longitude=dff["lon"].mean(), zoom=4)

    layer = pdk.Layer(
        "HexagonLayer",
        data=dff,
        get_position="[lon, lat]",
        radius=S.MAP_RADIUS_MAX_M // 3,  # ajuste fino
        elevation_scale=10,
        elevation_range=[0, 3000],
        extruded=True,
        coverage=1.0,
        pickable=True,
        # use FRP como peso (opcional); sem isso, agrega contagem de pontos
        get_elevation_weight="FRP",
        elevation_aggregation="SUM",
    )

    deck = pdk.Deck(layers=[layer], initial_view_state=view, map_style=None,
                    tooltip={"text":"Soma FRP do bin: {elevationValue}"})
    st.pydeck_chart(deck, **kw_for(st.pydeck_chart))

def screengrid_map(df: pd.DataFrame):
    """Agrega no cliente por tela (ScreenGrid), cor ~ intensidade."""
    if df.empty:
        st.info("Sem dados para mapear.")
        return

    dff = df[["lat","lon","FRP"]].dropna(subset=["lat","lon"]).copy()
    view = pdk.ViewState(latitude=dff["lat"].mean(), longitude=dff["lon"].mean(), zoom=4)

    layer = pdk.Layer(
        "ScreenGridLayer",
        data=dff,
        get_position="[lon, lat]",
        cell_size_pixels=30,  # maior → menos células, mais rápido
        color_range=[
            [255, 215, 0, 80],  # amarelo translúcido
            [255, 165, 0, 120],
            [255, 99, 71, 160],
            [220, 20, 60, 200], # vermelho mais forte
        ],
        get_weight="FRP",  # ou 1 para contagem
        aggregation="SUM",
        pickable=False,
    )

    deck = pdk.Deck(layers=[layer], initial_view_state=view, map_style=None)
    st.pydeck_chart(deck, **kw_for(st.pydeck_chart))

def grid_map(df_grid: pd.DataFrame):
    """Plota centroides de células agregadas, cor ~ risco, raio ~ FRP sum."""
    S = get_settings()
    
    if df_grid.empty:
        st.info("Sem dados para mapear.")
        return

    dff = df_grid.copy()
    dff["color"] = dff["risco_medio"].apply(_risk_to_rgb)

    x = dff["frp_sum"].clip(lower=0.0)
    x_norm = (x - x.min()) / (x.max() - x.min() + 1e-9)
    dff["radius"] = S.MAP_RADIUS_MIN_M + x_norm * (S.MAP_RADIUS_MAX_M - S.MAP_RADIUS_MIN_M)

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=dff,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius="radius",
        pickable=True,
        opacity=0.65,
        radius_min_pixels=3,
        radius_max_pixels=100,
    )
    view = pdk.ViewState(latitude=dff["lat"].mean(), longitude=dff["lon"].mean(), zoom=4)
    deck = pdk.Deck(layers=[layer], initial_view_state=view, map_style=None,
                    tooltip={"text":"Focos: {focos}\nRisco: {risco_medio}\nFRP sum: {frp_sum}"})
    st.pydeck_chart(deck, **kw_for(st.pydeck_chart))

    # legenda
    st.markdown("""
    <div style="padding:6px; border:1px solid #444; display:inline-block; border-radius:6px; background:#222; color:#ddd;">
      <b>Legenda (Risco de Fogo)</b>&nbsp;&nbsp;
      <span style="display:inline-block; width:14px; height:14px; background:rgb(255,215,0);"></span> 0 &nbsp;→&nbsp;
      <span style="display:inline-block; width:14px; height:14px; background:rgb(220,20,60);"></span> 1
      &nbsp;&nbsp;<small>(cor do marcador)</small>
    </div>
    """, unsafe_allow_html=True)