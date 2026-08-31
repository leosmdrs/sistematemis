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
from .conversa import ConversaTool
from .ips import IPSTool
from .metadados import MetadadosTool
from .espelhamento import EspelhamentoTool
from .extracao import ExtracaoTool
from .gravacao import GravacaoTool
from .ocrpdf import OCRPDFTool
from .pdf import PDFTool
from .planilha import PlanilhaTool
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
#: **Esta lista é a ordem do portal**, lida da esquerda para a direita e
#: de cima para baixo, em fileiras de cinco. Mudar a ordem aqui muda a
#: tela — não há segunda lista a acertar junto, e `provas/prova_readme.py`
#: obriga a tabela do README a acompanhar.
REGISTRY: list[tuple[ToolMeta, type | None]] = [
    # primeira fileira — a peça, e o preparo do documento que a instrui
    (IPSTool.meta,           IPSTool),
    (TarjaPretaTool.meta,    TarjaPretaTool),
    (AntiInjectionTool.meta, AntiInjectionTool),
    (MetadadosTool.meta,     MetadadosTool),
    (OCRPDFTool.meta,        OCRPDFTool),
    # segunda fileira — o registro da prova onde ela está
    (ConstatacaoTool.meta,   ConstatacaoTool),
    (ExtracaoTool.meta,      ExtracaoTool),
    (GravacaoTool.meta,      GravacaoTool),
    (EspelhamentoTool.meta,  EspelhamentoTool),
    (VarreduraTool.meta,     VarreduraTool),
    # terceira fileira — o exame do material e o registro do trabalho
    (QuadroTool.meta,        QuadroTool),
    (VideoTool.meta,         VideoTool),
    (TranscricaoTool.meta,   TranscricaoTool),
    (ConversaTool.meta,      ConversaTool),
    (PDFTool.meta,           PDFTool),
    (PlanilhaTool.meta,      PlanilhaTool),
    (AtividadesTool.meta,    AtividadesTool),
]


def build_tool(meta: ToolMeta, cls: type | None) -> ToolPage:
    """Instancia a ferramenta, ou a tela de 'em desenvolvimento'."""
    return cls() if cls is not None else PlaceholderPage(meta)


__all__ = ["REGISTRY", "build_tool", "ToolMeta", "ToolPage", "PlaceholderPage"]
