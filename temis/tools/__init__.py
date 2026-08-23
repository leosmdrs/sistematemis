"""
Registro de ferramentas do Sistema Têmis.

Acrescentar uma ferramenta ao hub é: criar o módulo com uma subclasse de
ToolPage, importá-la aqui e acrescentá-la ao REGISTRY. O casco
(`shell.py`) monta o portal a partir desta lista — não há nada a alterar
lá. Uma entrada com `None` no lugar da classe vira a tela de "em
desenvolvimento".
"""

from .base import ToolMeta, ToolPage, PlaceholderPage
from .antiinj import AntiInjectionTool
from .hash import HashTool
from .ips import IPSTool
from .metadados import MetadadosTool
from .quadro import QuadroTool
from .tarja_preta import TarjaPretaTool
from .video import VideoTool


# ─────────────────────────────────────────
#  REGISTRO
# ─────────────────────────────────────────

#: (meta, classe da ferramenta ou None se ainda não implementada)
REGISTRY: list[tuple[ToolMeta, type | None]] = [
    (TarjaPretaTool.meta,    TarjaPretaTool),
    (AntiInjectionTool.meta, AntiInjectionTool),
    (HashTool.meta,          HashTool),
    (QuadroTool.meta,        QuadroTool),
    (VideoTool.meta,         VideoTool),
    (IPSTool.meta,           IPSTool),
    (MetadadosTool.meta,     MetadadosTool),
]


def build_tool(meta: ToolMeta, cls: type | None) -> ToolPage:
    """Instancia a ferramenta, ou a tela de 'em desenvolvimento'."""
    return cls() if cls is not None else PlaceholderPage(meta)


__all__ = ["REGISTRY", "build_tool", "ToolMeta", "ToolPage", "PlaceholderPage"]
