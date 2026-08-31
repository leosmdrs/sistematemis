"""
Documentos PDF — a tela.

Três operações, um caminho só: acrescentar os arquivos, escolher o que
fazer, processar, gravar e emitir o termo. O botão do termo nasce
desligado e só acende depois de gravar, porque a peça cita o resumo
criptográfico do arquivo produzido — e esse resumo é calculado sobre os
bytes finais, que antes de gravar não existem.

Mexer em qualquer coisa depois de gravar desliga o botão de novo: o
termo passaria a citar o resumo de um arquivo que não corresponde mais
ao que está na tela.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QProgressDialog, QPushButton,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..icons import draw_icon
from ..theme import PALETTE
from ..widgets import (NoScrollComboBox, SidebarPanel,
                       field_label, group_title, hsep, output_button,
                       primary_button, subtext)
from . import derivado_core as derivado
from . import pdf_core as pc
from .base import ToolMeta, ToolPage
from .derivado_dialogo import TermoDerivadoDialog

#: (chave, rótulo, ícone, dica)
MODOS = [
    ("mesclar", "Mesclar", "merge", "Juntar vários PDFs num só"),
    ("separar", "Separar", "scissors", "Extrair páginas para um novo PDF"),
    ("comprimir", "Comprimir", "compress", "Reduzir o tamanho do arquivo"),
]

COL_N, COL_NOME, COL_PAG, COL_TAM, COL_DEL = range(5)


class Operario(QThread):
    """Roda a operação fora da linha da interface.

    Resumir as páginas exige rasterizar cada uma. Num documento de
    centenas de páginas isso leva dezenas de segundos, e na linha da
    interface deixaria a janela sem resposta — o Windows a ofereceria
    para ser encerrada no meio do trabalho.
    """

    andamento = pyqtSignal(int, int)
    pronto = pyqtSignal(object, object)          # (Producao, Roteiro)
    falhou = pyqtSignal(str)

    def __init__(self, operacao, origens, parametros):
        super().__init__()
        self._args = (operacao, list(origens), dict(parametros))

    def run(self):
        operacao, origens, parametros = self._args
        try:
            producao = pc.executar(operacao, origens, parametros,
                                   progresso=self.andamento.emit)
            roteiro = pc.montar(operacao, origens, parametros, producao)
        except Exception as e:                              # noqa: BLE001
            self.falhou.emit(f"{type(e).__name__}: {e}")
            return
        self.pronto.emit(producao, roteiro)


class PDFTool(ToolPage):
    """Mesclar, separar e comprimir — com a operação declarada."""

    meta = ToolMeta(
        key="pdf",
        name="Documentos PDF",
        icon="tool_pdf",
        tagline="Mescla, separa e comprime sem sair da máquina",
        description=(
            "Junta vários PDFs num só, extrai páginas para um documento novo e reduz o "
            "tamanho de documentos digitalizados — tudo na própria "
            "estação, sem enviar peça de procedimento para sítio de "
            "terceiro. Ao fim, emite termo que identifica origens e "
            "resultado pelos resumos criptográficos, declara os "
            "parâmetros e confere, refazendo a operação, que o documento "
            "entregue é aquele mesmo."),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._modo = "mesclar"
        self._documentos: list = []
        self._producao = None
        self._roteiro = None
        self._salvo = ""
        self._operario = None

        fora = QHBoxLayout(self)
        fora.setContentsMargins(0, 0, 0, 0)
        fora.setSpacing(0)
        fora.addWidget(self._montar_painel())
        fora.addWidget(self._montar_vista(), 1)
        self._refletir()

    # ── painel ───────────────────────────
    def _montar_painel(self) -> SidebarPanel:
        p = SidebarPanel()
        self._painel = p

        abrir = primary_button("Acrescentar PDFs")
        abrir.clicked.connect(self._acrescentar)
        p.header.addWidget(abrir)
        p.header.addWidget(subtext(
            "O arquivo de origem nunca é alterado: o resultado é sempre "
            "arquivo novo.", wrap=True))

        p.body.addWidget(group_title("O que fazer"))
        linha = QHBoxLayout()
        linha.setSpacing(6)
        self._botoes_modo = {}
        for chave, rotulo, icone, dica in MODOS:
            b = QPushButton("  " + rotulo)
            b.setIcon(draw_icon(icone, 15, PALETTE["text"]))
            b.setCheckable(True)
            b.setToolTip(dica)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=chave: self._trocar_modo(c))
            linha.addWidget(b, 1)
            self._botoes_modo[chave] = b
        caixa = QWidget()
        caixa.setLayout(linha)
        p.body.addWidget(caixa)

        self._paginas_modo = QStackedWidget()
        self._paginas_modo.addWidget(self._pagina_mesclar())
        self._paginas_modo.addWidget(self._pagina_separar())
        self._paginas_modo.addWidget(self._pagina_comprimir())
        p.body.addWidget(self._paginas_modo)

        p.body.addWidget(hsep())
        self._lbl_resultado = QLabel("")
        self._lbl_resultado.setObjectName("subtext")
        self._lbl_resultado.setWordWrap(True)
        p.body.addWidget(self._lbl_resultado)
        p.body.addStretch()

        self._b_processar = output_button("Processar", "check")
        self._b_processar.clicked.connect(self._processar)
        p.footer.addWidget(self._b_processar)

        self._b_termo = output_button("Gerar termo")
        self._b_termo.setEnabled(False)
        self._b_termo.setToolTip(
            "Disponível depois de gravar o resultado — a peça cita o resumo "
            "criptográfico do arquivo produzido")
        self._b_termo.clicked.connect(self._gerar_termo)
        p.footer.addWidget(self._b_termo)
        return p

    def _pagina_mesclar(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(subtext(
            "Os documentos entram na ordem da lista. Use Subir e Descer "
            "para mudá-la — a ordem é o que decide o resultado.", wrap=True))
        return w

    def _pagina_separar(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(subtext(
            "Separa o primeiro documento da lista.", wrap=True))

        lay.addWidget(field_label("Páginas"))
        self._e_paginas = QLineEdit()
        self._e_paginas.setPlaceholderText("Ex.: 1-3, 7, 10-12")
        self._e_paginas.setToolTip(
            "Faixas e páginas avulsas, separadas por vírgula. A ordem "
            "escrita é a ordem do resultado.")
        self._e_paginas.textChanged.connect(self._conferir_paginas)
        lay.addWidget(self._e_paginas)

        self._lbl_aviso_paginas = QLabel("")
        self._lbl_aviso_paginas.setObjectName("subtext")
        self._lbl_aviso_paginas.setWordWrap(True)
        self._lbl_aviso_paginas.setStyleSheet(f"color: {PALETTE['warning']};")
        lay.addWidget(self._lbl_aviso_paginas)
        self._conferir_paginas()
        return w

    def _pagina_comprimir(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(subtext(
            "Comprime o primeiro documento da lista.", wrap=True))

        lay.addWidget(field_label("Grau"))
        self._cb_nivel = NoScrollComboBox()
        for n in pc.NIVEIS:
            self._cb_nivel.addItem(n.rotulo, n.chave)
        self._cb_nivel.setCurrentIndex(2)          # média, o caso comum
        self._cb_nivel.currentIndexChanged.connect(self._explicar_nivel)
        lay.addWidget(self._cb_nivel)

        self._lbl_nivel = QLabel("")
        self._lbl_nivel.setObjectName("subtext")
        self._lbl_nivel.setWordWrap(True)
        lay.addWidget(self._lbl_nivel)

        lay.addWidget(subtext(
            "A camada de texto é preservada em todos os graus: o documento "
            "comprimido continua pesquisável.", wrap=True))
        self._explicar_nivel()
        return w

    def _montar_vista(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(8)

        topo = QHBoxLayout()
        topo.setSpacing(6)
        self._lbl_lista = QLabel("Nenhum documento")
        self._lbl_lista.setStyleSheet("font-size: 13px; font-weight: 700;")
        topo.addWidget(self._lbl_lista)
        topo.addStretch()
        self._b_sobe = QPushButton("↑")
        self._b_sobe.setFixedWidth(32)
        self._b_sobe.setToolTip("Adiantar — a ordem decide o resultado")
        self._b_sobe.clicked.connect(lambda: self._mover(-1))
        topo.addWidget(self._b_sobe)
        self._b_desce = QPushButton("↓")
        self._b_desce.setFixedWidth(32)
        self._b_desce.setToolTip("Atrasar")
        self._b_desce.clicked.connect(lambda: self._mover(1))
        topo.addWidget(self._b_desce)
        self._b_limpar = QPushButton("  Limpar")
        self._b_limpar.setIcon(draw_icon("trash", 14, PALETTE["text"]))
        self._b_limpar.clicked.connect(self._limpar)
        topo.addWidget(self._b_limpar)
        caixa = QWidget()
        caixa.setLayout(topo)
        lay.addWidget(caixa)

        self._tabela = QTableWidget(0, 5)
        self._tabela.setHorizontalHeaderLabels(
            ["#", "Documento", "Páginas", "Tamanho", ""])
        self._tabela.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self._tabela.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        cab = self._tabela.horizontalHeader()
        cab.setSectionResizeMode(COL_NOME, QHeaderView.ResizeMode.Stretch)
        self._tabela.verticalHeader().setVisible(False)
        lay.addWidget(self._tabela, 1)
        return w

    # ── lista ────────────────────────────
    def _acrescentar(self):
        caminhos, _ = QFileDialog.getOpenFileNames(
            self, "Acrescentar PDFs", str(Path.home()),
            "Documentos PDF (*.pdf);;Todos os arquivos (*)")
        if not caminhos:
            return
        for c in caminhos:
            self._documentos.append(pc.sondar(c))
        self._invalidar()
        self._encher_tabela()

    def _encher_tabela(self):
        self._tabela.setRowCount(len(self._documentos))
        for i, d in enumerate(self._documentos):
            def posto(coluna, texto, dica=""):
                item = QTableWidgetItem(texto)
                if dica:
                    item.setToolTip(dica)
                if d.erro:
                    item.setForeground(Qt.GlobalColor.red)
                self._tabela.setItem(i, coluna, item)

            posto(COL_N, str(i + 1))
            posto(COL_NOME, d.nome, d.erro or d.caminho)
            posto(COL_PAG, d.erro or str(d.paginas))
            posto(COL_TAM, pc.formatar_tamanho(d.tamanho))
            b = QPushButton()
            b.setIcon(draw_icon("minus", 13, PALETTE["text"]))
            b.setToolTip("Retirar da lista")
            b.clicked.connect(lambda _=False, x=i: self._remover(x))
            self._tabela.setCellWidget(i, COL_DEL, b)
        self._tabela.resizeColumnsToContents()
        self._tabela.horizontalHeader().setSectionResizeMode(
            COL_NOME, QHeaderView.ResizeMode.Stretch)
        self._refletir()
        self._conferir_paginas()

    def _remover(self, i: int):
        if 0 <= i < len(self._documentos):
            del self._documentos[i]
            self._invalidar()
            self._encher_tabela()

    def _limpar(self):
        self._documentos = []
        self._invalidar()
        self._encher_tabela()

    def _mover(self, passo: int):
        i = self._tabela.currentRow()
        j = i + passo
        if not (0 <= i < len(self._documentos)
                and 0 <= j < len(self._documentos)):
            return
        self._documentos[i], self._documentos[j] = (self._documentos[j],
                                                    self._documentos[i])
        self._invalidar()
        self._encher_tabela()
        self._tabela.setCurrentCell(j, COL_NOME)

    # ── modo e parâmetros ────────────────
    def _trocar_modo(self, chave: str):
        self._modo = chave
        for c, b in self._botoes_modo.items():
            b.setChecked(c == chave)
        self._paginas_modo.setCurrentIndex(
            [k for k, *_ in MODOS].index(chave))
        self._invalidar()
        self._refletir()

    def _explicar_nivel(self):
        n = pc.nivel_por_chave(self._cb_nivel.currentData() or "")
        self._lbl_nivel.setText(n.explicacao)
        self._invalidar()

    def _conferir_paginas(self):
        """Diz, enquanto se digita, o que a escolha vai render."""
        if not hasattr(self, "_lbl_aviso_paginas"):
            return
        if self._modo != "separar" or not self._documentos:
            self._lbl_aviso_paginas.setText("")
            return
        total = self._documentos[0].paginas
        indices, ignorados = pc.ler_paginas(self._e_paginas.text(), total)
        recado = ""
        if ignorados:
            recado = ("Sem efeito: " + "; ".join(ignorados)
                      + f". O documento tem {total} páginas.")
        self._lbl_aviso_paginas.setText(recado)
        if not recado and indices:
            self._lbl_resultado.setText(
                f"{len(indices)} página(s) escolhida(s) de {total}.")

    # ── estado ───────────────────────────
    def _invalidar(self):
        """Qualquer mudança invalida o que já foi produzido e gravado."""
        if self._producao is not None:
            self._producao.fechar()
        self._producao = None
        self._roteiro = None
        self._salvo = ""
        if hasattr(self, "_b_termo"):
            self._b_termo.setEnabled(False)

    def _origens(self) -> list:
        bons = [d for d in self._documentos if not d.erro]
        if self._modo == "mesclar":
            return [d.caminho for d in bons]
        return [bons[0].caminho] if bons else []

    def _refletir(self):
        bons = [d for d in self._documentos if not d.erro]
        n = len(self._documentos)
        self._lbl_lista.setText(
            "Nenhum documento" if not n
            else f"{n} documento(s), {sum(d.paginas for d in bons)} páginas")
        basta = (len(bons) >= 2 if self._modo == "mesclar" else len(bons) >= 1)
        self._b_processar.setEnabled(basta)
        for b in (self._b_sobe, self._b_desce, self._b_limpar):
            b.setEnabled(bool(n))
        self._b_termo.setEnabled(bool(self._salvo))
        if not basta and n:
            self._lbl_resultado.setText(
                "Mesclar precisa de pelo menos dois documentos legíveis."
                if self._modo == "mesclar"
                else "Nenhum documento legível na lista.")

    # ── processar ────────────────────────
    def _parametros(self) -> dict:
        if self._modo == "separar":
            total = self._documentos[0].paginas if self._documentos else 0
            indices, _ = pc.ler_paginas(self._e_paginas.text(), total)
            return {"paginas": indices}
        if self._modo == "comprimir":
            return {"nivel": self._cb_nivel.currentData() or "sem_perda"}
        return {}

    def _processar(self):
        origens = self._origens()
        if not origens:
            return
        parametros = self._parametros()
        if self._modo == "separar" and not parametros.get("paginas"):
            QMessageBox.warning(
                self, "Nenhuma página escolhida",
                "Escreva quais páginas extrair — por exemplo 1-3, 7.")
            return

        espera = QProgressDialog("Processando…", "", 0, 0, self)
        espera.setWindowTitle("Documentos PDF")
        espera.setCancelButton(None)
        espera.setWindowModality(Qt.WindowModality.WindowModal)
        espera.setMinimumDuration(300)

        def andou(feito, total):
            espera.setMaximum(total)
            espera.setValue(feito)
            espera.setLabelText(f"Resumindo as páginas… {feito} de {total}")

        def deu_certo(producao, roteiro):
            espera.close()
            self._producao, self._roteiro = producao, roteiro
            self._descrever_producao()
            self._gravar()

        def deu_errado(motivo):
            espera.close()
            QMessageBox.warning(self, "Não foi possível processar", motivo)

        self._operario = Operario(self._modo, origens, parametros)
        self._operario.andamento.connect(andou)
        self._operario.pronto.connect(deu_certo)
        self._operario.falhou.connect(deu_errado)
        self._operario.start()

    def _descrever_producao(self):
        p = self._producao
        if p is None:
            return
        recado = f"{len(p.paginas)} página(s) produzida(s). "
        if self._modo == "comprimir":
            nivel = pc.nivel_por_chave(self._roteiro.parametros.get("nivel"))
            recado += ("Nenhuma página foi alterada." if p.paginas_intactas
                       else "As páginas foram alteradas pela reamostragem "
                            f"das imagens ({nivel.rotulo.lower()}).")
        else:
            recado += ("Nenhuma página foi alterada." if p.paginas_intactas
                       else "Atenção: as páginas produzidas não conferem "
                            "com as de origem.")
        self._lbl_resultado.setText(recado)

    def _gravar(self):
        if self._producao is None:
            return
        base = Path(self._origens()[0])
        sufixo = {"mesclar": "-mesclado", "separar": "-paginas",
                  "comprimir": "-comprimido"}[self._modo]
        alvo = self.destino_na_sessao(
            "Documentos", base.stem + sufixo + ".pdf",
            str(base.with_name(base.stem + sufixo + ".pdf")))
        destino, _ = QFileDialog.getSaveFileName(
            self, "Onde gravar", alvo, "Documento PDF (*.pdf)")
        if not destino:
            return
        if not destino.lower().endswith(".pdf"):
            destino += ".pdf"
        try:
            pc.gravar(self._producao.documento, destino)
        except Exception as e:                              # noqa: BLE001
            QMessageBox.warning(self, "Não foi possível gravar",
                                f"{type(e).__name__}: {e}")
            return
        self._salvo = destino
        self._b_termo.setEnabled(True)
        tamanho = Path(destino).stat().st_size
        antes = sum(d.tamanho for d in self._documentos
                    if d.caminho in self._origens())
        variacao = ""
        if antes and self._modo == "comprimir":
            variacao = (f"  Redução de "
                        f"{100 * (1 - tamanho / antes):.0f}%.")
        self.status_msg.emit(f"Gravado: {Path(destino).name}")
        QMessageBox.information(
            self, "Documento gravado",
            f"Arquivo gravado em:\n{destino}\n\n"
            f"{pc.formatar_tamanho(tamanho)}.{variacao}\n\n"
            "O termo já pode ser gerado — ele traz os parâmetros da "
            "operação e os resumos criptográficos das origens e do "
            "resultado.")

    # ── o termo ──────────────────────────

    #: O que a operação alcança e o que ela não alcança. Vai impresso: uma
    #: ferramenta que se cala sobre os próprios limites convida a que se
    #: lhe atribua alcance que ela não tem.
    RESSALVAS = (
        "Os arquivos de origem não foram alterados. Esta ferramenta os "
        "abre somente para leitura; o resultado é sempre arquivo novo, em "
        "separado.",
        "O documento produzido não herda metadado algum dos originais — "
        "nem título, autor, assunto, palavras-chave ou bloco XMP. Ele é "
        "composto do zero e recebe apenas as páginas.",
        "A conferência é feita sobre o resumo do conteúdo das páginas, e "
        "não sobre os bytes do arquivo produzido: o formato PDF guarda "
        "dentro de si dados que variam a cada gravação, e refazer a mesma "
        "operação gera arquivos de resumos diferentes ainda que o "
        "conteúdo seja o mesmo. Conferir pelos bytes acusaria divergência "
        "onde não há.",
    )

    #: Acrescentadas conforme a operação — a peça não deve carregar
    #: ressalva que não diz respeito ao que foi feito.
    RESSALVA_INTACTAS = (
        "Cada página do documento produzido tem resumo idêntico ao da "
        "página de origem correspondente: a operação reordenou e reuniu "
        "páginas, sem alterar nenhuma delas.")
    RESSALVA_COM_PERDA = (
        "A compactação foi feita com perda: as imagens do documento foram "
        "reamostradas, e por isso as páginas produzidas diferem das "
        "originais. A redução de tamanho tem esse custo, e é ele que "
        "explica a divergência entre os resumos das páginas. A camada de "
        "texto, essa, foi preservada — o documento produzido continua "
        "pesquisável.")
    RESSALVA_SEM_PERDA = (
        "A compactação foi feita sem perda: limparam-se os dados "
        "supérfluos e recomprimiram-se os fluxos, sem tocar nas imagens. "
        "Cada página do documento produzido tem resumo idêntico ao da "
        "página original.")

    def _detalhes_do_termo(self) -> list:
        r = self._roteiro
        detalhes = [("Operação", r.descrever())]
        if r.operacao == "separar":
            detalhes.append(
                ("Páginas extraídas",
                 pc.escrever_paginas(r.parametros.get("paginas", []))))
        elif r.operacao == "comprimir":
            nivel = pc.nivel_por_chave(r.parametros.get("nivel", ""))
            detalhes.append(("Grau de compactação", nivel.rotulo))
            if nivel.com_perda:
                detalhes.append(
                    ("Reamostragem das imagens",
                     f"{nivel.dpi} dpi, qualidade {nivel.qualidade}"))
        elif r.operacao == "mesclar":
            detalhes.append(("Documentos reunidos", str(len(r.origens))))
        detalhes += [
            ("Páginas do resultado", str(r.paginas_produzidas)),
            ("Páginas alteradas",
             "nenhuma" if r.paginas_intactas else "sim — ver as ressalvas"),
            ("Resumo do conteúdo (SHA-256)", r.resumo_conteudo),
        ]
        return detalhes

    def _gerar_termo(self):
        if self._roteiro is None or not self._salvo:
            return
        espera = QProgressDialog("Refazendo a operação para conferir…",
                                 "", 0, 0, self)
        espera.setWindowTitle("Conferência de reprodutibilidade")
        espera.setCancelButton(None)
        espera.setWindowModality(Qt.WindowModality.WindowModal)
        espera.show()
        try:
            situacao, resumo, explicacao = pc.reproduzir(self._roteiro)
        finally:
            espera.close()

        r = self._roteiro
        ressalvas = list(self.RESSALVAS)
        if r.operacao == "comprimir":
            nivel = pc.nivel_por_chave(r.parametros.get("nivel", ""))
            ressalvas.append(self.RESSALVA_COM_PERDA if nivel.com_perda
                             else self.RESSALVA_SEM_PERDA)
        elif r.paginas_intactas:
            ressalvas.append(self.RESSALVA_INTACTAS)
        ressalvas.append(pc.frase_reproducao(situacao, resumo, explicacao))

        item = derivado.medir(r.caminhos, self._salvo,
                              detalhes=self._detalhes_do_termo())
        termo = derivado.TermoDerivado(
            titulo="Termo de Operação em Documento PDF",
            operacao=r.descrever(),
            ressalvas=tuple(ressalvas),
            motores=("pdf",),
            itens=[item])
        if situacao != "sim":
            QMessageBox.warning(
                self, "A conferência não passou",
                pc.frase_reproducao(situacao, resumo, explicacao)
                + "\n\nO termo será gerado assim mesmo, e trará isso "
                  "escrito. Ocultá-lo seria pior.")
        TermoDerivadoDialog(termo, self).exec()

    # ── ciclo de vida ────────────────────
    def shutdown(self):
        if self._operario is not None and self._operario.isRunning():
            self._operario.wait(5000)
        if self._producao is not None:
            self._producao.fechar()
