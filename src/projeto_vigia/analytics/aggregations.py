from __future__ import annotations
import pandas as pd

def by_day(df: pd.DataFrame) -> pd.DataFrame:
    dff = df.copy()
    dff["data"] = dff["data_hora"].dt.date
    return dff.groupby("data").size().reset_index(name="contagem")

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
    Top 10 municípios por número de focos, com o Bioma dominante para colorir barras.
    """
    dff = df.copy()
    # Contagem por município+bioma
    grp = dff.groupby(["municipio_nome","Bioma"]).size().reset_index(name="focos")
    # Bioma dominante por município
    dom = grp.sort_values(["municipio_nome","focos"], ascending=[True, False]) \
             .drop_duplicates(subset=["municipio_nome"])
    # Total por município
    tot = dff.groupby("municipio_nome").size().reset_index(name="Número de Focos")
    out = tot.merge(dom[["municipio_nome","Bioma"]], on="municipio_nome", how="left")
    out = out.rename(columns={"municipio_nome": "Município"}).nlargest(n, "Número de Focos")
    return out

def series_by_dimension(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """
    dimension ∈ {"estado_nome","Bioma"}
    Agrega focos por dia e dimensão.
    """
    dff = df.copy()
    dff["data"] = dff["data_hora"].dt.date
    out = dff.groupby(["data", dimension]).size().reset_index(name="contagem")
    return out

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
    dff = df.copy()
    grp = (dff.groupby(["estado_nome", "municipio_nome", "Bioma"])
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
    grp["risco_medio"] = grp["risco_medio"].fillna(0).astype("float64")
    grp["score"] = grp["focos"]*0.6 + grp["risco_medio"]*100*0.25 + grp["frp_medio"]*0.15
    return grp.sort_values(["score","focos","frp_medio"], ascending=False).head(top_n)