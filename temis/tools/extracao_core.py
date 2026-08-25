"""
Extração Registrada — a diligência em sistema interno, documentada.

O problema que esta ferramenta atende é concreto. A corregedoria pede à
área de tecnologia registros de auditoria de um sistema; a área extrai,
manda pelo processo eletrônico; e o servidor apurado contesta a cadeia
de custódia. O resumo criptográfico do arquivo prova que ele não mudou
depois — mas não diz de onde saiu, com que consulta, nem em que
condições.

A lacuna está na **origem**, e é lá que esta ferramenta trabalha: quem
extrai abre o sistema dentro do navegador do próprio Têmis, e cada passo
fica registrado — o endereço visitado, o que se clicou, o formulário
submetido com seus parâmetros, e o arquivo baixado, **resumido no
instante em que chega**, antes de tocar qualquer pasta de trabalho.

Por que isso vale mais que um vídeo
-----------------------------------

Um vídeo mostra pixels. O registro aqui documenta a transação: qual
endereço respondeu, o que foi pedido, quanto veio e qual o resumo dos
bytes recebidos. As duas coisas se somam — a gravação de tela roda junto
e o termo cruza uma com a outra pelo horário —, mas é o registro
estruturado que resiste ao exame.

Como os cliques são captados
----------------------------

Não há como o programa saber, de fora, no que a pessoa clicou dentro da
página. Injeta-se então um trecho de código na página que escuta cliques
e envios de formulário e os anuncia pelo console do navegador, com um
prefixo próprio; o programa lê essas mensagens e descarta o resto.

Campo de senha nunca é registrado. Campo oculto é — porque é neles que
os sistemas costumam guardar os parâmetros de verdade da consulta, e é
justamente o parâmetro que se quer demonstrar depois.
"""

from __future__ import annotations

import datetime
import hashlib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .gravacao_core import (Contexto, Resultado, data_br, formatar_tamanho,
                            ler_contexto, sha256)

#: Prefixo das mensagens que o código injetado manda pelo console. Nada
#: que não comece assim é lido.
MARCA = "TEMIS::"

#: Tipos de evento da linha do tempo.
ABERTURA = "abertura"
NAVEGACAO = "navegacao"
CARREGADA = "carregada"
CLIQUE = "clique"
FORMULARIO = "formulario"
DOWNLOAD = "download"
ANOTACAO = "anotacao"
FALHA = "falha"
ENCERRAMENTO = "encerramento"

ROTULO_EVENTO = {
    ABERTURA: "Início da diligência",
    NAVEGACAO: "Navegação",
    CARREGADA: "Página carregada",
    CLIQUE: "Clique",
    FORMULARIO: "Consulta submetida",
    DOWNLOAD: "Arquivo recebido",
    ANOTACAO: "Anotação do operador",
    FALHA: "Falha",
    ENCERRAMENTO: "Encerramento da diligência",
}

#: Código injetado em toda página, inclusive em quadros internos.
#:
#: Roda no mundo principal porque precisa enxergar os mesmos elementos
#: que o usuário vê. Escuta na fase de captura (`true` no terceiro
#: argumento) para que um `stopPropagation` da própria página não o
#: silencie.
ESPIA_JS = r"""
(function () {
  if (window.__temis_espia) { return; }
  window.__temis_espia = true;

  function rotulo(el) {
    if (!el) { return ''; }
    var t = el.innerText || el.value || el.getAttribute('aria-label') ||
            el.getAttribute('title') || el.name || el.id || '';
    return String(t).replace(/\s+/g, ' ').trim().slice(0, 90);
  }

  document.addEventListener('click', function (ev) {
    try {
      var el = ev.target;
      var alvo = (el && el.closest)
        ? (el.closest('a,button,input[type=submit],input[type=button],' +
                      '[role=button],[onclick]') || el)
        : el;
      console.log('TEMIS::clique::' + ((alvo && alvo.tagName) || '') +
                  '::' + rotulo(alvo) + '::' + ((alvo && alvo.href) || ''));
    } catch (e) { }
  }, true);

  document.addEventListener('submit', function (ev) {
    try {
      var f = ev.target, campos = [], i, c;
      for (i = 0; i < f.elements.length; i++) {
        c = f.elements[i];
        if (!c.name) { continue; }
        if (c.type === 'password') { continue; }
        if (c.type === 'checkbox' || c.type === 'radio') {
          if (!c.checked) { continue; }
        }
        campos.push(c.name + '=' + String(c.value || '').slice(0, 140));
      }
      console.log('TEMIS::formulario::' + (f.getAttribute('action') || '') +
                  '::' + (f.method || 'get') + '::' + campos.join(' | '));
    } catch (e) { }
  }, true);
})();
"""


# ─────────────────────────────────────────
#  MODELO
# ─────────────────────────────────────────

@dataclass
class Evento:
    """Um passo da diligência."""

    tipo: str
    descricao: str
    quando: str = ""
    decorrido: float = 0.0
    url: str = ""
    detalhe: str = ""

    @property
    def rotulo(self) -> str:
        return ROTULO_EVENTO.get(self.tipo, self.tipo)

    @property
    def relogio(self) -> str:
        s = int(self.decorrido)
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


@dataclass
class Baixado:
    """Um arquivo recebido do sistema durante a diligência."""

    nome: str = ""
    caminho: str = ""
    url: str = ""
    tipo_mime: str = ""
    tamanho: int = 0
    sha256: str = ""
    quando: str = ""
    decorrido: float = 0.0
    erro: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.sha256) and not self.erro


@dataclass
class Sessao:
    """Uma diligência inteira."""

    pasta: str = ""
    inicio: str = ""
    fim: str = ""
    eventos: list[Evento] = field(default_factory=list)
    baixados: list[Baixado] = field(default_factory=list)
    video: Resultado | None = None
    contexto: Contexto | None = None
    #: Falhas do próprio registro — não podem sumir em silêncio.
    erros: list[str] = field(default_factory=list)
    _t0: float = 0.0

    def comecar(self, pasta: str | Path):
        self.pasta = str(pasta)
        Path(pasta).mkdir(parents=True, exist_ok=True)
        self.contexto = ler_contexto()
        self._t0 = time.time()
        self.inicio = datetime.datetime.now().astimezone().isoformat(
            timespec="seconds")
        self.anotar(ABERTURA, "Sessão de extração iniciada")

    def encerrar(self):
        self.fim = datetime.datetime.now().astimezone().isoformat(
            timespec="seconds")
        self.anotar(ENCERRAMENTO, "Sessão de extração encerrada")

    @property
    def ativa(self) -> bool:
        return bool(self.inicio) and not self.fim

    @property
    def decorrido(self) -> float:
        return (time.time() - self._t0) if self._t0 else 0.0

    def anotar(self, tipo: str, descricao: str, url: str = "",
               detalhe: str = "") -> Evento:
        # A limpeza acontece aqui, e não em cada chamador: é a única
        # porta de entrada da linha do tempo, e credencial que escape
        # dela vai parar no termo.
        e = Evento(
            tipo=tipo, descricao=descricao, url=limpar_url(url),
            detalhe=detalhe,
            quando=datetime.datetime.now().astimezone().isoformat(
                timespec="seconds"),
            decorrido=self.decorrido)
        self.eventos.append(e)
        return e

    # ── contagens, para o resumo ──────────
    def quantos(self, tipo: str) -> int:
        return sum(1 for e in self.eventos if e.tipo == tipo)

    @property
    def paginas_visitadas(self) -> list[str]:
        vistas: list[str] = []
        for e in self.eventos:
            if e.tipo == NAVEGACAO and e.url and e.url not in vistas:
                vistas.append(e.url)
        return vistas

    @property
    def bons(self) -> list[Baixado]:
        return [b for b in self.baixados if b.ok]


#: Nomes de parâmetro cujo valor nunca entra no registro.
#:
#: Isto não é zelo excessivo. O código injetado já pula campo de senha,
#: mas quando o formulário é submetido por GET o próprio navegador põe
#: **todos** os campos na barra de endereço — inclusive a senha —, e o
#: endereço é registrado. Descobriu-se assim: um sistema de teste com
#: formulário GET e campo de senha, e a senha em claro no termo.
SIGILOSOS = ("senha", "password", "passwd", "pwd", "secret", "token",
             "credential", "credencial", "authorization", "auth",
             "apikey", "api_key", "access_key", "chave_acesso")

SUPRIMIDO = "[suprimido]"


def limpar_url(url: str) -> str:
    """Suprime, no endereço, o valor de parâmetro que pareça credencial.

    O nome do parâmetro permanece — ele é parte do que se quer
    demonstrar; some apenas o valor.
    """
    if not url or "?" not in url:
        return url
    try:
        base, _, resto = url.partition("?")
        consulta, marca, fragmento = resto.partition("#")

        def trocar(m):
            nome, valor = m.group(1), m.group(2)
            achatado = nome.lower()
            if valor and any(s in achatado for s in SIGILOSOS):
                return f"{nome}={SUPRIMIDO}"
            return m.group(0)

        # Substituição cirúrgica, e não reconstrução com `urlencode`: o
        # endereço vai impresso no termo e refazê-lo reescrevia o que não
        # precisava — uma data virava `01%2F01%2F2026` e ficava ilegível
        # justamente para quem tem de conferir.
        limpa = re.sub(r"([^&=?]+)=([^&#]*)", trocar, consulta)
        return base + "?" + limpa + (marca + fragmento if marca else "")
    except Exception:                                   # noqa: BLE001
        # Endereço estranho não pode impedir o registro — mas também não
        # pode entrar sem passar por aqui.
        return url.split("?", 1)[0] + "?" + SUPRIMIDO


def ler_console(mensagem: str) -> tuple[str, str, str] | None:
    """Traduz uma mensagem do código injetado em (tipo, descrição, detalhe).

    Devolve None para tudo que não vier com a marca — a página tem os
    próprios `console.log` e eles não interessam ao registro.
    """
    if not mensagem.startswith(MARCA):
        return None
    partes = mensagem[len(MARCA):].split("::")
    genero = partes[0] if partes else ""

    if genero == "clique":
        etiqueta = partes[1] if len(partes) > 1 else ""
        rotulo = partes[2] if len(partes) > 2 else ""
        destino = limpar_url(partes[3] if len(partes) > 3 else "")
        alvo = rotulo or etiqueta or "elemento sem rótulo"
        descricao = f"Clique em “{alvo}”"
        if etiqueta and rotulo:
            descricao += f" ({etiqueta.lower()})"
        return (CLIQUE, descricao, destino)

    if genero == "formulario":
        destino = partes[1] if len(partes) > 1 else ""
        metodo = (partes[2] if len(partes) > 2 else "").upper()
        campos = partes[3] if len(partes) > 3 else ""
        descricao = "Consulta submetida"
        if destino:
            descricao += f" a {destino}"
        if metodo:
            descricao += f" ({metodo})"
        return (FORMULARIO, descricao, campos)

    return None


def registrar_baixado(sessao: Sessao, caminho: str | Path, url: str,
                      tipo_mime: str = "") -> Baixado:
    """Resume o arquivo assim que ele termina de chegar.

    É o elo mais forte da corrente: o resumo é calculado sobre os bytes
    que o sistema entregou, na própria máquina que os pediu, antes de o
    arquivo ser copiado, renomeado ou anexado a coisa alguma.
    """
    caminho = Path(caminho)
    b = Baixado(
        nome=caminho.name, caminho=str(caminho), url=limpar_url(url),
        tipo_mime=tipo_mime,
        quando=datetime.datetime.now().astimezone().isoformat(
            timespec="seconds"),
        decorrido=sessao.decorrido)
    try:
        b.tamanho = caminho.stat().st_size
        b.sha256 = sha256(caminho)
    except OSError as e:
        b.erro = f"{type(e).__name__}: {e}"
    sessao.baixados.append(b)
    sessao.anotar(
        DOWNLOAD,
        f"Arquivo recebido: {b.nome} ({formatar_tamanho(b.tamanho)})",
        url=url,
        detalhe=(f"SHA-256 {b.sha256}" if b.sha256 else b.erro))
    return b


def pasta_padrao() -> Path:
    return Path.home() / "Documents" / "Sistema Têmis" / "Extrações"


def nome_de_sessao(processo: str = "") -> str:
    agora = datetime.datetime.now()
    limpo = "".join(c if c.isalnum() else "-" for c in processo).strip("-")
    limpo = "-".join(p for p in limpo.split("-") if p)[:40]
    return f"extracao-{limpo + '-' if limpo else ''}{agora:%Y-%m-%d-%H%M%S}"


# ─────────────────────────────────────────
#  TERMO
# ─────────────────────────────────────────

INK = "#16233A"
CINZA = "#5B6B82"
FECHO = "Sem mais a relatar, encerro o presente termo."

RESSALVAS = (
    "O registro reproduz os passos executados nesta sessão, no navegador "
    "embutido do sistema, e o que foi recebido em resposta. Não alcança o "
    "funcionamento interno do sistema consultado, a integridade dos dados "
    "que ele mantém, nem operações realizadas fora desta sessão.",
    "O resumo criptográfico de cada arquivo recebido foi calculado nesta "
    "estação, sobre os bytes entregues pelo sistema, imediatamente após a "
    "conclusão da transferência. Ele permite aferir, a qualquer tempo, que "
    "o arquivo juntado aos autos é o mesmo que foi recebido — não atesta a "
    "correção do conteúdo extraído.",
    "As datas e horas são as do relógio desta estação e não foram "
    "atestadas por terceiro. Onde a precisão temporal for controvertida, "
    "cabe carimbo do tempo emitido por autoridade credenciada.",
    "Os campos de senha não são registrados, e o valor de parâmetro de "
    "endereço cujo nome indique credencial é substituído por “[suprimido]”. "
    "Os demais campos submetidos, inclusive os ocultos, constam do registro "
    "por serem os parâmetros da consulta.",
)


@dataclass
class TermoExtracao:
    """Dados da peça."""

    nome: str = ""
    matricula: str = ""
    lotacao: str = ""
    cargo: str = "Servidor"
    tipo_processo: str = "IPS"
    numero_processo: str = ""
    dia: int = 1
    mes: int = 1
    ano: int = 2026
    solicitacao: str = ""
    objeto: str = ""
    sistema: str = ""
    sessao: Sessao | None = None


def intro_extracao(t: TermoExtracao) -> str:
    from .hash_core import ARTIGO_PROCESSO, MESES
    artigo = ARTIGO_PROCESSO.get(t.tipo_processo, "da")
    mes = MESES[t.mes - 1]
    quando = (f"Ao 1º dia do mês de {mes} de {t.ano}" if t.dia == 1
              else f"Aos {t.dia} dias do mês de {mes} de {t.ano}")
    pedido = (f", em atendimento à solicitação {t.solicitacao}"
              if t.solicitacao else "")
    return (
        f"{quando}, eu, {t.cargo} {t.nome}, matrícula {t.matricula}, "
        f"lotado(a) no(a) {t.lotacao}, visando instruir os autos "
        f"{artigo} {t.tipo_processo} nº {t.numero_processo}{pedido}, "
        f"declaro que procedi à extração de dados no sistema adiante "
        f"identificado, com registro de cada passo executado e do resumo "
        f"criptográfico de cada arquivo recebido."
    )


def validar_termo(t: TermoExtracao) -> list[str]:
    faltando = []
    for valor, rotulo in ((t.nome, "Nome completo"),
                          (t.matricula, "Matrícula"),
                          (t.lotacao, "Lotação"),
                          (t.numero_processo, "Número do processo"),
                          (t.objeto, "Objeto da extração"),
                          (t.sistema, "Sistema consultado")):
        if not str(valor).strip():
            faltando.append(rotulo)
    return faltando


def _cel(texto, alinhar: str = "left", fonte: str = "",
         tamanho: str = "") -> str:
    import html as _html
    abre = f'<font color="{INK}"'
    if fonte:
        abre += f' face="{fonte}"'
    if tamanho:
        abre += f' size="{tamanho}"'
    return (f'<td align="{alinhar}">{abre}>'
            f"{_html.escape(str(texto))}</font></td>")


def _quadro_par(linhas, largura: str = "34%") -> str:
    corpo = "".join(f"<tr>{_cel(r)}{_cel(v)}</tr>" for r, v in linhas if v)
    return (
        '<table width="100%" cellspacing="0" cellpadding="5" border="1" '
        'style="border-collapse:collapse; font-size:9.5pt;">'
        f'<tr style="background-color:#0a2442; color:#ffd633;">'
        f'<th width="{largura}">Item</th><th>Conteúdo</th></tr>'
        f"{corpo}</table>")


def _quadro_linha_do_tempo(s: Sessao) -> str:
    import html as _html
    linhas = []
    for e in s.eventos:
        detalhe = ""
        if e.url:
            detalhe += f'<font color="{CINZA}" size="1">{_html.escape(e.url)}'\
                       f"</font>"
        if e.detalhe:
            if detalhe:
                detalhe += "<br/>"
            detalhe += (f'<font color="{CINZA}" size="1">'
                        f"{_html.escape(e.detalhe)}</font>")
        linhas.append(
            "<tr>"
            + _cel(e.relogio, "center", "Courier New", "1")
            + _cel(e.rotulo, "center")
            + f'<td><font color="{INK}">{_html.escape(e.descricao)}</font>'
            + (f"<br/>{detalhe}" if detalhe else "")
            + "</td></tr>")
    return (
        '<table width="100%" cellspacing="0" cellpadding="4" border="1" '
        'style="border-collapse:collapse; font-size:8.5pt;">'
        '<tr style="background-color:#0a2442; color:#ffd633;">'
        '<th width="11%">Decorrido</th><th width="19%">Ato</th>'
        '<th width="70%">Descrição</th></tr>'
        f"{''.join(linhas)}</table>")


def _quadro_baixados(s: Sessao) -> str:
    linhas = []
    for i, b in enumerate(s.bons, 1):
        linhas.append(
            "<tr>"
            + _cel(i, "center")
            + _cel(b.nome)
            + _cel(formatar_tamanho(b.tamanho), "center")
            + _cel(data_br(b.quando), "center")
            + "</tr><tr>"
            + _cel("", "center")
            + f'<td colspan="3"><font color="{CINZA}" size="1">Origem: '
              f"{b.url or '—'}</font><br/>"
              f'<font color="{INK}" face="Courier New" size="1">'
              f"SHA-256: {b.sha256}</font></td></tr>")
    return (
        '<table width="100%" cellspacing="0" cellpadding="4" border="1" '
        'style="border-collapse:collapse; font-size:8.5pt;">'
        '<tr style="background-color:#0a2442; color:#ffd633;">'
        '<th width="4%">Nº</th><th width="46%">Arquivo</th>'
        '<th width="16%">Tamanho</th><th width="34%">Recebido em</th></tr>'
        f"{''.join(linhas)}</table>")


def build_html(t: TermoExtracao) -> str:
    """Termo em HTML, para exibir e exportar."""
    from ..impressao import cabecalho_html
    import html as _html
    e = _html.escape
    s = t.sessao or Sessao()

    partes = [
        "<html><body style=\"font-family:'Segoe UI',Arial,sans-serif; "
        'color:#16233a;">',
        cabecalho_html(),
        '<div align="center" style="margin-bottom:18px;">'
        '<b style="font-size:14pt; letter-spacing:0.5px;">'
        "Termo de Extração de Dados em Sistema Informatizado</b></div>",
        "<hr/>",
        f'<p align="justify" style="font-size:11pt; line-height:160%;">'
        f"{e(intro_extracao(t))}</p>",
        '<p style="font-size:11pt;"><b>1. Objeto e sistema</b></p>',
        _quadro_par([
            ("Sistema consultado", t.sistema),
            ("Objeto da extração", t.objeto),
            ("Solicitação atendida", t.solicitacao),
            ("Início da diligência", data_br(s.inicio)),
            ("Encerramento", data_br(s.fim)),
        ]),
    ]

    # ── estação ───────────────────────────
    partes.append('<p style="font-size:11pt;">'
                  "<b>2. Estação em que se realizou a extração</b></p>")
    if s.contexto is not None:
        partes.append(_quadro_par(s.contexto.linhas()))
    partes.append(
        '<p align="justify" style="font-size:10.5pt; line-height:150%; '
        'margin-top:8px;">Os dados acima foram lidos da própria estação no '
        "instante em que a diligência teve início.</p>")

    # ── arquivos recebidos ────────────────
    partes.append('<p style="font-size:11pt;">'
                  "<b>3. Arquivos recebidos</b></p>")
    if s.bons:
        partes.append(_quadro_baixados(s))
        partes.append(
            '<p align="justify" style="font-size:10.5pt; line-height:150%; '
            'margin-top:8px;">'
            "O resumo criptográfico de cada arquivo foi calculado nesta "
            "estação, sobre os bytes entregues pelo sistema, assim que a "
            "transferência se concluiu — antes de qualquer cópia, "
            "renomeação ou anexação.</p>")
    else:
        partes.append(
            '<p align="justify" style="font-size:10.5pt;">'
            "Não houve recebimento de arquivo nesta diligência.</p>")

    # ── gravação ──────────────────────────
    n = 4
    if s.video is not None and s.video.sha256:
        v = s.video
        partes.append(f'<p style="font-size:11pt;"><b>{n}. Registro '
                      f"audiovisual da diligência</b></p>")
        partes.append(_quadro_par([
            ("Arquivo", Path(v.arquivo).name),
            ("Período", f"{data_br(v.inicio)} a {data_br(v.fim)}"),
            ("Duração", v.duracao),
            ("Características",
             f"{v.largura}×{v.altura}, {v.quadros} quadros/s, "
             + ("com áudio" if v.com_audio else "sem áudio")),
            ("Tamanho", formatar_tamanho(v.tamanho)),
            ("SHA-256", v.sha256),
        ]))
        partes.append(
            '<p align="justify" style="font-size:10.5pt; line-height:150%; '
            'margin-top:8px;">A gravação correu simultaneamente à '
            "diligência; o contador de tempo decorrido impresso na imagem "
            "corresponde à coluna homônima da relação de atos adiante.</p>")
        n += 1

    # ── linha do tempo ────────────────────
    partes.append(f'<p style="font-size:11pt;"><b>{n}. Relação dos atos '
                  f"praticados</b></p>")
    partes.append(_quadro_linha_do_tempo(s))
    n += 1

    if s.erros:
        partes.append(f'<p align="justify" style="font-size:10.5pt; '
                      f'line-height:150%;">Falhas ocorridas no próprio '
                      f"registro: {e('; '.join(s.erros[:6]))}.</p>")

    # ── ressalvas ─────────────────────────
    partes.append(f'<p style="font-size:11pt;"><b>{n}. Ressalvas</b></p>')
    partes += [f'<p align="justify" style="font-size:10.5pt; '
               f'line-height:150%;">{e(linha)}</p>' for linha in RESSALVAS]

    partes.append(f'<p align="justify" style="font-size:11pt; '
                  f'margin-top:18px;">{FECHO}</p>')
    partes.append(
        '<br/><br/><div align="center" style="margin-top:36px;">'
        "______________________________________<br/>"
        f"<b>{e(t.nome)}</b><br/>"
        f'<span style="font-size:10pt;">{e(t.cargo)}</span>'
        + (f'<br/><span style="font-size:10pt;">Matrícula {e(t.matricula)}'
           f"</span>" if t.matricula else "")
        + "</div></body></html>")
    return "\n".join(partes)


def build_text(t: TermoExtracao) -> str:
    """Termo em texto puro."""
    s = t.sessao or Sessao()
    L = ["TERMO DE EXTRAÇÃO DE DADOS EM SISTEMA INFORMATIZADO", "",
         intro_extracao(t), "", "1. OBJETO E SISTEMA", "",
         f"Sistema consultado: {t.sistema}",
         f"Objeto da extração: {t.objeto}"]
    if t.solicitacao:
        L.append(f"Solicitação atendida: {t.solicitacao}")
    L.append(f"Início: {data_br(s.inicio)}")
    L.append(f"Encerramento: {data_br(s.fim)}")

    L += ["", "2. ESTAÇÃO EM QUE SE REALIZOU A EXTRAÇÃO", ""]
    if s.contexto is not None:
        for rotulo, valor in s.contexto.linhas():
            L.append(f"{rotulo}: {valor}")

    L += ["", "3. ARQUIVOS RECEBIDOS", ""]
    if s.bons:
        for i, b in enumerate(s.bons, 1):
            L.append(f"{i}. {b.nome}  ({formatar_tamanho(b.tamanho)})")
            L.append(f"   Origem: {b.url or '—'}")
            L.append(f"   Recebido em: {data_br(b.quando)}")
            L.append(f"   SHA-256: {b.sha256}")
            L.append("")
    else:
        L += ["Não houve recebimento de arquivo nesta diligência.", ""]

    n = 4
    if s.video is not None and s.video.sha256:
        v = s.video
        L += [f"{n}. REGISTRO AUDIOVISUAL DA DILIGÊNCIA", "",
              f"Arquivo: {Path(v.arquivo).name}",
              f"Período: {data_br(v.inicio)} a {data_br(v.fim)}",
              f"Duração: {v.duracao}",
              f"Tamanho: {formatar_tamanho(v.tamanho)}",
              f"SHA-256: {v.sha256}", ""]
        n += 1

    L += [f"{n}. RELAÇÃO DOS ATOS PRATICADOS", ""]
    for ev in s.eventos:
        L.append(f"  [{ev.relogio}] {ev.rotulo}: {ev.descricao}")
        if ev.url:
            L.append(f"             {ev.url}")
        if ev.detalhe:
            L.append(f"             {ev.detalhe}")
    n += 1

    L += ["", f"{n}. RESSALVAS", ""] + [f"  - {x}" for x in RESSALVAS]
    L += ["", FECHO, "", "_" * 40, t.nome, t.cargo]
    if t.matricula:
        L.append(f"Matrícula {t.matricula}")
    return "\n".join(L)
