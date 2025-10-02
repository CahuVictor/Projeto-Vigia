from __future__ import annotations
import pandas as pd
from projeto_vigia.config import ESSENTIAL_COLS, RENAME_MAP

def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza o CSV em um DataFrame com:
      - colunas essenciais garantidas
      - nomes padronizados (ex.: 'DataHora' -> 'data_hora', 'Estado' -> 'estado_nome', etc.)
      - tipos corretos (datetime e numéricos)
      - tratamento de sentinelas (-999) como ausentes (NA) nas colunas climáticas
      - remoção de linhas sem lat/lon/data_hora (e, hoje, sem RiscoFogo)

    Observação:
      - Manter 'RiscoFogo' com NA pode ser útil (para não descartar linhas),
        mas o seu pipeline hoje descarta onde 'RiscoFogo' é NA. Se quiser
        permitir pontos sem risco (p/ mapa “cinza”), pode tirar 'RiscoFogo'
        do dropna e tratar adiante na coloração/cálculo.
    """
    # 1) Validação de esquema mínimo
    if not all(c in df.columns for c in ESSENTIAL_COLS):
        missing = [c for c in ESSENTIAL_COLS if c not in df.columns]
        raise ValueError(f"CSV sem colunas essenciais: {', '.join(missing)}")

    # 2) Cópia local para não tocar no original
    df = df.copy()

    # 3) Renomeia para o padrão interno
    df.rename(columns=RENAME_MAP, inplace=True)
    
    # 4) Tipagem adequada + tratamento de sentinelas
    df["data_hora"]     = pd.to_datetime(df["data_hora"], errors="coerce")
    df["DiaSemChuva"]   = pd.to_numeric(df["DiaSemChuva"], errors="coerce").replace(-999, pd.NA)
    df["Precipitacao"]  = pd.to_numeric(df.get("Precipitacao", pd.NA), errors="coerce")
    df["RiscoFogo"]     = pd.to_numeric(df["RiscoFogo"], errors="coerce").replace(-999, pd.NA)
    df["FRP"]           = pd.to_numeric(df["FRP"], errors="coerce")
    
    # Dimensões → category (filtros muito mais rápidos e menos memória)
    for col in ("Satelite", "Pais", "estado_nome", "municipio_nome", "Bioma"):
        if col in df.columns:
            df[col] = df[col].astype("category")
    
    # 5) Remoção de registros inviáveis (sem localização/tempo/risco)
    # df.dropna(subset=["lat", "lon", "data_hora", "RiscoFogo"], inplace=True)
    df.dropna(subset=["lat", "lon", "data_hora"], inplace=True)
    # Se quiser manter pontos sem RiscoFogo, remova-o do dropna acima e trate nas médias/cores.
    # df["RiscoFogo"] pode ficar NA e ser ignorado em agregações.
    
    return df
