"""
Diálogo do termo de arquivo derivado.

A peça é a mesma para a Tarja Preta e para a Edição de Vídeo — muda o
título, a operação e as ressalvas, que vêm prontos no termo. Por isso o
diálogo vive aqui, e não duplicado nas duas ferramentas: um formulário
de qualificação, uma prévia editável e as saídas de sempre.

O que **não** é editável aqui são os resumos criptográficos e os nomes
dos arquivos. Eles foram medidos dos arquivos em disco, e um campo que
permitisse reescrevê-los faria da peça uma declaração sobre nada.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QGuiApplication, QTextDocument
from PyQt6.QtWidgets import (
    QDateEdit, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSizePolicy, QTextEdit,
    QVBoxLayout, QWidget,
)

from .. import perfil
from ..icons import draw_icon
from ..impressao import (documento_html, imprimir_documento,
                         limpar_para_sei, preparar_escritor)
from ..theme import PALETTE
from ..widgets import (NoScrollComboBox, field_label, fit_to_screen, hsep,
                       output_button, subtext)
from . import derivado_core as core


class TermoDerivadoDialog(QDialog):
    """A peça pronta para os autos, editável antes de salvar."""

    def __init__(self, termo: core.TermoDerivado, parent=None, modulo=None):
        super().__init__(parent)
        self.setWindowTitle(termo.titulo)
        self._termo = termo
        # Quem monta o texto da peca. A Analise de Planilha traz o seu
        # proprio, porque precisa do roteiro no meio; o formulario, a
        # previa e as saidas continuam sendo estes.
        self._core = modulo or core
        fit_to_screen(self, 940, 800)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        titulo = QLabel(termo.titulo)
        titulo.setObjectName("heading")
        titulo.setWordWrap(True)
        layout.addWidget(titulo)

        layout.addWidget(subtext(
            "Os resumos criptográficos e os nomes dos arquivos foram lidos "
            "do disco e não são editáveis — é o que amarra a peça aos "
            "arquivos. Complete a qualificação de quem assina.", wrap=True))

        layout.addWidget(self._montar_formulario())
        layout.addWidget(hsep())

        self._vista = QTextEdit()
        self._vista.setStyleSheet(
            "QTextEdit { background: #FFFFFF; color: #16233A; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; "
            "padding: 26px; }")
        layout.addWidget(self._vista, 1)
        layout.addWidget(hsep())
        layout.addWidget(self._montar_acoes())

        self._remontar()
        # Por último: preencher um campo dispara `textChanged`, que
        # remonta a prévia — e a prévia só existe depois. Chamado antes,
        # isto derruba o programa, porque exceção dentro de sinal do Qt
        # não vira erro, encerra o processo.
        perfil.aplicar(self)

    # ── formulário ───────────────────────────
    def _montar_formulario(self) -> QWidget:
        caixa = QWidget()
        grade = QGridLayout(caixa)
        grade.setContentsMargins(0, 4, 0, 4)
        grade.setHorizontalSpacing(10)
        grade.setVerticalSpacing(4)

        self._e_nome = QLineEdit()
        self._e_nome.setPlaceholderText("Ex.: João da Silva")
        self._e_cargo = QLineEdit()
        self._e_cargo.setPlaceholderText("Ex.: Policial Rodoviário Federal")
        self._e_matricula = QLineEdit()
        self._e_matricula.setPlaceholderText("Ex.: 1234567")
        self._e_lotacao = QLineEdit()
        self._e_lotacao.setPlaceholderText("Ex.: CGCOR — Brasília/DF")

        for coluna, (rotulo, campo) in enumerate((
                ("Nome do servidor", self._e_nome),
                ("Cargo", self._e_cargo),
                ("Matrícula", self._e_matricula),
                ("Lotação", self._e_lotacao))):
            grade.addWidget(field_label(rotulo), 0, coluna)
            grade.addWidget(campo, 1, coluna)
            campo.textChanged.connect(self._remontar)

        self._e_tipo = NoScrollComboBox()
        self._e_tipo.addItems(["IPS", "PAD"])
        self._e_tipo.currentTextChanged.connect(self._remontar)
        grade.addWidget(field_label("Procedimento"), 2, 0)
        grade.addWidget(self._e_tipo, 3, 0)

        self._e_processo = QLineEdit()
        self._e_processo.setPlaceholderText("Ex.: 08650.001234/2026-11")
        self._e_processo.textChanged.connect(self._remontar)
        grade.addWidget(field_label("Nº do procedimento"), 2, 1)
        grade.addWidget(self._e_processo, 3, 1)

        self._e_data = QDateEdit()
        self._e_data.setCalendarPopup(True)
        self._e_data.setDisplayFormat("dd/MM/yyyy")
        self._e_data.setDate(QDate.currentDate())
        self._e_data.dateChanged.connect(self._remontar)
        grade.addWidget(field_label("Data do termo"), 2, 2)
        grade.addWidget(self._e_data, 3, 2)

        return caixa

    def _montar_acoes(self) -> QWidget:
        acoes = QWidget()
        acoes.setSizePolicy(QSizePolicy.Policy.Preferred,
                            QSizePolicy.Policy.Fixed)
        linha = QHBoxLayout(acoes)
        linha.setContentsMargins(0, 8, 0, 0)
        linha.setSpacing(8)

        pdf = output_button("Salvar PDF")
        pdf.clicked.connect(self._salvar_pdf)
        linha.addWidget(pdf)

        htm = QPushButton("  Salvar HTML")
        htm.setIcon(draw_icon("save", 15, PALETTE["text"]))
        htm.setToolTip("Arquivo HTML, para importar no SEI")
        htm.setCursor(Qt.CursorShape.PointingHandCursor)
        htm.clicked.connect(self._salvar_html)
        linha.addWidget(htm)

        copiar = QPushButton("Copiar texto")
        copiar.setCursor(Qt.CursorShape.PointingHandCursor)
        copiar.clicked.connect(self._copiar)
        linha.addWidget(copiar)

        restaurar = QPushButton("  Restaurar original")
        restaurar.setIcon(draw_icon("undo"))
        restaurar.setToolTip("Descarta as alterações e remonta o termo")
        restaurar.setCursor(Qt.CursorShape.PointingHandCursor)
        restaurar.clicked.connect(self._remontar)
        linha.addWidget(restaurar)

        self._aviso = QLabel("")
        self._aviso.setObjectName("badge_ok")
        linha.addWidget(self._aviso)
        linha.addStretch()

        fechar = QPushButton("Fechar")
        fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        fechar.clicked.connect(self.accept)
        linha.addWidget(fechar)
        return acoes

    # ── estado ───────────────────────────────
    def _atualizado(self) -> core.TermoDerivado:
        t = self._termo
        d = self._e_data.date()
        t.nome = self._e_nome.text().strip()
        t.cargo = self._e_cargo.text().strip()
        t.matricula = self._e_matricula.text().strip()
        t.lotacao = self._e_lotacao.text().strip()
        t.tipo_processo = self._e_tipo.currentText()
        t.numero_processo = self._e_processo.text().strip()
        t.dia, t.mes, t.ano = d.day(), d.month(), d.year()
        return t

    def _remontar(self):
        self._vista.setHtml(self._core.build_html(self._atualizado()))

    def _sugerir(self, extensao: str) -> str:
        base = "termo"
        if self._termo.itens and self._termo.itens[0].saida.nome:
            base = Path(self._termo.itens[0].saida.nome).stem
        return str(Path.home() / "Documents" / f"termo-{base}{extensao}")

    # ── saídas ───────────────────────────────
    def _salvar_pdf(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar o termo", self._sugerir(".pdf"), "PDF (*.pdf)")
        if not caminho:
            return
        doc = QTextDocument()
        doc.setHtml(self._vista.toHtml())
        try:
            escritor = preparar_escritor(caminho, self._termo.titulo)
            imprimir_documento(doc, escritor)
        except Exception as e:                              # noqa: BLE001
            QMessageBox.warning(self, "Não foi possível salvar",
                                f"{type(e).__name__}: {e}")
            return
        self._anunciar(f"PDF salvo em {caminho}")

    def _salvar_html(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar o termo", self._sugerir(".html"), "HTML (*.html)")
        if not caminho:
            return
        try:
            Path(caminho).write_text(
                documento_html(limpar_para_sei(self._vista.toHtml()),
                               self._termo.titulo),
                encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, "Não foi possível salvar",
                                f"{type(e).__name__}: {e}")
            return
        self._anunciar(f"HTML salvo em {caminho}")

    def _copiar(self):
        QGuiApplication.clipboard().setText(
            self._core.build_texto(self._atualizado()))
        self._anunciar("Texto copiado")

    def _anunciar(self, texto: str):
        self._aviso.setText(f"  {texto}  ")
