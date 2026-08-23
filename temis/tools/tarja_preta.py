"""
Tarja Preta — tarjamento seguro de PDFs.

As páginas são rasterizadas antes de salvar, de modo que o texto sob a
tarja deixa de existir no arquivo final — não fica apenas encoberto por
um retângulo, como acontece quando se desenha por cima do PDF.
"""

import io
import re
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

from PyQt6.QtCore import Qt, QRect, QPoint, QSize, QThread, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QKeySequence, QShortcut,
)
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QLineEdit, QMessageBox, QProgressDialog, QCheckBox, QGroupBox,
    QListWidget, QListWidgetItem,
)

from ..icons import draw_icon
from ..pdfview import PaginaPDF, VisorPDFContinuo
from ..theme import PALETTE
from ..widgets import (
    NoScrollComboBox, SidebarPanel, ViewerToolbar, danger_button,
    output_button, primary_button, subtext,
)
from .base import ToolPage, ToolMeta


META = ToolMeta(
    key="tarja",
    name="Tarja Preta",
    icon="tool_tarja",
    tagline="Tarjamento seguro de PDFs",
    description=(
        "Oculta dados pessoais e sigilosos em PDFs de forma irreversível. "
        "A página é rasterizada ao salvar, então o texto sob a tarja é "
        "removido do arquivo — não fica apenas coberto. Aceita tarja manual "
        "com o mouse, marcação por [colchetes] no texto-fonte e busca "
        "automática por CPF, CNPJ, RG, telefone e e-mail."
    ),
)


# ─────────────────────────────────────────
#  CANVAS DE VISUALIZAÇÃO
# ─────────────────────────────────────────

class PaginaTarja(PaginaPDF):
    """Página do documento que aceita tarjas desenhadas com o mouse.

    Cada página é um widget próprio dentro da rolagem contínua, e converte
    as coordenadas com a sua própria escala. Antes havia um canvas único
    que trocava de página; com uma página por widget, não existe estado
    de "página corrente" a manter em sincronia.
    """

    #: Compartilhado por todas as páginas — o dono liga uma vez só.
    fonte_tarjas = None       # callable(indice) -> [(fitz.Rect, origem)]
    ao_criar_tarja = None     # callable(indice, fitz.Rect)

    def __init__(self, indice: int, parent=None):
        super().__init__(indice, parent)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._origem = QPoint()
        self._rect = QRect()
        self._desenhando = False

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.pronta():
            self._origem = ev.position().toPoint()
            self._rect = QRect(self._origem, QSize())
            self._desenhando = True

    def mouseMoveEvent(self, ev):
        if self._desenhando:
            self._rect = QRect(self._origem,
                               ev.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, ev):
        if not (self._desenhando and ev.button() == Qt.MouseButton.LeftButton):
            return
        self._desenhando = False
        r = QRect(self._origem, ev.position().toPoint()).normalized()
        # Mantém a tarja dentro da folha: fora dela, a conversão para
        # coordenadas do PDF cairia fora do papel.
        r = r.intersected(self.rect())
        if r.width() > 5 and r.height() > 5 and callable(self.ao_criar_tarja):
            self.ao_criar_tarja(self.indice, self.para_pdf(r))
        self._rect = QRect()
        self.update()

    def desenhar_sobreposicao(self):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if callable(self.fonte_tarjas):
            for pdf_r, _origem in self.fonte_tarjas(self.indice):
                p.fillRect(self.para_tela(pdf_r), QColor(PALETTE["tarja"]))

        if self._desenhando and not self._rect.isNull():
            p.fillRect(self._rect, QColor(0, 0, 0, 180))
            p.setPen(QPen(QColor(PALETTE["gold"]), 2, Qt.PenStyle.DashLine))
            p.drawRect(self._rect)
        p.end()


# ─────────────────────────────────────────
#  THREAD DE SALVAR
# ─────────────────────────────────────────

class SaveThread(QThread):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    #: Fator de rasterização (2.0 ≈ 144 DPI).
    RENDER_SCALE = 2.0

    def __init__(self, doc: fitz.Document, tarjas_por_pagina: dict, out_path: str):
        super().__init__()
        self.doc = doc
        self.tarjas_por_pagina = tarjas_por_pagina
        self.out_path = out_path

    def run(self):
        try:
            from PIL import ImageDraw

            out_doc = fitz.open()
            total = len(self.doc)
            k = self.RENDER_SCALE

            for i in range(total):
                self.progress.emit(i + 1, total)
                page = self.doc[i]
                tarjas = self.tarjas_por_pagina.get(i, [])

                pix = page.get_pixmap(matrix=fitz.Matrix(k, k), alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                draw = ImageDraw.Draw(img)

                for pdf_r, _ in tarjas:
                    draw.rectangle(
                        [round(pdf_r.x0 * k), round(pdf_r.y0 * k),
                         round(pdf_r.x1 * k), round(pdf_r.y1 * k)],
                        fill=(0, 0, 0),
                    )

                buf = io.BytesIO()
                img.save(buf, format="PDF")
                buf.seek(0)
                tmp = fitz.open("pdf", buf.read())
                out_doc.insert_pdf(tmp)
                tmp.close()

            out_doc.save(self.out_path, garbage=4, deflate=True)
            out_doc.close()
            self.done.emit(self.out_path)
        except Exception as e:
            self.failed.emit(str(e))


# ─────────────────────────────────────────
#  FERRAMENTA
# ─────────────────────────────────────────

class TarjaPretaTool(ToolPage):

    meta = META

    PATTERNS = {
        "CPF  (000.000.000-00)":     r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}",
        "CNPJ (00.000.000/0000-00)": r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}",
        "RG   (números)":            r"\b\d{1,2}\.?\d{3}\.?\d{3}-?[\dXx]\b",
        "Telefone":                  r"(?:\+55\s?)?(?:\(?\d{2}\)?\s?)(?:9\s?)?\d{4,5}-?\d{4}",
        "E-mail":                    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    }

    def __init__(self, parent=None):
        super().__init__(parent)

        self._doc: fitz.Document | None = None
        self._tarjas_por_pagina: dict[int, list] = {}

        self._build_ui()
        self._apply_shortcuts()

    # ─────────────────────────────────────
    #  ACESSO ÀS TARJAS
    # ─────────────────────────────────────

    def _tarjas_da(self, indice: int) -> list:
        return self._tarjas_por_pagina.get(indice, [])

    def _acrescentar(self, indice: int, retangulo, origem: str):
        self._tarjas_por_pagina.setdefault(indice, []).append((retangulo, origem))

    def _nova_tarja_manual(self, indice: int, retangulo):
        self._acrescentar(indice, retangulo, "manual")
        self._visor.redesenhar()
        self._update_tarja_count()
        self.status_msg.emit(
            f"Tarja adicionada na página {indice + 1} — "
            f"{len(self._tarjas_da(indice))} nesta página")

    # ─────────────────────────────────────
    #  UI
    # ─────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        main_area = QWidget()
        ml = QVBoxLayout(main_area)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        self._toolbar = self._build_toolbar()
        ml.addWidget(self._toolbar)

        # Uma página por widget, empilhadas numa rolagem só. O canal com as
        # tarjas é ligado na classe, não em cada instância, porque o visor
        # cria e descarta páginas conforme a rolagem.
        PaginaTarja.fonte_tarjas = self._tarjas_da
        PaginaTarja.ao_criar_tarja = self._nova_tarja_manual

        self._visor = VisorPDFContinuo(PaginaTarja)
        self._visor.pagina_mudou.connect(self._ao_mudar_pagina)
        self._visor.zoom_mudou.connect(self._toolbar.set_zoom)
        ml.addWidget(self._visor, 1)
        root.addWidget(main_area, 1)

        self._visor.definir_zoom(1.5)
        self._set_welcome_state()

    def _build_sidebar(self) -> SidebarPanel:
        panel = SidebarPanel()

        # Cabeçalho — ação de entrada. O nome da ferramenta já aparece na
        # barra do casco; repeti-lo aqui só consumiria altura útil.
        self._btn_open = primary_button("Abrir PDF…")
        self._btn_open.clicked.connect(self._open_file)
        panel.header.addWidget(self._btn_open)

        self._lbl_file = subtext("Nenhum arquivo aberto", wrap=True)
        panel.header.addWidget(self._lbl_file)

        # Corpo — controles
        panel.body.addWidget(self._group_brackets())
        panel.body.addWidget(self._group_search())
        panel.body.addWidget(self._group_actions())
        panel.body.addStretch()

        # Rodapé — ação de saída
        self._btn_save = output_button("Salvar PDF tarjado")
        self._btn_save.clicked.connect(self._save_pdf)
        self._btn_save.setEnabled(False)
        panel.footer.addWidget(self._btn_save)
        panel.add_note("O texto é removido permanentemente, não apenas ocultado.")
        return panel

    def _group_brackets(self) -> QGroupBox:
        grp = QGroupBox("MARCAÇÃO POR COLCHETES  [ ]")
        grp.setStyleSheet(
            f"QGroupBox {{ border-color: {PALETTE['warning']}55; }}"
            f"QGroupBox::title {{ color: {PALETTE['warning']}; }}"
        )
        lay = QVBoxLayout(grp)
        lay.setSpacing(8)

        info = QLabel(
            "Trechos entre colchetes no PDF são tarjados automaticamente.<br>"
            f"Ex.: <b style='color:{PALETTE['warning']}'>[Fulano de Tal]</b>"
        )
        info.setObjectName("subtext")
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(info)

        lay.addLayout(self._scope_row("_bracket_scope_combo"))

        self._btn_bracket = QPushButton("  Tarjar conteúdo entre [ ]")
        self._btn_bracket.setIcon(draw_icon("redact", color=PALETTE["warning"]))
        self._btn_bracket.setObjectName("btn_bracket")
        self._btn_bracket.clicked.connect(self._redact_brackets)
        self._btn_bracket.setEnabled(False)
        lay.addWidget(self._btn_bracket)

        self._lbl_bracket_hits = QLabel("")
        self._lbl_bracket_hits.setObjectName("bracket_badge")
        lay.addWidget(self._lbl_bracket_hits)

        self._bracket_list = QListWidget()
        self._bracket_list.setMaximumHeight(96)
        self._bracket_list.setToolTip("Termos que serão tarjados")
        lay.addWidget(self._bracket_list)

        self._btn_preview_brackets = QPushButton("Pré-visualizar termos")
        self._btn_preview_brackets.clicked.connect(self._preview_brackets)
        self._btn_preview_brackets.setEnabled(False)
        lay.addWidget(self._btn_preview_brackets)
        return grp

    def _group_search(self) -> QGroupBox:
        grp = QGroupBox("BUSCA AUTOMÁTICA")
        lay = QVBoxLayout(grp)
        lay.setSpacing(8)

        self._search_combo = NoScrollComboBox()
        self._search_combo.addItems(
            ["Texto livre", *self.PATTERNS.keys(), "Regex personalizado"]
        )
        self._search_combo.currentTextChanged.connect(self._on_search_kind_changed)
        lay.addWidget(self._search_combo)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Digite o termo ou padrão…")
        self._search_input.returnPressed.connect(self._search_and_redact)
        lay.addWidget(self._search_input)

        self._chk_case = QCheckBox("Distinguir maiúsculas")
        lay.addWidget(self._chk_case)

        lay.addLayout(self._scope_row("_scope_combo"))

        self._btn_search = QPushButton("Buscar e tarjar")
        self._btn_search.clicked.connect(self._search_and_redact)
        self._btn_search.setEnabled(False)
        lay.addWidget(self._btn_search)

        self._lbl_hits = QLabel("")
        self._lbl_hits.setObjectName("subtext")
        lay.addWidget(self._lbl_hits)
        return grp

    def _group_actions(self) -> QGroupBox:
        grp = QGroupBox("TARJAS")
        lay = QVBoxLayout(grp)
        lay.setSpacing(8)

        self._btn_undo = QPushButton("  Desfazer última tarja")
        self._btn_undo.setIcon(draw_icon("undo"))
        self._btn_undo.clicked.connect(self._undo_tarja)
        self._btn_undo.setEnabled(False)
        lay.addWidget(self._btn_undo)

        self._btn_clear_page = danger_button("Limpar página atual")
        self._btn_clear_page.clicked.connect(self._clear_page)
        self._btn_clear_page.setEnabled(False)
        lay.addWidget(self._btn_clear_page)

        self._btn_clear_all = danger_button("Limpar tudo")
        self._btn_clear_all.clicked.connect(self._clear_all)
        self._btn_clear_all.setEnabled(False)
        lay.addWidget(self._btn_clear_all)

        self._lbl_tarja_count = QLabel("0 tarjas em 0 páginas")
        self._lbl_tarja_count.setObjectName("subtext")
        lay.addWidget(self._lbl_tarja_count)
        return grp

    def _scope_row(self, attr: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel("Escopo:")
        lbl.setFixedWidth(50)
        combo = NoScrollComboBox()
        combo.addItems(["Esta página", "Todas as páginas"])
        setattr(self, attr, combo)
        row.addWidget(lbl)
        row.addWidget(combo, 1)
        return row

    def _build_toolbar(self) -> ViewerToolbar:
        bar = ViewerToolbar()
        bar.ir_para_pagina.connect(lambda i: self._visor.ir_para(i))
        bar.zoom_in.connect(lambda: self._visor.aplicar_zoom(1.25))
        bar.zoom_out.connect(lambda: self._visor.aplicar_zoom(1 / 1.25))
        bar.ajustar_largura.connect(lambda: self._visor.ajustar_a_largura())
        bar.add_separator()
        bar.add_hint(
            "Arraste o mouse para tarja manual   •   "
            "Use [ ] no texto-fonte   •   Ctrl+Z desfaz"
        )
        bar.add_stretch()
        return bar

    def _set_welcome_state(self):
        self._visor.mensagem("Abra um PDF para começar")

    def _ao_mudar_pagina(self, indice: int):
        self._toolbar.set_page(indice, self._visor.total())

    def _apply_shortcuts(self):
        # WidgetWithChildren: os atalhos só valem enquanto esta ferramenta
        # está em foco, para não vazarem para as outras do hub.
        ctx = Qt.ShortcutContext.WidgetWithChildrenShortcut
        for keys, slot in (
            ("Ctrl+O", self._open_file), ("Ctrl+S", self._save_pdf),
            ("Ctrl+Z", self._undo_tarja),
            ("+", lambda: self._visor.aplicar_zoom(1.25)),
            ("-", lambda: self._visor.aplicar_zoom(1 / 1.25)),
        ):
            QShortcut(QKeySequence(keys), self, slot, context=ctx)

    # ─────────────────────────────────────
    #  ARQUIVO E RENDERIZAÇÃO
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
            self._tarjas_por_pagina = {}
            self._lbl_file.setText(Path(path).name)
            self._bracket_list.clear()
            self._lbl_bracket_hits.clear()
            self._lbl_hits.clear()
            self._visor.carregar(self._doc)
            self._toolbar.set_page(0, len(self._doc))
            self._toolbar.set_zoom(self._visor.zoom())
            self._update_tarja_count()
            for w in (self._btn_search, self._btn_save, self._btn_undo,
                      self._btn_clear_page, self._btn_clear_all,
                      self._btn_bracket, self._btn_preview_brackets):
                w.setEnabled(True)
            self.status_msg.emit(f"PDF aberto: {len(self._doc)} página(s)")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível abrir o PDF:\n{e}")

    # ─────────────────────────────────────
    #  AÇÕES DE TARJA
    # ─────────────────────────────────────

    def _undo_tarja(self):
        """Desfaz a última tarja da página que está sendo lida."""
        indice = self._visor.pagina_atual()
        pilha = self._tarjas_por_pagina.get(indice)
        if not pilha:
            self.status_msg.emit(
                f"Nenhuma tarja na página {indice + 1} para desfazer")
            return
        pilha.pop()
        if not pilha:
            self._tarjas_por_pagina.pop(indice, None)
        self._visor.redesenhar()
        self._update_tarja_count()
        self.status_msg.emit(f"Última tarja da página {indice + 1} removida")

    def _clear_page(self):
        indice = self._visor.pagina_atual()
        if self._tarjas_por_pagina.pop(indice, None) is None:
            self.status_msg.emit(f"A página {indice + 1} não tem tarjas")
            return
        self._visor.redesenhar()
        self._update_tarja_count()
        self.status_msg.emit(f"Tarjas da página {indice + 1} removidas")

    def _clear_all(self):
        if QMessageBox.question(
            self, "Confirmar", "Remover todas as tarjas do documento?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        self._tarjas_por_pagina = {}
        self._visor.redesenhar()
        self._update_tarja_count()
        self.status_msg.emit("Todas as tarjas removidas")

    def _update_tarja_count(self):
        total = sum(len(v) for v in self._tarjas_por_pagina.values())
        pages = len(self._tarjas_por_pagina)
        self._lbl_tarja_count.setText(
            f"{total} tarja{'s' if total != 1 else ''} em "
            f"{pages} página{'s' if pages != 1 else ''}"
        )

    # ─────────────────────────────────────
    #  MODO COLCHETES
    # ─────────────────────────────────────

    def _pages_in_scope(self, combo) -> list[int]:
        if combo.currentText() == "Todas as páginas":
            return list(range(len(self._doc)))
        return [self._visor.pagina_atual()]

    def _collect_bracket_terms(self, pages: list[int]) -> dict[int, list[str]]:
        """Retorna {página: [termo, ...]} para cada [termo] encontrado."""
        pat = re.compile(r"\[([^\[\]]+)\]")
        result: dict[int, list[str]] = {}
        for pi in pages:
            termos = [
                m.group(1).strip()
                for m in pat.finditer(self._doc[pi].get_text("text"))
                if m.group(1).strip()
            ]
            if termos:
                result[pi] = termos
        return result

    def _preview_brackets(self):
        if not self._doc:
            return
        por_pagina = self._collect_bracket_terms(
            self._pages_in_scope(self._bracket_scope_combo))

        self._bracket_list.clear()
        total = 0
        for pi, termos in sorted(por_pagina.items()):
            for t in termos:
                item = QListWidgetItem(f"  p.{pi + 1}  →  {t}")
                item.setForeground(QColor(PALETTE["warning"]))
                self._bracket_list.addItem(item)
                total += 1

        if total == 0:
            self._lbl_bracket_hits.setText("Nenhum trecho [ ] encontrado")
            self._bracket_list.addItem("  (nenhum trecho marcado)")
        else:
            self._lbl_bracket_hits.setText(f"{total} trecho(s) detectado(s)")
        self.status_msg.emit(f"Pré-visualização: {total} trecho(s) entre colchetes")

    def _redact_brackets(self):
        if not self._doc:
            return
        por_pagina = self._collect_bracket_terms(
            self._pages_in_scope(self._bracket_scope_combo))

        if not por_pagina:
            self.status_msg.emit("Nenhum trecho entre [ ] nas páginas selecionadas")
            self._lbl_bracket_hits.setText("Nenhum trecho [ ] encontrado")
            return

        total_hits = 0
        for pi, termos in por_pagina.items():
            page = self._doc[pi]
            rects: list[fitz.Rect] = []
            for termo in termos:
                # O par [termo] completo cobre também os colchetes; quando
                # ele não é achado (quebra de linha entre os spans), cai-se
                # no conteúdo interno com uma folga lateral.
                full = page.search_for(f"[{termo}]")
                if full:
                    rects.extend(full)
                else:
                    rects.extend(
                        fitz.Rect(h.x0 - 4, h.y0 - 1, h.x1 + 4, h.y1 + 1)
                        for h in page.search_for(termo)
                    )
            if rects:
                self._tarjas_por_pagina.setdefault(pi, []).extend(
                    (r, "colchete") for r in rects)
                total_hits += len(rects)

        self._visor.redesenhar()
        self._update_tarja_count()
        self._preview_brackets()
        self._lbl_bracket_hits.setText(f"✓ {total_hits} tarja(s) aplicada(s)")
        self.status_msg.emit(
            f"Colchetes: {total_hits} trecho(s) tarjado(s) em {len(por_pagina)} página(s)")

    # ─────────────────────────────────────
    #  BUSCA AUTOMÁTICA
    # ─────────────────────────────────────

    def _on_search_kind_changed(self, kind: str):
        livre = kind in ("Texto livre", "Regex personalizado")
        self._search_input.setEnabled(livre)
        self._search_input.setPlaceholderText(
            "Digite a expressão regular…" if kind == "Regex personalizado"
            else "Digite o termo…" if livre
            else "Padrão pré-definido — não requer termo"
        )

    def _search_and_redact(self):
        if not self._doc:
            return
        kind = self._search_combo.currentText()
        termo = self._search_input.text().strip()

        if kind in ("Texto livre", "Regex personalizado") and not termo:
            self.status_msg.emit("Digite um termo para buscar")
            return

        if kind == "Regex personalizado":
            try:
                re.compile(termo)
            except re.error as e:
                QMessageBox.warning(
                    self, "Regex inválida",
                    f"A expressão informada não é válida:\n{e}")
                return

        flags = 0 if self._chk_case.isChecked() else re.IGNORECASE

        total_hits = 0
        for pi in self._pages_in_scope(self._scope_combo):
            page = self._doc[pi]
            if kind == "Texto livre":
                rects = list(page.search_for(termo))
            else:
                pattern = termo if kind == "Regex personalizado" else self.PATTERNS[kind]
                rects = []
                for m in re.finditer(pattern, page.get_text("text"), flags):
                    rects.extend(page.search_for(m.group()))

            if rects:
                self._tarjas_por_pagina.setdefault(pi, []).extend(
                    (r, "busca") for r in rects)
                total_hits += len(rects)

        self._visor.redesenhar()
        self._update_tarja_count()
        self._lbl_hits.setText(f"✓ {total_hits} ocorrência(s) tarjada(s)")
        self.status_msg.emit(f"Busca concluída — {total_hits} ocorrência(s) tarjada(s)")

    # ─────────────────────────────────────
    #  SALVAR
    # ─────────────────────────────────────

    def _save_pdf(self):
        if not self._doc:
            return

        if sum(len(v) for v in self._tarjas_por_pagina.values()) == 0:
            QMessageBox.information(
                self, "Sem tarjas",
                "Nenhuma tarja foi adicionada ainda.\n\n"
                "• Arraste o mouse sobre o texto para tarja manual\n"
                "• Use [ ] no texto-fonte e clique em 'Tarjar conteúdo entre [ ]'\n"
                "• Ou use a busca automática")
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Salvar PDF tarjado", "", "Arquivos PDF (*.pdf)")
        if not out_path:
            return
        if not out_path.lower().endswith(".pdf"):
            out_path += ".pdf"

        progress = QProgressDialog("Processando páginas…", None, 0, len(self._doc), self)
        progress.setWindowTitle("Salvando")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        self._save_thread = SaveThread(self._doc, self._tarjas_por_pagina, out_path)
        self._save_thread.progress.connect(lambda c, _t: progress.setValue(c))
        self._save_thread.done.connect(lambda p: self._on_save_done(p, progress))
        self._save_thread.failed.connect(lambda e: self._on_save_error(e, progress))
        self._save_thread.start()

    def _on_save_done(self, path: str, progress: QProgressDialog):
        progress.close()
        QMessageBox.information(
            self, "Salvo com sucesso",
            f"PDF tarjado salvo em:\n{path}\n\n"
            "O texto nas áreas tarjadas foi removido permanentemente.")
        self.status_msg.emit(f"Salvo: {Path(path).name}")

    def _on_save_error(self, err: str, progress: QProgressDialog):
        progress.close()
        QMessageBox.critical(self, "Erro ao salvar", f"Ocorreu um erro:\n{err}")

    # ─────────────────────────────────────
    #  CICLO DE VIDA
    # ─────────────────────────────────────

    def on_activated(self):
        if self._doc:
            self.status_msg.emit(
                f"{self._lbl_file.text()} — {len(self._doc)} página(s)")
        else:
            self.status_msg.emit("Abra um PDF para começar")

    def shutdown(self):
        if self._doc:
            self._doc.close()
            self._doc = None
