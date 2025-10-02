# src/projeto_vigia/ui/sections.py
from __future__ import annotations
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import datetime as dt

# Charts de séries/barras
from ..charts.time_series import time_chart_overall, time_chart_by_dimension
from ..charts.bar_charts import bioma_chart as _bioma_chart, municipio_chart_by_bioma as _municipio_chart_by_bioma

# Mapas (pontos + agregados)
from ..charts.maps import simple_map, hex_map, screengrid_map, grid_map

# Agregação de grade no servidor (cacheada)
from ..analytics.aggregations import aggregate_grid_cached, choose_time_freq, aggregate_time

# Compat de largura (remove warnings de use_container_width)
from .compat import kw_for

from ..core.logging_config import get_logger
from ..core.settings import get_settings

log = get_logger(app="ProjetoVigia", module="stats")

def _to_py_dt(x):
    """Converte qualquer coisa (Timestamp, str, etc.) para datetime.datetime (naive)."""
    if x is None or pd.isna(x):
        return None
    if isinstance(x, dt.datetime):
        return x
    # pandas.Timestamp -> datetime
    try:
        return pd.to_datetime(x).to_pydatetime()
    except Exception:
        return None

def _coerce_time_range_tuple(val, default_lo: dt.datetime, default_hi: dt.datetime):
    """
    Garante que o value da session seja (datetime, datetime) consistente para o slider.
    Se inválido, retorna (default_lo, default_hi).
    """
    if not isinstance(val, (list, tuple)) or len(val) != 2:
        return (default_lo, default_hi)
    lo, hi = _to_py_dt(val[0]), _to_py_dt(val[1])
    if lo is None or hi is None:
        return (default_lo, default_hi)
    # corrige inversão acidental
    if lo > hi:
        lo, hi = hi, lo
    # clip para os limites do dataset
    lo = max(lo, default_lo)
    hi = min(hi, default_hi)
    return (lo, hi)

def _top_k_labels(df: pd.DataFrame, col: str, k: int = 5) -> list[str]:
    """
    Retorna as 'k' categorias mais frequentes em 'col' (após filtros atuais).
    """
    return (
        df[col]
        .dropna()
        .value_counts()
        .head(k)
        .index
        .astype(str)
        .tolist()
    )

def _hist_server_side(x: pd.Series, bins: int = 60) -> pd.DataFrame:
    """
    Calcula histograma no servidor (numpy), retornando DataFrame [x, count].
    'x' são os limites esquerdos dos bins (edges[:-1]).
    """
    x = pd.to_numeric(x, errors="coerce").dropna()
    if x.empty:
        return pd.DataFrame({"x": [], "count": []})
    counts, edges = np.histogram(x, bins=bins)
    return pd.DataFrame({"x": edges[:-1], "count": counts})

def density_series(x: pd.Series, bins: int = 60) -> pd.DataFrame:
    """
    Calcula histograma simples no servidor (mais leve para o browser).
    Retorna DataFrame com colunas x (bin left) e count.
    """
    x = pd.to_numeric(x, errors="coerce").dropna()
    counts, edges = np.histogram(x, bins=bins)
    return pd.DataFrame({"x": edges[:-1], "count": counts})

# ==============================
# RESUMO (aba 1) — ORQUESTRADOR
# ==============================
def render_summary_tab(
    df: pd.DataFrame,
    estado: str,
    crit_df: pd.DataFrame | None = None,
    default_map_mode: str = "Agregado - Grade (servidor)",
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
    render_map_3(df, default_mode=default_map_mode)
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
def render_map(df: pd.DataFrame, default_mode: str = "Agregado - Grade (servidor)") -> None:
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

def render_map_2(df: pd.DataFrame, default_mode: str = "Agregado - Grade (servidor)") -> None:
    """
    Renderiza exatamente UM mapa, evitando duplicidade.
    
    Painel à direita contendo:
      - Filtro de risco de fogo (0–1) com duas alças (range slider)
      - Barra de cor vertical (amarelo → vermelho) como legenda da escala
    O filtro se aplica a TODOS os modos de mapa.
    
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

    # opções de modo
    options = [
        "Pontos (cor=Risco, raio=FRP)",
        "Agregado - Hexágonos (GPU)",
        "Agregado - ScreenGrid (GPU)",
        "Agregado - Grade (servidor)",
    ]
    try:
        default_index = options.index(default_mode)
    except ValueError:
        default_index = 1  # fallback

    # mode = st.radio("Visualização do mapa", options, horizontal=True, index=default_index)
    
    # layout: mapa à esquerda (mais largo), controles/legenda à direita
    left, right = st.columns([5, 1], gap="large")

    with right:
        # --- CONTROLES DO LADO DIREITO ---
        S = get_settings()

        # estado persistente do slider de risco (sobrevive aos reruns)
        if "risk_range" not in st.session_state:
            st.session_state["risk_range"] = (0.0, 1.0)

        # slider horizontal com 2 alças (0–1), passo 0.01
        lo, hi = st.slider(
            "Risco de fogo (0–1)",
            min_value=0.0, max_value=1.0,
            value=st.session_state["risk_range"],
            step=0.01,
            help="Mostra apenas focos cujo RiscoFogo esteja dentro da faixa selecionada."
        )
        # guarda de volta (para quando trocar o modo do mapa não perder o filtro)
        st.session_state["risk_range"] = (lo, hi)

        # barra de cor vertical (amarelo → vermelho) como referência visual
        # usamos as cores do settings (MAP_RISK_YELLOW e MAP_RISK_RED)
        y = S.MAP_RISK_YELLOW
        r = S.MAP_RISK_RED
        grad_css = f"linear-gradient(to bottom, rgb({y[0]},{y[1]},{y[2]}), rgb({r[0]},{r[1]},{r[2]}))"
        st.markdown(
            f"""
            <div style="display:flex; flex-direction:column; align-items:center;">
              <div style="height:160px; width:20px; background:{grad_css};
                          border:1px solid #444; border-radius:4px; margin:6px 0;"></div>
              <div style="width:40px; display:flex; justify-content:space-between; font-size:12px; color:#ddd;">
                <span>0</span><span>1</span>
              </div>
              <div style="font-size:11px; color:#aaa; margin-top:4px;">Escala do risco</div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # seletor do modo do mapa (fica junto do painel de controle,
        # assim o usuário enxerga que é “configuração da visualização”)
        mode = st.radio("Modo", options, index=default_index)

    # --- FILTRO DE RISCO APLICADO AO DATAFRAME ---
    # 1) converte RiscoFogo para numérico seguro
    dff = df.copy()
    dff["RiscoFogo"] = pd.to_numeric(dff["RiscoFogo"], errors="coerce")
    # 2) remove inválidos (NaN resultantes, -999 já vira NaN lá atrás, mas fica a prova de bala)
    dff = dff.dropna(subset=["RiscoFogo"])
    # 3) filtra pela faixa escolhida no slider
    #    inclusive em ambas as pontas (0 e 1)
    mask = (dff["RiscoFogo"] >= lo) & (dff["RiscoFogo"] <= hi)
    dff = dff.loc[mask]

    # --- MAPA (UM ÚNICO) ---
    with left:
        if dff.empty:
            st.info("Nenhum ponto atende ao filtro de risco selecionado.")
            return

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

def render_map_3(df: pd.DataFrame, default_mode: str = "Agregado - Grade (servidor)") -> None:
    """
    Renderiza exatamente UM mapa e dois filtros de visualização:
      - À direita: filtro de RiscoFogo (0–1, duas alças) + seletor de modo do mapa
      - Abaixo do mapa: escala de Tempo (início/fim) com duas alças (datetime)

    Ambos os filtros se aplicam a TODOS os modos de mapa (Pontos, Hex, ScreenGrid, Grade).
    Os valores ficam persistidos em st.session_state para sobreviver a reruns e troca de modo.
    """
    st.subheader("Mapa de Distribuição dos Focos")

    # Opções de modo
    options = [
        "Pontos (cor=Risco, raio=FRP)",
        "Agregado - Hexágonos (GPU)",
        "Agregado - ScreenGrid (GPU)",
        "Agregado - Grade (servidor)",
    ]
    try:
        default_index = options.index(default_mode)
    except ValueError:
        default_index = 1  # fallback

    # ==========================
    # 1) Estado persistente dos filtros de visualização
    # ==========================
    # Risco 0–1
    if "risk_range" not in st.session_state:
        st.session_state["risk_range"] = (0.0, 1.0)

    # Tempo (datetime range) — usa min/max do df filtrado atual
    # Garante tipo datetime64[ns]
    df_dt = df.copy()
    df_dt["data_hora"] = pd.to_datetime(df_dt["data_hora"], errors="coerce")
    min_dt = df_dt["data_hora"].min()
    max_dt = df_dt["data_hora"].max()
    
    # ⚠️ Converter para datetime.datetime (não usar pandas.Timestamp no slider!)
    min_dt_py = _to_py_dt(min_dt)
    max_dt_py = _to_py_dt(max_dt)

    if min_dt_py is None or max_dt_py is None:
        st.info("Sem intervalos de tempo válidos para exibir.")
        return

    # Estado inicial do time_range (sempre como datetime.datetime)
    if "time_range" not in st.session_state or st.session_state["time_range"] is None:
        # st.session_state["time_range"] = (min_dt, max_dt)
        st.session_state["time_range"] = (min_dt_py, max_dt_py)
    else:
        # Garante que a faixa salvas ainda esteja dentro dos dados atuais
        # lo_t, hi_t = st.session_state["time_range"]
        # if lo_t is None or hi_t is None or lo_t < min_dt or hi_t > max_dt:
        #     st.session_state["time_range"] = (min_dt, max_dt)
        st.session_state["time_range"] = _coerce_time_range_tuple(
            st.session_state["time_range"], min_dt_py, max_dt_py
        )
    
    t0, t1 = st.session_state["time_range"]

    # ==========================
    # 2) Layout: mapa à esquerda, controles à direita
    # ==========================
    left, right = st.columns([5, 1], gap="large")

    with right:
        S = get_settings()

        # Slider de risco 0–1 (duas alças)
        lo, hi = st.slider(
            "Risco de fogo (0–1)",
            min_value=0.0,
            max_value=1.0,
            value=st.session_state["risk_range"],
            step=0.01,
            help="Mostra apenas focos cujo RiscoFogo esteja dentro da faixa selecionada."
        )
        st.session_state["risk_range"] = (lo, hi)

        # Barra vertical amarelo→vermelho (referência visual)
        y = S.MAP_RISK_YELLOW
        r = S.MAP_RISK_RED
        grad_css = f"linear-gradient(to bottom, rgb({y[0]},{y[1]},{y[2]}), rgb({r[0]},{r[1]},{r[2]}))"
        st.markdown(
            f"""
            <div style="display:flex; flex-direction:column; align-items:center;">
              <div style="height:160px; width:20px; background:{grad_css};
                          border:1px solid #444; border-radius:4px; margin:6px 0;"></div>
              <div style="width:40px; display:flex; justify-content:space-between; font-size:12px; color:#ddd;">
                <span>0</span><span>1</span>
              </div>
              <div style="font-size:11px; color:#aaa; margin-top:4px;">Escala do risco</div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # Seletor de modo de mapa
        mode = st.radio("Modo", options, index=default_index)

    # ==========================
    # 3) Filtragem por risco e por tempo (aplicada antes do desenho)
    # ==========================
    dff = df_dt.copy()
    # risco seguro
    dff["RiscoFogo"] = pd.to_numeric(dff["RiscoFogo"], errors="coerce")
    dff = dff.dropna(subset=["RiscoFogo", "data_hora"])

    # aplica risco
    r0, r1 = st.session_state["risk_range"]
    dff = dff[(dff["RiscoFogo"] >= r0) & (dff["RiscoFogo"] <= r1)]

    # aplica tempo (usa faixa persistida no session_state)
    # t0, t1 = st.session_state["time_range"]
    # t0/t1 são datetime.datetime; data_hora é pandas.Timestamp → compare convertendo para datetime
    # (pandas trata datetime.datetime de boa; não precisa converter a série toda)
    dff = dff[(dff["data_hora"] >= t0) & (dff["data_hora"] <= t1)]

    # ==========================
    # 4) Desenho do mapa (UM único)
    # ==========================
    with left:
        if dff.empty:
            st.info("Nenhum ponto atende aos filtros de risco/tempo selecionados.")
        else:
            if mode.startswith("Pontos"):
                simple_map(dff)
            elif "Hexágonos" in mode:
                hex_map(dff)
            elif "ScreenGrid" in mode:
                screengrid_map(dff)
            else:
                cell = st.slider(
                    "Tamanho da célula (graus)", 0.05, 0.5, 0.1, 0.05,
                    help="Quanto maior a célula, mais forte a agregação (menos pontos no mapa)."
                )
                grid = aggregate_grid_cached(dff, cell_deg=cell)
                grid_map(grid)

    # ==========================
    # 5) Slider de tempo abaixo do mapa (sempre datetime.datetime!)
    # ==========================
    # Caso de borda: min == max → não há como abrir slider de faixa; mostre info e não quebre
        # st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)  # espaçador sutil
    try:
        if min_dt_py == max_dt_py:
            st.info(f"Todos os dados são do mesmo instante: {min_dt_py:%d/%m/%Y %H:%M}.")
        else:
            new_t0, new_t1 = st.slider(
                "Janela temporal",
                min_value=min_dt,
                max_value=max_dt,
                # value=st.session_state["time_range"],
                # value=_coerce_time_range_tuple(st.session_state["time_range"], min_dt_py, max_dt_py),
                value=(t0, t1),
                help="Selecione a janela de tempo dos dados exibidos no mapa.",
                format="DD/MM/YYYY HH:mm",
            )
            # Persiste de volta como datetime.datetime
            # st.session_state["time_range"] = (new_t0, new_t1)
            st.session_state["time_range"] = _coerce_time_range_tuple((new_t0, new_t1), min_dt_py, max_dt_py)
    except Exception as e:
        st.error(f"Erro ao carregar slider de tempo do mapa: {e}")

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
    st.subheader("Análise Estatística")
    cols_num = ["DiaSemChuva","Precipitacao","RiscoFogo","FRP"]
    
    # df_num = (df[cols_num]
    #           .apply(pd.to_numeric, errors="coerce")
    #           .dropna(how="any"))  # precisa estar completo para corr()
    df_num = df[cols_num].apply(pd.to_numeric, errors="coerce")
    
    # Fallback de cor caso variável não exista no settings/env
    # try:
    #     S = get_settings()
    #     dens_color = (getattr(S, "RISK_STATS_COLOR", None) or "violet")  # << fallback seguro
    # except Exception:
    #     dens_color = "violet"

    st.markdown("**Resumo estatístico**")
    st.dataframe(df_num.describe().T, **kw_for(st.dataframe))

    st.markdown("**Distribuições** (histograma + densidade)")
    target = st.selectbox("Escolha a variável:", cols_num, index=2)
    
    base = alt.Chart(df_num)
    
    # # no render_stats_tab:
    data = density_series(df_num[target], bins=60)
    
    # bins = st.slider("Bins do histograma", 10, 120, 60, 10)
    # data = _hist_server_side(df_num[target], bins=bins)

    # Gráfico de densidade com cor definida (NUNCA None)
    chart = (
        # base
        # .transform_density(target, as_=[target, 'density'])
        alt.Chart(data)
        # .mark_area(opacity=0.4, color=dens_color)
        .mark_area(opacity=0.5)
        .encode(
            x=alt.X(f"{target}:Q", title=target),
            # y="density:Q")
            y=alt.Y("count:Q", title="Contagem"),
            tooltip=["x:Q","count:Q"],
        )
    )
    hist = (
        base
        .mark_bar(opacity=0.5)
        .encode(x=alt.X(f"{target}:Q", bin=True), y="count()")
    )
    st.altair_chart(hist + chart, **kw_for(st.altair_chart))
    # st.altair_chart(chart, **kw_for(st.altair_chart))

    st.markdown("**Correlação**")
    chosen = st.multiselect("Selecione variáveis para correlação", cols_num, default=cols_num)
    
    if len(chosen) >= 2:
        # corr_input = (df[chosen]
        #               .apply(pd.to_numeric, errors="coerce")
        #               .dropna(how="any"))
        # if corr_input.empty:
        #     st.info("Sem dados suficientes (após limpar valores ausentes) para calcular correlação.")
        #     log.warning("correlation_skipped_empty_after_dropna", chosen=chosen)
        #     return

        # corr = corr_input.corr().reset_index().melt("index")
        corr = df_num[chosen].corr(numeric_only=True).reset_index().melt("index")
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

def render_time_tab_filtered(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp):
    """
    Séries temporais otimizadas:
      - pré-agregação por D/W/M (auto) com opção de override
      - seleção de poucos traços simultâneos (Top N por padrão)
    """
    st.subheader("Séries temporais (otimizadas)")

    # frequência sugerida pela janela — com override do usuário
    freq_sug = choose_time_freq(start, end)
    freq = st.radio(
        "Resolução temporal",
        ["Auto", "Diário (D)", "Semanal (W)", "Mensal (M)"],
        horizontal=True,
        index=0
    )
    if freq == "Auto":
        freq = freq_sug
    else:
        freq = {"Diário (D)": "D", "Semanal (W)": "W", "Mensal (M)": "M"}[freq]

    which = st.radio("Visualizar por:", ["Geral", "Estado", "Bioma"], horizontal=True, index=0)

    if which == "Geral":
        df_series = aggregate_time(df, freq=freq, dimension=None)
        chart = (
            alt.Chart(df_series)
            .mark_line()
            .encode(
                x=alt.X("data:T", title="Data"),
                y=alt.Y("contagem:Q", title="Focos"),
                tooltip=["data:T", "contagem:Q"],
            )
        )
        st.altair_chart(chart, **kw_for(st.altair_chart))
        return

    # Com dimensão: limitar a quantidade de traços
    if which == "Estado":
        dim = "estado_nome"
    else:
        dim = "Bioma"

    # Sugerir top K (ajustável) para não mandar 20+ linhas
    k = st.slider("Máx. de séries simultâneas", 1, 8, 5, 1)
    sugestoes = _top_k_labels(df, dim, k=k)
    selecionados = st.multiselect(
        f"Selecionar {dim} a exibir",
        options=sorted(df[dim].dropna().astype(str).unique().tolist()),
        default=sugestoes,
    )

    if not selecionados:
        st.info("Selecione pelo menos uma categoria.")
        return

    df_dim = df.loc[df[dim].astype(str).isin(selecionados)]
    df_series = aggregate_time(df_dim, freq=freq, dimension=dim)

    chart = (
        alt.Chart(df_series)
        .mark_line()
        .encode(
            x=alt.X("data:T", title="Data"),
            y=alt.Y("contagem:Q", title="Focos"),
            color=alt.Color(f"{dim}:N", title=dim),
            tooltip=["data:T", "contagem:Q", f"{dim}:N"],
        )
    )
    st.altair_chart(chart, **kw_for(st.altair_chart))