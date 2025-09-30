# src/projeto_vigia/ui/sections.py
from __future__ import annotations
import streamlit as st
import pandas as pd
import altair as alt

# Charts de séries/barras
from ..charts.time_series import time_chart_overall, time_chart_by_dimension
from ..charts.bar_charts import bioma_chart as _bioma_chart, municipio_chart_by_bioma as _municipio_chart_by_bioma

# Mapas (pontos + agregados)
from ..charts.maps import simple_map, hex_map, screengrid_map, grid_map

# Agregação de grade no servidor (cacheada)
from ..analytics.aggregations import aggregate_grid_cached

# Compat de largura (remove warnings de use_container_width)
from .compat import kw_for


from ..core.logging_config import get_logger
from ..core.settings import get_settings

log = get_logger(app="ProjetoVigia", module="stats")

# ==============================
# RESUMO (aba 1) — ORQUESTRADOR
# ==============================
def render_summary_tab(
    df: pd.DataFrame,
    estado: str,
    crit_df: pd.DataFrame | None = None,
    default_map_mode: str = "Agregado - Hexágonos (GPU)",
) -> None:
    """
    Orquestra a aba "Mapa e Métricas":
    1) Renderiza o 'resumo' (métricas principais do período/estado).
    2) Renderiza exatamente UM mapa (conforme seleção do usuário).
    3) Renderiza a tabela de 'Regiões Críticas' logo após o mapa.

    Parâmetros:
    - df: DataFrame já filtrado por estado/datas/bioma/turno/filtros numéricos.
    - estado: Nome do estado (ou 'Todos') — apenas para exibir no resumo.
    - crit_df: DataFrame com as regiões críticas (pré-calculadas).
    - default_map_mode: modo inicial do mapa (texto deve existir nas opções do radio).
    """
    render_summary_general(df, estado)
    render_map(df, default_mode=default_map_mode)
    render_regions_critic(crit_df)

# ==========================================
# BLOCO 1 — MÉTRICAS PRINCIPAIS DO RESUMO
# ==========================================
def render_summary_general(df: pd.DataFrame, estado: str) -> None:
    """
    Renderiza as métricas principais do período/estado selecionados.
    """
    st.subheader(f"Resumo para {estado}")

    total = len(df)
    municipio_top = df["municipio_nome"].value_counts().idxmax()
    n_muns = df["municipio_nome"].nunique()
    avg_sem_chuva = df["DiaSemChuva"].mean()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total de Focos no Período", f"{total} 🔥")
    c2.metric("Município com Mais Focos", municipio_top)
    c3.metric("Nº de Municípios Afetados", n_muns)
    c4.metric(
        "Média de Dias Sem Chuva",
        f"{avg_sem_chuva:.1f} dias" if pd.notna(avg_sem_chuva) else "N/A",
    )


# ==========================================
# BLOCO 2 — MAPA (somente UM por vez)
# ==========================================
def render_map(df: pd.DataFrame, default_mode: str = "Agregado - Hexágonos (GPU)") -> None:
    """
    Renderiza exatamente UM mapa, evitando duplicidade.
    Opções disponíveis:
    - "Pontos (cor=Risco, raio=FRP)"
    - "Agregado - Hexágonos (GPU)"
    - "Agregado - ScreenGrid (GPU)"
    - "Agregado - Grade (servidor)"

    Observações:
    - Modos 'Hexágonos' e 'ScreenGrid' agregam no CLIENTE (GPU via deck.gl).
    - 'Grade (servidor)' faz pré-agregação no servidor (menos pontos enviados).
    - O modo 'Pontos' plota cada foco individual (pode ficar pesado com muitos registros).
    """
    st.subheader("Mapa de Distribuição dos Focos")

    options = [
        "Pontos (cor=Risco, raio=FRP)",
        "Agregado - Hexágonos (GPU)",
        "Agregado - ScreenGrid (GPU)",
        "Agregado - Grade (servidor)",
    ]
    try:
        default_index = options.index(default_mode)
    except ValueError:
        default_index = 1  # fallback para 'Hexágonos (GPU)'

    mode = st.radio("Visualização do mapa", options, horizontal=True, index=default_index)

    # Renderiza um único mapa conforme o modo escolhido:
    if mode.startswith("Pontos"):
        # Pontos individuais: cor ~ RiscoFogo, raio ~ FRP
        simple_map(df)

    elif "Hexágonos" in mode:
        # Agregação na GPU (deck.gl) em hexágonos 3D; peso default = FRP
        hex_map(df)

    elif "ScreenGrid" in mode:
        # Agregação na GPU por célula de tela (mais simples e leve)
        screengrid_map(df)

    else:  # "Agregado - Grade (servidor)"
        # Slider para granularidade da grade (em graus). Maior célula => menos pontos => +performático
        cell = st.slider("Tamanho da célula (graus)", 0.05, 0.5, 0.1, 0.05)
        grid = aggregate_grid_cached(df, cell_deg=cell)
        grid_map(grid)


# ==========================================
# BLOCO 3 — REGIÕES CRÍTICAS
# ==========================================
def render_regions_critic(crit_df: pd.DataFrame | None) -> None:
    """
    Renderiza a tabela de 'Regiões Críticas' (logo após o mapa), caso exista.
    Espera um DataFrame com colunas:
      ["estado_nome","municipio_nome","Bioma",
       "focos","frp_sum","risco_medio","frp_medio","frp_max","precip_media","dias_sem_chuva_med"]
    """
    if crit_df is not None and not crit_df.empty:
        st.subheader("Regiões Críticas (top 5)")
        st.dataframe(
            crit_df[
                [
                    "estado_nome",
                    "municipio_nome",
                    "Bioma",
                    "focos",
                    "frp_sum",
                    "risco_medio",
                    "frp_medio",
                    "frp_max",
                    "precip_media",
                    "dias_sem_chuva_med",
                ]
            ],
            **kw_for(st.dataframe),
        )


# ==============================
# Outras abas
# ==============================

def render_time_tab(focos_por_dia: pd.DataFrame, df_series_estado: pd.DataFrame, df_series_bioma: pd.DataFrame):
    st.subheader("Séries temporais (dinâmicas)")
    which = st.radio("Visualizar por:", ["Geral","Estado","Bioma"], horizontal=True)
    if which == "Geral":
        st.altair_chart(
            time_chart_overall(focos_por_dia),
            **kw_for(st.altair_chart)
        )
    elif which == "Estado":
        st.altair_chart(
            time_chart_by_dimension(df_series_estado, "estado_nome"),
            **kw_for(st.altair_chart)
        )
    else:
        st.altair_chart(
            time_chart_by_dimension(df_series_bioma, "Bioma"),
            **kw_for(st.altair_chart)
        )

def render_biome_city_tab(df_bioma: pd.DataFrame, df_mun_bioma: pd.DataFrame):
    st.subheader("Distribuição de Focos por Bioma")
    st.altair_chart(_bioma_chart(df_bioma), **kw_for(st.altair_chart))

    st.subheader("Top 10 Municípios com Mais Focos")
    st.altair_chart(_municipio_chart_by_bioma(df_mun_bioma), **kw_for(st.altair_chart))

def render_prevention_tab():
    st.subheader("Como Prevenir Queimadas")
    st.markdown("""
    - **🚭 Não jogue bitucas de cigarro** em áreas de vegetação.
    - **🗑️ Não queime lixo**; é ilegal e perigoso.
    - **🏕️ Fogueiras com cuidado** e apague totalmente ao sair.
    - **🎈 Não solte balões** (crime e risco grave).
    - **🏡 Faça aceiro e mantenha terreno limpo**.
    - **📞 Ao avistar foco, ligue 193 (Bombeiros) ou 199 (Defesa Civil)**.
    """)

def render_stats_tab(df: pd.DataFrame):
    S = get_settings()
    
    VIOLETA = S.RISK_COLOR_FOR_STATS  # blueviolet
    
    st.subheader("Análise Estatística")
    cols_num = ["DiaSemChuva","Precipitacao","RiscoFogo","FRP"]
    
    df_num = (df[cols_num]
              .apply(pd.to_numeric, errors="coerce")
              .dropna(how="any"))  # precisa estar completo para corr()

    st.markdown("**Resumo estatístico**")
    st.dataframe(df_num.describe().T, **kw_for(st.dataframe))

    st.markdown("**Distribuições** (histograma + densidade)")
    target = st.selectbox("Escolha a variável:", cols_num, index=2)
    base = alt.Chart(df_num)

    # Cor violeta quando a variável for RiscoFogo
    hist_color = VIOLETA if target == "RiscoFogo" else None
    dens_color = VIOLETA if target == "RiscoFogo" else None

    chart = (base
             .transform_density(target, as_=[target, 'density'])
             .mark_area(opacity=0.4, color=dens_color)
             .encode(x=alt.X(f"{target}:Q", title=target), y="density:Q"))
    hist = (base
            .mark_bar(opacity=0.5, color=hist_color)
            .encode(x=alt.X(f"{target}:Q", bin=True), y="count()"))
    st.altair_chart(hist + chart, **kw_for(st.altair_chart))

    st.markdown("**Correlação**")
    chosen = st.multiselect("Selecione variáveis para correlação", cols_num, default=cols_num)
    
    if len(chosen) >= 2:
        corr_input = (df[chosen]
                      .apply(pd.to_numeric, errors="coerce")
                      .dropna(how="any"))
        if corr_input.empty:
            st.info("Sem dados suficientes (após limpar valores ausentes) para calcular correlação.")
            log.warning("correlation_skipped_empty_after_dropna", chosen=chosen)
            return

        corr = corr_input.corr().reset_index().melt("index")
        corr.columns = ["Var1", "Var2", "corr"]
        heat = (alt.Chart(corr)
                .mark_rect()
                .encode(
                    x="Var1:O", y="Var2:O",
                    color=alt.Color("corr:Q", scale=alt.Scale(scheme="redyellowblue", domain=(-1,1))),
                    tooltip=["Var1","Var2","corr"]
                ).properties(height=300))
        st.altair_chart(heat, **kw_for(st.altair_chart))
    else:
        st.info("Selecione pelo menos duas variáveis.")
