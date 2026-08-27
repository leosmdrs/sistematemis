"""
Termo de arquivo derivado de outro.

Duas ferramentas produzem um arquivo novo a partir de um existente: a
**Tarja Preta**, que censura dados protegidos, e a **Edição de Vídeo**,
que compacta, fatia ou mescla gravações. Nos dois casos a peça a juntar
aos autos diz a mesma coisa jurídica, e por isso vive aqui uma vez só:

    este arquivo, com este resumo criptográfico, foi produzido a partir
    daquele, com aquele resumo, por esta operação, nesta data, por mim.

O que torna a peça útil é o **par de resumos**. O do original prova de
que arquivo se partiu — e permite conferir, a qualquer tempo, que o
material que está nos autos é o mesmo que se tinha. O do resultado prova
que o arquivo entregue é exatamente o que saiu da operação, e não algo
alterado depois. Sem os dois, o termo seria uma afirmação sobre arquivos
que ninguém consegue identificar.

Por isso o termo só pode ser emitido **depois de gravar** o arquivo
derivado: o resumo é calculado sobre os bytes finais, e antes de existir
arquivo não há bytes a resumir.
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass, field
from pathlib import Path

from .hash_core import ARTIGO_PROCESSO, MESES, sha256_file

#: Cores da peça, iguais às dos demais termos do sistema.
INK = "#16233A"
CINZA = "#5A6B85"


def _do_perfil(campo: str) -> str:
    from .. import perfil
    try:
        return getattr(perfil.ler(), campo, "") or ""
    except Exception:                                       # noqa: BLE001
        return ""


def cargo_padrao() -> str:
    return _do_perfil("cargo")


def orgao_padrao() -> str:
    return _do_perfil("orgao")


def formatar_tamanho(n: int) -> str:
    if n <= 0:
        return "—"
    for unidade in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unidade == "GB":
            return (f"{n} {unidade}" if unidade == "bytes"
                    else f"{n:.1f} {unidade}".replace(".", ","))
        n /= 1024
    return f"{n:.1f} GB"


@dataclass
class Arquivo:
    """Um arquivo identificado pelo que ele é, não por onde está."""

    caminho: str = ""
    resumo: str = ""
    tamanho: int = 0
    erro: str = ""

    @property
    def nome(self) -> str:
        return Path(self.caminho).name if self.caminho else ""


def ler(caminho) -> Arquivo:
    """Mede um arquivo. Falha em ler não impede o termo de existir.

    Um termo que não aparece é pior do que um termo que declara não ter
    conseguido ler um dos arquivos — este segundo, ao menos, diz o que
    houve, e quem o lê decide o que fazer.
    """
    a = Arquivo(caminho=str(caminho))
    try:
        a.tamanho = Path(caminho).stat().st_size
        a.resumo = sha256_file(caminho)
    except OSError as e:
        a.erro = f"{type(e).__name__}: {e}"
    return a


@dataclass
class Derivacao:
    """Um arquivo produzido a partir de um ou mais outros.

    Mais de uma origem não é exceção: mesclar vídeos junta vários num só,
    e o termo precisa identificar cada um pelo resumo — senão a peça
    diria que o resultado veio "de uns arquivos", o que não amarra coisa
    alguma.
    """

    origens: list[Arquivo] = field(default_factory=list)
    saida: Arquivo = field(default_factory=Arquivo)
    #: Pares (rótulo, valor) próprios da operação — o que foi censurado,
    #: o trecho recortado, o preset de compactação. Cada ferramenta enche
    #: com o que só ela sabe.
    detalhes: list[tuple[str, str]] = field(default_factory=list)

    @property
    def erros(self) -> list[str]:
        return [f"{a.nome}: {a.erro}"
                for a in [*self.origens, self.saida] if a.erro]


def medir(origens, saida, detalhes=None) -> Derivacao:
    """Lê tamanho e resumo da origem (ou origens) e do resultado."""
    if isinstance(origens, (str, Path)):
        origens = [origens]
    return Derivacao(origens=[ler(o) for o in origens], saida=ler(saida),
                     detalhes=list(detalhes or []))


@dataclass
class TermoDerivado:
    """A peça, com quem assina e o que foi feito."""

    #: Título impresso e frase que abre o corpo — cada ferramenta traz os
    #: seus, porque a operação é que dá nome à peça.
    titulo: str = "Termo de Arquivo Derivado"
    operacao: str = "processamento"
    #: Parágrafos que descrevem o alcance e os limites da operação.
    ressalvas: tuple[str, ...] = ()

    nome: str = ""
    cargo: str = field(default_factory=cargo_padrao)
    matricula: str = ""
    lotacao: str = ""
    orgao: str = field(default_factory=orgao_padrao)
    tipo_processo: str = "IPS"
    numero_processo: str = ""
    dia: int = 1
    mes: int = 1
    ano: int = 2026

    itens: list[Derivacao] = field(default_factory=list)

    @property
    def quantos(self) -> int:
        return len(self.itens)


def _com_cargo(t: TermoDerivado) -> str:
    partes = (t.cargo.strip(), t.nome.strip())
    return " ".join(p for p in partes if p)


def intro(t: TermoDerivado) -> str:
    mes = MESES[t.mes - 1] if 1 <= t.mes <= 12 else ""
    quando = (f"Ao {t.dia}º dia do mês de {mes} de {t.ano}" if t.dia == 1
              else f"Aos {t.dia} dias do mês de {mes} de {t.ano}")
    artigo = ARTIGO_PROCESSO.get(t.tipo_processo, "do")
    quantos = ("do arquivo abaixo relacionado" if t.quantos == 1
               else f"dos {t.quantos} arquivos abaixo relacionados")
    return (
        f"{quando}, eu, {_com_cargo(t)}, matrícula {t.matricula}, "
        f"lotado(a) no(a) {t.lotacao}, visando instruir os autos "
        f"{artigo} {t.tipo_processo} nº {t.numero_processo}, declaro que "
        f"procedi ao {t.operacao} {quantos}, cujos resumos criptográficos "
        f"antes e depois da operação ficam adiante consignados."
    )


ENCERRAMENTO = (
    "Os resumos criptográficos acima permitem conferir, a qualquer tempo, "
    "tanto a integridade do arquivo original quanto a do arquivo "
    "produzido. Sem mais a relatar, encerro o presente termo."
)


def _quadro(d: Derivacao, numero: int) -> str:
    e = _html.escape

    def linha(rotulo, valor, mono=False):
        estilo = ("font-family:Consolas,monospace; font-size:9pt;"
                  if mono else "font-size:10.5pt;")
        return (f'<tr><td width="30%" valign="top">'
                f'<font color="{CINZA}" size="2">{e(rotulo)}</font></td>'
                f'<td><span style="{estilo}">{e(str(valor))}</span></td></tr>')

    linhas = []
    varias = len(d.origens) > 1
    for i, o in enumerate(d.origens, 1):
        rotulo = f"Arquivo original {i}" if varias else "Arquivo original"
        linhas.append(linha(rotulo, o.nome or "—"))
        linhas.append(linha("Tamanho", formatar_tamanho(o.tamanho)))
        linhas.append(linha("SHA-256", o.resumo or "não foi possível ler",
                            mono=True))
    linhas.append(linha("Arquivo produzido", d.saida.nome or "—"))
    linhas.append(linha("Tamanho do produzido",
                        formatar_tamanho(d.saida.tamanho)))
    linhas.append(linha("SHA-256 do produzido",
                        d.saida.resumo or "não foi possível ler", mono=True))
    linhas += [linha(rotulo, valor) for rotulo, valor in d.detalhes]
    for falha in d.erros:
        linhas.append(linha("Falha na leitura", falha))

    return (
        f'<p style="font-size:11pt; margin-top:14px;">'
        f'<b><font color="{INK}">{numero}. {e(d.saida.nome or "arquivo")}'
        f"</font></b></p>"
        '<table width="100%" cellspacing="0" cellpadding="5" border="1" '
        'style="border-collapse:collapse;">' + "".join(linhas) + "</table>"
    )


#: Nome público do quadro de arquivos. A Análise de Planilha monta uma
#: peça própria — com o roteiro no meio —, mas o quadro que identifica
#: original e resultado é o mesmo, e duplicá-lo faria as duas peças
#: divergirem com o tempo.
quadro_de_arquivos = _quadro


def build_html(t: TermoDerivado) -> str:
    """A peça em HTML, para exibir e exportar."""
    from ..impressao import cabecalho_html

    e = _html.escape
    partes = [
        "<html><body style=\"font-family:'Segoe UI',Arial,sans-serif; "
        'color:#16233a;">',
        cabecalho_html(),
        '<div align="center" style="margin-bottom:18px;">'
        f'<b style="font-size:14pt; letter-spacing:0.5px;">{e(t.titulo)}'
        "</b></div>",
        "<hr/>",
        f'<p align="justify" style="font-size:11pt; line-height:160%;">'
        f"{e(intro(t))}</p>",
    ]

    for i, d in enumerate(t.itens, 1):
        partes.append(_quadro(d, i))

    if t.ressalvas:
        partes.append(
            f'<p style="font-size:11pt; margin-top:18px;">'
            f'<b><font color="{INK}">Alcance e limites da operação</font></b>'
            "</p>")
        partes += [
            f'<p align="justify" style="font-size:10pt; line-height:150%;">'
            f'<font color="{INK}">{e(x)}</font></p>' for x in t.ressalvas]

    partes.append(
        f'<p align="justify" style="font-size:11pt; line-height:160%; '
        f'margin-top:16px;">{e(ENCERRAMENTO)}</p>')

    partes.append(
        '<p align="center" style="margin-top:38px; font-size:11pt;">'
        "______________________________________<br/>"
        f"<b>{e(t.nome)}</b><br/>"
        + (f'<span style="font-size:10pt;">{e(t.cargo)}</span><br/>'
           if t.cargo.strip() else "")
        + (f'<span style="font-size:10pt;">Matrícula {e(t.matricula)}</span>'
           if t.matricula.strip() else "")
        + "</p>")

    partes.append("</body></html>")
    return "".join(partes)


def build_texto(t: TermoDerivado) -> str:
    """A mesma peça em texto puro, para colar onde não se aceita HTML."""
    L = [t.titulo.upper(), "", intro(t), ""]
    for i, d in enumerate(t.itens, 1):
        L.append(f"{i}. {d.saida.nome or 'arquivo'}")
        varias = len(d.origens) > 1
        for j, o in enumerate(d.origens, 1):
            rotulo = f"Arquivo original {j}" if varias else "Arquivo original"
            L.append(f"   {rotulo}: {o.nome}")
            L.append(f"      Tamanho: {formatar_tamanho(o.tamanho)}")
            L.append(f"      SHA-256: {o.resumo or '—'}")
        L.append(f"   Arquivo produzido: {d.saida.nome}")
        L.append(f"      Tamanho: {formatar_tamanho(d.saida.tamanho)}")
        L.append(f"      SHA-256: {d.saida.resumo or '—'}")
        for rotulo, valor in d.detalhes:
            L.append(f"   {rotulo}: {valor}")
        for falha in d.erros:
            L.append(f"   Falha na leitura: {falha}")
        L.append("")
    if t.ressalvas:
        L.append("ALCANCE E LIMITES DA OPERAÇÃO")
        L += [f"- {x}" for x in t.ressalvas]
        L.append("")
    L += [ENCERRAMENTO, "", "_" * 40, t.nome]
    if t.cargo.strip():
        L.append(t.cargo)
    if t.matricula.strip():
        L.append(f"Matrícula {t.matricula}")
    return "\n".join(L)
