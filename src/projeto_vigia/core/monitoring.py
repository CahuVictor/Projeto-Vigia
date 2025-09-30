# src/projeto_vigia/core/monitoring.py
from __future__ import annotations
import os, psutil
from .logging_config import get_logger

log = get_logger(app="ProjetoVigia", module="monitoring")

def log_memory(tag: str, df=None):
    """Loga RSS do processo e, opcionalmente, memória estimada de um DataFrame."""
    rss = psutil.Process(os.getpid()).memory_info().rss
    payload = {"what": "mem_usage", "tag": tag, "rss_mb": round(rss/1024/1024, 1)}
    try:
        if df is not None:
            import pandas as pd
            if isinstance(df, pd.DataFrame):
                payload["df_rows"] = len(df)
                payload["df_mb"] = round(df.memory_usage(deep=True).sum()/1024/1024, 1)
    except Exception:
        pass
    log.info("mem_usage", **payload)
