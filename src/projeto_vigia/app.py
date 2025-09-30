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
    by_day, by_biome, top_municipios_with_bioma, 
    series_by_dimension, compute_critical_regions, 
    aggregate_grid, aggregate_grid_cached
)
from projeto_vigia.ui.sidebar import render_sidebar
from projeto_vigia.ui.sections import (
    render_summary_tab, render_time_tab, render_biome_city_tab,
    render_prevention_tab, render_stats_tab
)
from projeto_vigia.charts.maps import hex_map, screengrid_map, grid_map
from projeto_vigia.ui.compat import kw_for
from projeto_vigia.core.logging_config import configure_logging, get_logger
from projeto_vigia.core.settings import get_settings
from projeto_vigia.core.monitoring import log_memory

S = get_settings()

def _normalize_filters(sidebar_state: dict) -> dict:
    """
    Converte o estado dos filtros em tipos hasháveis/estáveis para comparação.
    Assim sabemos se os filtros mudaram entre um rerun e outro.
    """
    if not sidebar_state:
        return {}
    return {
        "estado": sidebar_state["estado"],
        "biomas": tuple(sorted(sidebar_state["biomas"] or [])),
        "start": str(sidebar_state["start"]),
        "end": str(sidebar_state["end"]),
        "turno_preset": sidebar_state["turno_preset"],
        # custom_time pode ser None ou (t0, t1); guardamos só HH:MM
        "custom_time": None if not sidebar_state["custom_time"] else (
            sidebar_state["custom_time"][0].strftime("%H:%M"),
            sidebar_state["custom_time"][1].strftime("%H:%M"),
        ),
        # regras numéricas: transforme em tuplas estáveis
        "numeric_rules": tuple(sorted([
            (k, v.get("op"), tuple(v.get("value")) if isinstance(v.get("value"), list) else v.get("value"))
            for k, v in (sidebar_state["numeric_rules"] or {}).items()
        ])),
    }

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
    log_memory("after_load", df_full)
except Exception as e:
    df_full = pd.DataFrame()
    st.error(f"Falha ao carregar dados: {e}")

sidebar_state = render_sidebar(df_full, S.LOGO_URL)

filters_now = _normalize_filters(sidebar_state) if sidebar_state else {}

# Isso mantém entre reruns
ss = st.session_state

# Condição para (re)analisar:
should_analyze = (
    df_full is not None
    and not df_full.empty
    and sidebar_state is not None
    and (
        sidebar_state["buscar"]                     # clicou no botão "Analisar"
        or ("last_filters" not in ss)               # primeira vez
        or (filters_now != ss.get("last_filters"))  # filtros mudaram
    )
)

if should_analyze:
    # ======= RECOMPÕE O PIPELINE =======
    estado = sidebar_state["estado"]
    biomas = sidebar_state["biomas"]
    start_dt = sidebar_state["start"]
    end_dt = sidebar_state["end"]
    turno_preset = sidebar_state["turno_preset"]
    custom_time = sidebar_state["custom_time"]
    numeric_rules = sidebar_state["numeric_rules"]

    # Estado
    dff = df_full if estado == "Todos" else df_full[df_full["estado_nome"] == estado].copy()
    # Período
    dff = filter_by_date_range(dff, start_dt, end_dt)
    # Bioma(s)
    dff = filter_by_biomes(dff, biomas)
    # Turno
    dff = filter_by_turno(dff, preset=turno_preset, custom_range=custom_time)
    # Numéricos
    dff = filter_numeric_columns(dff, numeric_rules)

    # Regiões críticas calculadas uma vez
    crit = compute_critical_regions(dff, top_n=5)

    # ======= PERSISTE NO SESSION_STATE =======
    ss["analysis_ready"] = True
    ss["last_filters"] = filters_now
    ss["dff"] = dff
    ss["crit"] = crit
    ss["estado"] = estado
    ss["periodo"] = (start_dt, end_dt)

    log.info("filters_applied",
        estado=estado,
        biomas=len(biomas) if biomas else 0,
        start=str(start_dt.date()),
        end=str(end_dt.date()),
        turno=turno_preset,
        custom_time=bool(custom_time),
        rows=len(dff))
    log_memory("after_filters", dff)

# ================= RENDER ==================

if df_full.empty:
    st.warning("Os dados não puderam ser carregados. Verifique o link/permissões.")
elif ss.get("analysis_ready") and "dff" in ss:
    # Sempre reusa o último resultado analisado enquanto os filtros não mudarem:
    dff = ss["dff"]
    crit = ss.get("crit")
    estado = ss.get("estado", "Todos")
    start_dt, end_dt = ss.get("periodo", (None, None))

    st.success(
        f"Análise concluída para **{estado}**"
        + (f" entre **{start_dt:%d/%m/%Y}** e **{end_dt:%d/%m/%Y}**!" if start_dt and end_dt else "!")
    )

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🗺️ Mapa e Métricas",
        "📈 Séries Temporais",
        "🌳 Bioma & Município",
        "📊 Estatística",
        "💡 Prevenção",
    ])

    with tab1:
        # orquestra tudo (resumo + mapa + regiões críticas)
        render_summary_tab(dff, estado, crit_df=crit)
        
        log_memory("after_summary_tab")
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
