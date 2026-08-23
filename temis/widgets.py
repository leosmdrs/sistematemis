"""
Componentes de interface compartilhados por todas as ferramentas.

O que é igual entre as ferramentas mora aqui, e não copiado em cada uma:
a padronização precisa ser estrutural. Se cada ferramenta montasse a sua
própria barra de navegação, elas voltariam a divergir na primeira
alteração — como já aconteceu com o lado do painel lateral e com os
botões de página.

**Convenção de layout de uma ferramenta**

    ┌─────────────┬──────────────────────────┐
    │  PAINEL     │  barra de visualização   │
    │  LATERAL    ├──────────────────────────┤
    │  (esquerda) │                          │
    │             │  conteúdo                │
    │  cabeçalho  │                          │
    │  corpo      │                          │
    │  rodapé     │                          │
    └─────────────┴──────────────────────────┘

  • **cabeçalho** — ação de entrada (abrir/selecionar arquivo), em dourado
  • **corpo**     — controles da ferramenta, rolável
  • **rodapé**    — ação de saída (salvar/gerar/emitir), em verde
  • **barra**     — navegação, zoom e modos de visualização do conteúdo
"""

from PyQt6.QtCore import Qt, QRectF, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QLabel, QLineEdit, QSpinBox, QDoubleSpinBox,
    QVBoxLayout, QHBoxLayout, QPushButton, QScrollArea, QWidget,
)

from .icons import draw_icon
from .theme import PALETTE

#: Largura única do painel lateral em todas as ferramentas.
SIDEBAR_WIDTH = 330

#: Altura única da barra de visualização.
TOOLBAR_HEIGHT = 48


# ─────────────────────────────────────────
#  CAMPOS QUE NÃO ROUBAM A RODA DO MOUSE
# ─────────────────────────────────────────

class NoScrollComboBox(QComboBox):
    """QComboBox que não captura a roda do mouse.

    Dentro de um painel rolável, girar a roda sobre um combo fechado
    trocava o valor selecionado em vez de rolar o painel — alterando
    silenciosamente coisas como o escopo de um tarjamento.
    """

    def __init__(self, parent=None, ajustar_largura: bool = True):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if ajustar_largura:
            # Sem isto, o combo reserva a largura do item mais longo da
            # lista (ex.: "CNPJ (00.000.000/0000-00)") e estoura o painel
            # lateral. Onde a largura já é imposta por fora, a conta é só
            # custo — e pesa quando são dezenas de combos.
            self.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy
                .AdjustToMinimumContentsLengthWithIcon)
            self.setMinimumContentsLength(8)

    def wheelEvent(self, ev):
        ev.ignore()


class NoScrollSpinBox(QSpinBox):
    """QSpinBox que só responde à roda do mouse quando tem o foco."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, ev):
        if self.hasFocus():
            super().wheelEvent(ev)
        else:
            ev.ignore()


class NoScrollDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox que só responde à roda do mouse quando tem o foco."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, ev):
        if self.hasFocus():
            super().wheelEvent(ev)
        else:
            ev.ignore()


# ─────────────────────────────────────────
#  SEPARADORES E RÓTULOS
# ─────────────────────────────────────────

def hsep() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"background: {PALETTE['border']}; border: none;")
    line.setFixedHeight(1)
    return line


def vsep(height: int = 24) -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setStyleSheet(f"background: {PALETTE['border']}; border: none;")
    line.setFixedWidth(1)
    line.setFixedHeight(height)
    return line


def subtext(text: str = "", wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("subtext")
    lbl.setWordWrap(wrap)
    return lbl


def field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {PALETTE['text2']}; font-size: 11px; font-weight: 600;")
    return lbl


def group_title(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"color: {PALETTE['text2']}; font-size: 11px; font-weight: 700;"
        "letter-spacing: 0.6px;")
    return lbl


# ─────────────────────────────────────────
#  BOTÕES PADRÃO
# ─────────────────────────────────────────

def primary_button(text: str, icon: str = "open") -> QPushButton:
    """Ação de entrada da ferramenta — abrir ou selecionar arquivos."""
    btn = QPushButton(f"  {text}")
    btn.setIcon(draw_icon(icon, color="#1A1400"))
    btn.setObjectName("btn_primary")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def output_button(text: str, icon: str = "save") -> QPushButton:
    """Ação de saída da ferramenta — salvar, gerar ou emitir."""
    btn = QPushButton(f"  {text}")
    btn.setIcon(draw_icon(icon, 18, "#06180F"))
    btn.setObjectName("btn_success")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def danger_button(text: str, icon: str = "trash") -> QPushButton:
    """Ação destrutiva — limpar ou remover."""
    btn = QPushButton(f"  {text}")
    btn.setIcon(draw_icon(icon, color=PALETTE["danger"]))
    btn.setObjectName("btn_danger")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


# ─────────────────────────────────────────
#  PAINEL LATERAL
# ─────────────────────────────────────────

class SidebarPanel(QFrame):
    """Painel lateral em três faixas: cabeçalho, corpo rolável e rodapé.

    Fica sempre à esquerda, com a mesma largura em todas as ferramentas.
    O corpo rola; cabeçalho e rodapé permanecem visíveis, para que a ação
    de abrir e a de gerar nunca saiam da tela.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        self.header = QVBoxLayout(header)
        self.header.setContentsMargins(16, 16, 16, 14)
        self.header.setSpacing(10)
        outer.addWidget(header)
        outer.addWidget(hsep())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea {{ background: {PALETTE['surface']}; }}")

        body = QWidget()
        body.setStyleSheet(f"background: {PALETTE['surface']};")
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(16, 16, 16, 16)
        self.body.setSpacing(14)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self._footer_sep = hsep()
        outer.addWidget(self._footer_sep)
        footer = QWidget()
        self.footer = QVBoxLayout(footer)
        self.footer.setContentsMargins(16, 12, 16, 14)
        self.footer.setSpacing(8)
        outer.addWidget(footer)

    def add_note(self, text: str):
        """Nota discreta no rodapé, abaixo da ação de saída."""
        note = QLabel(text)
        note.setObjectName("muted")
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.footer.addWidget(note)


# ─────────────────────────────────────────
#  BARRA DE VISUALIZAÇÃO
# ─────────────────────────────────────────

class ViewerToolbar(QFrame):
    """Ir para página e zoom, idênticos em toda ferramenta.

    Uma implementação só garante que os controles tenham o mesmo rótulo, o
    mesmo ícone, o mesmo atalho na dica e a mesma ordem em todo lugar.

    Não há "anterior"/"próxima": o documento rola de forma contínua, e os
    botões só serviriam para interromper a leitura. Fica o salto direto
    para uma página, que é o caso em que se quer mesmo pular.
    """

    ir_para_pagina = pyqtSignal(int)   # índice 0-based
    zoom_in = pyqtSignal()
    zoom_out = pyqtSignal()
    ajustar_largura = pyqtSignal()

    def __init__(self, parent=None, paginacao: bool = True,
                 zoom: bool = True):
        """A barra é a mesma em toda ferramenta.

        Ferramentas cujo conteúdo não tem página nem ampliação — a leitura
        de metadados, por exemplo — desligam esses trechos em vez de
        exibir controles inertes; a moldura, a altura e o espaçamento
        continuam iguais aos das demais.
        """
        super().__init__(parent)
        self.setObjectName("toolbar_frame")
        self.setFixedHeight(TOOLBAR_HEIGHT)
        self._total = 0

        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(14, 0, 14, 0)
        self._lay.setSpacing(8)

        if not paginacao and not zoom:
            self._campo_page = None
            self._lbl_total = None
            self._lbl_zoom = None
            return

        rot = QLabel("Página:")
        rot.setObjectName("subtext")
        self._lay.addWidget(rot)

        self._campo_page = QLineEdit()
        self._campo_page.setFixedWidth(52)
        self._campo_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._campo_page.setToolTip("Digite o número da página e tecle Enter")
        self._campo_page.setEnabled(False)
        self._campo_page.returnPressed.connect(self._ao_digitar_pagina)
        self._lay.addWidget(self._campo_page)

        self._lbl_total = QLabel("/ —")
        self._lbl_total.setObjectName("page_counter")
        self._lbl_total.setMinimumWidth(46)
        self._lay.addWidget(self._lbl_total)

        self._lay.addWidget(vsep())

        lbl = QLabel("Zoom:")
        lbl.setObjectName("subtext")
        self._lay.addWidget(lbl)

        self._btn_out = QPushButton()
        self._btn_out.setIcon(draw_icon("minus"))
        self._btn_out.setToolTip("Diminuir zoom  (−)")
        self._btn_out.setFixedSize(32, 32)
        self._btn_out.clicked.connect(self.zoom_out)
        self._lay.addWidget(self._btn_out)

        self._lbl_zoom = QLabel("—")
        self._lbl_zoom.setFixedWidth(48)
        self._lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lay.addWidget(self._lbl_zoom)

        self._btn_in = QPushButton()
        self._btn_in.setIcon(draw_icon("plus"))
        self._btn_in.setToolTip("Aumentar zoom  (+)")
        self._btn_in.setFixedSize(32, 32)
        self._btn_in.clicked.connect(self.zoom_in)
        self._lay.addWidget(self._btn_in)

        self._btn_largura = QPushButton("Ajustar")
        self._btn_largura.setToolTip("Ajustar a página à largura da janela")
        self._btn_largura.clicked.connect(self.ajustar_largura)
        self._lay.addWidget(self._btn_largura)

    def _ao_digitar_pagina(self):
        texto = self._campo_page.text().strip()
        if not texto.isdigit():
            self.set_page(self._pagina_atual, self._total)
            return
        numero = max(1, min(self._total, int(texto)))
        self.ir_para_pagina.emit(numero - 1)

    # ── composição ───────────────────────────────────
    def add_separator(self):
        self._lay.addWidget(vsep())

    def add_widget(self, w: QWidget):
        self._lay.addWidget(w)

    def add_hint(self, text: str):
        lbl = QLabel(text)
        lbl.setObjectName("muted")
        self._lay.addWidget(lbl)

    def add_stretch(self):
        self._lay.addStretch()

    # ── estado ───────────────────────────────────────
    _pagina_atual = 0

    def set_page(self, current: int, total: int):
        """`current` é 0-based."""
        self._pagina_atual = current
        self._total = total
        # Não mexe no campo enquanto o usuário digita nele: a rolagem
        # apagaria o número no meio da digitação.
        if not self._campo_page.hasFocus():
            self._campo_page.setText(str(current + 1) if total else "")
        self._campo_page.setEnabled(total > 0)
        self._lbl_total.setText(f"/ {total}" if total else "/ —")

    def set_zoom(self, zoom: float):
        self._lbl_zoom.setText(f"{int(round(zoom * 100))}%")


# ─────────────────────────────────────────
#  DIÁLOGOS
# ─────────────────────────────────────────

def fit_to_screen(dialog, prefer_w: int, prefer_h: int, margin: float = 0.88):
    """Dimensiona o diálogo sem estourar a área útil da tela.

    Um `resize()` fixo assume que a tela é grande o bastante; em telas
    menores o diálogo passava por baixo da barra de tarefas e os botões
    de ação ficavam inalcançáveis.
    """
    screen = None
    parent = dialog.parent()
    if parent is not None and parent.window().windowHandle() is not None:
        screen = parent.window().windowHandle().screen()
    screen = screen or QGuiApplication.primaryScreen()

    if screen is None:
        dialog.resize(prefer_w, prefer_h)
        return

    avail = screen.availableGeometry()
    w = min(prefer_w, int(avail.width() * margin))
    h = min(prefer_h, int(avail.height() * margin))
    dialog.resize(max(w, 420), max(h, 320))

    geo = dialog.frameGeometry()
    geo.moveCenter(avail.center())
    dialog.move(geo.topLeft())


# ─────────────────────────────────────────
#  SINAL DE CARREGAMENTO
# ─────────────────────────────────────────

class Carregando(QWidget):
    """Arco girando, para trechos que levam um instante para montar.

    Existe porque montar um elemento longo — meia centena de parágrafos,
    cada um com a sua caixa de texto — leva um tempo perceptível. Sem
    aviso, a página aparecia pela metade e dava impressão de defeito.
    """

    def __init__(self, texto: str = "Montando o elemento…", parent=None):
        super().__init__(parent)
        self._angulo = 0
        self._texto = texto
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._girar)

    def comecar(self):
        self._angulo = 0
        self._timer.start(60)
        self.update()

    def parar(self):
        self._timer.stop()

    def _girar(self):
        self._angulo = (self._angulo + 30) % 360
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(PALETTE["bg"]))

        lado = 34
        centro = self.rect().center()
        caixa = QRectF(centro.x() - lado / 2, centro.y() - lado / 2 - 14,
                       lado, lado)
        caneta = QPen(QColor(PALETTE["gold"]), 3)
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(caneta)
        # Arco de três quartos: o vão é o que faz o giro ser visível.
        p.drawArc(caixa, -self._angulo * 16, 270 * 16)

        p.setPen(QColor(PALETTE["text2"]))
        p.drawText(self.rect().adjusted(0, 34, 0, 0),
                   int(Qt.AlignmentFlag.AlignHCenter
                       | Qt.AlignmentFlag.AlignVCenter),
                   self._texto)
        p.end()
