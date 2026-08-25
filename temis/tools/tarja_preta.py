"""
Tarja Preta — tarjamento seguro de PDFs.

As páginas são rasterizadas antes de salvar, de modo que o texto sob a
tarja deixa de existir no arquivo final — não fica apenas encoberto por
um retângulo, como acontece quando se desenha por cima do PDF.
"""

import io
from dataclasses import dataclass
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

@dataclass(frozen=True)
class Palavra:
    """Uma palavra do PDF, com onde ela está e a que linha pertence.

    Vem de `get_text("words")`, que devolve tuplas de oito campos. O
    nome dos campos existe para que o código de seleção se leia: `p.linha`
    diz mais do que `p[6]`.
    """

    retangulo: "fitz.Rect"
    texto: str
    bloco: int
    linha: int
    ordem: int


def palavras_da_pagina(pagina) -> list[Palavra]:
    """As palavras em ordem de leitura, para a seleção com o mouse.

    A ordem importa: selecionar do ponto A ao ponto B é tomar tudo o que
    está entre eles **nessa** ordem, e não tudo o que cai no retângulo
    entre os dois pontos. Quem marca da metade de uma linha até a metade
    da seguinte quer as duas metades inteiras, como em qualquer editor.
    """
    try:
        cruas = pagina.get_text("words")
    except Exception:                                       # noqa: BLE001
        return []
    palavras = [
        Palavra(retangulo=fitz.Rect(p[0], p[1], p[2], p[3]), texto=p[4],
                bloco=int(p[5]), linha=int(p[6]), ordem=int(p[7]))
        for p in cruas
    ]
    palavras.sort(key=lambda p: (p.bloco, p.linha, p.ordem))
    return palavras


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
    fonte_palavras = None     # callable(indice) -> [Palavra, ...]

    #: Como o mouse tarja: desenhando um retângulo ou marcando o texto.
    #:
    #: São dois ofícios diferentes. O retângulo serve ao que não é texto —
    #: uma assinatura digitalizada, uma fotografia, um carimbo — e ao PDF
    #: que não tem camada de texto nenhuma. A seleção serve ao texto, e
    #: acerta o contorno das palavras sem depender do pulso de quem
    #: arrasta: o nome sai coberto rente, sem sobra por cima da linha de
    #: cima nem falta no fim.
    MODO_RETANGULO = "retangulo"
    MODO_TEXTO = "texto"
    modo = MODO_RETANGULO

    def __init__(self, indice: int, parent=None):
        super().__init__(indice, parent)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._origem = QPoint()
        self._rect = QRect()
        self._desenhando = False
        #: Retângulos, em coordenadas do papel, da seleção em curso.
        self._selecao: list = []

    # ── modo de seleção de texto ─────────────────
    def _palavras(self):
        if not callable(self.fonte_palavras):
            return []
        return self.fonte_palavras(self.indice) or []

    def _indice_da_palavra(self, ponto) -> int:
        """A palavra sob o ponto, ou a mais próxima dele.

        "Mais próxima" pesa a distância vertical em dobro: entre uma
        palavra ao lado e outra na linha de cima, quem clica no vão quer
        a da mesma linha — é assim que se lê.
        """
        palavras = self._palavras()
        if not palavras:
            return -1
        alvo = self.para_pdf(QRect(ponto, ponto))
        x, y = alvo.x0, alvo.y0
        melhor, menor = -1, None
        for i, p in enumerate(palavras):
            if p.retangulo.x0 <= x <= p.retangulo.x1 and \
                    p.retangulo.y0 <= y <= p.retangulo.y1:
                return i
            cx = (p.retangulo.x0 + p.retangulo.x1) / 2
            cy = (p.retangulo.y0 + p.retangulo.y1) / 2
            distancia = abs(cx - x) + 2 * abs(cy - y)
            if menor is None or distancia < menor:
                melhor, menor = i, distancia
        return melhor

    def _selecionar(self, de: int, ate: int) -> list:
        """Barras de tarja para o trecho entre duas palavras.

        Uma barra por linha, e não uma por palavra: palavras vizinhas na
        mesma linha viram um retângulo só, de modo que a tarja sai
        contínua em vez de listrada com frestas entre as palavras — e
        pelas frestas se leem as letras que sobram.
        """
        palavras = self._palavras()
        if not palavras or de < 0 or ate < 0:
            return []
        inicio, fim = (de, ate) if de <= ate else (ate, de)
        barras = []
        atual = None
        chave_atual = None
        for p in palavras[inicio:fim + 1]:
            chave = (p.bloco, p.linha)
            if chave != chave_atual:
                if atual is not None:
                    barras.append(atual)
                atual = fitz.Rect(p.retangulo)
                chave_atual = chave
            else:
                atual |= p.retangulo
        if atual is not None:
            barras.append(atual)
        # Uma folga mínima: o retângulo da palavra encosta nas letras, e
        # sem isso sobra um fio da parte de cima dos acentos.
        return [fitz.Rect(b.x0 - 1, b.y0 - 1, b.x1 + 1, b.y1 + 1)
                for b in barras]

    # ── mouse ────────────────────────────────────
    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton or not self.pronta():
            return
        self._origem = ev.position().toPoint()
        self._desenhando = True
        if self.modo == self.MODO_TEXTO:
            self._ancora = self._indice_da_palavra(self._origem)
            self._selecao = self._selecionar(self._ancora, self._ancora)
            self.update()
        else:
            self._rect = QRect(self._origem, QSize())

    def mouseMoveEvent(self, ev):
        if not self._desenhando:
            return
        if self.modo == self.MODO_TEXTO:
            fim = self._indice_da_palavra(ev.position().toPoint())
            self._selecao = self._selecionar(getattr(self, "_ancora", -1), fim)
        else:
            self._rect = QRect(self._origem,
                               ev.position().toPoint()).normalized()
        self.update()

    def mouseReleaseEvent(self, ev):
        if not (self._desenhando and ev.button() == Qt.MouseButton.LeftButton):
            return
        self._desenhando = False

        if self.modo == self.MODO_TEXTO:
            barras = list(self._selecao)
            self._selecao = []
            self.update()
            if barras and callable(self.ao_criar_tarja):
                for b in barras:
                    self.ao_criar_tarja(self.indice, b)
            return

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

        if self._desenhando and self.modo == self.MODO_TEXTO:
            # A seleção em curso aparece em dourado translúcido, e não em
            # preto: enquanto se arrasta, é preciso continuar lendo o que
            # está sendo marcado para saber onde soltar.
            for barra in self._selecao:
                tela = self.para_tela(barra)
                p.fillRect(tela, QColor(255, 204, 0, 90))
                p.setPen(QPen(QColor(PALETTE["gold"]), 1))
                p.drawRect(tela)
        elif self._desenhando and not self._rect.isNull():
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
        #: Palavras já lidas, por página. Ver `_palavras_da`.
        self._palavras_por_pagina: dict[int, list] = {}

        self._build_ui()
        self._apply_shortcuts()

    # ─────────────────────────────────────
    #  ACESSO ÀS TARJAS
    # ─────────────────────────────────────

    def _palavras_da(self, indice: int):
        """Palavras da página, guardadas na primeira vez que se pede.

        Ler é rápido, mas acontece a cada movimento do mouse enquanto se
        arrasta a seleção — e a cada movimento a página inteira seria
        relida. O cache é esvaziado ao abrir outro arquivo.
        """
        if self._doc is None:
            return []
        guardadas = self._palavras_por_pagina.get(indice)
        if guardadas is None:
            guardadas = palavras_da_pagina(self._doc[indice])
            self._palavras_por_pagina[indice] = guardadas
        return guardadas

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
        PaginaTarja.fonte_palavras = self._palavras_da

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

    #: Pares de sinais que podem delimitar o trecho a tarjar.
    #:
    #: O colchete continua sendo o primeiro porque é o que não aparece em
    #: texto corrente — quem escreve "[Fulano]" no rascunho está marcando
    #: de propósito. O parêntese está aqui porque foi pedido, mas é o mais
    #: perigoso dos três: peça jurídica é cheia de parênteses legítimos, e
    #: escolhê-lo tarja todos. A pré-visualização existe justamente para
    #: esse caso.
    PARES = {
        "Colchetes  [ ]": ("[", "]"),
        "Chaves  { }": ("{", "}"),
        "Parênteses  ( )": ("(", ")"),
    }

    def _par_escolhido(self) -> tuple[str, str]:
        return self.PARES.get(self._combo_par.currentText(), ("[", "]"))

    def _group_brackets(self) -> QGroupBox:
        grp = QGroupBox("MARCAÇÃO POR SINAIS")
        grp.setStyleSheet(
            f"QGroupBox {{ border-color: {PALETTE['warning']}55; }}"
            f"QGroupBox::title {{ color: {PALETTE['warning']}; }}"
        )
        lay = QVBoxLayout(grp)
        lay.setSpacing(8)

        self._combo_par = NoScrollComboBox()
        self._combo_par.addItems(list(self.PARES))
        self._combo_par.currentTextChanged.connect(self._ao_trocar_par)
        lay.addWidget(self._combo_par)

        self._info_par = QLabel("")
        self._info_par.setObjectName("subtext")
        self._info_par.setWordWrap(True)
        self._info_par.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self._info_par)

        lay.addLayout(self._scope_row("_bracket_scope_combo"))

        self._btn_bracket = QPushButton("  Tarjar conteúdo entre [ ]")
        self._btn_bracket.setMinimumHeight(30)
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
        self._ao_trocar_par()
        return grp

    def _ao_trocar_par(self, *_a):
        """Reescreve os rótulos com o par escolhido, e avisa do parêntese."""
        abre, fecha = self._par_escolhido()
        ouro = PALETTE["warning"]
        texto = (f"Trechos entre {abre} {fecha} no PDF são tarjados "
                 f"automaticamente.<br>Ex.: "
                 f"<b style='color:{ouro}'>{abre}Fulano de Tal{fecha}</b>")
        if (abre, fecha) == ("(", ")"):
            texto += (f"<br><b style='color:{PALETTE['danger']}'>Atenção:</b> "
                      "parênteses são de uso corrente no texto. Confira na "
                      "pré-visualização antes de tarjar.")
        self._info_par.setText(texto)
        self._btn_bracket.setText(f"  Tarjar conteúdo entre {abre} {fecha}")
        self._lbl_bracket_hits.setText("")
        self._bracket_list.clear()

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

        # O modo fica na barra do visor, e não no painel lateral: ele
        # governa o que o mouse faz sobre a página, e o lugar de um
        # controle é junto daquilo que ele governa.
        self._btn_modo_retangulo = QPushButton("  Retângulo")
        self._btn_modo_retangulo.setIcon(draw_icon("redact", 16,
                                                   PALETTE["text2"]))
        self._btn_modo_retangulo.setCheckable(True)
        self._btn_modo_retangulo.setChecked(True)
        self._btn_modo_retangulo.setToolTip(
            "Arraste para cobrir qualquer área — serve também para "
            "assinatura, foto e carimbo, e para PDF sem camada de texto")
        self._btn_modo_retangulo.clicked.connect(
            lambda: self._definir_modo(PaginaTarja.MODO_RETANGULO))
        bar.add_widget(self._btn_modo_retangulo)

        self._btn_modo_texto = QPushButton("  Selecionar texto")
        self._btn_modo_texto.setIcon(draw_icon("cursor", 16, PALETTE["text2"]))
        self._btn_modo_texto.setCheckable(True)
        self._btn_modo_texto.setToolTip(
            "Marque as palavras como num editor: a tarja acompanha o "
            "contorno delas")
        self._btn_modo_texto.clicked.connect(
            lambda: self._definir_modo(PaginaTarja.MODO_TEXTO))
        bar.add_widget(self._btn_modo_texto)

        bar.add_separator()
        self._dica = bar.add_hint("")
        bar.add_stretch()
        self._definir_modo(PaginaTarja.MODO_RETANGULO)
        return bar

    def _definir_modo(self, modo: str):
        """Troca o que o mouse faz sobre a página.

        O modo é da classe, e não de cada página: o visor cria e descarta
        páginas conforme a rolagem, e guardá-lo em cada uma faria o modo
        se perder ao rolar o documento.
        """
        PaginaTarja.modo = modo
        texto = modo == PaginaTarja.MODO_TEXTO
        self._btn_modo_texto.setChecked(texto)
        self._btn_modo_retangulo.setChecked(not texto)
        # A barra é montada antes do visor existir: na primeira chamada
        # não há página alguma a atualizar, e tentar buscá-las quebrava a
        # abertura da ferramenta.
        visor = getattr(self, "_visor", None)
        for pagina in (visor.paginas() if visor is not None else ()):
            pagina.setCursor(Qt.CursorShape.IBeamCursor if texto
                             else Qt.CursorShape.CrossCursor)
            pagina.update()
        if self._dica is not None:
            self._dica.setText(
                ("Marque as palavras a tarjar   •   Ctrl+Z desfaz"
                 if texto else
                 "Arraste para cobrir a área   •   Ctrl+Z desfaz"))

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
            # Palavras do arquivo anterior não servem ao novo: sem
            # esvaziar, a seleção de texto marcaria onde as palavras
            # estavam no PDF de antes.
            self._palavras_por_pagina = {}
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
        """Retorna {página: [termo, ...]} para cada trecho delimitado.

        O padrão é montado com os sinais escolhidos e **escapado**: sem
        isso, escolher parênteses geraria a expressão `(([^()]+))`, que o
        motor de busca leria como agrupamento e não como o caractere.
        """
        abre, fecha = self._par_escolhido()
        a, f = re.escape(abre), re.escape(fecha)
        pat = re.compile(f"{a}([^{a}{f}]+){f}")
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
            self._lbl_bracket_hits.setText(
            "Nenhum trecho "
            f"{' '.join(self._par_escolhido())} encontrado")
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
            self.status_msg.emit(
                "Nenhum trecho entre "
                f"{' '.join(self._par_escolhido())} "
                "nas páginas selecionadas")
            self._lbl_bracket_hits.setText(
            "Nenhum trecho "
            f"{' '.join(self._par_escolhido())} encontrado")
            return

        total_hits = 0
        for pi, termos in por_pagina.items():
            page = self._doc[pi]
            rects: list[fitz.Rect] = []
            for termo in termos:
                # O par [termo] completo cobre também os colchetes; quando
                # ele não é achado (quebra de linha entre os spans), cai-se
                # no conteúdo interno com uma folga lateral.
                abre, fecha = self._par_escolhido()
                full = page.search_for(f"{abre}{termo}{fecha}")
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
