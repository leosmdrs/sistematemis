"""
Anti-Injection — detecção de texto oculto em PDFs.

Três modos de visualização:
  • Normal   — a página como o leitor comum a vê
  • Revelar  — o texto oculto escrito por cima, no lugar exato
  • Raio-X   — miniaturas de todas as páginas com as marcas
"""

from __future__ import annotations

import datetime
from pathlib import Path

import fitz

from PyQt6.QtCore import Qt, QRect, QRectF, QSize, QThread, pyqtSignal
from PyQt6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QImage, QFont, QKeySequence, QShortcut,
    QGuiApplication, QPdfWriter, QPageSize,
)
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QScrollArea, QFrame, QSizePolicy, QMessageBox, QDialog, QTextEdit,
    QButtonGroup, QListWidget, QListWidgetItem, QProgressDialog, QLineEdit,
    QGridLayout, QStackedWidget,
)

from ..icons import draw_icon
from ..impressao import (documento_html, imprimir_documento,
                         limpar_para_sei, preparar_escritor)
from ..pdfview import PaginaPDF, VisorPDFContinuo
from ..theme import PALETTE
from ..widgets import (
    SidebarPanel, ViewerToolbar, field_label, fit_to_screen, hsep,
    output_button, primary_button, subtext,
)
from .base import ToolPage, ToolMeta
from . import antiinj_core as core


META = ToolMeta(
    key="antiinj",
    name="Anti-Injection",
    icon="tool_antiinj",
    tagline="Detecção de texto oculto em PDFs",
    description=(
        "Varre PDFs em busca de texto invisível à leitura convencional — "
        "opacidade zero, corpo minúsculo, branco sobre branco, conteúdo fora "
        "da área da página e camadas ocultas — usado para induzir a erro "
        "quem lê o documento, humano ou assistente de IA. Emite relatório "
        "de constatação pronto para os autos."
    ),
)

SEVERITY_COLOR = {
    "critica": PALETTE["danger"],
    "atencao": PALETTE["warning"],
    "baixa":   PALETTE["info"],
}


# ─────────────────────────────────────────
#  ANÁLISE EM SEGUNDO PLANO
# ─────────────────────────────────────────

class AnalyzeThread(QThread):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, doc: fitz.Document):
        super().__init__()
        self.doc = doc

    def run(self):
        try:
            self.done.emit(core.analyze_document(
                self.doc, progress=lambda c, t: self.progress.emit(c, t)))
        except Exception as e:
            self.failed.emit(str(e))


# ─────────────────────────────────────────
#  CANVAS
# ─────────────────────────────────────────

class PaginaAchados(PaginaPDF):
    """Página do documento com a sobreposição dos achados."""

    #: Ligados uma vez pela ferramenta; valem para todas as páginas.
    fonte_achados = None     # callable(indice) -> [Finding]
    modo_revelar = None      # callable() -> bool
    selecionado = None       # callable() -> Finding | None

    def _rect(self, f: core.Finding) -> QRectF:
        b = f.bbox
        e = self.escala
        r = QRectF(b.x0 * e, b.y0 * e,
                   max(b.x1 - b.x0, 1) * e, max(b.y1 - b.y0, 1) * e)
        # Trechos em corpo minúsculo produzem retângulos de poucos pixels,
        # invisíveis na tela; abre-se um mínimo para que a marca apareça.
        if r.height() < 10:
            r.setTop(r.top() - (10 - r.height()) / 2)
            r.setHeight(10)
        if r.width() < 14:
            r.setWidth(14)
        return r

    def desenhar_sobreposicao(self):
        achados = (self.fonte_achados(self.indice)
                   if callable(self.fonte_achados) else [])
        if not achados:
            return
        revelar = self.modo_revelar() if callable(self.modo_revelar) else False
        escolhido = self.selecionado() if callable(self.selecionado) else None

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        canvas = QRectF(0, 0, self.width(), self.height())

        # Achados próximos gerariam balões sobrepostos, ilegíveis; cada um
        # registra a área que ocupou para os seguintes desviarem.
        self._occupied: list[QRectF] = []

        for f in achados:
            color = QColor(SEVERITY_COLOR[f.severity])
            r = self._rect(f)
            # Achados fora da página são grampeados à borda, senão cairiam
            # fora da área visível justamente por estarem fora do papel.
            clipped = r.intersected(canvas)
            if clipped.isEmpty():
                clipped = QRectF(canvas.left() + 2, min(max(r.top(), 2),
                                 canvas.bottom() - 14), canvas.width() - 4, 12)

            fill = QColor(color)
            fill.setAlpha(46)
            p.fillRect(clipped, fill)
            p.setPen(QPen(color, 2 if f is escolhido else 1.2,
                          Qt.PenStyle.DashLine))
            p.drawRect(clipped)

            # Etiqueta da heurística
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            tag = f.code_label
            tw = p.fontMetrics().horizontalAdvance(tag) + 8
            tag_r = QRectF(clipped.left(), max(0.0, clipped.top() - 13), tw, 13)
            p.fillRect(tag_r, color)
            p.setPen(QColor("#12060A"))
            p.drawText(tag_r, Qt.AlignmentFlag.AlignCenter, tag)
            self._occupied.append(tag_r)

            if revelar:
                self._draw_revealed(p, clipped, canvas, f, color)

        p.end()

    def _draw_revealed(self, p: QPainter, anchor: QRectF, canvas: QRectF,
                       f: core.Finding, color: QColor):
        """Escreve o texto oculto, legível, logo abaixo do trecho."""
        p.setFont(QFont("Consolas", 8))
        text = f.preview(320)

        width = min(canvas.width() - anchor.left() - 8, 420.0)
        if width < 120:
            width = min(canvas.width() - 16, 420.0)
            left = 8.0
        else:
            left = anchor.left()

        metrics = p.fontMetrics()
        bounds = metrics.boundingRect(
            QRect(0, 0, int(width) - 12, 10_000),
            Qt.TextFlag.TextWordWrap, text)

        box = QRectF(left, anchor.bottom() + 3, width, bounds.height() + 20)
        if box.bottom() > canvas.bottom():
            box.moveTop(max(0.0, anchor.top() - box.height() - 3))

        # Empurra para baixo enquanto colidir com o que já foi desenhado.
        for _ in range(40):
            hit = next((r for r in self._occupied if r.intersects(box)), None)
            if hit is None:
                break
            box.moveTop(hit.bottom() + 4)
        self._occupied.append(box)

        p.fillRect(box, QColor(255, 255, 255, 240))
        p.setPen(QPen(color, 1.4))
        p.drawRect(box)

        head = QRectF(box.left() + 6, box.top() + 3, box.width() - 12, 11)
        p.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
        p.setPen(color)
        p.drawText(head, Qt.AlignmentFlag.AlignLeft, "TEXTO OCULTO REVELADO")

        p.setFont(QFont("Consolas", 8))
        p.setPen(QColor("#8A1020"))
        p.drawText(QRectF(box.left() + 6, box.top() + 16,
                          box.width() - 12, box.height() - 20),
                   int(Qt.TextFlag.TextWordWrap), text)


# ─────────────────────────────────────────
#  RELATÓRIO
# ─────────────────────────────────────────

class ReportDialog(QDialog):
    """Relatório de constatação como documento, no padrão do Termo de Juntada."""

    def __init__(self, file_name: str, n_pages: int, findings: list,
                 when: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Relatório de constatação")
        fit_to_screen(self, 940, 780)

        self._file_name = file_name
        self._n_pages = n_pages
        self._findings = findings
        self._when = when

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("Relatório de constatação")
        title.setObjectName("heading")
        layout.addWidget(title)

        sub = QLabel(
            "Preencha a identificação e confira o documento. Ele é editável: "
            "clique no texto para ajustar a redação."
        )
        sub.setObjectName("subtext")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        layout.addWidget(self._build_form())

        self._view = QTextEdit()
        self._view.setStyleSheet(
            "QTextEdit { background: #FFFFFF; color: #16233A; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; "
            "padding: 26px; }"
        )
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

        htm = QPushButton("  Salvar HTML")
        htm.setIcon(draw_icon("save", 15, PALETTE["text"]))
        htm.setToolTip("Arquivo HTML, para importar no SEI")
        htm.setCursor(Qt.CursorShape.PointingHandCursor)
        htm.clicked.connect(self._save_html)
        row.addWidget(htm)

        txt = QPushButton("Copiar texto")
        txt.setCursor(Qt.CursorShape.PointingHandCursor)
        txt.clicked.connect(self._copy)
        row.addWidget(txt)

        restore = QPushButton("  Restaurar original")
        restore.setIcon(draw_icon("undo"))
        restore.setToolTip("Descarta as alterações e remonta o relatório")
        restore.setCursor(Qt.CursorShape.PointingHandCursor)
        restore.clicked.connect(self._rebuild)
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
        self._rebuild()

    def _build_form(self) -> QWidget:
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 4, 0, 4)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)

        self._in_nome = QLineEdit()
        self._in_nome.setPlaceholderText("Ex.: João da Silva")
        self._in_matricula = QLineEdit()
        self._in_matricula.setPlaceholderText("Ex.: 1234567")
        self._in_lotacao = QLineEdit()
        self._in_lotacao.setPlaceholderText("Ex.: CGCOR - PRF/DF")

        for col, (rotulo, campo) in enumerate((
            ("Nome do servidor", self._in_nome),
            ("Matrícula", self._in_matricula),
            ("Lotação", self._in_lotacao),
        )):
            grid.addWidget(field_label(rotulo), 0, col)
            grid.addWidget(campo, 1, col)
            campo.textChanged.connect(self._rebuild)

        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 2)
        return box

    # ── documento ────────────────────────────────
    def _declarante(self) -> core.Declarante:
        return core.Declarante(
            nome=self._in_nome.text().strip(),
            matricula=self._in_matricula.text().strip(),
            lotacao=self._in_lotacao.text().strip(),
        )

    def _rebuild(self):
        self._view.setHtml(core.build_html(
            self._file_name, self._n_pages, self._findings,
            self._when, self._declarante()))

    def _copy(self):
        QGuiApplication.clipboard().setText(self._view.toPlainText())
        self._feedback.setText("✓ Texto copiado")

    def _save_html(self):
        """Exporta o que está na tela, limpo para a importação do SEI."""
        base = Path(self._file_name).stem or "documento"
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar relatório em HTML",
            f"constatacao-{base}.html", "Página HTML (*.html)")
        if not path:
            return
        if not path.lower().endswith((".html", ".htm")):
            path += ".html"
        try:
            # Sai o documento em edição, e não o remontado: os ajustes de
            # redação feitos aqui têm de acompanhar o arquivo exportado.
            Path(path).write_text(
                documento_html(limpar_para_sei(self._view.toHtml()),
                               "Relatório de Constatação de Texto Oculto"),
                encoding="utf-8")
            self._feedback.setText("✓ HTML salvo")
        except OSError as e:
            QMessageBox.critical(self, "Erro ao salvar",
                                 f"Não foi possível gravar:\n{e}")

    def _save_pdf(self):
        base = Path(self._file_name).stem or "documento"
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar relatório de constatação",
            f"constatacao-{base}.pdf", "Arquivos PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            writer = preparar_escritor(
                path, "Relatório de Constatação de Texto Oculto")

            # Clona o documento em edição — se remontasse a partir dos
            # achados, os ajustes de redação feitos na tela seriam
            # descartados em silêncio no arquivo exportado.
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

class AntiInjectionTool(ToolPage):

    meta = META

    MODES = ("Normal", "Revelar", "Raio-X")

    def __init__(self, parent=None):
        super().__init__(parent)

        self._doc: fitz.Document | None = None
        self._path = ""
        self._escolhido: core.Finding | None = None
        self._mode = "Normal"
        self._findings: list[core.Finding] = []

        self._build_ui()
        self._apply_shortcuts()

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
        self._toolbar = self._build_toolbar()
        ml.addWidget(self._toolbar)
        ml.addWidget(self._build_alert())

        self._scroll = QScrollArea()
        # As páginas se ligam à ferramenta pela classe: o visor cria e
        # descarta widgets conforme a rolagem, então não há instância fixa
        # onde pendurar os dados.
        PaginaAchados.fonte_achados = self._page_findings
        PaginaAchados.modo_revelar = lambda *_a: self._mode == "Revelar"
        PaginaAchados.selecionado = lambda *_a: self._escolhido

        self._visor = VisorPDFContinuo(PaginaAchados)
        self._visor.pagina_mudou.connect(
            lambda i: self._toolbar.set_page(i, self._visor.total()))
        self._visor.zoom_mudou.connect(self._toolbar.set_zoom)

        # Raio-X é uma vista à parte: mostra o documento inteiro de relance,
        # em vez de acompanhar a leitura página a página.
        self._pilha = QStackedWidget()
        self._pilha.addWidget(self._visor)
        self._xray = QScrollArea()
        self._xray.setWidgetResizable(True)
        self._xray.setFrameShape(QFrame.Shape.NoFrame)
        self._pilha.addWidget(self._xray)

        ml.addWidget(self._pilha, 1)
        root.addWidget(main, 1)
        self._visor.definir_zoom(1.25)
        self._set_welcome()

    def _build_toolbar(self) -> ViewerToolbar:
        bar = ViewerToolbar()
        bar.ir_para_pagina.connect(lambda i: self._visor.ir_para(i))
        bar.zoom_in.connect(lambda: self._visor.aplicar_zoom(1.25))
        bar.zoom_out.connect(lambda: self._visor.aplicar_zoom(1 / 1.25))
        bar.ajustar_largura.connect(lambda: self._visor.ajustar_a_largura())
        bar.add_separator()

        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        for i, name in enumerate(self.MODES):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setMinimumWidth(78)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip({
                "Normal":  "A página como o leitor comum a vê",
                "Revelar": "Escreve o texto oculto por cima, no lugar exato",
                "Raio-X":  "Miniaturas de todas as páginas com as marcas",
            }[name])
            btn.clicked.connect(lambda _c, n=name: self._set_mode(n))
            self._mode_group.addButton(btn)
            bar.add_widget(btn)

        bar.add_stretch()
        return bar

    def _build_alert(self) -> QFrame:
        self._alert = QFrame()
        self._alert.setFixedHeight(34)
        self._alert.setStyleSheet(
            f"background: {PALETTE['surface2']}; "
            f"border-bottom: 1px solid {PALETTE['border']};"
        )
        lay = QHBoxLayout(self._alert)
        lay.setContentsMargins(16, 0, 16, 0)

        self._lbl_alert = QLabel("")
        lay.addWidget(self._lbl_alert)
        lay.addStretch()

        self._alert.setVisible(False)
        return self._alert

    def _build_sidebar(self) -> SidebarPanel:
        panel = SidebarPanel()

        # Cabeçalho — ação de entrada, na mesma posição das demais.
        self._btn_open = primary_button("Abrir PDF…")
        self._btn_open.clicked.connect(self._open_file)
        panel.header.addWidget(self._btn_open)

        self._lbl_file = subtext("Nenhum arquivo aberto", wrap=True)
        panel.header.addWidget(self._lbl_file)

        # Corpo — a lista de achados ocupa todo o espaço disponível, então
        # dispensa a rolagem do painel e usa a sua própria.
        row = QHBoxLayout()
        title = QLabel("Achados")
        title.setObjectName("heading")
        row.addWidget(title)
        row.addStretch()
        self._lbl_count = subtext("—")
        row.addWidget(self._lbl_count)
        panel.body.addLayout(row)

        self._lbl_breakdown = QLabel("")
        self._lbl_breakdown.setTextFormat(Qt.TextFormat.RichText)
        self._lbl_breakdown.setWordWrap(True)
        panel.body.addWidget(self._lbl_breakdown)

        self._list = QListWidget()
        self._list.setWordWrap(True)
        self._list.setStyleSheet(
            f"QListWidget {{ background: {PALETTE['bg']}; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; }}"
            f"QListWidget::item {{ padding: 9px 10px; "
            f"border-bottom: 1px solid {PALETTE['surface2']}; }}"
        )
        self._list.currentRowChanged.connect(self._on_finding_selected)
        panel.body.addWidget(self._list, 1)

        # Rodapé — ação de saída, em verde como nas demais.
        self._btn_report = output_button("Relatório de constatação")
        self._btn_report.clicked.connect(self._show_report)
        self._btn_report.setEnabled(False)
        panel.footer.addWidget(self._btn_report)
        panel.add_note("Análise 100% local. O documento não é alterado.")
        return panel

    def _set_welcome(self):
        self._visor.mensagem(
            f"<div style='color:{PALETTE['text3']};font-size:15px;'>"
            "Abra um PDF para analisar</div>"
        )

    def _apply_shortcuts(self):
        ctx = Qt.ShortcutContext.WidgetWithChildrenShortcut
        for keys, slot in (
            ("Ctrl+O", self._open_file),
            ("+", lambda: self._visor.aplicar_zoom(1.25)),
            ("-", lambda: self._visor.aplicar_zoom(1 / 1.25)),
        ):
            QShortcut(QKeySequence(keys), self, slot, context=ctx)

    # ─────────────────────────────────────
    #  ARQUIVO E ANÁLISE
    # ─────────────────────────────────────

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir PDF", "", "Arquivos PDF (*.pdf)")
        if not path:
            return
        try:
            if self._doc:
                self._doc.close()
            self._doc = fitz.open(path)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível abrir o PDF:\n{e}")
            return

        self._path = path
        self._findings = []
        self._lbl_file.setText(Path(path).name)
        self._analyze()

    def _analyze(self):
        progress = QProgressDialog("Analisando páginas…", None, 0,
                                   len(self._doc), self)
        progress.setWindowTitle("Anti-Injection")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        self._thread = AnalyzeThread(self._doc)
        self._thread.progress.connect(lambda c, _t: progress.setValue(c))
        self._thread.done.connect(lambda f: self._on_analyzed(f, progress))
        self._thread.failed.connect(lambda e: self._on_failed(e, progress))
        self._thread.start()

    def _on_analyzed(self, findings: list, progress: QProgressDialog):
        progress.close()
        self._findings = findings
        self._populate_list()
        self._update_alert()
        self._btn_report.setEnabled(True)
        self._visor.carregar(self._doc)
        self._toolbar.set_page(0, len(self._doc))
        self._toolbar.set_zoom(self._visor.zoom())
        self._render()

        s = core.summarize(findings)
        if s["total"] == 0:
            self.status_msg.emit("Nenhum texto oculto encontrado no documento")
        else:
            self.status_msg.emit(
                f"{s['total']} achado(s) em {s['paginas']} página(s) — "
                f"{s['critica']} crítico(s)")

    def _on_failed(self, err: str, progress: QProgressDialog):
        progress.close()
        QMessageBox.critical(self, "Erro na análise", f"Ocorreu um erro:\n{err}")

    # ─────────────────────────────────────
    #  PAINEL DE ACHADOS
    # ─────────────────────────────────────

    def _populate_list(self):
        self._list.clear()
        s = core.summarize(self._findings)
        self._lbl_count.setText(str(s["total"]))

        if s["total"] == 0:
            self._lbl_breakdown.setText(
                f"<span style='color:{PALETTE['success']}'>"
                "✓ Nenhum texto oculto detectado</span>")
            item = QListWidgetItem("  Documento sem indícios de texto oculto.")
            item.setForeground(QColor(PALETTE["text3"]))
            self._list.addItem(item)
            return

        parts = []
        for key, label in (("critica", "crítico"), ("atencao", "atenção"),
                           ("baixa", "baixa")):
            if s[key]:
                parts.append(
                    f"<span style='color:{SEVERITY_COLOR[key]};font-weight:700'>"
                    f"{s[key]} {label}</span>")
        self._lbl_breakdown.setText(
            " &nbsp;·&nbsp; ".join(parts) +
            f"<span style='color:{PALETTE['text3']}'> &nbsp;em "
            f"{s['paginas']} página(s)</span>")

        last_page = -1
        self._row_map: dict[int, core.Finding] = {}
        for f in sorted(self._findings, key=lambda x: (x.page, x.bbox.y0)):
            if f.page != last_page:
                header = QListWidgetItem(f"  PÁGINA {f.page + 1}")
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                header.setForeground(QColor(PALETTE["text3"]))
                font = header.font()
                font.setBold(True)
                font.setPointSize(8)
                header.setFont(font)
                self._list.addItem(header)
                last_page = f.page

            item = QListWidgetItem(
                f"[{f.code_label}]  {f.severity_label} · {f.reason}\n{f.preview(150)}")
            item.setForeground(QColor(SEVERITY_COLOR[f.severity]))
            if f.injection:
                item.setToolTip("Contém instrução dirigida ao leitor do documento")
            self._list.addItem(item)
            self._row_map[self._list.row(item)] = f

    def _on_finding_selected(self, row: int):
        f = getattr(self, "_row_map", {}).get(row)
        if f is None:
            return
        self._escolhido = f
        if self._mode == "Raio-X":
            self._set_mode("Revelar")
            self._sync_mode_buttons()
        self._visor.ir_para(f.page)
        self._visor.redesenhar()
        self.status_msg.emit(f"Página {f.page + 1} — {f.reason}")

    def _update_alert(self):
        s = core.summarize(self._findings)
        if s["total"] == 0:
            self._alert.setVisible(False)
            return
        color = PALETTE["danger"] if s["critica"] else PALETTE["warning"]
        crit = f" ({s['critica']} crítico)" if s["critica"] else ""
        self._lbl_alert.setText(
            f"<span style='color:{color};font-weight:600'>⚠ {s['total']} "
            f"achado(s){crit} em {s['paginas']} página(s)</span>")
        self._lbl_alert.setTextFormat(Qt.TextFormat.RichText)
        self._alert.setVisible(True)

    # ─────────────────────────────────────
    #  RENDERIZAÇÃO
    # ─────────────────────────────────────

    def _page_findings(self, page: int) -> list:
        return [f for f in self._findings if f.page == page]

    def _render(self):
        if not self._doc:
            return
        if self._mode == "Raio-X":
            self._render_xray()
            self._pilha.setCurrentIndex(1)
        else:
            self._pilha.setCurrentIndex(0)
            self._visor.redesenhar()

    def _render_xray(self):
        """Miniaturas de todas as páginas, com as marcas dos achados."""
        antigo = self._xray.takeWidget()
        if antigo is not None:
            antigo.deleteLater()

        strip = QWidget()
        strip.setStyleSheet(f"background: {PALETTE['bg']};")
        grid = QHBoxLayout(strip)
        grid.setSpacing(16)
        grid.setContentsMargins(20, 20, 20, 20)
        grid.setAlignment(Qt.AlignmentFlag.AlignCenter)

        thumb_zoom = 0.34
        for i in range(len(self._doc)):
            col = QVBoxLayout()
            col.setSpacing(6)

            lbl = QLabel(f"PÁGINA {i + 1}")
            lbl.setObjectName("muted")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            thumb = PaginaAchados(i)
            r = self._doc[i].rect
            thumb.definir_medidas(r.width, r.height, thumb_zoom)
            pix = self._doc[i].get_pixmap(
                matrix=fitz.Matrix(thumb_zoom, thumb_zoom), alpha=False)
            thumb.definir_imagem(
                QPixmap.fromImage(QImage.fromData(pix.tobytes("ppm"))))

            col.addWidget(lbl)
            col.addWidget(thumb, 0, Qt.AlignmentFlag.AlignCenter)
            col.addStretch()
            grid.addLayout(col)

        self._xray.setWidget(strip)

    def _sync_mode_buttons(self):
        for btn in self._mode_group.buttons():
            btn.setChecked(btn.text() == self._mode)

    def _set_mode(self, name: str):
        self._mode = name
        self._render()
        self.status_msg.emit(f"Modo {name}")

    # ─────────────────────────────────────
    #  NAVEGAÇÃO
    # ─────────────────────────────────────

    # ─────────────────────────────────────
    #  RELATÓRIO
    # ─────────────────────────────────────

    def _show_report(self):
        if not self._doc:
            return
        when = datetime.datetime.now().strftime("%d/%m/%Y às %H:%M")
        ReportDialog(Path(self._path).name, len(self._doc),
                     self._findings, when, self).exec()

    # ─────────────────────────────────────
    #  CICLO DE VIDA
    # ─────────────────────────────────────

    def on_activated(self):
        if not self._doc:
            self.status_msg.emit("Abra um PDF para analisar")
        else:
            s = core.summarize(self._findings)
            self.status_msg.emit(
                f"{Path(self._path).name} — {s['total']} achado(s)")

    def shutdown(self):
        if self._doc:
            self._doc.close()
            self._doc = None
