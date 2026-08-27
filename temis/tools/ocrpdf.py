"""
PDF Pesquisável — reconhecimento óptico em documentos digitalizados.

A tela é uma fila: à esquerda entram os arquivos e os ajustes, à direita
sai o que aconteceu com cada um, página por página. O documento gerado
fica ao lado do original, com sufixo próprio — o recebido nunca é
sobrescrito.

Segue a disposição das outras ferramentas do sistema: painel lateral com
o que foi aberto, resultado ao centro e o termo saindo pelo botão verde
do rodapé.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PyQt6.QtCore import QDate, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox, QDateEdit, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QProgressBar, QPushButton, QSizePolicy,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import perfil
from ..icons import draw_icon
from ..impressao import (documento_html, imprimir_documento,
                         limpar_para_sei, preparar_escritor)
from ..theme import PALETTE
from ..widgets import (preparar_procedimento, ler_procedimento,
    
    NoScrollComboBox, SidebarPanel, danger_button, field_label,
    fit_to_screen, hsep, output_button, primary_button, subtext,
)
from . import ocr_windows
from . import ocrpdf_core as core
from .base import ToolMeta, ToolPage

META = ToolMeta(
    key="ocrpdf",
    name="PDF Pesquisável",
    icon="tool_ocrpdf",
    tagline="Torna o documento digitalizado pesquisável",
    description=(
        "Acrescenta camada de texto invisível a PDFs escaneados e a fotos "
        "de documentos, encaixada palavra por palavra sobre a imagem. O "
        "documento fica igual ao original — mesma imagem, mesma qualidade "
        "—, mas passa a permitir busca, seleção e cópia de texto, e a ser "
        "encontrado pela Varredura. Emite termo com o resumo "
        "criptográfico do arquivo recebido e do gerado."
    ),
)

FILTRO = (
    "Documentos digitalizados (*.pdf *.jpg *.jpeg *.png *.tif *.tiff "
    "*.bmp *.webp);;"
    "PDF (*.pdf);;"
    "Imagens (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp);;"
    "Todos os arquivos (*)"
)


# ─────────────────────────────────────────
#  CONVERSÃO EM SEGUNDO PLANO
# ─────────────────────────────────────────

class ConverterThread(QThread):
    """Reconhece a fila fora da interface.

    Uma página a 300 dpi leva mais de um segundo; um lote de cem
    páginas travaria a janela por minutos.
    """

    andamento = pyqtSignal(object)          # core.Progresso
    concluido = pyqtSignal(list, str)       # documentos, erro

    def __init__(self, entradas: list[str], pasta: str, opcoes: core.Opcoes):
        super().__init__()
        self._entradas = entradas
        self._pasta = pasta
        self._opcoes = opcoes
        self._parar = False

    def cancelar(self):
        self._parar = True

    def run(self):
        try:
            saidas = core.converter_varios(
                self._entradas, self._pasta, self._opcoes,
                progresso=self.andamento.emit,
                cancelar=lambda: self._parar)
            self.concluido.emit(saidas, "")
        except Exception as e:                          # noqa: BLE001
            self.concluido.emit([], f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────
#  TEXTO RECONHECIDO
# ─────────────────────────────────────────

class TextoDialog(QDialog):
    """O que a máquina leu, para conferência antes de juntar aos autos."""

    def __init__(self, documento: core.Documento, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Texto reconhecido — {documento.nome_saida}")
        fit_to_screen(self, 820, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        titulo = QLabel("Texto reconhecido")
        titulo.setObjectName("heading")
        layout.addWidget(titulo)
        layout.addWidget(subtext(
            "É o que ficou gravado na camada invisível. Serve à busca e à "
            "cópia; a leitura do documento continua sendo a da imagem "
            "original. Divergência entre um e outro resolve-se sempre em "
            "favor da imagem.", wrap=True))

        vista = QTextEdit()
        vista.setReadOnly(True)
        vista.setFont(QFont("Consolas", 9))
        vista.setPlainText(self._extrair(documento))
        layout.addWidget(vista, 1)

        rodape = QHBoxLayout()
        copiar = QPushButton("Copiar texto")
        copiar.setCursor(Qt.CursorShape.PointingHandCursor)
        copiar.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(vista.toPlainText()))
        rodape.addWidget(copiar)
        rodape.addStretch()
        fechar = QPushButton("Fechar")
        fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        fechar.clicked.connect(self.accept)
        rodape.addWidget(fechar)
        layout.addLayout(rodape)

    @staticmethod
    def _extrair(documento: core.Documento) -> str:
        import fitz
        try:
            with fitz.open(documento.saida) as pdf:
                partes = []
                for i, pagina in enumerate(pdf, 1):
                    partes.append(f"───── página {i} " + "─" * 40)
                    partes.append(pagina.get_text() or "(sem texto)")
                return "\n".join(partes)
        except Exception as e:                          # noqa: BLE001
            return f"Não foi possível ler o arquivo gerado:\n{e}"


# ─────────────────────────────────────────
#  TERMO
# ─────────────────────────────────────────

class TermoDialog(QDialog):
    """A peça pronta para os autos, editável antes de salvar."""

    def __init__(self, termo: core.TermoOCR, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Termo de Reconhecimento Óptico")
        self._termo = termo
        fit_to_screen(self, 940, 800)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        titulo = QLabel("Termo de Reconhecimento Óptico")
        titulo.setObjectName("heading")
        layout.addWidget(titulo)
        layout.addWidget(subtext(
            "Os campos abaixo montam a abertura do termo. O documento traz "
            "o resumo criptográfico do arquivo recebido e o do gerado, que "
            "é o que permite conferir um contra o outro depois.", wrap=True))
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
        # Por último, e não junto do formulário: preencher um campo
        # dispara `textChanged`, que remonta a prévia do termo — e a
        # prévia só existe depois. Chamado antes, isto derrubava o
        # programa inteiro, sem mensagem: exceção dentro de sinal do Qt
        # não vira erro em Python, vira encerramento do processo.
        #
        # Só os campos vazios são tocados. O que veio do termo anterior,
        # ou o que a pessoa escrever depois, vale mais que o perfil: ele
        # poupa digitação, não decide quem assina.
        perfil.aplicar(self)

    def _montar_formulario(self) -> QWidget:
        caixa = QWidget()
        grade = QGridLayout(caixa)
        grade.setContentsMargins(0, 4, 0, 4)
        grade.setHorizontalSpacing(10)
        grade.setVerticalSpacing(4)

        self._e_nome = QLineEdit()
        self._e_nome.setPlaceholderText("Ex.: João da Silva")
        self._e_matricula = QLineEdit()
        self._e_matricula.setPlaceholderText("Ex.: 1234567")
        self._e_lotacao = QLineEdit()
        self._e_lotacao.setPlaceholderText("Ex.: CGCOR - PRF/DF")
        for coluna, (rotulo, campo) in enumerate((
                ("Nome do servidor", self._e_nome),
                ("Matrícula", self._e_matricula),
                ("Lotação", self._e_lotacao))):
            grade.addWidget(field_label(rotulo), 0, coluna)
            grade.addWidget(campo, 1, coluna)
            campo.textChanged.connect(self._remontar)

        self._e_tipo = NoScrollComboBox()

        preparar_procedimento(self._e_tipo)
        self._e_tipo.currentIndexChanged.connect(self._remontar)
        self._e_processo = QLineEdit()
        self._e_processo.setPlaceholderText("Ex.: 08650.000123/2026-11")
        self._e_processo.textChanged.connect(self._remontar)
        self._e_data = QDateEdit()
        self._e_data.setCalendarPopup(True)
        self._e_data.setDisplayFormat("dd/MM/yyyy")
        self._e_data.setDate(QDate.currentDate())
        self._e_data.dateChanged.connect(self._remontar)
        for coluna, (rotulo, campo) in enumerate((
                ("Procedimento", self._e_tipo),
                ("Número do processo", self._e_processo),
                ("Data do termo", self._e_data))):
            grade.addWidget(field_label(rotulo), 2, coluna)
            grade.addWidget(campo, 3, coluna)

        grade.setColumnStretch(0, 3)
        grade.setColumnStretch(1, 1)
        grade.setColumnStretch(2, 2)
        grade.setRowMinimumHeight(2, 12)
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

    def _atualizado(self) -> core.TermoOCR:
        t = self._termo
        d = self._e_data.date()
        t.nome = self._e_nome.text().strip()
        t.matricula = self._e_matricula.text().strip()
        t.lotacao = self._e_lotacao.text().strip()
        t.tipo_processo = ler_procedimento(self._e_tipo)
        t.numero_processo = self._e_processo.text().strip()
        t.dia, t.mes, t.ano = d.day(), d.month(), d.year()
        return t

    def _remontar(self):
        self._vista.setHtml(core.build_html(self._atualizado()))

    def _copiar(self):
        QGuiApplication.clipboard().setText(core.build_text(self._atualizado()))
        self._aviso.setText("✓ Texto copiado")

    def _salvar_html(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo em HTML", "termo-ocr.html",
            "Página HTML (*.html)")
        if not caminho:
            return
        if not caminho.lower().endswith((".html", ".htm")):
            caminho += ".html"
        try:
            corpo = limpar_para_sei(self._vista.toHtml())
            Path(caminho).write_text(
                documento_html(corpo, "Termo de Reconhecimento Óptico de "
                                      "Documento Digitalizado"),
                encoding="utf-8")
            self._aviso.setText("✓ HTML salvo")
        except OSError as e:
            QMessageBox.critical(self, "Erro ao salvar",
                                 f"Não foi possível gravar o arquivo:\n{e}")

    def _salvar_pdf(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo", "termo-ocr.pdf", "Arquivos PDF (*.pdf)")
        if not caminho:
            return
        if not caminho.lower().endswith(".pdf"):
            caminho += ".pdf"
        try:
            escritor = preparar_escritor(
                caminho, "Termo de Reconhecimento Óptico de Documento "
                         "Digitalizado")
            doc = self._vista.document().clone()
            doc.setDefaultFont(QFont("Segoe UI", 10))
            imprimir_documento(doc, escritor)
            self._aviso.setText("✓ PDF salvo")
        except Exception as e:                          # noqa: BLE001
            QMessageBox.critical(self, "Erro ao salvar",
                                 f"Não foi possível gerar o PDF:\n{e}")


# ─────────────────────────────────────────
#  FERRAMENTA
# ─────────────────────────────────────────

class OCRPDFTool(ToolPage):
    meta = META

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fila: list[str] = []
        self._resultados: list[core.Documento] = []
        self._tarefa: ConverterThread | None = None
        self._pasta_saida = ""
        self._montar()
        self._atualizar_estado()

    # ── montagem ─────────────────────────────────
    def _montar(self):
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self._montar_lateral())

        principal = QWidget()
        coluna = QVBoxLayout(principal)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(0)
        coluna.addWidget(self._montar_progresso())
        coluna.addWidget(self._montar_resultados(), 1)
        coluna.addWidget(self._montar_detalhe())
        raiz.addWidget(principal, 1)

    def _montar_lateral(self) -> QWidget:
        painel = SidebarPanel()

        titulo = QLabel("Documentos")
        titulo.setObjectName("heading")
        painel.header.addWidget(titulo)

        b_add = primary_button("Adicionar arquivos…", "open")
        b_add.clicked.connect(self._adicionar)
        painel.header.addWidget(b_add)

        b_pasta = QPushButton("  Adicionar pasta…")
        b_pasta.setIcon(draw_icon("open", 15, PALETTE["text"]))
        b_pasta.setToolTip("Acrescenta todos os documentos da pasta")
        b_pasta.setCursor(Qt.CursorShape.PointingHandCursor)
        b_pasta.clicked.connect(self._adicionar_pasta)
        painel.header.addWidget(b_pasta)

        self._lista_fila = QListWidget()
        self._lista_fila.setMinimumHeight(140)
        painel.body.addWidget(self._lista_fila)

        self._b_remover = danger_button("Remover da fila")
        self._b_remover.clicked.connect(self._remover)
        painel.body.addWidget(self._b_remover)

        painel.body.addWidget(hsep())
        painel.body.addWidget(field_label("AJUSTES"))

        self._cb_dpi = NoScrollComboBox()
        for r in core.RESOLUCOES:
            self._cb_dpi.addItem(f"{r} dpi", r)
        self._cb_dpi.setCurrentIndex(core.RESOLUCOES.index(300))
        self._cb_dpi.setToolTip(
            "Resolução de leitura das páginas. Só o reconhecimento usa "
            "essa resolução; a imagem do documento não é alterada.")
        painel.body.addWidget(field_label("Resolução de leitura"))
        painel.body.addWidget(self._cb_dpi)

        self._op_so_sem_texto = QCheckBox("Só as páginas sem texto")
        self._op_so_sem_texto.setChecked(True)
        self._op_so_sem_texto.setToolTip(
            "Páginas que já têm texto são deixadas como estão. Desmarcado, "
            "todas são reconhecidas — o que duplica o texto das páginas "
            "já digitais.")
        painel.body.addWidget(self._op_so_sem_texto)

        self._rot_pasta = QLabel("Gerar ao lado do original")
        self._rot_pasta.setObjectName("muted")
        self._rot_pasta.setWordWrap(True)
        b_destino = QPushButton("Escolher pasta de saída…")
        b_destino.setCursor(Qt.CursorShape.PointingHandCursor)
        b_destino.clicked.connect(self._escolher_pasta)
        painel.body.addWidget(field_label("Onde gravar"))
        painel.body.addWidget(self._rot_pasta)
        painel.body.addWidget(b_destino)

        nota = QLabel(ocr_windows.diagnostico())
        nota.setObjectName("muted")
        nota.setWordWrap(True)
        painel.body.addWidget(hsep())
        painel.body.addWidget(nota)
        painel.body.addStretch()

        self._b_converter = primary_button("Reconhecer", "check")
        self._b_converter.clicked.connect(self._converter)
        painel.footer.addWidget(self._b_converter)

        self._b_termo = output_button("Gerar termo")
        self._b_termo.clicked.connect(self._gerar_termo)
        painel.footer.addWidget(self._b_termo)
        painel.add_note("O arquivo original nunca é sobrescrito: o "
                        "documento pesquisável sai em arquivo novo.")
        return painel

    def _montar_progresso(self) -> QWidget:
        self._caixa_progresso = QFrame()
        self._caixa_progresso.setStyleSheet(
            f"background: {PALETTE['surface2']}; "
            f"border-bottom: 1px solid {PALETTE['border']};")
        linha = QHBoxLayout(self._caixa_progresso)
        linha.setContentsMargins(14, 8, 14, 8)
        linha.setSpacing(10)

        self._barra = QProgressBar()
        self._barra.setTextVisible(False)
        self._barra.setFixedHeight(8)
        linha.addWidget(self._barra, 1)

        self._rot_progresso = QLabel("")
        self._rot_progresso.setObjectName("subtext")
        self._rot_progresso.setMinimumWidth(340)
        linha.addWidget(self._rot_progresso)

        self._b_cancelar = QPushButton("Cancelar")
        self._b_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._b_cancelar.clicked.connect(self._cancelar)
        linha.addWidget(self._b_cancelar)

        self._caixa_progresso.setVisible(False)
        return self._caixa_progresso

    def _montar_resultados(self) -> QWidget:
        self._arvore = QTreeWidget()
        self._arvore.setColumnCount(6)
        self._arvore.setHeaderLabels(
            ["Documento", "Páginas", "Reconhecidas", "Palavras",
             "Tamanho", "Tempo"])
        self._arvore.setRootIsDecorated(True)
        self._arvore.setAlternatingRowColors(True)
        cabeca = self._arvore.header()
        cabeca.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 6):
            cabeca.setSectionResizeMode(
                c, QHeaderView.ResizeMode.ResizeToContents)
        self._arvore.currentItemChanged.connect(self._mostrar_detalhe)
        self._arvore.itemDoubleClicked.connect(lambda *_: self._abrir())
        return self._arvore

    def _montar_detalhe(self) -> QWidget:
        painel = QFrame()
        painel.setStyleSheet(
            f"background: {PALETTE['surface']}; "
            f"border-top: 1px solid {PALETTE['border']};")
        linha = QHBoxLayout(painel)
        linha.setContentsMargins(14, 12, 14, 12)
        linha.setSpacing(14)

        self._corpo_detalhe = QTextEdit()
        self._corpo_detalhe.setReadOnly(True)
        self._corpo_detalhe.setStyleSheet(
            f"QTextEdit {{ background: {PALETTE['bg']}; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; "
            f"padding: 10px; }}")
        linha.addWidget(self._corpo_detalhe, 1)

        acoes = QVBoxLayout()
        acoes.setContentsMargins(0, 0, 0, 0)
        acoes.setSpacing(6)
        for rotulo, alvo in (("Abrir PDF gerado", self._abrir),
                             ("Abrir pasta", self._abrir_pasta),
                             ("Ver texto reconhecido", self._ver_texto),
                             ("Copiar hash do gerado", self._copiar_hash)):
            b = QPushButton(rotulo)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(alvo)
            acoes.addWidget(b)
        envelope = QWidget()
        envelope.setFixedWidth(210)
        envelope.setLayout(acoes)
        linha.addWidget(envelope)

        # A altura sai do que os botões pedem, e não de um número
        # escolhido a olho: a escala global do sistema e a fonte do
        # Windows mudam o tamanho deles, e um valor fixo corta o último.
        painel.setFixedHeight(envelope.sizeHint().height()
                              + linha.contentsMargins().top()
                              + linha.contentsMargins().bottom())
        return painel

    # ── fila ─────────────────────────────────────
    def _adicionar(self):
        caminhos, _ = QFileDialog.getOpenFileNames(
            self, "Escolha os documentos digitalizados", str(Path.home()),
            FILTRO)
        self._acrescentar(caminhos)

    def _adicionar_pasta(self):
        pasta = QFileDialog.getExistingDirectory(
            self, "Escolha a pasta com os documentos", str(Path.home()))
        if not pasta:
            return
        achados = [str(p) for p in sorted(Path(pasta).iterdir())
                   if p.is_file() and p.suffix.lower() in core.EXT_ACEITAS]
        if not achados:
            QMessageBox.information(
                self, "Nada a acrescentar",
                "Não há PDF nem imagem nessa pasta.")
            return
        self._acrescentar(achados)

    def _acrescentar(self, caminhos):
        novos = 0
        for caminho in caminhos:
            if caminho in self._fila:
                continue
            self._fila.append(caminho)
            item = QListWidgetItem(Path(caminho).name)
            item.setToolTip(caminho)
            self._lista_fila.addItem(item)
            novos += 1
        if novos:
            self.status_msg.emit(f"{novos} documento(s) na fila.")
        self._atualizar_estado()

    def _remover(self):
        for item in self._lista_fila.selectedItems():
            linha = self._lista_fila.row(item)
            self._lista_fila.takeItem(linha)
            del self._fila[linha]
        self._atualizar_estado()

    def _escolher_pasta(self):
        pasta = QFileDialog.getExistingDirectory(
            self, "Onde gravar os documentos gerados",
            self._pasta_saida or str(Path.home()))
        if not pasta:
            return
        self._pasta_saida = pasta
        self._rot_pasta.setText(pasta)

    # ── conversão ────────────────────────────────
    def _converter(self):
        if not self._fila:
            return
        if not ocr_windows.disponivel():
            QMessageBox.warning(self, "Reconhecimento indisponível",
                                ocr_windows.diagnostico())
            return

        opcoes = core.Opcoes(
            dpi=self._cb_dpi.currentData(),
            so_sem_texto=self._op_so_sem_texto.isChecked())

        self._resultados = []
        self._arvore.clear()
        self._tarefa = ConverterThread(list(self._fila), self._pasta_saida,
                                       opcoes)
        self._tarefa.andamento.connect(self._andamento)
        self._tarefa.concluido.connect(self._terminou)
        self._caixa_progresso.setVisible(True)
        self._barra.setRange(0, 0)
        self._rot_progresso.setText("Preparando…")
        self._atualizar_estado(trabalhando=True)
        self._tarefa.start()

    def _andamento(self, p: core.Progresso):
        if p.total_paginas:
            self._barra.setRange(0, p.total_paginas)
            self._barra.setValue(p.pagina)
        else:
            self._barra.setRange(0, 0)
        self._rot_progresso.setText(
            f"{p.arquivo} — página {p.pagina}/{p.total_paginas}"
            f"   ({p.indice_arquivo}/{p.total_arquivos} arquivos)")

    def _cancelar(self):
        if self._tarefa and self._tarefa.isRunning():
            self._rot_progresso.setText("Encerrando…")
            self._tarefa.cancelar()

    def _terminou(self, documentos: list, erro: str):
        self._caixa_progresso.setVisible(False)
        self._tarefa = None
        if erro:
            QMessageBox.critical(self, "Falha no reconhecimento", erro)
            self._atualizar_estado()
            return
        self._resultados = documentos
        self._preencher(documentos)
        self._atualizar_estado()

        bons = [d for d in documentos if d.gerou]
        pulados = [d for d in documentos if d.dispensado]
        ruins = [d for d in documentos if d.erro]
        self.status_msg.emit(
            f"{len(bons)} documento(s) gerado(s)"
            + (f", {len(pulados)} dispensado(s)" if pulados else "")
            + (f", {len(ruins)} com falha" if ruins else ""))
        if ruins:
            QMessageBox.warning(
                self, "Alguns documentos não foram processados",
                "\n".join(f"• {d.nome}: {d.erro}" for d in ruins[:8]))

    def _preencher(self, documentos: list):
        self._arvore.clear()
        for d in documentos:
            if d.erro:
                pai = QTreeWidgetItem([d.nome, "—", "—", "—", "—", "—"])
                pai.setForeground(0, QColor(PALETTE["danger"]))
                pai.setToolTip(0, d.erro)
                self._arvore.addTopLevelItem(pai)
                continue
            if d.dispensado:
                # Não gerou arquivo: dizer por quê, em vez de deixar uma
                # linha vazia que o usuário leria como falha.
                pai = QTreeWidgetItem([
                    f"{d.nome}  —  {d.motivo_dispensa}",
                    str(len(d.paginas)), "0", "0", "arquivo não gerado",
                    f"{d.segundos:.1f}s"])
                pai.setForeground(0, QColor(PALETTE["text3"]))
                pai.setData(0, Qt.ItemDataRole.UserRole, d.entrada)
                self._arvore.addTopLevelItem(pai)
                continue
            pai = QTreeWidgetItem([
                f"{d.nome}  →  {d.nome_saida}",
                str(len(d.paginas)), str(d.reconhecidas), str(d.palavras),
                f"{core.formatar_tamanho(d.tamanho_entrada)} → "
                f"{core.formatar_tamanho(d.tamanho_saida)}",
                f"{d.segundos:.1f}s"])
            pai.setData(0, Qt.ItemDataRole.UserRole, d.entrada)
            for p in d.paginas:
                filho = QTreeWidgetItem([
                    f"Página {p.numero} — "
                    f"{core.ROTULO_SITUACAO.get(p.situacao, p.situacao)}",
                    "", "", str(p.palavras), "", ""])
                if p.situacao == core.FALHOU:
                    filho.setForeground(0, QColor(PALETTE["danger"]))
                    filho.setToolTip(0, p.erro)
                elif p.situacao == core.NADA_ACHADO:
                    filho.setForeground(0, QColor(PALETTE["warning"]))
                pai.addChild(filho)
            self._arvore.addTopLevelItem(pai)
        if documentos:
            self._arvore.setCurrentItem(self._arvore.topLevelItem(0))

    # ── detalhe ──────────────────────────────────
    def _selecionado(self) -> core.Documento | None:
        item = self._arvore.currentItem()
        while item is not None and item.parent() is not None:
            item = item.parent()
        if item is None:
            return None
        entrada = item.data(0, Qt.ItemDataRole.UserRole)
        for d in self._resultados:
            if d.entrada == entrada:
                return d
        return None

    def _mostrar_detalhe(self, *_):
        d = self._selecionado()
        if d is None:
            self._corpo_detalhe.clear()
            return
        tinta, fraco = PALETTE["text"], PALETTE["text3"]
        if d.dispensado:
            self._corpo_detalhe.setHtml(
                f"<div style='font-family:Segoe UI; font-size:9pt; "
                f"color:{fraco};'><b style='color:{tinta};'>{d.nome}</b><br/>"
                f"{d.motivo_dispensa} — nenhum arquivo foi gerado.<br/><br/>"
                f"SHA-256 do recebido:<br/>"
                f"<span style='font-family:Consolas,monospace; font-size:8pt;"
                f" color:{tinta};'>{d.hash_entrada}</span></div>")
            return
        linhas = [
            ("Recebido", f"{d.nome}  "
                         f"({core.formatar_tamanho(d.tamanho_entrada)})"),
            ("SHA-256 do recebido", d.hash_entrada),
            ("Gerado", f"{d.nome_saida}  "
                       f"({core.formatar_tamanho(d.tamanho_saida)})"),
            ("SHA-256 do gerado", d.hash_saida),
            ("Resultado", f"{len(d.paginas)} página(s), "
                          f"{d.reconhecidas} reconhecida(s), "
                          f"{d.palavras} palavras, "
                          f"{d.caracteres} caracteres"),
        ]
        corpo = "".join(
            f"<tr><td style='padding:2px 12px 2px 0; color:{fraco}; "
            f"vertical-align:top; white-space:nowrap;'>{r}</td>"
            f"<td style='padding:2px 0; color:{tinta}; "
            f"font-family:{'Consolas,monospace' if 'SHA' in r else 'Segoe UI'};"
            f" font-size:{'8pt' if 'SHA' in r else '9pt'};'>{v}</td></tr>"
            for r, v in linhas)
        self._corpo_detalhe.setHtml(
            f"<div style='font-family:Segoe UI; font-size:9pt;'>"
            f"<table>{corpo}</table></div>")

    # ── ações ────────────────────────────────────
    def _abrir(self):
        d = self._selecionado()
        if d is None or not d.gerou:
            return
        try:
            os.startfile(d.saida)                       # noqa: S606
        except OSError as e:
            QMessageBox.warning(self, "Não foi possível abrir", str(e))

    def _abrir_pasta(self):
        d = self._selecionado()
        if d is None or not d.gerou:
            return
        try:
            subprocess.Popen(["explorer", "/select,", str(Path(d.saida))])
        except OSError as e:
            QMessageBox.warning(self, "Não foi possível abrir", str(e))

    def _ver_texto(self):
        d = self._selecionado()
        if d is None or not d.gerou:
            return
        TextoDialog(d, self).exec()

    def _copiar_hash(self):
        d = self._selecionado()
        if d is None or not d.gerou:
            return
        QGuiApplication.clipboard().setText(d.hash_saida)
        self.status_msg.emit("SHA-256 do documento gerado copiado.")

    # ── termo ────────────────────────────────────
    def _gerar_termo(self):
        if not [d for d in self._resultados if d.gerou]:
            return
        termo = core.TermoOCR(
            opcoes=core.Opcoes(
                dpi=self._cb_dpi.currentData(),
                so_sem_texto=self._op_so_sem_texto.isChecked(),
                idioma=ocr_windows.idioma_preferido()),
            documentos=list(self._resultados))
        TermoDialog(termo, self).exec()

    # ── estado ───────────────────────────────────
    def _atualizar_estado(self, trabalhando: bool = False):
        tem_fila = bool(self._fila) and not trabalhando
        self._b_converter.setEnabled(tem_fila)
        self._b_remover.setEnabled(bool(self._fila) and not trabalhando)
        self._b_termo.setEnabled(
            any(d.gerou for d in self._resultados) and not trabalhando)

    # ── ciclo de vida ────────────────────────────
    def can_close(self) -> bool:
        if self._tarefa and self._tarefa.isRunning():
            resposta = QMessageBox.question(
                self, "Reconhecimento em andamento",
                "Há documentos sendo processados. Encerrar agora interrompe "
                "o lote. Deseja encerrar mesmo assim?")
            if resposta != QMessageBox.StandardButton.Yes:
                return False
        return True

    def shutdown(self):
        if self._tarefa and self._tarefa.isRunning():
            self._tarefa.cancelar()
            self._tarefa.wait(6000)
