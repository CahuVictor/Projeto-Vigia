# src/projeto_vigia/services/assets.py
from __future__ import annotations
import io
import requests
from PIL import Image
import streamlit as st

@st.cache_resource(show_spinner=False)
def get_logo_image(url: str) -> Image.Image:
    """
    Baixa o logotipo uma única vez por processo da app (ou até o URL mudar).
    Retorna um objeto PIL.Image pronto para uso.
    """
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
    return img
