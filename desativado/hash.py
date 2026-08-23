"""
Gerador de Hash — SHA-256 e Termo de Juntada.

Calcula o hash dos arquivos digitais a serem juntados aos autos e emite o
Termo de Juntada de Arquivo(s) Digital(is), com identificação do
declarante, vínculo ao IPS/PAD e coluna de nº SEI.
"""

from __future__ import annotations

import re
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDate
from PyQt6.QtGui import (
    QColor, QGuiApplication, QKeySequence, QShortcut, QPdfWriter,
    QPageSize, QFont,
)
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QFrame, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QDateEdit, QDialog, QTextEdit, QAbstractItemView, QSizePolicy,
)

from ..widgets import hsep

from ..icons import draw_icon
from ..impressao import imprimir_documento, preparar_escritor
from ..theme import PALETTE
from ..widgets import (
    NoScrollComboBox, SidebarPanel, TOOLBAR_HEIGHT, danger_button,
    field_label, fit_to_screen, output_button, primary_button, subtext, vsep,
)
from .base import ToolPage, ToolMeta
from . import hash_core as core


META = ToolMeta(
    key="hash",
    name="Gerador de Hash",
    icon="tool_hash",
    tagline="Hash SHA-256 e termo de juntada",
    description=(
        "Calcula o hash SHA-256 dos arquivos digitais a serem juntados aos "
        "autos e gera o Termo de Juntada de Arquivo(s) Digital(is), com "
        "identificação do declarante, vínculo ao IPS/PAD e coluna de nº SEI. "
        "Garante a integridade e a rastreabilidade da prova digital."
    ),
)

COL_N, COL_NOME, COL_TAM, COL_HASH, COL_SEI, COL_DEL = range(6)


# ─────────────────────────────────────────
#  CÁLCULO EM SEGUNDO PLANO
# ─────────────────────────────────────────

class HashThread(QThread):
    """Calcula o hash dos arquivos sem travar a interface."""

    file_done = pyqtSignal(int, str, str)      # índice, hash, erro
    file_progress = pyqtSignal(int, int, int)  # índice, lidos, total
    all_done = pyqtSignal()

    def __init__(self, entries: list[core.FileEntry]):
        super().__init__()
        self._entries = entries
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        for i, entry in enumerate(self._entries):
            if self._stop:
                break
            if entry.ready:
                continue
            try:
                digest = core.sha256_file(
                    entry.path,
                    progress=lambda r, t, i=i: self.file_progress.emit(i, r, t),
                    should_stop=lambda: self._stop,
                )
                if digest:
                    self.file_done.emit(i, digest, "")
            except Exception as e:
                self.file_done.emit(i, "", str(e))
        self.all_done.emit()


# ─────────────────────────────────────────
#  DIÁLOGO DO TERMO
# ─────────────────────────────────────────

class TermoDialog(QDialog):

    def __init__(self, data: core.TermoData, parent=None):
        super().__init__(parent)
        self._data = data
        self.setWindowTitle("Termo de Juntada")
        # Nunca maior que a área útil da tela: com um resize fixo o
        # diálogo passava por baixo da barra de tarefas e os botões de
        # exportar ficavam inalcançáveis.
        fit_to_screen(self, 880, 760)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("Termo de Juntada de Arquivo(s) Digital(is)")
        title.setObjectName("heading")
        layout.addWidget(title)

        sub = QLabel(
            "O documento é editável: clique no texto para ajustar a redação "
            "ou preencher o Nº SEI."
        )
        sub.setObjectName("subtext")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        # QTextEdit, e não QTextBrowser: este último trata "relatorio.pdf"
        # como hiperlink e não permite edição. O documento fica editável
        # para o usuário ajustar a redação e preencher o Nº SEI direto na
        # tabela; o que sai no PDF é o que está aqui, não uma remontagem.
        self._view = QTextEdit()
        self._view.setHtml(core.build_html(data))
        self._view.setTabChangesFocus(False)
        # Fundo claro de propósito: é a pré-visualização de um documento
        # que será impresso em papel, não uma tela do sistema.
        self._view.setStyleSheet(
            "QTextEdit { background: #FFFFFF; color: #16233A; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; "
            "padding: 26px; }"
        )
        # A rolagem é do documento; a faixa de ações abaixo é fixa.
        layout.addWidget(self._view, 1)
        layout.addWidget(hsep())

        actions = QWidget()
        actions.setSizePolicy(QSizePolicy.Policy.Preferred,
                              QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(actions)
        row.setContentsMargins(0, 8, 0, 0)
        row.setSpacing(8)

        pdf = output_button("Salvar PDF")
        pdf.clicked.connect(self._save_pdf)
        row.addWidget(pdf)

        txt = QPushButton("Copiar texto")
        txt.setCursor(Qt.CursorShape.PointingHandCursor)
        txt.clicked.connect(self._copy)
        row.addWidget(txt)

        restore = QPushButton("  Restaurar original")
        restore.setIcon(draw_icon("undo"))
        restore.setToolTip("Descarta as alterações e remonta o termo")
        restore.setCursor(Qt.CursorShape.PointingHandCursor)
        restore.clicked.connect(self._restore)
        row.addWidget(restore)

        self._feedback = QLabel("")
        self._feedback.setObjectName("badge_ok")
        row.addWidget(self._feedback)

        row.addStretch()
        close = QPushButton("Fechar")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.accept)
        row.addWidget(close)

        layout.addWidget(actions)

    # ─────────────────────────────────────
    #  INTEGRIDADE
    # ─────────────────────────────────────

    def _hashes_alterados(self) -> list[str]:
        """Arquivos cujo hash não consta mais, íntegro, no documento.

        Como o termo é editável, um deslize de digitação sobre a coluna de
        hash passaria despercebido e produziria uma prova de integridade
        que não confere. Antes de exportar, cada hash é reprocurado no
        texto — desconsiderando espaços, porque a coluna quebra o valor em
        várias linhas.
        """
        texto = re.sub(r"\s+", "", self._view.toPlainText())
        return [f.name for f in self._data.arquivos
                if f.hash and f.hash not in texto]

    def _confirma_integridade(self) -> bool:
        alterados = self._hashes_alterados()
        if not alterados:
            return True
        resp = QMessageBox.warning(
            self, "Hash alterado",
            "O hash destes arquivos não consta mais no documento, ou foi "
            "modificado:\n\n• " + "\n• ".join(alterados) +
            "\n\nUm termo com hash incorreto não comprova a integridade do "
            "arquivo. Deseja exportar mesmo assim?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return resp == QMessageBox.StandardButton.Yes

    def _restore(self):
        self._view.setHtml(core.build_html(self._data))
        self._feedback.setText("✓ Documento restaurado")

    def _copy(self):
        if not self._confirma_integridade():
            return
        QGuiApplication.clipboard().setText(self._view.toPlainText())
        self._feedback.setText("✓ Texto copiado")

    def _save_pdf(self):
        if not self._confirma_integridade():
            return

        sugestao = f"termo-juntada-{self._data.numero_processo or 'sem-numero'}.pdf"
        sugestao = sugestao.replace("/", "-").replace("\\", "-")
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Termo de Juntada", sugestao, "Arquivos PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            # QPdfWriter vem do QtGui: gera PDF de verdade, sem depender do
            # diálogo de impressão (o sistema original só oferecia
            # "Imprimir → Salvar como PDF" do navegador).
            writer = preparar_escritor(
                path, "Termo de Juntada de Arquivo(s) Digital(is)")

            # Clona o documento em edição — e não remonta a partir dos
            # dados —, senão qualquer ajuste feito pelo usuário na tela
            # seria silenciosamente descartado no arquivo exportado.
            doc = self._view.document().clone()
            doc.setDefaultFont(QFont("Segoe UI", 10))
            imprimir_documento(doc, writer)

            self._feedback.setText("✓ PDF salvo")
        except Exception as e:
            QMessageBox.critical(self, "Erro ao salvar",
                                 f"Não foi possível gerar o PDF:\n{e}")


# ─────────────────────────────────────────
#  FERRAMENTA
# ─────────────────────────────────────────

class HashTool(ToolPage):

    meta = META

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[core.FileEntry] = []
        self._thread: HashThread | None = None

        self.setAcceptDrops(True)
        self._build_ui()
        QShortcut(QKeySequence("Ctrl+O"), self, self._pick_files,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

    # ─────────────────────────────────────
    #  UI
    # ─────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Painel à esquerda, como nas demais ferramentas.
        root.addWidget(self._build_sidebar())

        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        ml.addWidget(self._build_toolbar())
        ml.addWidget(self._build_table(), 1)
        root.addWidget(main, 1)

    def _build_toolbar(self) -> QFrame:
        """Barra do conteúdo.

        Esta ferramenta não tem páginas nem zoom, então no lugar da
        ViewerToolbar leva as ações da própria lista — mantendo a altura e
        as margens das demais.
        """
        frame = QFrame()
        frame.setObjectName("toolbar_frame")
        frame.setFixedHeight(TOOLBAR_HEIGHT)

        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(8)

        self._btn_clear = danger_button("Limpar lista")
        self._btn_clear.clicked.connect(self._clear)
        self._btn_clear.setEnabled(False)
        lay.addWidget(self._btn_clear)

        lay.addWidget(vsep())

        hint = QLabel("Arraste arquivos para esta janela   •   SHA-256")
        hint.setObjectName("muted")
        lay.addWidget(hint)

        lay.addStretch()

        self._lbl_status = subtext("")
        lay.addWidget(self._lbl_status)
        return frame

    def _build_table(self) -> QWidget:
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Nº", "Nome do arquivo", "Tamanho", "Hash SHA-256", "Nº SEI!", ""])
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(False)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setStyleSheet(
            f"QTableWidget {{ background: {PALETTE['bg']}; border: none; "
            f"gridline-color: {PALETTE['surface2']}; }}"
            f"QTableWidget::item {{ padding: 6px 8px; }}"
            f"QHeaderView::section {{ background: {PALETTE['surface']}; "
            f"color: {PALETTE['text2']}; padding: 8px; border: none; "
            f"border-bottom: 1px solid {PALETTE['border']}; font-weight: 700; }}"
        )
        self._table.itemChanged.connect(self._on_item_changed)

        h = self._table.horizontalHeader()
        h.setSectionResizeMode(COL_N, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(COL_NOME, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(COL_TAM, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(COL_HASH, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(COL_SEI, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(COL_DEL, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(COL_N, 44)
        self._table.setColumnWidth(COL_TAM, 92)
        self._table.setColumnWidth(COL_HASH, 430)
        self._table.setColumnWidth(COL_SEI, 120)
        self._table.setColumnWidth(COL_DEL, 40)

        lay.addWidget(self._table)

        self._empty = QLabel(
            "Nenhum arquivo selecionado.\n\n"
            "Arraste arquivos para cá ou use “Selecionar arquivos…”."
        )
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setObjectName("subtext")
        self._empty.setStyleSheet(
            f"color: {PALETTE['text3']}; background: {PALETTE['bg']};")
        lay.addWidget(self._empty, 1)
        self._table.setVisible(False)
        return holder

    def _build_sidebar(self) -> SidebarPanel:
        panel = SidebarPanel()

        # Cabeçalho — ação de entrada, na mesma posição das demais.
        btn = primary_button("Selecionar arquivos…")
        btn.clicked.connect(self._pick_files)
        panel.header.addWidget(btn)

        self._lbl_file = subtext("Nenhum arquivo selecionado", wrap=True)
        panel.header.addWidget(self._lbl_file)

        # Corpo — dados do termo
        title = QLabel("Dados do Termo")
        title.setObjectName("heading")
        panel.body.addWidget(title)

        form = panel.body
        self._in_nome = self._field(form, "Nome completo", "Ex.: João da Silva")
        self._in_matricula = self._field(form, "Matrícula", "Ex.: 1234567")
        self._in_lotacao = self._field(form, "Lotação", "Ex.: DEL10 - PRF/UF")

        form.addWidget(field_label("Tipo de processo"))
        self._cb_tipo = NoScrollComboBox()
        self._cb_tipo.addItems(core.TIPOS_PROCESSO)
        form.addWidget(self._cb_tipo)

        self._in_numero = self._field(
            form, "Número do processo", "Ex.: 08650.000123/2026-11")

        form.addWidget(field_label("Data"))
        self._in_data = QDateEdit()
        self._in_data.setCalendarPopup(True)
        self._in_data.setDisplayFormat("dd/MM/yyyy")
        self._in_data.setDate(QDate.currentDate())
        form.addWidget(self._in_data)
        form.addStretch()

        # Rodapé — ação de saída
        self._btn_gerar = output_button("Gerar Termo de Juntada")
        self._btn_gerar.clicked.connect(self._gerar)
        self._btn_gerar.setEnabled(False)
        panel.footer.addWidget(self._btn_gerar)
        panel.add_note("Os arquivos são lidos apenas para o cálculo do hash.")
        return panel

    def _field(self, layout: QVBoxLayout, label: str, placeholder: str) -> QLineEdit:
        layout.addWidget(field_label(label))
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.textChanged.connect(self._refresh_actions)
        layout.addWidget(edit)
        return edit

    # ─────────────────────────────────────
    #  ARRASTAR E SOLTAR
    # ─────────────────────────────────────

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        paths = [u.toLocalFile() for u in ev.mimeData().urls()
                 if u.isLocalFile() and Path(u.toLocalFile()).is_file()]
        if paths:
            self._add_files(paths)
            ev.acceptProposedAction()

    # ─────────────────────────────────────
    #  LISTA DE ARQUIVOS
    # ─────────────────────────────────────

    def _pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Selecionar arquivos", "", "Todos os arquivos (*.*)")
        if paths:
            self._add_files(paths)

    def _add_files(self, paths: list[str]):
        added = 0
        for p in paths:
            try:
                size = Path(p).stat().st_size
            except OSError:
                continue
            self._entries.append(core.FileEntry(path=p, size=size))
            added += 1
        if not added:
            return
        self._rebuild_table()
        self._start_hashing()
        self.status_msg.emit(f"{added} arquivo(s) adicionado(s)")

    def _rebuild_table(self):
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._entries))

        for i, entry in enumerate(self._entries):
            self._set_cell(i, COL_N, str(i + 1), editable=False,
                           align=Qt.AlignmentFlag.AlignCenter)
            self._set_cell(i, COL_NOME, entry.name, editable=False,
                           tooltip=entry.path)
            self._set_cell(i, COL_TAM, core.format_size(entry.size),
                           editable=False, align=Qt.AlignmentFlag.AlignRight)

            if entry.error:
                self._set_cell(i, COL_HASH, f"erro: {entry.error}",
                               editable=False, color=PALETTE["danger"])
            elif entry.hash:
                self._set_cell(i, COL_HASH, entry.hash, editable=False,
                               mono=True, color=PALETTE["gold"])
            else:
                self._set_cell(i, COL_HASH, "calculando…", editable=False,
                               color=PALETTE["text3"])

            self._set_cell(i, COL_SEI, entry.sei, editable=True)

            btn = QPushButton()
            btn.setIcon(draw_icon("trash", 14, PALETTE["danger"]))
            btn.setToolTip("Remover da lista")
            btn.setFixedSize(28, 24)
            btn.clicked.connect(lambda _c, e=entry: self._remove(e))
            self._table.setCellWidget(i, COL_DEL, btn)

        self._table.blockSignals(False)
        self._table.setVisible(bool(self._entries))
        self._empty.setVisible(not self._entries)

        n = len(self._entries)
        self._lbl_file.setText(
            "Nenhum arquivo selecionado" if n == 0
            else f"{n} arquivo{'s' if n != 1 else ''} na lista"
        )
        self._refresh_actions()

    def _set_cell(self, row: int, col: int, text: str, editable: bool,
                  align=None, color: str = None, mono: bool = False,
                  tooltip: str = ""):
        item = QTableWidgetItem(text)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if editable:
            flags |= Qt.ItemFlag.ItemIsEditable
        item.setFlags(flags)
        if align is not None:
            item.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
        if color:
            item.setForeground(QColor(color))
        if mono:
            item.setFont(QFont("Consolas", 8))
        if tooltip:
            item.setToolTip(tooltip)
        self._table.setItem(row, col, item)

    def _on_item_changed(self, item: QTableWidgetItem):
        if item.column() == COL_SEI and 0 <= item.row() < len(self._entries):
            # Ao contrário do original, o nº SEI digitado fica no modelo e
            # entra no termo — antes ele se perdia ao recarregar a página.
            self._entries[item.row()].sei = item.text().strip()

    def _remove(self, entry: core.FileEntry):
        if entry in self._entries:
            self._entries.remove(entry)
            self._rebuild_table()
            self.status_msg.emit("Arquivo removido da lista")

    def _clear(self):
        if self._thread and self._thread.isRunning():
            self._thread.stop()
            self._thread.wait(3000)
        self._entries = []
        self._rebuild_table()
        self._lbl_status.setText("")
        self.status_msg.emit("Lista limpa")

    # ─────────────────────────────────────
    #  HASH
    # ─────────────────────────────────────

    def _start_hashing(self):
        if self._thread and self._thread.isRunning():
            return
        pendentes = [e for e in self._entries if not e.ready and not e.error]
        if not pendentes:
            return

        self._thread = HashThread(self._entries)
        self._thread.file_done.connect(self._on_file_done)
        self._thread.file_progress.connect(self._on_file_progress)
        self._thread.all_done.connect(self._on_all_done)
        self._thread.start()
        self._lbl_status.setText("Calculando hashes…")
        self._refresh_actions()

    def _on_file_progress(self, index: int, read: int, total: int):
        if total > CHUNK_SHOW and 0 <= index < self._table.rowCount():
            pct = int(read * 100 / total) if total else 0
            item = self._table.item(index, COL_HASH)
            if item is not None:
                item.setText(f"calculando… {pct}%")

    def _on_file_done(self, index: int, digest: str, error: str):
        if not (0 <= index < len(self._entries)):
            return
        entry = self._entries[index]
        entry.hash = digest
        entry.error = error
        self._rebuild_table()

    def _on_all_done(self):
        prontos = sum(1 for e in self._entries if e.ready)
        falhas = sum(1 for e in self._entries if e.error)
        self._lbl_status.setText(
            f"{prontos} hash(es) calculado(s)"
            + (f" · {falhas} falha(s)" if falhas else ""))
        self._refresh_actions()
        self.status_msg.emit(f"{prontos} arquivo(s) com hash calculado")

    # ─────────────────────────────────────
    #  TERMO
    # ─────────────────────────────────────

    def _collect(self) -> core.TermoData:
        d = self._in_data.date()
        return core.TermoData(
            nome=self._in_nome.text().strip(),
            matricula=self._in_matricula.text().strip(),
            lotacao=self._in_lotacao.text().strip(),
            tipo_processo=self._cb_tipo.currentText(),
            numero_processo=self._in_numero.text().strip(),
            dia=d.day(), mes=d.month(), ano=d.year(),
            arquivos=[e for e in self._entries if e.ready],
        )

    def _refresh_actions(self):
        self._btn_clear.setEnabled(bool(self._entries))
        rodando = bool(self._thread and self._thread.isRunning())
        prontos = [e for e in self._entries if e.ready]
        self._btn_gerar.setEnabled(bool(prontos) and not rodando)

    def _gerar(self):
        if self._thread and self._thread.isRunning():
            QMessageBox.information(
                self, "Aguarde",
                "Aguarde o cálculo do hash de todos os arquivos antes de "
                "gerar o termo.")
            return

        data = self._collect()
        faltando = core.validate(data)
        if faltando:
            QMessageBox.warning(
                self, "Campos obrigatórios",
                "Preencha antes de gerar o termo:\n\n• "
                + "\n• ".join(faltando))
            return

        TermoDialog(data, self).exec()

    # ─────────────────────────────────────
    #  CICLO DE VIDA
    # ─────────────────────────────────────

    def on_activated(self):
        if self._entries:
            self.status_msg.emit(f"{len(self._entries)} arquivo(s) na lista")
        else:
            self.status_msg.emit(
                "Selecione ou arraste arquivos para calcular o hash")

    def can_close(self) -> bool:
        return True

    def shutdown(self):
        if self._thread and self._thread.isRunning():
            self._thread.stop()
            self._thread.wait(3000)


#: A partir deste tamanho vale a pena mostrar o percentual por arquivo.
CHUNK_SHOW = 8 * 1024 * 1024
