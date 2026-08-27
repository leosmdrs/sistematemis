"""
Cálculo de hash e montagem do Termo de Juntada.

Sem dependência de interface, para poder ser testado isoladamente.
"""

from __future__ import annotations

import hashlib
import html
from dataclasses import dataclass, field
from pathlib import Path

MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

#: Contração do artigo conforme o tipo: "da IPS" (sindicância), "do PAD".
ARTIGO_PROCESSO = {"IPS": "da", "PAD": "do"}

TIPOS_PROCESSO = ("IPS", "PAD")

#: Blocos de leitura. O original lia o arquivo inteiro na memória, o que
#: inviabiliza vídeos e imagens forenses de vários gigabytes.
CHUNK = 1024 * 1024


# ─────────────────────────────────────────
#  ARQUIVO
# ─────────────────────────────────────────

#: Cargo e órgão de quem assina.
#:
#: Vinham escritos no código, como "Policial Rodoviário Federal": o
#: sistema nasceu na PRF, mas não é dela. Agora saem da Identificação
#: guardada na estação, e continuam editáveis no próprio termo — o campo
#: da tela vale mais que a configuração, sempre.
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


def _com_cargo(t) -> str:
    """"Cargo Nome", ou só o nome quando não há cargo informado.

    Sem isto, quem não preenchesse o cargo teria termos abrindo com "eu,
    ,  Fulano" — dois espaços e uma vírgula órfã numa peça que vai ao
    processo.
    """
    cargo = (getattr(t, "cargo", "") or "").strip()
    nome = (getattr(t, "nome", "") or "").strip()
    return " ".join(x for x in (cargo, nome) if x)


@dataclass
class FileEntry:
    path: str
    size: int = 0
    hash: str = ""
    sei: str = ""
    error: str = ""

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def ready(self) -> bool:
        return bool(self.hash)


def format_size(n: int) -> str:
    """Tamanho legível. Inclui a faixa de GB, ausente no original."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.2f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


def sha256_file(path: str, progress=None, should_stop=None) -> str:
    """SHA-256 em blocos.

    `progress(lidos, total)` acompanha arquivos grandes; `should_stop()`
    permite cancelar sem esperar o arquivo inteiro.
    """
    h = hashlib.sha256()
    total = Path(path).stat().st_size
    read = 0
    with open(path, "rb") as fh:
        while True:
            if should_stop and should_stop():
                return ""
            block = fh.read(CHUNK)
            if not block:
                break
            h.update(block)
            read += len(block)
            if progress:
                progress(read, total)
    return h.hexdigest()


# ─────────────────────────────────────────
#  TERMO
# ─────────────────────────────────────────

@dataclass
class TermoData:
    nome: str = ""
    matricula: str = ""
    lotacao: str = ""
    cargo: str = field(default_factory=cargo_padrao)
    orgao: str = field(default_factory=orgao_padrao)
    tipo_processo: str = "IPS"
    numero_processo: str = ""
    dia: int = 1
    mes: int = 1
    ano: int = 2026
    arquivos: list[FileEntry] = field(default_factory=list)
    #: Chaves de `procedencia.MOTORES`. Ver `TermoDerivado.motores`.
    motores: tuple[str, ...] = ()


def build_intro(d: TermoData) -> str:
    """Parágrafo de abertura do termo.

    Mantém o texto do sistema original, com uma correção de concordância:
    no dia 1 o original produzia "Aos 1 dias do mês de…".
    """
    artigo = ARTIGO_PROCESSO.get(d.tipo_processo, "da")
    mes = MESES[d.mes - 1]
    quando = (
        f"Ao 1º dia do mês de {mes} de {d.ano}" if d.dia == 1
        else f"Aos {d.dia} dias do mês de {mes} de {d.ano}"
    )
    return (
        f"{quando}, eu, {_com_cargo(d)}, matrícula {d.matricula}, "
        f"lotado(a) no(a) {d.lotacao}, visando instruir os autos "
        f"{artigo} {d.tipo_processo} nº {d.numero_processo}, declaro que "
        f"foi realizada a juntada dos arquivos abaixo."
    )


ENCERRAMENTO = "Sem mais a relatar, encerro o presente termo."


def build_html(d: TermoData) -> str:
    """Termo em HTML, para exibir e exportar em PDF."""
    from ..impressao import cabecalho_html, rodape_html
    e = html.escape
    # A cor vai explícita em cada célula: o motor de texto do Qt não
    # propaga o `color` do <body> para dentro da tabela, e ainda trata
    # "relatorio.pdf" como hiperlink, pintando os nomes de azul.
    INK = "#16233A"
    rows = []
    for i, f in enumerate(d.arquivos, 1):
        rows.append(
            "<tr>"
            f'<td align="center"><font color="{INK}">{i}</font></td>'
            f'<td><font color="{INK}">{e(f.name)}</font></td>'
            f'<td align="center"><font color="{INK}">{e(format_size(f.size))}</font></td>'
            f'<td><font color="{INK}" face="Courier New" size="1">{e(f.hash)}</font></td>'
            f'<td><font color="{INK}">{e(f.sei)}</font></td>'
            "</tr>"
        )

    return f"""
<html><body style="font-family:'Segoe UI',Arial,sans-serif; color:#16233a;">
{cabecalho_html()}
<div align="center" style="margin-bottom:18px;">
  <b style="font-size:14pt; letter-spacing:0.5px;">Termo de Juntada de Arquivo(s) Digital(is)</b>
</div>
<hr/>
<p align="justify" style="font-size:11pt; line-height:160%;">{e(build_intro(d))}</p>
<table width="100%" cellspacing="0" cellpadding="5" border="1"
       style="border-collapse:collapse; font-size:9pt;">
  <tr style="background-color:#0a2442; color:#ffd633;">
    <th width="4%">Nº</th>
    <th width="30%">Nome do Arquivo</th>
    <th width="10%">Tamanho</th>
    <th width="40%">Hash SHA-256</th>
    <th width="16%">Nº SEI!</th>
  </tr>
  {''.join(rows)}
</table>
<p align="justify" style="font-size:11pt; margin-top:18px;">{ENCERRAMENTO}</p>
{rodape_html(*d.motores)}
<br/><br/>
<div align="center" style="margin-top:36px;">
  ______________________________________<br/>
  <b>{e(d.nome)}</b><br/>
  <span style="font-size:10pt;">{e(d.cargo)}</span>
</div>
</body></html>
"""


def build_text(d: TermoData) -> str:
    """Termo em texto puro, para colar no SEI."""
    L = [
        "TERMO DE JUNTADA DE ARQUIVO(S) DIGITAL(IS)",
        "",
        build_intro(d),
        "",
    ]
    for i, f in enumerate(d.arquivos, 1):
        L.append(f"{i}. {f.name}  ({format_size(f.size)})")
        L.append(f"   SHA-256: {f.hash}")
        if f.sei:
            L.append(f"   Nº SEI: {f.sei}")
        L.append("")
    L.append(ENCERRAMENTO)
    L.append("")
    from ..impressao import rodape_texto
    L.append(rodape_texto(*d.motores))
    L.append("")
    L.append("_" * 40)
    L.append(d.nome)
    if d.cargo.strip():
        L.append(d.cargo)
    return "\n".join(L)


def validate(d: TermoData) -> list[str]:
    """Campos obrigatórios que ficaram em branco."""
    faltando = []
    for valor, rotulo in (
        (d.nome, "Nome completo"),
        (d.matricula, "Matrícula"),
        (d.lotacao, "Lotação"),
        (d.numero_processo, "Número do processo"),
    ):
        if not valor.strip():
            faltando.append(rotulo)
    if not d.arquivos:
        faltando.append("Pelo menos um arquivo")
    return faltando
