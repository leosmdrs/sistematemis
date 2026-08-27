"""
Análise de Planilha — a tela.

A ferramenta é o roteiro. Tudo o que a tela oferece é acrescentar,
editar, remover e reordenar operações; não existe caminho para alterar
uma célula, e é essa ausência que faz a peça poder afirmar que a relação
de passos é completa (ver o cabeçalho de `planilha_core`).

A cada mudança no roteiro a análise é refeita **do começo**, sobre a
tabela lida do arquivo. Poderia ser incremental, e seria mais rápido —
mas aí o que aparece na tela seria fruto do caminho percorrido pelo
operador, e não do roteiro. Refazer do zero garante que a tela mostre
exatamente o que qualquer pessoa obteria re-executando a peça. Custa
milésimos: filtrar cem mil linhas leva 0,05 s.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QAbstractTableModel, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QDialog, QDialogButtonBox,
    QFileDialog,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPlainTextEdit, QProgressDialog, QPushButton,
    QStackedWidget, QTableView, QVBoxLayout, QWidget,
)

from ..icons import draw_icon
from ..theme import PALETTE
from ..widgets import (NoScrollComboBox, NoScrollSpinBox, SidebarPanel,
                       field_label, fit_to_screen, group_title, hsep,
                       output_button, primary_button, subtext)
from . import planilha_core as pc
from .base import ToolMeta, ToolPage
from .derivado_dialogo import TermoDerivadoDialog

#: Quantas linhas a tela mostra. Cem mil linhas numa QTableView é lento
#: de rolar e não serve para nada: ninguém confere planilha de olho. O
#: que importa é a contagem de cada passo, que é exata.
TETO_VISTA = 5000


# ─────────────────────────────────────────
#  A TABELA NA TELA
# ─────────────────────────────────────────

class ModeloTabela(QAbstractTableModel):
    """Mostra uma `pc.Tabela` sem copiar os dados."""

    def __init__(self, tabela: pc.Tabela | None = None):
        super().__init__()
        self._t = tabela or pc.Tabela()

    def trocar(self, tabela: pc.Tabela):
        self.beginResetModel()
        self._t = tabela
        self.endResetModel()

    def rowCount(self, parent=None):
        return min(self._t.n_linhas, TETO_VISTA)

    def columnCount(self, parent=None):
        return self._t.n_colunas

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            linha = self._t.linhas[index.row()]
            if index.column() < len(linha):
                return pc.texto(linha[index.column()])
        return None

    def headerData(self, secao, orientacao, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientacao == Qt.Orientation.Horizontal:
            return (self._t.colunas[secao] if secao < self._t.n_colunas
                    else None)
        return secao + 1


class Leitor(QThread):
    """Lê a planilha fora da linha da interface.

    Cem mil linhas levam uns quinze segundos para serem lidas do disco.
    Fazer isso na linha da interface deixaria a janela branca e sem
    resposta, e o Windows a ofereceria para ser encerrada.
    """

    pronto = pyqtSignal(object, object)     # (Analise, Tabela)
    falhou = pyqtSignal(str)

    def __init__(self, caminho: str, aba: str, linha: int):
        super().__init__()
        self._args = (caminho, aba, linha)

    def run(self):
        try:
            analise, tabela = pc.abrir(*self._args)
        except Exception as e:                              # noqa: BLE001
            self.falhou.emit(f"{type(e).__name__}: {e}")
            return
        self.pronto.emit(analise, tabela)


# ─────────────────────────────────────────
#  O DIÁLOGO DE UMA OPERAÇÃO
# ─────────────────────────────────────────

class DialogoOperacao(QDialog):
    """Monta uma operação do roteiro, ou edita uma já existente."""

    #: (rótulo na tela, chave)
    FAMILIAS = (
        ("Filtrar linhas", "filtro"),
        ("Ordenar", "ordenacao"),
        ("Escolher colunas", "colunas"),
        ("Remover duplicidades", "duplicidades"),
        ("Acrescentar coluna calculada", "derivada"),
        ("Agrupar e resumir", "agrupamento"),
        ("Marcar linhas", "marcacao"),
        ("Cruzar com outra planilha", "cruzamento"),
    )

    def __init__(self, colunas: list, operacao=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Operação da análise")
        self._colunas = list(colunas)
        fit_to_screen(self, 620, 560)

        fora = QVBoxLayout(self)
        fora.setContentsMargins(20, 18, 20, 16)
        fora.setSpacing(12)

        fora.addWidget(field_label("Tipo de operação"))
        self._familia = NoScrollComboBox()
        for rotulo, chave in self.FAMILIAS:
            self._familia.addItem(rotulo, chave)
        fora.addWidget(self._familia)

        self._paginas = QStackedWidget()
        self._paginas.addWidget(self._pagina_filtro())
        self._paginas.addWidget(self._pagina_ordenacao())
        self._paginas.addWidget(self._pagina_colunas())
        self._paginas.addWidget(self._pagina_duplicidades())
        self._paginas.addWidget(self._pagina_derivada())
        self._paginas.addWidget(self._pagina_agrupamento())
        self._paginas.addWidget(self._pagina_marcacao())
        self._paginas.addWidget(self._pagina_cruzamento())
        self._familia.currentIndexChanged.connect(self._paginas.setCurrentIndex)
        fora.addWidget(self._paginas, 1)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        fora.addWidget(botoes)

        if operacao is not None:
            self._carregar(operacao)

    # ── páginas ──────────────────────────
    def _combo_colunas(self) -> NoScrollComboBox:
        c = NoScrollComboBox()
        c.addItems(self._colunas)
        return c

    def _bloco_condicao(self, lay, ao_mudar) -> dict:
        """Os widgets das catorze condições, montados uma vez só.

        Filtrar e Marcar escolhem linhas pela mesma regra — no núcleo é
        a mesma função `avaliar`. Se a tela montasse a condição duas
        vezes, uma condição nova apareceria num lugar e não no outro, e
        o operador veria duas ferramentas que dizem julgar igual e não
        julgam.
        """
        campos = {}
        lay.addWidget(field_label("Coluna"))
        campos["coluna"] = self._combo_colunas()
        lay.addWidget(campos["coluna"])

        lay.addWidget(field_label("Condição"))
        condicao = NoScrollComboBox()
        for chave, (rotulo, _) in pc.CONDICOES.items():
            condicao.addItem(rotulo, chave)
        condicao.currentIndexChanged.connect(ao_mudar)
        campos["condicao"] = condicao
        lay.addWidget(condicao)

        campos["rotulo_valor"] = field_label("Valor")
        lay.addWidget(campos["rotulo_valor"])
        # Caixa de várias linhas porque a lista de alvos costuma vir
        # colada de outra planilha ou de uma decisão — um valor por linha.
        valor = QPlainTextEdit()
        valor.setMaximumHeight(96)
        valor.setPlaceholderText(
            "Um valor. Para a condição de lista, um por linha.")
        campos["valor"] = valor
        lay.addWidget(valor)

        campos["rotulo_valor2"] = field_label("Até")
        lay.addWidget(campos["rotulo_valor2"])
        valor2 = QPlainTextEdit()
        valor2.setMaximumHeight(44)
        campos["valor2"] = valor2
        lay.addWidget(valor2)

        sensivel = QCheckBox("Distinguir maiúsculas e acentos")
        sensivel.setToolTip(
            'Desmarcado, "José" e "JOSE" são a mesma coisa. A escolha vai '
            "declarada no termo, porque muda o resultado.")
        campos["sensivel"] = sensivel
        lay.addWidget(sensivel)
        return campos

    @staticmethod
    def _ajustar_condicao(campos: dict):
        chave = campos["condicao"].currentData() or "igual"
        _, quantos = pc.CONDICOES.get(chave, ("", 1))
        campos["rotulo_valor"].setVisible(quantos >= 1)
        campos["valor"].setVisible(quantos >= 1)
        campos["rotulo_valor2"].setVisible(quantos >= 2)
        campos["valor2"].setVisible(quantos >= 2)
        campos["sensivel"].setVisible(
            quantos >= 1 and chave not in pc.ORDINAIS)

    @staticmethod
    def _ler_condicao(campos: dict) -> dict:
        return {"coluna": campos["coluna"].currentText(),
                "condicao": campos["condicao"].currentData() or "igual",
                "valor": campos["valor"].toPlainText().strip(),
                "valor2": campos["valor2"].toPlainText().strip(),
                "sensivel": campos["sensivel"].isChecked()}

    @staticmethod
    def _por_condicao(campos: dict, op):
        campos["coluna"].setCurrentText(op.coluna)
        i = campos["condicao"].findData(op.condicao)
        if i >= 0:
            campos["condicao"].setCurrentIndex(i)
        campos["valor"].setPlainText(op.valor)
        campos["valor2"].setPlainText(op.valor2)
        campos["sensivel"].setChecked(op.sensivel)

    def _pagina_filtro(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(8)

        self._f = self._bloco_condicao(lay, self._ajustar_filtro)

        self._f_descartar = QCheckBox("Descartar as linhas que atendem, "
                                      "em vez de mantê-las")
        lay.addWidget(self._f_descartar)
        lay.addStretch()
        self._ajustar_filtro()
        return w

    def _ajustar_filtro(self):
        self._ajustar_condicao(self._f)

    def _pagina_ordenacao(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(subtext(
            "A segunda e a terceira colunas desempatam a primeira.",
            wrap=True))
        self._o_colunas, self._o_ordens = [], []
        for i in range(3):
            lay.addWidget(field_label(
                ["Ordenar por", "Depois por", "Depois por"][i]))
            linha = QHBoxLayout()
            coluna = NoScrollComboBox()
            coluna.addItem("—", "")
            coluna.addItems(self._colunas)
            ordem = NoScrollComboBox()
            ordem.addItem("Do menor para o maior", False)
            ordem.addItem("Do maior para o menor", True)
            linha.addWidget(coluna, 2)
            linha.addWidget(ordem, 1)
            lay.addLayout(linha)
            self._o_colunas.append(coluna)
            self._o_ordens.append(ordem)
        lay.addStretch()
        return w

    def _lista_marcavel(self, marcadas=True) -> QListWidget:
        lista = QListWidget()
        lista.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for nome in self._colunas:
            item = QListWidgetItem(nome)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if marcadas
                               else Qt.CheckState.Unchecked)
            lista.addItem(item)
        return lista

    def _pagina_colunas(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(subtext(
            "As colunas desmarcadas não seguem para o resultado. Arraste "
            "para mudar a ordem em que elas sairão. O termo registra "
            "quais ficaram.", wrap=True))
        self._c_lista = self._lista_marcavel(True)
        # A ordem da lista é a ordem das colunas no resultado, e por isso
        # precisa ser arrastável: sem isso, abrir uma operação para
        # editá-la devolveria as colunas na ordem do arquivo, desfazendo
        # em silêncio uma reordenação deliberada — e mudando o resultado.
        self._c_lista.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)   # para arrastar
        self._c_lista.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove)
        self._c_lista.setDefaultDropAction(Qt.DropAction.MoveAction)
        lay.addWidget(self._c_lista, 1)
        return w

    def _pagina_duplicidades(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(subtext(
            "Marque as colunas que identificam a repetição. Nenhuma "
            "marcada, a linha inteira é comparada.", wrap=True))
        self._d_lista = self._lista_marcavel(False)
        lay.addWidget(self._d_lista, 1)
        lay.addWidget(field_label("De cada repetição, manter"))
        self._d_qual = NoScrollComboBox()
        self._d_qual.addItem("A primeira ocorrência", "primeira")
        self._d_qual.addItem("A última ocorrência", "ultima")
        self._d_qual.setToolTip(
            "Muda o dado que sobra: numa planilha ordenada por data, é a "
            "diferença entre o primeiro e o último registro de cada um.")
        lay.addWidget(self._d_qual)
        return w

    # ── coluna derivada ──────────────────
    #: Resumo -> como aparece na tela. O núcleo guarda só o nome curto.
    ROTULOS_RESUMO = (("contar", "Quantidade de linhas"), ("somar", "Soma"),
                      ("media", "Média"), ("maximo", "Maior"),
                      ("minimo", "Menor"))

    def _pagina_derivada(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(subtext(
            "A coluna nova sai de um cálculo sobre as que já existem, e o "
            "cálculo vai declarado no termo. Coluna existente nunca é "
            "substituída: escolhendo um nome já em uso, o passo não "
            "executa e o termo diz por quê.", wrap=True))

        lay.addWidget(field_label("Nome da coluna nova"))
        self._r_titulo = QLineEdit()
        self._r_titulo.setPlaceholderText("Como ela se chamará no resultado")
        lay.addWidget(self._r_titulo)

        lay.addWidget(field_label("Cálculo"))
        self._r_calculo = NoScrollComboBox()
        for chave, (rotulo, _) in pc.CALCULOS.items():
            self._r_calculo.addItem(rotulo, chave)
        lay.addWidget(self._r_calculo)

        self._r_paginas = QStackedWidget()
        self._r_paginas.addWidget(self._sub_juntar())
        self._r_paginas.addWidget(self._sub_extrair())
        self._r_paginas.addWidget(self._sub_dias())
        self._r_calculo.currentIndexChanged.connect(
            self._r_paginas.setCurrentIndex)
        lay.addWidget(self._r_paginas, 1)
        return w

    def _sub_juntar(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(subtext(
            "Marque as colunas a juntar e arraste para definir a ordem. "
            "Célula vazia não entra e não deixa separador sobrando.",
            wrap=True))
        self._r_lista = self._lista_marcavel(False)
        self._r_lista.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self._r_lista.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove)
        self._r_lista.setDefaultDropAction(Qt.DropAction.MoveAction)
        lay.addWidget(self._r_lista, 1)
        lay.addWidget(field_label("Entre um pedaço e outro"))
        self._r_sep = QLineEdit(" ")
        lay.addWidget(self._r_sep)
        return w

    def _sub_extrair(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(field_label("Da coluna"))
        self._r_col_extrair = self._combo_colunas()
        lay.addWidget(self._r_col_extrair)

        linha = QHBoxLayout()
        esquerda = QVBoxLayout()
        esquerda.addWidget(field_label("A partir do caractere"))
        self._r_inicio = NoScrollSpinBox()
        self._r_inicio.setRange(1, 9999)
        esquerda.addWidget(self._r_inicio)
        direita = QVBoxLayout()
        direita.addWidget(field_label("Quantos caracteres"))
        self._r_tamanho = NoScrollSpinBox()
        self._r_tamanho.setRange(0, 9999)
        self._r_tamanho.setSpecialValueText("até o fim")
        direita.addWidget(self._r_tamanho)
        linha.addLayout(esquerda)
        linha.addLayout(direita)
        lay.addLayout(linha)

        lay.addWidget(subtext(
            "Serve ao dado que vem grudado: os primeiros dígitos de um "
            "documento, o ano dentro de um número de protocolo.", wrap=True))
        lay.addStretch()
        return w

    def _sub_dias(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(field_label("Da data em"))
        self._r_de = self._combo_colunas()
        lay.addWidget(self._r_de)
        lay.addWidget(field_label("Até a data em"))
        self._r_ate = self._combo_colunas()
        lay.addWidget(self._r_ate)
        lay.addWidget(subtext(
            "O resultado é o número de dias corridos. A linha cuja data não "
            "puder ser lida fica com a coluna nova vazia, permanece no "
            "resultado, e é contada no termo — não some.", wrap=True))
        lay.addStretch()
        return w

    # ── agrupamento ──────────────────────
    def _pagina_agrupamento(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(subtext(
            "Uma linha por grupo — o quadro-resumo que vai na peça. Os "
            "grupos se formam pelo texto exato da célula e saem na ordem "
            "em que apareceram, de modo que uma ordenação feita antes "
            "continua valendo.", wrap=True))

        lay.addWidget(field_label("Agrupar por"))
        self._g_lista = self._lista_marcavel(False)
        self._g_lista.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self._g_lista.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove)
        self._g_lista.setDefaultDropAction(Qt.DropAction.MoveAction)
        lay.addWidget(self._g_lista, 1)

        lay.addWidget(field_label("Resumir"))
        self._g_funcoes, self._g_colunas_resumo = [], []
        for i in range(3):
            linha = QHBoxLayout()
            funcao = NoScrollComboBox()
            funcao.addItem("—", "")
            for chave, rotulo in self.ROTULOS_RESUMO:
                funcao.addItem(rotulo, chave)
            coluna = NoScrollComboBox()
            coluna.addItem("—", "")
            coluna.addItems(self._colunas)
            funcao.currentIndexChanged.connect(
                lambda _=0, k=i: self._ajustar_resumo(k))
            linha.addWidget(funcao, 2)
            linha.addWidget(coluna, 2)
            lay.addLayout(linha)
            self._g_funcoes.append(funcao)
            self._g_colunas_resumo.append(coluna)
        for i in range(3):
            self._ajustar_resumo(i)
        return w

    def _ajustar_resumo(self, i: int):
        """A contagem não pede coluna; as demais pedem."""
        chave = self._g_funcoes[i].currentData() or ""
        precisa = bool(chave) and pc.RESUMOS.get(chave, ("", True))[1]
        self._g_colunas_resumo[i].setEnabled(precisa)
        if not precisa:
            self._g_colunas_resumo[i].setCurrentIndex(0)

    # ── marcação ─────────────────────────
    def _pagina_marcacao(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(subtext(
            "Ocupa o lugar de pintar a célula de amarelo, com uma "
            "diferença: a marca nasce de uma regra declarada, vai na peça "
            "junto da razão de tê-la aplicado, e qualquer pessoa "
            "re-executa e obtém as mesmas linhas. Marcando de novo na "
            "mesma coluna, a marca se soma à que já estava — nada é "
            "apagado.", wrap=True))

        self._m = self._bloco_condicao(lay, self._ajustar_marcacao)

        linha = QHBoxLayout()
        esquerda = QVBoxLayout()
        esquerda.addWidget(field_label("Coluna da marcação"))
        self._m_destino = QLineEdit("Marcação")
        esquerda.addWidget(self._m_destino)
        direita = QVBoxLayout()
        direita.addWidget(field_label("Marca"))
        self._m_marca = QLineEdit("SIM")
        direita.addWidget(self._m_marca)
        linha.addLayout(esquerda)
        linha.addLayout(direita)
        lay.addLayout(linha)

        lay.addWidget(field_label("Justificativa"))
        self._m_justificativa = QPlainTextEdit()
        self._m_justificativa.setMaximumHeight(70)
        self._m_justificativa.setPlaceholderText(
            "Por que estas linhas foram separadas. Sai impresso no termo.")
        lay.addWidget(self._m_justificativa)
        lay.addStretch()
        self._ajustar_marcacao()
        return w

    def _ajustar_marcacao(self):
        self._ajustar_condicao(self._m)

    # ── cruzamento ───────────────────────
    #: Filtros do seletor de arquivo, iguais aos da abertura principal.
    FILTROS = ("Planilhas (*.xlsx *.xlsm *.xlsb *.xls *.ods *.csv *.txt)"
               ";;Todos os arquivos (*)")

    def _pagina_cruzamento(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(subtext(
            "É o PROCV. A planilha escolhida aqui entra no termo como "
            "segunda origem, com resumo criptográfico próprio — o achado "
            "depende dos dois arquivos, e a peça precisa dizer contra o "
            "que o cruzamento foi feito.", wrap=True))

        # Estado da planilha do outro lado. Só a tela guarda; a operação
        # leva o caminho e o resumo, e relê por conta própria.
        self._x_caminho = ""
        self._x_resumo = ""
        self._x_recarregando = False

        escolha = QHBoxLayout()
        botao = QPushButton("Escolher planilha…")
        botao.clicked.connect(self._escolher_cruzada)
        self._x_rotulo = QLabel("nenhuma escolhida")
        self._x_rotulo.setWordWrap(True)
        escolha.addWidget(botao)
        escolha.addWidget(self._x_rotulo, 1)
        lay.addLayout(escolha)

        leitura = QHBoxLayout()
        esquerda = QVBoxLayout()
        esquerda.addWidget(field_label("Aba"))
        self._x_aba = NoScrollComboBox()
        esquerda.addWidget(self._x_aba)
        direita = QVBoxLayout()
        direita.addWidget(field_label("Linha do cabeçalho"))
        self._x_cabecalho = NoScrollSpinBox()
        self._x_cabecalho.setRange(1, 200)
        direita.addWidget(self._x_cabecalho)
        leitura.addLayout(esquerda, 2)
        leitura.addLayout(direita, 1)
        lay.addLayout(leitura)

        chaves = QHBoxLayout()
        aqui = QVBoxLayout()
        aqui.addWidget(field_label("Casar esta coluna"))
        self._x_chave_aqui = self._combo_colunas()
        aqui.addWidget(self._x_chave_aqui)
        la = QVBoxLayout()
        la.addWidget(field_label("Com esta, da outra"))
        self._x_chave_la = NoScrollComboBox()
        la.addWidget(self._x_chave_la)
        chaves.addLayout(aqui)
        chaves.addLayout(la)
        lay.addLayout(chaves)

        lay.addWidget(field_label("Trazer as colunas"))
        self._x_trazer = QListWidget()
        self._x_trazer.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        lay.addWidget(self._x_trazer, 1)

        self._x_sensivel = QCheckBox(
            "Distinguir maiúsculas e acentos ao casar as chaves")
        lay.addWidget(self._x_sensivel)

        lay.addWidget(field_label("Linhas que não encontrarem par"))
        self._x_sem_par = NoScrollComboBox()
        self._x_sem_par.addItem("Manter, com as colunas trazidas vazias",
                                "manter")
        self._x_sem_par.addItem("Descartar", "descartar")
        self._x_sem_par.addItem("Ficar só com elas — a relação das "
                                "divergências", "somente")
        self._x_sem_par.setToolTip(
            "A terceira é o cruzamento que costuma produzir o achado: quem "
            "está de um lado e não está do outro.")
        lay.addWidget(self._x_sem_par)

        self._x_aba.currentIndexChanged.connect(self._reler_cruzada)
        self._x_cabecalho.valueChanged.connect(self._reler_cruzada)
        return w

    def _escolher_cruzada(self):
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Escolher a planilha a cruzar", str(Path.home()),
            self.FILTROS)
        if not caminho:
            return
        try:
            nomes = pc.abas(caminho)
        except Exception as e:                              # noqa: BLE001
            QMessageBox.warning(self, "Não foi possível abrir",
                                f"{type(e).__name__}: {e}")
            return
        self._x_caminho = caminho
        self._x_recarregando = True
        self._x_aba.clear()
        self._x_aba.addItems(nomes)
        self._x_aba.setEnabled(len(nomes) > 1)
        self._x_cabecalho.setValue(1)
        self._x_recarregando = False
        self._reler_cruzada()

    def _reler_cruzada(self):
        """Relê a planilha do outro lado e reoferece as colunas dela.

        Vai pela mesma `ler_auxiliar` que a operação usa, e portanto pelo
        mesmo cache: oferecer aqui colunas lidas de outro jeito criaria a
        chance de a operação, depois, não encontrar a que foi escolhida.
        """
        if self._x_recarregando or not self._x_caminho:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            tabela, resumo, erro = pc.ler_auxiliar(
                self._x_caminho, self._aba_cruzada(),
                self._x_cabecalho.value())
        finally:
            QApplication.restoreOverrideCursor()
        if tabela is None:
            self._x_rotulo.setText("não foi possível ler: " + erro)
            return
        self._x_resumo = resumo
        self._x_rotulo.setText(
            Path(self._x_caminho).name + " — " + str(tabela.n_linhas)
            + " linha(s), " + str(tabela.n_colunas) + " coluna(s)")
        marcadas = set(self._marcadas(self._x_trazer))
        escolhida = self._x_chave_la.currentText()
        self._x_chave_la.clear()
        self._x_chave_la.addItems(tabela.colunas)
        if escolhida in tabela.colunas:
            self._x_chave_la.setCurrentText(escolhida)
        self._x_trazer.clear()
        for nome in tabela.colunas:
            item = QListWidgetItem(nome)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if nome in marcadas
                               else Qt.CheckState.Unchecked)
            self._x_trazer.addItem(item)

    def _aba_cruzada(self) -> str:
        return self._x_aba.currentText() if self._x_aba.count() > 1 else ""

    # ── entrada e saída ──────────────────
    def _carregar(self, op):
        indices = {chave: i for i, (_, chave) in enumerate(self.FAMILIAS)}
        self._familia.setCurrentIndex(indices.get(op.tipo, 0))
        self._paginas.setCurrentIndex(indices.get(op.tipo, 0))
        if isinstance(op, pc.Filtro):
            self._por_condicao(self._f, op)
            self._f_descartar.setChecked(not op.manter)
            self._ajustar_filtro()
        elif isinstance(op, pc.Ordenacao):
            for i, (coluna, desc) in enumerate(op.chaves[:3]):
                self._o_colunas[i].setCurrentText(coluna)
                self._o_ordens[i].setCurrentIndex(1 if desc else 0)
        elif isinstance(op, pc.Colunas):
            # As escolhidas primeiro, na ordem em que a operação as tem —
            # que é a ordem em que sairão —, e as demais depois.
            resto = [c for c in self._colunas if c not in op.manter]
            self._c_lista.clear()
            for nome in list(op.manter) + resto:
                item = QListWidgetItem(nome)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if nome in op.manter
                                   else Qt.CheckState.Unchecked)
                self._c_lista.addItem(item)
        elif isinstance(op, pc.Duplicidades):
            for i in range(self._d_lista.count()):
                item = self._d_lista.item(i)
                item.setCheckState(Qt.CheckState.Checked
                                   if item.text() in op.chaves
                                   else Qt.CheckState.Unchecked)
            j = self._d_qual.findData(op.manter)
            if j >= 0:
                self._d_qual.setCurrentIndex(j)
        elif isinstance(op, pc.Derivada):
            self._r_titulo.setText(op.nome)
            i = self._r_calculo.findData(op.calculo)
            if i >= 0:
                self._r_calculo.setCurrentIndex(i)
                self._r_paginas.setCurrentIndex(i)
            if op.calculo == "juntar":
                self._reordenar(self._r_lista, op.origens)
                self._r_sep.setText(op.separador)
            elif op.calculo == "extrair":
                if op.origens:
                    self._r_col_extrair.setCurrentText(op.origens[0])
                self._r_inicio.setValue(max(1, int(op.inicio)))
                self._r_tamanho.setValue(max(0, int(op.tamanho)))
            elif len(op.origens) >= 2:
                self._r_de.setCurrentText(op.origens[0])
                self._r_ate.setCurrentText(op.origens[1])
        elif isinstance(op, pc.Agrupamento):
            self._reordenar(self._g_lista, op.chaves)
            for i, (resumo, coluna) in enumerate(op.resumos[:3]):
                k = self._g_funcoes[i].findData(resumo)
                if k >= 0:
                    self._g_funcoes[i].setCurrentIndex(k)
                self._ajustar_resumo(i)
                if coluna:
                    self._g_colunas_resumo[i].setCurrentText(coluna)
        elif isinstance(op, pc.Marcacao):
            self._por_condicao(self._m, op)
            self._m_destino.setText(op.coluna_marca)
            self._m_marca.setText(op.marca)
            self._m_justificativa.setPlainText(op.justificativa)
            self._ajustar_marcacao()
        elif isinstance(op, pc.Cruzamento):
            self._x_caminho = op.arquivo
            self._x_resumo = op.resumo_arquivo
            self._x_recarregando = True
            self._x_aba.clear()
            try:
                nomes = pc.abas(op.arquivo) if op.arquivo else []
            except Exception:                               # noqa: BLE001
                nomes = []
            self._x_aba.addItems(nomes)
            self._x_aba.setEnabled(len(nomes) > 1)
            if op.aba and op.aba in nomes:
                self._x_aba.setCurrentText(op.aba)
            self._x_cabecalho.setValue(max(1, int(op.linha_cabecalho)))
            self._x_recarregando = False
            self._reler_cruzada()
            self._x_chave_aqui.setCurrentText(op.chave_aqui)
            self._x_chave_la.setCurrentText(op.chave_la)
            for i in range(self._x_trazer.count()):
                item = self._x_trazer.item(i)
                item.setCheckState(Qt.CheckState.Checked
                                   if item.text() in op.trazer
                                   else Qt.CheckState.Unchecked)
            self._x_sensivel.setChecked(op.sensivel)
            j = self._x_sem_par.findData(op.sem_par)
            if j >= 0:
                self._x_sem_par.setCurrentIndex(j)

    def _reordenar(self, lista: QListWidget, escolhidas: list):
        """Repõe a lista com as escolhidas em cima, na ordem da operação.

        A ordem é resultado, e não enfeite: ela decide a ordem de junção
        e a das colunas de grupo. Reabrir uma operação para editá-la e
        recebê-la na ordem do arquivo desfaria em silêncio uma escolha
        deliberada — e mudaria o que a peça declara.
        """
        resto = [c for c in self._colunas if c not in escolhidas]
        lista.clear()
        for nome in list(escolhidas) + resto:
            item = QListWidgetItem(nome)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if nome in escolhidas
                               else Qt.CheckState.Unchecked)
            lista.addItem(item)

    @staticmethod
    def _marcadas(lista: QListWidget) -> list:
        return [lista.item(i).text() for i in range(lista.count())
                if lista.item(i).checkState() == Qt.CheckState.Checked]

    def operacao(self):
        """A operação montada, ou None se a escolha estiver incompleta."""
        chave = self._familia.currentData()
        if chave == "filtro":
            return pc.Filtro(manter=not self._f_descartar.isChecked(),
                             **self._ler_condicao(self._f))
        if chave == "ordenacao":
            chaves = [(c.currentText(), bool(o.currentData()))
                      for c, o in zip(self._o_colunas, self._o_ordens)
                      if c.currentIndex() > 0]
            return pc.Ordenacao(chaves=chaves) if chaves else None
        if chave == "colunas":
            manter = self._marcadas(self._c_lista)
            return pc.Colunas(manter=manter) if manter else None
        if chave == "duplicidades":
            return pc.Duplicidades(
                chaves=self._marcadas(self._d_lista),
                manter=self._d_qual.currentData() or "primeira")
        if chave == "cruzamento":
            if not self._x_caminho or self._x_chave_la.currentIndex() < 0:
                return None
            return pc.Cruzamento(
                arquivo=self._x_caminho, resumo_arquivo=self._x_resumo,
                aba=self._aba_cruzada(),
                linha_cabecalho=self._x_cabecalho.value(),
                chave_aqui=self._x_chave_aqui.currentText(),
                chave_la=self._x_chave_la.currentText(),
                trazer=self._marcadas(self._x_trazer),
                sensivel=self._x_sensivel.isChecked(),
                sem_par=self._x_sem_par.currentData() or "manter")
        if chave == "derivada":
            return self._operacao_derivada()
        if chave == "agrupamento":
            return self._operacao_agrupamento()
        if chave == "marcacao":
            marca = self._m_marca.text().strip()
            if not marca:
                return None
            return pc.Marcacao(
                coluna_marca=self._m_destino.text().strip() or "Marcação",
                marca=marca,
                justificativa=self._m_justificativa.toPlainText().strip(),
                **self._ler_condicao(self._m))
        return None

    def _operacao_derivada(self):
        nome = self._r_titulo.text().strip()
        if not nome:
            return None
        calculo = self._r_calculo.currentData() or "juntar"
        if calculo == "juntar":
            origens = self._marcadas(self._r_lista)
            if not origens:
                return None
            return pc.Derivada(nome=nome, calculo="juntar", origens=origens,
                               separador=self._r_sep.text())
        if calculo == "extrair":
            return pc.Derivada(nome=nome, calculo="extrair",
                               origens=[self._r_col_extrair.currentText()],
                               inicio=self._r_inicio.value(),
                               tamanho=self._r_tamanho.value())
        de, ate = self._r_de.currentText(), self._r_ate.currentText()
        if not de or not ate:
            return None
        return pc.Derivada(nome=nome, calculo="dias", origens=[de, ate])

    def _operacao_agrupamento(self):
        chaves = self._marcadas(self._g_lista)
        if not chaves:
            return None
        resumos = []
        for funcao, coluna in zip(self._g_funcoes, self._g_colunas_resumo):
            resumo = funcao.currentData() or ""
            if not resumo:
                continue
            precisa = pc.RESUMOS.get(resumo, ("", True))[1]
            alvo = coluna.currentText() if (precisa
                                            and coluna.currentIndex() > 0) else ""
            if precisa and not alvo:
                continue
            resumos.append((resumo, alvo))
        return pc.Agrupamento(chaves=chaves, resumos=resumos) if resumos else None


# ─────────────────────────────────────────
#  A FERRAMENTA
# ─────────────────────────────────────────

class PlanilhaTool(ToolPage):
    """Abrir a planilha, montar o roteiro, gravar o resultado e a peça."""

    meta = ToolMeta(
        key="planilha",
        name="Análise de Planilha",
        icon="tool_planilha",
        tagline="Examina planilha registrando cada passo",
        description=(
            "Abre planilhas de auditoria e permite filtrar, ordenar, escolher "
            "colunas, remover duplicidades, acrescentar coluna calculada, "
            "agrupar e resumir, marcar linhas com justificativa e cruzar com "
            "outra planilha — registrando cada passo. Ao fim, produz o "
            "arquivo com o resultado e um termo que identifica original e "
            "resultado pelos resumos criptográficos e traz o roteiro "
            "completo da análise, que pode ser re-executado por terceiro "
            "para conferir que o resultado é aquele mesmo."),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._analise = None
        self._base = pc.Tabela()
        self._resultado = pc.Tabela()
        self._passos: list = []
        self._salvo = ""
        self._leitor = None

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

        abrir = primary_button("Abrir planilha")
        abrir.clicked.connect(self._abrir)
        p.header.addWidget(abrir)

        self._lbl_arquivo = QLabel("Nenhuma planilha aberta")
        self._lbl_arquivo.setObjectName("subtext")
        self._lbl_arquivo.setWordWrap(True)
        p.header.addWidget(self._lbl_arquivo)

        # ── de onde ler dentro do arquivo
        self._cx_leitura = QWidget()
        leitura = QVBoxLayout(self._cx_leitura)
        leitura.setContentsMargins(0, 0, 0, 0)
        leitura.setSpacing(6)
        leitura.addWidget(field_label("Aba"))
        self._cb_aba = NoScrollComboBox()
        self._cb_aba.currentIndexChanged.connect(self._reler)
        leitura.addWidget(self._cb_aba)
        leitura.addWidget(field_label("Linha do cabeçalho"))
        self._sp_cabecalho = NoScrollSpinBox()
        self._sp_cabecalho.setRange(1, 100)
        self._sp_cabecalho.setToolTip(
            "Exportação com brasão ou título em cima começa a tabela mais "
            "abaixo. Esta é a linha em que estão os nomes das colunas.")
        self._sp_cabecalho.valueChanged.connect(self._reler)
        leitura.addWidget(self._sp_cabecalho)
        p.body.addWidget(self._cx_leitura)

        self._lbl_alerta = QLabel("")
        self._lbl_alerta.setObjectName("subtext")
        self._lbl_alerta.setWordWrap(True)
        self._lbl_alerta.setStyleSheet(f"color: {PALETTE['warning']};")
        p.body.addWidget(self._lbl_alerta)

        p.body.addWidget(hsep())
        p.body.addWidget(group_title("Roteiro da análise"))

        self._lista = QListWidget()
        self._lista.setWordWrap(True)
        self._lista.setMinimumHeight(180)
        self._lista.itemDoubleClicked.connect(lambda *_: self._editar())
        p.body.addWidget(self._lista, 1)

        linha = QHBoxLayout()
        linha.setSpacing(6)
        self._bt_mais = QPushButton("  Acrescentar")
        self._bt_mais.setIcon(draw_icon("plus", 14, PALETTE["text"]))
        self._bt_mais.clicked.connect(self._acrescentar)
        linha.addWidget(self._bt_mais, 1)
        self._bt_menos = QPushButton("")
        self._bt_menos.setIcon(draw_icon("minus", 14, PALETTE["text"]))
        self._bt_menos.setToolTip("Remover a operação selecionada")
        self._bt_menos.setFixedWidth(38)
        self._bt_menos.clicked.connect(self._remover)
        linha.addWidget(self._bt_menos)
        self._bt_sobe = QPushButton("↑")
        self._bt_sobe.setToolTip("Adiantar a operação — a ordem muda o resultado")
        self._bt_sobe.setFixedWidth(32)
        self._bt_sobe.clicked.connect(lambda: self._mover(-1))
        linha.addWidget(self._bt_sobe)
        self._bt_desce = QPushButton("↓")
        self._bt_desce.setToolTip("Atrasar a operação")
        self._bt_desce.setFixedWidth(32)
        self._bt_desce.clicked.connect(lambda: self._mover(1))
        linha.addWidget(self._bt_desce)
        caixa = QWidget()
        caixa.setLayout(linha)
        p.body.addWidget(caixa)

        p.body.addWidget(subtext(
            "A ordem importa: filtrar antes ou depois de remover "
            "duplicidades dá resultados diferentes.", wrap=True))

        # ── rodapé
        self._bt_salvar = output_button("Salvar resultado")
        self._bt_salvar.clicked.connect(self._salvar_resultado)
        p.footer.addWidget(self._bt_salvar)

        roteiro = QHBoxLayout()
        roteiro.setSpacing(6)
        self._bt_grava_rot = QPushButton("Salvar roteiro")
        self._bt_grava_rot.setToolTip(
            "Grava o roteiro em arquivo, para acompanhar a peça nos autos e "
            "permitir que terceiro refaça a análise")
        self._bt_grava_rot.clicked.connect(self._salvar_roteiro)
        roteiro.addWidget(self._bt_grava_rot, 1)
        self._bt_le_rot = QPushButton("Abrir roteiro")
        self._bt_le_rot.setToolTip("Aplica a esta planilha um roteiro salvo")
        self._bt_le_rot.clicked.connect(self._abrir_roteiro)
        roteiro.addWidget(self._bt_le_rot, 1)
        cx = QWidget()
        cx.setLayout(roteiro)
        p.footer.addWidget(cx)

        # O termo cita o resumo criptográfico do arquivo produzido, e esse
        # resumo só existe depois de o arquivo ser gravado: é calculado
        # sobre os bytes finais. Por isso o botão nasce desligado.
        self._bt_termo = output_button("Gerar termo de análise")
        self._bt_termo.setEnabled(False)
        self._bt_termo.setToolTip(
            "Disponível depois de salvar o resultado — a peça cita o resumo "
            "criptográfico do arquivo produzido")
        self._bt_termo.clicked.connect(self._gerar_termo)
        p.footer.addWidget(self._bt_termo)
        return p

    def _montar_vista(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(8)

        self._lbl_contagem = QLabel("")
        fonte = QFont()
        fonte.setPointSize(11)
        fonte.setBold(True)
        self._lbl_contagem.setFont(fonte)
        lay.addWidget(self._lbl_contagem)

        self._lbl_teto = QLabel("")
        self._lbl_teto.setObjectName("subtext")
        lay.addWidget(self._lbl_teto)

        self._modelo = ModeloTabela()
        self._tabela = QTableView()
        self._tabela.setModel(self._modelo)
        self._tabela.setAlternatingRowColors(True)
        self._tabela.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tabela.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)   # ver o módulo
        self._tabela.horizontalHeader().setStretchLastSection(True)
        self._tabela.verticalHeader().setDefaultSectionSize(22)
        lay.addWidget(self._tabela, 1)
        return w

    # ── abertura ─────────────────────────
    def _abrir(self):
        filtros = ("Planilhas (*.xlsx *.xlsm *.xlsb *.xls *.ods *.csv *.txt)"
                   ";;Todos os arquivos (*)")
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Abrir planilha", str(Path.home()), filtros)
        if not caminho:
            return
        try:
            nomes = pc.abas(caminho)
        except Exception as e:                              # noqa: BLE001
            QMessageBox.warning(self, "Não foi possível abrir",
                                f"{type(e).__name__}: {e}")
            return
        # Trocar de arquivo apaga o roteiro: aplicar a uma planilha os
        # passos montados para outra produziria um resultado que a peça
        # não saberia explicar.
        self._caminho = caminho
        self._passos = []
        self._salvo = ""
        self._lista.clear()
        self._cb_aba.blockSignals(True)
        self._cb_aba.clear()
        self._cb_aba.addItems(nomes)
        self._cb_aba.setEnabled(len(nomes) > 1)
        self._cb_aba.blockSignals(False)
        self._sp_cabecalho.blockSignals(True)
        self._sp_cabecalho.setValue(1)
        self._sp_cabecalho.blockSignals(False)
        self._ler(caminho, nomes[0] if len(nomes) > 1 else "", 1, [])

    def _reler(self):
        """Recarrega quando muda a aba ou a linha do cabeçalho.

        O roteiro é preservado. Se alguma coluna deixar de existir, o
        passo correspondente não se aplica e diz isso — em vez de
        desaparecer, que faria a peça mentir por omissão.
        """
        if not getattr(self, "_caminho", ""):
            return
        anteriores = list(self._analise.operacoes) if self._analise else []
        self._ler(self._caminho,
                  self._cb_aba.currentText() if self._cb_aba.count() > 1 else "",
                  self._sp_cabecalho.value(), anteriores)

    def _ler(self, caminho: str, aba: str, linha: int, operacoes: list):
        espera = QProgressDialog("Lendo a planilha…", "", 0, 0, self)
        espera.setWindowTitle("Análise de Planilha")
        espera.setCancelButton(None)
        espera.setWindowModality(Qt.WindowModality.WindowModal)
        espera.setMinimumDuration(400)

        def deu_certo(analise, tabela):
            espera.close()
            analise.operacoes = operacoes
            self._analise, self._base = analise, tabela
            self._salvo = ""
            self._refletir()
            self._atualizar()
            self.status_msg.emit(
                f"{Path(caminho).name}: {tabela.n_linhas} linhas, "
                f"{tabela.n_colunas} colunas")

        def deu_errado(motivo):
            espera.close()
            QMessageBox.warning(self, "Não foi possível ler", motivo)

        self._leitor = Leitor(caminho, aba, linha)
        self._leitor.pronto.connect(deu_certo)
        self._leitor.falhou.connect(deu_errado)
        self._leitor.start()

    # ── roteiro ──────────────────────────
    def _acrescentar(self):
        if self._analise is None:
            return
        d = DialogoOperacao(self._base.colunas, None, self)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        op = d.operacao()
        if op is None:
            return
        self._analise.operacoes.append(op)
        self._atualizar()

    def _editar(self):
        i = self._lista.currentRow()
        if self._analise is None or not 0 <= i < len(self._analise.operacoes):
            return
        d = DialogoOperacao(self._base.colunas, self._analise.operacoes[i], self)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        op = d.operacao()
        if op is None:
            return
        self._analise.operacoes[i] = op
        self._atualizar(i)

    def _remover(self):
        i = self._lista.currentRow()
        if self._analise is None or not 0 <= i < len(self._analise.operacoes):
            return
        del self._analise.operacoes[i]
        self._atualizar(min(i, len(self._analise.operacoes) - 1))

    def _mover(self, passo: int):
        i = self._lista.currentRow()
        j = i + passo
        if self._analise is None:
            return
        ops = self._analise.operacoes
        if not (0 <= i < len(ops) and 0 <= j < len(ops)):
            return
        ops[i], ops[j] = ops[j], ops[i]
        self._atualizar(j)

    def _atualizar(self, selecionar: int = -1):
        """Refaz a análise do começo e reflete tudo na tela."""
        if self._analise is None:
            return
        self._resultado, self._passos = self._analise.executar(self._base)
        # Mexer no roteiro invalida o arquivo já gravado: o termo passaria
        # a citar o resumo de um arquivo que não corresponde mais ao que
        # está na tela.
        self._salvo = ""
        self._lista.clear()
        for n, p in enumerate(self._passos, 1):
            rotulo = f"{n}. {p.descricao}\n     {p.antes} → {p.depois} linhas"
            if p.incomparaveis:
                rotulo += f"  ({p.incomparaveis} não comparadas)"
            item = QListWidgetItem(rotulo)
            if p.aviso:
                item.setText(rotulo + f"\n     {p.aviso}")
                item.setForeground(QColor(PALETTE["warning"]))
            self._lista.addItem(item)
        if selecionar >= 0:
            self._lista.setCurrentRow(selecionar)
        self._modelo.trocar(self._resultado)
        self._tabela.resizeColumnsToContents()
        self._refletir()

    # ── estado da tela ───────────────────
    def _refletir(self):
        tem = self._analise is not None
        self._cx_leitura.setVisible(tem)
        for b in (self._bt_mais, self._bt_menos, self._bt_sobe,
                  self._bt_desce, self._bt_salvar, self._bt_grava_rot,
                  self._bt_le_rot):
            b.setEnabled(tem)
        self._bt_termo.setEnabled(bool(self._salvo))
        if not tem:
            self._lbl_contagem.setText("")
            self._lbl_teto.setText("")
            self._lbl_alerta.setText("")
            return

        a = self._analise
        self._lbl_arquivo.setText(
            f"{Path(a.origem).name}\nSHA-256 {a.resumo_origem[:16]}…\n"
            f"{a.linhas_originais} linhas, {len(a.colunas_originais)} colunas")
        self._lbl_contagem.setText(
            f"{a.linhas_originais} linhas no original  →  "
            f"{self._resultado.n_linhas} no resultado"
            f"   ({self._resultado.n_colunas} colunas)")
        self._lbl_teto.setText(
            f"A tela mostra as primeiras {TETO_VISTA} linhas; o arquivo "
            f"gravado leva todas as {self._resultado.n_linhas}."
            if self._resultado.n_linhas > TETO_VISTA else "")
        self._lbl_alerta.setText(
            f"Atenção: {a.formulas_vazias} célula(s) com fórmula sem "
            "resultado gravado. O arquivo nunca foi aberto em programa que "
            "as calculasse, e elas foram lidas como vazias — filtrar por "
            "essas colunas levaria a conclusão errada."
            if a.formulas_vazias else "")

    # ── saídas ───────────────────────────
    def _salvar_resultado(self):
        if self._analise is None:
            return
        sugestao = Path(self._analise.origem)
        alvo = str(sugestao.with_name(sugestao.stem + "-analisado.xlsx"))
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar o resultado", alvo,
            "Planilha (*.xlsx);;Texto separado (*.csv)")
        if not caminho:
            return
        try:
            pc.gravar(self._resultado, caminho)
        except Exception as e:                              # noqa: BLE001
            QMessageBox.warning(self, "Não foi possível salvar",
                                f"{type(e).__name__}: {e}")
            return
        self._salvo = caminho
        self._refletir()
        self.status_msg.emit(f"Resultado salvo: {Path(caminho).name}")
        QMessageBox.information(
            self, "Resultado salvo",
            f"Arquivo gravado em:\n{caminho}\n\n"
            "O termo de análise já pode ser gerado — ele traz o roteiro "
            "completo e os resumos criptográficos do original e do "
            "resultado.")

    def _salvar_roteiro(self):
        if self._analise is None:
            return
        sugestao = Path(self._analise.origem)
        alvo = str(sugestao.with_name(sugestao.stem + "-roteiro.json"))
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar o roteiro", alvo, "Roteiro (*.json)")
        if not caminho:
            return
        try:
            pc.salvar_roteiro(self._analise, caminho)
        except OSError as e:
            QMessageBox.warning(self, "Não foi possível salvar", str(e))
            return
        self.status_msg.emit(f"Roteiro salvo: {Path(caminho).name}")

    def _abrir_roteiro(self):
        if self._analise is None:
            return
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Abrir roteiro", str(Path(self._analise.origem).parent),
            "Roteiro (*.json)")
        if not caminho:
            return
        try:
            outra = pc.ler_roteiro(caminho)
        except Exception as e:                              # noqa: BLE001
            QMessageBox.warning(self, "Não foi possível ler o roteiro",
                                f"{type(e).__name__}: {e}")
            return
        # O roteiro pode ter sido escrito para outro arquivo. Isso não é
        # erro — é o caso normal de repetir a mesma análise no mês
        # seguinte —, mas quem opera precisa saber que está fazendo isso.
        if (outra.resumo_origem and self._analise.resumo_origem
                and outra.resumo_origem != self._analise.resumo_origem):
            r = QMessageBox.question(
                self, "Roteiro de outro arquivo",
                f"Este roteiro foi montado sobre {Path(outra.origem).name}, "
                "cujo resumo criptográfico não é o da planilha aberta.\n\n"
                "Aplicar assim mesmo? Os passos que citarem colunas "
                "inexistentes serão registrados como não executados.")
            if r != QMessageBox.StandardButton.Yes:
                return
        self._analise.operacoes = outra.operacoes
        self._atualizar()

    def _gerar_termo(self):
        if self._analise is None or not self._salvo:
            return
        # A conferência roda antes da peça, e não depois: o que ela
        # apurar vai impresso, inclusive quando não confere.
        espera = QProgressDialog("Re-executando a análise para conferir…",
                                 "", 0, 0, self)
        espera.setWindowTitle("Conferência de reprodutibilidade")
        espera.setCancelButton(None)
        espera.setWindowModality(Qt.WindowModality.WindowModal)
        espera.show()
        try:
            ok, _, motivo = pc.reproduzir(self._analise,
                                          self._resultado.resumo())
        finally:
            espera.close()
        termo = pc.montar_termo(self._analise, self._resultado, self._passos,
                                self._salvo, "sim" if ok else motivo)
        if not ok:
            QMessageBox.warning(
                self, "A conferência não passou",
                "A re-execução não reproduziu o mesmo resultado:\n\n"
                f"{motivo}\n\nO termo será gerado assim mesmo, e trará "
                "essa divergência escrita. Ocultá-la seria pior.")
        TermoDerivadoDialog(termo, self, modulo=pc).exec()

    # ── ciclo de vida ────────────────────
    def shutdown(self):
        if self._leitor is not None and self._leitor.isRunning():
            self._leitor.wait(3000)
