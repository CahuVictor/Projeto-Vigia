from __future__ import annotations
from functools import lru_cache
from typing import Tuple, Literal, Any
import json
from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

def _parse_tuple_of_floats(v: Any, expected_len: int | None = None) -> Tuple[float, ...]:
    if isinstance(v, (list, tuple)):
        out = tuple(float(x) for x in v)
    elif isinstance(v, str):
        s = v.strip()
        # tenta JSON primeiro
        try:
            parsed = json.loads(s)
            if isinstance(parsed, (list, tuple)):
                out = tuple(float(x) for x in parsed)
            else:
                raise ValueError
        except Exception:
            # fallback: remove parênteses e divide por vírgula
            s = s.strip("()[]")
            out = tuple(float(x.strip()) for x in s.split(",") if x.strip() != "")
    else:
        raise ValueError("unsupported type for float tuple")
    if expected_len is not None and len(out) != expected_len:
        raise ValueError(f"expected {expected_len} items, got {len(out)}")
    return out

def _parse_tuple_of_ints(v: Any, expected_len: int | None = None) -> Tuple[int, ...]:
    if isinstance(v, (list, tuple)):
        out = tuple(int(x) for x in v)
    elif isinstance(v, str):
        s = v.strip()
        try:
            parsed = json.loads(s)
            if isinstance(parsed, (list, tuple)):
                out = tuple(int(x) for x in parsed)
            else:
                raise ValueError
        except Exception:
            s = s.strip("()[]")
            out = tuple(int(x.strip()) for x in s.split(",") if x.strip() != "")
    else:
        raise ValueError("unsupported type for int tuple")
    if expected_len is not None and len(out) != expected_len:
        raise ValueError(f"expected {expected_len} items, got {len(out)}")
    return out

class Settings(BaseSettings):
    # Configurações do Pydantic Settings (v2)
    model_config = SettingsConfigDict(
        env_prefix="PV_",       # prefixo padrão para envs
        case_sensitive=False,   # envs não sensíveis a maiúsc/minúsc
        extra="ignore",         # ignorar variáveis extras
    )
    
    # =========================
    # Dados / Cache / Fontes
    # =========================
    FILE_URL: str                                    = Field(..., description="URL do CSV (Google Drive/HTTP)")
    LOGO_URL: str                                    = Field(..., description="URL do logotipo")
    CACHE_TTL_SECONDS: int                           = Field(86400, env="PV_CACHE_TTL")

    # =========================
    # UI / Tema
    # =========================
    PRIMARY_COLOR: str                               = Field("#ff6347", env="PV_PRIMARY_COLOR")   # tomate
    THEME_BG_DARK: str                               = Field("#1a1a1a", env="PV_THEME_BG_DARK")
    THEME_SIDEBAR_DARK: str                          = Field("#262730", env="PV_THEME_SIDEBAR_DARK")
    RISK_COLOR_FOR_STATS: str                        = Field("#8A2BE2", env="PV_RISK_STATS_COLOR")  # violeta

    # =========================
    # Mapa / Visual
    # =========================
    MAP_RADIUS_MIN_M: int                            = Field(300, env="PV_MAP_RADIUS_MIN")      # raio min (m)
    MAP_RADIUS_MAX_M: int                            = Field(2000, env="PV_MAP_RADIUS_MAX")     # raio max (m)
    MAP_RISK_YELLOW: Tuple[int,int,int]              = Field((255, 215, 0), env="PV_MAP_RISK_YELLOW")  # 0
    MAP_RISK_RED: Tuple[int,int,int]                 = Field((220, 20, 60), env="PV_MAP_RISK_RED")        # 1

    # =========================
    # Analytics
    # =========================
    CRITICAL_REGIONS_TOP_N: int                      = Field(5, env="PV_CRITICAL_TOP_N")
    CRITICAL_SCORE_WEIGHTS: Tuple[float,float,float] = Field((0.6, 0.25, 0.15), env="PV_CRITICAL_WTS")
    # ordem: (peso_focos, peso_risco, peso_frp_medio)

    # =========================
    # Turnos (em horas, [ini, fim))
    # =========================
    SHIFT_MADRUGADA: Tuple[float,float]              = Field((0.0, 6.0), env="PV_SHIFT_MADRUGADA")
    SHIFT_MANHA: Tuple[float,float]                  = Field((6.0, 12.0), env="PV_SHIFT_MANHA")
    SHIFT_TARDE: Tuple[float,float]                  = Field((12.0, 18.0), env="PV_SHIFT_TARDE")
    SHIFT_NOITE: Tuple[float,float]                  = Field((18.0, 24.0), env="PV_SHIFT_NOITE")

    # =========================
    # Logging
    # =========================
    LOG_LEVEL: Literal["DEBUG","INFO","WARNING","ERROR","CRITICAL"] = Field("INFO", env="LOG_LEVEL")
    LOG_FORMAT: Literal["json","plain"] = Field("json", env="LOG_FORMAT")
    LOG_FILE: str | None = Field(None, env="LOG_FILE")
    
    # --- Validadores tolerantes ---
    @field_validator("CRITICAL_SCORE_WEIGHTS", mode="before")
    def _coerce_weights(cls, v):
        return _parse_tuple_of_floats(v, expected_len=3)

    @field_validator("MAP_RISK_YELLOW", mode="before")
    def _coerce_risk_yellow(cls, v):
        return _parse_tuple_of_ints(v, expected_len=3)

    @field_validator("MAP_RISK_RED", mode="before")
    def _coerce_risk_red(cls, v):
        return _parse_tuple_of_ints(v, expected_len=3)

    @field_validator("SHIFT_MADRUGADA", "SHIFT_MANHA", "SHIFT_TARDE", "SHIFT_NOITE", mode="before")
    def _coerce_shifts(cls, v):
        return _parse_tuple_of_floats(v, expected_len=2)

@lru_cache
def get_settings() -> Settings:
    return Settings()  # lido 1x, reusado globalmente
