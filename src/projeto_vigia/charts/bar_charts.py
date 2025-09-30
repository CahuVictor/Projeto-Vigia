import altair as alt
import pandas as pd
from ..core.settings import get_settings

def bioma_chart(df_bioma: pd.DataFrame) -> alt.Chart:
    return (alt.Chart(df_bioma)
            .mark_bar()
            .encode(
                x=alt.X("Número de Focos:Q"),
                y=alt.Y("Bioma:N", sort="-x"),
                tooltip=["Bioma", "Número de Focos"],
                color=alt.Color("Bioma:N", title="Bioma")  # legenda visível
            )
            .properties(title="Focos de Queimada por Bioma"))

# def municipio_chart(df_mun: pd.DataFrame) -> alt.Chart:
#     S = get_settings()
#     return (alt.Chart(df_mun)
#             .mark_bar(color=S.PRIMARY_COLOR)
#             .encode(x=alt.X("Número de Focos:Q"),
#                     y=alt.Y("Município:N", sort="-x"),
#                     tooltip=["Município", "Número de Focos"])
#             .properties(title="Top 10 Municípios com Mais Focos"))

def municipio_chart_by_bioma(df_mun: pd.DataFrame) -> alt.Chart:
    """
    Espera colunas: Município, Número de Focos, Bioma
    """
    return (alt.Chart(df_mun)
            .mark_bar()
            .encode(
                x=alt.X("Número de Focos:Q"),
                y=alt.Y("Município:N", sort="-x"),
                color=alt.Color("Bioma:N", title="Bioma"),  # legenda por bioma
                tooltip=["Município","Bioma","Número de Focos"]
            )
            .properties(title="Top 10 Municípios (cor por Bioma dominante)"))
