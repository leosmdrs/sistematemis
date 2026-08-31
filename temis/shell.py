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


import html as _html
from pathlib import Path

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QColor, QKeySequence,
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

#: Tamanho dos ladrilhos, em pixels de widget.
#:
#: A grade inteira precisa caber sem barra de rolagem num notebook
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
#: Todos da mesma medida: na grade, quem diz a hierarquia é a ordem das
#: fileiras, e um ladrilho fora de medida quebraria o alinhamento.
LADRILHO = (148, 147)

#: Proporções internas, acompanhando o tamanho de cada ladrilho.
#: Encolher a moldura sem encolher o conteúdo apertaria o texto contra a
#: borda.
ICONE_LADRILHO = 29



class ToolTile(QFrame):
    """Ladrilho clicável do portal: ícone, nome e a frase que resume.

    Todos do mesmo tamanho. Houve uma medida maior e dourada, para a
    ferramenta que ficava no centro da constelação; com a grade, a
    hierarquia passou a ser dita pela ordem das fileiras, e um ladrilho
    fora de medida quebraria o alinhamento em vez de destacar.
    """

    clicked = pyqtSignal(str)   # emite meta.key

    def __init__(self, meta: ToolMeta, parent=None):
        super().__init__(parent)
        self._meta = meta
        self.setObjectName("tile" if meta.available else "tile_soon")
        self.setFixedSize(*LADRILHO)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(
            f"{meta.name} — {meta.tagline}"
            + ("" if meta.available else "   (em desenvolvimento)")
        )

        accent = (PALETTE["gold"] if meta.available else PALETTE["text3"])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 8)
        layout.setSpacing(0)

        # Esticadas dos dois lados: com uma só, o conjunto encostava no
        # topo e sobrava todo o vão embaixo do quadrado.
        layout.addStretch()

        corpo_icone = ICONE_LADRILHO
        icon = QLabel()
        icon.setPixmap(draw_icon(meta.icon, corpo_icone, accent, width=2.0)
                       .pixmap(corpo_icone, corpo_icone))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        layout.addSpacing(7)

        name = QLabel(meta.name)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setWordWrap(True)
        cor_nome = (PALETTE["text"] if meta.available
                    else PALETTE["text2"])
        name.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {cor_nome};")
        layout.addWidget(name)

        layout.addSpacing(5)

        tagline = QLabel(meta.tagline)
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setWordWrap(True)
        tagline.setStyleSheet(
            f"font-size: 10px; color: {PALETTE['text3']}; "
            "line-height: 130%;")
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

def ferramentas_online() -> list[str]:
    """As ferramentas disponíveis que saem à rede.

    O portal e o Sobre dizem a mesma coisa ao usuário e por isso partem
    da mesma lista. Já partiram de duas: o Sobre passou versões falando
    no singular de duas ferramentas, e chamando de "página oficial
    externa" o endereço que o operador é quem indica. Promessa de
    privacidade escrita duas vezes é promessa que diverge.
    """
    return [m.name for m, _ in REGISTRY if m.online and m.available]


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

class GradePortal(QWidget):
    """As ferramentas em fileiras de cinco, na ordem do registro.

    Substituiu uma constelação: o Encarregado de IPS ao centro, maior e
    dourado, e os demais em órbita numa elipse, ligados a ele por linhas.
    A disposição afirmava que os instrumentos existem em função da peça
    que instruem, o que é verdade — mas cobrava caro por dizê-lo.
    Catorze ladrilhos sobre uma elipse só fechavam a volta sem
    sobreposição a partir de 1224×500, e cada ferramenta nova apertava a
    volta outra vez: a repartição por arco igual precisou de um
    afrouxamento iterativo para as quinas pararem de se tocar.

    A grade não precisa de nada disso. Cabe em menos tela, a décima sexta
    ferramenta entra sem redesenhar coisa alguma, e a hierarquia que a
    elipse desenhava passa a ser dita pela ordem — o procedimento abre a
    primeira fileira.
    """

    tool_requested = pyqtSignal(str)

    #: Ladrilhos por fileira.
    COLUNAS = 6

    #: Distância entre dois ladrilhos vizinhos, em cada eixo. Não é folga
    #: estética: abaixo disto as molduras se tocam.
    FOLGA = 12

    #: Espaço entre a borda do widget e o ladrilho mais externo.
    MARGEM = 8

    _FILEIRAS = -(-len(REGISTRY) // COLUNAS)

    #: Menor área em que as fileiras cabem inteiras. Calculado, e não
    #: escrito: com a elipse este número era medido a cada ferramenta
    #: nova, e envelhecia calado entre uma medição e outra.
    MINIMO = (COLUNAS * LADRILHO[0] + (COLUNAS - 1) * FOLGA + 2 * MARGEM,
              _FILEIRAS * LADRILHO[1] + (_FILEIRAS - 1) * FOLGA + 2 * MARGEM)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ladrilhos: list[ToolTile] = []
        for meta, _cls in REGISTRY:
            tile = ToolTile(meta, self)
            tile.clicked.connect(self.tool_requested)
            self._ladrilhos.append(tile)
        self.setMinimumSize(*self.MINIMO)

    # ── geometria ────────────────────────────────
    def _reposicionar(self):
        """Assenta a grade no meio do espaço disponível."""
        if not self._ladrilhos:
            return
        largura, altura = LADRILHO
        colunas = self.COLUNAS
        quantos = len(self._ladrilhos)
        fileiras = -(-quantos // colunas)

        passo_x = largura + self.FOLGA
        passo_y = altura + self.FOLGA
        bloco_l = colunas * largura + (colunas - 1) * self.FOLGA
        bloco_a = fileiras * altura + (fileiras - 1) * self.FOLGA
        x0 = max(self.MARGEM, (self.width() - bloco_l) // 2)
        y0 = max(self.MARGEM, (self.height() - bloco_a) // 2)

        for i, tile in enumerate(self._ladrilhos):
            fileira, coluna = divmod(i, colunas)
            # Fileira incompleta fica centrada sob as demais. Encostada à
            # esquerda, o portal parece truncado — e uma ferramenta nova
            # não deve exigir que alguém repare nisso depois.
            nesta = min(colunas, quantos - fileira * colunas)
            recuo = (colunas - nesta) * passo_x // 2
            tile.move(x0 + recuo + coluna * passo_x, y0 + fileira * passo_y)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._reposicionar()

    def showEvent(self, ev):
        # Também aqui, e não só no redimensionamento: um widget pode
        # receber o tamanho sem que o evento de redimensionamento chegue,
        # e aí os ladrilhos ficam empilhados no canto superior esquerdo.
        # Aconteceu ao montar o portal dentro de um pai ainda não exibido.
        super().showEvent(ev)
        self._reposicionar()

    # ── conferência ──────────────────────────────
    def sobreposicoes(self) -> list[tuple[str, str]]:
        """Pares de ladrilhos que se tocam. Existe para ser medido.

        A única forma de saber se a disposição coube é conferir os
        retângulos depois de a janela ter tamanho: não há fórmula que
        substitua isso com ladrilho de largura fixa sobre elipse de
        proporção variável.
        """
        colisoes = []
        for i, a in enumerate(self._ladrilhos):
            for b in self._ladrilhos[i + 1:]:
                if a.geometry().intersects(b.geometry()):
                    colisoes.append((a._meta.name, b._meta.name))
        return colisoes

    def transbordo(self) -> list[str]:
        """Ladrilhos que saíram da área visível. Existe para ser medido."""
        area = self.rect()
        return [t._meta.name for t in self._ladrilhos
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
        online = ferramentas_online()
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
        self._constelacao = GradePortal()
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
        online = ferramentas_online()
        # Sem número escrito na frase. "Em apenas duas situações" virou
        # falso no instante em que a segunda ferramenta de rede entrou, e
        # continuou impresso por duas versões. Aqui a redação se monta a
        # partir do registro: concorda em número e nomeia quem sai.
        if online:
            abertura = (
                "O sistema acessa a rede <b>apenas</b> nestas situações, "
                "todas visíveis: "
                + ("a ferramenta " if len(online) == 1
                   else "as ferramentas ")
                + enumerar(["<b>" + n + "</b>" for n in online])
                + (", que abre " if len(online) == 1 else ", que abrem ")
                + "num navegador dedicado o endereço que o operador "
                  "indicar; e a ")
        else:
            abertura = "O sistema acessa a rede <b>apenas</b> para a "
        texto = QLabel(
            f"<p>Versão <b>{__version__}</b> — {disponiveis} de "
            f"{len(REGISTRY)} ferramentas disponíveis.</p>"
            "<p>Reúne num só lugar os instrumentos de apoio à atividade de "
            "corregedoria: tarjamento e exame de documentos, integridade e "
            "metadados de arquivos, registro de diligências feitas no "
            "computador e em celular, degravação de oitivas, indexação de "
            "acervo apreendido, análise auditável de planilha e montagem "
            "da Informação.</p>"
            "<p><b>Os arquivos não saem desta máquina.</b> Nenhum documento, "
            "hash ou metadado é enviado a servidor algum — tudo é lido e "
            "processado localmente.</p>"
            "<p>" + abertura
            + "<b>verificação de atualização</b>, que lê um arquivo de "
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

        # A pasta desta sessão. Nasce só quando a primeira peça é gravada
        # (ver sessao.py). Herda o identificador do registro, para que a
        # pasta e o log encadeado concordem na hora; se o registro não
        # subiu, gera o seu. Nunca impede o sistema de abrir.
        self._sessao_trabalho = None
        try:
            from .sessao import SessaoTrabalho
            ident = (self._registrador.sessao.identificador
                     if self._registrador is not None else "")
            self._sessao_trabalho = SessaoTrabalho(ident)
        except Exception:                                   # noqa: BLE001
            pass

        # O aviso de abertura só depois de a janela aparecer, e uma vez:
        # em __init__ ele surgiria antes de haver o que ver atrás dele.
        # Inicializado aqui, fora do try do registrador, para que o
        # showEvent nunca o encontre indefinido — nem quando o registro
        # de sessão não pôde subir.
        self._avisou_abertura = False

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

    def showEvent(self, ev):
        super().showEvent(ev)
        if not self._avisou_abertura:
            self._avisou_abertura = True
            QTimer.singleShot(250, self._avisar_registro_abertura)

    def _avisar_registro_abertura(self):
        """Diz, ao abrir, que a sessão será registrada localmente.

        É consentimento informado, e não formalidade: a transparência
        sobre o que se registra é o que separa este registro de uma
        vigilância — o operador sabe, desde o início, o que fica anotado
        e o que não fica.
        """
        if self._registrador is None:
            return
        caixa = QMessageBox(self)
        caixa.setIcon(QMessageBox.Icon.Information)
        caixa.setWindowTitle("Registro desta sessão")
        caixa.setTextFormat(Qt.TextFormat.RichText)
        caixa.setText(
            "<b>Esta sessão de trabalho será registrada nesta máquina.</b>")
        caixa.setInformativeText(
            "Enquanto o Sistema Têmis estiver aberto, anota-se, apenas "
            "nesta estação, quais ferramentas foram usadas e por quanto "
            "tempo, e o que cada uma relatou ao concluir — em ordem "
            "cronológica e encadeada por resumo criptográfico.<br><br>"
            "<b>Nada é enviado a servidor algum.</b> Não se anota o "
            "conteúdo dos arquivos examinados, o texto digitado, os "
            "endereços visitados nem nomes de investigados. O registro "
            "pode ser lido e apagado por quem opera, na ferramenta "
            "Relatório de Atividades.")
        caixa.setStandardButtons(QMessageBox.StandardButton.Ok)
        caixa.button(QMessageBox.StandardButton.Ok).setText("Entendi")
        caixa.exec()

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

            # A pasta da sessão é oferecida a quem a quiser como destino
            # padrão. Ferramenta que não a conhece salva onde sempre salvou.
            if hasattr(tool, "sessao"):
                tool.sessao = self._sessao_trabalho

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
        destino = None
        if self._registrador is not None:
            try:
                destino = self._registrador.encerrar()
            except Exception:                               # noqa: BLE001
                pass

        # Se a sessão produziu algo, o registro e o PDF vão para a pasta
        # dela, e o modal aponta e abre essa pasta. Se não produziu nada,
        # pasta_sessao é None, e o fechamento segue discreto como sempre.
        pasta_sessao = None
        try:
            pasta_sessao = self._depositar_na_sessao()
        except Exception:                                   # noqa: BLE001
            pass

        if self._registrador is not None:
            try:
                self._recomendar_juntar_registro(destino, pasta_sessao)
            except Exception:                               # noqa: BLE001
                pass

        ev.accept()

    def _abrir_no_explorador(self, caminho):
        """Abre uma pasta no explorador de arquivos do sistema."""
        try:
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(caminho)))
        except Exception:                                   # noqa: BLE001
            pass

    def _depositar_na_sessao(self):
        """Deixa na pasta da sessão o registro encadeado e o PDF, se houve.

        A pasta já reúne as peças da diligência; para valer como registro
        completo, recebe também o relatório da sessão — o mesmo que a
        ferramenta de Atividades produz, só que aqui sozinho, no
        encerramento. Nada disto acontece numa sessão sem peças: a pasta
        nem chega a existir. Devolve a pasta, para o modal apontar e abrir.
        """
        if self._sessao_trabalho is None or not self._sessao_trabalho.usada():
            return None
        if self._registrador is None:
            return self._sessao_trabalho.pasta
        from .tools import atividades_core
        sessao = self._registrador.sessao
        pasta = self._sessao_trabalho.garantir()
        base = f"registro-da-sessao-{sessao.identificador}"
        html = atividades_core.relatorio_html(sessao)
        try:
            from PyQt6.QtGui import QTextDocument
            from .impressao import imprimir_documento, preparar_escritor
            doc = QTextDocument()
            doc.setHtml(html)
            escritor = preparar_escritor(str(pasta / f"{base}.pdf"),
                                         "Registro da sessão")
            imprimir_documento(doc, escritor)
        except Exception:                                   # noqa: BLE001
            pass
        try:
            (pasta / f"{base}.html").write_text(html, encoding="utf-8")
        except Exception:                                   # noqa: BLE001
            pass
        return pasta

    def _recomendar_juntar_registro(self, destino, pasta_sessao=None):
        """Ao fechar, recomenda juntar o registro às peças da sessão.

        O registro sozinho vale como prestação de contas; junto das peças,
        vale como cadeia de custódia — amarra cada termo, documento e
        arquivo produzido ao momento e à sessão em que se produziu. A
        recomendação existe porque essa juntada depende de quem opera
        lembrar de fazê-la, e é justamente o que costuma se perder.

        Quando a sessão produziu peças, elas já estão reunidas numa pasta;
        o modal aponta essa pasta e a abre ao ser fechado, para que o que
        se juntar aos autos seja a diligência inteira, num lugar só.
        """
        caixa = QMessageBox(self)
        caixa.setIcon(QMessageBox.Icon.Information)
        caixa.setWindowTitle("Registro desta sessão")
        caixa.setTextFormat(Qt.TextFormat.RichText)
        caixa.setText("<b>A sessão foi registrada.</b>")

        if pasta_sessao is not None:
            caixa.setInformativeText(
                "Tudo o que esta sessão produziu está reunido numa pasta só "
                "— os termos, os documentos e os arquivos recebidos —, agora "
                "com o registro encadeado do que foi feito e o relatório da "
                "sessão em <b>PDF</b>. Reunida assim, a diligência inteira "
                "fica pronta para juntar aos autos, e cada peça carrega a "
                "sessão em que nasceu.<br><br>A pasta será aberta a seguir:"
                f"<br><code>{_html.escape(str(pasta_sessao))}</code>")
            caixa.addButton("Fechar", QMessageBox.ButtonRole.AcceptRole)
            caixa.exec()
            self._abrir_no_explorador(pasta_sessao)
            return

        corpo = (
            "Recomenda-se juntar o registro desta sessão aos autos "
            "<b>junto com os termos, documentos e arquivos</b> que tenham "
            "sido gerados durante ela. O registro documenta, em ordem "
            "cronológica e encadeada, o que foi feito, e é o que reforça a "
            "cadeia de custódia das peças produzidas.")
        if destino:
            corpo += ("<br><br>O relatório foi gravado em:<br>"
                      f"<code>{_html.escape(str(destino))}</code>")
        caixa.setInformativeText(corpo)

        abrir = None
        if destino:
            abrir = caixa.addButton("Abrir a pasta",
                                    QMessageBox.ButtonRole.ActionRole)
        caixa.addButton("Fechar", QMessageBox.ButtonRole.AcceptRole)
        caixa.exec()

        if abrir is not None and caixa.clickedButton() is abrir:
            self._abrir_no_explorador(Path(destino).parent)
