from __future__ import annotations
import streamlit as st
import pandas as pd

# --- carregar .env antes de tudo ---
from dotenv import load_dotenv
load_dotenv()
# -----------------------------------

from projeto_vigia.theming import setup_page, inject_css
from projeto_vigia.services.data_io import read_csv_from_gdrive
from projeto_vigia.domain.preprocessing import normalize_dataframe
from projeto_vigia.analytics.filters import (
    filter_by_date_range, filter_by_turno, filter_by_biomes, filter_numeric_columns
)
from projeto_vigia.analytics.aggregations import (
    by_day, by_biome, top_municipios_with_bioma, series_by_dimension, compute_critical_regions
)
from projeto_vigia.ui.sidebar import render_sidebar
from projeto_vigia.ui.sections import (
    render_summary_tab, render_time_tab, render_biome_city_tab,
    render_prevention_tab, render_stats_tab
)
from projeto_vigia.ui.compat import kw_for
from projeto_vigia.core.logging_config import configure_logging, get_logger
from projeto_vigia.core.settings import get_settings

S = get_settings()

@st.cache_data(ttl=S.CACHE_TTL_SECONDS, show_spinner="Baixando e processando dados CSV...")
def load_dataset(url: str) -> pd.DataFrame:
    # ...
    return normalize_dataframe(df)

# Logging
configure_logging()
log = get_logger(app="ProjetoVigia", module="app")
log.info("startup", page="main")

setup_page()
inject_css()

st.title("🔥 Painel de Análise de Queimadas no Brasil")
st.markdown("Este painel realiza uma análise interativa de focos de queimadas com base em um arquivo de dados da web.")

@st.cache_data(ttl=86400, show_spinner="Baixando e processando dados CSV...")
def load_dataset(url: str) -> pd.DataFrame:
    log.info("dataset_download_start", url=url)
    df = read_csv_from_gdrive(url)
    log.info("dataset_download_ok", rows=len(df))
    df2 = normalize_dataframe(df)
    log.info("dataset_normalized", rows=len(df2), cols=list(df2.columns))
    return df2

try:
    df_full = load_dataset(S.FILE_URL)
except Exception as e:
    df_full = pd.DataFrame()
    st.error(f"Falha ao carregar dados: {e}")

sidebar_state = render_sidebar(df_full, S.LOGO_URL)

if df_full.empty:
    st.warning("Os dados não puderam ser carregados. Verifique o link/permissões.")
elif sidebar_state and sidebar_state["buscar"]:
    # 1) Coleta de parâmetros da sidebar
    estado = sidebar_state["estado"]
    biomas = sidebar_state["biomas"]
    start_dt = sidebar_state["start"]
    end_dt = sidebar_state["end"]
    turno_preset = sidebar_state["turno_preset"]
    custom_time = sidebar_state["custom_time"]  # (t0, t1) ou None
    numeric_rules = sidebar_state["numeric_rules"]

    # 2) Pipeline de filtros em ordem
    # Estado
    dff = df_full if estado == "Todos" else df_full[df_full["estado_nome"] == estado].copy()
    # Período
    dff = filter_by_date_range(dff, start_dt, end_dt)
    # Bioma(s)
    dff = filter_by_biomes(dff, biomas)
    # Turno / horário (preset ou faixa customizada)
    dff = filter_by_turno(dff, preset=turno_preset, custom_range=custom_time)
    # Filtros numéricos (dias sem chuva, precipitação, risco, FRP)
    dff = filter_numeric_columns(dff, numeric_rules)
    
    log.info("filters_applied",
         estado=estado,
         biomas=len(biomas) if biomas else 0,
         start=str(start_dt.date()),
         end=str(end_dt.date()),
         turno=turno_preset,
         custom_time=bool(custom_time),
         rows=len(dff))

    # 3) Saída
    if dff.empty:
        st.warning("Nenhum foco de queimada foi encontrado para os filtros selecionados.")
        log.warning("no_results_after_filters")
    else:
        crit = compute_critical_regions(dff, top_n=5)  # << calcular aqui

        st.success(f"Análise concluída para **{estado}** entre **{start_dt:%d/%m/%Y}** e **{end_dt:%d/%m/%Y}**!")

        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "🗺️ Mapa e Métricas",
            "📈 Séries Temporais",
            "🌳 Bioma & Município",
            "📊 Estatística",
            "💡 Prevenção",
        ])

        with tab1:
            render_summary_tab(dff, estado, crit_df=crit)
        with tab2:
            render_time_tab(
                by_day(dff),
                series_by_dimension(dff, "estado_nome"),
                series_by_dimension(dff, "Bioma"),
            )
        with tab3:
            df_bioma = by_biome(dff)
            df_mun_bioma = top_municipios_with_bioma(dff)
            render_biome_city_tab(df_bioma, df_mun_bioma) # old render_biome_city_tab(by_biome(dff), top_municipios(dff))
        with tab4:
            render_stats_tab(dff)
        with tab5:
            render_prevention_tab()

        with st.expander("Ver dados brutos (todas as colunas)"):
            df_disp = dff.rename(columns={"lat":"Latitude","lon":"Longitude","data_hora":"Data/Hora",
                                          "municipio_nome":"Município","estado_nome":"Estado"})
            st.dataframe(df_disp, **kw_for(st.dataframe))
else:
    st.info("⬅️ Selecione os filtros na barra lateral e clique em **Analisar** para começar.")
