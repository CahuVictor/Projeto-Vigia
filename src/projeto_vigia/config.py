from __future__ import annotations

ESSENTIAL_COLS = [
    "DataHora", "Latitude", "Longitude", "Estado", "Municipio", "Bioma", "DiaSemChuva", "RiscoFogo"
]

RENAME_MAP = {
    "DataHora": "data_hora",
    "Latitude": "lat",
    "Longitude": "lon",
    "Estado": "estado_nome",
    "Municipio": "municipio_nome",
}
