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

import math

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QKeySequence, QPainter, QPen,
                         QShortcut)
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

#: A ferramenta que ocupa o centro da constelação; as demais orbitam.
CHAVE_CENTRAL = "ips"

#: Tamanho dos ladrilhos, em pixels de widget.
#:
#: A constelação inteira precisa caber sem barra de rolagem num notebook
#: de catorze polegadas — que, medido, entrega 1310×520 ao portal, seja a
#: 1366×768, seja a 1920×1080 com escala de 150% do Windows.
#:
#: Os números saíram de medição, não de estimativa. A altura mínima em
#: que nenhuma das treze frases perde a última linha é 133, achada por
#: busca binária; a folga até 145 é respiro. A largura é o que deixa a
#: volta se fechar nas três áreas que a janela realmente produz —
#: 1224×650 no tamanho de abertura, 1310×520 no notebook de catorze
#: polegadas e 1220×500 numa janela solta entre as duas. A 172 de
#: largura a última delas já não fecha: oito pares se tocam. Doze
#: ladrilhos de largura fixa sobre uma elipse se encostam bem antes do
#: que o olho supõe.
#:
#: O do centro é maior porque é o procedimento, e os demais o instruem —
#: a diferença de tamanho diz isso sem precisar de legenda. Não pode
#: crescer muito: passando de uns 170 de altura, ele alcança o satélite
#: que fica logo acima.
LADRILHO = (152, 145)
LADRILHO_CENTRO = (200, 166)

#: Proporções internas, acompanhando o tamanho de cada ladrilho.
#: Encolher a moldura sem encolher o conteúdo apertaria o texto contra a
#: borda.
ICONE_LADRILHO = 29
ICONE_CENTRO = 40



class ToolTile(QFrame):
    """Ladrilho clicável do portal: ícone, nome e a frase que resume.

    Vem em duas medidas. A do centro, maior e dourada, é o procedimento;
    as demais, os instrumentos que o instruem.
    """

    clicked = pyqtSignal(str)   # emite meta.key

    def __init__(self, meta: ToolMeta, parent=None, centro: bool = False):
        super().__init__(parent)
        self._meta = meta
        self._centro = centro
        if not meta.available:
            estilo = "tile_soon"
        else:
            estilo = "tile_centro" if centro else "tile"
        self.setObjectName(estilo)
        self.setFixedSize(*(LADRILHO_CENTRO if centro else LADRILHO))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(
            f"{meta.name} — {meta.tagline}"
            + ("" if meta.available else "   (em desenvolvimento)")
        )

        # No centro a moldura é dourada, então o traço do ícone tem de ser
        # escuro para aparecer. Nos demais é o contrário.
        accent = (PALETTE["surface"] if centro and meta.available
                  else PALETTE["gold"] if meta.available
                  else PALETTE["text3"])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 8)
        layout.setSpacing(0)

        # Esticadas dos dois lados: com uma só, o conjunto encostava no
        # topo e sobrava todo o vão embaixo do quadrado.
        layout.addStretch()

        corpo_icone = ICONE_CENTRO if centro else ICONE_LADRILHO
        icon = QLabel()
        icon.setPixmap(draw_icon(meta.icon, corpo_icone, accent, width=2.0)
                       .pixmap(corpo_icone, corpo_icone))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        layout.addSpacing(7)

        name = QLabel(meta.name)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setWordWrap(True)
        cor_nome = (PALETTE["surface"] if centro and meta.available
                    else PALETTE["text"] if meta.available
                    else PALETTE["text2"])
        name.setStyleSheet(
            f"font-size: {15 if centro else 12}px; font-weight: 700; "
            f"color: {cor_nome};"
        )
        layout.addWidget(name)

        layout.addSpacing(5)

        tagline = QLabel(meta.tagline)
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setWordWrap(True)
        cor_frase = (PALETTE["surface2"] if centro and meta.available
                     else PALETTE["text3"])
        tagline.setStyleSheet(
            f"font-size: {11 if centro else 10}px; color: {cor_frase}; "
            f"line-height: 130%;")
        # A frase toma as linhas de que precisar. Havia aqui uma altura
        # fixa de duas linhas, para que os ícones ficassem alinhados ao
        # longo da fileira — e ela cortava a última linha de onze das
        # treze frases, medido. Sem fileiras não há o que alinhar, e a
        # altura do ladrilho já reserva o bastante para a frase mais
        # comprida; as mais curtas apenas sobram em respiro.
        layout.addWidget(tagline)

        layout.addStretch()

        # A faixa "REQUER INTERNET" saiu do ladrilho, mas o aviso não se
        # perdeu: a linha logo acima da constelação nomeia as ferramentas
        # que acessam a rede, e a tela "Sobre" repete. Dizer no quadrado
        # era uma terceira vez, no lugar mais apertado da tela.
        if not meta.available:
            rotulo, obj = "EM BREVE", "badge_soon"
        else:
            rotulo, obj = "", ""
        # A faixa fica presa ao rodapé, fora do empilhamento: se entrasse
        # nele, reservaria altura em todos os ladrilhos e empurraria o
        # conjunto para cima, justamente o que se quer evitar. Assim o
        # ícone, o nome e a frase ficam centrados no quadrado, e a faixa
        # aparece só onde há o que avisar.
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

def enumerar(nomes: list[str]) -> str:
    """Lista nomes em português: "A", "A e B", "A, B e C"."""
    if not nomes:
        return ""
    if len(nomes) == 1:
        return nomes[0]
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]


# ─────────────────────────────────────────
#  CONSTELAÇÃO DO PORTAL
# ─────────────────────────────────────────

class ConstelacaoPortal(QWidget):
    """O procedimento ao centro; os instrumentos em volta, ligados a ele.

    A disposição não é enfeite. As ferramentas existem em função da peça
    que instruem, e uma grade de fileiras iguais diz o contrário — diz
    que são treze coisas equivalentes. Aqui o Encarregado de IPS fica no
    meio, em cor própria e maior, e cada instrumento é ligado a ele por
    uma linha.

    As posições são recalculadas a cada redimensionamento, e não fixadas:
    a elipse se ajusta ao espaço, de modo que o conjunto caiba tanto num
    monitor grande quanto no notebook de catorze polegadas — que é onde
    ele aperta.
    """

    tool_requested = pyqtSignal(str)

    #: Distância mínima que se exige entre dois ladrilhos vizinhos, em
    #: cada eixo. Não é folga estética: abaixo disto as molduras se tocam
    #: e o conjunto vira amontoado.
    FOLGA = 12

    #: Espaço a deixar entre a borda do widget e o ladrilho mais externo.
    MARGEM = 8

    #: Menor área em que a volta ainda se fecha com folga de verdade.
    #:
    #: Medido por busca binária, não estimado: a 500 pixels de altura a
    #: órbita se fecha a partir de 1117 de largura, mas raspando — um
    #: pixel entre dois ladrilhos. Em 1200×500 sobra a folga pedida.
    #:
    #: Declarar o mínimo faz com que, numa janela menor que isso, o
    #: portal role — feio, mas honesto — em vez de sobrepor os ladrilhos,
    #: que seria defeito calado. O notebook de catorze polegadas entrega
    #: 1310×520 ao portal, logo acima deste piso.
    MINIMO = (1200, 500)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._centro: ToolTile | None = None
        self._orbita: list[ToolTile] = []

        for meta, _cls in REGISTRY:
            tile = ToolTile(meta, self, centro=(meta.key == CHAVE_CENTRAL))
            tile.clicked.connect(self.tool_requested)
            if meta.key == CHAVE_CENTRAL and self._centro is None:
                self._centro = tile
            else:
                self._orbita.append(tile)

        # Sem um central declarado, o primeiro do registro assume o posto:
        # melhor um centro arbitrário do que um buraco no meio da tela.
        if self._centro is None and self._orbita:
            self._centro = self._orbita.pop(0)

        self.setMinimumSize(*self.MINIMO)

    # ── geometria ────────────────────────────────
    def _elipse(self) -> tuple[int, int, float, float]:
        """Centro e semieixos da órbita, ajustados ao espaço disponível."""
        largura, altura = LADRILHO
        cx, cy = self.width() / 2, self.height() / 2
        # O ladrilho é posicionado pelo próprio centro sobre a curva, de
        # modo que a elipse tem de recuar meio ladrilho da borda.
        rx = max(largura, cx - largura / 2 - self.MARGEM)
        ry = max(altura, cy - altura / 2 - self.MARGEM)
        return int(cx), int(cy), rx, ry

    #: Passos em que a elipse é percorrida para medir o arco. Não há
    #: fórmula fechada para o perímetro de uma elipse; somar os passos é
    #: exato o bastante para posicionar pixels.
    PASSOS = 1024

    def _arco(self, rx: float, ry: float) -> list[float]:
        """Comprimento de arco acumulado, passo a passo, a partir de 0°."""
        acumulado = [0.0]
        anterior = (rx, 0.0)
        for i in range(1, self.PASSOS + 1):
            t = 2 * math.pi * i / self.PASSOS
            ponto = (rx * math.cos(t), ry * math.sin(t))
            acumulado.append(acumulado[-1]
                             + math.hypot(ponto[0] - anterior[0],
                                          ponto[1] - anterior[1]))
            anterior = ponto
        return acumulado

    def _angulo(self, arco: float, acumulado: list[float]) -> float:
        """O ângulo em que a curva já percorreu esse comprimento de arco.

        Meia volta de recuo no fim: o primeiro satélite fica no alto, e a
        roda segue o sentido horário — que é como se lê uma lista
        disposta em círculo.
        """
        arco %= acumulado[-1]
        baixo, alto = 0, self.PASSOS
        while baixo < alto:
            meio = (baixo + alto) // 2
            if acumulado[meio] < arco:
                baixo = meio + 1
            else:
                alto = meio
        return 2 * math.pi * baixo / self.PASSOS - math.pi / 2

    def _pontos(self) -> list[QPoint]:
        """Onde fica o centro de cada satélite.

        A repartição parte de arco igual, e não de ângulo igual: numa
        elipse achatada o ângulo constante amontoa os ladrilhos nas
        pontas do eixo maior e os rareia em cima e embaixo.

        Mas arco igual, sozinho, também não basta — e isso foi medido,
        não suposto. Dois ladrilhos lado a lado no alto da elipse se
        separam com o arco que vale a largura de um deles; dois na quina,
        onde a curva corre na diagonal, precisam de quase metade a mais
        do mesmo arco para se descolarem. Repartido por igual, o portal
        sobrava em cima e faltava nas quinas, e quatro pares se tocavam
        na tela de catorze polegadas.

        Daí o afrouxamento: enquanto houver par sobreposto, empurra-se
        cada um ao longo da própria curva, na medida da invasão. O que a
        quina toma vem da folga de cima, e nenhum ladrilho sai da elipse
        — de modo que a ligação com o centro continua radial e o desenho,
        redondo.
        """
        cx, cy, rx, ry = self._elipse()
        largura, altura = LADRILHO
        quantos = len(self._orbita)
        if quantos == 0:
            return []

        acumulado = self._arco(rx, ry)
        volta = acumulado[-1]
        posicao = [volta * k / quantos for k in range(quantos)]

        def coordenadas():
            saida = []
            for u in posicao:
                t = self._angulo(u, acumulado)
                saida.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
            return saida

        exigido_x = largura + self.FOLGA
        exigido_y = altura + self.FOLGA
        for _ in range(200):
            pontos = coordenadas()
            empurrao = [0.0] * quantos
            sossegou = True
            for i in range(quantos):
                j = (i + 1) % quantos
                if j == i:
                    break
                ax, ay = pontos[i]
                bx, by = pontos[j]
                invasao = min(exigido_x - abs(ax - bx),
                              exigido_y - abs(ay - by))
                if invasao <= 0:
                    continue
                sossegou = False
                # Um terço da invasão de cada lado por volta: mais que
                # isso faz o anel oscilar sem assentar.
                empurrao[i] -= invasao / 3
                empurrao[j] += invasao / 3
            if sossegou:
                break
            # Nenhum passo maior que um quarto do vão até o vizinho: sem
            # esse limite dois ladrilhos trocam de lugar e o portal muda
            # de ordem a cada redimensionamento.
            for i in range(quantos):
                anterior = (posicao[i] - posicao[i - 1]) % volta
                seguinte = (posicao[(i + 1) % quantos] - posicao[i]) % volta
                limite = min(anterior, seguinte) / 4
                posicao[i] += max(-limite, min(limite, empurrao[i]))

        return [QPoint(int(x), int(y)) for x, y in coordenadas()]

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._reposicionar()

    def showEvent(self, ev):
        # Também aqui, e não só no redimensionamento: um widget pode
        # receber o tamanho sem que o evento de redimensionamento chegue
        # — e aí os treze ladrilhos ficam empilhados no canto superior
        # esquerdo, uns por cima dos outros. Aconteceu ao montar o portal
        # dentro de um pai ainda não exibido.
        super().showEvent(ev)
        self._reposicionar()

    def _reposicionar(self):
        cx, cy, _rx, _ry = self._elipse()
        if self._centro is not None:
            largura, altura = LADRILHO_CENTRO
            self._centro.move(cx - largura // 2, cy - altura // 2)
        largura, altura = LADRILHO
        for tile, p in zip(self._orbita, self._pontos()):
            tile.move(p.x() - largura // 2, p.y() - altura // 2)

    # ── desenho ──────────────────────────────────
    def paintEvent(self, _ev):
        """As linhas que ligam cada instrumento ao procedimento.

        Desenhadas aqui, e não sobre os ladrilhos: os ladrilhos são
        filhos e pintam depois, de modo que as linhas saem de trás deles
        sem cruzar o texto.
        """
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, _rx, _ry = self._elipse()
        meio = QPoint(cx, cy)

        caneta = QPen(QColor(PALETTE["border"]))
        caneta.setWidthF(1.4)
        pintor.setPen(caneta)
        for p in self._pontos():
            pintor.drawLine(meio, p)

        # O nó central, atrás do ladrilho: dá peso ao ponto de encontro
        # das linhas nas frestas entre as quinas.
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor(PALETTE["gold_dim"]))
        pintor.drawEllipse(meio, 7, 7)

    # ── conferência ──────────────────────────────
    def sobreposicoes(self) -> list[tuple[str, str]]:
        """Pares de ladrilhos que se tocam. Existe para ser medido.

        A única forma de saber se a disposição coube é conferir os
        retângulos depois de a janela ter tamanho: não há fórmula que
        substitua isso com ladrilho de largura fixa sobre elipse de
        proporção variável.
        """
        tiles = ([self._centro] if self._centro else []) + self._orbita
        colisoes = []
        for i, a in enumerate(tiles):
            for b in tiles[i + 1:]:
                if a.geometry().intersects(b.geometry()):
                    colisoes.append((a._meta.name, b._meta.name))
        return colisoes

    def transbordo(self) -> list[str]:
        """Ladrilhos que saíram da área visível. Existe para ser medido."""
        area = self.rect()
        return [t._meta.name
                for t in ([self._centro] if self._centro else []) + self._orbita
                if not area.contains(t.geometry())]


class PortalPage(QWidget):
    """Tela inicial: cabeçalho fixo e a grade de ferramentas."""

    tool_requested = pyqtSignal(str)
    about_requested = pyqtSignal()

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
        layout.setContentsMargins(28, 10, 28, 10)
        # Apertado de propósito: o que sobra em cima é altura que falta à
        # constelação, e é a altura que a aperta.
        layout.setSpacing(4)

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
            # Plural correto e redação que serve às duas: uma abre página
            # externa, a outra o sistema que o operador indicar. Dizer
            # "página oficial externa" das duas seria impreciso.
            texto += ("  A ferramenta " if len(online) == 1
                      else "  As ferramentas ")
            texto += enumerar(online)
            texto += (" acessa a rede." if len(online) == 1
                      else " acessam a rede.")
        # A verificação de atualização é acesso à rede, e a promessa acima
        # ficaria pela metade se ela não fosse dita no mesmo lugar.
        texto += ("  Ao abrir, o sistema consulta se há versão nova, sem "
                  "enviar identificação — desligável em Sobre.")
        privacy = QLabel(texto)
        privacy.setObjectName("subtext")
        privacy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Sem quebra, esta linha crescia numa só: a cada ferramenta nova
        # ficava mais comprida, e ao chegar a treze exigia do portal
        # perto de dois mil e oitocentos pixels de largura — medidos —,
        # o que punha barra de rolagem horizontal em qualquer notebook.
        # A largura máxima é para não esticar de ponta a ponta num
        # monitor grande, onde a linha vira uma faixa ilegível.
        privacy.setWordWrap(True)
        privacy.setMaximumWidth(880)
        # Sem esta linha o empilhamento pergunta ao rótulo a altura de
        # que ele precisa **sem saber a largura**, recebe a de uma linha
        # só e reserva isso — as outras duas linhas ficam por baixo do
        # título e da constelação. Rótulo que quebra só responde certo
        # quando lhe perguntam junto com a largura, e é este ajuste de
        # política que faz o layout perguntar assim.
        politica = privacy.sizePolicy()
        politica.setHeightForWidth(True)
        privacy.setSizePolicy(politica)
        # Centrado por esticadas, e não por alinhamento: alinhar ao
        # centro dá ao rótulo a largura que ele pede, e rótulo que quebra
        # pede pouca — ele encolhia a duzentos e trinta pixels e caía em
        # sete linhas. Assim ele ocupa três quintos da faixa, até o teto
        # de 880.
        faixa = QHBoxLayout()
        faixa.setContentsMargins(0, 0, 0, 0)
        faixa.addStretch(1)
        faixa.addWidget(privacy, 3)
        faixa.addStretch(1)
        layout.addLayout(faixa)

        layout.addSpacing(10)

        # A constelação toma toda a altura que sobrar: ela não tem tamanho
        # "certo", tem o espaço que houver, e recalcula as posições a cada
        # redimensionamento.
        self._constelacao = ConstelacaoPortal()
        self._constelacao.tool_requested.connect(self.tool_requested)
        layout.addWidget(self._constelacao, 1)

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

        # Antes de "Sobre", porque a dúvida de quem abre uma ferramenta
        # pela primeira vez é o que ela faz — não quem escreveu o sistema.
        ajuda = QPushButton("  Como usar")
        ajuda.setIcon(draw_icon("manual", 16, PALETTE["gold"]))
        ajuda.setToolTip(f"Para que serve a {meta.name} e como utilizá-la")
        ajuda.setCursor(Qt.CursorShape.PointingHandCursor)
        ajuda.clicked.connect(self._abrir_guia)
        bl.addWidget(ajuda)

        about = QPushButton("  Sobre")
        about.setIcon(draw_icon("info", 16, PALETTE["text2"]))
        about.setCursor(Qt.CursorShape.PointingHandCursor)
        about.clicked.connect(self.about_requested)
        bl.addWidget(about)

        layout.addWidget(bar)
        layout.addWidget(hsep())
        layout.addWidget(tool, 1)

    def _abrir_guia(self):
        from .guias import GuiaDialog
        GuiaDialog(self.tool.meta, self).exec()


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
