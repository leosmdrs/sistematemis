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

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QColor, QKeySequence, QPainter, QPen,
                         QShortcut)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QVBoxLayout,
    QHBoxLayout, QStackedWidget, QPushButton, QScrollArea, QMessageBox,
    QCheckBox, QDialog, QLineEdit,
)

from . import (__appname__, __author__, __org__, __version__,
               atualizacao, perfil)
from .icons import draw_icon, temis_pixmap, app_icon
from .theme import PALETTE, stylesheet
from .tools import REGISTRY, build_tool, ToolMeta
from .widgets import field_label, fit_to_screen, hsep


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
#: Os números saíram de medição, não de estimativa, e são revistos a
#: cada ferramenta nova — a décima quarta obrigou a refazer a conta, e
#: foi o autoteste quem avisou.
#:
#: A altura é a menor em que nenhum dos catorze nomes ou frases perde a
#: última linha, achada por busca binária. A largura é a que deixa a
#: volta se fechar nas três áreas que a janela realmente produz: 1224×650
#: no tamanho de abertura, 1310×520 no notebook de catorze polegadas
#: maximizado, e 1224×520 numa janela solta entre as duas.
#:
#: A margem é estreita dos dois lados, e por isso medida em vez de
#: arredondada: a 154 de largura o nome quebra numa linha a mais e a
#: altura salta para 159, que aperta a vertical; a 162 dois pares se
#: tocam na janela solta. Entre um e outro, 156 sobra folga de nove
#: pixels no pior caso e treze nos demais.
#:
#: O do centro é maior porque é o procedimento, e os demais o instruem —
#: a diferença de tamanho diz isso sem precisar de legenda.
LADRILHO = (156, 147)
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
    #: Com catorze ferramentas — treze em volta —, a volta ainda se
    #: fecha em 1224×500, com quatro pixels entre os dois ladrilhos mais
    #: próximos; em 1224×510 sobram nove.
    #:
    #: O piso é o segundo, e não o primeiro, porque ele tem de caber no
    #: que a tela realmente entrega. O notebook de catorze polegadas
    #: maximizado dá ao portal 1300×506 — medido —, e um piso de 520 de
    #: altura, que parecia folgado, punha barra de rolagem justamente
    #: nessa tela. Piso alto demais é tão defeito quanto piso baixo
    #: demais: um sobrepõe ladrilho, o outro faz rolar.
    #:
    #: Declarar o mínimo faz com que, numa janela menor que isso, o
    #: portal role — feio, mas honesto — em vez de sobrepor os ladrilhos,
    #: que seria defeito calado. O notebook de catorze polegadas entrega
    #: 1310×520 ao portal, logo acima deste piso.
    MINIMO = (1224, 500)

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
    perfil_requested = pyqtSignal()

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

        identidade = QPushButton("  Identificação")
        identidade.setIcon(draw_icon("cracha", 16, PALETTE["text2"]))
        identidade.setCursor(Qt.CursorShape.PointingHandCursor)
        identidade.setToolTip(
            "Guarda nome, matrícula e lotação para não digitar a cada termo")
        identidade.clicked.connect(self.perfil_requested)
        layout.addWidget(identidade)

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
#  IDENTIFICAÇÃO DO OPERADOR
# ─────────────────────────────────────────

def subtexto_perfil(texto: str) -> QLabel:
    """Explicação curta sob um campo, que quebra e informa a altura certa."""
    rotulo = QLabel(texto)
    rotulo.setObjectName("subtext")
    rotulo.setWordWrap(True)
    politica = rotulo.sizePolicy()
    politica.setHeightForWidth(True)
    rotulo.setSizePolicy(politica)
    return rotulo

class PerfilDialog(QDialog):
    """Onde se guarda nome, matrícula e lotação de quem opera.

    A tela diz, em letras, o que o código garante: isto **preenche**, não
    **assina**. O campo de cada ferramenta continua aberto, e o que valer
    no termo é o que estiver lá na hora de gerar. Sem essa frase, guardar
    a identificação num lugar central pareceria vincular os termos a ela
    — e alguém, com razão, perguntaria depois quem de fato assinou.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Identificação do operador")
        # A altura cresceu com os campos de cargo, órgão e brasão; a
        # área rolável abaixo garante que ela caiba numa tela baixa sem
        # cortar nada — o que já aconteceu aqui uma vez.
        fit_to_screen(self, 560, 700)

        atual = perfil.ler()
        externo = QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        externo.setSpacing(0)

        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        corpo = QWidget()
        lay = QVBoxLayout(corpo)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(10)

        titulo = QLabel("Identificação do operador")
        titulo.setObjectName("heading")
        lay.addWidget(titulo)

        aviso = QLabel(
            "Estes dados são guardados nesta máquina e oferecidos às "
            "ferramentas que pedem identificação, para poupar a digitação "
            "a cada termo.<br><br>"
            "<b>Nada fica preso a eles.</b> Na hora de gerar um termo, o "
            "campo continua aberto: apague e escreva outro nome sempre que "
            "for o caso. O que valer no documento é o que estiver no campo "
            "naquele momento — e um campo já preenchido nunca é alterado "
            "por esta tela.")
        aviso.setObjectName("subtext")
        aviso.setWordWrap(True)
        # Rótulo que quebra só informa a altura certa quando lhe
        # perguntam junto com a largura. Sem esta política o empilhamento
        # reservava a altura de uma linha e cortava o resto do aviso —
        # justamente a parte que diz que a pessoa pode escrever outro
        # nome.
        politica = aviso.sizePolicy()
        politica.setHeightForWidth(True)
        aviso.setSizePolicy(politica)
        lay.addWidget(aviso)

        lay.addSpacing(6)

        self._campos = {}
        for chave, rotulo, exemplo in (
                ("nome", "Nome", "Ex.: João da Silva"),
                ("cargo", "Cargo", "Ex.: Policial Rodoviário Federal"),
                ("matricula", "Matrícula", "Ex.: 1234567"),
                ("lotacao", "Lotação", "Ex.: CGCOR — Brasília/DF"),
                ("orgao", "Órgão", "Ex.: Polícia Rodoviária Federal")):
            lay.addWidget(field_label(rotulo))
            campo = QLineEdit(getattr(atual, chave))
            campo.setPlaceholderText(exemplo)
            self._campos[chave] = campo
            lay.addWidget(campo)

        lay.addSpacing(8)
        lay.addWidget(field_label("Brasão do órgão"))
        lay.addWidget(subtexto_perfil(
            "Opcional. Se houver, sai no alto de cada termo e relatório, "
            "ao lado do nome do órgão. Não havendo, a peça sai sem ele — "
            "a marca do Sistema Têmis aparece sempre."))

        linha_brasao = QHBoxLayout()
        self._vista_brasao = QLabel()
        self._vista_brasao.setFixedSize(96, 64)
        self._vista_brasao.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._vista_brasao.setStyleSheet(
            f"border: 1px dashed {PALETTE['border']}; border-radius: 6px;")
        linha_brasao.addWidget(self._vista_brasao)

        coluna = QVBoxLayout()
        self._b_escolher = QPushButton("  Escolher imagem…")
        self._b_escolher.setIcon(draw_icon("open", 16, PALETTE["text2"]))
        self._b_escolher.setCursor(Qt.CursorShape.PointingHandCursor)
        self._b_escolher.clicked.connect(self._escolher_brasao)
        coluna.addWidget(self._b_escolher)

        self._b_tirar = QPushButton("  Remover o brasão")
        self._b_tirar.setIcon(draw_icon("trash", 16, PALETTE["text2"]))
        self._b_tirar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._b_tirar.clicked.connect(self._remover_brasao)
        coluna.addWidget(self._b_tirar)
        coluna.addStretch()
        linha_brasao.addLayout(coluna, 1)
        lay.addLayout(linha_brasao)

        self._mostrar_brasao()

        lay.addStretch()
        rolagem.setWidget(corpo)
        externo.addWidget(rolagem, 1)

        rodape = QWidget()
        lay = QVBoxLayout(rodape)
        lay.setContentsMargins(24, 10, 24, 16)
        lay.setSpacing(10)
        lay.addWidget(hsep())

        acoes = QHBoxLayout()
        limpar = QPushButton("  Limpar")
        limpar.setIcon(draw_icon("trash", 16, PALETTE["text2"]))
        limpar.setCursor(Qt.CursorShape.PointingHandCursor)
        limpar.setToolTip("Apaga a identificação guardada nesta máquina")
        limpar.clicked.connect(self._limpar)
        acoes.addWidget(limpar)
        acoes.addStretch()

        cancelar = QPushButton("Cancelar")
        cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        cancelar.clicked.connect(self.reject)
        acoes.addWidget(cancelar)

        guardar = QPushButton("  Guardar")
        guardar.setObjectName("primary")
        guardar.setIcon(draw_icon("save", 16, PALETTE["surface"]))
        guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        guardar.setDefault(True)
        guardar.clicked.connect(self._guardar)
        acoes.addWidget(guardar)
        lay.addLayout(acoes)
        externo.addWidget(rodape)

    # ── o brasão ─────────────────────────────
    #: Caixa em que o brasão é guardado, em pixels.
    #:
    #: O dobro da caixa em que o documento o desenha, para que a
    #: impressão em 300 dpi não o veja pixelado. Mais do que isso é peso
    #: à toa: cada termo carrega esta imagem embutida, e um brasão de
    #: dois megabytes viraria dois megabytes em cada peça dos autos.
    #:
    #: Encaixa preservando a proporção, e não força altura: brasão
    #: redondo, faixa larga e escudo alto têm de sair todos no mesmo peso
    #: visual.
    CAIXA_BRASAO = (300, 144)

    def _mostrar_brasao(self):
        from PyQt6.QtGui import QPixmap
        if perfil.tem_brasao():
            pix = QPixmap(str(perfil.caminho_brasao()))
            if not pix.isNull():
                self._vista_brasao.setPixmap(pix.scaled(
                    92, 60, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
                self._b_tirar.setEnabled(True)
                return
        self._vista_brasao.setPixmap(QPixmap())
        self._vista_brasao.setText("sem brasão")
        self._vista_brasao.setStyleSheet(
            f"border: 1px dashed {PALETTE['border']}; border-radius: 6px; "
            f"color: {PALETTE['text3']}; font-size: 10px;")
        self._b_tirar.setEnabled(False)

    def _escolher_brasao(self):
        from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
        from PyQt6.QtGui import QPixmap
        from PyQt6.QtWidgets import QFileDialog

        caminho, _ = QFileDialog.getOpenFileName(
            self, "Escolher o brasão do órgão", "",
            "Imagens (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if not caminho:
            return
        pix = QPixmap(caminho)
        if pix.isNull():
            QMessageBox.warning(
                self, "Imagem não reconhecida",
                "Não foi possível ler esse arquivo como imagem.")
            return
        # Reduzido e convertido para PNG aqui, uma vez, e não a cada
        # termo: o que fica guardado já é exatamente o que vai ao
        # documento.
        pix = pix.scaled(
            *self.CAIXA_BRASAO, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        bytes_ = QByteArray()
        buffer = QBuffer(bytes_)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pix.save(buffer, "PNG")
        buffer.close()
        try:
            perfil.gravar_brasao(bytes(bytes_.data()))
        except OSError as e:                                # noqa: BLE001
            QMessageBox.warning(self, "Não foi possível guardar",
                                f"{type(e).__name__}: {e}")
            return
        self._mostrar_brasao()

    def _remover_brasao(self):
        perfil.remover_brasao()
        self._mostrar_brasao()

    # ── ações ────────────────────────────────
    def _limpar(self):
        for campo in self._campos.values():
            campo.clear()

    def _guardar(self):
        perfil.gravar(perfil.Perfil(
            **{c: w.text().strip() for c, w in self._campos.items()}))
        self.accept()


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

        # O registro da sessão começa aqui, antes de qualquer ferramenta:
        # ele documenta a execução do sistema, e não o uso de uma tela.
        # Se falhar, o sistema abre assim mesmo — registro é acessório
        # ao trabalho, e não pode impedi-lo.
        self._registrador = None
        try:
            from .tools import atividades_core
            self._registrador = atividades_core.Registrador()
            self._registrador.iniciar()
        except Exception:                                   # noqa: BLE001
            pass

        self._build_ui()
        self.go_portal()

        # Regravação periódica, além da que acompanha cada anotação: numa
        # sessão longa e sem eventos, é o que garante que a duração em
        # disco não fique parada na hora em que o sistema abriu.
        if self._registrador is not None:
            from .tools import atividades_core
            self._pulso_registro = QTimer(self)
            self._pulso_registro.setInterval(
                int(atividades_core.INTERVALO_GRAVACAO * 1000))
            self._pulso_registro.timeout.connect(
                lambda: self._registrador.gravar())
            self._pulso_registro.start()

    def _build_ui(self):
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._portal = PortalPage()
        self._portal.tool_requested.connect(self.open_tool)
        self._portal.about_requested.connect(self._show_about)
        self._portal.perfil_requested.connect(self._editar_perfil)
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
        if self._registrador is not None:
            try:
                self._registrador.fechou()
            except Exception:                               # noqa: BLE001
                pass

    def _anotar_atividade(self, ferramenta: str, texto: str):
        if self._registrador is None:
            return
        try:
            self._registrador.anotar(ferramenta, texto)
        except Exception:                                   # noqa: BLE001
            pass

    def open_tool(self, key: str):
        entry = next((e for e in REGISTRY if e[0].key == key), None)
        if entry is None:
            return
        meta, cls = entry

        self._deactivate_current()

        if key not in self._tools:
            tool = build_tool(meta, cls)
            tool.status_msg.connect(self.statusBar().showMessage)
            # A mesma mensagem que informa a barra de status alimenta o
            # relatório de atividades. Sai de graça e é o que há de mais
            # fiel: é a própria ferramenta dizendo o que concluiu, sem
            # que nenhuma delas precise saber que existe um relatório.
            tool.status_msg.connect(
                lambda texto, nome=meta.name: self._anotar_atividade(
                    nome, texto))

            # A tela do relatório precisa do registrador para mostrar a
            # sessão em curso; as demais ferramentas não sabem dele.
            if hasattr(tool, "registrador"):
                tool.registrador = self._registrador

            frame = ToolFrame(tool)
            frame.back_requested.connect(self.go_portal)
            frame.about_requested.connect(self._show_about)

            self._tools[key] = tool
            self._pages[key] = self._stack.addWidget(frame)

        # O perfil é oferecido a cada abertura, e não só na primeira:
        # quem preenche a identificação depois de já ter aberto uma
        # ferramenta encontra os campos preenchidos ao voltar. Campo com
        # conteúdo nunca é tocado — quem apagou e escreveu outra coisa
        # continua com o que escreveu.
        perfil.aplicar(self._tools[key])

        if self._registrador is not None:
            try:
                self._registrador.abriu(key, meta.name)
            except Exception:                               # noqa: BLE001
                pass

        self._stack.setCurrentIndex(self._pages[key])
        self._tools[key].on_activated()

    # ─────────────────────────────────────
    #  SOBRE
    # ─────────────────────────────────────

    def _show_about(self):
        SobreDialog(self).exec()

    def _editar_perfil(self):
        if PerfilDialog(self).exec() != QDialog.DialogCode.Accepted:
            return
        # Vale já para as ferramentas abertas nesta sessão, sem esperar
        # que sejam reabertas — mas só nos campos ainda vazios.
        p = perfil.ler()
        alcancadas = sum(bool(perfil.aplicar(t, p))
                         for t in self._tools.values())
        self.statusBar().showMessage(
            "Identificação guardada nesta máquina."
            + (f"  Preenchida em {alcancadas} ferramenta(s) já aberta(s)."
               if alcancadas else ""), 6000)

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

        # Por último, e dentro de um `try`: o relatório é o registro do
        # que se fez, mas uma falha ao compô-lo não pode impedir o
        # sistema de fechar.
        if self._registrador is not None:
            try:
                self._registrador.encerrar()
            except Exception:                               # noqa: BLE001
                pass

        ev.accept()
