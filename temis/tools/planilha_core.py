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

    def _grandeza(self, v):
        d = como_data(v)
        return float(d.toordinal()) if d is not None else como_numero(v)

    def _casa(self, celula):
        """Verdadeiro, falso, ou None quando não deu para comparar."""
        c = self.condicao
        if c == "vazio":
            return not texto(celula)
        if c == "preenchido":
            return bool(texto(celula))

        if c in ORDINAIS:
            a = self._grandeza(celula)
            b = self._grandeza(self.valor)
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
            b2 = self._grandeza(self.valor2)
            if b2 is None:
                return None
            baixo, alto = min(b, b2), max(b, b2)
            return baixo <= a <= alto

        arruma = (str.strip) if self.sensivel else sem_acento
        alvo = arruma(texto(celula))
        ref = arruma(self.valor)
        if c == "igual":
            return alvo == ref
        if c == "diferente":
            return alvo != ref
        if c == "contem":
            return ref in alvo
        if c == "nao_contem":
            return ref not in alvo
        if c == "comeca":
            return alvo.startswith(ref)
        if c == "termina":
            return alvo.endswith(ref)
        if c == "na_lista":
            lista = {arruma(x) for x in SEPARA_LISTA.split(self.valor)
                     if x.strip()}
            return alvo in lista
        return False

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
        rotulo, quantos = CONDICOES.get(self.condicao, (self.condicao, 1))
        verbo = "Mantidas" if self.manter else "Descartadas"
        frase = verbo + ' as linhas em que "' + self.coluna + '" ' + rotulo
        if quantos == 1:
            valores = [v for v in SEPARA_LISTA.split(self.valor) if v.strip()]
            if self.condicao == "na_lista" and len(valores) > 6:
                frase += " (" + str(len(valores)) + " valores relacionados)"
            else:
                frase += ' "' + self.valor + '"'
        elif quantos == 2:
            frase += ' "' + self.valor + '" e "' + self.valor2 + '"'
        if quantos and self.condicao not in ORDINAIS:
            frase += (", distinguindo maiúsculas e acentos" if self.sensivel
                      else ", sem distinguir maiúsculas nem acentos")
        return frase

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


#: Como o roteiro salvo volta a ser operação. Toda operação nova precisa
#: entrar aqui, senão o roteiro grava e não relê.
TIPOS: dict = {
    Filtro.tipo: Filtro,
    Ordenacao.tipo: Ordenacao,
    Colunas.tipo: Colunas,
    Duplicidades.tipo: Duplicidades,
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
                    "e ficaram de fora</font>")
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
    from ..impressao import cabecalho_html

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
        + "</p></body></html>")
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
    item = derivado.medir(
        analise.origem, saida,
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
        ressalvas=RESSALVAS,
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
