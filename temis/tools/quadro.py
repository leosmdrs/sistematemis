"""
Quadro de Evidências — mural de vínculos da investigação.

Anotações, imagens e marcações espalhadas numa tela infinita e ligadas por
barbante, organizadas por caso. Serve para enxergar as relações entre
pessoas, fatos e provas antes de redigir a peça.

O fluxo pretendido é direto: coloque as peças da investigação no quadro,
escreva sobre elas e ligue o que se relaciona. Por isso a anotação é
editada no próprio quadro (duplo clique), a ferramenta volta sozinha para
"Selecionar" depois de criar um item, e todo passo é desfazível.
"""

from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer, pyqtSignal, QSizeF
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QKeySequence, QImage, QPainter, QPainterPath,
    QPainterPathStroker, QPen, QPixmap, QShortcut, QPageSize, QPdfWriter,
    QGuiApplication, QTextOption,
)
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QFrame, QMessageBox, QGraphicsScene, QGraphicsView, QGraphicsItem,
    QGraphicsPathItem, QGraphicsTextItem, QButtonGroup, QTextEdit,
    QInputDialog, QGridLayout, QDialog, QListWidget, QListWidgetItem,
)

from ..icons import draw_icon
from ..theme import PALETTE
from ..widgets import (
    NoScrollComboBox, SidebarPanel, TOOLBAR_HEIGHT, danger_button,
    field_label, fit_to_screen, group_title, output_button, primary_button,
    subtext, vsep,
)
from .base import ToolPage, ToolMeta
from . import quadro_core as core


META = ToolMeta(
    key="quadro",
    name="Quadro de Evidências",
    icon="tool_quadro",
    tagline="Mural de vínculos da investigação",
    description=(
        "Mural livre para mapear a apuração: anotações, imagens e marcações "
        "conectadas por vínculos, organizadas por caso. Serve para enxergar "
        "as relações entre pessoas, fatos e provas antes de redigir a peça."
    ),
)

#: (chave, rótulo, ícone, dica)
FERRAMENTAS = [
    ("selecionar", "Selecionar", "cursor",
     "Selecionar, mover e editar  (V)\nDuplo clique numa anotação para escrever"),
    ("mover", "Mover", "hand",
     "Arrastar o quadro  (H, ou segure a barra de espaço)"),
    ("nota", "Nota", "note", "Adicionar anotação  (N)"),
    ("imagem", "Imagem", "image", "Adicionar imagem  (I)"),
    ("marcacao", "Marcação", "highlight", "Destacar uma área  (M)"),
    ("conectar", "Conectar", "link", "Ligar dois itens  (C)"),
    ("apagar", "Apagar", "trash", "Apagar item ou vínculo  (Del)"),
]

#: Ferramentas que criam algo e devolvem o controle para "Selecionar".
FERRAMENTAS_DE_CRIACAO = {"nota", "imagem", "marcacao"}

PIN_R = 7.0
HANDLE = 18.0
GRADE_PASSO = 20
LIMITE_HISTORICO = 60

PLACEHOLDER = "Duplo clique para escrever"


# ─────────────────────────────────────────
#  EDIÇÃO DE TEXTO NO PRÓPRIO QUADRO
# ─────────────────────────────────────────

class _EditorTexto(QGraphicsTextItem):
    """Caixa de edição que aparece sobre a anotação no duplo clique."""

    def __init__(self, dono: "NodeItem"):
        super().__init__(dono)
        self._dono = dono
        self.setDefaultTextColor(QColor("#222222"))
        fonte = QFont("Georgia", dono.node.fonte)
        fonte.setStyleHint(QFont.StyleHint.Serif)
        self.setFont(fonte)
        self.setTextWidth(dono.node.largura - 24)
        self.setPos(12, 12)
        self.setPlainText(dono.node.texto)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.document().setDefaultTextOption(
            QTextOption(Qt.AlignmentFlag.AlignLeft))

    def focusOutEvent(self, ev):
        super().focusOutEvent(ev)
        self._dono.terminar_edicao(salvar=True)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self._dono.terminar_edicao(salvar=False)
            return
        # Enter quebra linha; Ctrl+Enter encerra a edição.
        if (ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and ev.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._dono.terminar_edicao(salvar=True)
            return
        super().keyPressEvent(ev)


# ─────────────────────────────────────────
#  ITENS DO QUADRO
# ─────────────────────────────────────────

class NodeItem(QGraphicsItem):
    """Anotação, imagem ou marcação sobre o quadro."""

    def __init__(self, node: core.Node, pixmap: QPixmap | None = None):
        super().__init__()
        self.node = node
        self._pixmap = pixmap
        self._redimensionando = False
        self._editor: _EditorTexto | None = None
        self._origem_conexao = False

        self.setPos(node.x, node.y)
        self.setZValue(node.z)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

    # ── geometria ────────────────────────────────
    def boundingRect(self) -> QRectF:
        # Folga acima para o alfinete, desenhado meio para fora do corpo.
        return QRectF(-6, -PIN_R - 6,
                      self.node.largura + 12, self.node.altura + PIN_R + 12)

    def corpo(self) -> QRectF:
        return QRectF(0, 0, self.node.largura, self.node.altura)

    def pino_cena(self) -> QPointF:
        """Ancoragem do barbante: o alfinete, no topo do item."""
        return self.mapToScene(QPointF(self.node.largura / 2, 0))

    def _area_handle(self) -> QRectF:
        return QRectF(self.node.largura - HANDLE, self.node.altura - HANDLE,
                      HANDLE, HANDLE)

    def editando(self) -> bool:
        return self._editor is not None

    # ── pintura ──────────────────────────────────
    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.corpo()
        tipo = self.node.tipo

        if tipo == "marcacao":
            cor = QColor(self.node.cor)
            cor.setAlphaF(core.MARCACAO_ALPHA)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(cor)
            p.drawRoundedRect(r, 5, 5)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 46))
            p.drawRect(r.translated(4, 4))

            if tipo == "nota":
                p.setBrush(QColor(self.node.cor))
                p.drawRect(r)
                if not self.editando():
                    self._paint_texto(p, r)
            else:
                p.setBrush(QColor("#FFFFFF"))
                p.drawRect(r)
                p.setPen(QPen(QColor("#DDDDDD"), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))
                self._paint_imagem(p, r)

            self._paint_pino(p, r)

        if self._origem_conexao:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(core.CORDAO), 3, Qt.PenStyle.DashLine))
            p.drawRect(r.adjusted(-3, -3, 3, 3))
        elif self.isSelected():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(core.SELECAO), 2))
            p.drawRect(r)
            if not self.editando():
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(core.SELECAO))
                h = self._area_handle()
                p.drawRect(QRectF(h.right() - 10, h.bottom() - 10, 10, 10))

    def _paint_pino(self, p: QPainter, r: QRectF):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawEllipse(QPointF(r.width() / 2 + 1.5, 1.5), PIN_R, PIN_R)
        p.setBrush(QColor(core.CORDAO))
        p.drawEllipse(QPointF(r.width() / 2, 0), PIN_R, PIN_R)
        p.setBrush(QColor(255, 255, 255, 90))
        p.drawEllipse(QPointF(r.width() / 2 - 2, -2), PIN_R * 0.32, PIN_R * 0.32)

    def _paint_texto(self, p: QPainter, r: QRectF):
        texto = self.node.texto
        p.setPen(QColor("#222222") if texto else QColor(0, 0, 0, 80))
        f = QFont("Georgia", self.node.fonte)
        f.setStyleHint(QFont.StyleHint.Serif)
        f.setItalic(not texto)
        p.setFont(f)
        p.drawText(
            r.adjusted(12, 12, -12, -12),
            int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
                | Qt.TextFlag.TextWordWrap),
            texto or PLACEHOLDER,
        )

    def _paint_imagem(self, p: QPainter, r: QRectF):
        if self._pixmap is None or self._pixmap.isNull():
            p.setPen(QColor("#B3261E"))
            p.drawText(r, int(Qt.AlignmentFlag.AlignCenter
                              | Qt.TextFlag.TextWordWrap),
                       "imagem não encontrada")
            return
        area = r.adjusted(10, 10, -10, -26)
        if area.width() < 4 or area.height() < 4:
            return
        escala = self._pixmap.scaled(
            area.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(
            QPointF(area.center().x() - escala.width() / 2,
                    area.center().y() - escala.height() / 2), escala)
        if self.node.texto:
            p.setPen(QColor("#444444"))
            f = QFont("Georgia", 9)
            f.setStyleHint(QFont.StyleHint.Serif)
            p.setFont(f)
            p.drawText(QRectF(r.left() + 8, r.bottom() - 24, r.width() - 16, 20),
                       int(Qt.AlignmentFlag.AlignCenter), self.node.texto)

    # ── edição no local ──────────────────────────
    def iniciar_edicao(self):
        if self.node.tipo != "nota" or self._editor is not None:
            return
        # Arrastar enquanto se digita moveria a anotação a cada clique
        # dentro do texto; o movimento volta ao encerrar a edição.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._editor = _EditorTexto(self)
        self._editor.setFocus(Qt.FocusReason.MouseFocusReason)
        cursor = self._editor.textCursor()
        cursor.select(cursor.SelectionType.Document)
        self._editor.setTextCursor(cursor)
        self.update()

    def terminar_edicao(self, salvar: bool = True):
        if self._editor is None:
            return
        novo = self._editor.toPlainText()
        editor, self._editor = self._editor, None
        editor.setParentItem(None)
        cena = self.scene()
        if cena is not None:
            cena.removeItem(editor)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.update()

        if salvar and novo != self.node.texto:
            self.node.texto = novo
            if cena is not None:
                cena.texto_editado.emit(self)

    def mouseDoubleClickEvent(self, ev):
        if self.node.tipo == "nota":
            self.iniciar_edicao()
            ev.accept()
            return
        super().mouseDoubleClickEvent(ev)

    # ── interação ────────────────────────────────
    def hoverMoveEvent(self, ev):
        if self.isSelected() and not self.editando() \
                and self._area_handle().contains(ev.pos()):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(ev)

    def mousePressEvent(self, ev):
        if (self.isSelected() and not self.editando()
                and self._area_handle().contains(ev.pos())):
            self._redimensionando = True
            cena = self.scene()
            if cena is not None:
                cena.antes_de_alterar.emit()
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._redimensionando:
            self.prepareGeometryChange()
            self.node.largura = max(core.TAMANHO_MIN, ev.pos().x())
            self.node.altura = max(core.TAMANHO_MIN, ev.pos().y())
            self.update()
            cena = self.scene()
            if cena is not None:
                cena.atualizar_conexoes(self)
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._redimensionando:
            self._redimensionando = False
            cena = self.scene()
            if cena is not None:
                cena.alterado.emit()
            ev.accept()
            return
        super().mouseReleaseEvent(ev)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.node.x = self.pos().x()
            self.node.y = self.pos().y()
            cena = self.scene()
            if cena is not None:
                cena.atualizar_conexoes(self)
        return super().itemChange(change, value)


class ConexaoItem(QGraphicsPathItem):
    """Barbante entre dois itens."""

    #: Faixa clicável ao redor do traço. Sem ela seria preciso acertar uma
    #: linha de 2px para selecionar ou apagar um vínculo.
    TOLERANCIA = 14.0

    def __init__(self, conexao: core.Conexao, origem: NodeItem, destino: NodeItem):
        super().__init__()
        self.conexao = conexao
        self.origem = origem
        self.destino = destino
        self.setZValue(-2000)      # sempre atrás de tudo, inclusive marcações
        self.setPen(QPen(QColor(conexao.cor), 2.2,
                         Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.recalcular()

    def recalcular(self):
        a = self.origem.pino_cena()
        b = self.destino.pino_cena()
        caminho = QPainterPath(a)
        # Barriga para baixo, como um cordão frouxo entre dois alfinetes.
        meio = QPointF((a.x() + b.x()) / 2,
                       (a.y() + b.y()) / 2 + abs(b.x() - a.x()) * 0.12 + 18)
        caminho.quadTo(meio, b)
        self.prepareGeometryChange()
        self.setPath(caminho)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(self.TOLERANCIA)
        return stroker.createStroke(self.path())

    def boundingRect(self) -> QRectF:
        m = self.TOLERANCIA
        return self.path().boundingRect().adjusted(-m, -m, m, m)

    def hoverEnterEvent(self, ev):
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        super().hoverEnterEvent(ev)

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.isSelected():
            p.setPen(QPen(QColor(core.SELECAO), 5))
            p.drawPath(self.path())
        p.setPen(self.pen())
        p.drawPath(self.path())


# ─────────────────────────────────────────
#  CENA E VISTA
# ─────────────────────────────────────────

class BoardScene(QGraphicsScene):

    alterado = pyqtSignal()
    antes_de_alterar = pyqtSignal()
    texto_editado = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._conexoes: list[ConexaoItem] = []

    def registrar_conexao(self, item: ConexaoItem):
        self._conexoes.append(item)
        self.addItem(item)

    def esquecer_conexao(self, item: ConexaoItem):
        if item in self._conexoes:
            self._conexoes.remove(item)
        self.removeItem(item)

    def conexoes_do_node(self, node_item: NodeItem) -> list[ConexaoItem]:
        return [c for c in self._conexoes
                if c.origem is node_item or c.destino is node_item]

    def atualizar_conexoes(self, node_item: NodeItem):
        for c in self.conexoes_do_node(node_item):
            c.recalcular()

    def limpar_tudo(self):
        self.clear()
        self._conexoes = []


class BoardView(QGraphicsView):
    """Tela do quadro: grade, zoom, deslocamento e ferramentas."""

    alterado = pyqtSignal()
    antes_de_alterar = pyqtSignal()
    status = pyqtSignal(str)
    selecao_mudou = pyqtSignal()
    zoom_mudou = pyqtSignal(float)
    ferramenta_concluida = pyqtSignal()

    ZOOM_MIN, ZOOM_MAX = 0.1, 5.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = BoardScene(self)
        self._scene.setSceneRect(-8000, -8000, 16000, 16000)
        self._scene.alterado.connect(self.alterado)
        self._scene.antes_de_alterar.connect(self.antes_de_alterar)
        self._scene.texto_editado.connect(lambda _i: self.alterado.emit())
        self._scene.selectionChanged.connect(self.selecao_mudou)
        self.setScene(self._scene)

        self.setRenderHints(QPainter.RenderHint.Antialiasing
                            | QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Redesenha a viewport inteira a cada quadro. Com atualização por
        # região, redimensionar um item e recalcular os barbantes ligados a
        # ele deixava rastros das geometrias anteriores na tela. O quadro
        # tem dezenas de itens, não milhares — o custo é irrelevante.
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

        self.caso: core.Caso | None = None
        self.acervo: core.Acervo | None = None
        self._itens: dict[str, NodeItem] = {}
        self._ferramenta = "selecionar"
        self._conectando: NodeItem | None = None
        self._preview: QGraphicsPathItem | None = None
        self._espaco = False
        self._zoom = 1.0
        self._arrastando = False

    # ── fundo ────────────────────────────────────
    def drawBackground(self, p: QPainter, rect: QRectF):
        p.fillRect(rect, QColor(core.FUNDO))
        # Abaixo de ~30% os pontos ficariam mais juntos que a própria
        # grade e virariam um chuvisco cinza, em vez de referência.
        if self._zoom < 0.3:
            return
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(core.GRADE))
        x0 = int(rect.left()) - int(rect.left()) % GRADE_PASSO
        y0 = int(rect.top()) - int(rect.top()) % GRADE_PASSO
        r = 1.0 / max(self._zoom, 0.35)
        y = y0
        while y < rect.bottom():
            x = x0
            while x < rect.right():
                p.drawEllipse(QPointF(x, y), r, r)
                x += GRADE_PASSO
            y += GRADE_PASSO

    # ── caso ─────────────────────────────────────
    def carregar_caso(self, caso: core.Caso, acervo: core.Acervo):
        self.caso = caso
        self.acervo = acervo
        self._cancelar_conexao()
        self._scene.limpar_tudo()
        self._itens = {}

        for node in sorted(caso.nodes, key=lambda n: n.z):
            self._criar_item(node)

        orfas = []
        for conexao in list(caso.conexoes):
            a = self._itens.get(conexao.de)
            b = self._itens.get(conexao.para)
            if a and b:
                self._scene.registrar_conexao(ConexaoItem(conexao, a, b))
            else:
                orfas.append(conexao.id)
        for cid in orfas:
            caso.desconectar(cid)

        self.selecao_mudou.emit()

    def _criar_item(self, node: core.Node) -> NodeItem:
        pix = None
        if node.tipo == "imagem" and node.imagem and self.acervo:
            caminho = self.acervo.caminho_imagem(node.imagem)
            if caminho.exists():
                pix = QPixmap(str(caminho))
        item = NodeItem(node, pix)
        # Item recém-criado precisa obedecer à ferramenta ativa; sem isto
        # ele nascia arrastável mesmo em modos onde nada deve mover.
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                     self._ferramenta == "selecionar")
        self._scene.addItem(item)
        self._itens[node.id] = item
        return item

    # ── ferramentas ──────────────────────────────
    def ferramenta(self) -> str:
        return self._ferramenta

    def definir_ferramenta(self, chave: str):
        self._encerrar_edicoes()
        self._ferramenta = chave
        self._cancelar_conexao()

        if chave == "mover":
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        elif chave == "selecionar":
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)

        cursores = {
            "nota": Qt.CursorShape.CrossCursor,
            "marcacao": Qt.CursorShape.CrossCursor,
            "imagem": Qt.CursorShape.CrossCursor,
            "conectar": Qt.CursorShape.PointingHandCursor,
            "apagar": Qt.CursorShape.PointingHandCursor,
        }
        self.viewport().setCursor(cursores.get(chave, Qt.CursorShape.ArrowCursor))

        movivel = chave == "selecionar"
        for item in self._itens.values():
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movivel)

    def _encerrar_edicoes(self):
        for item in self._itens.values():
            if item.editando():
                item.terminar_edicao(salvar=True)

    # ── criação ──────────────────────────────────
    def adicionar_nota(self, pos: QPointF):
        self.antes_de_alterar.emit()
        node = core.Node(tipo="nota", x=pos.x() - 110, y=pos.y() - 90,
                         largura=220, altura=180, texto="")
        self.caso.adicionar(node)
        item = self._criar_item(node)
        self.alterado.emit()
        self._concluir_criacao(item)
        item.iniciar_edicao()
        self.status.emit("Escreva a anotação — Esc cancela, Ctrl+Enter conclui")

    def adicionar_marcacao(self, pos: QPointF):
        self.antes_de_alterar.emit()
        node = core.Node(tipo="marcacao", x=pos.x() - 150, y=pos.y() - 60,
                         largura=300, altura=120, cor=core.MARCACAO_PADRAO)
        self.caso.adicionar(node)
        item = self._criar_item(node)
        self.alterado.emit()
        self._concluir_criacao(item)
        self.status.emit("Marcação adicionada")

    def adicionar_imagem(self, pos: QPointF, caminho: str | None = None) -> bool:
        if caminho is None:
            caminho, _ = QFileDialog.getOpenFileName(
                self, "Adicionar imagem", "",
                "Imagens (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff)")
            if not caminho:
                return False
        pix = QPixmap(caminho)
        if pix.isNull():
            QMessageBox.warning(
                self, "Imagem inválida",
                f"Não foi possível abrir:\n{Path(caminho).name}")
            return False

        self.antes_de_alterar.emit()
        try:
            nome = self.acervo.guardar_imagem(caminho)
        except OSError as e:
            QMessageBox.critical(self, "Erro",
                                 f"Não foi possível copiar a imagem:\n{e}")
            return False

        larg, alt = self._medida_imagem(pix)
        node = core.Node(tipo="imagem", x=pos.x() - larg / 2, y=pos.y() - alt / 2,
                         largura=larg, altura=alt, imagem=nome,
                         texto=Path(caminho).name)
        self.caso.adicionar(node)
        item = self._criar_item(node)
        self.alterado.emit()
        self._concluir_criacao(item)
        self.status.emit(f"Imagem adicionada: {Path(caminho).name}")
        return True

    def colar_imagem(self, pos: QPointF | None = None):
        cb = QGuiApplication.clipboard()
        img = cb.image()
        if img.isNull():
            # Copiar um arquivo no Explorador coloca a URL, não a imagem.
            md = cb.mimeData()
            if md is not None and md.hasUrls():
                for u in md.urls():
                    c = u.toLocalFile()
                    if c and Path(c).is_file() and not QPixmap(c).isNull():
                        self.adicionar_imagem(
                            pos or self.mapToScene(
                                self.viewport().rect().center()), c)
                        return
            self.status.emit("Não há imagem na área de transferência")
            return

        self.antes_de_alterar.emit()
        nome = self.acervo.guardar_bytes(self._png_bytes(img), ".png")
        pix = QPixmap.fromImage(img)
        larg, alt = self._medida_imagem(pix)
        p = pos or self.mapToScene(self.viewport().rect().center())
        node = core.Node(tipo="imagem", x=p.x() - larg / 2, y=p.y() - alt / 2,
                         largura=larg, altura=alt, imagem=nome,
                         texto="Imagem colada")
        self.caso.adicionar(node)
        item = self._criar_item(node)
        self.alterado.emit()
        self._concluir_criacao(item)
        self.status.emit("Imagem colada da área de transferência")

    def _concluir_criacao(self, item: NodeItem):
        """Seleciona o novo item e devolve o controle para "Selecionar".

        Manter a ferramenta de criação ativa fazia com que o clique dado
        para sair da edição criasse outro item logo em seguida.
        """
        self.definir_ferramenta("selecionar")
        self._scene.clearSelection()
        item.setSelected(True)
        self.ferramenta_concluida.emit()

    @staticmethod
    def _png_bytes(img: QImage) -> bytes:
        from PyQt6.QtCore import QBuffer, QByteArray
        buf = QBuffer(QByteArray())
        buf.open(QBuffer.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        return bytes(buf.data())

    @staticmethod
    def _medida_imagem(pix: QPixmap) -> tuple[float, float]:
        larg = min(pix.width(), core.IMAGEM_LARGURA_MAX)
        escala = larg / max(pix.width(), 1)
        return larg + 20, pix.height() * escala + 36

    # ── apagar / conectar ────────────────────────
    def apagar_selecionados(self) -> int:
        alvos = list(self._scene.selectedItems())
        if not alvos:
            return 0
        self.antes_de_alterar.emit()
        removidos = sum(self._apagar(i) for i in alvos)
        if removidos:
            self.alterado.emit()
            self.status.emit(f"{removidos} item(ns) removido(s)")
        return removidos

    def _apagar(self, item) -> int:
        if isinstance(item, NodeItem):
            item.terminar_edicao(salvar=False)
            for c in self._scene.conexoes_do_node(item):
                self._scene.esquecer_conexao(c)
            self.caso.remover(item.node.id)
            self._itens.pop(item.node.id, None)
            self._scene.removeItem(item)
            return 1
        if isinstance(item, ConexaoItem):
            self.caso.desconectar(item.conexao.id)
            self._scene.esquecer_conexao(item)
            return 1
        return 0

    def _iniciar_conexao(self, item: NodeItem):
        self._conectando = item
        item._origem_conexao = True
        item.update()
        self._preview = QGraphicsPathItem()
        self._preview.setPen(QPen(QColor(core.CORDAO), 2, Qt.PenStyle.DashLine))
        self._preview.setZValue(5000)
        # A linha-guia não pode receber cliques: por estar acima de tudo,
        # ela interceptava o clique no item de destino e a ligação nunca
        # se concluía.
        self._preview.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._preview.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._scene.addItem(self._preview)
        self.status.emit("Agora clique no item de destino  (Esc cancela)")

    def _concluir_conexao(self, item: NodeItem):
        origem = self._conectando
        self._cancelar_conexao()
        if origem is None:
            return
        if origem is item:
            self.status.emit("Ligação cancelada")
            return
        conexao = self.caso.conectar(origem.node.id, item.node.id)
        if conexao is None:
            self.status.emit("Estes itens já estão ligados")
            return
        self.antes_de_alterar.emit()
        self._scene.registrar_conexao(ConexaoItem(conexao, origem, item))
        self.alterado.emit()
        self.status.emit("Vínculo criado")

    def _cancelar_conexao(self):
        if self._preview is not None:
            self._scene.removeItem(self._preview)
            self._preview = None
        if self._conectando is not None:
            self._conectando._origem_conexao = False
            self._conectando.update()
            self._conectando = None

    # ── eventos ──────────────────────────────────
    def mousePressEvent(self, ev):
        if self.caso is None:
            return
        if ev.button() != Qt.MouseButton.LeftButton or self._espaco:
            super().mousePressEvent(ev)
            return

        pos = self.mapToScene(ev.position().toPoint())
        item = self._item_em(ev.position().toPoint())
        node_item = self._node_sob(item)
        f = self._ferramenta

        if f == "nota":
            self.adicionar_nota(pos)
            return
        if f == "marcacao":
            self.adicionar_marcacao(pos)
            return
        if f == "imagem":
            self.adicionar_imagem(pos)
            return
        if f == "apagar":
            alvo = node_item or (item if isinstance(item, ConexaoItem) else None)
            if alvo is not None:
                self.antes_de_alterar.emit()
                if self._apagar(alvo):
                    self.alterado.emit()
                    self.status.emit("Item removido")
            else:
                self.status.emit("Clique sobre um item ou vínculo para apagar")
            return
        if f == "conectar":
            if node_item is None:
                self.status.emit("Clique sobre um item para ligar")
                return
            if self._conectando is None:
                self._iniciar_conexao(node_item)
            else:
                self._concluir_conexao(node_item)
            return

        # Clicar não altera mais a profundidade: a hierarquia é escolha do
        # usuário, e trazer para a frente a cada clique desfaria em silêncio
        # o empilhamento que ele montou.
        super().mousePressEvent(ev)

    def aplicar_profundidade(self, node_id: str, destino) -> bool:
        """Reordena o item e reflete a nova pilha na cena."""
        if self.caso is None or not self.caso.mover_profundidade(node_id, destino):
            return False
        for node in self.caso.nodes:
            item = self._itens.get(node.id)
            if item is not None:
                item.setZValue(node.z)
        self.viewport().update()
        return True

    def _item_em(self, ponto):
        """Primeiro item do quadro sob o ponto, ignorando a linha-guia.

        `itemAt` devolve o item mais ao alto, que durante uma ligação é a
        própria linha-guia — daí a necessidade de percorrer a pilha.
        """
        for it in self.items(ponto):
            if it is self._preview:
                continue
            if isinstance(it, (NodeItem, ConexaoItem)) or it.parentItem() is not None:
                return it
        return None

    @staticmethod
    def _node_sob(item) -> NodeItem | None:
        """Sobe do item clicado até o NodeItem dono, se houver.

        O editor de texto é filho da anotação: sem subir na hierarquia,
        clicar sobre o texto não identificaria o item.
        """
        while item is not None:
            if isinstance(item, NodeItem):
                return item
            item = item.parentItem()
        return None

    def mouseMoveEvent(self, ev):
        if self._conectando is not None and self._preview is not None:
            caminho = QPainterPath(self._conectando.pino_cena())
            caminho.lineTo(self.mapToScene(ev.position().toPoint()))
            self._preview.setPath(caminho)
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        movia = self._arrastando
        super().mouseReleaseEvent(ev)
        if movia:
            self._arrastando = False
            self.alterado.emit()

    def mouseDoubleClickEvent(self, ev):
        if self._ferramenta not in ("selecionar",):
            ev.accept()
            return
        super().mouseDoubleClickEvent(ev)

    def wheelEvent(self, ev):
        passo = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
        self.aplicar_zoom(self._zoom * passo)

    def aplicar_zoom(self, alvo: float):
        alvo = max(self.ZOOM_MIN, min(self.ZOOM_MAX, alvo))
        if abs(alvo - self._zoom) < 1e-4:
            return
        fator = alvo / self._zoom
        self._zoom = alvo
        self.scale(fator, fator)
        self.resetCachedContent()
        self.viewport().update()
        self.zoom_mudou.emit(self._zoom)

    def enquadrar(self):
        area = self.area_conteudo()
        self.fitInView(area, Qt.AspectRatioMode.KeepAspectRatio)
        # fitInView escreve direto na matriz; realinha o contador interno
        # com a escala que de fato ficou aplicada.
        self._zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX,
                                            self.transform().m11()))
        self.viewport().update()
        self.zoom_mudou.emit(self._zoom)

    def zoom(self) -> float:
        return self._zoom

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Space and not ev.isAutoRepeat():
            self._espaco = True
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            return
        if ev.key() == Qt.Key.Key_Escape:
            self._cancelar_conexao()
            self._encerrar_edicoes()
            self._scene.clearSelection()
            return
        if ev.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.apagar_selecionados()
            return
        super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev):
        if ev.key() == Qt.Key.Key_Space and not ev.isAutoRepeat():
            self._espaco = False
            self.definir_ferramenta(self._ferramenta)
            return
        super().keyReleaseEvent(ev)

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls() or ev.mimeData().hasImage():
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev):
        ev.acceptProposedAction()

    def dropEvent(self, ev):
        pos = self.mapToScene(ev.position().toPoint())
        if not ev.mimeData().hasUrls():
            return
        recusados = []
        for u in ev.mimeData().urls():
            caminho = u.toLocalFile()
            if not caminho or not Path(caminho).is_file():
                continue
            if QPixmap(caminho).isNull():
                recusados.append(Path(caminho).name)
                continue
            if self.adicionar_imagem(pos, caminho):
                pos += QPointF(28, 28)
        ev.acceptProposedAction()
        if recusados:
            self.status.emit(
                f"Ignorado(s) por não ser(em) imagem: {', '.join(recusados[:3])}")

    # ── exportação ───────────────────────────────
    def area_conteudo(self) -> QRectF:
        r = self._scene.itemsBoundingRect()
        if r.isEmpty():
            return QRectF(-400, -300, 800, 600)
        return r.adjusted(-40, -40, 40, 40)

    def render_para_imagem(self, escala: float = 2.0) -> QImage:
        self._encerrar_edicoes()
        self._scene.clearSelection()
        area = self.area_conteudo()
        img = QImage(max(1, int(area.width() * escala)),
                     max(1, int(area.height() * escala)),
                     QImage.Format.Format_ARGB32)
        img.fill(QColor(core.FUNDO))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self._scene.render(p, QRectF(img.rect()), area)
        p.end()
        return img


# ─────────────────────────────────────────
#  CASOS SALVOS
# ─────────────────────────────────────────

class CasosDialog(QDialog):
    """Lista os casos gravados no computador, com o conteúdo de cada um."""

    def __init__(self, casos: list[core.Caso], atual: str, acervo: core.Acervo,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Casos salvos")
        fit_to_screen(self, 640, 520)
        self.escolhido: str | None = None
        self._casos = casos

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        titulo = QLabel("Casos salvos neste computador")
        titulo.setObjectName("heading")
        layout.addWidget(titulo)

        caminho = QLabel(str(acervo.raiz))
        caminho.setObjectName("muted")
        caminho.setWordWrap(True)
        caminho.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(caminho)

        self._lista = QListWidget()
        self._lista.setStyleSheet(
            f"QListWidget {{ background: {PALETTE['bg']}; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; }}"
            f"QListWidget::item {{ padding: 10px 12px; "
            f"border-bottom: 1px solid {PALETTE['surface2']}; }}")
        for c in sorted(casos, key=lambda x: -x.atualizado):
            quando = time.strftime("%d/%m/%Y às %H:%M",
                                   time.localtime(c.atualizado))
            marca = "●  " if c.id == atual else "    "
            item = QListWidgetItem(
                f"{marca}{c.nome}\n"
                f"     {len(c.nodes)} item(ns) · {len(c.conexoes)} vínculo(s)"
                f" · alterado em {quando}")
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            if c.id == atual:
                item.setForeground(QColor(PALETTE["gold"]))
            self._lista.addItem(item)
        self._lista.itemDoubleClicked.connect(self._abrir)
        layout.addWidget(self._lista, 1)

        linha = QHBoxLayout()
        linha.setSpacing(8)
        btn_abrir = output_button("Abrir caso")
        btn_abrir.clicked.connect(
            lambda: self._abrir(self._lista.currentItem()))
        linha.addWidget(btn_abrir)
        linha.addStretch()
        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.reject)
        linha.addWidget(fechar)
        layout.addLayout(linha)

        if self._lista.count():
            self._lista.setCurrentRow(0)

    def _abrir(self, item):
        if item is None:
            return
        self.escolhido = item.data(Qt.ItemDataRole.UserRole)
        self.accept()


# ─────────────────────────────────────────
#  FERRAMENTA
# ─────────────────────────────────────────

class QuadroTool(ToolPage):

    meta = META

    def __init__(self, parent=None):
        super().__init__(parent)
        self._acervo = core.Acervo()
        self._casos, atual = self._acervo.carregar()
        self._caso = next(c for c in self._casos if c.id == atual)

        self._historico: list[dict] = []
        self._futuro: list[dict] = []
        self._restaurando = False

        # Gravar a cada tecla faria uma escrita em disco por caractere;
        # o temporizador junta as alterações numa só.
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(700)
        self._save_timer.timeout.connect(self._gravar)

        self._build_ui()
        self._recarregar_casos()
        self._view.carregar_caso(self._caso, self._acervo)
        self._atualizar_propriedades()
        self._apply_shortcuts()
        # Enquadra ao abrir: sem isto, um quadro cujo conteúdo esteja longe
        # da origem aparecia como uma tela vazia.
        QTimer.singleShot(0, self._view.enquadrar)

    # ─────────────────────────────────────
    #  UI
    # ─────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        self._view = BoardView()
        self._view.setAcceptDrops(True)
        self._view.alterado.connect(self._marcar_alterado)
        self._view.antes_de_alterar.connect(self._registrar_historico)
        self._view.status.connect(self.status_msg)
        self._view.selecao_mudou.connect(self._atualizar_propriedades)
        self._view.zoom_mudou.connect(self._mostrar_zoom)
        self._view.ferramenta_concluida.connect(self._sincronizar_botoes)

        ml.addWidget(self._build_toolbar())
        ml.addWidget(self._view, 1)
        root.addWidget(main, 1)

    def _build_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("toolbar_frame")
        frame.setFixedHeight(TOOLBAR_HEIGHT)

        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(6)

        # Ícones sem rótulo: com os sete nomes escritos por extenso a barra
        # não cabia na janela e os textos saíam cortados ("Selecio",
        # "Marcaç"). A dica de cada botão traz o nome e o atalho, e o
        # rótulo da ferramenta ativa fica escrito ao lado do zoom.
        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)
        self._botoes: dict[str, QPushButton] = {}
        for i, (chave, rotulo, icone, dica) in enumerate(FERRAMENTAS):
            btn = QPushButton()
            btn.setIcon(draw_icon(icone, 18, PALETTE["text"]))
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setFixedSize(38, 32)
            btn.setToolTip(f"{rotulo} — {dica}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c, k=chave: self._escolher(k))
            self._grupo.addButton(btn)
            self._botoes[chave] = btn
            lay.addWidget(btn)

        lay.addSpacing(6)
        self._lbl_ferramenta = QLabel("Selecionar")
        self._lbl_ferramenta.setStyleSheet(
            f"color: {PALETTE['gold']}; font-weight: 700;")
        self._lbl_ferramenta.setMinimumWidth(84)
        lay.addWidget(self._lbl_ferramenta)

        lay.addWidget(vsep())

        self._btn_desfazer = QPushButton()
        self._btn_desfazer.setIcon(draw_icon("undo"))
        self._btn_desfazer.setToolTip("Desfazer  (Ctrl+Z)")
        self._btn_desfazer.setFixedSize(32, 32)
        self._btn_desfazer.clicked.connect(self._desfazer)
        self._btn_desfazer.setEnabled(False)
        lay.addWidget(self._btn_desfazer)

        self._btn_refazer = QPushButton()
        self._btn_refazer.setIcon(draw_icon("undo"))
        self._btn_refazer.setToolTip("Refazer  (Ctrl+Y)")
        self._btn_refazer.setFixedSize(32, 32)
        self._btn_refazer.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._btn_refazer.clicked.connect(self._refazer)
        self._btn_refazer.setEnabled(False)
        lay.addWidget(self._btn_refazer)

        lay.addWidget(vsep())

        lbl = QLabel("Zoom:")
        lbl.setObjectName("subtext")
        lay.addWidget(lbl)

        btn_out = QPushButton()
        btn_out.setIcon(draw_icon("minus"))
        btn_out.setToolTip("Diminuir zoom  (−)")
        btn_out.setFixedSize(32, 32)
        btn_out.clicked.connect(lambda: self._zoom(1 / 1.25))
        lay.addWidget(btn_out)

        self._lbl_zoom = QLabel("100%")
        self._lbl_zoom.setFixedWidth(48)
        self._lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._lbl_zoom)

        btn_in = QPushButton()
        btn_in.setIcon(draw_icon("plus"))
        btn_in.setToolTip("Aumentar zoom  (+)")
        btn_in.setFixedSize(32, 32)
        btn_in.clicked.connect(lambda: self._zoom(1.25))
        lay.addWidget(btn_in)

        btn_fit = QPushButton("Enquadrar")
        btn_fit.setToolTip("Enquadrar todo o conteúdo  (F)")
        btn_fit.clicked.connect(self._view_enquadrar)
        lay.addWidget(btn_fit)

        lay.addWidget(vsep())
        self._lbl_dica = QLabel("")
        self._lbl_dica.setObjectName("muted")
        lay.addWidget(self._lbl_dica)
        lay.addStretch()
        return frame

    def _build_sidebar(self) -> SidebarPanel:
        panel = SidebarPanel()

        btn_novo = primary_button("Novo caso", "plus")
        btn_novo.clicked.connect(self._novo_caso)
        panel.header.addWidget(btn_novo)

        self._cb_caso = NoScrollComboBox()
        self._cb_caso.currentIndexChanged.connect(self._trocar_caso)
        panel.header.addWidget(self._cb_caso)

        linha = QHBoxLayout()
        linha.setSpacing(6)
        btn_ren = QPushButton("Renomear")
        btn_ren.clicked.connect(self._renomear_caso)
        linha.addWidget(btn_ren)
        self._btn_excluir = danger_button("Excluir")
        self._btn_excluir.clicked.connect(self._excluir_caso)
        linha.addWidget(self._btn_excluir)
        panel.header.addLayout(linha)

        btn_casos = QPushButton("  Casos salvos…")
        btn_casos.setIcon(draw_icon("open"))
        btn_casos.setToolTip("Ver todos os casos gravados neste computador")
        btn_casos.clicked.connect(self._abrir_gerenciador)
        panel.header.addWidget(btn_casos)

        panel.body.addWidget(group_title("Item selecionado"))
        self._lbl_sel = subtext("Nenhum item selecionado", wrap=True)
        panel.body.addWidget(self._lbl_sel)

        # texto + fonte
        self._box_texto = QWidget()
        bt = QVBoxLayout(self._box_texto)
        bt.setContentsMargins(0, 0, 0, 0)
        bt.setSpacing(6)
        bt.addWidget(field_label("Texto"))
        self._txt = QTextEdit()
        self._txt.setPlaceholderText("Escreva algo…")
        self._txt.setFixedHeight(104)
        self._txt.textChanged.connect(self._texto_alterado)
        bt.addWidget(self._txt)

        linha_fonte = QHBoxLayout()
        linha_fonte.setSpacing(6)
        linha_fonte.addWidget(field_label("Fonte"))
        btn_menor = QPushButton()
        btn_menor.setIcon(draw_icon("minus"))
        btn_menor.setToolTip("Diminuir fonte")
        btn_menor.setFixedSize(28, 26)
        btn_menor.clicked.connect(lambda: self._mudar_fonte(-2))
        linha_fonte.addWidget(btn_menor)
        self._lbl_fonte = QLabel("14")
        self._lbl_fonte.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_fonte.setFixedWidth(28)
        linha_fonte.addWidget(self._lbl_fonte)
        btn_maior = QPushButton()
        btn_maior.setIcon(draw_icon("plus"))
        btn_maior.setToolTip("Aumentar fonte")
        btn_maior.setFixedSize(28, 26)
        btn_maior.clicked.connect(lambda: self._mudar_fonte(2))
        linha_fonte.addWidget(btn_maior)
        linha_fonte.addStretch()
        bt.addLayout(linha_fonte)
        panel.body.addWidget(self._box_texto)

        # cor
        self._box_cor = QWidget()
        bc = QVBoxLayout(self._box_cor)
        bc.setContentsMargins(0, 0, 0, 0)
        bc.setSpacing(6)
        bc.addWidget(field_label("Cor"))
        self._grade_cores = QGridLayout()
        self._grade_cores.setSpacing(6)
        bc.addLayout(self._grade_cores)
        panel.body.addWidget(self._box_cor)

        # Profundidade — o usuário decide o que fica na frente do quê.
        self._box_ordem = QWidget()
        bo = QVBoxLayout(self._box_ordem)
        bo.setContentsMargins(0, 0, 0, 0)
        bo.setSpacing(6)
        bo.addWidget(field_label("Profundidade"))
        grade = QGridLayout()
        grade.setSpacing(6)
        for col, (rotulo, destino, dica) in enumerate((
            ("Fundo", "fundo", "Enviar para o fundo  (Ctrl+Shift+↓)"),
            ("Recuar", -1, "Recuar um nível  (Ctrl+↓)"),
            ("Avançar", +1, "Avançar um nível  (Ctrl+↑)"),
            ("Frente", "topo", "Trazer para a frente  (Ctrl+Shift+↑)"),
        )):
            b = QPushButton(rotulo)
            b.setToolTip(dica)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c, d=destino: self._mudar_ordem(d))
            grade.addWidget(b, col // 2, col % 2)
        bo.addLayout(grade)
        panel.body.addWidget(self._box_ordem)

        self._btn_apagar_sel = danger_button("Remover item")
        self._btn_apagar_sel.clicked.connect(self._remover_selecionados)
        panel.body.addWidget(self._btn_apagar_sel)

        panel.body.addStretch()

        panel.body.addWidget(group_title("Quadro"))
        self._lbl_contagem = subtext("—")
        panel.body.addWidget(self._lbl_contagem)
        btn_limpar = danger_button("Limpar quadro")
        btn_limpar.clicked.connect(self._limpar_quadro)
        panel.body.addWidget(btn_limpar)

        self._btn_export = output_button("Exportar quadro")
        self._btn_export.clicked.connect(self._exportar)
        panel.footer.addWidget(self._btn_export)
        panel.add_note("Os casos ficam gravados neste computador.")
        return panel

    def _apply_shortcuts(self):
        ctx = Qt.ShortcutContext.WidgetWithChildrenShortcut
        for tecla, chave in {"V": "selecionar", "H": "mover", "N": "nota",
                             "I": "imagem", "M": "marcacao",
                             "C": "conectar"}.items():
            QShortcut(QKeySequence(tecla), self,
                      lambda k=chave: self._escolher(k, marcar=True), context=ctx)
        QShortcut(QKeySequence("F"), self, self._view_enquadrar, context=ctx)
        QShortcut(QKeySequence("+"), self, lambda: self._zoom(1.25), context=ctx)
        QShortcut(QKeySequence("-"), self, lambda: self._zoom(1 / 1.25), context=ctx)
        QShortcut(QKeySequence("Ctrl+V"), self,
                  lambda: self._view.colar_imagem(), context=ctx)
        QShortcut(QKeySequence.StandardKey.Undo, self, self._desfazer, context=ctx)
        QShortcut(QKeySequence.StandardKey.Redo, self, self._refazer, context=ctx)
        QShortcut(QKeySequence("Ctrl+Y"), self, self._refazer, context=ctx)
        for atalho, destino in (("Ctrl+Up", +1), ("Ctrl+Down", -1),
                                ("Ctrl+Shift+Up", "topo"),
                                ("Ctrl+Shift+Down", "fundo")):
            QShortcut(QKeySequence(atalho), self,
                      lambda d=destino: self._mudar_ordem(d), context=ctx)

    # ─────────────────────────────────────
    #  DESFAZER / REFAZER
    # ─────────────────────────────────────

    def _registrar_historico(self):
        """Guarda o estado ANTES da alteração que está por vir."""
        if self._restaurando:
            return
        self._historico.append(self._caso.to_dict())
        if len(self._historico) > LIMITE_HISTORICO:
            self._historico.pop(0)
        self._futuro.clear()
        self._atualizar_historico_ui()

    def _aplicar_estado(self, estado: dict):
        self._restaurando = True
        try:
            novo = core.Caso.from_dict(estado)
            idx = self._casos.index(self._caso)
            self._casos[idx] = novo
            self._caso = novo
            self._view.carregar_caso(novo, self._acervo)
            self._atualizar_propriedades()
            self._save_timer.start()
        finally:
            self._restaurando = False
        self._atualizar_historico_ui()

    def _desfazer(self):
        if not self._historico:
            self.status_msg.emit("Nada a desfazer")
            return
        self._futuro.append(self._caso.to_dict())
        self._aplicar_estado(self._historico.pop())
        self.status_msg.emit("Desfeito")

    def _refazer(self):
        if not self._futuro:
            self.status_msg.emit("Nada a refazer")
            return
        self._historico.append(self._caso.to_dict())
        self._aplicar_estado(self._futuro.pop())
        self.status_msg.emit("Refeito")

    def _atualizar_historico_ui(self):
        self._btn_desfazer.setEnabled(bool(self._historico))
        self._btn_refazer.setEnabled(bool(self._futuro))

    # ─────────────────────────────────────
    #  FERRAMENTAS E ZOOM
    # ─────────────────────────────────────

    DICAS = {
        "selecionar": "Duplo clique numa anotação para escrever",
        "mover": "Arraste para deslocar o quadro",
        "nota": "Clique no quadro para colocar a anotação",
        "imagem": "Clique no quadro para escolher a imagem",
        "marcacao": "Clique no quadro para destacar uma área",
        "conectar": "Clique no item de origem e depois no de destino",
        "apagar": "Clique no item ou no vínculo a remover",
    }

    def _escolher(self, chave: str, marcar: bool = False):
        self._view.definir_ferramenta(chave)
        self._sincronizar_botoes()
        rotulo = next(r for k, r, *_ in FERRAMENTAS if k == chave)
        self.status_msg.emit(f"Ferramenta: {rotulo}")

    def _sincronizar_botoes(self):
        atual = self._view.ferramenta()
        for chave, btn in self._botoes.items():
            btn.setChecked(chave == atual)
        rotulo = next((r for k, r, *_ in FERRAMENTAS if k == atual), "")
        self._lbl_ferramenta.setText(rotulo)
        self._lbl_dica.setText(self.DICAS.get(atual, ""))

    def _zoom(self, fator: float):
        self._view.aplicar_zoom(self._view.zoom() * fator)

    def _view_enquadrar(self):
        self._view.enquadrar()

    def _mostrar_zoom(self, z: float):
        self._lbl_zoom.setText(f"{int(round(z * 100))}%")

    # ─────────────────────────────────────
    #  CASOS
    # ─────────────────────────────────────

    def _recarregar_casos(self):
        self._cb_caso.blockSignals(True)
        self._cb_caso.clear()
        for c in self._casos:
            self._cb_caso.addItem(c.nome, c.id)
        idx = next((i for i, c in enumerate(self._casos)
                    if c.id == self._caso.id), 0)
        self._cb_caso.setCurrentIndex(idx)
        self._cb_caso.blockSignals(False)
        self._btn_excluir.setEnabled(len(self._casos) > 1)

    def _abrir_caso(self, caso: core.Caso):
        self._caso = caso
        self._historico.clear()
        self._futuro.clear()
        self._atualizar_historico_ui()
        self._view.carregar_caso(caso, self._acervo)
        self._atualizar_propriedades()
        self._view.enquadrar()

    def _trocar_caso(self, idx: int):
        if idx < 0 or idx >= len(self._casos):
            return
        self._gravar()
        self._abrir_caso(self._casos[idx])
        self.status_msg.emit(f"Caso: {self._caso.nome}")

    def _novo_caso(self):
        nome, ok = QInputDialog.getText(self, "Novo caso", "Nome do caso:")
        if not ok:
            return
        self._gravar()
        caso = core.Caso(nome=nome.strip() or "Novo caso")
        self._casos.append(caso)
        self._abrir_caso(caso)
        self._recarregar_casos()
        self._gravar()
        self.status_msg.emit(f"Caso criado: {caso.nome}")

    def _abrir_gerenciador(self):
        self._gravar()
        dlg = CasosDialog(self._casos, self._caso.id, self._acervo, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.escolhido:
            return
        idx = next((i for i, c in enumerate(self._casos)
                    if c.id == dlg.escolhido), None)
        if idx is not None and self._casos[idx] is not self._caso:
            self._cb_caso.setCurrentIndex(idx)   # dispara _trocar_caso

    def _renomear_caso(self):
        nome, ok = QInputDialog.getText(self, "Renomear caso", "Nome do caso:",
                                        text=self._caso.nome)
        if not ok or not nome.strip():
            return
        self._caso.nome = nome.strip()
        self._recarregar_casos()
        self._gravar()
        self.status_msg.emit(f"Caso renomeado: {self._caso.nome}")

    def _excluir_caso(self):
        if len(self._casos) <= 1:
            return
        if QMessageBox.question(
            self, "Excluir caso",
            f"Excluir o caso “{self._caso.nome}” e tudo o que ele contém?\n\n"
            "Esta ação não pode ser desfeita.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._casos.remove(self._caso)
        self._abrir_caso(self._casos[0])
        self._recarregar_casos()
        self._gravar()
        self._acervo.limpar_imagens_orfas(self._casos)
        self.status_msg.emit("Caso excluído")

    def _limpar_quadro(self):
        if not self._caso.nodes:
            self.status_msg.emit("O quadro já está vazio")
            return
        if QMessageBox.question(
            self, "Limpar quadro",
            f"Remover os {len(self._caso.nodes)} item(ns) e "
            f"{len(self._caso.conexoes)} vínculo(s) deste caso?\n\n"
            "Pode ser desfeito com Ctrl+Z.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._registrar_historico()
        self._caso.limpar()
        self._view.carregar_caso(self._caso, self._acervo)
        self._atualizar_propriedades()
        self._save_timer.start()
        self.status_msg.emit("Quadro limpo")

    # ─────────────────────────────────────
    #  PROPRIEDADES DO ITEM
    # ─────────────────────────────────────

    def _selecionados(self) -> list[NodeItem]:
        return [i for i in self._view.scene().selectedItems()
                if isinstance(i, NodeItem)]

    def _selecionado(self) -> NodeItem | None:
        itens = self._selecionados()
        return itens[0] if len(itens) == 1 else None

    def _atualizar_contagem(self):
        self._lbl_contagem.setText(
            f"{len(self._caso.nodes)} item(ns)  ·  "
            f"{len(self._caso.conexoes)} vínculo(s)")

    def _atualizar_propriedades(self):
        self._atualizar_contagem()
        varios = self._selecionados()
        item = self._selecionado()

        if item is None:
            n = len(varios)
            self._lbl_sel.setText(
                f"{n} itens selecionados" if n > 1
                else "Nenhum item selecionado")
            self._box_texto.setVisible(False)
            self._box_cor.setVisible(False)
            self._box_ordem.setVisible(n > 0)
            # Apagar em lote funciona; deixar o botão inerte com vários
            # itens marcados só confundia.
            self._btn_apagar_sel.setEnabled(n > 0)
            self._btn_apagar_sel.setText(
                "  Remover itens" if n > 1 else "  Remover item")
            return

        node = item.node
        rotulos = {"nota": "Anotação", "imagem": "Imagem", "marcacao": "Marcação"}
        ordem = self._caso.ordem()
        pos = next((i for i, n in enumerate(ordem) if n.id == node.id), 0)
        self._lbl_sel.setText(
            f"{rotulos.get(node.tipo, node.tipo)}  —  "
            f"nível {pos + 1} de {len(ordem)}")
        self._btn_apagar_sel.setEnabled(True)
        self._btn_apagar_sel.setText("  Remover item")
        self._box_ordem.setVisible(True)

        self._box_texto.setVisible(node.tipo in ("nota", "imagem"))
        if node.tipo in ("nota", "imagem"):
            if self._txt.toPlainText() != node.texto:
                self._txt.blockSignals(True)
                self._txt.setPlainText(node.texto)
                self._txt.blockSignals(False)
            self._lbl_fonte.setText(str(node.fonte))

        self._box_cor.setVisible(node.tipo in ("nota", "marcacao"))
        if node.tipo in ("nota", "marcacao"):
            self._montar_cores(
                core.NOTA_CORES if node.tipo == "nota" else core.MARCACAO_CORES,
                node.cor)

    def _montar_cores(self, cores: list[str], atual: str):
        while self._grade_cores.count():
            w = self._grade_cores.takeAt(0).widget()
            if w:
                w.deleteLater()
        for i, cor in enumerate(cores):
            btn = QPushButton()
            btn.setFixedSize(30, 26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            borda = (f"2px solid {PALETTE['text']}" if cor.upper() == atual.upper()
                     else f"1px solid {PALETTE['border']}")
            btn.setStyleSheet(
                f"QPushButton {{ background: {cor}; border: {borda};"
                "border-radius: 5px; }}")
            btn.clicked.connect(lambda _c, k=cor: self._mudar_cor(k))
            self._grade_cores.addWidget(btn, i // 5, i % 5)

    def _mudar_cor(self, cor: str):
        item = self._selecionado()
        if item is None or item.node.cor == cor:
            return
        self._registrar_historico()
        item.node.cor = cor
        item.update()
        self._montar_cores(
            core.NOTA_CORES if item.node.tipo == "nota" else core.MARCACAO_CORES,
            cor)
        self._marcar_alterado()

    def _mudar_ordem(self, destino):
        itens = self._selecionados()
        if not itens:
            self.status_msg.emit("Selecione um item para mudar a profundidade")
            return
        self._registrar_historico()
        mudou = False
        # Ao empurrar vários, começa pelo que está mais próximo do destino
        # para que a ordem relativa entre eles seja preservada.
        ordem = sorted(itens, key=lambda i: i.node.z,
                       reverse=destino in ("topo", +1))
        for item in ordem:
            mudou |= self._view.aplicar_profundidade(item.node.id, destino)
        if mudou:
            self._marcar_alterado()
            nomes = {"topo": "para a frente", "fundo": "para o fundo",
                     1: "um nível à frente", -1: "um nível atrás"}
            self.status_msg.emit(f"Item movido {nomes.get(destino, '')}")
        else:
            self._historico.pop()
            self._atualizar_historico_ui()
            self.status_msg.emit("O item já está nessa posição")

    def _mudar_fonte(self, delta: int):
        item = self._selecionado()
        if item is None:
            return
        novo = max(core.FONTE_MIN, min(core.FONTE_MAX, item.node.fonte + delta))
        if novo == item.node.fonte:
            return
        self._registrar_historico()
        item.node.fonte = novo
        self._lbl_fonte.setText(str(novo))
        item.update()
        self._marcar_alterado()

    def _texto_alterado(self):
        """Digitação no painel lateral.

        Não reconstrói o painel: chamar `setPlainText` a cada tecla
        devolvia o cursor para o início da caixa e tornava impossível
        escrever mais que uma palavra.
        """
        item = self._selecionado()
        if item is None:
            return
        item.node.texto = self._txt.toPlainText()
        item.update()
        self._save_timer.start()
        self._atualizar_contagem()

    def _remover_selecionados(self):
        if self._view.apagar_selecionados():
            self._atualizar_propriedades()

    # ─────────────────────────────────────
    #  PERSISTÊNCIA
    # ─────────────────────────────────────

    def _marcar_alterado(self):
        self._atualizar_propriedades()
        self._save_timer.start()

    def _gravar(self):
        self._caso.atualizado = time.time()
        try:
            self._acervo.gravar(self._casos, self._caso.id)
        except OSError as e:
            self.status_msg.emit(f"Não foi possível gravar o caso: {e}")

    # ─────────────────────────────────────
    #  EXPORTAÇÃO
    # ─────────────────────────────────────

    def _exportar(self):
        if not self._caso.nodes:
            QMessageBox.information(self, "Quadro vazio",
                                    "Adicione itens ao quadro antes de exportar.")
            return
        base = "".join(c for c in self._caso.nome
                       if c.isalnum() or c in " -_").strip() or "quadro"
        caminho, filtro = QFileDialog.getSaveFileName(
            self, "Exportar quadro", f"{base}.png",
            "Imagem PNG (*.png);;Documento PDF (*.pdf)")
        if not caminho:
            return
        try:
            if caminho.lower().endswith(".pdf") or "PDF" in filtro:
                if not caminho.lower().endswith(".pdf"):
                    caminho += ".pdf"
                self._exportar_pdf(caminho)
            else:
                if not caminho.lower().endswith(".png"):
                    caminho += ".png"
                if not self._view.render_para_imagem().save(caminho, "PNG"):
                    raise RuntimeError("o arquivo não pôde ser gravado")
            self.status_msg.emit(f"Quadro exportado: {Path(caminho).name}")
            QMessageBox.information(self, "Exportado",
                                    f"Quadro salvo em:\n{caminho}")
        except Exception as e:
            QMessageBox.critical(self, "Erro ao exportar",
                                 f"Não foi possível exportar:\n{e}")

    def _exportar_pdf(self, caminho: str):
        self._view._encerrar_edicoes()
        self._view.scene().clearSelection()
        area = self._view.area_conteudo()
        writer = QPdfWriter(caminho)
        writer.setPageSize(QPageSize(QSizeF(area.width(), area.height()),
                                     QPageSize.Unit.Point))
        writer.setResolution(150)
        writer.setTitle(f"Quadro de Evidências — {self._caso.nome}")
        p = QPainter(writer)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        destino = QRectF(0, 0, writer.width(), writer.height())
        p.fillRect(destino, QColor(core.FUNDO))
        self._view.scene().render(p, destino, area)
        p.end()

    # ─────────────────────────────────────
    #  CICLO DE VIDA
    # ─────────────────────────────────────

    def on_activated(self):
        self.status_msg.emit(
            f"Caso: {self._caso.nome} — {len(self._caso.nodes)} item(ns)")
        self._view.setFocus()

    def on_deactivated(self):
        self._view._encerrar_edicoes()
        self._gravar()

    def shutdown(self):
        self._view._encerrar_edicoes()
        self._gravar()
