"""
Casco do Sistema Têmis.

O programa tem dois estados: o **portal**, que lista as ferramentas, e uma
**ferramenta aberta**, que ocupa a tela inteira. Não há barra lateral
permanente — a volta ao portal fica numa barra fina que o casco monta em
volta de cada ferramenta, de modo que as ferramentas não precisam saber
que existe um portal.

A janela não conhece nenhuma ferramenta em particular: monta tudo a
partir de `tools.REGISTRY` e apenas encaminha os sinais de status.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QVBoxLayout,
    QHBoxLayout, QStackedWidget, QPushButton, QScrollArea, QMessageBox,
    QCheckBox, QDialog,
)

from . import (__appname__, __author__, __org__, __version__,
               atualizacao)
from .icons import draw_icon, temis_pixmap, app_icon
from .theme import PALETTE, stylesheet
from .tools import REGISTRY, build_tool, ToolMeta
from .widgets import fit_to_screen, hsep


# ─────────────────────────────────────────
#  LADRILHO DE FERRAMENTA
# ─────────────────────────────────────────

class ToolTile(QFrame):
    """Ladrilho clicável do portal: ícone grande e nome, sem texto extra."""

    clicked = pyqtSignal(str)   # emite meta.key

    def __init__(self, meta: ToolMeta, parent=None):
        super().__init__(parent)
        self._meta = meta
        self.setObjectName("tile" if meta.available else "tile_soon")
        self.setFixedSize(216, 146)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(
            f"{meta.name} — {meta.tagline}"
            + ("" if meta.available else "   (em desenvolvimento)")
        )

        accent = PALETTE["gold"] if meta.available else PALETTE["text3"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 9)
        layout.setSpacing(0)

        # Esticadas dos dois lados: com uma só, o conjunto encostava no
        # topo e sobrava todo o vão embaixo do quadrado.
        layout.addStretch()

        icon = QLabel()
        icon.setPixmap(draw_icon(meta.icon, 38, accent, width=2.0).pixmap(38, 38))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        layout.addSpacing(8)

        name = QLabel(meta.name)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setWordWrap(True)
        name.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: "
            f"{PALETTE['text'] if meta.available else PALETTE['text2']};"
        )
        layout.addWidget(name)

        layout.addSpacing(6)

        tagline = QLabel(meta.tagline)
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setWordWrap(True)
        tagline.setStyleSheet(
            f"font-size: 11px; color: {PALETTE['text3']}; line-height: 130%;")
        # Altura de duas linhas em todos: assim o conteúdo tem a mesma
        # altura em qualquer ladrilho, e os ícones ficam na mesma linha ao
        # longo da fileira mesmo com a frase centrada no quadrado.
        tagline.setFixedHeight(30)
        tagline.setAlignment(Qt.AlignmentFlag.AlignHCenter
                             | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(tagline)

        layout.addStretch()

        # Uma ferramenta que sai da máquina precisa dizer isso no portal:
        # a linha "todo o processamento é local" não pode encobri-la.
        if not meta.available:
            rotulo, obj = "EM BREVE", "badge_soon"
        elif meta.online:
            rotulo, obj = "REQUER INTERNET", "badge_online"
        else:
            rotulo, obj = "", ""
        # A faixa fica presa ao rodapé, fora do empilhamento: se entrasse
        # nele, reservaria altura em todos os ladrilhos e empurraria o
        # conjunto para cima, justamente o que se quer evitar. Assim o
        # ícone, o nome e a frase ficam centrados no quadrado, iguais em
        # todos, e a faixa aparece só onde há o que avisar.
        if rotulo:
            badge = QLabel(rotulo, self)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setObjectName(obj)
            badge.setGeometry(10, self.height() - 26, self.width() - 20, 18)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._meta.key)
        super().mouseReleaseEvent(ev)


# ─────────────────────────────────────────
#  PORTAL
# ─────────────────────────────────────────

def fileiras(total: int, maximo: int = 4) -> list[int]:
    """Como repartir os ladrilhos em fileiras.

    Reparte o mais igualmente possível, respeitando o teto por fileira:
    sete ferramentas saem 4 e 3, e não 4, 4 e 1 — uma fileira com um
    ladrilho solto desequilibra a tela.
    """
    if total <= maximo:
        return [total] if total else []
    linhas = -(-total // maximo)              # arredonda para cima
    base, resto = divmod(total, linhas)
    return [base + (1 if i < resto else 0) for i in range(linhas)]


class PortalPage(QWidget):
    """Tela inicial: cabeçalho fixo e a grade de ferramentas."""

    tool_requested = pyqtSignal(str)
    about_requested = pyqtSignal()

    #: Máximo de ladrilhos por fileira.
    COLUMNS = 4

    def __init__(self, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())
        outer.addWidget(hsep())
        outer.addWidget(self._build_grid(), 1)

    def _build_header(self) -> QFrame:
        """Cabeçalho fixo — fora da área de rolagem, nunca sai da tela."""
        frame = QFrame()
        frame.setObjectName("toolbar_frame")
        frame.setFixedHeight(84)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(28, 0, 24, 0)
        layout.setSpacing(16)

        mark = QLabel()
        mark.setPixmap(temis_pixmap(52))
        mark.setFixedSize(52, 52)
        layout.addWidget(mark)

        # As esticadas prendem os dois rótulos um ao outro e centram o par
        # na altura da barra; sem elas o layout reparte os 84px entre os
        # dois e abre um vão que desliga o subtítulo do nome.
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.setContentsMargins(0, 0, 0, 0)
        titles.addStretch()

        name = QLabel(__appname__)
        name.setStyleSheet(
            f"font-size: 22px; font-weight: 800; color: {PALETTE['text']};"
            "letter-spacing: -0.3px;"
        )
        titles.addWidget(name)

        org = QLabel(__org__)
        org.setStyleSheet(
            f"color: {PALETTE['gold']}; font-size: 12px; font-weight: 600;"
            "letter-spacing: 0.3px;"
        )
        titles.addWidget(org)
        titles.addStretch()

        layout.addLayout(titles)
        layout.addStretch()

        about = QPushButton("  Sobre")
        about.setIcon(draw_icon("info", 16, PALETTE["text2"]))
        about.setCursor(Qt.CursorShape.PointingHandCursor)
        about.clicked.connect(self.about_requested)
        layout.addWidget(about)

        return frame

    def _build_grid(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(6)

        # O bloco inteiro fica centrado na vertical: encostado no topo,
        # sobrava um vazio enorme embaixo em telas grandes.
        layout.addStretch(1)

        pick = QLabel("Selecione uma ferramenta")
        pick.setObjectName("heading")
        pick.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(pick)

        # A frase nomeia a exceção em vez de generalizar: com uma ferramenta
        # que abre página externa, um "tudo é local" seco seria falso.
        online = [m.name for m, _ in REGISTRY if m.online and m.available]
        texto = ("Os arquivos não saem desta máquina: tudo é lido e "
                 "processado aqui.")
        if online:
            texto += (f"  A ferramenta {', '.join(online)} abre uma página "
                      "oficial externa e requer internet.")
        # A verificação de atualização é acesso à rede, e a promessa acima
        # ficaria pela metade se ela não fosse dita no mesmo lugar.
        texto += ("  Ao abrir, o sistema consulta se há versão nova, sem "
                  "enviar identificação — desligável em Sobre.")
        privacy = QLabel(texto)
        privacy.setObjectName("subtext")
        privacy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(privacy)

        layout.addSpacing(28)

        # Cada fileira é centrada por conta própria. Numa grade comum a
        # última fileira incompleta encostaria à esquerda, desequilibrando
        # o conjunto — e ela quase sempre é incompleta.
        inicio = 0
        for quantidade in fileiras(len(REGISTRY), self.COLUMNS):
            row = QHBoxLayout()
            row.setSpacing(18)
            row.addStretch()
            for meta, _cls in REGISTRY[inicio:inicio + quantidade]:
                tile = ToolTile(meta)
                tile.clicked.connect(self.tool_requested)
                row.addWidget(tile)
            row.addStretch()
            layout.addLayout(row)
            layout.addSpacing(18)
            inicio += quantidade

        layout.addStretch(1)

        scroll.setWidget(body)
        return scroll


# ─────────────────────────────────────────
#  MOLDURA DE FERRAMENTA
# ─────────────────────────────────────────

class ToolFrame(QWidget):
    """Envolve uma ferramenta com a barra de retorno ao portal.

    Fica no casco, e não em cada ferramenta, para que uma ferramenta
    continue sendo um widget autônomo — sem saber que existe um portal.
    """

    back_requested = pyqtSignal()
    about_requested = pyqtSignal()

    def __init__(self, tool, parent=None):
        super().__init__(parent)
        self.tool = tool
        meta = tool.meta

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("toolbar_frame")
        bar.setFixedHeight(52)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 0, 16, 0)
        bl.setSpacing(12)

        back = QPushButton("  Portal")
        back.setIcon(draw_icon("arrow_left", 16, PALETTE["gold"]))
        back.setToolTip("Voltar ao portal de ferramentas  (Esc)")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_requested)
        bl.addWidget(back)

        icon = QLabel()
        icon.setPixmap(draw_icon(meta.icon, 20, PALETTE["gold"], 1.9).pixmap(20, 20))
        icon.setFixedSize(20, 20)
        bl.addWidget(icon)

        name = QLabel(meta.name)
        name.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {PALETTE['text']};")
        bl.addWidget(name)

        bl.addStretch()

        about = QPushButton("  Sobre")
        about.setIcon(draw_icon("info", 16, PALETTE["text2"]))
        about.setCursor(Qt.CursorShape.PointingHandCursor)
        about.clicked.connect(self.about_requested)
        bl.addWidget(about)

        layout.addWidget(bar)
        layout.addWidget(hsep())
        layout.addWidget(tool, 1)


# ─────────────────────────────────────────
#  JANELA PRINCIPAL
# ─────────────────────────────────────────

class SobreDialog(QDialog):
    """Quem é o sistema, o que sai da máquina, e a atualização."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Sobre o {__appname__}")
        fit_to_screen(self, 600, 560)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(10)

        topo = QHBoxLayout()
        topo.setSpacing(14)
        marca = QLabel()
        marca.setPixmap(temis_pixmap(64))
        marca.setFixedSize(64, 64)
        topo.addWidget(marca)

        titulos = QVBoxLayout()
        titulos.setSpacing(0)
        titulos.addStretch()
        nome = QLabel(__appname__)
        nome.setObjectName("heading")
        titulos.addWidget(nome)
        org = QLabel(__org__)
        org.setStyleSheet(f"color: {PALETTE['gold']}; font-weight: 600;")
        titulos.addWidget(org)
        titulos.addStretch()
        topo.addLayout(titulos)
        topo.addStretch()
        lay.addLayout(topo)
        lay.addWidget(hsep())

        disponiveis = sum(1 for m, _ in REGISTRY if m.available)
        online = [m.name for m, _ in REGISTRY if m.online and m.available]
        texto = QLabel(
            f"<p>Versão <b>{__version__}</b> — {disponiveis} de "
            f"{len(REGISTRY)} ferramentas disponíveis.</p>"
            "<p>Reúne num só lugar os instrumentos de apoio à atividade de "
            "corregedoria: tarjamento de documentos, integridade de "
            "arquivos, detecção de conteúdo oculto, extração de metadados, "
            "organização de evidências e montagem da Informação.</p>"
            "<p><b>Os arquivos não saem desta máquina.</b> Nenhum documento, "
            "hash ou metadado é enviado a servidor algum — tudo é lido e "
            "processado localmente.</p>"
            "<p>O sistema acessa a rede em apenas duas situações, ambas "
            "visíveis: "
            + (f"a ferramenta <b>{', '.join(online)}</b>, que abre uma "
               "página oficial externa; e " if online else "")
            + "a <b>verificação de atualização</b>, que lê um arquivo de "
            "versão e não envia identificação do usuário nem da estação.</p>"
            f"<p style='margin-top:12px;color:{PALETTE['text2']}'>"
            f"Criado por <b style='color:{PALETTE['text']}'>{__author__}"
            "</b></p>")
        texto.setTextFormat(Qt.TextFormat.RichText)
        texto.setWordWrap(True)
        lay.addWidget(texto)
        lay.addStretch()
        lay.addWidget(hsep())

        prefs = atualizacao.ler_preferencias()
        self._chk_auto = QCheckBox("Verificar atualizações ao abrir o sistema")
        self._chk_auto.setChecked(prefs.verificar)
        self._chk_auto.toggled.connect(self._alternar_verificacao)
        lay.addWidget(self._chk_auto)

        self._estado = QLabel("")
        self._estado.setObjectName("subtext")
        self._estado.setWordWrap(True)
        lay.addWidget(self._estado)

        acoes = QHBoxLayout()
        acoes.setSpacing(8)
        self._btn_verificar = QPushButton("  Verificar agora")
        self._btn_verificar.setIcon(draw_icon("reload", 15, PALETTE["text"]))
        self._btn_verificar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_verificar.clicked.connect(self._verificar)
        acoes.addWidget(self._btn_verificar)
        acoes.addStretch()
        fechar = QPushButton("Fechar")
        fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        fechar.clicked.connect(self.accept)
        acoes.addWidget(fechar)
        lay.addLayout(acoes)

    def _alternar_verificacao(self, ligado: bool):
        prefs = atualizacao.ler_preferencias()
        prefs.verificar = ligado
        atualizacao.gravar_preferencias(prefs)

    def _verificar(self):
        from .atualizacao_ui import verificar_agora
        self._btn_verificar.setEnabled(False)
        self._estado.setText("Consultando…")

        def terminou(mensagem: str):
            self._estado.setText(mensagem)
            self._btn_verificar.setEnabled(True)

        verificar_agora(self, terminou)


class TemisWindow(QMainWindow):

    PORTAL = "__portal__"

    def __init__(self):
        super().__init__()
        self.setWindowTitle(__appname__)
        self.setWindowIcon(app_icon())
        self.resize(1280, 840)
        self.setMinimumSize(940, 620)

        # A folha vai na aplicação, não na janela: diálogos (relatório,
        # "Sobre", mensagens de erro) são janelas de topo e não herdam de
        # forma confiável o estilo do pai — apareciam claros, com texto
        # claro por cima, praticamente ilegíveis.
        app = QApplication.instance()
        (app or self).setStyleSheet(stylesheet())

        self._pages: dict[str, int] = {}
        self._tools: dict[str, object] = {}

        self._build_ui()
        self.go_portal()

    def _build_ui(self):
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._portal = PortalPage()
        self._portal.tool_requested.connect(self.open_tool)
        self._portal.about_requested.connect(self._show_about)
        self._pages[self.PORTAL] = self._stack.addWidget(self._portal)

        bar = self.statusBar()
        self._status_right = QLabel(f"v{__version__}   •   Processamento local")
        self._status_right.setObjectName("muted")
        bar.addPermanentWidget(self._status_right)

        QShortcut(QKeySequence("Ctrl+H"), self, self.go_portal)
        QShortcut(QKeySequence("Esc"), self, self.go_portal)

    # ─────────────────────────────────────
    #  NAVEGAÇÃO
    # ─────────────────────────────────────

    def go_portal(self):
        self._deactivate_current()
        self._stack.setCurrentIndex(self._pages[self.PORTAL])
        self.statusBar().showMessage("Selecione uma ferramenta")

    def _deactivate_current(self):
        current = self._stack.currentWidget()
        tool = getattr(current, "tool", None)
        if tool is not None:
            tool.on_deactivated()

    def open_tool(self, key: str):
        entry = next((e for e in REGISTRY if e[0].key == key), None)
        if entry is None:
            return
        meta, cls = entry

        self._deactivate_current()

        if key not in self._tools:
            tool = build_tool(meta, cls)
            tool.status_msg.connect(self.statusBar().showMessage)

            frame = ToolFrame(tool)
            frame.back_requested.connect(self.go_portal)
            frame.about_requested.connect(self._show_about)

            self._tools[key] = tool
            self._pages[key] = self._stack.addWidget(frame)

        self._stack.setCurrentIndex(self._pages[key])
        self._tools[key].on_activated()

    # ─────────────────────────────────────
    #  SOBRE
    # ─────────────────────────────────────

    def _show_about(self):
        SobreDialog(self).exec()

    # ─────────────────────────────────────
    #  ENCERRAMENTO
    # ─────────────────────────────────────

    def closeEvent(self, ev):
        for tool in self._tools.values():
            if not tool.can_close():
                ev.ignore()
                return
        for tool in self._tools.values():
            tool.shutdown()
        ev.accept()
