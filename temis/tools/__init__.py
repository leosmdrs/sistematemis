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
from .atividades import AtividadesTool
from .constatacao import ConstatacaoTool
from .ips import IPSTool
from .metadados import MetadadosTool
from .espelhamento import EspelhamentoTool
from .extracao import ExtracaoTool
from .gravacao import GravacaoTool
from .ocrpdf import OCRPDFTool
from .quadro import QuadroTool
from .tarja_preta import TarjaPretaTool
from .transcricao import TranscricaoTool
from .varredura import VarreduraTool
from .video import VideoTool


# ─────────────────────────────────────────
#  REGISTRO
# ─────────────────────────────────────────

#: (meta, classe da ferramenta ou None se ainda não implementada)
#:
#: A ordem é a da pirâmide do portal, lida de cima para baixo. No
#: vértice, a peça que instrui o procedimento; na fileira seguinte, o
#: que identifica e captura a prova onde ela está; depois, o que extrai
#: conteúdo do material apreendido; na base, o preparo e o apoio.
REGISTRY: list[tuple[ToolMeta, type | None]] = [
    # vértice — o procedimento
    (IPSTool.meta,           IPSTool),
    # identificação e captura da prova
    (MetadadosTool.meta,     MetadadosTool),
    (ConstatacaoTool.meta,   ConstatacaoTool),
    # extração de conteúdo do material apreendido
    (VarreduraTool.meta,     VarreduraTool),
    (OCRPDFTool.meta,        OCRPDFTool),
    (TranscricaoTool.meta,   TranscricaoTool),
    (ExtracaoTool.meta,      ExtracaoTool),
    (GravacaoTool.meta,      GravacaoTool),
    (EspelhamentoTool.meta,  EspelhamentoTool),
    # preparo e apoio
    (TarjaPretaTool.meta,    TarjaPretaTool),
    (AntiInjectionTool.meta, AntiInjectionTool),
    (QuadroTool.meta,        QuadroTool),
    (VideoTool.meta,         VideoTool),
    # o registro do próprio trabalho, que corre sozinho
    (AtividadesTool.meta,    AtividadesTool),
]


def build_tool(meta: ToolMeta, cls: type | None) -> ToolPage:
    """Instancia a ferramenta, ou a tela de 'em desenvolvimento'."""
    return cls() if cls is not None else PlaceholderPage(meta)


__all__ = ["REGISTRY", "build_tool", "ToolMeta", "ToolPage", "PlaceholderPage"]
