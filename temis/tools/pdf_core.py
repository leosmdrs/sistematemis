"""
Documentos PDF — mesclar, separar e comprimir.

Três tarefas que hoje se fazem em sítio da internet, enviando o
documento do procedimento para servidor alheio. Fazê-las aqui resolve
isso; mas resolver só isso seria pouco. Como nas demais ferramentas do
sistema, a operação é **declarada** e o resultado é **conferível**.

**A conferência é do conteúdo, e não dos bytes** — e isto foi medido,
não suposto. Mesclando duas vezes os mesmos arquivos, com os mesmos
parâmetros, os PDFs produzidos têm resumos criptográficos diferentes;
limpando antes todos os metadados, continuam diferentes. Conferir pelos
bytes acusaria divergência onde não há. É o oposto da Edição de Vídeo,
onde o FFmpeg devolve arquivo idêntico e por isso se conferem os bytes.

O que se confere aqui é o **resumo das páginas**: cada página é
rasterizada numa resolução fixa e resumida, e o resumo do documento sai
da sequência desses resumos. Disso decorre uma afirmação mais forte do
que igualdade de arquivo, e mais útil na peça:

    ao mesclar e ao separar, **nenhuma página foi alterada** — as
    páginas do resultado são, uma a uma, as mesmas páginas das origens.

Comprimir é outra conversa, e a peça não pode fingir que não. Comprimir
sem perda costuma não ganhar nada num arquivo já limpo — medido: zero por
cento em documento recém-gravado. O ganho vem de reamostrar as imagens, e
isso **altera as páginas**: o resumo passa a divergir, de propósito, e o
termo declara a divergência em vez de escondê-la.

Uma diferença importante em relação à Tarja Preta, que também produz PDF:
lá cada página vira imagem e a camada de texto se perde. Aqui **a camada
de texto sobrevive** — medido em todos os níveis de compressão. O
documento comprimido continua pesquisável.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz

#: Resolução em que cada página é rasterizada para ser resumida. 72 dpi
#: é o ponto do PDF: uma página A4 vira 595×842, o bastante para que
#: qualquer diferença visível mude o resumo, e barato o bastante para
#: percorrer um documento de centenas de páginas sem cansar quem espera.
DPI_CONFERENCIA = 72

#: O que cada operação é, dito como vai na peça.
OPERACOES = {
    "mesclar": "mesclagem de documentos",
    "separar": "separação de páginas",
    "comprimir": "compactação de documento",
}


@dataclass
class Nivel:
    """Um grau de compactação, com o que ele faz e o que custa."""

    chave: str
    rotulo: str
    #: Resolução alvo das imagens. Zero significa não tocar em imagem
    #: alguma — só limpar e recomprimir os fluxos, sem perda.
    dpi: int = 0
    qualidade: int = 0
    explicacao: str = ""

    @property
    def com_perda(self) -> bool:
        return self.dpi > 0


#: Os números vêm de medida, num PDF de oito páginas que se comporta como
#: digitalização (2,33 MB): 0%, 66%, 75% e 97% de redução. O ganho real
#: depende do arquivo — documento sem imagem quase não encolhe, por não
#: haver o que reamostrar.
NIVEIS: tuple = (
    Nivel("sem_perda", "Sem perda", 0, 0,
          "Limpa o que sobra e recomprime os fluxos. Não altera página "
          "alguma — mas costuma ganhar pouco, ou nada, num arquivo que já "
          "esteja limpo."),
    Nivel("leve", "Leve — 120 dpi", 120, 80,
          "Reduz as imagens a 120 dpi. Mantém a leitura confortável na "
          "tela e na impressão comum."),
    Nivel("media", "Média — 96 dpi", 96, 65,
          "Reduz as imagens a 96 dpi. Boa para juntar aos autos "
          "documento digitalizado que excede o limite do sistema."),
    Nivel("forte", "Forte — 72 dpi", 72, 50,
          "Reduz as imagens a 72 dpi. Encolhe muito, e a perda passa a "
          "ser visível em detalhe fino — carimbo, assinatura, letra "
          "miúda."),
)


def nivel_por_chave(chave: str) -> Nivel:
    for n in NIVEIS:
        if n.chave == chave:
            return n
    return NIVEIS[0]


# ─────────────────────────────────────────
#  O DOCUMENTO
# ─────────────────────────────────────────

@dataclass
class Documento:
    """O que se sabe de um PDF sem ainda operar sobre ele."""

    caminho: str = ""
    paginas: int = 0
    tamanho: int = 0
    #: PDF protegido por senha. Não se abre, e a peça precisa dizer isso
    #: em vez de o programa cair.
    cifrado: bool = False
    erro: str = ""

    @property
    def nome(self) -> str:
        return Path(self.caminho).name if self.caminho else ""


def sondar(caminho) -> Documento:
    """Lê o que dá para saber do arquivo sem alterá-lo.

    Falha em abrir não estoura: vira `erro` no próprio registro. A lista
    da tela precisa poder mostrar o arquivo problemático junto dos
    demais, e não sumir com a operação inteira por causa de um.
    """
    d = Documento(caminho=str(caminho))
    try:
        d.tamanho = Path(caminho).stat().st_size
    except OSError as e:
        d.erro = f"{type(e).__name__}: {e}"
        return d
    try:
        with fitz.open(str(caminho)) as doc:
            d.cifrado = bool(doc.needs_pass)
            if d.cifrado:
                d.erro = "o documento está protegido por senha"
            else:
                d.paginas = doc.page_count
    except Exception as e:                                  # noqa: BLE001
        d.erro = f"{type(e).__name__}: {e}"
    return d


def formatar_tamanho(n: int) -> str:
    if n <= 0:
        return "—"
    valor = float(n)
    for unidade in ("bytes", "KB", "MB", "GB"):
        if valor < 1024 or unidade == "GB":
            return (f"{int(valor)} {unidade}" if unidade == "bytes"
                    else f"{valor:.1f} {unidade}".replace(".", ","))
        valor /= 1024
    return f"{valor:.1f} GB"


# ─────────────────────────────────────────
#  O RESUMO DAS PÁGINAS
# ─────────────────────────────────────────

def resumo_das_paginas(doc, dpi: int = DPI_CONFERENCIA,
                       progresso=None) -> list:
    """Um resumo criptográfico por página, do que a página mostra.

    Rasterizar e resumir os pixels, em vez de resumir o fluxo interno do
    PDF, é o que torna o resumo comparável entre documentos diferentes:
    a mesma página, mesclada num arquivo ou extraída para outro, é
    guardada de formas diferentes lá dentro e mostra exatamente a mesma
    coisa. É a igualdade do que se mostra que interessa à peça.
    """
    fora = []
    total = doc.page_count
    for i in range(total):
        if progresso is not None:
            progresso(i + 1, total)
        pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
        h = hashlib.sha256()
        h.update(f"{pix.width}x{pix.height}".encode("utf-8"))
        h.update(pix.samples)
        fora.append(h.hexdigest())
    return fora


def resumo_do_documento(paginas: list, dpi: int = DPI_CONFERENCIA) -> str:
    """O resumo do documento inteiro, derivado do de cada página.

    O separador é caractere de controle para que nenhum resumo de página
    consiga imitá-lo e fazer dois documentos diferentes resumirem igual.
    """
    h = hashlib.sha256()
    h.update(f"dpi={dpi}".encode("utf-8"))
    h.update(b"\x1e")
    for p in paginas:
        h.update(p.encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()


# ─────────────────────────────────────────
#  A ESCOLHA DE PÁGINAS
# ─────────────────────────────────────────

_FAIXA = re.compile(r"^\s*(\d+)\s*(?:[-–]\s*(\d+))?\s*$")


def ler_paginas(texto: str, total: int) -> tuple:
    """Interpreta "1-3, 7, 10-12" e devolve (índices, o que se ignorou).

    Os índices saem em base zero e sem repetição, na ordem escrita — a
    ordem importa, porque extrair "3,1" produz documento diferente de
    extrair "1,3", e quem escreveu assim quis assim.

    O segundo elemento não é enfeite: pedaço ignorado por estar fora do
    documento ou por não se entender precisa aparecer na tela e no termo.
    Sumir com ele em silêncio faria o resultado ter menos páginas do que
    se pediu, sem que nada dissesse por quê.
    """
    indices: list = []
    ignorados: list = []
    for pedaco in re.split(r"[,;]", texto or ""):
        if not pedaco.strip():
            continue
        m = _FAIXA.match(pedaco)
        if not m:
            ignorados.append(pedaco.strip())
            continue
        inicio = int(m.group(1))
        fim = int(m.group(2)) if m.group(2) else inicio
        if inicio > fim:
            inicio, fim = fim, inicio
        if fim < 1 or inicio > total:
            ignorados.append(pedaco.strip())
            continue
        cortou = inicio < 1 or fim > total
        for n in range(max(1, inicio), min(total, fim) + 1):
            if n - 1 not in indices:
                indices.append(n - 1)
        if cortou:
            ignorados.append(f"{pedaco.strip()} (o documento tem {total})")
    return indices, ignorados


def escrever_paginas(indices: list) -> str:
    """O caminho de volta: [0,1,2,6] vira "1-3, 7"."""
    if not indices:
        return ""
    partes, inicio, anterior = [], indices[0], indices[0]
    for n in indices[1:] + [None]:
        if n is not None and n == anterior + 1:
            anterior = n
            continue
        partes.append(f"{inicio + 1}" if inicio == anterior
                      else f"{inicio + 1}-{anterior + 1}")
        if n is not None:
            inicio = anterior = n
    return ", ".join(partes)


# ─────────────────────────────────────────
#  AS OPERAÇÕES
# ─────────────────────────────────────────

@dataclass
class Producao:
    """O que uma operação produziu, e com que se compara.

    `esperadas` são os resumos das páginas **das origens** que deveriam
    ter ido para o resultado. Guardar as duas listas é o que permite
    afirmar, e não supor, que mesclar e separar não alteraram página
    alguma — e permite à compactação com perda declarar honestamente que
    alterou.
    """

    documento: object = None
    paginas: list = field(default_factory=list)
    esperadas: list = field(default_factory=list)

    @property
    def resumo(self) -> str:
        return resumo_do_documento(self.paginas)

    @property
    def paginas_intactas(self) -> bool:
        return bool(self.paginas) and self.paginas == self.esperadas

    def fechar(self):
        if self.documento is not None:
            self.documento.close()
            self.documento = None


def _abrir(caminho):
    doc = fitz.open(str(caminho))
    if doc.needs_pass:
        doc.close()
        raise RuntimeError(
            f"{Path(caminho).name} está protegido por senha e não pôde ser "
            "aberto.")
    return doc


def executar(operacao: str, origens: list, parametros: dict,
             progresso=None) -> Producao:
    """Faz a operação e mede as duas coisas que a peça vai afirmar.

    Devolve o documento produzido **aberto**, ainda não gravado: quem
    chama decide o destino. É de propósito — a mesma função serve para
    produzir e para reconferir, e reconferir não deve escrever em disco.
    """
    saida = fitz.open()
    esperadas: list = []

    if operacao == "mesclar":
        for caminho in origens:
            with _abrir(caminho) as o:
                esperadas += resumo_das_paginas(o)
                saida.insert_pdf(o)

    elif operacao == "separar":
        with _abrir(origens[0]) as o:
            todas = resumo_das_paginas(o)
            for i in parametros.get("paginas", []):
                if 0 <= i < o.page_count:
                    esperadas.append(todas[i])
                    saida.insert_pdf(o, from_page=i, to_page=i)

    elif operacao == "comprimir":
        nivel = nivel_por_chave(parametros.get("nivel", ""))
        with _abrir(origens[0]) as o:
            esperadas = resumo_das_paginas(o)
            saida.insert_pdf(o)
        if nivel.com_perda:
            # O limiar é o piso a partir do qual a imagem é reamostrada, e
            # o alvo tem de ficar abaixo dele. Alvo+1 faz toda imagem
            # acima do alvo ser reduzida, que é o que se quer.
            saida.rewrite_images(dpi_threshold=nivel.dpi + 1,
                                 dpi_target=nivel.dpi,
                                 quality=nivel.qualidade)
        try:
            saida.subset_fonts()
        except Exception:                                   # noqa: BLE001
            # Reduzir fonte é ganho marginal; falhar nisso não pode
            # derrubar a compactação inteira.
            pass
    else:
        saida.close()
        raise ValueError("operação desconhecida: " + operacao)

    return Producao(documento=saida,
                    paginas=resumo_das_paginas(saida, progresso=progresso),
                    esperadas=esperadas)


def gravar(doc, destino) -> None:
    """Grava o produzido, limpo do que não é conteúdo.

    Os metadados do original não acompanham: o documento é composto do
    zero e recebe só as páginas. Limpar o que a própria biblioteca
    escreveria evita que a peça circule declarando programa e data de
    geração que nada dizem sobre o ato.
    """
    doc.set_metadata({})
    try:
        doc.del_xml_metadata()
    except Exception:                                       # noqa: BLE001
        pass
    doc.save(str(destino), garbage=4, deflate=True, clean=True)


# ─────────────────────────────────────────
#  O ROTEIRO
# ─────────────────────────────────────────

@dataclass
class Roteiro:
    """A operação declarada, com o que ela precisa para ser refeita.

    Guardar o PDF produzido seria guardar a conclusão. Guardar o roteiro
    é guardar o caminho — e o caminho é o que se confere.
    """

    operacao: str = ""
    #: [(caminho, resumo do arquivo)] na ordem em que entraram, que na
    #: mesclagem é o que decide o resultado.
    origens: list = field(default_factory=list)
    parametros: dict = field(default_factory=dict)
    #: Resumo do conteúdo produzido — ver o cabeçalho do módulo.
    resumo_conteudo: str = ""
    paginas_produzidas: int = 0
    paginas_intactas: bool = False
    #: A versão da biblioteca que compôs. A promessa de reprodução vale
    #: para ela; com outra, o resultado pode ser equivalente sem ser
    #: idêntico, e a peça precisa poder dizer qual dos dois casos é.
    pymupdf: str = ""
    criado_em: str = ""

    @property
    def caminhos(self) -> list:
        return [c for c, _ in self.origens]

    def descrever(self) -> str:
        return OPERACOES.get(self.operacao, self.operacao)

    def dados(self) -> dict:
        return {"versao": 1, "operacao": self.operacao,
                "origens": [{"caminho": c, "resumo": r}
                            for c, r in self.origens],
                "parametros": dict(self.parametros),
                "resumo_conteudo": self.resumo_conteudo,
                "paginas_produzidas": self.paginas_produzidas,
                "paginas_intactas": self.paginas_intactas,
                "pymupdf": self.pymupdf, "criado_em": self.criado_em}

    @classmethod
    def de_dados(cls, d: dict) -> "Roteiro":
        return cls(operacao=d.get("operacao", ""),
                   origens=[(x.get("caminho", ""), x.get("resumo", ""))
                            for x in d.get("origens", [])],
                   parametros=dict(d.get("parametros", {})),
                   resumo_conteudo=d.get("resumo_conteudo", ""),
                   paginas_produzidas=int(d.get("paginas_produzidas", 0)),
                   paginas_intactas=bool(d.get("paginas_intactas", False)),
                   pymupdf=d.get("pymupdf", ""),
                   criado_em=d.get("criado_em", ""))


def versao_biblioteca() -> str:
    try:
        return str(fitz.version[0])
    except Exception:                                       # noqa: BLE001
        return ""


def montar(operacao: str, origens: list, parametros: dict,
           producao: Producao) -> Roteiro:
    """O roteiro correspondente à operação que acabou de rodar."""
    from ..relogio import carimbo
    from .hash_core import sha256_file

    def resumo(caminho):
        try:
            return sha256_file(str(caminho))
        except OSError:
            return ""

    return Roteiro(
        operacao=operacao,
        origens=[(str(c), resumo(c)) for c in origens],
        parametros=dict(parametros),
        resumo_conteudo=producao.resumo,
        paginas_produzidas=len(producao.paginas),
        paginas_intactas=producao.paginas_intactas,
        pymupdf=versao_biblioteca(),
        criado_em=carimbo())


def salvar_roteiro(roteiro: Roteiro, caminho) -> None:
    Path(caminho).write_text(
        json.dumps(roteiro.dados(), ensure_ascii=False, indent=2),
        encoding="utf-8")


def ler_roteiro(caminho) -> Roteiro:
    return Roteiro.de_dados(
        json.loads(Path(caminho).read_text(encoding="utf-8")))


def reproduzir(roteiro: Roteiro, esperado: str = "") -> tuple:
    """Refaz a operação sobre as origens e confere o resultado.

    É a função que dá razão a todo o resto: responde por verificação, e
    não por afirmação, à pergunta de quem recebe a peça — partindo destes
    arquivos e seguindo estes parâmetros, chega-se a este documento?

    Devolve (situação, resumo obtido, explicação). A situação é "sim",
    "nao" ou "impossivel" — e a terceira não é a segunda: origem que
    sumiu não é operação que não reproduz.
    """
    from .hash_core import sha256_file

    alvo = esperado or roteiro.resumo_conteudo
    for caminho, resumo_declarado in roteiro.origens:
        p = Path(caminho)
        if not p.is_file():
            return "impossivel", "", (
                "o arquivo de origem não foi encontrado em " + str(p))
        try:
            atual = sha256_file(str(p))
        except OSError as e:
            return "impossivel", "", f"não foi possível ler {p.name}: {e}"
        if resumo_declarado and atual != resumo_declarado:
            return "impossivel", "", (
                f"{p.name} não é mais o mesmo arquivo: o resumo atual não "
                "corresponde ao declarado no roteiro")

    try:
        producao = executar(roteiro.operacao, roteiro.caminhos,
                            roteiro.parametros)
    except Exception as e:                                  # noqa: BLE001
        return "impossivel", "", f"{type(e).__name__}: {e}"
    obtido = producao.resumo
    producao.fechar()

    if not alvo:
        return "impossivel", obtido, "não há resumo declarado a conferir"
    if obtido == alvo:
        return "sim", obtido, ""
    return "nao", obtido, "o conteúdo produzido não corresponde ao declarado"


def frase_reproducao(situacao: str, resumo: str, explicacao: str = "") -> str:
    """Como a conferência se lê na peça."""
    if situacao == "sim":
        return ("A operação foi refeita a partir dos arquivos de origem, "
                "pelos mesmos parâmetros, e produziu documento de conteúdo "
                f"idêntico ao consignado ({resumo}).")
    if situacao == "nao":
        return ("A conferência não confirmou o resultado: refeita a "
                "operação sobre os mesmos arquivos de origem, o documento "
                f"produzido teve conteúdo diverso ({resumo}). " + explicacao)
    return ("A conferência de reprodutibilidade não pôde ser concluída: "
            + explicacao + ".")
