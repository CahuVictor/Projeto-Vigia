from __future__ import annotations
import pandas as pd
from typing import Iterable, Optional, Tuple

from ..core.settings import get_settings

# ---------------------------
# Datas e turno
# ---------------------------
def filter_by_date_range(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """
    Filtra por intervalo [start, end] *inclusivo no dia*.

    Observação: não usa .copy(), pois não alteramos o DF retornado.
    """
    # end é inclusivo no dia; soma 1 dia e corta < end+1
    # mask = (df["data_hora"] >= start) & (df["data_hora"] < (end + pd.Timedelta(days=1)))
    end_exclusive = end + pd.Timedelta(days=1)
    mask = (df["data_hora"] >= start) & (df["data_hora"] < end_exclusive)
    return df.loc[mask] # df.loc[mask].copy()

def filter_by_turno(
    df: pd.DataFrame,
    preset: Optional[str] = None,
    custom_range: Optional[Tuple[pd.Timestamp, pd.Timestamp]] = None,
) -> pd.DataFrame:
    """
    Filtra por turno com base em 'data_hora'. Não cria coluna temporária.

    - preset ∈ {"Madrugada","Manhã","Tarde","Noite"} ou None
    - custom_range: (t0, t1) só usa HH:MM de cada Timestamp
    """
    if not (preset or custom_range):
        return df
    
    # dff = df.copy()
    # dff["hora"] = dff["data_hora"].dt.hour + dff["data_hora"].dt.minute/60.0
    
    hours = df["data_hora"].dt.hour + df["data_hora"].dt.minute / 60.0

    if preset:
        S = get_settings()
        
        RANGES = {
            "Madrugada": S.SHIFT_MADRUGADA,
            "Manhã": S.SHIFT_MANHA,
            "Tarde": S.SHIFT_TARDE,
            "Noite": S.SHIFT_NOITE,
        }
        
        h0, h1 = RANGES[preset]
        # mask = (dff["hora"] >= h0) & (dff["hora"] < h1)
        # return dff.loc[mask].drop(columns=["hora"])
        mask = (hours >= h0) & (hours < h1)
        return df.loc[mask]
    
    # faixa customizada
    # if custom_range:
    t0, t1 = custom_range
    h0 = t0.hour + t0.minute/60.0
    h1 = t1.hour + t1.minute/60.0
    if h0 <= h1:
        # mask = (dff["hora"] >= h0) & (dff["hora"] < h1)
        mask = (hours >= h0) & (hours < h1)
    else:
        # faixa cruzando meia-noite (ex.: 22:00–03:00)
        # mask = (dff["hora"] >= h0) | (dff["hora"] < h1)
        mask = (hours >= h0) | (hours < h1)
    # return dff.loc[mask].drop(columns=["hora"])

    # return dff.drop(columns=["hora"])
    return df.loc[mask]

# ---------------------------
# Bioma
# ---------------------------
def filter_by_biomes(df: pd.DataFrame, biomas: Optional[Iterable[str]]) -> pd.DataFrame:
    """
    Filtra por lista de biomas. Se vazio/None, retorna o DF original.
    """
    if not biomas:
        return df
    return df.loc[df["Bioma"].isin(biomas)] # df[df["Bioma"].isin(list(biomas))].copy()

# ---------------------------
# Filtros numéricos genéricos
# ---------------------------
def apply_numeric_filter(series: pd.Series, operator: str,
                         a: Optional[float] = None,
                         b: Optional[float] = None) -> pd.Series:
    """
    operator ∈ {"(sem filtro)","=","<",">","<=" ,">=","entre"}
    a = valor (ou limite inferior se "entre")
    b = limite superior se "entre"
    Retorna uma máscara booleana.
    """
    if operator == "(sem filtro)" or operator is None:
        return pd.Series(True, index=series.index)
    if operator == "=" and a is not None:
        return series == a
    if operator == "<" and a is not None:
        return series < a
    if operator == ">" and a is not None:
        return series > a
    if operator == "<=" and a is not None:
        return series <= a
    if operator == ">=" and a is not None:
        return series >= a
    if operator == "entre" and a is not None and b is not None:
        lo, hi = min(a, b), max(a, b)
        return (series >= lo) & (series <= hi)
    return pd.Series(True, index=series.index)

def filter_numeric_columns(df: pd.DataFrame,
                           rules: dict) -> pd.DataFrame:
    """
    Aplica um conjunto de regras numéricas por coluna. Não cria cópia.
    
    rules = {
      "DiaSemChuva": {"op": "entre", "a": 0, "b": 16},
      "Precipitacao": {"op": "=", "a": 0.0},
      "RiscoFogo": {"op": ">=", "a": 0.8},
      "FRP": {"op": ">", "a": 60}
    }
    """
    mask = pd.Series(True, index=df.index)
    for col, cfg in rules.items():
        op = cfg.get("op")
        a = cfg.get("a")
        b = cfg.get("b")
        mask &= apply_numeric_filter(df[col], op, a, b)
    return df.loc[mask] # df.loc[mask].copy()
