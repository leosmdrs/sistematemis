"""Censura auditável: o roteiro das tarjas, e a conferência dele.

A Tarja Preta produzia um arquivo e um termo que dizia "N áreas cobertas
em M páginas". É afirmação: quem lê acredita ou não acredita, e não tem
como refazer o caminho. Um terceiro que quisesse conferir precisaria do
original, da relação exata das áreas e do mesmo modo de rasterizar — e
nada disso saía da ferramenta.

Aqui a censura passa a ser **roteiro**, no mesmo molde da Análise de
Planilha: uma relação declarada de retângulos sobre páginas, que
qualquer pessoa re-executa sobre o arquivo original para chegar
exatamente ao mesmo resultado. A peça deixa de afirmar e passa a ser
conferível, que é garantia de outra natureza.

Duas decisões, cada uma por um motivo medido:

**A conferência é do conteúdo, e não do arquivo.** Gravar duas vezes a
mesma censura produz PDFs de bytes diferentes — o formato guarda dentro
de si a hora da gravação e a ordem dos objetos. Conferir pelo resumo do
arquivo acusaria divergência onde não há. O que se confere é o resumo
das páginas rasterizadas, que é o material que a censura produziu, e que
independe do empacotamento.

**A reprodução depende da versão do motor**, e isso vai declarado. A
rasterização é determinística, mas quem a faz é o PyMuPDF: a mesma
página, no mesmo fator, sai igual sempre — no mesmo PyMuPDF. Por isso a
linha de procedência ao pé da peça nomeia a versão. Sem ela, "confere"
seria promessa sem endereço.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass, field
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

#: Fator de rasterização (2,0 ≈ 144 DPI). Entra no roteiro porque muda o
#: resultado: a mesma tarja sobre a mesma página, em fator diferente,
#: produz conteúdo diferente e resumo diferente.
ESCALA = 2.0

#: Como cada tarja nasceu. Vai impresso no roteiro porque distingue o que
#: foi decidido à mão do que a busca automática apontou — e quem confere
#: uma censura quer saber quais áreas alguém escolheu cobrir.
ORIGENS = {
    "manual": "área marcada à mão",
    "texto": "seleção de texto",
    "colchete": "marcação por sinal no texto-fonte",
    "busca": "busca automática de dado protegido",
}


@dataclass(frozen=True)
class Tarja:
    """Um retângulo coberto, na página em que está."""

    pagina: int
    x0: float
    y0: float
    x1: float
    y1: float
    origem: str = "manual"

    def rect(self):
        return fitz.Rect(self.x0, self.y0, self.x1, self.y1)

    def dados(self) -> dict:
        return {"pagina": self.pagina, "x0": self.x0, "y0": self.y0,
                "x1": self.x1, "y1": self.y1, "origem": self.origem}

    @classmethod
    def de_dados(cls, d: dict) -> "Tarja":
        return cls(pagina=int(d.get("pagina", 0)),
                   x0=float(d.get("x0", 0)), y0=float(d.get("y0", 0)),
                   x1=float(d.get("x1", 0)), y1=float(d.get("y1", 0)),
                   origem=d.get("origem", "manual"))


@dataclass
class Roteiro:
    """O arquivo de partida e as tarjas aplicadas sobre ele.

    É esta a coisa que se salva e que se re-executa. Guardar o arquivo
    censurado seria guardar a conclusão; guardar o roteiro é guardar o
    caminho, que é o que se pode conferir.
    """

    origem: str = ""
    resumo_origem: str = ""
    escala: float = ESCALA
    #: Resumo do conteúdo produzido, para a conferência bater contra ele.
    resumo_conteudo: str = ""
    criado_em: str = ""
    tarjas: list = field(default_factory=list)

    @property
    def paginas_atingidas(self) -> int:
        return len({t.pagina for t in self.tarjas})

    def por_pagina(self) -> dict:
        saida: dict = {}
        for t in self.tarjas:
            saida.setdefault(t.pagina, []).append((t.rect(), t.origem))
        return saida

    def dados(self) -> dict:
        return {"versao": 1, "origem": self.origem,
                "resumo_origem": self.resumo_origem, "escala": self.escala,
                "resumo_conteudo": self.resumo_conteudo,
                "criado_em": self.criado_em,
                "tarjas": [t.dados() for t in self.tarjas]}

    @classmethod
    def de_dados(cls, d: dict) -> "Roteiro":
        return cls(origem=d.get("origem", ""),
                   resumo_origem=d.get("resumo_origem", ""),
                   escala=float(d.get("escala", ESCALA)),
                   resumo_conteudo=d.get("resumo_conteudo", ""),
                   criado_em=d.get("criado_em", ""),
                   tarjas=[Tarja.de_dados(x) for x in d.get("tarjas", [])])


def montar(caminho: str, tarjas_por_pagina: dict, escala: float = ESCALA):
    """O roteiro correspondente ao que está na tela."""
    from ..relogio import carimbo
    from .hash_core import sha256_file

    try:
        resumo = sha256_file(caminho)
    except OSError:
        resumo = ""
    tarjas = [Tarja(pagina=p, x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1,
                    origem=origem)
              for p, lista in sorted(tarjas_por_pagina.items())
              for r, origem in lista]
    return Roteiro(origem=str(caminho), resumo_origem=resumo, escala=escala,
                   criado_em=carimbo(), tarjas=tarjas)


def compor(doc, tarjas_por_pagina: dict, escala: float = ESCALA,
           progresso=None) -> tuple:
    """Rasteriza cada página, cobre as áreas e devolve (documento, resumo).

    O resumo sai daqui, e não do arquivo gravado depois: é dos pixels
    produzidos, que são o material da censura. O PDF que os embala carrega
    a hora da gravação e muda de bytes a cada vez.
    """
    saida = fitz.open()
    h = hashlib.sha256()
    h.update(f"escala={escala}".encode("utf-8"))
    total = len(doc)

    for i in range(total):
        if progresso is not None:
            progresso(i + 1, total)
        pagina = doc[i]
        pix = pagina.get_pixmap(matrix=fitz.Matrix(escala, escala),
                                alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        desenho = ImageDraw.Draw(img)
        for retangulo, _origem in tarjas_por_pagina.get(i, []):
            desenho.rectangle(
                [round(retangulo.x0 * escala), round(retangulo.y0 * escala),
                 round(retangulo.x1 * escala), round(retangulo.y1 * escala)],
                fill=(0, 0, 0))

        h.update(f"{img.width}x{img.height}".encode("utf-8"))
        h.update(img.tobytes())
        h.update(b"\x1e")

        buffer = io.BytesIO()
        # A resolução precisa ir declarada. Sem ela o PIL grava a imagem
        # assumindo 72 DPI, e como a página foi rasterizada em `escala` o
        # papel saía multiplicado pelo mesmo fator: um A4 virava
        # 1190x1684 pt, perto de um A2. O documento censurado é peça dos
        # autos, e peça em papel de tamanho errado é problema de quem for
        # juntá-la.
        img.save(buffer, format="PDF", resolution=72.0 * escala)
        buffer.seek(0)
        temporario = fitz.open("pdf", buffer.read())
        saida.insert_pdf(temporario)
        temporario.close()

    return saida, h.hexdigest()


def salvar_roteiro(roteiro: Roteiro, caminho) -> None:
    Path(caminho).write_text(
        json.dumps(roteiro.dados(), ensure_ascii=False, indent=2),
        encoding="utf-8")


def ler_roteiro(caminho) -> Roteiro:
    return Roteiro.de_dados(
        json.loads(Path(caminho).read_text(encoding="utf-8")))


def reproduzir(roteiro: Roteiro, esperado: str = "") -> tuple:
    """Re-executa o roteiro sobre o original e confere o resultado.

    É a função que dá razão a todo o resto. Responde, por verificação e
    não por afirmação, à única pergunta que importa: quem receber o
    original e este roteiro chega ao mesmo material censurado?

    Devolve (situação, resumo obtido, explicação). A situação é "sim",
    "nao" ou "impossivel" — e a terceira não é a segunda: original que
    sumiu não é censura que não reproduz.
    """
    from .hash_core import sha256_file

    alvo = esperado or roteiro.resumo_conteudo
    caminho = Path(roteiro.origem)
    if not caminho.is_file():
        return "impossivel", "", (
            "o arquivo original não foi encontrado em " + str(caminho))
    try:
        atual = sha256_file(str(caminho))
    except OSError as e:
        return "impossivel", "", f"não foi possível ler o original: {e}"
    if roteiro.resumo_origem and atual != roteiro.resumo_origem:
        return "impossivel", "", (
            "o arquivo original não é mais o mesmo: o resumo atual não "
            "corresponde ao declarado no roteiro")

    try:
        doc = fitz.open(str(caminho))
    except Exception as e:                              # noqa: BLE001
        return "impossivel", "", f"não foi possível abrir o original: {e}"
    try:
        produzido, resumo = compor(doc, roteiro.por_pagina(), roteiro.escala)
        produzido.close()
    finally:
        doc.close()

    if not alvo:
        return "impossivel", resumo, "não há resumo declarado a conferir"
    if resumo == alvo:
        return "sim", resumo, ""
    return "nao", resumo, "o conteúdo produzido não corresponde ao declarado"


def frase_reproducao(situacao: str, explicacao: str = "") -> str:
    """Como a conferência se lê na peça."""
    if situacao == "sim":
        return ("A censura foi re-executada a partir do arquivo original, "
                "pelo roteiro que acompanha esta peça, e reproduziu resumo "
                "de conteúdo idêntico ao declarado. O resultado é, "
                "portanto, conferível por terceiro que disponha do "
                "original e do roteiro.")
    if situacao == "nao":
        return ("A re-execução do roteiro sobre o arquivo original **não** "
                "reproduziu o resumo de conteúdo declarado. Enquanto a "
                "divergência não for esclarecida, o arquivo produzido não "
                "deve ser tratado como resultado deste roteiro.")
    return ("Não foi possível re-executar o roteiro nesta oportunidade"
            + (": " + explicacao if explicacao else "")
            + ". A conferência segue possível por quem disponha do arquivo "
            "original e do roteiro que acompanha esta peça.")
