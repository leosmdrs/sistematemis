"""
Análise auditável de planilha.

Trabalhar uma planilha de auditoria no Excel resolve o problema prático
e destrói o problema jurídico: ao fim, existe um resultado e não existe
como demonstrar de onde ele veio. Filtro aplicado é filtro perdido. Quem
lê o relatório precisa acreditar em quem o escreveu.

O que esta ferramenta faz **não é registrar cliques**. Um registro de
ações é uma afirmação — diz que alguém fez algo, e continua dependendo
de confiança. Aqui a análise inteira é um **roteiro**: uma lista ordenada
de operações declaradas e determinísticas, que qualquer pessoa pode
re-executar sobre o arquivo original para chegar exatamente ao mesmo
resultado. A peça deixa de afirmar e passa a ser conferível.

Disso decorre a regra que sustenta tudo, e que precisa ser respeitada em
qualquer acréscimo futuro a este módulo:

    **não pode existir maneira de alterar dado que não seja uma
    operação declarada.**

Sem edição livre de célula, sem ajuste "só para arrumar". Marcar linhas
de interesse é uma operação registrada, não uma digitação. Uma ferramenta
que registra tudo mas deixa uma porta lateral aberta não registra nada, e
a peça que ela emite passa a mentir por omissão.

Três decisões de projeto, cada uma por um motivo medido:

**O resumo é dos dados, não do arquivo.** Gravar duas vezes o mesmo
conteúdo em `.xlsx` produz arquivos com resumos criptográficos
diferentes: o formato é um zip e carrega a hora da gravação dentro.
Conferir reprodutibilidade pelo resumo do arquivo, portanto, não
funciona — falharia sempre. O que se confere é `Tabela.resumo()`, um
resumo canônico do conteúdo, que independe do empacotamento e sobrevive
a re-exportar em outro formato.

**A comparação é livre de idioma.** Ordenação por caractere depende de
configuração regional; o mesmo roteiro em outra estação daria ordem
diferente e o resumo não bateria. Aqui a chave de ordenação é derivada
por regra fixa (ver `chave_ordem`), e não pelo Windows.

**O que não pôde ser comparado é contado, e não some.** Filtrar por
faixa numérica uma coluna que tem três células com texto faz essas três
desaparecerem silenciosamente no Excel. Aqui elas entram no registro do
passo como incomparáveis, porque uma linha que sumiu por não ser número
é exatamente o tipo de coisa que precisa aparecer na peça.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from html import escape as _escape
from pathlib import Path

from . import derivado_core as derivado

#: Como uma célula vazia é representada em todo o módulo. O leitor
#: devolve `None` ou texto vazio conforme o formato de origem; unificar
#: aqui evita que "vazio" signifique duas coisas em pontos diferentes.
VAZIO = ""

#: Formatos que o leitor abre. O csv entra porque sistema de auditoria
#: exporta em csv o tempo todo, e obrigar a passar pelo Excel antes
#: seria justamente reintroduzir a etapa não rastreável.
FORMATOS = (".xlsx", ".xlsm", ".xlsb", ".xls", ".ods", ".csv", ".txt")


# ─────────────────────────────────────────
#  VALORES
# ─────────────────────────────────────────

def texto(v) -> str:
    """A forma escrita de uma célula — para exibir, comparar e resumir.

    Precisa ser uma função só, usada nos três lugares. Se a tela
    mostrasse uma coisa e o resumo criptográfico consumisse outra, o
    operador estaria conferindo o que não foi resumido.
    """
    if v is None or v == VAZIO:
        return ""
    if isinstance(v, bool):
        return "VERDADEIRO" if v else "FALSO"
    if isinstance(v, datetime.datetime):
        if (v.hour, v.minute, v.second) == (0, 0, 0):
            return v.strftime("%d/%m/%Y")
        return v.strftime("%d/%m/%Y %H:%M:%S")
    if isinstance(v, datetime.date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, datetime.time):
        return v.strftime("%H:%M:%S")
    if isinstance(v, float):
        # O leitor devolve todo número como decimal. Mostrar a matrícula
        # 1234567 como "1234567.0" seria trocar o dado por outro aos
        # olhos de quem confere.
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return repr(v)
    return str(v).strip()


_DATA = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})$")


def como_data(v):
    """A data por trás da célula, ou None se não houver uma.

    Aceita a data já tipada e também a escrita como texto, porque
    exportação de sistema entrega das duas formas — às vezes na mesma
    coluna.
    """
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    m = _DATA.match(texto(v))
    if not m:
        return None
    d, mes, a = (int(x) for x in m.groups())
    if a < 100:
        a += 2000 if a < 70 else 1900
    try:
        return datetime.date(a, mes, d)
    except ValueError:
        return None


def como_numero(v):
    """O número por trás da célula, ou None.

    Entende o decimal com vírgula e o milhar com ponto, que é como o
    número chega quando a exportação veio formatada em português.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = texto(v)
    if not s:
        return None
    s = re.sub(r"[R$\s ]", "", s)
    if "," in s:                       # 1.234,56 -> 1234.56
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def sem_acento(s: str) -> str:
    """Texto reduzido para comparar: sem acento, sem caixa, sem sobra.

    É o que faz "José" e "JOSE" encontrarem um ao outro num filtro. A
    escolha é declarada na peça, porque muda o resultado e não pode ser
    silenciosa.
    """
    s = unicodedata.normalize("NFKD", s.casefold())
    return "".join(c for c in s if not unicodedata.combining(c)).strip()


def chave_ordem(v):
    """Chave de ordenação estável e independente da estação.

    Ordenar por caractere depende da configuração regional do Windows: o
    mesmo roteiro rodado em outra máquina poderia devolver outra ordem, e
    aí o resumo dos dados não bateria — a reprodutibilidade cairia por um
    motivo que nada tem a ver com a análise. Por isso a regra é fixa
    aqui: número antes de texto, texto antes de vazio.
    """
    s = texto(v)
    if not s:
        return (2, 0.0, "")
    d = como_data(v)
    if d is not None:
        return (0, float(d.toordinal()), "")
    n = como_numero(v)
    if n is not None:
        return (0, n, "")
    return (1, 0.0, sem_acento(s))


# ─────────────────────────────────────────
#  A TABELA
# ─────────────────────────────────────────

@dataclass
class Tabela:
    """Colunas nomeadas e linhas, imutáveis por convenção.

    Nenhuma operação altera a tabela que recebe: todas devolvem uma
    tabela nova. É o que permite re-executar o roteiro do zero e obter o
    mesmo fim — e o que impede que um passo estrague a origem do passo
    anterior.
    """

    colunas: list[str] = field(default_factory=list)
    linhas: list[tuple] = field(default_factory=list)

    @property
    def n_linhas(self) -> int:
        return len(self.linhas)

    @property
    def n_colunas(self) -> int:
        return len(self.colunas)

    def indice(self, coluna: str) -> int:
        """Posição da coluna pelo nome. -1 se ela não existe.

        Devolver -1 em vez de estourar é proposital: um roteiro salvo
        pode ser re-executado sobre um arquivo cuja coluna foi renomeada,
        e a falha precisa virar uma linha na peça, não uma queda.
        """
        try:
            return self.colunas.index(coluna)
        except ValueError:
            return -1

    def coluna(self, nome: str) -> list:
        i = self.indice(nome)
        return [] if i < 0 else [l[i] for l in self.linhas]

    def resumo(self) -> str:
        """Resumo criptográfico do **conteúdo**, não do arquivo.

        Ver a explicação no cabeçalho do módulo: o resumo do arquivo
        `.xlsx` muda a cada gravação porque o formato guarda a hora
        dentro. Este aqui depende só dos nomes das colunas e do texto das
        células, na ordem em que estão — que é exatamente o que a análise
        produziu.

        Os separadores são caracteres de controle (0x1F entre células,
        0x1E entre linhas) para que nenhum conteúdo de célula consiga
        imitá-los e fazer duas tabelas diferentes resumirem igual.
        """
        h = hashlib.sha256()
        h.update("\x1f".join(self.colunas).encode("utf-8"))
        h.update(b"\x1e")
        for linha in self.linhas:
            h.update("\x1f".join(texto(c) for c in linha).encode("utf-8"))
            h.update(b"\x1e")
        return h.hexdigest()


# ─────────────────────────────────────────
#  LEITURA
# ─────────────────────────────────────────

def abas(caminho) -> list[str]:
    """Nomes das abas. Uma só, chamada "csv", quando for texto puro."""
    if Path(caminho).suffix.lower() in (".csv", ".txt"):
        return ["csv"]
    from python_calamine import CalamineWorkbook
    return list(CalamineWorkbook.from_path(str(caminho)).sheet_names)


def formulas_sem_valor(caminho) -> int:
    """Quantas fórmulas estão sem o resultado guardado no arquivo.

    Armadilha silenciosa e comum: planilha gerada por sistema, que nunca
    foi aberta no Excel, guarda a fórmula mas não guarda o valor que ela
    calcularia. A coluna chega vazia. Quem filtra sobre ela conclui
    errado sem nunca perceber, e a peça sairia atestando uma análise
    feita sobre nada.

    O arquivo é varrido em blocos porque a planilha pode ter dezenas de
    megabytes de XML, e carregar tudo em memória para contar fórmula
    seria caro à toa.
    """
    if Path(caminho).suffix.lower() not in (".xlsx", ".xlsm"):
        return 0
    total = com_valor = 0
    try:
        with zipfile.ZipFile(caminho) as z:
            folhas = [n for n in z.namelist()
                      if n.startswith("xl/worksheets/") and n.endswith(".xml")]
            for nome in folhas:
                with z.open(nome) as f:
                    while bloco := f.read(1 << 20):
                        total += len(re.findall(rb"<f[ >/]", bloco))
                        com_valor += len(re.findall(rb"<v>[^<]", bloco))
    except (OSError, zipfile.BadZipFile, KeyError):
        return 0
    return max(0, total - com_valor)


def _cabecalho(bruto: list[list], linha: int) -> tuple[list[str], list[list]]:
    """Separa o cabeçalho do corpo, dando nome a coluna sem nome.

    Coluna sem título não pode ficar sem nome: o roteiro identifica
    coluna pelo nome, e um nome vazio tornaria o passo impossível de
    escrever e de reproduzir. Título repetido é desfeito pelo mesmo
    motivo.
    """
    if not bruto:
        return [], []
    i = max(0, min(linha - 1, len(bruto) - 1))
    nomes, vistos = [], {}
    for pos, celula in enumerate(bruto[i], 1):
        nome = texto(celula) or f"Coluna {pos}"
        if nome in vistos:
            vistos[nome] += 1
            nome = f"{nome} ({vistos[nome]})"
        else:
            vistos[nome] = 1
        nomes.append(nome)
    return nomes, bruto[i + 1:]


def _ler_csv(caminho) -> list[list]:
    """Lê csv adivinhando codificação e separador, nesta ordem.

    Exportação de sistema no Brasil sai quase sempre em ponto-e-vírgula e
    em Windows-1252; ler como vírgula e UTF-8 devolveria uma coluna só,
    ou texto corrompido, e a análise partiria de dado errado.
    """
    dados = Path(caminho).read_bytes()
    for cod in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            conteudo = dados.decode(cod)
            break
        except UnicodeDecodeError:
            continue
    else:
        conteudo = dados.decode("latin-1", "replace")
    amostra = conteudo[:8192]
    sep = max(";,\t|", key=amostra.count)
    return [list(l) for l in csv.reader(conteudo.splitlines(), delimiter=sep)]


def carregar(caminho, aba: str = "", linha_cabecalho: int = 1) -> Tabela:
    """Lê a planilha como ela está, sem converter nada por conta própria.

    O leitor devolve o valor guardado no arquivo. Texto continua texto —
    é o que preserva o CPF "01234567890" com o zero à frente, que é o
    estrago clássico de quem abre o arquivo no Excel e salva de volta.
    """
    caminho = str(caminho)
    if Path(caminho).suffix.lower() in (".csv", ".txt"):
        bruto = _ler_csv(caminho)
    else:
        from python_calamine import CalamineWorkbook
        livro = CalamineWorkbook.from_path(caminho)
        folha = (livro.get_sheet_by_name(aba) if aba
                 else livro.get_sheet_by_index(0))
        bruto = folha.to_python()
    nomes, corpo = _cabecalho(bruto, linha_cabecalho)
    largura = len(nomes)
    # Linha mais curta que o cabeçalho é comum em exportação; completar
    # com vazio mantém toda linha com a mesma largura, sem o que qualquer
    # operação por índice de coluna quebraria no meio do caminho.
    linhas = [tuple(l[:largura]) + (VAZIO,) * (largura - len(l))
              for l in corpo]
    # Rodapé em branco é lixo de exportação, não dado.
    while linhas and not any(texto(c) for c in linhas[-1]):
        linhas.pop()
    return Tabela(colunas=nomes, linhas=linhas)


# ─────────────────────────────────────────
#  OPERAÇÕES
# ─────────────────────────────────────────
#
#  Cada operação sabe três coisas: como se aplicar a uma tabela, como se
#  escrever em português para a peça, e como se guardar e voltar do
#  roteiro salvo. As três precisam andar juntas — uma operação que se
#  aplica mas não sabe se descrever produz um resultado que a peça não
#  consegue explicar, e é exatamente isso que se está tentando evitar.

@dataclass
class Passo:
    """O que uma operação fez, medido.

    O par antes/depois é o que dá para conferir de olho na peça, e é a
    informação que ninguém consegue apresentar depois de ter trabalhado
    no Excel: quantas linhas entraram no filtro e quantas saíram.
    """

    descricao: str = ""
    antes: int = 0
    depois: int = 0
    #: Linhas que a comparação não alcançou — célula com texto onde se
    #: pediu número, data ilegível. No Excel elas somem sem aviso; aqui
    #: são contadas e vão impressas.
    incomparaveis: int = 0
    #: Falha que não impede a análise de seguir, mas que precisa aparecer
    #: na peça (coluna que sumiu, por exemplo).
    aviso: str = ""
    #: Como a peça diz o que aconteceu com as incomparáveis. O padrão
    #: serve ao filtro, onde a linha some do resultado. A coluna derivada
    #: e o agrupamento trocam esta frase, porque ali a linha permanece e
    #: só o valor calculado fica vazio — dizer que "ficaram de fora"
    #: seria a peça afirmando uma perda que não houve.
    destino_incomparaveis: str = "ficaram de fora"


class Operacao:
    """Contrato de uma operação do roteiro."""

    tipo: str = ""

    def aplicar(self, t: Tabela) -> tuple[Tabela, Passo]:
        raise NotImplementedError

    def descrever(self) -> str:
        raise NotImplementedError

    def dados(self) -> dict:
        raise NotImplementedError

    @classmethod
    def de_dados(cls, d: dict) -> "Operacao":
        raise NotImplementedError

    def _falta(self, t: Tabela, *colunas: str):
        """Passo de aviso quando alguma coluna não existe mais.

        Acontece ao re-executar um roteiro sobre outra versão do arquivo.
        A análise segue, sem alterar a tabela, e a peça registra o que
        não pôde ser feito — mais útil do que interromper tudo.
        """
        faltando = [c for c in colunas if t.indice(c) < 0]
        if not faltando:
            return None
        quais = ", ".join('"' + c + '"' for c in faltando)
        return Passo(descricao=self.descrever(), antes=t.n_linhas,
                     depois=t.n_linhas,
                     aviso="não executado: coluna " + quais + " não existe")


# ── filtro ───────────────────────────────

#: Condição -> (como se escreve na peça, quantos valores consome).
#: A ordem é a que aparece na tela, das mais usadas para as menos.
CONDICOES: dict[str, tuple[str, int]] = {
    "igual":       ("igual a", 1),
    "diferente":   ("diferente de", 1),
    "contem":      ("contém", 1),
    "nao_contem":  ("não contém", 1),
    "comeca":      ("começa com", 1),
    "termina":     ("termina com", 1),
    "na_lista":    ("está entre os valores", 1),
    "vazio":       ("está vazia", 0),
    "preenchido":  ("está preenchida", 0),
    "maior":       ("maior que", 1),
    "maior_igual": ("maior ou igual a", 1),
    "menor":       ("menor que", 1),
    "menor_igual": ("menor ou igual a", 1),
    "entre":       ("entre", 2),
}

#: Condições que comparam grandeza, e não texto. São as que produzem
#: incomparáveis, e por isso precisam ser distinguidas.
ORDINAIS = ("maior", "maior_igual", "menor", "menor_igual", "entre")

#: Separadores de uma lista colada pelo operador — de outra planilha, de
#: um ofício, de uma decisão judicial.
SEPARA_LISTA = re.compile(r"[\r\n;]+")


def _grandeza(v):
    """O valor comparável por grandeza — data vira número de dias."""
    d = como_data(v)
    return float(d.toordinal()) if d is not None else como_numero(v)


def avaliar(condicao: str, celula, valor: str = "", valor2: str = "",
            sensivel: bool = False):
    """A condição aplicada a uma célula: True, False, ou None.

    None é o terceiro resultado, e o que não pode ser perdido: significa
    que a comparação não pôde ser feita — texto onde se pediu número,
    data ilegível. Quem chama decide o destino da linha, mas ninguém
    pode confundir "não atende" com "não deu para saber".

    Vive aqui fora, e não dentro do Filtro, porque a Marcação de linhas
    usa exatamente as mesmas catorze condições. Duas implementações da
    palavra "contém" divergiriam com o tempo, e aí a peça descreveria
    uma coisa enquanto a ferramenta fazia outra.
    """
    c = condicao
    if c == "vazio":
        return not texto(celula)
    if c == "preenchido":
        return bool(texto(celula))

    if c in ORDINAIS:
        a = _grandeza(celula)
        b = _grandeza(valor)
        if a is None or b is None:
            return None
        if c == "maior":
            return a > b
        if c == "maior_igual":
            return a >= b
        if c == "menor":
            return a < b
        if c == "menor_igual":
            return a <= b
        b2 = _grandeza(valor2)
        if b2 is None:
            return None
        baixo, alto = min(b, b2), max(b, b2)
        return baixo <= a <= alto

    arruma = (str.strip) if sensivel else sem_acento
    x = arruma(texto(celula))
    ref = arruma(valor)
    if c == "igual":
        return x == ref
    if c == "diferente":
        return x != ref
    if c == "contem":
        return ref in x
    if c == "nao_contem":
        return ref not in x
    if c == "comeca":
        return x.startswith(ref)
    if c == "termina":
        return x.endswith(ref)
    if c == "na_lista":
        lista = {arruma(v) for v in SEPARA_LISTA.split(valor) if v.strip()}
        return x in lista
    return False


def frase_condicao(coluna: str, condicao: str, valor: str = "",
                   valor2: str = "", sensivel: bool = False) -> str:
    """Como a condição se lê na peça. Uma redação só, para os dois usos."""
    rotulo, quantos = CONDICOES.get(condicao, (condicao, 1))
    frase = '"' + coluna + '" ' + rotulo
    if quantos == 1:
        valores = [v for v in SEPARA_LISTA.split(valor) if v.strip()]
        if condicao == "na_lista" and len(valores) > 6:
            frase += " (" + str(len(valores)) + " valores relacionados)"
        else:
            frase += ' "' + valor + '"'
    elif quantos == 2:
        frase += ' "' + valor + '" e "' + valor2 + '"'
    if quantos and condicao not in ORDINAIS:
        frase += (", distinguindo maiúsculas e acentos" if sensivel
                  else ", sem distinguir maiúsculas nem acentos")
    return frase


@dataclass
class Filtro(Operacao):
    """Mantém (ou descarta) as linhas que atendem a uma condição."""

    coluna: str = ""
    condicao: str = "igual"
    valor: str = ""
    valor2: str = ""
    #: Distinguir maiúscula e acento. Falso por padrão, porque é o que
    #: serve ao trabalho — mas vai declarado na peça, já que muda o
    #: resultado, e escolha silenciosa aqui seria inaceitável.
    sensivel: bool = False
    #: Falso inverte o filtro: descarta o que casa, em vez de manter.
    manter: bool = True

    tipo = "filtro"

    def _casa(self, celula):
        return avaliar(self.condicao, celula, self.valor, self.valor2,
                       self.sensivel)

    def aplicar(self, t: Tabela) -> tuple[Tabela, Passo]:
        p = self._falta(t, self.coluna)
        if p is not None:
            return t, p
        i = t.indice(self.coluna)
        guardadas, incomparaveis = [], 0
        for linha in t.linhas:
            r = self._casa(linha[i])
            if r is None:
                incomparaveis += 1
                continue
            if r == self.manter:
                guardadas.append(linha)
        return (Tabela(colunas=list(t.colunas), linhas=guardadas),
                Passo(descricao=self.descrever(), antes=t.n_linhas,
                      depois=len(guardadas), incomparaveis=incomparaveis))

    def descrever(self) -> str:
        verbo = "Mantidas" if self.manter else "Descartadas"
        return (verbo + " as linhas em que "
                + frase_condicao(self.coluna, self.condicao, self.valor,
                                 self.valor2, self.sensivel))

    def dados(self) -> dict:
        return {"tipo": self.tipo, "coluna": self.coluna,
                "condicao": self.condicao, "valor": self.valor,
                "valor2": self.valor2, "sensivel": self.sensivel,
                "manter": self.manter}

    @classmethod
    def de_dados(cls, d: dict) -> "Filtro":
        return cls(coluna=d.get("coluna", ""),
                   condicao=d.get("condicao", "igual"),
                   valor=d.get("valor", ""), valor2=d.get("valor2", ""),
                   sensivel=bool(d.get("sensivel", False)),
                   manter=bool(d.get("manter", True)))


# ── ordenação ────────────────────────────

@dataclass
class Ordenacao(Operacao):
    """Ordena por uma ou mais colunas.

    A ordenação do Python é estável, e a chave vem de `chave_ordem`, que
    não consulta a configuração regional. As duas coisas juntas é que
    fazem a mesma ordenação sair igual em qualquer estação — sem isso, o
    resumo dos dados não se reproduziria.
    """

    chaves: list = field(default_factory=list)   # [(coluna, decrescente)]

    tipo = "ordenacao"

    def aplicar(self, t: Tabela) -> tuple[Tabela, Passo]:
        p = self._falta(t, *[c for c, _ in self.chaves])
        if p is not None:
            return t, p
        linhas = list(t.linhas)
        # De trás para a frente: como a ordenação é estável, ordenar pela
        # última chave primeiro e pela primeira por último deixa a
        # primeira predominando, que é o que se espera.
        for coluna, desc in reversed(self.chaves):
            i = t.indice(coluna)
            linhas.sort(key=lambda l, i=i: chave_ordem(l[i]), reverse=desc)
        return (Tabela(colunas=list(t.colunas), linhas=linhas),
                Passo(descricao=self.descrever(), antes=t.n_linhas,
                      depois=len(linhas)))

    def descrever(self) -> str:
        partes = ['"' + c + '" (' +
                  ("maior para menor" if d else "menor para maior") + ")"
                  for c, d in self.chaves]
        return "Ordenadas as linhas por " + ", depois por ".join(partes)

    def dados(self) -> dict:
        return {"tipo": self.tipo,
                "chaves": [[c, bool(d)] for c, d in self.chaves]}

    @classmethod
    def de_dados(cls, d: dict) -> "Ordenacao":
        return cls(chaves=[(c, bool(x)) for c, x in d.get("chaves", [])])


# ── colunas ──────────────────────────────

@dataclass
class Colunas(Operacao):
    """Escolhe e reordena as colunas que seguem adiante.

    Descartar coluna é operação com efeito jurídico — some dado do
    resultado —, então é passo declarado como qualquer outro, e a peça
    diz quantas e quais ficaram.
    """

    manter: list = field(default_factory=list)

    tipo = "colunas"

    def aplicar(self, t: Tabela) -> tuple[Tabela, Passo]:
        existentes = [c for c in self.manter if t.indice(c) >= 0]
        sumidas = [c for c in self.manter if t.indice(c) < 0]
        indices = [t.indice(c) for c in existentes]
        linhas = [tuple(l[i] for i in indices) for l in t.linhas]
        aviso = ("colunas ausentes no arquivo: "
                 + ", ".join('"' + c + '"' for c in sumidas)) if sumidas else ""
        return (Tabela(colunas=existentes, linhas=linhas),
                Passo(descricao=self.descrever(), antes=t.n_linhas,
                      depois=len(linhas), aviso=aviso))

    def descrever(self) -> str:
        quais = ", ".join('"' + c + '"' for c in self.manter)
        if len(self.manter) <= 8:
            return "Mantidas as colunas " + quais
        return ("Mantidas " + str(len(self.manter))
                + " colunas, a saber: " + quais)

    def dados(self) -> dict:
        return {"tipo": self.tipo, "manter": list(self.manter)}

    @classmethod
    def de_dados(cls, d: dict) -> "Colunas":
        return cls(manter=list(d.get("manter", [])))


# ── duplicidades ─────────────────────────

@dataclass
class Duplicidades(Operacao):
    """Remove linhas repetidas segundo as colunas-chave escolhidas."""

    chaves: list = field(default_factory=list)
    #: Qual das repetidas fica. Precisa ser escolha explícita: manter a
    #: primeira ou a última muda o dado que sobra, e numa planilha
    #: ordenada por data isso é a diferença entre o primeiro e o último
    #: registro de cada pessoa.
    manter: str = "primeira"

    tipo = "duplicidades"

    def aplicar(self, t: Tabela) -> tuple[Tabela, Passo]:
        alvo = self.chaves or list(t.colunas)
        p = self._falta(t, *alvo)
        if p is not None:
            return t, p
        indices = [t.indice(c) for c in alvo]
        vistos: dict = {}
        guardadas: list = []
        for linha in t.linhas:
            chave = tuple(sem_acento(texto(linha[i])) for i in indices)
            if chave in vistos:
                if self.manter == "ultima":
                    guardadas[vistos[chave]] = linha
                continue
            vistos[chave] = len(guardadas)
            guardadas.append(linha)
        return (Tabela(colunas=list(t.colunas), linhas=guardadas),
                Passo(descricao=self.descrever(), antes=t.n_linhas,
                      depois=len(guardadas)))

    def descrever(self) -> str:
        onde = (", ".join('"' + c + '"' for c in self.chaves) if self.chaves
                else "todas as colunas")
        qual = "a primeira" if self.manter == "primeira" else "a última"
        return ("Removidas as duplicidades por " + onde
                + ", mantida " + qual + " ocorrência de cada")

    def dados(self) -> dict:
        return {"tipo": self.tipo, "chaves": list(self.chaves),
                "manter": self.manter}

    @classmethod
    def de_dados(cls, d: dict) -> "Duplicidades":
        return cls(chaves=list(d.get("chaves", [])),
                   manter=d.get("manter", "primeira"))


# ── coluna derivada ──────────────────────

#: Cálculo -> (como se escreve na peça, quantas colunas de origem
#: consome; 0 é lista sem limite).
CALCULOS: dict[str, tuple[str, int]] = {
    "juntar":  ("juntar textos", 0),
    "extrair": ("extrair parte do texto", 1),
    "dias":    ("contar dias entre datas", 2),
}


def _nome_livre(usados: list, base: str) -> str:
    """Um nome de coluna que ainda não está na lista.

    Duas colunas com o mesmo nome quebrariam `Tabela.indice`, que devolve
    sempre a primeira: o passo seguinte leria a coluna errada sem que
    nada avisasse.
    """
    if base not in usados:
        return base
    n = 2
    while base + " (" + str(n) + ")" in usados:
        n += 1
    return base + " (" + str(n) + ")"


@dataclass
class Derivada(Operacao):
    """Acrescenta uma coluna calculada a partir das que já existem.

    Coluna derivada é dado novo dentro da análise, e por isso é operação
    declarada como qualquer outra — quem lê a peça precisa poder refazer
    a conta. Nenhum dos três cálculos consulta coisa alguma fora da
    própria linha, e é isso que os torna reproduzíveis em outra estação.

    A operação **não sobrescreve coluna existente**. Se o nome escolhido
    já estiver em uso, ela não executa e a peça registra o motivo:
    substituir uma coluna apagaria dado, e apagar dado sem que o termo
    diga é exatamente a porta lateral que este módulo não pode ter.
    """

    nome: str = ""
    calculo: str = "juntar"
    origens: list = field(default_factory=list)
    #: Só o "juntar" usa: o que vai entre um pedaço e outro.
    separador: str = " "
    #: Só o "extrair" usa: posição do primeiro caractere, contando de 1,
    #: e quantos levar — zero leva até o fim.
    inicio: int = 1
    tamanho: int = 0

    tipo = "derivada"

    def _calcular(self, valores: list) -> tuple:
        """O valor da célula nova, e se foi possível calculá-lo."""
        if self.calculo == "juntar":
            partes = [texto(v) for v in valores]
            return self.separador.join(p for p in partes if p), True
        if self.calculo == "extrair":
            s = texto(valores[0]) if valores else ""
            ini = max(1, int(self.inicio))
            fim = (ini - 1 + int(self.tamanho)) if self.tamanho > 0 else len(s)
            return s[ini - 1:fim], True
        if self.calculo == "dias":
            if len(valores) < 2:
                return VAZIO, False
            d1, d2 = como_data(valores[0]), como_data(valores[1])
            if d1 is None or d2 is None:
                return VAZIO, False
            return (d2 - d1).days, True
        return VAZIO, False

    def _parado(self, t: Tabela, motivo: str) -> Passo:
        return Passo(descricao=self.descrever(), antes=t.n_linhas,
                     depois=t.n_linhas, aviso="não executado: " + motivo)

    def aplicar(self, t: Tabela) -> tuple[Tabela, Passo]:
        nome = self.nome.strip()
        if not nome:
            return t, self._parado(t, "a coluna nova não recebeu nome")
        if t.indice(nome) >= 0:
            return t, self._parado(
                t, 'já existe uma coluna chamada "' + nome
                + '", e substituí-la apagaria dado')
        p = self._falta(t, *self.origens)
        if p is not None:
            return t, p
        indices = [t.indice(c) for c in self.origens]
        linhas, incomparaveis = [], 0
        for linha in t.linhas:
            valor, deu = self._calcular([linha[i] for i in indices])
            if not deu:
                incomparaveis += 1
            linhas.append(tuple(linha) + (valor,))
        return (Tabela(colunas=list(t.colunas) + [nome], linhas=linhas),
                Passo(descricao=self.descrever(), antes=t.n_linhas,
                      depois=len(linhas), incomparaveis=incomparaveis,
                      destino_incomparaveis="ficaram com a coluna nova vazia"))

    def descrever(self) -> str:
        quais = ", ".join('"' + c + '"' for c in self.origens)
        frase = 'Acrescentada a coluna "' + self.nome.strip() + '", '
        if self.calculo == "juntar":
            return (frase + "juntando o texto de " + quais + ' separado por "'
                    + self.separador + '" (os vazios não entram)')
        if self.calculo == "extrair":
            quanto = ("até o fim" if self.tamanho <= 0
                      else str(self.tamanho) + " caractere(s)")
            return (frase + "extraindo de " + quais + " " + quanto
                    + ", a partir do caractere " + str(max(1, self.inicio)))
        if self.calculo == "dias":
            de, ate = (list(self.origens) + ["", ""])[:2]
            return (frase + 'com os dias corridos de "' + de + '" até "'
                    + ate + '"')
        return frase + "por cálculo desconhecido"

    def dados(self) -> dict:
        return {"tipo": self.tipo, "nome": self.nome,
                "calculo": self.calculo, "origens": list(self.origens),
                "separador": self.separador, "inicio": int(self.inicio),
                "tamanho": int(self.tamanho)}

    @classmethod
    def de_dados(cls, d: dict) -> "Derivada":
        return cls(nome=d.get("nome", ""), calculo=d.get("calculo", "juntar"),
                   origens=list(d.get("origens", [])),
                   separador=d.get("separador", " "),
                   inicio=int(d.get("inicio", 1)),
                   tamanho=int(d.get("tamanho", 0)))


# ── agrupamento ──────────────────────────

#: Resumo -> (como a coluna se chama no resultado, se precisa de coluna).
RESUMOS: dict[str, tuple[str, bool]] = {
    "contar": ("Quantidade", False),
    "somar":  ("Soma", True),
    "media":  ("Média", True),
    "maximo": ("Maior", True),
    "minimo": ("Menor", True),
}


@dataclass
class Agrupamento(Operacao):
    """Reduz a tabela a um quadro-resumo: uma linha por grupo.

    É a tabela dinâmica, e costuma ser o que vai impresso na peça — o
    quadro por unidade, por ano, por servidor.

    Duas escolhas ficam declaradas porque mudam o resultado:

    **Os grupos se formam pelo texto exato da célula.** "São Paulo" e
    "SAO PAULO" ficam em grupos separados. Juntá-los por conta própria
    seria a ferramenta decidindo que duas grafias são a mesma coisa —
    juízo que é de quem analisa, e que tem lugar próprio: um filtro ou
    uma coluna derivada, declarados antes deste passo.

    **A ordem dos grupos é a da primeira aparição**, e não alfabética.
    Assim uma ordenação feita antes continua valendo, e o resultado não
    depende de configuração regional nenhuma.

    A média sai como o cálculo a produziu, sem arredondamento — cem
    dividido por três aparece com todas as casas. Arredondar seria
    alterar valor fora de operação declarada, que é o que este módulo
    não faz; quem quiser a casa decimal certa acrescenta, adiante, uma
    coluna derivada que a produza e diga que produziu.
    """

    chaves: list = field(default_factory=list)
    #: [(resumo, coluna)] — a coluna fica vazia quando o resumo é contar.
    resumos: list = field(default_factory=list)

    tipo = "agrupamento"

    def _titulo(self, resumo: str, coluna: str) -> str:
        rotulo, usa_coluna = RESUMOS.get(resumo, (resumo, True))
        return rotulo + " de " + coluna if usa_coluna else rotulo

    def aplicar(self, t: Tabela) -> tuple[Tabela, Passo]:
        precisa = list(self.chaves) + [c for r, c in self.resumos
                                       if RESUMOS.get(r, ("", True))[1]]
        p = self._falta(t, *precisa)
        if p is not None:
            return t, p
        if not self.chaves:
            return t, Passo(descricao=self.descrever(), antes=t.n_linhas,
                            depois=t.n_linhas,
                            aviso="não executado: nenhuma coluna de grupo")

        ik = [t.indice(c) for c in self.chaves]
        # dict comum: em Python a ordem de inserção é preservada, e é ela
        # que dá a ordem de primeira aparição prometida na docstring.
        grupos: dict = {}
        for linha in t.linhas:
            chave = tuple(texto(linha[i]) for i in ik)
            grupos.setdefault(chave, []).append(linha)

        colunas = list(self.chaves)
        titulos = []
        for resumo, coluna in self.resumos:
            titulo = _nome_livre(colunas + titulos,
                                 self._titulo(resumo, coluna))
            titulos.append(titulo)
        colunas += titulos

        linhas, incomparaveis = [], 0
        for chave, membros in grupos.items():
            saida = list(chave)
            perdeu = False
            for resumo, coluna in self.resumos:
                # "Contar" não olha coluna nenhuma: conta as linhas do
                # grupo. Buscar a coluna vazia devolveria -1 e a conta
                # sairia zero em todo grupo — quadro-resumo de auditoria
                # com a quantidade zerada é peça que informa o contrário
                # do que aconteceu.
                if not RESUMOS.get(resumo, ("", True))[1]:
                    celulas = list(membros)
                else:
                    i = t.indice(coluna)
                    celulas = [m[i] for m in membros] if i >= 0 else []
                valor, faltou = self._resumir(resumo, celulas)
                perdeu = perdeu or faltou
                saida.append(valor)
            if perdeu:
                incomparaveis += 1
            linhas.append(tuple(saida))
        return (Tabela(colunas=colunas, linhas=linhas),
                Passo(descricao=self.descrever(), antes=t.n_linhas,
                      depois=len(linhas), incomparaveis=incomparaveis,
                      destino_incomparaveis=(
                          "tinham célula que não é número, "
                          "e ela não entrou na conta do grupo")))

    @staticmethod
    def _resumir(resumo: str, celulas: list) -> tuple:
        """O valor do resumo, e se alguma célula ficou de fora da conta."""
        if resumo == "contar":
            return len(celulas), False
        if resumo in ("maximo", "minimo"):
            # Por `chave_ordem`, e não por número: assim o maior e o menor
            # servem também a data e a texto, com a mesma regra de ordem
            # que a Ordenação usa — e o valor devolvido é o original, do
            # jeito que estava na planilha.
            cheias = [c for c in celulas if texto(c)]
            if not cheias:
                return VAZIO, False
            escolha = (max if resumo == "maximo" else min)
            return escolha(cheias, key=chave_ordem), False
        numeros = [como_numero(c) for c in celulas]
        validos = [n for n in numeros if n is not None]
        faltou = len(validos) != len([c for c in celulas if texto(c)])
        if not validos:
            return VAZIO, faltou
        total = sum(validos)
        if resumo == "somar":
            return total, faltou
        if resumo == "media":
            return total / len(validos), faltou
        return VAZIO, faltou

    def descrever(self) -> str:
        por = ", ".join('"' + c + '"' for c in self.chaves)
        quais = ", ".join(self._titulo(r, c) for r, c in self.resumos)
        frase = "Agrupadas as linhas por " + por
        if quais:
            frase += ", resumindo em " + quais
        return (frase + ". Os grupos se formam pelo texto exato da célula, "
                "e saem na ordem em que apareceram")

    def dados(self) -> dict:
        return {"tipo": self.tipo, "chaves": list(self.chaves),
                "resumos": [[r, c] for r, c in self.resumos]}

    @classmethod
    def de_dados(cls, d: dict) -> "Agrupamento":
        return cls(chaves=list(d.get("chaves", [])),
                   resumos=[(r, c) for r, c in d.get("resumos", [])])


# ── marcação ─────────────────────────────

@dataclass
class Marcacao(Operacao):
    """Marca as linhas que atendem a uma condição, com justificativa.

    É a operação que ocupa o lugar de pintar a célula de amarelo no
    Excel, e a diferença não é de estética. A marca aqui nasce de uma
    regra declarada: a condição que a produziu está escrita na peça, a
    razão de tê-la aplicado está junto, e qualquer pessoa re-executa o
    roteiro e obtém exatamente as mesmas linhas marcadas. Célula pintada
    não se re-executa, não se justifica e não se confere.

    A marca **se acumula, nunca substitui**. Marcando duas vezes na mesma
    coluna, a linha que atende às duas condições carrega as duas marcas,
    lado a lado. Sobrescrever apagaria o resultado do passo anterior sem
    que o termo dissesse — e o termo continuaria relacionando os dois
    passos, afirmando o que já não estaria lá.
    """

    coluna_marca: str = "Marcação"
    marca: str = "SIM"
    #: Por que estas linhas foram marcadas. Vai na peça junto do passo;
    #: é a diferença entre um destaque e uma decisão fundamentada.
    justificativa: str = ""
    coluna: str = ""
    condicao: str = "igual"
    valor: str = ""
    valor2: str = ""
    sensivel: bool = False

    tipo = "marcacao"

    #: Entre uma marca e a seguinte, na mesma célula.
    JUNTA = "; "

    def aplicar(self, t: Tabela) -> tuple[Tabela, Passo]:
        destino = self.coluna_marca.strip() or "Marcação"
        marca = self.marca.strip()
        if not marca:
            return t, Passo(descricao=self.descrever(), antes=t.n_linhas,
                            depois=t.n_linhas,
                            aviso="não executado: a marca está em branco")
        p = self._falta(t, self.coluna)
        if p is not None:
            return t, p

        i = t.indice(self.coluna)
        j = t.indice(destino)
        colunas = list(t.colunas) if j >= 0 else list(t.colunas) + [destino]
        linhas, incomparaveis, marcadas = [], 0, 0
        for linha in t.linhas:
            r = avaliar(self.condicao, linha[i], self.valor, self.valor2,
                        self.sensivel)
            antes = texto(linha[j]) if j >= 0 else ""
            if r is None:
                incomparaveis += 1
                novo = antes
            elif r:
                marcadas += 1
                partes = [x for x in antes.split(self.JUNTA.strip()) if x.strip()]
                novo = (antes if marca in [x.strip() for x in partes]
                        else (antes + self.JUNTA + marca if antes else marca))
            else:
                novo = antes
            if j >= 0:
                celulas = list(linha)
                celulas[j] = novo
                linhas.append(tuple(celulas))
            else:
                linhas.append(tuple(linha) + (novo,))
        return (Tabela(colunas=colunas, linhas=linhas),
                Passo(descricao=self.descrever() + " Marcadas "
                      + str(marcadas) + " linha(s).",
                      antes=t.n_linhas, depois=len(linhas),
                      incomparaveis=incomparaveis,
                      destino_incomparaveis="seguiram adiante sem marca"))

    def descrever(self) -> str:
        destino = self.coluna_marca.strip() or "Marcação"
        frase = ('Marcadas com "' + self.marca.strip() + '", na coluna "'
                 + destino + '", as linhas em que '
                 + frase_condicao(self.coluna, self.condicao, self.valor,
                                  self.valor2, self.sensivel) + ".")
        razao = " ".join(self.justificativa.split())
        if razao:
            frase += " Justificativa: " + razao
            if not razao.endswith("."):
                frase += "."
        return frase

    def dados(self) -> dict:
        return {"tipo": self.tipo, "coluna_marca": self.coluna_marca,
                "marca": self.marca, "justificativa": self.justificativa,
                "coluna": self.coluna, "condicao": self.condicao,
                "valor": self.valor, "valor2": self.valor2,
                "sensivel": self.sensivel}

    @classmethod
    def de_dados(cls, d: dict) -> "Marcacao":
        return cls(coluna_marca=d.get("coluna_marca", "Marcação"),
                   marca=d.get("marca", "SIM"),
                   justificativa=d.get("justificativa", ""),
                   coluna=d.get("coluna", ""),
                   condicao=d.get("condicao", "igual"),
                   valor=d.get("valor", ""), valor2=d.get("valor2", ""),
                   sensivel=bool(d.get("sensivel", False)))


# ── cruzamento ───────────────────────────

#: Planilhas auxiliares já lidas. O roteiro é refeito do zero a cada
#: mudança na tela (ver o cabeçalho de `planilha.py`), e reabrir cem mil
#: linhas a cada tecla inviabilizaria a ferramenta. A chave carrega a
#: hora de modificação e o tamanho do arquivo: trocado no disco, ele
#: invalida a própria entrada, sem ninguém precisar lembrar de limpar.
_CACHE_AUXILIAR: dict = {}

#: Quantas planilhas auxiliares ficam em memória. Um roteiro costuma
#: cruzar uma ou duas; o teto existe para que abrir muitas em sequência
#: não vá guardando todas.
TETO_CACHE_AUXILIAR = 4


def ler_auxiliar(caminho: str, aba: str, linha_cabecalho: int) -> tuple:
    """(tabela, resumo do arquivo, erro) da planilha cruzada."""
    from .hash_core import sha256_file

    if not caminho:
        return None, "", "não indicada"
    try:
        estado = Path(caminho).stat()
    except OSError:
        return None, "", "não encontrada em " + str(caminho)
    chave = (str(caminho), aba, int(linha_cabecalho),
             estado.st_mtime_ns, estado.st_size)
    guardado = _CACHE_AUXILIAR.get(chave)
    if guardado is not None:
        return guardado[0], guardado[1], ""
    try:
        tabela = carregar(caminho, aba, linha_cabecalho)
        resumo = sha256_file(caminho)
    except Exception as e:                              # noqa: BLE001
        return None, "", "não pôde ser lida: " + str(e)
    if len(_CACHE_AUXILIAR) >= TETO_CACHE_AUXILIAR:
        _CACHE_AUXILIAR.pop(next(iter(_CACHE_AUXILIAR)))
    _CACHE_AUXILIAR[chave] = (tabela, resumo)
    return tabela, resumo, ""


#: Destino da linha que não encontrou par -> como se lê na peça.
SEM_PAR: dict[str, str] = {
    "manter": "mantidas, com as colunas trazidas vazias",
    "descartar": "descartadas",
    "somente": "é o que fica; as que encontraram par saem",
}


@dataclass
class Cruzamento(Operacao):
    """Traz colunas de outra planilha, casando por uma coluna-chave.

    É o PROCV, e em auditoria costuma ser o passo que produz o achado: a
    folha contra o cadastro, o empenho contra a nota, o beneficiário
    contra o quadro de servidores.

    Três coisas o separam do PROCV da planilha comum, e as três existem
    porque a peça precisa poder ser conferida:

    **A segunda planilha entra na peça com resumo próprio.** O resultado
    passa a depender de dois arquivos; dizer que veio só do primeiro
    seria afirmação incompleta, e não haveria como demonstrar contra o
    que o cruzamento foi feito.

    **Chave repetida do outro lado é contada e declarada.** O PROCV pega
    a primeira ocorrência e se cala. Aqui também se usa a primeira — mas
    a peça registra quantas chaves tinham mais de uma, porque saber que o
    casamento foi ambíguo muda o peso do achado.

    **A linha sem par não some por descuido.** O destino dela é escolha
    declarada: mantida com as colunas vazias, descartada, ou é justamente
    o que se quer guardar — que é como se produz a relação das
    divergências, o cruzamento que mais interessa numa apuração.
    """

    arquivo: str = ""
    #: Resumo do arquivo no momento em que foi escolhido. Serve para o
    #: passo acusar, na re-execução, que a planilha cruzada não é mais a
    #: mesma — sem isso o roteiro renderia outro resultado sem explicar.
    resumo_arquivo: str = ""
    aba: str = ""
    linha_cabecalho: int = 1
    chave_aqui: str = ""
    chave_la: str = ""
    trazer: list = field(default_factory=list)
    sensivel: bool = False
    sem_par: str = "manter"

    tipo = "cruzamento"

    def _parado(self, t: Tabela, motivo: str) -> Passo:
        return Passo(descricao=self.descrever(), antes=t.n_linhas,
                     depois=t.n_linhas, aviso="não executado: " + motivo)

    def aplicar(self, t: Tabela) -> tuple[Tabela, Passo]:
        p = self._falta(t, self.chave_aqui)
        if p is not None:
            return t, p
        outra, resumo, erro = ler_auxiliar(self.arquivo, self.aba,
                                            self.linha_cabecalho)
        if outra is None:
            return t, self._parado(t, "a planilha cruzada " + erro)
        if outra.indice(self.chave_la) < 0:
            return t, self._parado(
                t, 'a coluna "' + self.chave_la
                + '" não existe na planilha cruzada')

        avisos = []
        if self.resumo_arquivo and resumo and resumo != self.resumo_arquivo:
            avisos.append(
                "a planilha cruzada mudou depois de escolhida: o resumo do "
                "arquivo não é mais o declarado no roteiro")

        trazer = [c for c in self.trazer if outra.indice(c) >= 0]
        sumidas = [c for c in self.trazer if outra.indice(c) < 0]
        if sumidas:
            avisos.append("colunas ausentes na planilha cruzada: "
                          + ", ".join('"' + c + '"' for c in sumidas))

        arruma = (str.strip) if self.sensivel else sem_acento
        jota = outra.indice(self.chave_la)
        de_la = [outra.indice(c) for c in trazer]
        indice: dict = {}
        ambiguas: set = set()
        for linha in outra.linhas:
            k = arruma(texto(linha[jota]))
            if k in indice:
                ambiguas.add(k)
                continue
            indice[k] = tuple(linha[i] for i in de_la)
        if ambiguas:
            avisos.append(
                str(len(ambiguas)) + " chave(s) da planilha cruzada "
                "apareciam mais de uma vez; de cada uma foi usada a "
                "primeira ocorrência")

        novos: list = []
        for c in trazer:
            novos.append(_nome_livre(list(t.colunas) + novos, c))
        vazios = tuple(VAZIO for _ in trazer)

        aqui = t.indice(self.chave_aqui)
        linhas, com_par, sem = [], 0, 0
        for linha in t.linhas:
            par = indice.get(arruma(texto(linha[aqui])))
            if par is None:
                sem += 1
                if self.sem_par == "descartar":
                    continue
            else:
                com_par += 1
                if self.sem_par == "somente":
                    continue
            linhas.append(tuple(linha) + (vazios if par is None else par))

        return (Tabela(colunas=list(t.colunas) + novos, linhas=linhas),
                Passo(descricao=self.descrever() + " Encontraram par "
                      + str(com_par) + " linha(s); " + str(sem) + ", não.",
                      antes=t.n_linhas, depois=len(linhas),
                      aviso="; ".join(avisos)))

    def descrever(self) -> str:
        nome = Path(self.arquivo).name if self.arquivo else "(não indicada)"
        frase = 'Cruzada com a planilha "' + nome + '"'
        if self.aba:
            frase += ', aba "' + self.aba + '"'
        frase += (', casando "' + self.chave_aqui + '" com "'
                  + self.chave_la + '"')
        if self.trazer:
            frase += (", trazendo "
                      + ", ".join('"' + c + '"' for c in self.trazer))
        frase += (", distinguindo maiúsculas e acentos" if self.sensivel
                  else ", sem distinguir maiúsculas nem acentos")
        return (frase + ". Linhas sem par: "
                + SEM_PAR.get(self.sem_par, self.sem_par) + ".")

    def dados(self) -> dict:
        return {"tipo": self.tipo, "arquivo": self.arquivo,
                "resumo_arquivo": self.resumo_arquivo, "aba": self.aba,
                "linha_cabecalho": int(self.linha_cabecalho),
                "chave_aqui": self.chave_aqui, "chave_la": self.chave_la,
                "trazer": list(self.trazer), "sensivel": self.sensivel,
                "sem_par": self.sem_par}

    @classmethod
    def de_dados(cls, d: dict) -> "Cruzamento":
        return cls(arquivo=d.get("arquivo", ""),
                   resumo_arquivo=d.get("resumo_arquivo", ""),
                   aba=d.get("aba", ""),
                   linha_cabecalho=int(d.get("linha_cabecalho", 1)),
                   chave_aqui=d.get("chave_aqui", ""),
                   chave_la=d.get("chave_la", ""),
                   trazer=list(d.get("trazer", [])),
                   sensivel=bool(d.get("sensivel", False)),
                   sem_par=d.get("sem_par", "manter"))


def arquivos_auxiliares(analise) -> list:
    """As planilhas que o roteiro consulta além da de partida.

    O termo precisa relacionar cada uma com o seu resumo: o resultado
    depende delas tanto quanto do arquivo aberto, e uma peça que citasse
    só a origem estaria escondendo metade do que produziu o achado.
    """
    vistos: list = []
    for op in analise.operacoes:
        caminho = getattr(op, "arquivo", "")
        if caminho and caminho not in vistos:
            vistos.append(caminho)
    return vistos


#: Como o roteiro salvo volta a ser operação. Toda operação nova precisa
#: entrar aqui, senão o roteiro grava e não relê.
TIPOS: dict = {
    Filtro.tipo: Filtro,
    Ordenacao.tipo: Ordenacao,
    Colunas.tipo: Colunas,
    Duplicidades.tipo: Duplicidades,
    Derivada.tipo: Derivada,
    Agrupamento.tipo: Agrupamento,
    Marcacao.tipo: Marcacao,
    Cruzamento.tipo: Cruzamento,
}


# ─────────────────────────────────────────
#  A ANÁLISE
# ─────────────────────────────────────────

@dataclass
class Analise:
    """O arquivo de partida e o roteiro aplicado sobre ele.

    É esta a coisa que se salva, se carrega e se re-executa. Guardar a
    tabela resultante seria guardar a conclusão; guardar o roteiro é
    guardar o caminho, que é o que se pode conferir.
    """

    origem: str = ""
    resumo_origem: str = ""
    tamanho_origem: int = 0
    aba: str = ""
    linha_cabecalho: int = 1
    #: Quando o arquivo foi lido por esta ferramenta. A cadeia de
    #: custódia da análise começa aqui, e não antes — ver as ressalvas.
    aberta_em: str = ""
    #: Fórmulas sem resultado guardado no arquivo. Zero é o normal.
    formulas_vazias: int = 0
    colunas_originais: list = field(default_factory=list)
    linhas_originais: int = 0
    operacoes: list = field(default_factory=list)

    def executar(self, base: Tabela) -> tuple[Tabela, list]:
        """Aplica o roteiro inteiro, do começo, sobre a tabela lida.

        Do começo sempre, e não a partir de onde parou: é o que garante
        que o resultado na tela seja o mesmo que qualquer um obteria
        re-executando o roteiro do zero. Recalcular custa milésimos —
        filtrar cem mil linhas leva 0,05 s.
        """
        t, passos = base, []
        for op in self.operacoes:
            t, p = op.aplicar(t)
            passos.append(p)
        return t, passos

    def dados(self) -> dict:
        return {"versao": 1, "origem": self.origem,
                "resumo_origem": self.resumo_origem,
                "tamanho_origem": self.tamanho_origem,
                "aba": self.aba, "linha_cabecalho": self.linha_cabecalho,
                "aberta_em": self.aberta_em,
                "formulas_vazias": self.formulas_vazias,
                "colunas_originais": list(self.colunas_originais),
                "linhas_originais": self.linhas_originais,
                "operacoes": [o.dados() for o in self.operacoes]}

    @classmethod
    def de_dados(cls, d: dict) -> "Analise":
        ops = []
        for item in d.get("operacoes", []):
            classe = TIPOS.get(item.get("tipo", ""))
            if classe is not None:
                ops.append(classe.de_dados(item))
        return cls(origem=d.get("origem", ""),
                   resumo_origem=d.get("resumo_origem", ""),
                   tamanho_origem=int(d.get("tamanho_origem", 0)),
                   aba=d.get("aba", ""),
                   linha_cabecalho=int(d.get("linha_cabecalho", 1)),
                   aberta_em=d.get("aberta_em", ""),
                   formulas_vazias=int(d.get("formulas_vazias", 0)),
                   colunas_originais=list(d.get("colunas_originais", [])),
                   linhas_originais=int(d.get("linhas_originais", 0)),
                   operacoes=ops)


def abrir(caminho, aba: str = "", linha_cabecalho: int = 1):
    """Abre a planilha e devolve (análise recém-nascida, tabela lida).

    O resumo criptográfico do arquivo é tirado **aqui**, no primeiro
    contato, antes de qualquer coisa. É o marco a partir do qual esta
    ferramenta pode responder pelo material.
    """
    from .hash_core import sha256_file

    caminho = str(caminho)
    tabela = carregar(caminho, aba, linha_cabecalho)
    try:
        tamanho = Path(caminho).stat().st_size
        resumo = sha256_file(caminho)
    except OSError:
        tamanho, resumo = 0, ""
    analise = Analise(
        origem=caminho, resumo_origem=resumo, tamanho_origem=tamanho,
        aba=aba, linha_cabecalho=linha_cabecalho,
        aberta_em=datetime.datetime.now().astimezone().isoformat(
            timespec="seconds"),
        formulas_vazias=formulas_sem_valor(caminho),
        colunas_originais=list(tabela.colunas),
        linhas_originais=tabela.n_linhas)
    return analise, tabela


def reproduzir(analise: Analise, esperado: str) -> tuple[bool, str, str]:
    """Re-executa o roteiro do arquivo original e confere o resultado.

    Esta função é a razão de ser da ferramenta. Ela responde, por
    verificação e não por afirmação, à única pergunta que importa: quem
    partir deste arquivo e seguir estes passos chega a este resultado?

    Devolve (conferiu, resumo obtido, motivo da falha).
    """
    from .hash_core import sha256_file

    try:
        agora = sha256_file(analise.origem)
    except OSError as e:
        return False, "", f"não foi possível reler o arquivo original: {e}"
    if analise.resumo_origem and agora != analise.resumo_origem:
        return False, "", ("o arquivo original mudou desde a abertura — "
                           "o resumo criptográfico não confere mais")
    try:
        base = carregar(analise.origem, analise.aba, analise.linha_cabecalho)
        final, _ = analise.executar(base)
    except Exception as e:                                   # noqa: BLE001
        return False, "", f"{type(e).__name__}: {e}"
    obtido = final.resumo()
    if obtido != esperado:
        return False, obtido, ("a re-execução produziu resultado diferente "
                               "do que está na tela")
    return True, obtido, ""


# ─────────────────────────────────────────
#  GRAVAÇÃO DO RESULTADO
# ─────────────────────────────────────────

def gravar(t: Tabela, caminho) -> None:
    """Grava o resultado. Formato pela extensão do nome escolhido.

    Os valores vão como estão — data como data, número como número,
    texto como texto. Converter tudo em texto na saída faria o arquivo
    entregue diferir do que foi analisado, e o resumo dos dados deixaria
    de servir para conferir o que está nos autos.
    """
    caminho = str(caminho)
    if Path(caminho).suffix.lower() in (".csv", ".txt"):
        # Ponto-e-vírgula e BOM: é o que o Excel em português abre em
        # colunas e com acento certo, sem assistente de importação.
        with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(t.colunas)
            w.writerows([texto(c) for c in l] for l in t.linhas)
        return
    from openpyxl import Workbook

    # `write_only` grava a linha e a esquece, em vez de manter a planilha
    # inteira em memória: é a diferença entre gravar cem mil linhas em
    # segundos ou em minuto e meio.
    livro = Workbook(write_only=True)
    folha = livro.create_sheet("Resultado")
    folha.append(list(t.colunas))
    for linha in t.linhas:
        folha.append([c if c != VAZIO else None for c in linha])
    livro.save(caminho)


def salvar_roteiro(analise: Analise, caminho) -> None:
    """Grava o roteiro em JSON, para acompanhar a peça nos autos.

    É o que permite a terceiro refazer a análise sem depender de nada
    que esteja nesta máquina — nem da tela, nem de quem a operou.
    """
    Path(caminho).write_text(
        json.dumps(analise.dados(), ensure_ascii=False, indent=2),
        encoding="utf-8")


def ler_roteiro(caminho) -> Analise:
    return Analise.de_dados(
        json.loads(Path(caminho).read_text(encoding="utf-8")))


# ─────────────────────────────────────────
#  O TERMO
# ─────────────────────────────────────────

@dataclass
class TermoPlanilha(derivado.TermoDerivado):
    """A peça da análise.

    Herda de `TermoDerivado` porque a qualificação de quem assina, o
    número do procedimento e o quadro de arquivos são idênticos — e
    porque assim o mesmo diálogo serve às duas. O que ela acrescenta é o
    roteiro: a lista numerada dos passos, com o antes e o depois de cada
    um, que é a parte que ninguém consegue apresentar depois de trabalhar
    no Excel.
    """

    passos: list = field(default_factory=list)
    aba: str = ""
    linhas_originais: int = 0
    colunas_originais: int = 0
    linhas_finais: int = 0
    colunas_finais: int = 0
    formulas_vazias: int = 0
    #: Resumo do conteúdo do resultado — ver `Tabela.resumo`.
    resumo_dados: str = ""
    #: Vazio enquanto não se conferiu; "sim" quando a re-execução bateu;
    #: caso contrário, o motivo da divergência.
    reproducao: str = ""


#: O que a operação alcança e o que ela não alcança. Vai impresso: uma
#: ferramenta que se cala sobre os próprios limites convida a que se lhe
#: atribua alcance que ela não tem.
RESSALVAS = (
    "O arquivo original não foi alterado. Esta ferramenta o abre somente "
    "para leitura e nunca grava sobre ele; o resultado é sempre arquivo "
    "novo, em separado.",
    "Toda alteração de dado aqui é uma das operações relacionadas acima. "
    "A ferramenta não permite editar célula, e por isso a relação de "
    "passos é necessariamente completa: não há como ter havido alteração "
    "que não esteja declarada.",
    "As operações são determinísticas e independem da configuração "
    "regional da estação. O roteiro que acompanha esta peça pode ser "
    "re-executado por terceiro sobre o arquivo original, com a mesma "
    "ferramenta, e há de produzir resultado idêntico.",
    "A conferência de reprodutibilidade é feita sobre o resumo "
    "criptográfico do conteúdo — colunas e células, na ordem em que "
    "estão —, e não sobre os bytes do arquivo produzido. É que o formato "
    "de planilha guarda dentro de si a hora da gravação: gravar duas "
    "vezes o mesmo conteúdo gera arquivos de resumos diferentes, de modo "
    "que conferir pelo arquivo acusaria divergência onde não há.",
    "Esta peça responde pelo material a partir do momento em que o "
    "arquivo foi aberto por esta ferramenta, quando seu resumo "
    "criptográfico foi tomado. Nada afirma sobre a origem do arquivo "
    "antes disso.",
)

#: Acrescentada às demais quando o roteiro cruza com outra planilha. Só
#: então, porque ressalva que não se aplica ao caso é ruído que ensina o
#: leitor a passar os olhos pelas que se aplicam.
RESSALVA_CRUZAMENTO = (
    "O resultado depende também da planilha cruzada, relacionada acima "
    "entre as origens e identificada por resumo criptográfico próprio. "
    "Re-executar este roteiro exige os dois arquivos; alterada a segunda "
    "planilha, o resultado muda, e a conferência de reprodutibilidade "
    "acusa a divergência em vez de deixá-la passar."
)


def _quadro_roteiro(t: TermoPlanilha) -> str:
    """A tabela dos passos — o miolo da peça."""
    e = _escape

    linhas = ['<tr>'
              f'<td width="6%" align="center"><font color="{derivado.CINZA}" '
              'size="2"><b>#</b></font></td>'
              f'<td><font color="{derivado.CINZA}" size="2"><b>Operação'
              '</b></font></td>'
              f'<td width="22%" align="center"><font color="{derivado.CINZA}" '
              'size="2"><b>Linhas</b></font></td></tr>']
    for i, p in enumerate(t.passos, 1):
        nota = ""
        if p.incomparaveis:
            nota = (f'<br/><font color="{derivado.CINZA}" size="1">'
                    f'{p.incomparaveis} linha(s) não puderam ser comparadas '
                    f"e {e(p.destino_incomparaveis)}</font>")
        if p.aviso:
            nota += (f'<br/><font color="{derivado.CINZA}" size="1">'
                     f"{e(p.aviso)}</font>")
        movimento = (f"{p.antes} &rarr; {p.depois}" if p.antes != p.depois
                     else f"{p.depois} (sem alteração)")
        linhas.append(
            f'<tr><td align="center" valign="top">'
            f'<span style="font-size:10.5pt;">{i}</span></td>'
            f'<td><span style="font-size:10.5pt;">{e(p.descricao)}</span>'
            f"{nota}</td>"
            f'<td align="center" valign="top">'
            f'<span style="font-size:10.5pt;">{movimento}</span></td></tr>')
    return ('<table width="100%" cellspacing="0" cellpadding="5" border="1" '
            'style="border-collapse:collapse;">' + "".join(linhas) + "</table>")


def _frase_reproducao(t: TermoPlanilha) -> str:
    if t.reproducao == "sim":
        return ("A análise foi re-executada a partir do arquivo original, "
                "pelo roteiro acima, e reproduziu resumo de conteúdo "
                f"idêntico ao consignado ({t.resumo_dados}).")
    if t.reproducao:
        return ("A conferência de reprodutibilidade não pôde ser concluída: "
                + t.reproducao + ".")
    return ("O resumo de conteúdo do resultado é " + t.resumo_dados
            + ", e permite conferir, a qualquer tempo, que o arquivo "
              "entregue é o que saiu desta análise.")


def build_html(t: TermoPlanilha) -> str:
    """A peça em HTML, para exibir e exportar."""
    from ..impressao import cabecalho_html, rodape_html

    e = _escape
    partes = [
        "<html><body style=\"font-family:'Segoe UI',Arial,sans-serif; "
        'color:#16233a;">',
        cabecalho_html(),
        '<div align="center" style="margin-bottom:18px;">'
        f'<b style="font-size:14pt; letter-spacing:0.5px;">{e(t.titulo)}'
        "</b></div>",
        "<hr/>",
        f'<p align="justify" style="font-size:11pt; line-height:160%;">'
        f"{e(derivado.intro(t))}</p>",
    ]

    for i, d in enumerate(t.itens, 1):
        partes.append(derivado.quadro_de_arquivos(d, i))

    partes.append(
        f'<p style="font-size:11pt; margin-top:18px;">'
        f'<b><font color="{derivado.INK}">Roteiro da análise</font></b></p>')
    if t.formulas_vazias:
        partes.append(
            f'<p align="justify" style="font-size:10pt; line-height:150%;">'
            f'<font color="{derivado.INK}">Registre-se que o arquivo de '
            f"origem contém {t.formulas_vazias} célula(s) com fórmula sem "
            "resultado gravado, por nunca ter sido aberto em programa que "
            "as calculasse. Essas células foram lidas como vazias.</font></p>")
    partes.append(_quadro_roteiro(t))

    partes.append(
        f'<p align="justify" style="font-size:11pt; line-height:160%; '
        f'margin-top:14px;">{e(_frase_reproducao(t))}</p>')

    partes.append(
        f'<p style="font-size:11pt; margin-top:18px;">'
        f'<b><font color="{derivado.INK}">Alcance e limites da operação'
        "</font></b></p>")
    partes += [
        f'<p align="justify" style="font-size:10pt; line-height:150%;">'
        f'<font color="{derivado.INK}">{e(x)}</font></p>' for x in t.ressalvas]

    partes.append(
        f'<p align="justify" style="font-size:11pt; line-height:160%; '
        f'margin-top:16px;">{e(derivado.ENCERRAMENTO)}</p>')

    partes.append(
        '<p align="center" style="margin-top:38px; font-size:11pt;">'
        "______________________________________<br/>"
        f"<b>{e(t.nome)}</b><br/>"
        + (f'<span style="font-size:10pt;">{e(t.cargo)}</span><br/>'
           if t.cargo.strip() else "")
        + (f'<span style="font-size:10pt;">Matrícula {e(t.matricula)}</span>'
           if t.matricula.strip() else "")
        + "</p>" + rodape_html(*t.motores) + "</body></html>")
    return "".join(partes)


def build_texto(t: TermoPlanilha) -> str:
    """A mesma peça em texto puro."""
    L = [t.titulo.upper(), "", derivado.intro(t), ""]
    for d in t.itens:
        for o in d.origens:
            L.append(f"Arquivo original: {o.nome}")
            L.append(f"   Tamanho: {derivado.formatar_tamanho(o.tamanho)}")
            L.append(f"   SHA-256: {o.resumo or '—'}")
        L.append(f"Arquivo produzido: {d.saida.nome}")
        L.append(f"   Tamanho: {derivado.formatar_tamanho(d.saida.tamanho)}")
        L.append(f"   SHA-256: {d.saida.resumo or '—'}")
        for rotulo, valor in d.detalhes:
            L.append(f"   {rotulo}: {valor}")
    L.append("")
    L.append("ROTEIRO DA ANÁLISE")
    if t.formulas_vazias:
        L.append(f"(o arquivo de origem tem {t.formulas_vazias} fórmula(s) "
                 "sem resultado gravado; lidas como vazias)")
    for i, p in enumerate(t.passos, 1):
        L.append(f"{i}. {p.descricao}")
        L.append(f"   Linhas: {p.antes} -> {p.depois}")
        if p.incomparaveis:
            L.append(f"   {p.incomparaveis} linha(s) não puderam ser "
                     "comparadas e ficaram de fora")
        if p.aviso:
            L.append(f"   {p.aviso}")
    L += ["", _frase_reproducao(t), "", "ALCANCE E LIMITES DA OPERAÇÃO"]
    L += [f"- {x}" for x in t.ressalvas]
    L += ["", derivado.ENCERRAMENTO, "", "_" * 40, t.nome]
    if t.cargo.strip():
        L.append(t.cargo)
    if t.matricula.strip():
        L.append(f"Matrícula {t.matricula}")
    return "\n".join(L)


def montar_termo(analise: Analise, resultado: Tabela, passos: list,
                 saida: str, reproducao: str = "") -> TermoPlanilha:
    """Junta o que a análise produziu na peça pronta para assinar."""
    auxiliares = arquivos_auxiliares(analise)
    item = derivado.medir(
        [analise.origem] + auxiliares, saida,
        detalhes=[
            ("Aba analisada", analise.aba or "primeira"),
            ("Linhas do original", str(analise.linhas_originais)),
            ("Colunas do original", str(len(analise.colunas_originais))),
            ("Linhas do resultado", str(resultado.n_linhas)),
            ("Colunas do resultado", str(resultado.n_colunas)),
            ("Resumo do conteúdo (SHA-256)", resultado.resumo()),
        ])
    return TermoPlanilha(
        titulo="Termo de Análise de Planilha",
        operacao="exame analítico",
        ressalvas=RESSALVAS + ((RESSALVA_CRUZAMENTO,) if auxiliares
                               else ()),
        motores=("planilha",),
        itens=[item],
        passos=list(passos),
        aba=analise.aba,
        linhas_originais=analise.linhas_originais,
        colunas_originais=len(analise.colunas_originais),
        linhas_finais=resultado.n_linhas,
        colunas_finais=resultado.n_colunas,
        formulas_vazias=analise.formulas_vazias,
        resumo_dados=resultado.resumo(),
        reproducao=reproducao)
