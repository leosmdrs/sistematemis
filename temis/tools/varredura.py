"""
Varredura — indexação e busca em massa de acervos digitais.

A tela responde a uma pergunta só: *o que tem aqui dentro?* À esquerda,
a origem e os recortes; no alto, a linha de busca; embaixo, o que
apareceu, com o trecho que casou destacado. As demais abas olham o mesmo
acervo por outros ângulos — as imagens em galeria, os arquivos
repetidos, o resumo do conjunto.

Segue a disposição das outras ferramentas do sistema: painel lateral com
a origem e os filtros, barra de modos no alto e o termo saindo pelo
botão verde do rodapé.
"""

from __future__ import annotations

import datetime
import os
import subprocess
from pathlib import Path

from PyQt6.QtCore import QDate, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QGuiApplication, QIcon, QPixmap, QTextDocument,
)
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QDateEdit, QDialog,
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QPushButton, QSizePolicy, QStackedWidget, QStyle, QStyledItemDelegate,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import perfil
from ..icons import draw_icon
from ..impressao import (documento_html, imprimir_documento,
                         limpar_para_sei, preparar_escritor)
from ..theme import PALETTE
from ..widgets import (preparar_procedimento, ler_procedimento,
    
    NoScrollComboBox, SidebarPanel, field_label, fit_to_screen, hsep,
    output_button, primary_button, subtext,
)
from . import ocr_windows
from . import varredura_core as core
from .base import ToolMeta, ToolPage

META = ToolMeta(
    key="varredura",
    name="Varredura",
    icon="tool_varredura",
    tagline="Indexa um acervo e procura dentro de tudo",
    description=(
        "Percorre um pendrive, um cartão ou uma pasta inteira, calcula o "
        "SHA-256 de cada arquivo e extrai o texto que houver — inclusive "
        "o de páginas digitalizadas, por reconhecimento óptico. A partir "
        "daí a busca é instantânea e não toca mais no dispositivo, que "
        "pode ser lacrado. Filtra por natureza do arquivo, data, tamanho "
        "e coordenadas; mostra as imagens em galeria e aponta os "
        "duplicados. Emite termo com o resumo do conjunto e o registro "
        "das pesquisas feitas."
    ),
)

#: Onde ficam os índices, por padrão.
PASTA_PADRAO = Path.home() / "Documents" / "Sistema Têmis" / "Varreduras"

#: Cores do trecho destacado no resultado.
COR_ACERTO = PALETTE["gold"]
COR_TRECHO = PALETTE["text2"]


# ─────────────────────────────────────────
#  INDEXAÇÃO EM SEGUNDO PLANO
# ─────────────────────────────────────────

class IndexarThread(QThread):
    """Varre a origem fora da interface.

    Um pendrive de 32 GB leva minutos só para ser resumido
    criptograficamente; travar a janela nesse tempo seria inaceitável.
    """

    andamento = pyqtSignal(object)          # core.Progresso
    concluido = pyqtSignal(object, str)     # resumo, erro

    def __init__(self, indice: core.Indice, raiz: str, opcoes: core.Opcoes):
        super().__init__()
        self._indice = indice
        self._raiz = raiz
        self._opcoes = opcoes
        self._parar = False

    def cancelar(self):
        self._parar = True

    def run(self):
        try:
            resumo = self._indice.indexar(
                self._raiz, self._opcoes,
                progresso=self.andamento.emit,
                cancelar=lambda: self._parar)
            self.concluido.emit(resumo, "")
        except Exception as e:                          # noqa: BLE001
            self.concluido.emit(None, f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────
#  TRECHO COM DESTAQUE
# ─────────────────────────────────────────

class DelegadoTrecho(QStyledItemDelegate):
    """Pinta o trecho do resultado com o termo procurado em destaque.

    Sem o destaque a coluna vira um borrão de texto: o que faz a busca
    útil é enxergar, na própria lista, *onde* a palavra apareceu.
    """

    PAPEL = Qt.ItemDataRole.UserRole + 1

    def _documento(self, indice) -> QTextDocument:
        doc = QTextDocument()
        doc.setDefaultFont(QFont("Segoe UI", 8))
        doc.setDocumentMargin(2)
        doc.setHtml(indice.data(self.PAPEL) or "")
        return doc

    def paint(self, pintor, opcao, indice):
        bruto = indice.data(self.PAPEL)
        if not bruto:
            super().paint(pintor, opcao, indice)
            return
        estilo = opcao.widget.style() if opcao.widget else None
        if estilo:
            estilo.drawControl(QStyle.ControlElement.CE_ItemViewItem,
                               opcao, pintor, opcao.widget)
        doc = self._documento(indice)
        doc.setTextWidth(opcao.rect.width() - 6)
        pintor.save()
        pintor.translate(opcao.rect.left() + 3, opcao.rect.top() + 2)
        doc.drawContents(pintor)
        pintor.restore()

    def sizeHint(self, opcao, indice):
        if not indice.data(self.PAPEL):
            return super().sizeHint(opcao, indice)
        return QSize(200, 34)


def _html_trecho(achado: core.Achado) -> str:
    """O trecho em uma linha, com o acerto realçado."""
    if not achado.trecho:
        return ""
    bruto = achado.trecho.replace("\n", " ")
    corpo = core.destacar(bruto).replace(
        '<span class="hit">', f'<b style="color:{COR_ACERTO};">').replace(
        "</span>", "</b>")
    return f'<span style="color:{COR_TRECHO};">{corpo}</span>'


# ─────────────────────────────────────────
#  TERMO
# ─────────────────────────────────────────

class TermoDialog(QDialog):
    """A peça pronta para os autos, editável antes de salvar."""

    def __init__(self, termo: core.TermoVarredura, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Termo de Varredura e Indexação")
        self._termo = termo
        fit_to_screen(self, 960, 820)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        titulo = QLabel("Termo de Varredura")
        titulo.setObjectName("heading")
        layout.addWidget(titulo)
        layout.addWidget(subtext(
            "Os campos abaixo montam a abertura do termo. O documento já "
            "traz a identificação do dispositivo, o resumo criptográfico "
            "do conjunto e as pesquisas que foram registradas.", wrap=True))
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

        self._e_nome = QLineEdit(self._termo.nome)
        self._e_nome.setPlaceholderText("Ex.: João da Silva")
        self._e_matricula = QLineEdit(self._termo.matricula)
        self._e_matricula.setPlaceholderText("Ex.: 1234567")
        self._e_lotacao = QLineEdit(self._termo.lotacao)
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
        self._e_processo = QLineEdit(self._termo.numero_processo)
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

        # O dispositivo, descrito por quem o recebeu. É o que liga o
        # índice ao objeto físico guardado na sala de custódia.
        self._e_dispositivo = QLineEdit(self._termo.descricao_origem)
        self._e_dispositivo.setPlaceholderText(
            "Ex.: Pen drive SanDisk 32 GB, lacre nº 004321")
        self._e_dispositivo.textChanged.connect(self._remontar)
        grade.addWidget(field_label("Descrição do dispositivo"), 4, 0, 1, 3)
        grade.addWidget(self._e_dispositivo, 5, 0, 1, 3)

        grade.setColumnStretch(0, 3)
        grade.setColumnStretch(1, 1)
        grade.setColumnStretch(2, 2)
        grade.setRowMinimumHeight(2, 12)
        grade.setRowMinimumHeight(4, 12)
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

    # ── documento ────────────────────────────────
    def _atualizado(self) -> core.TermoVarredura:
        t = self._termo
        d = self._e_data.date()
        t.nome = self._e_nome.text().strip()
        t.matricula = self._e_matricula.text().strip()
        t.lotacao = self._e_lotacao.text().strip()
        t.tipo_processo = ler_procedimento(self._e_tipo)
        t.numero_processo = self._e_processo.text().strip()
        t.descricao_origem = self._e_dispositivo.text().strip()
        t.dia, t.mes, t.ano = d.day(), d.month(), d.year()
        return t

    def _remontar(self):
        self._vista.setHtml(core.build_html(self._atualizado()))

    def _copiar(self):
        QGuiApplication.clipboard().setText(core.build_text(self._atualizado()))
        self._aviso.setText("✓ Texto copiado")

    def _salvar_html(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo em HTML", "termo-varredura.html",
            "Página HTML (*.html)")
        if not caminho:
            return
        if not caminho.lower().endswith((".html", ".htm")):
            caminho += ".html"
        try:
            # Sai o documento em edição, não o remontado: os ajustes de
            # redação feitos aqui têm de acompanhar o arquivo exportado.
            corpo = limpar_para_sei(self._vista.toHtml())
            Path(caminho).write_text(
                documento_html(corpo, "Termo de Varredura e Indexação de "
                                      "Acervo Digital"), encoding="utf-8")
            self._aviso.setText("✓ HTML salvo")
        except OSError as e:
            QMessageBox.critical(self, "Erro ao salvar",
                                 f"Não foi possível gravar o arquivo:\n{e}")

    def _salvar_pdf(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo", "termo-varredura.pdf",
            "Arquivos PDF (*.pdf)")
        if not caminho:
            return
        if not caminho.lower().endswith(".pdf"):
            caminho += ".pdf"
        try:
            escritor = preparar_escritor(
                caminho, "Termo de Varredura e Indexação de Acervo Digital")
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

class VarreduraTool(ToolPage):
    meta = META

    ABAS = ("Resultados", "Galeria", "Duplicatas", "Panorama")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._indice: core.Indice | None = None
        self._tarefa: IndexarThread | None = None
        self._achados: list[core.Achado] = []
        self._marcados: dict[int, core.Achado] = {}
        self._registros: list[core.Registro] = []
        self._selecionado: core.Achado | None = None

        # Digitar dispara a busca, mas não a cada tecla: sem a espera, um
        # acervo grande refaz a consulta seis vezes ao escrever "roubo".
        self._espera = QTimer(self)
        self._espera.setSingleShot(True)
        self._espera.setInterval(320)
        self._espera.timeout.connect(self._buscar)

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
        coluna.addWidget(self._montar_barra())
        coluna.addWidget(self._montar_progresso())

        corpo = QHBoxLayout()
        corpo.setContentsMargins(0, 0, 0, 0)
        corpo.setSpacing(0)
        corpo.addWidget(self._montar_paginas(), 1)
        corpo.addWidget(self._montar_detalhe())
        envelope = QWidget()
        envelope.setLayout(corpo)
        coluna.addWidget(envelope, 1)
        raiz.addWidget(principal, 1)

    def _montar_lateral(self) -> QWidget:
        painel = SidebarPanel()

        titulo = QLabel("Acervo")
        titulo.setObjectName("heading")
        painel.header.addWidget(titulo)

        b_nova = primary_button("Nova varredura…", "open")
        b_nova.clicked.connect(self._nova_varredura)
        painel.header.addWidget(b_nova)

        b_abrir = QPushButton("  Abrir índice existente…")
        b_abrir.setIcon(draw_icon("open", 15, PALETTE["text"]))
        b_abrir.setCursor(Qt.CursorShape.PointingHandCursor)
        b_abrir.clicked.connect(self._abrir_indice)
        painel.header.addWidget(b_abrir)

        # ── origem ────────────────────────
        self._rot_origem = QLabel("Nenhum acervo carregado.")
        self._rot_origem.setObjectName("subtext")
        self._rot_origem.setWordWrap(True)
        painel.body.addWidget(self._rot_origem)

        painel.body.addWidget(hsep())

        # ── opções da varredura ───────────
        painel.body.addWidget(field_label("AO INDEXAR"))
        self._op_ocr = QCheckBox("Reconhecer texto em imagens (OCR)")
        self._op_ocr.setChecked(ocr_windows.disponivel())
        self._op_ocr.setEnabled(ocr_windows.disponivel())
        self._op_ocr.setToolTip(ocr_windows.diagnostico())
        painel.body.addWidget(self._op_ocr)

        nota_ocr = QLabel(ocr_windows.diagnostico())
        nota_ocr.setObjectName("muted")
        nota_ocr.setWordWrap(True)
        painel.body.addWidget(nota_ocr)

        self._op_ocultos = QCheckBox("Incluir arquivos ocultos")
        self._op_ocultos.setChecked(True)
        painel.body.addWidget(self._op_ocultos)

        self._op_leitura = QCheckBox("Origem em somente leitura")
        self._op_leitura.setToolTip(
            "Marque quando o acesso for por bloqueador de escrita ou "
            "sobre cópia de trabalho. Vai declarado no termo.")
        painel.body.addWidget(self._op_leitura)

        painel.body.addWidget(hsep())

        # ── filtros ───────────────────────
        painel.body.addWidget(field_label("RECORTE"))
        self._caixas_categoria: dict[str, QCheckBox] = {}
        for nome in core.ORDEM_CATEGORIAS:
            caixa = QCheckBox(nome)
            caixa.stateChanged.connect(self._buscar)
            caixa.setVisible(False)
            painel.body.addWidget(caixa)
            self._caixas_categoria[nome] = caixa

        self._f_texto = QCheckBox("Só com texto extraído")
        self._f_ocr = QCheckBox("Só o que veio de OCR")
        self._f_gps = QCheckBox("Só com coordenadas")
        for caixa in (self._f_texto, self._f_ocr, self._f_gps):
            caixa.stateChanged.connect(self._buscar)
            painel.body.addWidget(caixa)

        b_limpar = QPushButton("Limpar recorte")
        b_limpar.setCursor(Qt.CursorShape.PointingHandCursor)
        b_limpar.clicked.connect(self._limpar_filtros)
        painel.body.addWidget(b_limpar)
        painel.body.addStretch()

        # ── rodapé ────────────────────────
        self._b_termo = output_button("Gerar termo")
        self._b_termo.clicked.connect(self._gerar_termo)
        painel.footer.addWidget(self._b_termo)
        self._rot_registros = QLabel("")
        self._rot_registros.setObjectName("muted")
        self._rot_registros.setWordWrap(True)
        self._rot_registros.setAlignment(Qt.AlignmentFlag.AlignCenter)
        painel.footer.addWidget(self._rot_registros)
        painel.add_note("A leitura é passiva: nenhum arquivo da origem é "
                        "alterado.")
        return painel

    def _montar_barra(self) -> QWidget:
        barra = QFrame()
        barra.setObjectName("toolbar")
        barra.setStyleSheet(
            f"QFrame#toolbar {{ background: {PALETTE['surface']}; "
            f"border-bottom: 1px solid {PALETTE['border']}; }}")
        linha = QVBoxLayout(barra)
        linha.setContentsMargins(14, 10, 14, 10)
        linha.setSpacing(8)

        busca = QHBoxLayout()
        busca.setSpacing(8)
        self._e_busca = QLineEdit()
        self._e_busca.setPlaceholderText(
            "Procure em tudo — palavra, \"expressão exata\", prefixo* , "
            "termo1 E termo2, termo1 OU termo2, termo NAO outro")
        self._e_busca.setClearButtonEnabled(True)
        self._e_busca.textChanged.connect(lambda: self._espera.start())
        self._e_busca.returnPressed.connect(self._buscar)
        busca.addWidget(self._e_busca, 1)

        self._b_registrar = QPushButton("  Registrar no termo")
        self._b_registrar.setIcon(draw_icon("check", 15, PALETTE["text"]))
        self._b_registrar.setToolTip(
            "Anota esta pesquisa e o que ela devolveu no termo de varredura")
        self._b_registrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._b_registrar.clicked.connect(self._registrar_busca)
        busca.addWidget(self._b_registrar)
        linha.addLayout(busca)

        abas = QHBoxLayout()
        abas.setSpacing(6)
        self._grupo_abas = QButtonGroup(self)
        self._grupo_abas.setExclusive(True)
        for i, nome in enumerate(self.ABAS):
            botao = QPushButton(nome)
            botao.setCheckable(True)
            botao.setChecked(i == 0)
            botao.setCursor(Qt.CursorShape.PointingHandCursor)
            self._grupo_abas.addButton(botao, i)
            abas.addWidget(botao)
        self._grupo_abas.idClicked.connect(self._trocar_aba)

        abas.addStretch()
        self._rot_contagem = QLabel("")
        self._rot_contagem.setObjectName("subtext")
        abas.addWidget(self._rot_contagem)
        linha.addLayout(abas)
        return barra

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
        self._rot_progresso.setMinimumWidth(360)
        linha.addWidget(self._rot_progresso)

        self._b_cancelar = QPushButton("Cancelar")
        self._b_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._b_cancelar.clicked.connect(self._cancelar_varredura)
        linha.addWidget(self._b_cancelar)

        self._caixa_progresso.setVisible(False)
        return self._caixa_progresso

    def _montar_paginas(self) -> QWidget:
        self._paginas = QStackedWidget()

        # ── resultados ────────────────────
        self._arvore = QTreeWidget()
        self._arvore.setColumnCount(5)
        self._arvore.setHeaderLabels(
            ["Arquivo", "Trecho encontrado", "Tamanho", "Alterado", "Texto"])
        self._arvore.setRootIsDecorated(False)
        self._arvore.setAlternatingRowColors(True)
        self._arvore.setUniformRowHeights(False)
        self._arvore.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._arvore.setItemDelegateForColumn(1, DelegadoTrecho(self._arvore))
        cabeca = self._arvore.header()
        cabeca.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        cabeca.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (2, 3, 4):
            cabeca.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self._arvore.setColumnWidth(0, 300)
        self._arvore.currentItemChanged.connect(self._mostrar_detalhe)
        self._arvore.itemChanged.connect(self._alternar_marca)
        self._arvore.itemDoubleClicked.connect(
            lambda *_: self._abrir_arquivo())
        self._paginas.addWidget(self._arvore)

        # ── galeria ───────────────────────
        self._galeria = QListWidget()
        self._galeria.setViewMode(QListWidget.ViewMode.IconMode)
        self._galeria.setIconSize(QSize(150, 150))
        self._galeria.setGridSize(QSize(172, 194))
        self._galeria.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._galeria.setMovement(QListWidget.Movement.Static)
        self._galeria.setSpacing(6)
        self._galeria.setWordWrap(True)
        # O tema desenha uma linha sob cada item da lista, que serve para
        # lista em coluna e vira risco atravessado sob a miniatura aqui.
        self._galeria.setStyleSheet(
            f"QListWidget {{ background: {PALETTE['bg']}; border: none; }}"
            f"QListWidget::item {{ border: none; padding: 4px; "
            f"color: {PALETTE['text2']}; }}"
            f"QListWidget::item:selected {{ background: {PALETTE['surface3']}; "
            f"color: {PALETTE['text']}; border-radius: 6px; }}")
        self._galeria.currentItemChanged.connect(self._detalhe_da_galeria)
        self._galeria.itemDoubleClicked.connect(
            lambda *_: self._abrir_arquivo())
        self._paginas.addWidget(self._galeria)

        # ── duplicatas ────────────────────
        self._dupes = QTreeWidget()
        self._dupes.setColumnCount(3)
        self._dupes.setHeaderLabels(["Arquivo", "Tamanho", "SHA-256"])
        self._dupes.setAlternatingRowColors(True)
        self._dupes.currentItemChanged.connect(self._detalhe_da_duplicata)
        self._dupes.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._paginas.addWidget(self._dupes)

        # ── panorama ──────────────────────
        self._panorama = QTextEdit()
        self._panorama.setReadOnly(True)
        self._panorama.setStyleSheet(
            f"QTextEdit {{ background: {PALETTE['bg']}; border: none; "
            f"padding: 20px 26px; }}")
        self._paginas.addWidget(self._panorama)
        return self._paginas

    def _montar_detalhe(self) -> QWidget:
        painel = QFrame()
        painel.setFixedWidth(330)
        painel.setStyleSheet(
            f"background: {PALETTE['surface']}; "
            f"border-left: 1px solid {PALETTE['border']};")
        coluna = QVBoxLayout(painel)
        coluna.setContentsMargins(14, 14, 14, 14)
        coluna.setSpacing(10)

        self._rot_detalhe = QLabel("Selecione um arquivo.")
        self._rot_detalhe.setObjectName("subtext")
        self._rot_detalhe.setWordWrap(True)
        coluna.addWidget(self._rot_detalhe)

        self._miniatura = QLabel()
        self._miniatura.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._miniatura.setVisible(False)
        coluna.addWidget(self._miniatura)

        self._corpo_detalhe = QTextEdit()
        self._corpo_detalhe.setReadOnly(True)
        self._corpo_detalhe.setStyleSheet(
            f"QTextEdit {{ background: {PALETTE['bg']}; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; "
            f"padding: 10px; }}")
        coluna.addWidget(self._corpo_detalhe, 1)

        self._b_marcar = QPushButton("Destacar para juntada")
        self._b_marcar.setCheckable(True)
        self._b_marcar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._b_marcar.clicked.connect(self._marcar_selecionado)
        coluna.addWidget(self._b_marcar)

        acoes = QHBoxLayout()
        acoes.setSpacing(6)
        b_abrir = QPushButton("Abrir")
        b_abrir.setCursor(Qt.CursorShape.PointingHandCursor)
        b_abrir.clicked.connect(self._abrir_arquivo)
        acoes.addWidget(b_abrir)
        b_pasta = QPushButton("Abrir pasta")
        b_pasta.setCursor(Qt.CursorShape.PointingHandCursor)
        b_pasta.clicked.connect(self._abrir_pasta)
        acoes.addWidget(b_pasta)
        b_hash = QPushButton("Copiar hash")
        b_hash.setCursor(Qt.CursorShape.PointingHandCursor)
        b_hash.clicked.connect(self._copiar_hash)
        acoes.addWidget(b_hash)
        coluna.addLayout(acoes)
        return painel

    # ── varredura ────────────────────────────────
    def _nova_varredura(self):
        origem = QFileDialog.getExistingDirectory(
            self, "Escolha a pasta ou a unidade a varrer", str(Path.home()))
        if not origem:
            return

        volume = core.informacao_volume(origem)
        aviso = QMessageBox(self)
        aviso.setWindowTitle("Antes de varrer")
        aviso.setIcon(QMessageBox.Icon.Information)
        rotulo = volume.get("rotulo") or volume.get("unidade") or "—"
        aviso.setText(f"Origem: {origem}\nVolume: {rotulo}"
                      + (f"  (série {volume['serie']})"
                         if volume.get("serie") else ""))
        aviso.setInformativeText(
            "A leitura é passiva — nenhum arquivo será alterado pelo "
            "programa. Ainda assim, montar um dispositivo no Windows pode "
            "modificá-lo: o sistema cria pastas próprias e a indexação do "
            "Explorer escreve nele.\n\n"
            "Quando o material for objeto de apuração, o correto é usar "
            "bloqueador de escrita ou trabalhar sobre cópia — e marcar a "
            "opção “Origem em somente leitura”, que fica declarada no "
            "termo.\n\nDeseja prosseguir?")
        aviso.setStandardButtons(QMessageBox.StandardButton.Yes
                                 | QMessageBox.StandardButton.Cancel)
        aviso.setDefaultButton(QMessageBox.StandardButton.Yes)
        if aviso.exec() != QMessageBox.StandardButton.Yes:
            return

        PASTA_PADRAO.mkdir(parents=True, exist_ok=True)
        sugestao = PASTA_PADRAO / (
            f"varredura-{Path(origem).name or rotulo or 'acervo'}"
            f"-{datetime.date.today():%Y-%m-%d}{core.SUFIXO}")
        destino, _ = QFileDialog.getSaveFileName(
            self, "Onde gravar o índice", str(sugestao),
            f"Índice de varredura (*{core.SUFIXO})")
        if not destino:
            return
        if not destino.lower().endswith(core.SUFIXO):
            destino += core.SUFIXO
        # Índice antigo com o mesmo nome seria mesclado ao novo; a
        # indexação limpa as tabelas, mas o arquivo cresceria à toa.
        try:
            Path(destino).unlink(missing_ok=True)
        except OSError as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível "
                                               f"substituir o índice:\n{e}")
            return

        self._fechar_indice()
        try:
            self._indice = core.Indice(destino)
        except Exception as e:                          # noqa: BLE001
            QMessageBox.critical(self, "Erro",
                                 f"Não foi possível criar o índice:\n{e}")
            return

        opcoes = core.Opcoes(
            ocr=self._op_ocr.isChecked(),
            ocultos=self._op_ocultos.isChecked(),
            somente_leitura=self._op_leitura.isChecked())

        self._marcados.clear()
        self._registros.clear()
        self._tarefa = IndexarThread(self._indice, origem, opcoes)
        self._tarefa.andamento.connect(self._andamento)
        self._tarefa.concluido.connect(self._varredura_terminou)
        self._caixa_progresso.setVisible(True)
        self._barra.setRange(0, 0)
        self._rot_progresso.setText("Percorrendo a origem…")
        self._atualizar_estado(varrendo=True)
        self.status_msg.emit(f"Varrendo {origem}…")
        self._tarefa.start()

    def _andamento(self, p: core.Progresso):
        if p.total:
            self._barra.setRange(0, p.total)
            self._barra.setValue(p.atual)
            self._rot_progresso.setText(
                f"{p.fase} {p.atual}/{p.total} — {p.arquivo[-60:]}")
        else:
            self._barra.setRange(0, 0)
            self._rot_progresso.setText(f"{p.fase}: {p.atual} arquivos…")

    def _cancelar_varredura(self):
        if self._tarefa and self._tarefa.isRunning():
            self._rot_progresso.setText("Encerrando…")
            self._tarefa.cancelar()

    def _varredura_terminou(self, resumo, erro: str):
        self._caixa_progresso.setVisible(False)
        self._tarefa = None
        if erro:
            QMessageBox.critical(self, "Falha na varredura", erro)
            self._atualizar_estado()
            return
        parcial = resumo.get("cancelado")
        self.status_msg.emit(
            f"{resumo['lidos']} arquivos indexados"
            + (" (varredura interrompida)" if parcial else ""))
        if parcial:
            QMessageBox.warning(
                self, "Varredura interrompida",
                f"A varredura foi interrompida com {resumo['lidos']} de "
                f"{resumo['total']} arquivos indexados. O índice é "
                f"parcial — o termo não deve ser emitido a partir dele "
                f"sem essa ressalva.")
        self._atualizar_estado()
        self._buscar()
        self._carregar_galeria()
        self._carregar_duplicatas()
        self._carregar_panorama()
        self._trocar_aba(0)

    def _abrir_indice(self):
        PASTA_PADRAO.mkdir(parents=True, exist_ok=True)
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Abrir índice de varredura", str(PASTA_PADRAO),
            f"Índice de varredura (*{core.SUFIXO});;Todos os arquivos (*)")
        if not caminho:
            return
        self._fechar_indice()
        try:
            self._indice = core.abrir(caminho)
        except Exception as e:                          # noqa: BLE001
            QMessageBox.critical(self, "Não foi possível abrir", str(e))
            self._indice = None
            self._atualizar_estado()
            return
        self._marcados.clear()
        self._registros.clear()
        self._atualizar_estado()
        self._buscar()
        self._carregar_galeria()
        self._carregar_duplicatas()
        self._carregar_panorama()

    def _fechar_indice(self):
        if self._indice is not None:
            self._indice.fechar()
            self._indice = None

    # ── estado da tela ───────────────────────────
    def _atualizar_estado(self, varrendo: bool = False):
        tem = self._indice is not None and not varrendo
        for w in (self._e_busca, self._b_registrar, self._b_termo,
                  self._f_texto, self._f_ocr, self._f_gps):
            w.setEnabled(tem)
        for caixa in self._caixas_categoria.values():
            caixa.setEnabled(tem)

        if self._indice is None:
            self._rot_origem.setText("Nenhum acervo carregado.")
            self._rot_contagem.setText("")
            return

        p = self._indice.panorama()
        v = core.informacao_volume(self._indice.raiz)
        linhas = [f"<b>{Path(self._indice.raiz).name or self._indice.raiz}</b>",
                  f"<span style='color:{PALETTE['text3']};'>"
                  f"{self._indice.raiz}</span>"]
        if v.get("rotulo") or v.get("serie"):
            linhas.append(f"Volume {v.get('rotulo') or '—'} · "
                          f"série {v.get('serie') or '—'}")
        linhas.append(f"{p['total']} arquivos · "
                      f"{core.formatar_tamanho(p['bytes'] or 0)}")
        quando = self._indice.anotacao("quando").replace("T", " às ")
        if quando:
            linhas.append(f"Varrido em {quando}")
        self._rot_origem.setText("<br/>".join(linhas))

        # Só aparecem as categorias que o acervo de fato tem.
        presentes = {c for c, _n, _b in p["por_categoria"]}
        for nome, caixa in self._caixas_categoria.items():
            caixa.setVisible(nome in presentes)
        self._atualizar_rodape()

    def _atualizar_rodape(self):
        partes = []
        if self._registros:
            partes.append(f"{len(self._registros)} pesquisa(s) registrada(s)")
        if self._marcados:
            partes.append(f"{len(self._marcados)} arquivo(s) destacado(s)")
        self._rot_registros.setText(" · ".join(partes))

    def _trocar_aba(self, indice: int):
        self._paginas.setCurrentIndex(indice)
        botao = self._grupo_abas.button(indice)
        if botao:
            botao.setChecked(True)

    def _limpar_filtros(self):
        for caixa in list(self._caixas_categoria.values()) + [
                self._f_texto, self._f_ocr, self._f_gps]:
            caixa.blockSignals(True)
            caixa.setChecked(False)
            caixa.blockSignals(False)
        self._buscar()

    def _filtros(self) -> core.Filtros:
        return core.Filtros(
            categorias={n for n, c in self._caixas_categoria.items()
                        if c.isChecked()},
            so_com_texto=self._f_texto.isChecked(),
            so_ocr=self._f_ocr.isChecked(),
            so_com_gps=self._f_gps.isChecked())

    def _descricao_recorte(self) -> str:
        f = self._filtros()
        partes = []
        if f.categorias:
            partes.append("natureza: " + ", ".join(sorted(f.categorias)))
        if f.so_com_texto:
            partes.append("somente arquivos com texto extraído")
        if f.so_ocr:
            partes.append("somente texto obtido por OCR")
        if f.so_com_gps:
            partes.append("somente arquivos com coordenadas")
        return "; ".join(partes)

    # ── busca ────────────────────────────────────
    def _buscar(self):
        if self._indice is None:
            return
        consulta = self._e_busca.text()
        filtros = self._filtros()
        try:
            self._achados = self._indice.buscar(consulta, filtros)
            total = self._indice.contar(consulta, filtros)
        except ValueError as e:
            self._rot_contagem.setText(str(e))
            return

        self._arvore.blockSignals(True)
        self._arvore.clear()
        for a in self._achados:
            item = QTreeWidgetItem([
                a.nome, "", core.formatar_tamanho(a.tamanho),
                core.data_br(a.modificado),
                core.ROTULO_ORIGEM.get(a.origem, a.origem)])
            item.setData(0, Qt.ItemDataRole.UserRole, a.id)
            item.setData(1, DelegadoTrecho.PAPEL, _html_trecho(a))
            item.setToolTip(0, a.caminho)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                0, Qt.CheckState.Checked if a.id in self._marcados
                else Qt.CheckState.Unchecked)
            if a.erro:
                item.setForeground(0, QColor(PALETTE["danger"]))
                item.setToolTip(4, a.erro)
            self._arvore.addTopLevelItem(item)
        self._arvore.blockSignals(False)

        mostrados = len(self._achados)
        texto = f"{total} arquivo(s)"
        if mostrados < total:
            texto += f" — exibindo os {mostrados} mais relevantes"
        if self._marcados:
            texto += f" · {len(self._marcados)} destacado(s)"
        self._rot_contagem.setText(texto)
        self._trocar_aba(0)

    def _registrar_busca(self):
        if self._indice is None:
            return
        consulta = self._e_busca.text().strip()
        if not consulta:
            QMessageBox.information(
                self, "Nada a registrar",
                "Digite a expressão pesquisada antes de registrá-la. O "
                "termo relaciona as pesquisas feitas, não o acervo inteiro.")
            return
        total = self._indice.contar(consulta, self._filtros())
        escolhidos = self._achados_selecionados() or self._achados[:25]
        self._registros.append(core.Registro(
            consulta=consulta, recorte=self._descricao_recorte(),
            total=total, achados=escolhidos))
        self._atualizar_rodape()
        self.status_msg.emit(
            f"Pesquisa “{consulta}” registrada no termo "
            f"({total} resultado(s)).")

    def _achados_selecionados(self) -> list[core.Achado]:
        por_id = {a.id: a for a in self._achados}
        return [por_id[i] for i in
                (it.data(0, Qt.ItemDataRole.UserRole)
                 for it in self._arvore.selectedItems())
                if i in por_id]

    # ── galeria, duplicatas, panorama ────────────
    def _carregar_galeria(self):
        self._galeria.clear()
        if self._indice is None:
            return
        for a in self._indice.imagens():
            bruto = self._indice.miniatura(a.id)
            mapa = QPixmap()
            if bruto:
                mapa.loadFromData(bruto)
            item = QListWidgetItem(QIcon(mapa), a.nome)
            item.setData(Qt.ItemDataRole.UserRole, a.id)
            dica = [a.caminho, core.formatar_tamanho(a.tamanho),
                    core.data_br(a.modificado)]
            if a.gps:
                dica.append(f"Coordenadas: {a.gps}")
            item.setToolTip("\n".join(dica))
            if a.gps:
                item.setForeground(QColor(PALETTE["gold"]))
            self._galeria.addItem(item)

    def _carregar_duplicatas(self):
        self._dupes.clear()
        if self._indice is None:
            return
        grupos = self._indice.duplicatas()
        for grupo in grupos:
            desperdicio = grupo[0].tamanho * (len(grupo) - 1)
            pai = QTreeWidgetItem([
                f"{len(grupo)} cópias idênticas",
                core.formatar_tamanho(grupo[0].tamanho),
                grupo[0].sha256])
            pai.setToolTip(1, f"{core.formatar_tamanho(desperdicio)} "
                              f"em repetição")
            for a in grupo:
                filho = QTreeWidgetItem([a.caminho, "", ""])
                filho.setData(0, Qt.ItemDataRole.UserRole, a.id)
                pai.addChild(filho)
            self._dupes.addTopLevelItem(pai)
            pai.setExpanded(True)
        if not grupos:
            self._dupes.addTopLevelItem(
                QTreeWidgetItem(["Nenhum arquivo repetido no acervo.", "", ""]))

    def _carregar_panorama(self):
        if self._indice is None:
            self._panorama.clear()
            return
        p = self._indice.panorama()
        e = self._indice.anotacao
        tinta = PALETTE["text"]
        fraco = PALETTE["text3"]

        def quadro(titulo, linhas):
            corpo = "".join(
                f"<tr><td style='padding:3px 14px 3px 0;'>{r}</td>"
                f"<td style='padding:3px 0; color:{tinta};'>{v}</td></tr>"
                for r, v in linhas)
            return (f"<p style='color:{PALETTE['gold']}; font-weight:700;'>"
                    f"{titulo}</p><table>{corpo}</table>")

        blocos = [quadro("Acervo", [
            ("Origem", e("raiz")),
            ("Varrido em", e("quando").replace("T", " às ")),
            ("Arquivos", f"{p['total']}"),
            ("Volume", core.formatar_tamanho(p["bytes"] or 0)),
            ("Com texto indexado", f"{p['com_texto']}"),
            ("Lidos por OCR", f"{p['ocr']} "
                              f"({p['ocr_paginas']} páginas ou imagens)"),
            ("Com coordenadas", f"{p['com_gps']}"),
            ("Duplicados", f"{p['duplicados']}"),
            ("Falhas de leitura", f"{p['falhas']}"),
            ("Período dos arquivos",
             f"{core.data_br(p['primeiro'])} a {core.data_br(p['ultimo'])}"),
        ])]
        blocos.append(quadro("Por natureza", [
            (cat, f"{n} · {core.formatar_tamanho(b or 0)}")
            for cat, n, b in p["por_categoria"]]))
        blocos.append(quadro("Extensões mais frequentes", [
            (ext, f"{n}") for ext, n in p["extensoes"][:12]]))
        blocos.append(quadro("Maiores arquivos", [
            (a.caminho, core.formatar_tamanho(a.tamanho))
            for a in p["maiores"][:10]]))
        blocos.append(
            f"<p style='color:{fraco}; margin-top:18px;'>"
            f"Resumo criptográfico do conjunto:<br/>"
            f"<span style='font-family:Consolas,monospace; color:{tinta};'>"
            f"{e('hash_conjunto')}</span></p>")
        self._panorama.setHtml(
            f"<div style='color:{fraco}; font-family:Segoe UI;'>"
            + "".join(blocos) + "</div>")

    # ── detalhe ──────────────────────────────────
    def _achado_por_id(self, ident) -> core.Achado | None:
        if self._indice is None or ident is None:
            return None
        return self._indice.arquivo(int(ident))

    def _mostrar_detalhe(self, item, _anterior=None):
        if item is None:
            return
        self._detalhar(self._achado_por_id(
            item.data(0, Qt.ItemDataRole.UserRole)))

    def _detalhe_da_galeria(self, item, _anterior=None):
        if item is None:
            return
        self._detalhar(self._achado_por_id(
            item.data(Qt.ItemDataRole.UserRole)))

    def _detalhe_da_duplicata(self, item, _anterior=None):
        if item is None:
            return
        self._detalhar(self._achado_por_id(
            item.data(0, Qt.ItemDataRole.UserRole)))

    def _detalhar(self, achado: core.Achado | None):
        self._selecionado = achado
        if achado is None or self._indice is None:
            self._rot_detalhe.setText("Selecione um arquivo.")
            self._corpo_detalhe.clear()
            self._miniatura.setVisible(False)
            self._b_marcar.setChecked(False)
            return

        self._rot_detalhe.setText(f"<b>{achado.nome}</b><br/>"
                                  f"<span style='color:{PALETTE['text3']};'>"
                                  f"{achado.caminho}</span>")
        bruto = self._indice.miniatura(achado.id)
        if bruto:
            mapa = QPixmap()
            mapa.loadFromData(bruto)
            self._miniatura.setPixmap(mapa.scaledToWidth(
                290, Qt.TransformationMode.SmoothTransformation))
            self._miniatura.setVisible(True)
        else:
            self._miniatura.setVisible(False)

        tinta = PALETTE["text"]
        fraco = PALETTE["text3"]
        linhas = [
            ("Tamanho", core.formatar_tamanho(achado.tamanho)),
            ("Alterado", core.data_br(achado.modificado)),
            ("Natureza", achado.categoria),
            ("Texto", core.ROTULO_ORIGEM.get(achado.origem, achado.origem)
             + (f" · {achado.caracteres} caracteres"
                if achado.caracteres else "")),
        ]
        if achado.erro:
            linhas.append(("Falha", achado.erro))
        for rotulo, valor, _grupo, relevante in self._indice.metadados(achado.id):
            linhas.append((rotulo, f"<b>{valor}</b>" if relevante else valor))

        corpo = "".join(
            f"<tr><td style='padding:2px 10px 2px 0; color:{fraco};"
            f" vertical-align:top;'>{r}</td>"
            f"<td style='padding:2px 0; color:{tinta};'>{v}</td></tr>"
            for r, v in linhas)
        html = (f"<div style='font-family:Segoe UI; font-size:9pt;'>"
                f"<table>{corpo}</table>"
                f"<p style='color:{fraco}; margin-top:10px;'>SHA-256</p>"
                f"<p style='font-family:Consolas,monospace; font-size:8pt; "
                f"color:{tinta}; word-wrap:break-word;'>{achado.sha256}</p>")

        texto = self._indice.texto_de(achado.id)
        if texto:
            import html as _h
            html += (f"<p style='color:{fraco}; margin-top:10px;'>"
                     f"Texto extraído</p>"
                     f"<p style='color:{tinta}; white-space:pre-wrap;'>"
                     f"{_h.escape(texto[:4000])}"
                     f"{'…' if len(texto) > 4000 else ''}</p>")
        self._corpo_detalhe.setHtml(html + "</div>")
        self._b_marcar.setChecked(achado.id in self._marcados)

    # ── marcação ─────────────────────────────────
    def _alternar_marca(self, item, coluna):
        if coluna != 0:
            return
        ident = item.data(0, Qt.ItemDataRole.UserRole)
        achado = self._achado_por_id(ident)
        if achado is None:
            return
        if item.checkState(0) == Qt.CheckState.Checked:
            self._marcados[achado.id] = achado
        else:
            self._marcados.pop(achado.id, None)
        if self._selecionado and self._selecionado.id == achado.id:
            self._b_marcar.setChecked(achado.id in self._marcados)
        self._atualizar_rodape()

    def _marcar_selecionado(self):
        if self._selecionado is None:
            self._b_marcar.setChecked(False)
            return
        ident = self._selecionado.id
        if self._b_marcar.isChecked():
            self._marcados[ident] = self._selecionado
        else:
            self._marcados.pop(ident, None)
        # O bloqueio é da árvore, não do item: QTreeWidgetItem não é
        # QObject e não tem sinais próprios. Sem isso, mudar a marca aqui
        # dispararia `itemChanged`, que reentraria em `_alternar_marca`.
        self._arvore.blockSignals(True)
        try:
            for i in range(self._arvore.topLevelItemCount()):
                item = self._arvore.topLevelItem(i)
                if item.data(0, Qt.ItemDataRole.UserRole) == ident:
                    item.setCheckState(
                        0, Qt.CheckState.Checked if self._b_marcar.isChecked()
                        else Qt.CheckState.Unchecked)
                    break
        finally:
            self._arvore.blockSignals(False)
        self._atualizar_rodape()

    # ── ações sobre o arquivo ────────────────────
    def _caminho_absoluto(self) -> Path | None:
        if self._selecionado is None or self._indice is None:
            return None
        return Path(self._indice.raiz) / self._selecionado.caminho

    def _abrir_arquivo(self):
        alvo = self._caminho_absoluto()
        if alvo is None:
            return
        if not alvo.exists():
            QMessageBox.information(
                self, "Arquivo indisponível",
                f"O arquivo não está acessível em:\n{alvo}\n\n"
                f"O índice continua consultável, mas abrir o arquivo exige "
                f"que a origem esteja conectada.")
            return
        try:
            os.startfile(str(alvo))                     # noqa: S606
        except OSError as e:
            QMessageBox.warning(self, "Não foi possível abrir", str(e))

    def _abrir_pasta(self):
        alvo = self._caminho_absoluto()
        if alvo is None:
            return
        try:
            if alvo.exists():
                subprocess.Popen(["explorer", "/select,", str(alvo)])
            else:
                QMessageBox.information(
                    self, "Pasta indisponível",
                    f"A origem não está acessível em:\n{alvo.parent}")
        except OSError as e:
            QMessageBox.warning(self, "Não foi possível abrir", str(e))

    def _copiar_hash(self):
        if self._selecionado is None:
            return
        QGuiApplication.clipboard().setText(self._selecionado.sha256)
        self.status_msg.emit("SHA-256 copiado.")

    # ── termo ────────────────────────────────────
    def _gerar_termo(self):
        if self._indice is None:
            return
        e = self._indice.anotacao
        termo = core.TermoVarredura(
            origem=self._indice.raiz,
            volume=core.informacao_volume(self._indice.raiz),
            somente_leitura=bool(int(e("somente_leitura", "0") or 0)),
            quando_varreu=e("quando").replace("T", " às "),
            hash_conjunto=e("hash_conjunto"),
            ajustes=[e(f"ajuste_{i}") for i in range(4) if e(f"ajuste_{i}")],
            panorama=self._indice.panorama(),
            registros=list(self._registros),
            marcados=list(self._marcados.values()))
        TermoDialog(termo, self).exec()

    # ── ciclo de vida ────────────────────────────
    def can_close(self) -> bool:
        if self._tarefa and self._tarefa.isRunning():
            resposta = QMessageBox.question(
                self, "Varredura em andamento",
                "Há uma varredura em curso. Encerrar agora deixa o índice "
                "incompleto. Deseja encerrar mesmo assim?")
            if resposta != QMessageBox.StandardButton.Yes:
                return False
        return True

    def shutdown(self):
        if self._tarefa and self._tarefa.isRunning():
            self._tarefa.cancelar()
            self._tarefa.wait(4000)
        self._fechar_indice()
