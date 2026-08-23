"""
Motor de detecção de texto oculto em PDFs.

Sem nenhuma dependência de interface: recebe um documento e devolve
achados, para poder ser testado isoladamente.

A varredura usa `page.get_texttrace()`, que expõe o estado gráfico real de
cada trecho — opacidade, modo de renderização, cor, corpo e camada. É por
isso que a detecção aqui alcança casos que um extrator de texto comum não
enxerga: `get_text()` devolveria a mesma string para um trecho visível e
para um trecho com opacidade zero.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import fitz


# ─────────────────────────────────────────
#  HEURÍSTICAS
# ─────────────────────────────────────────

#: Abaixo disto o trecho é tido como transparente.
OPACITY_MAX = 0.05

#: Corpo, em pontos, abaixo do qual o texto é ilegível a olho nu.
#: 1,5 pt equivale a cerca de meio milímetro de altura.
SIZE_MIN = 1.5

#: Luminância a partir da qual a cor é praticamente branca.
LUMA_WHITE = 0.95

#: Fração do trecho que precisa estar dentro da página para valer como visível.
INSIDE_MIN = 0.20

SEVERITIES = ("critica", "atencao", "baixa")

SEVERITY_LABEL = {
    "critica": "Crítica",
    "atencao": "Atenção",
    "baixa":   "Baixa",
}

HEURISTICS = {
    "H1": ("opacidade zero",        "atencao"),
    "H2": ("corpo minúsculo",       "atencao"),
    "H3": ("fora da página",        "baixa"),
    "H4": ("branco sobre branco",   "atencao"),
    "H5": ("camada oculta",         "baixa"),
    "H6": ("renderização invisível", "atencao"),
}

#: Expressões típicas de tentativa de manipulação de quem lê o documento —
#: seja o servidor, seja um assistente de IA que resuma os autos. Um trecho
#: oculto que as contenha deixa de ser anomalia e passa a ser instrução
#: dirigida, por isso escala a severidade para crítica.
INJECTION_PATTERNS = [
    r"ignor[ae]\s+(?:as\s+|todas\s+as\s+)?instru[çc]",
    r"desconsider[ae]\s+(?:as\s+|o\s+|todo)",
    r"recomend[ae]\s+o\s+arquivamento",
    r"arquivamento\s+imediato",
    r"conclu[ai]\s+que",
    r"respond[ae]\s+(?:apenas\s+)?que",
    r"n[ãa]o\s+mencion[ae]",
    r"n[ãa]o\s+cite",
    r"aja\s+como",
    r"voc[êe]\s+[ée]\s+(?:um|uma)\b",
    r"nov[ao]s?\s+instru[çc][õo]es",
    r"ignore\s+(?:all\s+)?(?:previous|prior|above)",
    r"disregard\s+(?:all\s+)?(?:previous|prior|above)",
    r"system\s+prompt",
    r"you\s+are\s+(?:now\s+)?(?:a|an)\b",
    r"new\s+instructions?",
    r"act\s+as\b",
    r"do\s+not\s+mention",
    r"override",
]

_INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


# ─────────────────────────────────────────
#  ACHADO
# ─────────────────────────────────────────

@dataclass
class Finding:
    page: int                       # índice 0-based
    codes: list[str]                # heurísticas acionadas, ex. ["H1", "H6"]
    severity: str                   # critica | atencao | baixa
    text: str                       # o texto oculto
    bbox: fitz.Rect                 # posição na página
    details: list[str] = field(default_factory=list)
    injection: bool = False         # contém instrução dirigida

    @property
    def code_label(self) -> str:
        return " + ".join(self.codes)

    @property
    def severity_label(self) -> str:
        return SEVERITY_LABEL[self.severity]

    @property
    def reason(self) -> str:
        return " · ".join(HEURISTICS[c][0] for c in self.codes)

    def preview(self, limit: int = 160) -> str:
        t = " ".join(self.text.split())
        return t if len(t) <= limit else t[:limit - 1] + "…"


# ─────────────────────────────────────────
#  APOIO
# ─────────────────────────────────────────

def _span_text(span: dict) -> str:
    """Reconstrói o texto de um span de get_texttrace()."""
    return "".join(chr(c[0]) for c in span.get("chars", ()))


def _luma(color) -> float:
    """Luminância percebida de uma cor RGB normalizada."""
    if not color or len(color) < 3:
        return 0.0
    r, g, b = color[0], color[1], color[2]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _inside_fraction(bbox: fitz.Rect, page_rect: fitz.Rect) -> float:
    """Fração da área do trecho que cai dentro da página."""
    if bbox.is_empty or bbox.is_infinite:
        return 1.0
    area = abs(bbox.get_area())
    if area <= 0:
        # Trecho degenerado (altura ou largura zero): decide pelo ponto inicial.
        return 1.0 if page_rect.contains(fitz.Point(bbox.x0, bbox.y0)) else 0.0
    inter = bbox & page_rect
    return abs(inter.get_area()) / area if not inter.is_empty else 0.0


def _dark_backdrop(page: fitz.Page, bbox: fitz.Rect, drawings) -> bool:
    """Há uma forma escura preenchida atrás deste trecho?

    Sem esta checagem, texto branco sobre uma tarja ou cabeçalho escuro —
    perfeitamente legível — seria acusado de 'branco sobre branco'.
    """
    for d in drawings:
        fill = d.get("fill")
        if fill is None:
            continue
        if _luma(fill) > 0.5:
            continue
        rect = d.get("rect")
        if rect is not None and rect.contains(bbox):
            return True
    return False


def hidden_layer_configs(doc: fitz.Document) -> list[dict]:
    """Camadas (OCG) atualmente desligadas no documento."""
    try:
        return [c for c in doc.layer_ui_configs() if not c.get("on")]
    except Exception:
        # Documento sem camadas: nada a esconder.
        return []


def hidden_layer_names(doc: fitz.Document) -> list[str]:
    return [c.get("text", "") for c in hidden_layer_configs(doc) if c.get("text")]


def _span_key(span: dict, text: str) -> tuple:
    """Identidade de um trecho, para comparar duas extrações da mesma página."""
    b = span.get("bbox", (0, 0, 0, 0))
    return (round(b[0], 1), round(b[1], 1), round(b[2], 1), text)


# ─────────────────────────────────────────
#  ANÁLISE
# ─────────────────────────────────────────

def analyze_page(page: fitz.Page, baseline_keys: set | None = None,
                 layer_note: str = "") -> list[Finding]:
    """Devolve os achados de texto oculto de uma página.

    `baseline_keys` são os trechos que a página exibia com as camadas no
    estado original. Quando informado, todo trecho fora desse conjunto só
    apareceu porque as camadas foram forçadas — ou seja, estava oculto.
    """
    page_rect = page.rect
    findings: list[Finding] = []

    try:
        spans = page.get_texttrace()
    except Exception:
        return findings

    drawings = None   # só carregado se algum trecho for branco

    for span in spans:
        text = _span_text(span)
        if not text.strip():
            continue

        codes: list[str] = []
        details: list[str] = []

        opacity = span.get("opacity", 1.0)
        size = span.get("size", 0.0)
        color = span.get("color")
        layer = span.get("layer") or ""
        stype = span.get("type", 0)
        bbox = fitz.Rect(span.get("bbox", (0, 0, 0, 0)))

        if opacity is not None and opacity <= OPACITY_MAX:
            codes.append("H1")
            details.append(f"opacidade {opacity:.2f}")

        if 0 < size < SIZE_MIN:
            codes.append("H2")
            details.append(f"corpo {size:.2f} pt".replace(".", ","))

        inside = _inside_fraction(bbox, page_rect)
        if inside < INSIDE_MIN:
            codes.append("H3")
            details.append(f"{(1 - inside) * 100:.0f}% fora da área da página")

        if _luma(color) >= LUMA_WHITE:
            if drawings is None:
                try:
                    drawings = page.get_drawings()
                except Exception:
                    drawings = []
            if not _dark_backdrop(page, bbox, drawings):
                codes.append("H4")
                details.append("cor praticamente branca, sem fundo escuro atrás")

        if baseline_keys is not None and _span_key(span, text) not in baseline_keys:
            codes.append("H5")
            details.append(
                f"conteúdo em camada não exibida{layer_note}"
                if not layer else f"camada “{layer}” desligada"
            )

        if stype == 3:
            codes.append("H6")
            details.append("modo de renderização invisível (Tr 3)")

        if not codes:
            continue

        injection = bool(_INJECTION_RE.search(text))
        severity = "critica" if injection else min(
            (HEURISTICS[c][1] for c in codes),
            key=lambda s: SEVERITIES.index(s),
        )

        findings.append(Finding(
            page=page.number,
            codes=codes,
            severity=severity,
            text=text,
            bbox=bbox,
            details=details,
            injection=injection,
        ))

    return findings


def analyze_document(doc: fitz.Document, progress=None) -> list[Finding]:
    """Varre o documento inteiro. `progress(atual, total)` é opcional.

    Se houver camadas desligadas, o MuPDF simplesmente não devolve o texto
    delas — nem em `get_texttrace()`, nem em `get_text()`. Para enxergar
    esse conteúdo é preciso registrar o que a página exibe no estado
    original, ligar as camadas, extrair de novo e comparar. O estado é
    restaurado ao final, de modo que o documento em memória fica como
    estava.
    """
    total = len(doc)
    hidden_cfgs = hidden_layer_configs(doc)

    baseline: dict[int, set] = {}
    layer_note = ""
    if hidden_cfgs:
        names = [c.get("text", "") for c in hidden_cfgs if c.get("text")]
        if len(names) == 1:
            layer_note = f" (“{names[0]}”)"

        for i in range(total):
            try:
                baseline[i] = {
                    _span_key(s, _span_text(s)) for s in doc[i].get_texttrace()
                }
            except Exception:
                baseline[i] = set()

        for c in hidden_cfgs:
            try:
                doc.set_layer_ui_config(c["number"], action=1)
            except Exception:
                pass

    try:
        out: list[Finding] = []
        for i in range(total):
            if progress:
                progress(i + 1, total)
            out.extend(analyze_page(
                doc[i],
                baseline_keys=baseline.get(i) if hidden_cfgs else None,
                layer_note=layer_note,
            ))
        return out
    finally:
        for c in hidden_cfgs:
            try:
                doc.set_layer_ui_config(c["number"], action=2)
            except Exception:
                pass


def summarize(findings: list[Finding]) -> dict:
    """Contagens por severidade e nº de páginas afetadas."""
    return {
        "total": len(findings),
        "critica": sum(1 for f in findings if f.severity == "critica"),
        "atencao": sum(1 for f in findings if f.severity == "atencao"),
        "baixa": sum(1 for f in findings if f.severity == "baixa"),
        "paginas": len({f.page for f in findings}),
    }


# ─────────────────────────────────────────
#  RELATÓRIO
# ─────────────────────────────────────────

_EXTENSO = {
    1: "um", 2: "dois", 3: "três", 4: "quatro", 5: "cinco", 6: "seis",
    7: "sete", 8: "oito", 9: "nove", 10: "dez",
}


def _n(n: int) -> str:
    """'3 (três)' quando houver extenso conhecido."""
    return f"{n} ({_EXTENSO[n]})" if n in _EXTENSO else str(n)


SEVERITY_INK = {
    "critica": "#B3261E",
    "atencao": "#9A6B00",
    "baixa":   "#1B4B85",
}

#: Tinta única do corpo do documento. Vai explícita em cada célula porque
#: o motor de texto do Qt não propaga a cor do <body> para dentro da tabela.
INK = "#16233A"


@dataclass
class Declarante:
    """Quem assina a constatação."""
    nome: str = ""
    matricula: str = ""
    lotacao: str = ""
    cargo: str = "Policial Rodoviário Federal"


def build_html(file_name: str, n_pages: int, findings: list[Finding],
               when: str, decl: Declarante | None = None) -> str:
    """Relatório de constatação em HTML, para exibir e exportar em PDF."""
    import html as _html

    e = _html.escape
    decl = decl or Declarante()
    s = summarize(findings)

    ordenados = sorted(findings, key=lambda x: (x.page, x.bbox.y0))

    if findings:
        frase = (
            f"Foram identificados <b>{_n(s['total'])}</b> trecho(s) de texto "
            f"não visíveis à leitura convencional, distribuídos em "
            f"{_n(s['paginas'])} página(s)"
        )
        if s["critica"]:
            frase += (f", sendo <b>{_n(s['critica'])}</b> de severidade "
                      f"<b>CRÍTICA</b>")
        frase += ", conforme o quadro abaixo."
    else:
        frase = ("<b>Não foram identificados</b> trechos de texto ocultos à "
                 "leitura convencional no documento examinado.")

    linhas = []
    for i, f in enumerate(ordenados, 1):
        detalhes = "; ".join(f.details)
        if f.injection:
            detalhes += ("; contém instrução dirigida ao leitor do documento"
                         if detalhes else
                         "contém instrução dirigida ao leitor do documento")
        linhas.append(
            "<tr>"
            f'<td align="center"><font color="{INK}">{i}</font></td>'
            f'<td align="center"><font color="{INK}">{f.page + 1}</font></td>'
            f'<td align="center"><font color="{SEVERITY_INK[f.severity]}">'
            f"<b>{e(f.severity_label.upper())}</b></font></td>"
            f'<td align="center"><font color="{INK}">{e(f.code_label)}</font></td>'
            f'<td><font color="{INK}">{e(f.reason)}<br/>'
            f'<font size="1" color="#5B6B82">{e(detalhes)}</font></font></td>'
            f'<td><font color="{INK}" face="Courier New" size="1">'
            f"{e(f.preview(220))}</font></td>"
            "</tr>"
        )

    tabela = f"""
<table width="100%" cellspacing="0" cellpadding="5" border="1"
       style="border-collapse:collapse; font-size:9pt;">
  <tr style="background-color:#0A2442; color:#FFD633;">
    <th width="4%">Nº</th>
    <th width="6%">Pág.</th>
    <th width="11%">Severidade</th>
    <th width="8%">Heur.</th>
    <th width="26%">Motivo da ocultação</th>
    <th width="45%">Conteúdo oculto</th>
  </tr>
  {''.join(linhas)}
</table>
""" if findings else ""

    assinatura = ""
    if decl.nome:
        vinculo = " · ".join(x for x in (
            f"matrícula {e(decl.matricula)}" if decl.matricula else "",
            e(decl.lotacao) if decl.lotacao else "",
        ) if x)
        assinatura = f"""
<div align="center" style="margin-top:40px;">
  ______________________________________<br/>
  <b><font color="{INK}">{e(decl.nome)}</font></b><br/>
  <font color="{INK}" size="2">{e(decl.cargo)}</font>
  {f'<br/><font color="#5B6B82" size="1">{vinculo}</font>' if vinculo else ''}
</div>
"""

    return f"""
<html><body style="font-family:'Segoe UI',Arial,sans-serif; color:{INK};">
<div align="center" style="margin-bottom:16px;">
  <b style="font-size:14pt; letter-spacing:0.5px;">Relatório de Constatação de Texto Oculto em Documento PDF</b>
</div>
<hr/>
<table width="100%" cellspacing="0" cellpadding="4" style="font-size:10pt;">
  <tr><td width="24%"><font color="#5B6B82">Arquivo examinado</font></td>
      <td><b><font color="{INK}">{e(file_name)}</font></b>
          <font color="#5B6B82">({_n(n_pages)} página(s))</font></td></tr>
  <tr><td><font color="#5B6B82">Data da análise</font></td>
      <td><font color="{INK}">{e(when)}</font></td></tr>
  <tr><td><font color="#5B6B82">Processamento</font></td>
      <td><font color="{INK}">Local, sem envio do arquivo a terceiros</font></td></tr>
</table>
<p align="justify" style="font-size:11pt; line-height:160%;">{frase}</p>
{tabela}
<p align="justify" style="font-size:10pt; line-height:150%; margin-top:16px;">
A constatação foi realizada por inspeção do estado gráfico de cada trecho de
texto do arquivo — opacidade, modo de renderização, cor, corpo da fonte,
posição e camada —, sem qualquer alteração do documento original.
</p>
<p align="justify" style="font-size:11pt; margin-top:14px;">
Sem mais a relatar, encerro o presente relatório.
</p>
{assinatura}
</body></html>
"""


def build_report(file_name: str, n_pages: int, findings: list[Finding],
                 when: str) -> str:
    """Monta o relatório de constatação, pronto para juntar aos autos."""
    s = summarize(findings)
    L: list[str] = []
    L.append("CONSTATAÇÃO DE TEXTO OCULTO EM DOCUMENTO PDF")
    L.append("")
    L.append(f'Arquivo: "{file_name}" ({_n(n_pages)} página(s))')
    L.append(f"Data da análise: {when} — processamento local")
    L.append("")

    if not findings:
        L.append("Não foram identificados trechos de texto ocultos à leitura")
        L.append("convencional no documento examinado.")
        return "\n".join(L)

    frase = (
        f"Foram identificados {_n(s['total'])} trecho(s) de texto não "
        f"visíveis à leitura convencional, distribuídos em "
        f"{_n(s['paginas'])} página(s)"
    )
    if s["critica"]:
        frase += f", sendo {_n(s['critica'])} de severidade CRÍTICA"
    L.append(frase + ".")
    L.append("")

    for i, f in enumerate(sorted(findings, key=lambda x: (x.page, x.bbox.y0)), 1):
        L.append(f"{i}. Página {f.page + 1} — {f.severity_label.upper()} "
                 f"[{f.code_label}: {f.reason}]")
        for d in f.details:
            L.append(f"   • {d}")
        if f.injection:
            L.append("   • contém instrução dirigida ao leitor do documento")
        L.append("   Conteúdo:")
        for line in (" ".join(f.text.split()),):
            L.append(f'     "{line}"')
        L.append("")

    L.append("A constatação foi realizada por inspeção do estado gráfico de")
    L.append("cada trecho de texto do arquivo (opacidade, modo de")
    L.append("renderização, cor, corpo da fonte, posição e camada), sem")
    L.append("alteração do documento original.")
    return "\n".join(L)
