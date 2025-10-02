# src/projeto_vigia/analytics/aggregations.py
from __future__ import annotations
import pandas as pd
import streamlit as st

from ..core.settings import get_settings

def _hash_df(x: pd.DataFrame) -> bytes:
    # hash por conteúdo (custo moderado; ótimo ganho em repetição)
    return pd.util.hash_pandas_object(x, index=True).values.tobytes()

def by_day(df: pd.DataFrame) -> pd.DataFrame:
    """
    Conta focos por dia sem criar coluna auxiliar 'data'.
    """
    # dff = df.copy()
    # dff["data"] = dff["data_hora"].dt.date
    # return dff.groupby("data").size().reset_index(name="contagem")
    # Se você quiser dias de calendário (UTC do dado):
    s = df["data_hora"].dt.date
    return s.value_counts(sort=False).rename_axis("data").reset_index(name="contagem")

def by_biome(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df["Bioma"]
        .value_counts()
        .rename_axis("Bioma")
        .reset_index(name="Número de Focos")
    )

# def top_municipios(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
#     return (
#         df["municipio_nome"]
#         .value_counts()
#         .nlargest(n)
#         .rename_axis("Município")
#         .reset_index(name="Número de Focos")
#     )

def top_municipios_with_bioma(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """
    Top N municípios por nº de focos, com bioma dominante (para cor).
    Não cria cópias desnecessárias.
    """
    # dff = df.copy()
    # Contagem por município+bioma
    grp = (
        # dff.groupby(["municipio_nome","Bioma"])
        df.groupby(["municipio_nome", "Bioma"])
        .size()
        .reset_index(name="focos")
    )
    # Bioma dominante por município
    # dom = grp.sort_values(["municipio_nome","focos"], ascending=[True, False]) \
    #          .drop_duplicates(subset=["municipio_nome"])
    dom = (grp.sort_values(["municipio_nome", "focos"], ascending=[True, False])
              .drop_duplicates(subset=["municipio_nome"]))
    # Total por município
    tot = df.groupby("municipio_nome").size().reset_index(name="Número de Focos") # dff
    # out = tot.merge(dom[["municipio_nome","Bioma"]], on="municipio_nome", how="left")
    # out = out.rename(columns={"municipio_nome": "Município"}).nlargest(n, "Número de Focos")
    out = (tot.merge(dom[["municipio_nome", "Bioma"]], on="municipio_nome", how="left")
              .rename(columns={"municipio_nome": "Município"})
              .nlargest(n, "Número de Focos"))
    return out

def series_by_dimension(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """
    Agrega focos por 'dimension' (ex.: estado_nome/Bioma) e dia,
    sem criar cópia nem coluna auxiliar.
    """
    # dff = df.copy()
    # dff["data"] = dff["data_hora"].dt.date
    # out = dff.groupby(["data", dimension]).size().reset_index(name="contagem")
    # return out
    g = df.groupby([df["data_hora"].dt.date, dimension]).size().reset_index(name="contagem")
    g.rename(columns={"data_hora": "data"}, inplace=True)  # (apenas por clareza)
    g.rename(columns={g.columns[0]: "data"}, inplace=True) # garante nome 'data'
    return g

def compute_critical_regions(df: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """
    Agrega por Município + Estado + Bioma:
    - focos (contagem)
    - risco_medio (ignorando NAs)
    - frp_medio, frp_max, frp_sum
    - precip_media, dias_sem_chuva_med
    - lat/lon médios (para referência)
    - score simples para rank
    """
    S = get_settings()
    w_focos, w_risco, w_frp = S.CRITICAL_SCORE_WEIGHTS
    
    # dff = df.copy()
    # grp = (dff.groupby(["estado_nome", "municipio_nome", "Bioma"])
    grp = (df.groupby(["estado_nome", "municipio_nome", "Bioma"])
             .agg(
                 focos=("FRP","size"),
                 risco_medio=("RiscoFogo","mean"),    # ignora NAs automaticamente
                 frp_medio=("FRP","mean"),
                 frp_max=("FRP","max"),
                 frp_sum=("FRP","sum"),
                 precip_media=("Precipitacao","mean"),
                 dias_sem_chuva_med=("DiaSemChuva","mean"),
                 lat=("lat","mean"),
                 lon=("lon","mean"),
             )
             .reset_index())
    # Score: quantidade + risco médio (se NA vira 0) + FRP médio
    grp["risco_medio"] = (
        pd.to_numeric(grp["risco_medio"], errors="coerce")
        .fillna(0.0)
        .astype("float64")
    )
    grp["score"] = grp["focos"]*w_focos + grp["risco_medio"]*100*w_risco + grp["frp_medio"]*w_frp
    return grp.sort_values(["score","focos","frp_medio"], ascending=False).head(top_n or S.CRITICAL_REGIONS_TOP_N)

def aggregate_grid(df: pd.DataFrame, cell_deg: float = 0.1) -> pd.DataFrame:
    """
    Agrupa pontos de latitude/longitude em uma grade (grid) de ~`cell_deg` graus.

    Isso reduz o número de pontos no mapa, já que em vez de mostrar cada ponto
    individual (potencialmente milhões, com sobreposição), mostra apenas
    o "centroide" da célula e métricas agregadas (FRP médio, risco médio, etc.).

    Exemplo:
      - cell_deg = 0.1 → cada célula é um quadrado de 0.1º x 0.1º (~11 km)
      - Todos os pontos dentro desse quadrado são agrupados em 1 ponto (o centroide).
    """

    # Pega apenas as colunas relevantes para os cálculos
    dff = df[["lat", "lon", "RiscoFogo", "FRP", "Precipitacao", "DiaSemChuva"]].copy()

    # Cria "bins" (células de grade):
    # Dividi latitude e longitude pelo tamanho da célula (ex: 0.1),
    # arredonda e transforma em inteiro para identificar a célula.
    dff["lat_bin"] = (dff["lat"] / cell_deg).round().astype(int)
    dff["lon_bin"] = (dff["lon"] / cell_deg).round().astype(int)

    # Agora agrupa por cada célula (lat_bin, lon_bin).
    # Para cada célula, calcula várias estatísticas:
    g = (
        dff.groupby(["lat_bin", "lon_bin"], as_index=False)
        .agg(
            # Centroide: média das coordenadas originais
            lat=("lat", "mean"),
            lon=("lon", "mean"),

            # Quantidade de focos (contagem de registros naquela célula)
            focos=("FRP", "size"),

            # Soma, média e máximo do FRP dentro da célula
            frp_sum=("FRP", "sum"),
            frp_medio=("FRP", "mean"),

            # Risco médio de fogo (ignora NAs automaticamente)
            risco_medio=("RiscoFogo", "mean"),

            # Médias climáticas na célula
            precip_media=("Precipitacao", "mean"),
            dias_sem_chuva_med=("DiaSemChuva", "mean"),
        )
    )

    # Garanti que risco_medio sempre seja numérico,
    # substituindo valores inválidos/ausentes por 0
    g["risco_medio"] = (
        pd.to_numeric(g["risco_medio"], errors="coerce")
        .fillna(0.0)
        .astype("float64")
    )

    return g

@st.cache_data(hash_funcs={pd.DataFrame: _hash_df})
def aggregate_grid_cached(df: pd.DataFrame, cell_deg: float = 0.1) -> pd.DataFrame:
    return aggregate_grid(df, cell_deg=cell_deg)

def choose_time_freq(start: pd.Timestamp, end: pd.Timestamp) -> str:
    """
    Retorna a frequência temporal sugerida com base no comprimento da janela:
    - <= 35 dias: 'D' (diário)
    - 36–120 dias: 'W' (semanal)
    - > 120 dias: 'M' (mensal)
    """
    days = int((end.normalize() - start.normalize()).days) + 1
    if days <= 35:
        return "D"
    if days <= 120:
        return "W"
    return "M"

def aggregate_time(df: pd.DataFrame, freq: str = "D", dimension: str | None = None) -> pd.DataFrame:
    """
    Agrega contagem de focos por 'freq' (D/W/M).
    - Se 'dimension' for None: série única (geral).
    - Se 'dimension' for 'estado_nome' ou 'Bioma': agrega por tempo + dimensão.
    """
    # garante datetime index temporário sem copiar demais
    s = df.set_index("data_hora")
    if dimension is None:
        out = (
            s
            .groupby(pd.Grouper(freq=freq))
            .size()
            .rename("contagem")
            .reset_index()
            .rename(columns={"data_hora": "data"})
        )
    else:
        out = (
            s
            .groupby([pd.Grouper(freq=freq), dimension])
            .size()
            .rename("contagem")
            .reset_index()
            .rename(columns={"data_hora": "data"})
        )
    # remove pontos vazios/NaT (podem aparecer em 'M'/'W' se não houver dados em certos bins)
    return out.dropna(subset=["data"])