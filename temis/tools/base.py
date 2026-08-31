"""
Contrato entre o casco do Têmis e cada ferramenta.

Uma ferramenta é apenas um QWidget que descreve a si mesma (`meta`) e
conversa com o casco por sinais — nunca chamando a janela principal
diretamente. Assim cada ferramenta continua sendo testável isolada, e
acrescentar uma nova ao hub é só registrá-la em `tools/__init__.py`.
"""

from dataclasses import dataclass

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel

from ..icons import draw_icon
from ..theme import PALETTE


@dataclass(frozen=True)
class ToolMeta:
    """Descrição de uma ferramenta para o menu e a tela inicial."""

    key: str            # identificador estável
    name: str           # nome exibido no portal e na barra da ferramenta
    icon: str           # chave em icons.draw_icon
    tagline: str        # uma linha, usada em dicas de contexto
    description: str    # parágrafo curto, na tela de "em desenvolvimento"
    available: bool = True
    #: Depende de acesso à internet. O sistema promete processamento local;
    #: uma ferramenta que sai da máquina precisa dizer isso ao usuário, e
    #: não ficar escondida atrás da promessa geral.
    online: bool = False


class ToolPage(QWidget):
    """Classe-base de uma ferramenta do Têmis."""

    #: Mensagem para a barra de status do casco.
    status_msg = pyqtSignal(str)

    meta: ToolMeta

    #: A pasta desta sessão de trabalho, entregue pelo casco quando há uma.
    #: Ferramenta que a ignora salva onde sempre salvou; quem a usa — por
    #: `destino_na_sessao` — faz suas peças caírem, por padrão, na pasta da
    #: diligência, reunindo a sessão inteira num lugar só.
    sessao = None

    def destino_na_sessao(self, subpasta: str, nome: str,
                          fallback=None) -> str:
        """Caminho a propor num diálogo de salvar, na pasta da sessão.

        Delega à função homônima do módulo `sessao`, que acha a sessão
        subindo pela árvore de widgets — de modo que serve tanto aqui,
        na ferramenta, quanto nos diálogos de termo que ela abre.
        """
        from ..sessao import destino_para_dialogo
        return destino_para_dialogo(self, subpasta, nome, fallback)

    def on_activated(self):
        """Chamado sempre que a ferramenta passa a ser a visível."""

    def on_deactivated(self):
        """Chamado quando outra ferramenta assume a tela."""

    def can_close(self) -> bool:
        """Retorna False para impedir o fechamento (trabalho não salvo)."""
        return True

    def shutdown(self):
        """Libera recursos (arquivos abertos, threads) ao encerrar."""


class PlaceholderPage(ToolPage):
    """Tela das ferramentas ainda não implementadas."""

    def __init__(self, meta: ToolMeta, parent=None):
        super().__init__(parent)
        self.meta = meta

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(14)
        layout.addStretch()

        icon = QLabel()
        icon.setPixmap(draw_icon(meta.icon, 56, PALETTE["text3"], width=2.4).pixmap(56, 56))
        layout.addWidget(icon)

        title = QLabel(meta.name)
        title.setStyleSheet(
            f"font-size: 24px; font-weight: 800; color: {PALETTE['text2']};"
        )
        layout.addWidget(title)

        badge = QLabel("EM DESENVOLVIMENTO")
        badge.setStyleSheet(
            f"color: {PALETTE['warning']}; font-size: 11px; font-weight: 700;"
            f"letter-spacing: 1px;"
        )
        layout.addWidget(badge)

        desc = QLabel(meta.description)
        desc.setObjectName("subtext")
        desc.setWordWrap(True)
        desc.setMaximumWidth(560)
        layout.addWidget(desc)

        layout.addStretch()
