"""
Relatório de Atividades — a tela.

Esta ferramenta não registra nada: quem registra é o casco, desde que o
sistema abre. Aqui apenas se **lê** o que foi registrado — a sessão em
curso e as anteriores —, e se imprime ou apaga.

A separação é deliberada. Se o registro dependesse desta tela estar
aberta, faltaria justamente nas sessões em que ninguém a abriu — que são
quase todas. E o operador precisa poder ver, a qualquer momento, tudo o
que foi anotado a seu respeito: registro que o registrado não pode ler é
outra coisa, com outro nome.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QTextEdit, QVBoxLayout, QWidget,
)

from ..icons import draw_icon
from ..impressao import imprimir_documento, preparar_escritor
from ..theme import PALETTE
from ..widgets import (SidebarPanel, danger_button, output_button,
                       primary_button, subtext)
from . import atividades_core as core
from .base import ToolMeta, ToolPage

META = ToolMeta(
    key="atividades",
    name="Relatório de Atividades",
    icon="tool_atividades",
    tagline="Registra sozinho o que se fez em cada sessão",
    description=(
        "Documenta cada execução do sistema, do abrir ao fechar: as "
        "ferramentas usadas e por quanto tempo, o que cada uma relatou ao "
        "concluir, e a identificação completa da estação e da rede. "
        "Funciona sozinha, sem que ninguém precise ligá-la, e grava "
        "enquanto a sessão corre — de modo que uma queda de energia não "
        "leva junto o registro do que já havia sido feito. Tudo fica "
        "nesta máquina, à vista de quem operou."
    ),
)


class AtividadesTool(ToolPage):
    """Lê as sessões gravadas. Não grava nenhuma."""

    meta = META

    def __init__(self, parent=None):
        super().__init__(parent)
        #: Preenchido pelo casco, que é quem tem o registrador. Sem ele a
        #: tela ainda funciona: mostra as sessões que estão em disco.
        self.registrador: core.Registrador | None = None
        self._sessoes: list[core.Sessao] = []

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        raiz.addWidget(self._montar_painel())
        raiz.addWidget(self._montar_leitura(), 1)

        # A sessão em curso muda enquanto se trabalha; sem isto, quem
        # deixa a tela aberta vê um retrato parado.
        self._pulso = QTimer(self)
        self._pulso.setInterval(5000)
        self._pulso.timeout.connect(self._atualizar_corrente)

    # ── construção ───────────────────────────
    def _montar_painel(self) -> QWidget:
        painel = SidebarPanel()

        titulo = QLabel("Sessões")
        titulo.setObjectName("heading")
        painel.header.addWidget(titulo)
        painel.header.addWidget(subtext(
            "Cada execução do sistema, da mais recente para a mais antiga.",
            wrap=True))

        self._lista = QListWidget()
        self._lista.setWordWrap(True)
        self._lista.currentRowChanged.connect(self._mostrar)
        painel.body.addWidget(self._lista, 1)

        # Apagar fica no corpo, com a lista: é ação sobre o que está
        # selecionado ali. Salvar e abrir a pasta ficam no rodapé, que é
        # onde o painel guarda as ações de saída — e onde elas não somem
        # quando a lista de sessões cresce e o corpo rola.
        self._b_apagar = danger_button("Apagar esta sessão")
        self._b_apagar.setToolTip(
            "Remove do disco o registro da sessão selecionada")
        self._b_apagar.clicked.connect(self._apagar)
        painel.body.addWidget(self._b_apagar)

        self._b_pasta = primary_button("Abrir a pasta", "open")
        self._b_pasta.clicked.connect(self._abrir_pasta)
        painel.footer.addWidget(self._b_pasta)

        self._b_imprimir = output_button("Salvar em PDF")
        self._b_imprimir.clicked.connect(self._salvar_pdf)
        painel.footer.addWidget(self._b_imprimir)

        painel.add_note(
            "Fica só nesta máquina. Não são anotados o conteúdo dos "
            "arquivos nem o texto digitado — apenas que ferramenta foi "
            "usada, quando, e o que ela relatou ao concluir.")
        return painel

    def _montar_leitura(self) -> QWidget:
        caixa = QWidget()
        lay = QVBoxLayout(caixa)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)

        self._titulo = QLabel("Relatório de Atividades")
        self._titulo.setObjectName("heading")
        lay.addWidget(self._titulo)

        self._vista = QTextEdit()
        self._vista.setReadOnly(True)
        self._vista.setStyleSheet(
            "QTextEdit { background: #FFFFFF; color: #16233A; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; "
            "padding: 26px; }")
        lay.addWidget(self._vista, 1)
        return caixa

    # ── ciclo ────────────────────────────────
    def on_activated(self):
        self._recarregar()
        self._pulso.start()

    def on_deactivated(self):
        self._pulso.stop()

    # ── dados ────────────────────────────────
    def _recarregar(self, manter: int = 0):
        pasta = (self.registrador.pasta if self.registrador
                 else core.pasta_padrao())
        gravadas = core.sessoes(pasta)

        # A sessão em curso vem do registrador, e não do disco: ela ainda
        # está acontecendo, e o que está gravado é sempre um instante
        # atrás. Substitui a homônima em disco, se houver.
        corrente = self.registrador.sessao if self.registrador else None
        if corrente is not None and corrente.identificador:
            gravadas = [s for s in gravadas
                        if s.identificador != corrente.identificador]
            gravadas.insert(0, corrente)

        self._sessoes = gravadas
        self._lista.blockSignals(True)
        self._lista.clear()
        for s in self._sessoes:
            marca = "●" if not s.encerrada else "○"
            rotulo = (f" {marca}  {core.data_br(s.inicio)}\n"
                      f"      {core.duracao_por_extenso(s.duracao)} · "
                      f"{len(s.usos)} abertura(s) · "
                      f"{len(s.anotacoes)} ato(s)")
            item = QListWidgetItem(rotulo)
            if not s.encerrada:
                item.setForeground(Qt.GlobalColor.yellow)
                item.setToolTip("Sessão em curso ou interrompida")
            self._lista.addItem(item)
        self._lista.blockSignals(False)
        if self._sessoes:
            self._lista.setCurrentRow(min(manter, len(self._sessoes) - 1))
        else:
            self._vista.setHtml("")
            self._titulo.setText("Nenhuma sessão registrada ainda")
        self._habilitar()

    def _atualizar_corrente(self):
        """Redesenha só se a sessão em curso é a que está sendo lida."""
        if self._lista.currentRow() != 0 or self.registrador is None:
            return
        if self._sessoes and not self._sessoes[0].encerrada:
            self._mostrar(0)

    def _mostrar(self, linha: int):
        if not (0 <= linha < len(self._sessoes)):
            return
        s = self._sessoes[linha]
        self._titulo.setText(
            f"Sessão de {core.data_br(s.inicio)}"
            + ("" if s.encerrada else "   —   em curso ou interrompida"))
        self._vista.setHtml(core.relatorio_html(s))
        self._habilitar()

    def _habilitar(self):
        tem = 0 <= self._lista.currentRow() < len(self._sessoes)
        self._b_imprimir.setEnabled(tem)
        self._b_apagar.setEnabled(tem)

    # ── ações ────────────────────────────────
    def _selecionada(self) -> core.Sessao | None:
        linha = self._lista.currentRow()
        return self._sessoes[linha] if 0 <= linha < len(self._sessoes) else None

    def _salvar_pdf(self):
        s = self._selecionada()
        if s is None:
            return
        sugerido = str(Path.home() / "Documents" /
                       f"atividades-{s.identificador}.pdf")
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar o relatório", sugerido, "PDF (*.pdf)")
        if not caminho:
            return
        from PyQt6.QtGui import QTextDocument
        doc = QTextDocument()
        doc.setHtml(core.relatorio_html(s))
        try:
            escritor = preparar_escritor(caminho, "Relatório de Atividades")
            imprimir_documento(doc, escritor)
        except Exception as e:                              # noqa: BLE001
            QMessageBox.warning(self, "Não foi possível salvar",
                                f"{type(e).__name__}: {e}")
            return
        self.status_msg.emit(f"Relatório de atividades salvo em {caminho}")

    def _abrir_pasta(self):
        pasta = (self.registrador.pasta if self.registrador
                 else core.pasta_padrao())
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(pasta)                         # noqa: S606
            else:
                subprocess.Popen(["xdg-open", str(pasta)])
        except OSError as e:
            QMessageBox.warning(self, "Não foi possível abrir a pasta",
                                f"{type(e).__name__}: {e}")

    def _apagar(self):
        s = self._selecionada()
        if s is None:
            return
        corrente = (self.registrador is not None
                    and self.registrador.sessao.identificador
                    == s.identificador)
        if corrente:
            QMessageBox.information(
                self, "Sessão em curso",
                "Esta é a sessão que está acontecendo agora. Ela pode ser "
                "apagada depois que o sistema for encerrado.")
            return
        if QMessageBox.question(
                self, "Apagar o registro",
                f"Apagar em definitivo o registro da sessão de "
                f"{core.data_br(s.inicio)}?\n\nO relatório já salvo em PDF, "
                f"se houver, não é afetado.") != QMessageBox.StandardButton.Yes:
            return
        pasta = (self.registrador.pasta if self.registrador
                 else core.pasta_padrao())
        removidos = 0
        for alvo in (pasta / f"sessao-{s.identificador}.json",
                     pasta / f"atividades-{s.identificador}.html"):
            try:
                if alvo.exists():
                    alvo.unlink()
                    removidos += 1
            except OSError as e:
                QMessageBox.warning(self, "Não foi possível apagar",
                                    f"{alvo.name}: {e}")
        self.status_msg.emit(
            f"Registro da sessão de {core.data_br(s.inicio)} apagado "
            f"({removidos} arquivo(s)).")
        self._recarregar()
