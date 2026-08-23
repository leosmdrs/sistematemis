"""
Blocos numerados do corpo da Informação.

O corpo de cada elemento não é um texto corrido: é uma sequência de
**blocos**, cada um com um nível e um estilo de marcador. A numeração
(1.1, 1.1.1, a), I) nunca é digitada — é calculada a partir da posição.

O motivo é prático: numeração escrita à mão quebra. Basta inserir um
parágrafo no meio, ou remover um, para tudo abaixo ficar errado, e num
documento que vai aos autos isso é erro material. Calculando, inserir e
mover é seguro: a numeração se refaz sozinha.

Este módulo não depende de interface, para poder ser testado isolado.
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field, asdict


# ─────────────────────────────────────────
#  ESTILOS DE MARCADOR
# ─────────────────────────────────────────

#: Numeração composta com a do elemento e dos níveis acima: 1.1, 1.1.2.
NUMERO = "numero"
#: Alíneas a), b), c) — reiniciam a cada parágrafo-pai.
ALINEA = "alinea"
#: Incisos I, II, III — reiniciam a cada parágrafo-pai.
INCISO = "inciso"
#: Continuação sem marcador, apenas recuada no mesmo nível.
SEM_MARCADOR = "sem_marcador"

ESTILOS = {
    NUMERO: "Numeração (1.1)",
    ALINEA: "Alínea (a)",
    INCISO: "Inciso (I)",
    SEM_MARCADOR: "Sem marcador",
}

def espaco(pontos: int = 6) -> str:
    """Um respiro entre parágrafos, do tamanho pedido em pontos.

    Sai como um parágrafo vazio de fonte pequena, e não como
    `margin-bottom`: medindo a prévia constatou-se que o motor de texto do
    Qt — o mesmo que gera o PDF — ignora margem, padding e line-height em
    parágrafo. Só um bloco de verdade abre espaço, e é o que o importador
    do SEI também preserva.
    """
    return f'<p style="font-size:{pontos}pt; margin:0;">&nbsp;</p>'


#: Espaço entre um parágrafo e o seguinte.
ESPACO = 6
#: Espaço maior, em volta do título do elemento.
ESPACO_SECAO = 9

#: Recuo de cada nível, em porcentagem da largura — o mesmo mecanismo do
#: bloco da ementa, porque é o que o Qt e o SEI respeitam.
RECUO_POR_NIVEL = 4

NIVEL_MAX = 5

_ROMANOS = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
            (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
            (5, "V"), (4, "IV"), (1, "I")]


def romano(n: int) -> str:
    if n <= 0:
        return ""
    saida = []
    for valor, simbolo in _ROMANOS:
        while n >= valor:
            saida.append(simbolo)
            n -= valor
    return "".join(saida)


def letra(n: int) -> str:
    """1 → a, 2 → b … 27 → aa."""
    if n <= 0:
        return ""
    saida = ""
    while n > 0:
        n, resto = divmod(n - 1, 26)
        saida = chr(ord("a") + resto) + saida
    return saida


# ─────────────────────────────────────────
#  BLOCO
# ─────────────────────────────────────────

TEXTO = "texto"
TABELA = "tabela"


@dataclass
class Bloco:
    """Um parágrafo — ou uma tabela — do corpo de um elemento."""

    tipo: str = TEXTO
    nivel: int = 1                 # 1 = primeiro nível dentro do elemento
    estilo: str = NUMERO
    html: str = ""                 # conteúdo, quando tipo == TEXTO
    #: Grade da tabela: lista de linhas, cada uma lista de células (HTML).
    celulas: list = field(default_factory=list)
    cabecalho: bool = True         # primeira linha da tabela é cabeçalho
    #: Trecho de exemplo vindo do roteiro. Fica visível no editor como
    #: guia, mas **não entra no documento** enquanto for exemplo: o modelo
    #: da Corregedoria ilustra os itens com fatos fictícios, e um deles
    #: chegar aos autos por esquecimento seria erro grave. Escrever por
    #: cima desfaz a marca e o parágrafo passa a valer.
    exemplo: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Bloco":
        campos = {k: d[k] for k in Bloco.__dataclass_fields__ if k in d}
        return Bloco(**campos)

    # ── tabela ───────────────────────────────────
    def linhas(self) -> int:
        return len(self.celulas)

    def colunas(self) -> int:
        return len(self.celulas[0]) if self.celulas else 0

    def inserir_linha(self, onde: int | None = None):
        cols = max(1, self.colunas())
        nova = [""] * cols
        self.celulas.insert(len(self.celulas) if onde is None else onde, nova)

    def remover_linha(self, indice: int):
        if 0 <= indice < len(self.celulas) and len(self.celulas) > 1:
            self.celulas.pop(indice)

    def inserir_coluna(self, onde: int | None = None):
        for linha in self.celulas:
            linha.insert(len(linha) if onde is None else onde, "")

    def remover_coluna(self, indice: int):
        if self.colunas() <= 1:
            return
        for linha in self.celulas:
            if 0 <= indice < len(linha):
                linha.pop(indice)


def nova_tabela(linhas: int = 3, colunas: int = 3, nivel: int = 1) -> Bloco:
    return Bloco(tipo=TABELA, nivel=nivel, estilo=SEM_MARCADOR,
                 celulas=[["" for _ in range(colunas)] for _ in range(linhas)])


# ─────────────────────────────────────────
#  NUMERAÇÃO
# ─────────────────────────────────────────

def numerar(blocos: list[Bloco], numero_elemento: int) -> list[str]:
    """Marcador de cada bloco, calculado a partir da posição.

    Mantém uma pilha de contadores, um por nível. Ao voltar a um nível
    mais raso, os contadores dos níveis abaixo são descartados — é isso
    que faz as alíneas recomeçarem em "a)" a cada parágrafo-pai.
    """
    marcadores: list[str] = []
    contadores: list[int] = []      # contador de cada nível
    estilos: list[str] = []         # estilo em vigor em cada nível

    for b in blocos:
        nivel = max(1, min(NIVEL_MAX, b.nivel))

        if b.estilo == SEM_MARCADOR or b.tipo == TABELA or b.exemplo:
            # Não consome contador: uma continuação de texto ou uma tabela
            # não deve empurrar a numeração do parágrafo seguinte.
            marcadores.append("")
            continue

        del contadores[nivel:]
        del estilos[nivel:]
        while len(contadores) < nivel:
            contadores.append(0)
            estilos.append(b.estilo)

        # Trocar de estilo no mesmo nível recomeça a contagem: passar de
        # "1.1" para "a)" não deve produzir "b)".
        if estilos[nivel - 1] != b.estilo:
            estilos[nivel - 1] = b.estilo
            contadores[nivel - 1] = 0
        contadores[nivel - 1] += 1

        atual = contadores[nivel - 1]
        if b.estilo == ALINEA:
            marcadores.append(f"{letra(atual)})")
        elif b.estilo == INCISO:
            marcadores.append(f"{romano(atual)} –")
        else:
            partes = [str(numero_elemento)]
            for i in range(nivel):
                partes.append(str(contadores[i]) if estilos[i] == NUMERO
                              else str(contadores[i]))
            marcadores.append(".".join(partes) + ".")

    return marcadores


# ─────────────────────────────────────────
#  RENDERIZAÇÃO
# ─────────────────────────────────────────

def _sanear(fragmento: str) -> str:
    """Tira do HTML do editor o que não deve ir para o documento."""
    if not fragmento:
        return ""
    corpo = re.search(r"<body[^>]*>(.*)</body>", fragmento, re.S | re.I)
    texto = corpo.group(1) if corpo else fragmento
    texto = re.sub(r"<!--.*?-->", "", texto, flags=re.S)
    texto = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", texto,
                   flags=re.S | re.I)
    texto = re.sub(r"\s+(class|id)=\"[^\"]*\"", "", texto, flags=re.I)
    texto = re.sub(r"-qt-[a-z-]+\s*:\s*[^;\"]*;?", "", texto, flags=re.I)
    texto = re.sub(r'\s+style="\s*"', "", texto)
    return texto


def _limpar(fragmento: str) -> str:
    """Conteúdo do fragmento sem a marcação de parágrafo — para células."""
    texto = re.sub(r"</?p[^>]*>", " ", _sanear(fragmento), flags=re.I)
    return " ".join(texto.split())


ALINHAMENTOS = ("left", "right", "center", "justify")


def _alinhamento(atributos: str) -> str:
    achado = re.search(r'align\s*=\s*"?([a-z]+)', atributos, re.I)
    if achado is None:
        achado = re.search(r"text-align\s*:\s*([a-z]+)", atributos, re.I)
    valor = achado.group(1).lower() if achado else ""
    return valor if valor in ALINHAMENTOS else "justify"


#: Peça que já vem pronta e é copiada como está — hoje, listas.
BLOCO_PRONTO = "pronto"
PARAGRAFO = "paragrafo"


def _fim_do_elemento(texto: str, tag: str, inicio: int) -> int:
    """Posição logo após o fechamento de `tag`, contando aninhamentos."""
    padrao = re.compile(rf"<(/?){tag}\b[^>]*>", re.I)
    profundidade = 0
    for m in padrao.finditer(texto, inicio):
        profundidade += -1 if m.group(1) else 1
        if profundidade == 0:
            return m.end()
    return len(texto)


def paragrafos(fragmento: str) -> list[tuple[str, str, str]]:
    """Peças do bloco, na ordem: (tipo, alinhamento, conteúdo).

    Os parágrafos vêm um a um, cada qual com o seu alinhamento, em vez de
    fundidos num só: uma imagem centralizada em linha própria tem de sair
    centralizada no documento, e não herdar o justificado do texto ao
    redor.

    Listas passam inteiras, sem serem desmontadas — se fossem tratadas
    como parágrafo, os itens sumiriam do documento sem aviso.
    """
    texto = _sanear(fragmento)
    saida: list[tuple[str, str, str]] = []
    posicao = 0
    padrao = re.compile(r"<(p|ul|ol)\b([^>]*)>", re.I)

    while True:
        m = padrao.search(texto, posicao)
        if m is None:
            break
        tag = m.group(1).lower()
        if tag in ("ul", "ol"):
            fim = _fim_do_elemento(texto, tag, m.start())
            trecho = texto[m.start():fim]
            if texto_visivel(trecho):
                saida.append((BLOCO_PRONTO, "", " ".join(trecho.split())))
            posicao = fim
            continue
        fechamento = re.compile(r"</p\s*>", re.I).search(texto, m.end())
        fim = fechamento.start() if fechamento else len(texto)
        conteudo = " ".join(texto[m.end():fim].split())
        if texto_visivel(conteudo) or "<img" in conteudo:
            saida.append((PARAGRAFO, _alinhamento(m.group(2)), conteudo))
        posicao = fechamento.end() if fechamento else len(texto)

    if not saida:
        # Conteúdo solto, sem marcação de parágrafo.
        conteudo = " ".join(texto.split())
        if texto_visivel(conteudo) or "<img" in conteudo:
            saida.append((PARAGRAFO, "justify", conteudo))
    return saida


def texto_visivel(fragmento: str) -> str:
    sem_bloco = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ",
                       fragmento or "", flags=re.S | re.I)
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", sem_bloco)).split())


def texto_escrito(blocos: list[Bloco]) -> str:
    """Texto que o encarregado escreveu de fato, sem os exemplos."""
    return " ".join(texto_visivel(b.html) for b in blocos
                    if b.tipo == TEXTO and not b.exemplo)


def render_blocos(blocos: list[Bloco], numero_elemento: int) -> str:
    """Corpo do elemento em HTML, com marcadores e recuos.

    O recuo sai por tabela de duas colunas, e não por `margin-left`: o
    motor de texto do Qt ignora margens em cm/pt e trata porcentagem como
    valor absoluto, mas respeita largura de coluna percentual — que é
    também o que o SEI preserva melhor.
    """
    marcadores = numerar(blocos, numero_elemento)
    saida: list[str] = []

    for b, marcador in zip(blocos, marcadores):
        if b.exemplo:
            continue
        recuo = (b.nivel - 1) * RECUO_POR_NIVEL
        corpo = (_render_tabela(b) if b.tipo == TABELA
                 else _render_paragrafo(b, marcador))
        if not corpo:
            continue
        if recuo <= 0:
            saida.append(corpo)
        else:
            saida.append(
                '<table width="100%" cellspacing="0" cellpadding="0" '
                'border="0"><tr>'
                f'<td width="{recuo}%"></td>'
                f'<td width="{100 - recuo}%">{corpo}</td>'
                "</tr></table>")
    # Um respiro entre um parágrafo e o seguinte, nunca depois do último.
    return espaco(ESPACO).join(saida)


def _render_paragrafo(b: Bloco, marcador: str) -> str:
    linhas = paragrafos(b.html)
    if not linhas:
        return ""
    rotulo = (f"<b>{_html.escape(marcador)}</b>&nbsp;&nbsp;"
              if marcador else "")
    saida = []
    for tipo, alinhamento, conteudo in linhas:
        if tipo == BLOCO_PRONTO:
            if rotulo and not saida:
                # O bloco começa por uma lista: o marcador ganha linha
                # própria, em vez de se perder dentro do primeiro item.
                saida.append(
                    f'<p align="left" style="margin:0;">{rotulo}</p>')
            saida.append(conteudo)
            continue
        saida.append(
            f'<p align="{alinhamento}" '
            f'style="text-align:{alinhamento}; margin:0;">'
            f"{rotulo if not saida else ''}{conteudo}</p>")
    return espaco(ESPACO).join(saida)


def _render_tabela(b: Bloco) -> str:
    if not b.celulas:
        return ""
    largura = f"{100 // max(1, b.colunas())}%"
    linhas = []
    for i, linha in enumerate(b.celulas):
        celulas = []
        for cel in linha:
            conteudo = _limpar(cel) or "&nbsp;"
            if i == 0 and b.cabecalho:
                celulas.append(
                    f'<td width="{largura}" style="background-color:#E8EAF0;">'
                    f'<p align="center" style="margin:0;"><b>{conteudo}</b></p>'
                    "</td>")
            else:
                celulas.append(
                    f'<td width="{largura}">'
                    f'<p align="justify" style="margin:0;">{conteudo}</p>'
                    "</td>")
        linhas.append("<tr>" + "".join(celulas) + "</tr>")
    return ('<table width="100%" cellspacing="0" cellpadding="4" border="1" '
            'style="border-collapse:collapse;">'
            + "".join(linhas) + "</table>")
