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
from . import derivado_core as derivado
from . import tarja_core
from .derivado_dialogo import TermoDerivadoDialog
from .base import ToolPage, ToolMeta


META = ToolMeta(
    key="tarja",
    name="Tarja Preta",
    icon="tool_tarja",
    tagline="Tarjamento seguro de PDFs e imagens",
    description=(
        "Oculta dados pessoais e sigilosos de forma irreversível, em PDF e "
        "em imagem — fotografia de documento, digitalização, captura de "
        "tela. A página é rasterizada ao salvar, então o texto sob a tarja "
        "é removido do arquivo, e não fica apenas coberto. Aceita tarja "
        "manual com o mouse e, havendo camada de texto, tarja por seleção, "
        "marcação por sinal escolhido e busca automática por CPF, CNPJ, "
        "RG, telefone e e-mail."
    ),
)


#: Imagens que a ferramenta abre. Não é lista inventada: o PyMuPDF abre
#: cada uma como documento de uma página, com retângulo e rasterização
#: iguais aos de um PDF — daí em diante o visor, a tarja e a gravação não
#: distinguem uma coisa da outra.
#:
#: Documento do Word não está aqui, e não por esquecimento: tarjá-lo
#: exigiria convertê-lo em PDF antes, e não há conversor que se possa
#: embutir no instalador. O caminho é exportar para PDF no próprio Word
#: e abrir o PDF.
FORMATOS_IMAGEM = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp",
                   ".gif", ".pnm", ".pgm", ".ppm", ".jp2", ".jpx")

_CURINGAS = " ".join("*" + e for e in FORMATOS_IMAGEM)
FILTRO_ABERTURA = (
    f"Documentos e imagens (*.pdf {_CURINGAS})"
    ";;Arquivos PDF (*.pdf)"
    f";;Imagens ({_CURINGAS})"
    ";;Todos os arquivos (*)"
)

#: Dito a quem abrir arquivo sem texto extraível.
SEM_CAMADA_DE_TEXTO = (
    "Indisponível neste arquivo: ele não tem camada de texto — é imagem, "
    "ou PDF de digitalização. A tarja por retângulo continua servindo a "
    "tudo. Para habilitar a busca automática e a seleção de palavras, "
    "passe o arquivo antes pela ferramenta PDF Pesquisável, que "
    "acrescenta a camada por reconhecimento óptico."
)


def tem_camada_de_texto(doc, ate: int = 20) -> bool:
    """Se há texto extraível no documento aberto.

    A pergunta não é sobre formato. PDF de digitalização — que é a maior
    parte do que chega a uma corregedoria — também não tem camada de
    texto, e nele a busca automática sempre respondeu "nada encontrado"
    sobre páginas cheias de CPF, sem dizer por quê. Quem lê essa resposta
    conclui que não há CPF ali, que é a conclusão oposta à verdadeira.

    Olha as primeiras páginas e para na primeira que tiver texto: num
    documento de trezentas páginas digitalizadas, varrer todas custaria
    caro para responder o que a primeira já responde.
    """
    for i in range(min(len(doc), ate)):
        if doc[i].get_text("words"):
            return True
    return False


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
    #: (caminho gravado, resumo do conteúdo produzido). O resumo vem
    #: junto porque é dos pixels, e depois de gravado o PDF não se pode
    #: recalculá-lo do arquivo: o formato guarda a hora da gravação, e o
    #: resumo do arquivo muda a cada vez sem que o conteúdo mude.
    done = pyqtSignal(str, str)
    failed = pyqtSignal(str)

    #: Fator de rasterização (2.0 ≈ 144 DPI). Vive no núcleo porque entra
    #: no roteiro: em fator diferente, a mesma tarja produz outro
    #: conteúdo e outro resumo.
    RENDER_SCALE = tarja_core.ESCALA

    def __init__(self, doc: fitz.Document, tarjas_por_pagina: dict,
                 out_path: str):
        super().__init__()
        self.doc = doc
        self.tarjas_por_pagina = tarjas_por_pagina
        self.out_path = out_path

    def run(self):
        try:
            saida, resumo = tarja_core.compor(
                self.doc, self.tarjas_por_pagina, self.RENDER_SCALE,
                progresso=lambda i, n: self.progress.emit(i, n))
            saida.save(self.out_path, garbage=4, deflate=True)
            saida.close()
            self.done.emit(self.out_path, resumo)
        except Exception as e:                          # noqa: BLE001
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
        #: De onde veio o PDF aberto, e para onde foi o tarjado. O termo
        #: precisa dos dois: ele existe para amarrar um ao outro.
        self._caminho_origem = ""
        self._ultimo_salvo = ""
        #: Resumo do conteúdo do último arquivo gravado. Só existe depois
        #: de compor: é dos pixels produzidos, e não dos bytes do PDF.
        self._ultimo_conteudo = ""
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

    def _ajustar_por_camada_de_texto(self):
        """Liga ou desliga o que só funciona havendo texto extraível.

        Deixar essas ações ligadas sobre uma digitalização não é
        neutro: a ferramenta responderia "nada encontrado" a um
        documento cheio de dado protegido, e quem lê isso arquiva
        acreditando ter conferido.
        """
        for w in (self._btn_search, self._btn_bracket,
                  self._btn_preview_brackets, self._btn_modo_texto):
            if w.property("dica_original") is None:
                w.setProperty("dica_original", w.toolTip())
            w.setEnabled(self._tem_texto)
            w.setToolTip(w.property("dica_original") if self._tem_texto
                         else SEM_CAMADA_DE_TEXTO)
        if not self._tem_texto:
            self._definir_modo(PaginaTarja.MODO_RETANGULO)

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

        # No rodapé, e não no corpo: o corpo rola, e com três grupos de
        # controles o botão caía abaixo da dobra — existia, estava
        # habilitado, e não era encontrado. Aqui ele fica ao lado da ação
        # que o antecede, que é onde se olha depois de salvar.
        #
        # Nasce desligado porque o termo cita o resumo criptográfico do
        # arquivo tarjado, e esse resumo só existe depois de gravar: é
        # calculado sobre os bytes finais.
        # O roteiro é o que torna a censura conferível: com ele e o
        # original, um terceiro re-executa e chega ao mesmo material.
        # Nasce desligado porque só existe depois de gravar — é ali que o
        # resumo do conteúdo é calculado, e roteiro sem ele não confronta
        # coisa alguma.
        linha_roteiro = QHBoxLayout()
        self._btn_roteiro = QPushButton("  Salvar roteiro")
        self._btn_roteiro.setIcon(draw_icon("save", 14, PALETTE["text2"]))
        self._btn_roteiro.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_roteiro.setEnabled(False)
        self._btn_roteiro.setToolTip(
            "Grava a relação declarada das tarjas, com o resumo do "
            "original e o do conteúdo produzido. Acompanha a peça: é por "
            "ele que a censura se confere.")
        self._btn_roteiro.clicked.connect(self._salvar_roteiro)
        linha_roteiro.addWidget(self._btn_roteiro)

        self._btn_abrir_roteiro = QPushButton("  Abrir roteiro")
        self._btn_abrir_roteiro.setIcon(draw_icon("open", 14,
                                                  PALETTE["text2"]))
        self._btn_abrir_roteiro.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_abrir_roteiro.setToolTip(
            "Carrega um roteiro salvo sobre o arquivo aberto, para "
            "conferir a censura de outra pessoa")
        self._btn_abrir_roteiro.clicked.connect(self._abrir_roteiro)
        linha_roteiro.addWidget(self._btn_abrir_roteiro)
        panel.footer.addLayout(linha_roteiro)

        self._btn_termo = QPushButton("  Gerar termo de censura")
        self._btn_termo.setIcon(draw_icon("save", 16, PALETTE["text"]))
        self._btn_termo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_termo.setEnabled(False)
        self._btn_termo.setToolTip(
            "Disponível depois de salvar o PDF tarjado — o termo cita os "
            "resumos criptográficos do original e do arquivo produzido")
        self._btn_termo.clicked.connect(self._gerar_termo)
        panel.footer.addWidget(self._btn_termo)
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
            if not getattr(self, "_tem_texto", True):
                self._dica.setText(
                    "Sem camada de texto — tarja por retângulo   •   "
                    "Ctrl+Z desfaz")
            else:
                self._dica.setText(
                    ("Marque as palavras a tarjar   •   Ctrl+Z desfaz"
                     if texto else
                     "Arraste para cobrir a área   •   Ctrl+Z desfaz"))

    def _set_welcome_state(self):
        self._visor.mensagem("Abra um PDF ou uma imagem para começar")

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
            self, "Abrir documento ou imagem", "", FILTRO_ABERTURA)
        if not path:
            return
        try:
            if self._doc:
                self._doc.close()
            self._doc = fitz.open(path)
            self._caminho_origem = path
            # Um arquivo novo apaga o termo do anterior: emitir a peça do
            # PDF de antes, com o documento de agora aberto, seria trocar
            # os autos de lugar.
            self._ultimo_salvo = ""
            self._btn_termo.setEnabled(False)
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
            for w in (self._btn_save, self._btn_undo,
                      self._btn_clear_page, self._btn_clear_all):
                w.setEnabled(True)
            self._tem_texto = tem_camada_de_texto(self._doc)
            self._ajustar_por_camada_de_texto()
            quantas = f"{len(self._doc)} página(s)"
            self.status_msg.emit(
                f"Aberto: {quantas}" if self._tem_texto else
                f"Aberto: {quantas}, sem camada de texto — só a tarja por "
                "retângulo está disponível")
        except Exception as e:
            QMessageBox.critical(
                self, "Erro", f"Não foi possível abrir o arquivo:\n{e}")

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

        from ..sessao import destino_para_dialogo
        fonte = (Path(self._doc.name).stem
                 if getattr(self._doc, "name", "") else "documento")
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Salvar PDF tarjado",
            destino_para_dialogo(self, "Documentos tarjados",
                                 f"{fonte}-tarjado.pdf"),
            "Arquivos PDF (*.pdf)")
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
        self._save_thread.done.connect(
            lambda p, r: self._on_save_done(p, r, progress))
        self._save_thread.failed.connect(lambda e: self._on_save_error(e, progress))
        self._save_thread.start()

    def _on_save_done(self, path: str, resumo: str,
                      progress: QProgressDialog):
        progress.close()
        self._ultimo_salvo = path
        self._ultimo_conteudo = resumo
        self._btn_roteiro.setEnabled(True)
        self._btn_termo.setEnabled(bool(self._caminho_origem))
        QMessageBox.information(
            self, "Salvo com sucesso",
            f"PDF tarjado salvo em:\n{path}\n\n"
            "O texto nas áreas tarjadas foi removido permanentemente, e o "
            "arquivo gerado não carrega metadado algum do original.\n\n"
            "O termo de censura já pode ser gerado — ele cita os resumos "
            "criptográficos do original e do arquivo produzido, e traz a "
            "conferência de que o roteiro reproduz este resultado.")
        self.status_msg.emit(f"Salvo: {Path(path).name}")

    # ─────────────────────────────────────
    #  ROTEIRO
    # ─────────────────────────────────────

    def _roteiro_atual(self) -> "tarja_core.Roteiro":
        roteiro = tarja_core.montar(self._caminho_origem,
                                    self._tarjas_por_pagina,
                                    SaveThread.RENDER_SCALE)
        roteiro.resumo_conteudo = self._ultimo_conteudo
        return roteiro

    def _salvar_roteiro(self):
        if not (self._caminho_origem and self._ultimo_conteudo):
            return
        if self._ultimo_salvo:
            # ao lado do PDF tarjado que já foi salvo — na pasta da sessão,
            # se foi ali que ele caiu
            sugerido = str(Path(self._ultimo_salvo).with_suffix(".roteiro.json"))
        else:
            from ..sessao import destino_para_dialogo
            base = (Path(self._caminho_origem).stem
                    if self._caminho_origem else "censura")
            sugerido = destino_para_dialogo(self, "Roteiros",
                                            f"{base}.roteiro.json")
        destino, _ = QFileDialog.getSaveFileName(
            self, "Salvar roteiro da censura", sugerido,
            "Roteiro (*.json)")
        if not destino:
            return
        if not destino.lower().endswith(".json"):
            destino += ".json"
        try:
            tarja_core.salvar_roteiro(self._roteiro_atual(), destino)
        except Exception as e:                          # noqa: BLE001
            QMessageBox.critical(self, "Erro ao salvar o roteiro", str(e))
            return
        self.status_msg.emit(f"Roteiro salvo: {Path(destino).name}")

    def _abrir_roteiro(self):
        if self._doc is None:
            QMessageBox.information(
                self, "Abra o documento primeiro",
                "O roteiro relaciona tarjas sobre um arquivo. Abra o "
                "arquivo original e então carregue o roteiro.")
            return
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Abrir roteiro da censura", "", "Roteiro (*.json)")
        if not caminho:
            return
        try:
            roteiro = tarja_core.ler_roteiro(caminho)
        except Exception as e:                          # noqa: BLE001
            QMessageBox.critical(self, "Erro ao ler o roteiro", str(e))
            return

        # Roteiro montado para outro arquivo aplicado a este cobriria
        # áreas que ali não são as mesmas — e o operador só descobriria
        # olhando. O aviso é explícito, e a decisão fica com ele.
        from .hash_core import sha256_file
        try:
            atual = sha256_file(self._caminho_origem)
        except OSError:
            atual = ""
        if roteiro.resumo_origem and atual and roteiro.resumo_origem != atual:
            resposta = QMessageBox.warning(
                self, "O roteiro é de outro arquivo",
                "O resumo criptográfico declarado no roteiro não "
                "corresponde ao do arquivo aberto.\n\nAplicá-lo assim "
                "cobriria áreas que neste documento podem não ser as "
                "mesmas. Deseja aplicar mesmo assim?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if resposta != QMessageBox.StandardButton.Yes:
                return

        self._tarjas_por_pagina = roteiro.por_pagina()
        self._ultimo_conteudo = ""
        self._ultimo_salvo = ""
        self._btn_termo.setEnabled(False)
        self._btn_roteiro.setEnabled(False)
        self._update_tarja_count()
        for pagina in self._visor.paginas():
            pagina.update()
        self.status_msg.emit(
            f"Roteiro carregado: {len(roteiro.tarjas)} tarja(s) em "
            f"{roteiro.paginas_atingidas} página(s). Salve para conferir.")

    # ─────────────────────────────────────
    #  TERMO DE CENSURA
    # ─────────────────────────────────────

    #: O que a operação faz e o que ela não faz. Vai impresso na peça:
    #: uma ferramenta que se cala sobre os próprios limites convida a que
    #: se lhe atribua alcance que ela não tem.
    RESSALVAS = (
        "A censura não oculta o conteúdo: remove-o. Cada página do "
        "documento produzido é uma imagem, sobre a qual as áreas "
        "protegidas foram cobertas antes da gravação — não há texto por "
        "baixo da tarja a ser recuperado por seleção, cópia ou extração.",
        "O arquivo produzido não carrega metadado algum do original: nem "
        "título, autor, assunto, palavras-chave, programa de origem ou "
        "bloco XMP. Ele é composto do zero, e não descende do arquivo de "
        "entrada.",
        "Como cada página passa a ser imagem, o documento produzido não "
        "tem camada de texto pesquisável — tampouco no que não foi "
        "censurado. Havendo necessidade de pesquisa no documento "
        "censurado, ele pode ser submetido à ferramenta PDF Pesquisável, "
        "que devolve a camada de texto por reconhecimento óptico.",
        "O arquivo original permanece inalterado. Este termo o identifica "
        "pelo resumo criptográfico justamente para que a correspondência "
        "entre um e outro possa ser conferida a qualquer tempo.",
        "A censura não é apenas relatada: é um roteiro. As áreas cobertas "
        "constam de relação declarada, que acompanha esta peça em arquivo "
        "próprio e que terceiro re-executa sobre o original, com esta "
        "mesma ferramenta, para obter o mesmo material. A conferência é "
        "feita sobre o resumo do conteúdo das páginas — e não sobre os "
        "bytes do arquivo produzido, porque o formato PDF guarda dentro "
        "de si a hora da gravação e gerar duas vezes a mesma censura "
        "produz arquivos de resumos diferentes.",
    )

    def _gerar_termo(self):
        if not (self._ultimo_salvo and self._caminho_origem):
            return
        contagem = sum(len(v) for v in self._tarjas_por_pagina.values())
        paginas = len([p for p, v in self._tarjas_por_pagina.items() if v])
        detalhes = [
            ("Áreas censuradas", str(contagem)),
            ("Páginas com censura", f"{paginas} de {len(self._doc)}"),
        ]
        # Imagem entra e PDF sai. A peça precisa dizer isso: quem confere
        # os dois resumos veria arquivos de formatos diferentes e ficaria
        # sem saber se houve conversão ou se houve troca de material.
        origem = Path(self._caminho_origem).suffix.lower()
        if origem != ".pdf":
            detalhes.insert(0, ("Conversão de formato",
                                "imagem " + origem.lstrip(".").upper()
                                + " convertida em PDF de uma página"))
        roteiro = self._roteiro_atual()
        situacao, _obtido, explicacao = tarja_core.reproduzir(roteiro)
        if roteiro.resumo_conteudo:
            detalhes.append(("Resumo do conteúdo (SHA-256)",
                             roteiro.resumo_conteudo))
        detalhes.append(("Fator de rasterização", f"{roteiro.escala:g}×"))

        item = derivado.medir(self._caminho_origem, self._ultimo_salvo,
                              detalhes=detalhes)
        termo = derivado.TermoDerivado(
            titulo="Termo de Censura em Dados e Informações Protegidas",
            operacao="tarjamento de dados e informações protegidas",
            ressalvas=self.RESSALVAS + (
                tarja_core.frase_reproducao(situacao, explicacao),),
            motores=("pdf", "imagem"),
            itens=[item])
        TermoDerivadoDialog(termo, self).exec()

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
