"""
Modelo, persistência e exportação da Informação de IPS.

Sem dependência de interface, para poder ser testado isoladamente.

As seções que compõem o documento são **dados**, não código: estão em
`SECOES`, e acrescentar ou reordenar uma parte é mexer nessa lista. A
ferramenta monta sozinha o roteiro, o progresso e o documento final a
partir dela.
"""

from __future__ import annotations

import html
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path

from ..impressao import limpar_para_sei as _limpar_para_sei
from . import ips_blocos as blocos
from . import ips_modelo as modelo


def _novo_id() -> str:
    return uuid.uuid4().hex


# ─────────────────────────────────────────
#  SEÇÕES DA INFORMAÇÃO
# ─────────────────────────────────────────

def _do_perfil(campo: str) -> str:
    """Lê um campo da Identificação guardada; vazio se não houver."""
    from .. import perfil
    try:
        return getattr(perfil.ler(), campo, "") or ""
    except Exception:                                       # noqa: BLE001
        return ""


@dataclass(frozen=True)
class Campo:
    """Um dado isolado dentro de uma parte.

    Partes cuja formatação é fixa — como as Iniciais — não devem ser
    escritas à mão num editor livre: o encarregado teria de acertar o
    recuo e o negrito a cada documento. Aqui ele informa só o conteúdo, e
    a diagramação sai sempre igual.
    """

    id: str
    rotulo: str
    tipo: str = "linha"         # linha | paragrafo
    exemplo: str = ""
    padrao: str = ""
    ajuda: str = ""


@dataclass(frozen=True)
class Secao:
    """Uma parte do documento, com o roteiro e o respaldo normativo."""

    id: str
    titulo: str                 # como sai no documento, por extenso
    resumo: str                 # uma linha, no cabeçalho do editor
    #: Nome curto na lista de etapas. Ali o que serve é reconhecer a
    #: etapa de relance; o título por extenso fica para o documento.
    rotulo: str = ""
    esqueleto: str = ""         # HTML inicial, quando é editor livre
    orientacao: str = ""        # o que se espera desta parte
    norma: str = ""             # dispositivo da instrução normativa
    texto_norma: str = ""       # transcrição do dispositivo
    obrigatoria: bool = True
    numerada: bool = True       # entra na numeração do documento
    #: Quando preenchido, a parte vira um formulário em vez de um editor.
    campos: tuple[Campo, ...] = ()
    #: Parágrafos que a parte já traz montados, na abertura.
    blocos_padrao: tuple[dict, ...] = ()

    @property
    def por_campos(self) -> bool:
        return bool(self.campos)

    @property
    def nome_curto(self) -> str:
        return self.rotulo or self.titulo


#: Partes da Informação, na ordem em que saem no documento.
#:
#: EM CONSTRUÇÃO — a Fase 1 (Iniciais) está definida. As demais partes e o
#: texto da instrução normativa entram acrescentando itens a esta lista.
SECOES: list[Secao] = [
    Secao(
        id="iniciais",
        titulo="Iniciais",
        resumo="Assunto, ementa e destinatário",
        numerada=False,     # abre o documento, antes da numeração
        campos=(
            Campo(
                id="assunto",
                rotulo="Assunto",
                tipo="linha",
                padrao="Disciplinar.",
                exemplo="Disciplinar.",
                ajuda="Costuma ser apenas “Disciplinar.”",
            ),
            Campo(
                id="ementa",
                rotulo="Ementa",
                tipo="paragrafo",
                exemplo=(
                    "Processo nº 08667.001923/2026-02. IPS. SPRF-ES. Falta de "
                    "urbanidade no trato dispensado a colega de trabalho. "
                    "Art. 116, inc. XI, c/c art. 130 da Lei nº 8.112/90. "
                    "Infração punível com suspensão. Encarregado de IPS sugere "
                    "o oferecimento de Termo de Ajustamento de Conduta — TAC."
                ),
                ajuda=(
                    "Períodos curtos separados por ponto, na ordem: número do "
                    "processo · IPS · unidade · fato apurado · enquadramento "
                    "legal · conclusão/sugestão do encarregado."
                ),
            ),
            Campo(
                id="destinatario",
                rotulo="Destinatário",
                tipo="linha",
                exemplo="Ao Senhor Corregedor Regional da PRF no Espírito Santo,",
                ajuda="Autoridade a quem a Informação é dirigida.",
            ),
        ),
        orientacao=(
            "Abertura do documento. Assunto e ementa saem num bloco recuado "
            "à direita, justificado, com os rótulos em negrito; o "
            "destinatário vem logo abaixo, à esquerda.\n\n"
            "A ementa deve seguir o padrão do documento SEI nº 28873450."
        ),
        norma="IN PRF nº 127/2024 — art. 92, caput; e art. 72",
        texto_norma=(
            "Art. 92. Finalizada a IPS ou após diligências preliminares, "
            "será elaborada Informação de caráter opinativo, com os dados "
            "indispensáveis ao juízo de admissibilidade da autoridade "
            "disciplinar competente, e deverá conter:\n"
            "I - identificação do procedimento;\n"
            "II - apresentação da denúncia inicial e dos fatos apurados;\n"
            "III - documentos e diligências contidas no procedimento;\n"
            "IV - análise prescricional;\n"
            "V - exame de admissibilidade e, se for o caso, a indicação de "
            "justa causa para instauração do PAD, composta de:\n"
            "a) indícios de autoria e materialidade;\n"
            "b) enquadramento preliminar;\n"
            "c) dosimetria preliminar; e\n"
            "d) matriz de responsabilidade.\n"
            "VI - conclusão, com as sugestões previstas no art. 72.\n\n"
            "Art. 72. Ao final da IPS serão apresentadas as conclusões na "
            "forma prevista nos arts. 92 e 93, podendo ser sugeridas as "
            "decisões previstas no art. 32.\n"
            "§ 2º A IPS sempre será submetida a juízo de admissibilidade "
            "por parte da autoridade disciplinar competente, sendo "
            "anulável a decisão de autoridade incompetente."
        ),
    ),
    Secao(
        id="identificacao",
        titulo="Identificação do procedimento, ordem de missão/portaria e autoria",
        rotulo="Identificação do procedimento",
        resumo="Instauração, prazo e quem são os apurados",
        orientacao=modelo.ORIENTACAO_IDENTIFICACAO,
        norma="IN PRF nº 127/2024 — arts. 92, I; 68 e 69",
        texto_norma=modelo.NORMA_IDENTIFICACAO,
        blocos_padrao=modelo.IDENTIFICACAO,
    ),
    Secao(
        id="apresentacao",
        titulo="Apresentação do fato",
        resumo="O que aconteceu: quê, onde, quem, quando, como",
        orientacao=modelo.ORIENTACAO_APRESENTACAO,
        norma="IN PRF nº 127/2024 — arts. 92, II; e 71",
        texto_norma=modelo.NORMA_APRESENTACAO,
        blocos_padrao=modelo.APRESENTACAO,
    ),
    Secao(
        id="documentos",
        titulo="Documentos e diligências",
        resumo="Elementos de convicção juntados, com o nº SEI",
        orientacao=modelo.ORIENTACAO_DOCUMENTOS,
        norma="IN PRF nº 127/2024 — arts. 92, III; e 70",
        texto_norma=modelo.NORMA_DOCUMENTOS,
        blocos_padrao=modelo.DOCUMENTOS,
    ),
    Secao(
        id="prescricional",
        titulo="Análise prescricional",
        resumo="Cálculo do prazo para cada penalidade possível",
        orientacao=modelo.ORIENTACAO_PRESCRICIONAL,
        norma="IN PRF nº 127/2024 — art. 92, IV; Lei nº 8.112/90 — art. 142",
        texto_norma=modelo.NORMA_PRESCRICIONAL,
        blocos_padrao=modelo.PRESCRICIONAL,
    ),
    Secao(
        id="admissibilidade",
        titulo=("Exame de admissibilidade e da justa causa para instauração "
                "de processo administrativo disciplinar - PAD"),
        rotulo="Exame de admissibilidade e justa causa",
        resumo="Indícios, enquadramento, dosimetria, TAC e matriz",
        orientacao=modelo.ORIENTACAO_ADMISSIBILIDADE,
        norma="IN PRF nº 127/2024 — arts. 92, V; 67; 41 a 44",
        texto_norma=modelo.NORMA_ADMISSIBILIDADE,
        blocos_padrao=modelo.ADMISSIBILIDADE,
    ),
    Secao(
        id="conclusao",
        titulo="Conclusão",
        resumo="O que se sugere à autoridade disciplinar",
        orientacao=modelo.ORIENTACAO_CONCLUSAO,
        norma="IN PRF nº 127/2024 — arts. 92, VI; 93; 32, § 2º; e 72",
        texto_norma=modelo.NORMA_CONCLUSAO,
        blocos_padrao=modelo.CONCLUSAO,
    ),

]


def blocos_do_roteiro(base: Secao | None) -> list:
    """Parágrafos prontos de uma parte, recém-criados a cada caso."""
    if base is None or not base.blocos_padrao:
        return []
    return [blocos.Bloco.from_dict(dict(d)) for d in base.blocos_padrao]


def secao(secao_id: str) -> Secao | None:
    return next((s for s in SECOES if s.id == secao_id), None)


# ─────────────────────────────────────────
#  CASO
# ─────────────────────────────────────────

@dataclass
class Parte:
    """O que o encarregado escreveu numa seção."""

    id: str
    html: str = ""                                  # legado (texto livre)
    valores: dict = field(default_factory=dict)     # seções por campos
    blocos: list = field(default_factory=list)      # corpo em parágrafos
    concluida: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id, "html": self.html, "valores": dict(self.valores),
            "blocos": [b.to_dict() for b in self.blocos],
            "concluida": self.concluida,
        }

    @staticmethod
    def from_dict(d: dict) -> "Parte":
        campos = {k: d[k] for k in Parte.__dataclass_fields__
                  if k in d and k != "blocos"}
        campos["blocos"] = [blocos.Bloco.from_dict(b)
                            for b in (d.get("blocos") or [])]
        return Parte(**campos)


#: Quanto de texto já conta como "começou a escrever". Um esqueleto
#: intocado não deve marcar a parte como iniciada.
MINIMO_UTIL = 12


def texto_puro(html_str: str) -> str:
    """Texto visível de um HTML, para medir preenchimento.

    O conteúdo de `<style>` e `<script>` é descartado antes das tags: o
    Qt exporta o documento com uma folha de estilo embutida, e contá-la
    como texto faria uma parte em branco parecer preenchida.
    """
    sem_bloco = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ",
                       html_str or "", flags=re.S | re.I)
    sem_tags = re.sub(r"<[^>]+>", " ", sem_bloco)
    return " ".join(html.unescape(sem_tags).split())


@dataclass
class CasoIPS:
    id: str = field(default_factory=_novo_id)
    nome: str = "Nova Informação"
    numero_processo: str = ""
    encarregado: str = ""
    matricula: str = ""
    unidade: str = ""
    #: Vêm da Identificação guardada na estação, e continuam editáveis.
    #: Estavam escritos no código como "Policial Rodoviário Federal": a
    #: peça é a mesma em qualquer corregedoria, o cargo de quem assina
    #: não.
    cargo: str = field(default_factory=lambda: _do_perfil("cargo"))
    orgao: str = field(default_factory=lambda: _do_perfil("orgao"))
    partes: dict[str, Parte] = field(default_factory=dict)
    criado: float = field(default_factory=time.time)
    atualizado: float = field(default_factory=time.time)

    # ── acesso ───────────────────────────────────
    def parte(self, secao_id: str) -> Parte:
        """Devolve a parte, criando-a já com o roteiro na primeira vez."""
        if secao_id not in self.partes:
            base = secao(secao_id)
            if base is not None and base.por_campos:
                self.partes[secao_id] = Parte(
                    id=secao_id,
                    valores={c.id: c.padrao for c in base.campos})
            else:
                self.partes[secao_id] = Parte(
                    id=secao_id, html=base.esqueleto if base else "",
                    blocos=blocos_do_roteiro(base))
        return self.partes[secao_id]

    def iniciada(self, secao_id: str) -> bool:
        """A parte foi mexida, ou continua como veio?"""
        p = self.partes.get(secao_id)
        base = secao(secao_id)
        if p is None or base is None:
            return False
        if base.por_campos:
            # Um campo que continua igual ao padrão não conta como
            # preenchido: senão a seção nasceria "iniciada".
            return any(
                (p.valores.get(c.id) or "").strip()
                and (p.valores.get(c.id) or "").strip() != c.padrao.strip()
                for c in base.campos)
        if p.blocos:
            # Os exemplos do roteiro não contam: a parte só é "iniciada"
            # quando o encarregado escreve algo próprio.
            return len(blocos.texto_escrito(p.blocos)) >= MINIMO_UTIL
        if texto_puro(p.html) == texto_puro(base.esqueleto):
            return False
        return len(texto_puro(p.html)) >= MINIMO_UTIL

    # ── progresso ────────────────────────────────
    def progresso(self) -> tuple[int, int]:
        """(concluídas, total de obrigatórias)."""
        obrigatorias = [s for s in SECOES if s.obrigatoria]
        feitas = sum(1 for s in obrigatorias
                     if self.partes.get(s.id, Parte(s.id)).concluida)
        return feitas, len(obrigatorias)

    def pendentes(self) -> list[Secao]:
        return [s for s in SECOES if s.obrigatoria
                and not self.partes.get(s.id, Parte(s.id)).concluida]

    def completo(self) -> bool:
        return not self.pendentes()

    # ── serialização ─────────────────────────────
    def to_dict(self) -> dict:
        return {
            "id": self.id, "nome": self.nome,
            "numero_processo": self.numero_processo,
            "encarregado": self.encarregado, "matricula": self.matricula,
            "unidade": self.unidade,
            "partes": {k: v.to_dict() for k, v in self.partes.items()},
            "criado": self.criado, "atualizado": self.atualizado,
        }

    @staticmethod
    def from_dict(d: dict) -> "CasoIPS":
        return CasoIPS(
            id=d.get("id") or _novo_id(),
            nome=d.get("nome", "Nova Informação"),
            numero_processo=d.get("numero_processo", ""),
            encarregado=d.get("encarregado", ""),
            matricula=d.get("matricula", ""),
            unidade=d.get("unidade", ""),
            partes={k: Parte.from_dict(v)
                    for k, v in (d.get("partes") or {}).items()},
            criado=d.get("criado", time.time()),
            atualizado=d.get("atualizado", time.time()),
        )


# ─────────────────────────────────────────
#  ARMAZENAMENTO
# ─────────────────────────────────────────

def pasta_dados() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    raiz = Path(base) if base else Path.home() / ".local" / "share"
    return raiz / "SistemaTemis" / "ips"


class AcervoIPS:
    """Casos gravados em disco."""

    ARQUIVO = "informacoes.json"

    def __init__(self, raiz: Path | None = None):
        self.raiz = Path(raiz) if raiz else pasta_dados()
        self.raiz.mkdir(parents=True, exist_ok=True)

    def carregar(self) -> tuple[list[CasoIPS], str]:
        arq = self.raiz / self.ARQUIVO
        if not arq.exists():
            novo = CasoIPS()
            return [novo], novo.id
        try:
            dados = json.loads(arq.read_text(encoding="utf-8"))
            casos = [CasoIPS.from_dict(c) for c in dados.get("casos", [])]
        except (json.JSONDecodeError, OSError, TypeError, AttributeError):
            casos = []
        if not casos:
            novo = CasoIPS()
            return [novo], novo.id
        atual = dados.get("atual") if isinstance(dados, dict) else None
        if atual not in [c.id for c in casos]:
            atual = casos[0].id
        return casos, atual

    # ── imagens ──────────────────────────────────
    #: As imagens ficam em arquivos, e não embutidas no JSON: em base64
    #: uma única foto de câmera deixa o índice com megabytes e torna cada
    #: salvamento automático caro.
    def pasta_imagens(self, caso_id: str) -> Path:
        destino = self.raiz / "imagens" / caso_id
        destino.mkdir(parents=True, exist_ok=True)
        return destino

    def guardar_imagem(self, caso_id: str, origem: str | Path) -> str:
        import shutil
        origem = Path(origem)
        nome = f"{_novo_id()}{origem.suffix.lower() or '.png'}"
        shutil.copy2(origem, self.pasta_imagens(caso_id) / nome)
        return nome

    def guardar_bytes(self, caso_id: str, dados: bytes, sufixo=".png") -> str:
        nome = f"{_novo_id()}{sufixo}"
        (self.pasta_imagens(caso_id) / nome).write_bytes(dados)
        return nome

    def caminho_imagem(self, caso_id: str, nome: str) -> Path:
        return self.pasta_imagens(caso_id) / nome

    def gravar(self, casos: list[CasoIPS], atual: str):
        # Grava num temporário e só então substitui: uma queda no meio da
        # escrita truncaria o arquivo e levaria junto todos os casos, não
        # apenas o que estava sendo salvo.
        alvo = self.raiz / self.ARQUIVO
        tmp = alvo.with_suffix(".tmp")
        payload = {"casos": [c.to_dict() for c in casos], "atual": atual}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(alvo)


# ─────────────────────────────────────────
#  EXPORTAÇÃO PARA O SEI
# ─────────────────────────────────────────

#: Elementos que o editor pode produzir e que o SEI aceita na importação.
TAGS_PERMITIDAS = {
    "p", "br", "b", "strong", "i", "em", "u", "span", "font",
    "ul", "ol", "li", "table", "tr", "td", "th", "tbody", "thead",
    "h1", "h2", "h3", "h4", "img", "div", "sub", "sup", "a",
}

_ESTILO_CORPO = (
    "font-family:'Times New Roman',serif; font-size:12pt; "
    "text-align:justify; line-height:1.5;"
)


#: A limpeza mora em `temis.impressao`, usada também pelo termo de
#: juntada. Regra de formatação duplicada é regra que diverge com o tempo.
limpar_para_sei = _limpar_para_sei


#: Como a imagem é referenciada dentro do editor.
PREFIXO_IMAGEM = "imagens/"

_TIPOS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
          ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp"}


def imagens_referenciadas(html_str: str) -> list[str]:
    """Nomes de imagem citados num HTML do editor."""
    return re.findall(rf'src="{PREFIXO_IMAGEM}([^"]+)"', html_str or "")


def embutir_imagens(html_str: str, pasta: Path) -> tuple[str, list[str]]:
    """Troca as referências por base64. Devolve (html, nomes usados)."""
    import base64

    usados: list[str] = []

    def troca(m):
        nome = m.group(1)
        arq = Path(pasta) / nome
        if not arq.exists():
            return m.group(0)
        usados.append(nome)
        tipo = _TIPOS.get(arq.suffix.lower(), "image/png")
        dados = base64.b64encode(arq.read_bytes()).decode("ascii")
        return f'src="data:{tipo};base64,{dados}"'

    novo = re.sub(rf'src="{PREFIXO_IMAGEM}([^"]+)"', troca, html_str or "")
    return novo, usados


#: Largura da coluna vazia que empurra o bloco de assunto e ementa para a
#: direita. O bloco ocupa o restante.
RECUO_BLOCO = "22%"


def render_iniciais(caso: CasoIPS) -> str:
    """Assunto e ementa recuados à direita e justificados.

    O recuo sai por uma **tabela de duas colunas** — a primeira vazia —
    e não por `margin-left`. Medindo o resultado constatou-se que o motor
    de texto do Qt, usado na prévia e no PDF, ignora `margin-left` em cm
    ou pt e trata porcentagem como valor absoluto; e que desconsidera
    `text-align:justify` no CSS, obedecendo apenas ao atributo `align`.
    Largura de coluna em porcentagem, essa sim, ele respeita — e é também
    o que o importador do SEI preserva com mais fidelidade.
    """
    e = html.escape
    v = caso.partes.get("iniciais", Parte("iniciais")).valores or {}
    assunto = (v.get("assunto") or "").strip()
    ementa = (v.get("ementa") or "").strip()
    destinatario = (v.get("destinatario") or "").strip()

    linhas = []
    bloco = []
    if assunto:
        bloco.append(
            '<p align="justify" style="margin:0; text-align:justify;">'
            f"<b>Assunto:</b> {e(assunto)}</p>")
    if ementa:
        if bloco:
            bloco.append(blocos.espaco(blocos.ESPACO))
        bloco.append(
            '<p align="justify" style="margin:0; text-align:justify;">'
            f"<b>Ementa:</b> {e(ementa)}</p>")
    if bloco:
        largura = f"{100 - int(RECUO_BLOCO.rstrip('%'))}%"
        linhas.append(
            '<table width="100%" cellspacing="0" cellpadding="0" border="0">'
            "<tr>"
            f'<td width="{RECUO_BLOCO}"></td>'
            f'<td width="{largura}">' + "".join(bloco) + "</td>"
            "</tr></table>")
    if destinatario:
        if linhas:
            linhas.append(blocos.espaco(blocos.ESPACO_SECAO))
        linhas.append(
            '<p align="left" style="text-align:left; margin:0;">'
            f"{e(destinatario)}</p>")
    return "".join(linhas)


#: Partes cuja diagramação é própria. As demais saem como o encarregado
#: escreveu no editor.
RENDERIZADORES = {"iniciais": render_iniciais}


def render_parte(caso: CasoIPS, s: Secao, numero: int = 1,
                 pasta_imagens: Path | None = None) -> str:
    montador = RENDERIZADORES.get(s.id)
    if montador is not None:
        return montador(caso)
    parte = caso.partes.get(s.id, Parte(s.id))
    if parte.blocos:
        conteudo = blocos.render_blocos(parte.blocos, numero)
    else:
        conteudo = limpar_para_sei(parte.html)
    if pasta_imagens is not None:
        conteudo, _ = embutir_imagens(conteudo, pasta_imagens)
    return conteudo


#: Fundo da faixa do título de cada elemento.
FUNDO_TITULO = "#D9D9D9"


def titulo_secao(numero: int, titulo: str) -> str:
    """Título do elemento sobre faixa cinza, como no modelo em uso.

    Sai por tabela de uma célula: fundo aplicado a <p> ou <div> costuma
    se perder na importação do SEI, enquanto o de célula é preservado.
    """
    e = html.escape
    return (
        '<table width="100%" cellspacing="0" cellpadding="3" border="0"><tr>'
        f'<td width="100%" style="background-color:{FUNDO_TITULO};">'
        '<p style="margin:0;">'
        f"<b>{e(str(numero))}.&nbsp;&nbsp;&nbsp;{e(titulo.upper())}</b>"
        "</p></td></tr></table>")


def build_html(caso: CasoIPS, quando: str = "",
               pasta_imagens: Path | None = None) -> str:
    """Documento final, pronto para a importação de HTML do SEI."""
    from ..impressao import cabecalho_html, rodape_html
    e = html.escape
    # Sem cabeçalho: no SEI o timbre, o nome do documento e o número do
    # processo são gerados pelo próprio sistema. O documento importado
    # começa no "Assunto".
    partes = []

    numero = 0
    for s in SECOES:
        # O número vem da posição da parte no modelo, e não de quantas já
        # foram preenchidas: a Conclusão é o item 6 mesmo que as anteriores
        # ainda estejam em branco, e o encarregado pode escrever fora de
        # ordem sem ver a numeração dançar.
        if s.numerada:
            numero += 1
        conteudo = render_parte(caso, s, numero, pasta_imagens)
        if not texto_puro(conteudo) and "<img" not in conteudo:
            continue
        if s.numerada:
            if partes:
                partes.append(blocos.espaco(blocos.ESPACO_SECAO))
            partes.append(titulo_secao(numero, s.titulo))
            partes.append(blocos.espaco(blocos.ESPACO))
        # Seções não numeradas — como as Iniciais — abrem o documento sem
        # título: o rótulo "Assunto"/"Ementa" já vem no próprio bloco.
        partes.append(conteudo)

    if caso.encarregado:
        vinculo = " · ".join(x for x in (
            f"matrícula {e(caso.matricula)}" if caso.matricula else "",
            e(caso.unidade) if caso.unidade else "") if x)
        partes.append(blocos.espaco(24))
        partes.append(
            '<p style="text-align:center; margin:0;">'
            "______________________________________<br/>"
            f"<b>{e(caso.encarregado)}</b>"
            + (f"<br/>{e(caso.cargo)}" if caso.cargo.strip() else "")
            + (f"<br/><span style=\"font-size:10pt;\">{vinculo}</span>"
               if vinculo else "")
            + "</p>")

    return (
        "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">"
        f"<title>Informação — {e(caso.nome)}</title></head>\n"
        f'<body style="{_ESTILO_CORPO}">\n'
        + cabecalho_html()
        + "\n".join(partes)
        + rodape_html() + "\n</body></html>\n"
    )
