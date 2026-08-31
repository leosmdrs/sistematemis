"""
Vídeo da Internet — baixar e documentar o que está publicado.

Vídeo publicado em rede social é prova que some. Some porque o autor
apaga, porque a plataforma remove, porque a conta é encerrada. Quem
precisa dele num procedimento tem de obtê-lo enquanto existe — e tem de
poder demonstrar, depois, **o que** obteve, **de onde** e **quando**.

É por isso que esta ferramenta não é um baixador. Baixar é a parte fácil.
O que ela produz, além do arquivo, é a peça que o identifica: o endereço,
os dados que a plataforma publicava naquele instante, a hora qualificada
da captura, o resumo criptográfico do arquivo e as versões de tudo o que
participou.

**A garantia aqui é de outra natureza, e a peça não pode fingir o
contrário.** Nas demais ferramentas do sistema a operação é
determinística: quem repetir os passos chega ao mesmo resultado, e o
termo promete isso. Aqui, não. Baixar de novo amanhã pode devolver
arquivo diferente — a plataforma recodifica, troca formatos, remove o
conteúdo. O que esta peça afirma é mais estreito e verdadeiro:

    este arquivo, com este resumo, foi obtido deste endereço neste
    instante, e o que a plataforma então publicava era isto.

Prometer reprodutibilidade seria prometer o que não se cumpre.

Duas outras coisas que a peça precisa dizer, e que se esconderiam com
facilidade. A primeira: as plataformas servem vídeo e áudio em fluxos
separados, e o arquivo entregue costuma ser a **junção local** dos dois —
não é cópia byte a byte de um arquivo que estivesse lá. A segunda: os
dados de título, canal e data são **informados pela própria plataforma**;
a ferramenta os transcreve, e não os certifica.

Nada de credencial: só se alcança o que está publicamente acessível. A
disponibilidade que a plataforma declara fica consignada na peça, para
que se possa ver que nada restrito foi contornado.
"""

from __future__ import annotations

import datetime
import html as _html
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import derivado_core as derivado

#: Quantos dias de vida bastam para desconfiar da biblioteca. As
#: plataformas mudam de tempos em tempos e quebram a extração; cópia
#: velha falha com mensagem que não ajuda ninguém. Ver `estado`.
DIAS_PARA_DESCONFIAR = 120

#: (chave, rótulo, seletor de formato do yt-dlp)
#:
#: O seletor pede fluxo de vídeo e fluxo de áudio, que a plataforma serve
#: em separado, e deixa a junção para o FFmpeg. Daí a ressalva sobre o
#: arquivo entregue não ser cópia de um arquivo servido.
QUALIDADES: tuple = (
    ("melhor", "A melhor disponível", "bestvideo*+bestaudio/best"),
    ("1080", "Até 1080p", "bestvideo[height<=1080]+bestaudio/best[height<=1080]"),
    ("720", "Até 720p", "bestvideo[height<=720]+bestaudio/best[height<=720]"),
    ("480", "Até 480p", "bestvideo[height<=480]+bestaudio/best[height<=480]"),
    ("audio", "Somente o áudio", "bestaudio/best"),
)


def seletor(chave: str) -> str:
    for c, _rotulo, s in QUALIDADES:
        if c == chave:
            return s
    return QUALIDADES[0][2]


def rotulo_qualidade(chave: str) -> str:
    for c, rotulo, _s in QUALIDADES:
        if c == chave:
            return rotulo
    return chave


# ─────────────────────────────────────────
#  A BIBLIOTECA
# ─────────────────────────────────────────

def versao() -> str:
    try:
        import yt_dlp
        return str(yt_dlp.version.__version__)
    except Exception:                                       # noqa: BLE001
        return ""


def _data_da_versao(v: str):
    """A versão do yt-dlp é a data em que saiu: 2026.08.19."""
    m = re.match(r"^(\d{4})\.(\d{2})\.(\d{2})", v or "")
    if not m:
        return None
    try:
        return datetime.date(*(int(x) for x in m.groups()))
    except ValueError:
        return None


def estado() -> tuple:
    """(pode usar, recado). O recado vai para a tela e para a peça.

    Uma ferramenta que depende de acompanhar mudanças de plataforma
    envelhece, e envelhecer aqui não dá erro claro: dá extração que falha
    por motivo obscuro. Dizer a idade antes é mais honesto do que deixar
    a pessoa descobrir no meio de uma diligência.
    """
    v = versao()
    if not v:
        return False, ("a biblioteca de captura não está instalada nesta "
                       "estação")
    data = _data_da_versao(v)
    if data is None:
        return True, f"versão {v}"
    dias = (datetime.date.today() - data).days
    if dias > DIAS_PARA_DESCONFIAR:
        return True, (f"versão {v}, de {dias} dias atrás — as plataformas "
                      "mudam com frequência, e cópia antiga costuma falhar")
    return True, f"versão {v}, de {data.strftime('%d/%m/%Y')}"


def _ffmpeg():
    """O FFmpeg que o sistema já embarca, para a junção das faixas."""
    from .video_core import ffmpeg_path
    caminho = ffmpeg_path()
    return str(Path(caminho).parent) if caminho else ""


class _Mudo:
    """Engole o que a biblioteca escreveria no console.

    `quiet` cala as mensagens comuns, mas não os erros, que a biblioteca
    manda para a saída de erro por conta própria. Num programa de janela
    isso vai para um console que pode nem existir — e, o que importa
    mais, o erro já sobe por `explicar_falha`, em português e no lugar em
    que quem opera vai lê-lo. Deixá-lo sair também pelo console só criaria
    duas versões do mesmo problema, uma delas ilegível.
    """

    def debug(self, msg):
        pass

    info = warning = debug

    def error(self, msg):
        pass


# ─────────────────────────────────────────
#  O QUE A PLATAFORMA PUBLICA
# ─────────────────────────────────────────

@dataclass
class Publicacao:
    """Os dados que a plataforma informava no instante da consulta.

    Transcritos, e não certificados: quem os produziu foi a plataforma.
    A peça diz isso com todas as letras.
    """

    url: str = ""
    identificador: str = ""
    titulo: str = ""
    canal: str = ""
    canal_url: str = ""
    publicado_em: str = ""
    duracao: int = 0
    visualizacoes: int = 0
    licenca: str = ""
    disponibilidade: str = ""
    extrator: str = ""
    restricao_idade: int = 0
    ao_vivo: str = ""
    descricao: str = ""
    erro: str = ""

    @property
    def publica(self) -> bool:
        return self.disponibilidade in ("public", "")


def _data_publicada(info: dict) -> str:
    bruto = info.get("upload_date") or ""
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", bruto)
    if not m:
        return bruto
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"


def _da_informacao(info: dict, url: str) -> Publicacao:
    return Publicacao(
        url=info.get("webpage_url") or url,
        identificador=str(info.get("id") or ""),
        titulo=info.get("title") or "",
        canal=info.get("channel") or info.get("uploader") or "",
        canal_url=info.get("channel_url") or info.get("uploader_url") or "",
        publicado_em=_data_publicada(info),
        duracao=int(info.get("duration") or 0),
        visualizacoes=int(info.get("view_count") or 0),
        licenca=info.get("license") or "",
        disponibilidade=info.get("availability") or "",
        extrator=info.get("extractor_key") or "",
        restricao_idade=int(info.get("age_limit") or 0),
        ao_vivo=info.get("live_status") or "",
        descricao=(info.get("description") or "")[:2000])


def sondar(url: str) -> Publicacao:
    """Consulta o endereço sem baixar nada.

    Serve para que quem opera veja o que vai capturar antes de capturar —
    e para que erro de endereço apareça como recado, e não como diligência
    perdida no meio.
    """
    import yt_dlp

    opcoes = {"quiet": True, "no_warnings": True, "skip_download": True,
              "noplaylist": True, "logger": _Mudo()}
    try:
        with yt_dlp.YoutubeDL(opcoes) as y:
            info = y.extract_info(url, download=False)
    except Exception as e:                                  # noqa: BLE001
        return Publicacao(url=url, erro=explicar_falha(str(e)))
    if info.get("_type") == "playlist":
        entradas = info.get("entries") or []
        if not entradas:
            return Publicacao(url=url, erro="o endereço não tem vídeo algum")
        info = entradas[0]
    return _da_informacao(info, url)


# ─────────────────────────────────────────
#  A CAPTURA
# ─────────────────────────────────────────

@dataclass
class Captura:
    """O arquivo obtido, e tudo o que o identifica."""

    arquivo: str = ""
    sha256: str = ""
    tamanho: int = 0
    formato: str = ""
    largura: int = 0
    altura: int = 0
    #: Instante da captura, com o fuso e a qualificação do relógio.
    quando: str = ""
    #: O arquivo entregue resultou de juntar faixas servidas em separado.
    juntou_faixas: bool = False
    qualidade: str = ""
    yt_dlp: str = ""
    ffmpeg: str = ""
    publicacao: Publicacao = field(default_factory=Publicacao)
    erro: str = ""

    @property
    def nome(self) -> str:
        return Path(self.arquivo).name if self.arquivo else ""


#: Falhas conhecidas, ditas em português. O que não estiver aqui vai
#: cru: o texto original ao menos pode ser pesquisado.
_FALHAS = (
    ("Private video",
     "O vídeo é privado. Esta ferramenta só alcança o que está "
     "publicamente acessível, e não contorna restrição de acesso."),
    ("members-only",
     "O vídeo é restrito a membros do canal. Esta ferramenta só alcança o "
     "que está publicamente acessível."),
    ("Sign in to confirm your age",
     "O vídeo tem restrição de idade e a plataforma exige identificação "
     "para exibi-lo. Esta ferramenta não se identifica em plataforma "
     "alguma."),
    ("Video unavailable",
     "A plataforma informa que o vídeo não está disponível. Ele pode ter "
     "sido removido, ou estar bloqueado nesta região."),
    ("This video has been removed",
     "A plataforma informa que o vídeo foi removido."),
    ("Unsupported URL",
     "O endereço não é de um sítio que a biblioteca de captura saiba ler."),
    ("Sign in to confirm you’re not a bot",
     "A plataforma passou a exigir identificação para servir este vídeo."),
    ("Unable to download webpage",
     "Não foi possível alcançar o endereço. Pode ser falta de rede, ou "
     "bloqueio da saída para a internet nesta estação."),
    ("nsig extraction failed",
     "A plataforma mudou a forma de servir o vídeo e a biblioteca de "
     "captura desta instalação não acompanha mais. É o sintoma típico de "
     "cópia desatualizada."),
    ("Requested format is not available",
     "A qualidade pedida não existe para este vídeo. Escolha outra."),
)


def explicar_falha(erro: str) -> str:
    """Traduz o que a biblioteca disse, sem esconder o que ela disse."""
    limpo = re.sub(r"\x1b\[[0-9;]*m", "", erro or "")
    limpo = re.sub(r"^ERROR:\s*", "", limpo).strip()
    for marca, explicacao in _FALHAS:
        if marca.lower() in limpo.lower():
            return explicacao
    pode, recado = estado()
    sufixo = ""
    if pode and "dias atrás" in recado:
        sufixo = ("\n\nVale notar que a biblioteca de captura desta "
                  "instalação está antiga (" + recado + ").")
    return (limpo or "a captura falhou, e a biblioteca não disse por quê") + sufixo


def baixar(url: str, pasta, qualidade: str = "melhor",
           progresso=None) -> Captura:
    """Obtém o vídeo e mede tudo o que a peça vai afirmar.

    O instante da captura é tomado **depois** de o arquivo estar em
    disco, e do relógio qualificado do sistema — é o instante em que se
    passou a ter o material, que é o que a peça declara.
    """
    import yt_dlp

    from ..relogio import carimbo
    from .hash_core import sha256_file
    from .video_core import versao_curta

    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    captura = Captura(qualidade=qualidade, yt_dlp=versao())

    def gancho(d):
        if progresso is None:
            return
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            progresso(int(d.get("downloaded_bytes") or 0), int(total))
        elif d.get("status") == "finished":
            progresso(1, 1)

    opcoes = {
        # `quiet` cala as mensagens, mas não a barra de progresso, que a
        # biblioteca escreve direto na saída padrão. Num programa de
        # janela isso vai para um console que pode nem existir, e o
        # andamento de verdade é o que sobe pelo gancho abaixo.
        "quiet": True, "no_warnings": True, "noprogress": True,
        "noplaylist": True, "logger": _Mudo(),
        "format": seletor(qualidade),
        "outtmpl": str(pasta / "%(title).120B [%(id)s].%(ext)s"),
        "progress_hooks": [gancho],
        "restrictfilenames": True,
        # Sem isto, uma falha no meio deixa fragmento com cara de arquivo
        # bom, e a peça poderia acabar citando o resumo de um pedaço.
        "continuedl": False,
        "overwrites": True,
    }
    pasta_ffmpeg = _ffmpeg()
    if pasta_ffmpeg:
        opcoes["ffmpeg_location"] = pasta_ffmpeg

    try:
        with yt_dlp.YoutubeDL(opcoes) as y:
            info = y.extract_info(url, download=True)
            if info.get("_type") == "playlist":
                entradas = info.get("entries") or []
                if not entradas:
                    captura.erro = "o endereço não tem vídeo algum"
                    return captura
                info = entradas[0]
            caminho = Path(y.prepare_filename(info))
    except Exception as e:                                  # noqa: BLE001
        captura.erro = explicar_falha(str(e))
        return captura

    # O nome muda quando houve junção de faixas: o arquivo final vira
    # .mp4 ou .mkv, e o que `prepare_filename` devolve é o do fluxo.
    if not caminho.is_file():
        candidatos = sorted(
            pasta.glob(caminho.stem + ".*"),
            key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidatos:
            captura.erro = ("a captura terminou sem deixar arquivo em "
                            + str(pasta))
            return captura
        caminho = candidatos[0]

    captura.publicacao = _da_informacao(info, url)
    captura.arquivo = str(caminho)
    captura.formato = caminho.suffix.lstrip(".").upper()
    captura.largura = int(info.get("width") or 0)
    captura.altura = int(info.get("height") or 0)
    captura.ffmpeg = versao_curta()
    # Pediu vídeo e áudio em fluxos separados: o entregue é a junção.
    captura.juntou_faixas = ("+" in seletor(qualidade)
                             and qualidade != "audio")
    try:
        captura.tamanho = caminho.stat().st_size
        captura.sha256 = sha256_file(str(caminho))
    except OSError as e:
        captura.erro = f"não foi possível medir o arquivo obtido: {e}"
    captura.quando = carimbo()
    return captura


def formatar_duracao(segundos: int) -> str:
    if segundos <= 0:
        return "—"
    h, resto = divmod(int(segundos), 3600)
    m, s = divmod(resto, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# ─────────────────────────────────────────
#  O TERMO
# ─────────────────────────────────────────

@dataclass
class TermoCaptura(derivado.TermoDerivado):
    """A peça da captura.

    Herda de `TermoDerivado` pela qualificação de quem assina e pelo
    número do procedimento, que são os mesmos de todas as peças — e para
    que o mesmo diálogo sirva. O que ela acrescenta é o par que aqui
    importa: o que a plataforma publicava, e o que se obteve.
    """

    captura: Captura = field(default_factory=Captura)


#: O que a operação alcança e o que ela não alcança. Vai impresso: uma
#: ferramenta que se cala sobre os próprios limites convida a que se lhe
#: atribua alcance que ela não tem.
RESSALVAS: tuple = (
    "Esta peça não afirma reprodutibilidade, e não poderia. Baixar o "
    "mesmo endereço noutro momento pode devolver arquivo diferente, ou "
    "não devolver arquivo algum: a plataforma recodifica o material, "
    "troca os formatos que serve e remove conteúdo. O que aqui se afirma "
    "é mais estreito e verificável — este arquivo, com este resumo "
    "criptográfico, foi obtido deste endereço neste instante.",
    "Os dados de título, canal, data de publicação, duração e "
    "visualizações são informados pela própria plataforma. A ferramenta "
    "os transcreve como estavam no momento da consulta; não os certifica, "
    "nem teria como.",
    "As plataformas servem imagem e som em fluxos separados. Salvo quando "
    "adiante se consigne o contrário, o arquivo entregue é a junção local "
    "desses fluxos, feita nesta estação pelo FFmpeg cuja versão fica "
    "consignada — e não a cópia byte a byte de um arquivo que estivesse "
    "publicado.",
    "A captura alcança somente o que está publicamente acessível. Nenhuma "
    "credencial foi apresentada, nenhuma restrição de acesso foi "
    "contornada, e a disponibilidade que a plataforma declarava fica "
    "adiante consignada.",
    "O conteúdo obtido não foi alterado por esta ferramenta. Para "
    "compactá-lo, recortá-lo ou juntá-lo a outro, use a Edição de Vídeo, "
    "que emite termo próprio ligando o resultado a este arquivo pelo "
    "resumo criptográfico.",
)


def intro(t: TermoCaptura) -> str:
    from .hash_core import ARTIGO_PROCESSO, MESES

    mes = MESES[t.mes - 1] if 1 <= t.mes <= 12 else ""
    quando = (f"Ao {t.dia}º dia do mês de {mes} de {t.ano}" if t.dia == 1
              else f"Aos {t.dia} dias do mês de {mes} de {t.ano}")
    artigo = ARTIGO_PROCESSO.get(t.tipo_processo, "do")
    partes = (t.cargo.strip(), t.nome.strip())
    quem = " ".join(p for p in partes if p)
    return (
        f"{quando}, eu, {quem}, matrícula {t.matricula}, lotado(a) no(a) "
        f"{t.lotacao}, visando instruir os autos {artigo} "
        f"{t.tipo_processo} nº {t.numero_processo}, declaro que procedi à "
        "captura do material audiovisual publicado no endereço eletrônico "
        "adiante identificado, cujo conteúdo obtive e cujo resumo "
        "criptográfico fica consignado."
    )


ENCERRAMENTO = (
    "O resumo criptográfico acima permite conferir, a qualquer tempo, que "
    "o arquivo juntado aos autos é exatamente o que foi obtido no ato aqui "
    "relatado. Sem mais a relatar, encerro o presente termo."
)


def _quadro(titulo: str, linhas: list) -> str:
    e = _html.escape
    corpo = []
    for rotulo, valor, *resto in linhas:
        if not valor:
            continue
        mono = bool(resto and resto[0])
        estilo = ("font-family:Consolas,monospace; font-size:9pt;"
                  if mono else "font-size:10.5pt;")
        corpo.append(
            f'<tr><td width="30%" valign="top">'
            f'<font color="{derivado.CINZA}" size="2">{e(rotulo)}</font></td>'
            f'<td><span style="{estilo}">{e(str(valor))}</span></td></tr>')
    return (
        f'<p style="font-size:11pt; margin-top:14px;">'
        f'<b><font color="{derivado.INK}">{e(titulo)}</font></b></p>'
        '<table width="100%" cellspacing="0" cellpadding="5" border="1" '
        'style="border-collapse:collapse;">' + "".join(corpo) + "</table>")


def _linhas_da_publicacao(p: Publicacao) -> list:
    disponibilidade = {"public": "pública",
                       "unlisted": "não listada (acessível por quem tem o "
                                   "endereço)"}.get(p.disponibilidade,
                                                    p.disponibilidade)
    return [
        ("Endereço", p.url),
        ("Plataforma", p.extrator),
        ("Identificador na plataforma", p.identificador),
        ("Título", p.titulo),
        ("Canal ou perfil", p.canal),
        ("Endereço do canal", p.canal_url),
        ("Publicado em", p.publicado_em),
        ("Duração", formatar_duracao(p.duracao)),
        ("Visualizações na consulta",
         f"{p.visualizacoes:n}".replace(",", ".") if p.visualizacoes else ""),
        ("Licença declarada", p.licenca),
        ("Disponibilidade declarada", disponibilidade),
        ("Restrição de idade",
         f"{p.restricao_idade} anos" if p.restricao_idade else ""),
    ]


def _linhas_do_arquivo(c: Captura) -> list:
    resolucao = (f"{c.largura}×{c.altura}" if c.largura and c.altura else "")
    return [
        ("Arquivo obtido", c.nome),
        ("Tamanho", derivado.formatar_tamanho(c.tamanho)),
        ("SHA-256", c.sha256 or "não foi possível medir", True),
        ("Formato", c.formato),
        ("Resolução", resolucao),
        ("Qualidade pedida", rotulo_qualidade(c.qualidade)),
        ("Momento da captura", c.quando),
        ("Composição do arquivo",
         "junção local dos fluxos de imagem e som servidos em separado"
         if c.juntou_faixas else "fluxo único, tal como servido"),
        ("Biblioteca de captura",
         f"yt-dlp {c.yt_dlp}" if c.yt_dlp else ""),
        ("Junção das faixas", f"FFmpeg {c.ffmpeg}" if c.ffmpeg else ""),
    ]


def build_html(t: TermoCaptura) -> str:
    """A peça em HTML, para exibir e exportar."""
    from ..impressao import cabecalho_html, rodape_html

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
        _quadro("O que estava publicado", _linhas_da_publicacao(t.captura.publicacao)),
        _quadro("O que foi obtido", _linhas_do_arquivo(t.captura)),
    ]

    if t.captura.publicacao.descricao:
        partes.append(
            f'<p style="font-size:11pt; margin-top:14px;">'
            f'<b><font color="{derivado.INK}">Descrição publicada</font></b>'
            "</p>"
            f'<p align="justify" style="font-size:10pt; line-height:150%; '
            f'white-space:pre-wrap;">{e(t.captura.publicacao.descricao)}</p>')

    partes.append(
        f'<p style="font-size:11pt; margin-top:18px;">'
        f'<b><font color="{derivado.INK}">Alcance e limites da operação'
        "</font></b></p>")
    partes += [
        f'<p align="justify" style="font-size:10pt; line-height:150%;">'
        f'<font color="{derivado.INK}">{e(x)}</font></p>' for x in t.ressalvas]

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
    partes.append(rodape_html(*t.motores))
    partes.append("</body></html>")
    return "".join(partes)


def build_texto(t: TermoCaptura) -> str:
    """A mesma peça em texto puro, para colar onde não se aceita HTML."""
    from ..impressao import rodape_texto

    L = [t.titulo.upper(), "", intro(t), "", "O QUE ESTAVA PUBLICADO"]
    for rotulo, valor, *_ in _linhas_da_publicacao(t.captura.publicacao):
        if valor:
            L.append(f"   {rotulo}: {valor}")
    L += ["", "O QUE FOI OBTIDO"]
    for rotulo, valor, *_ in _linhas_do_arquivo(t.captura):
        if valor:
            L.append(f"   {rotulo}: {valor}")
    if t.captura.publicacao.descricao:
        L += ["", "DESCRIÇÃO PUBLICADA", t.captura.publicacao.descricao]
    L += ["", "ALCANCE E LIMITES DA OPERAÇÃO"]
    L += [f"- {x}" for x in t.ressalvas]
    L += ["", ENCERRAMENTO, "", rodape_texto(*t.motores), "", "_" * 40,
          t.nome]
    if t.cargo.strip():
        L.append(t.cargo)
    if t.matricula.strip():
        L.append(f"Matrícula {t.matricula}")
    return "\n".join(L)


def montar_termo(captura: Captura) -> TermoCaptura:
    """A peça pronta para receber a qualificação de quem assina."""
    item = derivado.Derivacao(origens=[], saida=derivado.ler(captura.arquivo))
    return TermoCaptura(
        titulo="Termo de Captura de Material Audiovisual Publicado na Internet",
        operacao="captura de material audiovisual publicado",
        ressalvas=RESSALVAS,
        motores=("video",),
        itens=[item],
        captura=captura)
