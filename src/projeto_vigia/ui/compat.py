# src/projeto_vigia/ui/compat.py
from __future__ import annotations
import os
import inspect
import streamlit as st
# from functools import lru_cache

"""
Compat layer para sizing em APIs Streamlit:
- Em versões antigas: usar `use_container_width=True`
- Em versões novas (quando suportado): usar `width='stretch'`

A detecção acontece UMA vez ao importar este módulo e fica guardada em
PV_ST_WIDTH_MODE, evitando reflexão repetida.
"""

_ENV_KEY = "PV_ST_WIDTH_MODE"  # valores: "width" | "use_container_width" | ""

def _detect_width_mode() -> str:
    """
    Tenta detectar se a API aceita `width`. Caso contrário, cai para
    `use_container_width`. Se nenhuma das duas existir, retorna "" (vazio).
    """
    try:
        params = inspect.signature(st.altair_chart).parameters
        if "width" in params:
            return "width"
        if "use_container_width" in params:
            return "use_container_width"
    except Exception:
        # fallback conservador
        pass
    return "use_container_width"  # preferência segura p/ versões atuais

# 1) Leitura do ambiente (permite forçar o modo)
_MODE = os.getenv(_ENV_KEY, "").strip()

# 2) Se não definido, detecta uma vez e salva no ambiente
if _MODE not in ("width", "use_container_width"):
    _MODE = _detect_width_mode()
    os.environ[_ENV_KEY] = _MODE  # cache no processo

def _supports(func, param_name: str) -> bool:
    try:
        # return param_name in inspect.signature(func).parameters
        return _MODE
    except Exception:
        return False

# @lru_cache(maxsize=16)
def kw_for(func):
    """
    Decide *por função* quais kwargs usar:
    - se a função aceitar `width`, usa width='stretch'
    - senão, se aceitar `use_container_width`, usa use_container_width=True
    - senão, {}
    A decisão fica cacheada por função.
    """
    # if _supports(func, "width"):
    if _MODE == "width":
        return {"width": "stretch"}
    # if _supports(func, "use_container_width"):
    if _MODE == "use_container_width":
        return {"use_container_width": True}
    return {}