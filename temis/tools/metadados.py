"""
Metadados e Hash — o que o arquivo informa sobre si, e o que o identifica.

Reúne duas coisas que sempre andaram juntas na prática: o resumo
criptográfico que amarra o arquivo aos autos e os metadados que ele
carrega por dentro. Sai um documento só, que abre como termo de juntada —
é o que lhe dá valor de peça — e, conforme o modo, traz em seguida os
quadros de metadados.

Segue a disposição do Anti-Injection: painel à esquerda com a lista do que
foi aberto, barra de modos no alto, e o termo saindo pelo botão verde do
rodapé.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QDate, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QFrame, QSizePolicy, QMessageBox, QDialog, QTextEdit, QButtonGroup,
    QListWidget, QListWidgetItem, QProgressDialog, QLineEdit, QGridLayout,
    QDateEdit,
)

from .. import perfil
from ..icons import draw_icon
from ..impressao import (documento_html, imprimir_documento,
                         limpar_para_sei, preparar_escritor)
from ..theme import PALETTE
from ..widgets import (
    NoScrollComboBox, SidebarPanel, ViewerToolbar, field_label,
    fit_to_screen, hsep, output_button, primary_button, subtext,
)
from .base import ToolPage, ToolMeta
from . import metadados_core as core


META = ToolMeta(
    key="metadados",
    name="Metadados e Hash",
    icon="tool_metadados",
    tagline="Identifica o arquivo e o que ele carrega",
    description=(
        "Calcula o SHA-256 dos arquivos e lê o que eles informam sobre si: "
        "autor, programa que gerou, datas de criação e alteração, "
        "equipamento de origem e, quando o aparelho as gravou, as "
        "coordenadas da captura. Emite um termo único — juntada e "
        "metadados na mesma peça —, com coluna de nº SEI e assinatura do "
        "servidor."
    ),
)

#: Formatos oferecidos no seletor de arquivos.
FILTRO = (
    "Todos os suportados (*.pdf *.jpg *.jpeg *.png *.tif *.tiff *.webp "
    "*.heic *.bmp *.gif *.docx *.xlsx *.pptx *.odt *.ods *.odp *.mp4 *.mov "
    "*.avi *.mkv *.wmv *.m4v *.mp3 *.wav *.m4a *.aac *.ogg *.flac *.webm);;"
    "Documentos (*.pdf *.docx *.xlsx *.pptx *.odt *.ods *.odp);;"
    "Imagens (*.jpg *.jpeg *.png *.tif *.tiff *.webp *.heic *.bmp *.gif);;"
    "Mídias (*.mp4 *.mov *.avi *.mkv *.wmv *.m4v *.mp3 *.wav *.m4a *.aac "
    "*.ogg *.flac *.webm);;"
    "Todos os arquivos (*)"
)

TINTA = core.INK
CINZA = core.CINZA


# ─────────────────────────────────────────
#  LEITURA EM SEGUNDO PLANO
# ─────────────────────────────────────────

class ExtrairThread(QThread):
    """Lê o lote fora da interface: o SHA-256 de um vídeo demora."""

    progresso = pyqtSignal(int, int)
    pronto = pyqtSignal(list)

    def __init__(self, caminhos: list[str], avancado: bool = False):
        super().__init__()
        self._caminhos = caminhos
        self._avancado = avancado

    def run(self):
        self.pronto.emit(core.extrair_varios(
            self._caminhos, avancado=self._avancado,
            progresso=lambda i, t: self.progresso.emit(i, t)))


# ─────────────────────────────────────────
#  TERMO DE DILIGÊNCIA
# ─────────────────────────────────────────

class TermoDialog(QDialog):
    """Documento pronto para os autos, editável antes de salvar."""

    def __init__(self, arquivos: list[core.Arquivo], quando: str,
                 modo: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Termo de Juntada e Extração de Metadados")
        self._arquivos = arquivos
        self._quando = quando
        self._modo = modo
        fit_to_screen(self, 940, 800)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        titulo = QLabel("Termo de Juntada")
        titulo.setObjectName("heading")
        layout.addWidget(titulo)
        layout.addWidget(subtext(
            "Os campos abaixo montam a abertura do termo. Confira e ajuste "
            "o texto antes de salvar — o documento sai em PDF, pronto para "
            "juntada.", wrap=True))
        layout.addWidget(self._build_form())
        layout.addWidget(hsep())

        self._view = QTextEdit()
        self._view.setStyleSheet(
            "QTextEdit { background: #FFFFFF; color: #16233A; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; "
            "padding: 26px; }")
        layout.addWidget(self._view, 1)
        layout.addWidget(hsep())

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

        layout.addWidget(acoes)
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

    def _build_form(self) -> QWidget:
        caixa = QWidget()
        grade = QGridLayout(caixa)
        grade.setContentsMargins(0, 4, 0, 4)
        grade.setHorizontalSpacing(10)
        grade.setVerticalSpacing(4)

        self._in_nome = QLineEdit()
        self._in_nome.setPlaceholderText("Ex.: João da Silva")
        self._in_matricula = QLineEdit()
        self._in_matricula.setPlaceholderText("Ex.: 1234567")
        self._in_lotacao = QLineEdit()
        self._in_lotacao.setPlaceholderText("Ex.: CGCOR - PRF/DF")

        for coluna, (rotulo, campo) in enumerate((
            ("Nome do servidor", self._in_nome),
            ("Matrícula", self._in_matricula),
            ("Lotação", self._in_lotacao),
        )):
            grade.addWidget(field_label(rotulo), 0, coluna)
            grade.addWidget(campo, 1, coluna)
            campo.textChanged.connect(self._remontar)

        # Segunda fileira: o vínculo aos autos e a data por extenso. Sem
        # eles o texto não passa de relatório técnico.
        self._cb_tipo = NoScrollComboBox()
        for t in ("IPS", "PAD"):
            self._cb_tipo.addItem(t)
        self._cb_tipo.currentIndexChanged.connect(self._remontar)
        self._in_processo = QLineEdit()
        self._in_processo.setPlaceholderText("Ex.: 08650.000123/2026-11")
        self._in_processo.textChanged.connect(self._remontar)
        self._data = QDateEdit()
        self._data.setCalendarPopup(True)
        self._data.setDisplayFormat("dd/MM/yyyy")
        self._data.setDate(QDate.currentDate())
        self._data.dateChanged.connect(self._remontar)

        for coluna, (rotulo, campo) in enumerate((
            ("Procedimento", self._cb_tipo),
            ("Número do processo", self._in_processo),
            ("Data do termo", self._data),
        )):
            grade.addWidget(field_label(rotulo), 2, coluna)
            grade.addWidget(campo, 3, coluna)

        # Terceira fileira: como o material chegou. Fica junto do vínculo
        # aos autos porque é da mesma natureza — o que amarra a peça ao
        # que veio de fora dela. Tudo opcional: campo vazio não sai
        # impresso, e rótulo genérico preenchido para cumprir formulário
        # é pior do que silêncio.
        self._in_recebido_de = QLineEdit()
        self._in_recebido_de.setPlaceholderText("Ex.: Setor de Inteligência")
        self._in_recebido_de.textChanged.connect(self._remontar)
        self._cb_meio = NoScrollComboBox()
        self._cb_meio.setEditable(True)
        self._cb_meio.addItems(
            ["", "ofício nº ", "mídia lacrada nº ", "download do sistema ",
             "mensagem eletrônica de ", "entrega pessoal"])
        self._cb_meio.setToolTip(
            "Como o material chegou. As opções são começos de frase — "
            "complete com o número ou o nome que identifica a entrega.")
        self._cb_meio.editTextChanged.connect(self._remontar)
        self._in_recebido_em = QLineEdit()
        self._in_recebido_em.setPlaceholderText("Ex.: 26/08/2026, às 15h")
        self._in_recebido_em.setToolTip(
            "Quando o material foi recebido — que é anterior à leitura "
            "nesta estação, e por isso se digita em vez de ser medido")
        self._in_recebido_em.textChanged.connect(self._remontar)

        for coluna, (rotulo, campo) in enumerate((
            ("Recebido de", self._in_recebido_de),
            ("Por qual meio", self._cb_meio),
            ("Recebido em", self._in_recebido_em),
        )):
            grade.addWidget(field_label(rotulo), 4, coluna)
            grade.addWidget(campo, 5, coluna)

        grade.setColumnStretch(0, 3)
        grade.setColumnStretch(1, 1)
        grade.setColumnStretch(2, 2)
        grade.setRowMinimumHeight(2, 12)
        grade.setRowMinimumHeight(4, 12)
        return caixa

    # ── documento ────────────────────────────────
    def _declarante(self) -> core.Declarante:
        return core.Declarante(
            nome=self._in_nome.text().strip(),
            matricula=self._in_matricula.text().strip(),
            lotacao=self._in_lotacao.text().strip(),
        )

    def _juntada(self) -> core.Juntada:
        d = self._data.date()
        return core.Juntada(
            tipo_processo=self._cb_tipo.currentText(),
            numero_processo=self._in_processo.text().strip(),
            dia=d.day(), mes=d.month(), ano=d.year(),
            recebido_de=self._in_recebido_de.text().strip(),
            meio_entrega=self._cb_meio.currentText().strip(),
            recebido_em=self._in_recebido_em.text().strip(),
        )

    def _remontar(self):
        self._view.setHtml(core.build_html(
            self._arquivos, self._quando, self._declarante(),
            self._modo, self._juntada()))

    def _copiar(self):
        QGuiApplication.clipboard().setText(self._view.toPlainText())
        self._aviso.setText("✓ Texto copiado")

    def _salvar_html(self):
        """Exporta o que está na tela, limpo para a importação do SEI."""
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo em HTML",
            f"termo-{self._base()}.html", "Página HTML (*.html)")
        if not caminho:
            return
        if not caminho.lower().endswith((".html", ".htm")):
            caminho += ".html"
        try:
            # Sai o documento em edição, e não o remontado: os ajustes de
            # redação feitos aqui têm de acompanhar o arquivo exportado.
            corpo = limpar_para_sei(self._view.toHtml())
            Path(caminho).write_text(
                documento_html(corpo, "Termo de Juntada e Extração de "
                                      "Metadados"),
                encoding="utf-8")
            self._aviso.setText("✓ HTML salvo")
        except OSError as e:
            QMessageBox.critical(self, "Erro ao salvar",
                                 f"Não foi possível gravar o arquivo:\n{e}")

    def _base(self) -> str:
        return (Path(self._arquivos[0].caminho).stem
                if self._arquivos else "arquivos")

    def _salvar_pdf(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo",
            f"termo-{self._base()}.pdf", "Arquivos PDF (*.pdf)")
        if not caminho:
            return
        if not caminho.lower().endswith(".pdf"):
            caminho += ".pdf"
        try:
            escritor = preparar_escritor(
                caminho, "Termo de Juntada e Extração de Metadados")
            # Clona o documento em edição: remontar a partir dos dados
            # descartaria em silêncio os ajustes feitos na tela.
            doc = self._view.document().clone()
            doc.setDefaultFont(QFont("Segoe UI", 10))
            imprimir_documento(doc, escritor)
            self._aviso.setText("✓ PDF salvo")
        except Exception as e:                          # noqa: BLE001
            QMessageBox.critical(self, "Erro ao salvar",
                                 f"Não foi possível gerar o PDF:\n{e}")


# ─────────────────────────────────────────
#  FERRAMENTA
# ─────────────────────────────────────────

class MetadadosTool(ToolPage):
    meta = META

    MODOS = (core.SO_HASH, core.RELEVANTES, core.COMPLETO, core.AVANCADO)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._arquivos: list[core.Arquivo] = []
        self._modo = core.RELEVANTES
        self._thread: ExtrairThread | None = None
        self._build_ui()

    # ── montagem ─────────────────────────────────
    def _build_ui(self):
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self._build_sidebar())

        principal = QWidget()
        coluna = QVBoxLayout(principal)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(0)
        coluna.addWidget(self._build_toolbar())
        coluna.addWidget(self._build_alerta())

        self._view = QTextEdit()
        self._view.setReadOnly(True)
        self._view.setStyleSheet(
            "QTextEdit { background: #FFFFFF; color: #16233A; "
            f"border: none; padding: 30px 38px; }}")
        coluna.addWidget(self._view, 1)

        raiz.addWidget(principal, 1)
        self._boas_vindas()

    def _build_toolbar(self) -> ViewerToolbar:
        barra = ViewerToolbar(paginacao=False, zoom=False)

        dica = QLabel("Termo:")
        dica.setObjectName("subtext")
        barra.add_widget(dica)

        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)
        self._botoes_modo = {}
        for chave in self.MODOS:
            b = QPushButton(core.MODOS[chave])
            b.setCheckable(True)
            b.setChecked(chave == self._modo)
            b.setMinimumWidth(92)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip({
                core.SO_HASH: "Termo de juntada puro: nome, tamanho, "
                              "hash e nº SEI, sem os quadros de metadados",
                core.RELEVANTES: "Juntada mais o que costuma interessar à "
                                 "apuração: pessoas, equipamento, datas e "
                                 "local",
                core.COMPLETO: "Juntada mais todos os metadados lidos",
                core.AVANCADO: "Procura o que a leitura comum não mostra: "
                               "fluxos alternativos do sistema de arquivos, "
                               "revisões preservadas dentro do documento, "
                               "propriedades ocultas e dados anexados após "
                               "o fim do formato",
            }[chave])
            b.clicked.connect(lambda _c, n=chave: self._definir_modo(n))
            self._grupo.addButton(b)
            self._botoes_modo[chave] = b
            barra.add_widget(b)

        barra.add_separator()

        self._btn_copiar = QPushButton("  Copiar")
        self._btn_copiar.setIcon(draw_icon("note", 15, PALETTE["text"]))
        self._btn_copiar.setToolTip("Copia os metadados deste arquivo")
        self._btn_copiar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_copiar.clicked.connect(self._copiar)
        barra.add_widget(self._btn_copiar)

        barra.add_stretch()
        return barra

    def _build_alerta(self) -> QFrame:
        self._alerta = QFrame()
        self._alerta.setFixedHeight(34)
        self._alerta.setStyleSheet(
            f"background: {PALETTE['surface2']}; "
            f"border-bottom: 1px solid {PALETTE['border']};")
        lay = QHBoxLayout(self._alerta)
        lay.setContentsMargins(16, 0, 16, 0)
        self._lbl_alerta = QLabel("")
        lay.addWidget(self._lbl_alerta)
        lay.addStretch()
        self._alerta.setVisible(False)
        return self._alerta

    def _build_sidebar(self) -> SidebarPanel:
        painel = SidebarPanel()

        self._btn_abrir = primary_button("Abrir arquivos…", "plus")
        self._btn_abrir.clicked.connect(self._abrir)
        painel.header.addWidget(self._btn_abrir)

        self._lbl_estado = subtext("Nenhum arquivo aberto", wrap=True)
        painel.header.addWidget(self._lbl_estado)

        linha = QHBoxLayout()
        titulo = QLabel("Arquivos")
        titulo.setObjectName("heading")
        linha.addWidget(titulo)
        linha.addStretch()
        self._lbl_contagem = subtext("—")
        linha.addWidget(self._lbl_contagem)
        painel.body.addLayout(linha)

        self._lista = QListWidget()
        self._lista.setWordWrap(True)
        self._lista.setStyleSheet(
            f"QListWidget {{ background: {PALETTE['bg']}; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; }}"
            f"QListWidget::item {{ padding: 9px 10px; "
            f"border-bottom: 1px solid {PALETTE['surface2']}; }}")
        self._lista.currentRowChanged.connect(self._mostrar)
        painel.body.addWidget(self._lista, 1)

        # O nº SEI é por arquivo, e é ele que amarra a peça aos autos.
        # Fica junto da lista, e não numa tabela à parte, para que se veja
        # de imediato a qual arquivo pertence.
        painel.body.addWidget(field_label("Nº SEI deste arquivo"))
        self._in_sei = QLineEdit()
        self._in_sei.setPlaceholderText("Ex.: 28873450")
        self._in_sei.setToolTip(
            "Número do documento no SEI, que vai para a coluna do termo")
        self._in_sei.setEnabled(False)
        self._in_sei.textEdited.connect(self._anotar_sei)
        painel.body.addWidget(self._in_sei)

        # O resumo que veio declarado com o arquivo — do ofício que o
        # encaminhou, da mídia lacrada, do termo de quem o entregou. É o
        # que transforma gerar resumo em conferir resumo: sem um par a
        # confrontar, o hash prova apenas que o arquivo não mudou de
        # agora em diante, e nada sobre o que se recebeu.
        painel.body.addWidget(field_label("Resumo declarado na entrega"))
        self._in_declarado = QLineEdit()
        self._in_declarado.setPlaceholderText(
            "Cole o SHA-256 que veio com o arquivo — opcional")
        self._in_declarado.setToolTip(
            "Maiúsculas, espaços e dois-pontos são ignorados; pode-se "
            "colar a linha inteira de um sha256sum. Havendo resumo "
            "declarado, o termo passa a atestar a conferência.")
        self._in_declarado.setEnabled(False)
        self._in_declarado.textEdited.connect(self._anotar_declarado)
        painel.body.addWidget(self._in_declarado)

        self._lbl_confere = QLabel("")
        self._lbl_confere.setWordWrap(True)
        painel.body.addWidget(self._lbl_confere)

        acoes = QHBoxLayout()
        self._btn_remover = QPushButton("  Remover")
        self._btn_remover.setIcon(draw_icon("trash", 14, PALETTE["danger"]))
        self._btn_remover.setToolTip("Tira este arquivo da lista")
        self._btn_remover.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_remover.clicked.connect(self._remover)
        acoes.addWidget(self._btn_remover)
        self._btn_limpar = QPushButton("Limpar tudo")
        self._btn_limpar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_limpar.clicked.connect(self._limpar)
        acoes.addWidget(self._btn_limpar)
        painel.body.addLayout(acoes)

        self._btn_termo = output_button("Gerar termo")
        self._btn_termo.clicked.connect(self._mostrar_termo)
        self._btn_termo.setEnabled(False)
        painel.footer.addWidget(self._btn_termo)
        painel.add_note("Leitura 100% local. Os arquivos não são alterados.")
        return painel

    # ── abertura ─────────────────────────────────
    def _abrir(self):
        caminhos, _ = QFileDialog.getOpenFileNames(
            self, "Abrir arquivos para o termo", "", FILTRO)
        if caminhos:
            self.acrescentar(caminhos)

    def acrescentar(self, caminhos: list[str]):
        """Lê os arquivos e junta ao que já está na lista."""
        ja = {a.caminho for a in self._arquivos}
        novos = [c for c in caminhos if str(Path(c)) not in ja]
        if not novos:
            self.status_msg.emit("Estes arquivos já estão na lista.")
            return

        progresso = QProgressDialog("Lendo metadados…", "Cancelar", 0,
                                    len(novos), self)
        progresso.setWindowTitle("Extração")
        progresso.setMinimumDuration(400)
        progresso.setValue(0)

        self._thread = ExtrairThread(novos)
        self._thread.progresso.connect(
            lambda i, t: (progresso.setMaximum(t), progresso.setValue(i)))
        self._thread.pronto.connect(
            lambda lidos: self._ao_extrair(lidos, progresso))
        self._thread.start()

    def _ao_extrair(self, lidos: list[core.Arquivo],
                    progresso: QProgressDialog):
        progresso.close()
        self._arquivos.extend(lidos)
        self._preencher_lista()
        self._lista.setCurrentRow(len(self._arquivos) - len(lidos))
        self._btn_termo.setEnabled(bool(self._arquivos))
        com_local = sum(1 for a in self._arquivos if a.tem_localizacao)
        self.status_msg.emit(
            f"{len(lidos)} arquivo(s) lido(s)"
            + (f" · {com_local} com coordenadas" if com_local else ""))

    # ── lista ────────────────────────────────────
    def _preencher_lista(self):
        self._lista.blockSignals(True)
        atual = self._lista.currentRow()
        self._lista.clear()
        for a in self._arquivos:
            marca = "!" if a.tem_localizacao else ("×" if a.erro else "•")
            cor = (PALETTE["warning"] if a.tem_localizacao
                   else PALETTE["danger"] if a.erro else PALETTE["text2"])
            item = QListWidgetItem(f" {marca}  {a.nome}\n      {a.tipo} · "
                                   f"{len(a.relevantes)} de interesse")
            item.setForeground(QColor(cor))
            self._lista.addItem(item)
        self._lista.blockSignals(False)
        self._lbl_contagem.setText(f"{len(self._arquivos)}")
        self._lbl_estado.setText(
            f"{len(self._arquivos)} arquivo(s) na juntada"
            if self._arquivos else "Nenhum arquivo aberto")
        if 0 <= atual < self._lista.count():
            self._lista.setCurrentRow(atual)

    def _remover(self):
        i = self._lista.currentRow()
        if not (0 <= i < len(self._arquivos)):
            return
        self._arquivos.pop(i)
        self._preencher_lista()
        self._btn_termo.setEnabled(bool(self._arquivos))
        if self._arquivos:
            self._lista.setCurrentRow(min(i, len(self._arquivos) - 1))
        else:
            self._boas_vindas()

    def _limpar(self):
        if not self._arquivos:
            return
        if QMessageBox.question(
            self, "Limpar lista",
            "Tirar todos os arquivos da diligência?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._arquivos.clear()
        self._preencher_lista()
        self._btn_termo.setEnabled(False)
        self._boas_vindas()

    # ── exibição ─────────────────────────────────
    def _atual(self) -> core.Arquivo | None:
        i = self._lista.currentRow()
        return self._arquivos[i] if 0 <= i < len(self._arquivos) else None

    def _anotar_sei(self, texto: str):
        a = self._atual()
        if a is not None:
            a.sei = texto.strip()

    def _anotar_declarado(self, texto: str):
        a = self._atual()
        if a is not None:
            a.declarado = texto.strip()
        self._mostrar_conferencia(a)

    def _mostrar_conferencia(self, a):
        """O veredito ao lado do campo, enquanto se digita.

        Aparece aqui, e não só no termo, porque errar ao colar é comum e
        descobrir isso na peça pronta custa refazer tudo. Enquanto o que
        foi colado não tiver a forma de um SHA-256, a tela diz isso em
        vez de acusar divergência — resumo pela metade não diverge de
        coisa alguma, está apenas incompleto.
        """
        if a is None or not a.declarado.strip():
            self._lbl_confere.clear()
            return
        if not core.resumo_valido(a.declarado):
            faltam = core.TAMANHO_SHA256 - len(
                core.normalizar_resumo(a.declarado))
            self._lbl_confere.setText(
                f"<font color='{PALETTE['text3']}'>Resumo incompleto — "
                f"{'faltam ' + str(faltam) if faltam > 0 else 'excedem ' + str(-faltam)}"
                " caractere(s) para um SHA-256.</font>")
            return
        confere = a.confere
        if confere is None:
            self._lbl_confere.setText(
                f"<font color='{PALETTE['text3']}'>O resumo do arquivo "
                "ainda não foi calculado.</font>")
        elif confere:
            self._lbl_confere.setText(
                f"<b><font color='{PALETTE['success']}'>CONFERE</font></b> — "
                "o arquivo é o mesmo a que se refere o resumo declarado.")
        else:
            self._lbl_confere.setText(
                f"<b><font color='{PALETTE['danger']}'>NÃO CONFERE</font></b>"
                " — o arquivo recebido não é o mesmo a que se refere o "
                "resumo declarado.")

    def _definir_modo(self, nome: str):
        self._modo = nome
        for chave, b in self._botoes_modo.items():
            b.setChecked(chave == nome)
        if nome == core.AVANCADO:
            self._examinar_pendentes()
        self._mostrar(self._lista.currentRow())

    def _examinar_pendentes(self):
        """Roda o exame avançado nos arquivos que ainda não passaram.

        Não se faz na leitura inicial de propósito: o exame percorre o
        arquivo atrás de fluxos alternativos, revisões e cauda anexada, e
        cobrar esse tempo de quem só quer o termo de juntada seria trocar
        a espera de todos pela conveniência de alguns.
        """
        pendentes = [a for a in self._arquivos if a.analise is None]
        if not pendentes:
            return
        from . import metadados_avancado
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for a in pendentes:
                try:
                    a.analise = metadados_avancado.analisar(a.caminho)
                except Exception as e:                  # noqa: BLE001
                    a.analise = metadados_avancado.Analise(
                        caminho=a.caminho,
                        erros=[f"{type(e).__name__}: {e}"])
        finally:
            QGuiApplication.restoreOverrideCursor()
        achados = sum(len(a.analise.achados) for a in self._arquivos
                      if a.analise is not None)
        relevantes = sum(
            a.analise.quantos(metadados_avancado.ALERTA)
            for a in self._arquivos if a.analise is not None)
        self.status_msg.emit(
            f"Exame avançado concluído: {achados} achado(s), "
            f"{relevantes} de maior relevância."
            if achados else
            "Exame avançado concluído: nada além dos metadados já lidos.")

    def _mostrar(self, _linha: int = -1):
        a = self._atual()
        self._in_sei.setEnabled(a is not None)
        self._in_sei.setText(a.sei if a is not None else "")
        self._in_declarado.setEnabled(a is not None)
        self._in_declarado.setText(a.declarado if a is not None else "")
        self._mostrar_conferencia(a)
        if a is None:
            self._boas_vindas()
            return
        self._view.setHtml(self._html(a))
        self._atualizar_alerta(a)

    def _html_avancado(self, a: core.Arquivo) -> str:
        """O painel do exame avançado: achados, e não campos."""
        import html as _html

        from . import metadados_avancado as av

        e = _html.escape
        cores = {av.ALERTA: core.DESTAQUE, av.ATENCAO: PALETTE["warning"],
                 av.INFORMATIVO: CINZA}
        partes = [
            f'<p style="font-size:14pt; margin-bottom:2px;">'
            f'<b><font color="{TINTA}">{e(a.nome)}</font></b></p>'
            f'<p style="margin-top:0;"><font color="{CINZA}" size="2">'
            f"{e(a.tipo)} · exame avançado</font></p>"]

        analise = a.analise
        if analise is None:
            partes.append(f'<p><font color="{CINZA}">Ainda não examinado.'
                          f"</font></p>")
            return "".join(partes)
        if analise.vazio:
            partes.append(
                f'<p style="margin-top:18px;"><font color="{CINZA}">'
                f"Nada foi encontrado além dos metadados que o arquivo "
                f"declara.<br/><br/>Isso não significa que ele não tenha "
                f"sido alterado — significa que não foram encontradas as "
                f"marcas procuradas: fluxos alternativos, revisões "
                f"preservadas, propriedades ocultas e dados anexados após "
                f"o fim do formato.</font></p>")
            return "".join(partes)

        for ach in analise.ordenados:
            cor = cores.get(ach.relevancia, CINZA)
            partes.append(
                f'<p style="margin-top:18px; margin-bottom:2px;">'
                f'<font color="{cor}" size="1">'
                f"{e(av.ROTULO_RELEVANCIA.get(ach.relevancia, '').upper())}"
                + (f" · {e(ach.origem)}" if ach.origem else "")
                + f'</font><br/><b><font color="{TINTA}">{e(ach.titulo)}'
                f"</font></b></p>")
            if ach.detalhe:
                partes.append(
                    f'<p style="margin-top:0;"><font color="{CINZA}">'
                    + e(ach.detalhe).replace(chr(10), "<br/>")
                    + "</font></p>")
        if analise.erros:
            partes.append(
                f'<p style="margin-top:20px;"><font color="{CINZA}" size="2">'
                f"Falhas durante o exame: {e('; '.join(analise.erros[:4]))}"
                f"</font></p>")
        return "".join(partes)

    def _html(self, a: core.Arquivo) -> str:
        import html as _html

        e = _html.escape
        if self._modo == core.AVANCADO:
            return self._html_avancado(a)
        campos = a.relevantes if self._modo != core.COMPLETO else a.campos
        partes = [
            f'<p style="font-size:14pt; margin-bottom:2px;">'
            f'<b><font color="{TINTA}">{e(a.nome)}</font></b></p>'
            f'<p style="margin-top:0;"><font color="{CINZA}" size="2">'
            f"{e(a.tipo)}</font></p>"
        ]
        if a.erro:
            partes.append(
                f'<p><font color="{core.DESTAQUE}">Leitura parcial: '
                f"{e(a.erro)}</font></p>")

        for grupo in core.GRUPOS:
            do_grupo = [c for c in campos if c.grupo == grupo]
            if not do_grupo:
                continue
            linhas = "".join(
                "<tr>"
                f'<td width="34%"><font color="{CINZA}">{e(c.rotulo)}</font>'
                "</td>"
                f'<td><font color="'
                f'{core.DESTAQUE if grupo == "Localização" else TINTA}">'
                + (f"<b>{e(c.valor)}</b>" if c.relevante else e(c.valor))
                + "</font></td></tr>"
                for c in do_grupo)
            partes.append(
                f'<p style="margin-top:16px; margin-bottom:4px;">'
                f'<b><font color="{TINTA}">{e(grupo)}</font></b></p>'
                '<table width="100%" cellspacing="0" cellpadding="5" '
                'border="1" style="border-collapse:collapse; font-size:10pt;">'
                f"{linhas}</table>")

        if a.sha256:
            partes.append(
                f'<p style="margin-top:18px;"><font color="{CINZA}" size="2">'
                "Resumo criptográfico (SHA-256)</font><br/>"
                f'<font color="{TINTA}" face="Courier New" size="2">'
                f"{a.sha256}</font></p>")

        if not campos:
            partes.append(f'<p><font color="{CINZA}">Nenhum metadado '
                          "registrado neste arquivo.</font></p>")

        return ("<html><body style=\"font-family:'Segoe UI',Arial,sans-serif;"
                f' color:{TINTA};">' + "".join(partes) + "</body></html>")

    def _atualizar_alerta(self, a: core.Arquivo):
        if a.tem_localizacao:
            coords = a.valor("Coordenadas")
            self._lbl_alerta.setText(
                f"<span style='color:{PALETTE['warning']};'><b>Coordenadas "
                f"geográficas registradas no arquivo</b></span> "
                f"<span style='color:{PALETTE['text2']};'>— {coords}</span>")
            self._alerta.setVisible(True)
        elif a.relevantes:
            self._lbl_alerta.setText(
                f"<span style='color:{PALETTE['text2']};'>"
                f"{len(a.relevantes)} campo(s) de interesse para a apuração"
                "</span>")
            self._alerta.setVisible(True)
        else:
            self._alerta.setVisible(False)

    def _boas_vindas(self):
        self._alerta.setVisible(False)
        self._view.setHtml(
            "<html><body style=\"font-family:'Segoe UI',Arial,sans-serif;\">"
            f'<p style="font-size:13pt; color:{CINZA};">'
            "Abra um ou mais arquivos para extrair os metadados.</p>"
            f'<p style="color:{CINZA}; font-size:10pt;">'
            "Documentos PDF e de escritório, fotografias e mídias. "
            "De fotografias e vídeos de celular costumam sair o equipamento, "
            "o instante da captura e, quando o aparelho as gravou, as "
            "coordenadas.</p></body></html>")

    def _copiar(self):
        a = self._atual()
        if a is None:
            return
        QGuiApplication.clipboard().setText(self._view.toPlainText())
        self.status_msg.emit("Metadados copiados.")

    # ── termo ────────────────────────────────────
    def _mostrar_termo(self):
        if not self._arquivos:
            return
        from ..relogio import carimbo
        quando = carimbo()
        dlg = TermoDialog(self._arquivos, quando, self._modo, self)
        dlg.exec()

    # ── contrato do casco ────────────────────────
    def shutdown(self):
        if self._thread is not None and self._thread.isRunning():
            self._thread.wait(3000)
