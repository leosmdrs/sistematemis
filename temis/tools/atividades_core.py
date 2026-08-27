"""
Relatório de Atividades — o que se fez, entre abrir e fechar o sistema.

Cada execução do Têmis é uma **sessão**: começa quando a janela abre e
termina quando ela fecha. No intervalo, a ferramenta anota sozinha o que
aconteceu — quais instrumentos foram abertos, por quanto tempo, e o que
cada um relatou ao concluir — e ao fim compõe o relatório.

Três decisões de fundo, e as razões:

**Ninguém precisa ligá-la.** Registro que depende de alguém lembrar de
ligar é registro que falta justamente no dia em que faria falta. Ela sobe
com o sistema e encerra com ele.

**Grava enquanto corre, não só no fim.** Queda de energia, travamento,
encerramento à força — em qualquer deles, o que já aconteceu tem de estar
em disco. A sessão é regravada a cada anotação e a cada minuto, por
arquivo temporário: uma queda no meio da escrita não corrompe o que já
havia. O relatório de uma sessão interrompida sai marcado como tal, e não
se faz passar por sessão encerrada.

**Não sai da máquina.** O sistema promete, no portal, que nada é enviado
a servidor algum, e esta ferramenta é a que mais poderia desmentir isso.
Ela grava em pasta local, mostra ao próprio operador tudo o que anotou a
seu respeito, e permite apagar. Registro de atividade que o registrado
não pode ler é vigilância; que ele pode ler e apagar é documentação.

O que **não** é anotado, de propósito: conteúdo de arquivo, texto
digitado, endereço visitado ou nome de pessoa investigada. A ferramenta
registra *que* um instrumento foi usado e *o que ele próprio relatou* ao
concluir — não o material da apuração. Esse material está nos termos das
respectivas ferramentas, que são as peças dos autos.
"""

from __future__ import annotations

import datetime
import getpass
import html
import hashlib
import json
import os
import platform
import socket
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .. import __version__

#: Tudo o que é gravado passa por aqui. Uma pasta só, sob os documentos
#: do usuário, para que ele encontre e possa apagar sem procurar.
def pasta_padrao() -> Path:
    return Path.home() / "Documents" / "Sistema Têmis" / "Relatórios de Atividade"


#: De quanto em quanto tempo a sessão em curso é regravada, mesmo sem
#: nada novo. Um minuto: é o que se aceita perder num corte de energia.
INTERVALO_GRAVACAO = 60.0

#: Mensagens de status que não valem anotação — ruído de navegação, não
#: ato praticado. Compara-se sem acento e sem caixa.
RUIDO = (
    "selecione uma ferramenta",
    "pronto",
    "",
)

#: Começos que denunciam instrução, e não relato. Uma ferramenta que
#: acaba de abrir diz "Abra um PDF para começar"; isso é a tela
#: conversando com quem chegou, não ato praticado — e num relatório
#: analítico entra como ruído que empurra o que importa para baixo.
#:
#: Filtrar pelo início do texto é grosseiro, e assumido: o critério é o
#: modo verbal, e português não o entrega sem análise. A lista cobre os
#: convites que as ferramentas de fato usam, e erra para o lado de
#: anotar demais — perder um ato seria pior do que guardar um convite.
RUIDO_INICIO = (
    "abra ", "selecione ", "escolha ", "arraste ", "clique ",
    "informe ", "digite ", "adicione ", "aguarde",
)


def _sem_acento(texto: str) -> str:
    tabela = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüçñ",
                           "aaaaaeeeeiiiiooooouuuucn")
    return texto.lower().translate(tabela)


@dataclass
class Uso:
    """Uma passagem por uma ferramenta.

    Não é "quantas vezes abriu": é cada abertura, com o instante e a
    permanência. Duas visitas de dois minutos e uma de quarenta contam
    histórias diferentes, e a soma sozinha esconde as duas.
    """

    chave: str
    nome: str
    abriu: str = ""
    fechou: str = ""
    segundos: float = 0.0


@dataclass
class Anotacao:
    """Algo que uma ferramenta relatou enquanto trabalhava."""

    quando: str
    ferramenta: str
    texto: str
    #: O elo com a anotação anterior: resumo do elo dela somado ao
    #: conteúdo desta. Alterar, remover ou inserir uma linha no meio
    #: rompe a corrente a partir dali, e a conferência aponta onde.
    elo: str = ""


def elo_de(anterior: str, quando: str, ferramenta: str, texto: str) -> str:
    """O elo de uma anotação, a partir do elo da anterior.

    Os separadores são caracteres de controle para que nenhum conteúdo
    consiga imitá-los: sem isso, mover texto de um campo para o outro
    produziria o mesmo elo, e a corrente deixaria passar a alteração.
    """
    h = hashlib.sha256()
    for parte in (anterior, quando, ferramenta, texto):
        h.update(parte.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


@dataclass
class Sessao:
    """Uma execução do sistema, do abrir ao fechar."""

    identificador: str = ""
    versao: str = ""
    inicio: str = ""
    fim: str = ""
    encerrada: bool = False
    #: Quem operava, pela identificação guardada — se houver. É conveniência
    #: de leitura, não prova de autoria: o perfil pode estar em branco ou
    #: pertencer a outra pessoa que usou a estação.
    operador: dict = field(default_factory=dict)
    maquina: dict = field(default_factory=dict)
    usos: list[Uso] = field(default_factory=list)
    anotacoes: list[Anotacao] = field(default_factory=list)
    #: Falhas do próprio registrador. Se ele não conseguiu anotar algo,
    #: isso tem de aparecer no relatório — silêncio aqui seria pior do
    #: que a falha.
    erros: list[str] = field(default_factory=list)
    #: Resumo de fecho, calculado no encerramento sobre a sessão inteira.
    #: É ele que se cita fora daqui — num termo, num ofício —, e é dessa
    #: citação que vem a força do registro: publicado o resumo, qualquer
    #: alteração posterior no arquivo passa a ser detectável contra ele.
    elo_final: str = ""

    # ── leitura ──────────────────────────────
    @property
    def duracao(self) -> float:
        try:
            fim = (datetime.datetime.fromisoformat(self.fim) if self.fim
                   else datetime.datetime.now().astimezone())
            return max(0.0, (fim - datetime.datetime.fromisoformat(
                self.inicio)).total_seconds())
        except (ValueError, TypeError):
            return 0.0

    def por_ferramenta(self) -> list[tuple[str, int, float]]:
        """(nome, quantas aberturas, segundos somados), do maior ao menor."""
        soma: dict[str, list] = {}
        for u in self.usos:
            linha = soma.setdefault(u.nome, [0, 0.0])
            linha[0] += 1
            linha[1] += u.segundos
        return sorted(((nome, n, s) for nome, (n, s) in soma.items()),
                      key=lambda x: -x[2])


# ─────────────────────────────────────────
#  O REGISTRADOR
# ─────────────────────────────────────────

class Registrador:
    """Acompanha uma execução do sistema e grava o que observa.

    Vive no casco, não numa ferramenta: quem sabe que uma ferramenta foi
    aberta é a janela principal. A ferramenta homônima apenas **lê** o
    que este objeto escreve — de modo que o registro não depende de
    ninguém ter aberto a tela dela.
    """

    def __init__(self, pasta: Path | None = None):
        self.pasta = Path(pasta) if pasta else pasta_padrao()
        self.sessao = Sessao()
        self._aberta: Uso | None = None
        self._desde: datetime.datetime | None = None

    # ── ciclo ────────────────────────────────
    def iniciar(self) -> Sessao:
        agora = datetime.datetime.now().astimezone()
        self.sessao = Sessao(
            identificador=agora.strftime("%Y-%m-%d-%H%M%S"),
            versao=__version__,
            inicio=agora.isoformat(timespec="seconds"),
            operador=self._operador(),
            maquina=self._maquina(),
        )
        self.gravar()
        return self.sessao

    def abriu(self, chave: str, nome: str):
        """Uma ferramenta passou a ser a visível."""
        self.fechou()
        agora = datetime.datetime.now().astimezone()
        self._desde = agora
        self._aberta = Uso(chave=chave, nome=nome,
                           abriu=agora.isoformat(timespec="seconds"))
        self.sessao.usos.append(self._aberta)
        self.gravar()

    def fechou(self):
        """A ferramenta visível deixou de ser. Fecha a contagem dela."""
        if self._aberta is None or self._desde is None:
            return
        agora = datetime.datetime.now().astimezone()
        self._aberta.fechou = agora.isoformat(timespec="seconds")
        self._aberta.segundos = round(
            (agora - self._desde).total_seconds(), 1)
        self._aberta = None
        self._desde = None
        self.gravar()

    def anotar(self, ferramenta: str, texto: str):
        """Guarda o que uma ferramenta relatou, se valer registro."""
        texto = (texto or "").strip()
        simples = _sem_acento(texto)
        if simples in RUIDO or simples.startswith(RUIDO_INICIO):
            return
        # A mesma mensagem repetida em sequência é progresso de tela, não
        # ato novo — anotar cada uma encheria o relatório de eco.
        if (self.sessao.anotacoes
                and self.sessao.anotacoes[-1].texto == texto):
            return
        quando = datetime.datetime.now().astimezone().isoformat(
            timespec="seconds")
        corte = texto[:400]
        anterior = (self.sessao.anotacoes[-1].elo
                    if self.sessao.anotacoes else "")
        self.sessao.anotacoes.append(Anotacao(
            quando=quando, ferramenta=ferramenta, texto=corte,
            elo=elo_de(anterior, quando, ferramenta, corte)))
        self.gravar()

    def encerrar(self) -> Path | None:
        """Fecha a sessão e escreve o relatório. Devolve onde ele ficou."""
        self.fechou()
        self.sessao.fim = datetime.datetime.now().astimezone().isoformat(
            timespec="seconds")
        self.sessao.encerrada = True
        self.sessao.elo_final = fecho_de(self.sessao)
        self.gravar(forcar=True)
        try:
            destino = self.caminho_relatorio()
            destino.write_text(relatorio_html(self.sessao), encoding="utf-8")
            return destino
        except OSError as e:
            self.sessao.erros.append(f"relatório: {type(e).__name__}: {e}")
            self.gravar(forcar=True)
            return None

    # ── disco ────────────────────────────────
    def caminho_dados(self) -> Path:
        return self.pasta / f"sessao-{self.sessao.identificador}.json"

    def caminho_relatorio(self) -> Path:
        return self.pasta / f"atividades-{self.sessao.identificador}.html"

    def gravar(self, forcar: bool = False):
        """Regrava a sessão inteira. Nunca interrompe o sistema se falhar.

        Por arquivo temporário e substituição atômica: se a máquina cair
        no meio da escrita, o que já estava em disco continua íntegro.

        Sem economia de escrita: houve aqui um intervalo mínimo entre
        gravações, para agrupar rajadas de mensagens. Ele foi retirado —
        o arquivo tem alguns quilobytes, e a única razão desta ferramenta
        existir é que o registro esteja em disco quando a máquina cair. O
        `forcar` fica pelo encerramento, que grava sem depender de nada.
        """
        try:
            self.pasta.mkdir(parents=True, exist_ok=True)
            alvo = self.caminho_dados()
            tmp = alvo.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(asdict(self.sessao), ensure_ascii=False, indent=1),
                encoding="utf-8")
            tmp.replace(alvo)
        except OSError as e:
            erro = f"gravação: {type(e).__name__}: {e}"
            if erro not in self.sessao.erros:
                self.sessao.erros.append(erro)

    # ── contexto ─────────────────────────────
    def _operador(self) -> dict:
        try:
            from .. import perfil
            p = perfil.ler()
            return {c: getattr(p, c, "") for c in perfil.CAMPOS}
        except Exception as e:                              # noqa: BLE001
            self.sessao.erros.append(f"perfil: {type(e).__name__}: {e}")
            return {}

    def _maquina(self) -> dict:
        """A estação e a rede, no início da sessão.

        Reaproveita o levantamento da Gravação de Tela em vez de repetir:
        duas versões da mesma coisa divergem com o tempo, e aí dois termos
        do mesmo processo passam a descrever a mesma estação de formas
        diferentes.
        """
        dados = {}
        try:
            from .gravacao_core import ler_contexto
            dados = asdict(ler_contexto())
        except Exception as e:                              # noqa: BLE001
            self.sessao.erros.append(f"contexto: {type(e).__name__}: {e}")
            dados = {"usuario": getpass.getuser(),
                     "estacao": socket.gethostname(),
                     "sistema": platform.platform()}
        dados["python"] = sys.version.split()[0]
        dados["processadores"] = os.cpu_count() or 0
        dados["arquitetura"] = platform.machine()
        return dados


# ─────────────────────────────────────────
#  LEITURA DAS SESSÕES GRAVADAS
# ─────────────────────────────────────────

def fecho_de(s: Sessao) -> str:
    """O resumo da sessão inteira, para ser citado fora dela.

    Cobre a identificação, a máquina, quem operava, cada passagem por
    ferramenta e cada anotação, na ordem em que estão. Não cobre a si
    mesmo, evidentemente — por isso é calculado uma vez, no encerramento.
    """
    h = hashlib.sha256()

    def somar(*partes):
        for parte in partes:
            h.update(str(parte).encode("utf-8"))
            h.update(b"\x1f")
        h.update(b"\x1e")

    somar(s.identificador, s.versao, s.inicio, s.fim)
    somar(*(f"{k}={v}" for k, v in sorted(s.maquina.items())))
    somar(*(f"{k}={v}" for k, v in sorted(s.operador.items())))
    for u in s.usos:
        somar(u.chave, u.nome, u.abriu, u.fechou, round(u.segundos, 3))
    for a in s.anotacoes:
        somar(a.quando, a.ferramenta, a.texto, a.elo)
    return h.hexdigest()


def conferir(s: Sessao) -> tuple:
    """Confere a corrente e o fecho. Devolve (situação, explicação).

    A situação é "integro", "rompido" ou "aberto" — a última para a
    sessão que não chegou a ser encerrada, e que por isso não tem fecho a
    conferir. Sessão interrompida não é sessão adulterada, e chamar uma
    pela outra seria acusar o que não se constatou.

    **O alcance disto precisa ficar claro, e o relatório o diz.** A
    corrente detecta a alteração feita à mão sobre o arquivo: mudar uma
    linha, remover outra, inserir uma terceira. Não detém quem reproduza
    o algoritmo e recalcule a corrente inteira, porque não há aqui chave
    que só o sistema conheça. A força do registro vem de outro lugar: do
    resumo de fecho ser citado numa peça que circula. Publicado ele, a
    alteração posterior passa a ser detectável contra o que foi
    publicado — e aí não adianta recalcular.
    """
    anterior = ""
    for i, a in enumerate(s.anotacoes, 1):
        if a.elo != elo_de(anterior, a.quando, a.ferramenta, a.texto):
            return "rompido", (
                f"a corrente se rompe na anotação {i} de "
                f"{len(s.anotacoes)}, de {a.quando}")
        anterior = a.elo
    if not s.encerrada or not s.elo_final:
        return "aberto", "a sessão não foi encerrada, e não tem fecho a conferir"
    if fecho_de(s) != s.elo_final:
        return "rompido", (
            "a corrente das anotações está inteira, mas o resumo de fecho "
            "não corresponde ao conteúdo da sessão")
    return "integro", ""


def sessoes(pasta: Path | None = None) -> list[Sessao]:
    """Todas as sessões em disco, da mais recente para a mais antiga."""
    pasta = Path(pasta) if pasta else pasta_padrao()
    achadas = []
    for arquivo in sorted(pasta.glob("sessao-*.json"), reverse=True):
        s = ler_sessao(arquivo)
        if s is not None:
            achadas.append(s)
    return achadas


def ler_sessao(arquivo: Path) -> Sessao | None:
    """Lê uma sessão gravada. Arquivo defeituoso é ignorado, não explode."""
    try:
        dados = json.loads(Path(arquivo).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(dados, dict):
        return None
    try:
        return Sessao(
            identificador=str(dados.get("identificador", "")),
            versao=str(dados.get("versao", "")),
            inicio=str(dados.get("inicio", "")),
            fim=str(dados.get("fim", "")),
            encerrada=bool(dados.get("encerrada", False)),
            operador=dados.get("operador") or {},
            maquina=dados.get("maquina") or {},
            usos=[Uso(**u) for u in dados.get("usos", [])
                  if isinstance(u, dict)],
            anotacoes=[Anotacao(**a) for a in dados.get("anotacoes", [])
                       if isinstance(a, dict)],
            erros=list(dados.get("erros", [])),
        )
    except TypeError:
        return None


# ─────────────────────────────────────────
#  APRESENTAÇÃO
# ─────────────────────────────────────────

def duracao_por_extenso(segundos: float) -> str:
    segundos = int(max(0, segundos))
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    if h:
        return f"{h}h{m:02d}min"
    if m:
        return f"{m}min{s:02d}s"
    return f"{s}s"


def _hora(iso: str) -> str:
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return iso or "—"


def data_br(iso: str) -> str:
    try:
        return datetime.datetime.fromisoformat(iso).strftime(
            "%d/%m/%Y às %H:%M:%S")
    except (ValueError, TypeError):
        return iso or "—"


#: Rótulos dos campos da máquina, na ordem em que interessam ler. O que
#: não estiver aqui não vai ao relatório: campo sem rótulo vira sigla
#: solta numa peça que alguém vai ler daqui a um ano.
CAMPOS_MAQUINA = (
    ("usuario", "Usuário do Windows"),
    ("dominio", "Domínio"),
    ("estacao", "Nome da estação"),
    ("sistema", "Sistema operacional"),
    ("arquitetura", "Arquitetura"),
    ("processadores", "Núcleos de processamento"),
    ("fabricante", "Fabricante"),
    ("modelo", "Modelo"),
    ("serie", "Número de série"),
    ("mac", "Endereço físico (MAC)"),
    ("fuso", "Fuso horário"),
    ("python", "Interpretador"),
)


#: O que a corrente prova, e o que ela não prova. Vai impresso junto do
#: veredito: um registro que se apresentasse como inviolável prometeria o
#: que não tem, e é a promessa exagerada que derruba a peça, não a
#: limitação declarada.
ALCANCE_CORRENTE = (
    "Cada anotação carrega o resumo criptográfico da anterior, de modo que "
    "alterar, remover ou inserir uma linha rompe a corrente a partir dali. "
    "A conferência acima percorre essa corrente e o resumo de fecho, "
    "calculado sobre a sessão inteira no encerramento.",
    "O alcance disto é o seguinte, e convém que fique dito: a corrente "
    "detecta a alteração feita sobre o arquivo, e não detém quem reproduza "
    "o algoritmo e recalcule a corrente inteira — não há aqui chave que só "
    "o sistema conheça. A força do registro está em o resumo de fecho ser "
    "citado fora deste arquivo, num termo ou num ofício: publicado ele, "
    "qualquer alteração posterior passa a ser detectável contra o que foi "
    "publicado, e recalcular deixa de adiantar.",
)


def _bloco_integridade(s: Sessao) -> str:
    """O veredito da conferência, e o resumo de fecho a citar."""
    import html as _h

    e = _h.escape
    situacao, explicacao = conferir(s)
    cores = {"integro": "#1B6E3C", "rompido": "#8A2B18", "aberto": "#5A6B85"}
    frases = {
        "integro": "A corrente das anotações está inteira e o resumo de "
                   "fecho corresponde ao conteúdo desta sessão.",
        "rompido": "ATENÇÃO — a conferência não fechou: " + explicacao + ".",
        "aberto": "A sessão não foi encerrada normalmente, e por isso não "
                  "tem resumo de fecho a conferir. A corrente das "
                  "anotações, até onde vai, está inteira.",
    }
    partes = ["<h2 style='font-size:12pt;margin-top:22px'>"
              "Integridade do registro</h2>",
              f"<p style='color:{cores.get(situacao, cores['aberto'])}'>"
              f"<b>{e(frases.get(situacao, ''))}</b></p>"]
    if s.elo_final:
        partes.append(
            "<p style='font-size:10pt'>Resumo de fecho (SHA-256):<br>"
            f"<code style='font-size:9pt'>{e(s.elo_final)}</code></p>")
    partes += [f"<p style='font-size:9pt'>{e(x)}</p>"
               for x in ALCANCE_CORRENTE]
    return "".join(partes)


def relatorio_html(s: Sessao) -> str:
    """A peça de leitura, em HTML — a mesma que vira PDF na impressão."""
    e = html.escape

    def linha(rotulo, valor):
        return (f"<tr><td width='34%'><b>{e(str(rotulo))}</b></td>"
                f"<td>{e(str(valor))}</td></tr>")

    from ..impressao import cabecalho_html

    partes = [cabecalho_html(),
              "<h2>Relatório de Atividades</h2>"]

    if not s.encerrada:
        partes.append(
            "<p><b>Sessão interrompida.</b> Este relatório foi composto a "
            "partir do registro gravado durante a execução, que não chegou "
            "a ser encerrada normalmente — o sistema pode ter sido fechado "
            "à força, ou a máquina desligada. O que consta abaixo é o que "
            "havia sido anotado até o último instante gravado.</p>")

    op = s.operador or {}
    if any((op.get(c) or "").strip() for c in op):
        partes.append("<h3>Operador</h3><table width='100%'>")
        partes.append(linha("Nome", op.get("nome") or "—"))
        if (op.get("cargo") or "").strip():
            partes.append(linha("Cargo", op["cargo"]))
        partes.append(linha("Matrícula", op.get("matricula") or "—"))
        partes.append(linha("Lotação", op.get("lotacao") or "—"))
        if (op.get("orgao") or "").strip():
            partes.append(linha("Órgão", op["orgao"]))
        partes.append("</table>")
        partes.append(
            "<p style='font-size:9pt'>A qualificação acima é a que estava "
            "guardada nesta estação no início da sessão. Ela identifica a "
            "configuração da máquina, não a autoria dos atos: cada termo "
            "produzido traz a qualificação que constava dele no momento de "
            "sua emissão.</p>")

    partes.append("<h3>Sessão</h3><table width='100%'>")
    partes += [
        linha("Início", data_br(s.inicio)),
        linha("Encerramento",
              data_br(s.fim) if s.fim else "não registrado"),
        linha("Duração", duracao_por_extenso(s.duracao)),
        linha("Versão do sistema", s.versao or "—"),
        linha("Ferramentas abertas", len(s.usos)),
        linha("Atos relatados", len(s.anotacoes)),
    ]
    partes.append("</table>")

    partes.append("<h3>Estação</h3><table width='100%'>")
    for chave, rotulo in CAMPOS_MAQUINA:
        valor = s.maquina.get(chave)
        if valor not in (None, "", 0, []):
            partes.append(linha(rotulo, valor))
    enderecos = s.maquina.get("enderecos") or []
    if enderecos:
        partes.append(linha("Endereços de rede", ", ".join(enderecos)))
    partes.append("</table>")

    resumo = s.por_ferramenta()
    if resumo:
        partes.append("<h3>Ferramentas utilizadas</h3>")
        partes.append("<table width='100%' border='1' cellspacing='0' "
                      "cellpadding='5' style='border-collapse:collapse'>")
        partes.append("<tr><td><b>Ferramenta</b></td>"
                      "<td><b>Aberturas</b></td><td><b>Tempo</b></td></tr>")
        for nome, quantas, segundos in resumo:
            partes.append(
                f"<tr><td>{e(nome)}</td><td>{quantas}</td>"
                f"<td>{duracao_por_extenso(segundos)}</td></tr>")
        partes.append("</table>")

    if s.usos:
        partes.append("<h3>Linha do tempo</h3>")
        partes.append("<table width='100%' border='1' cellspacing='0' "
                      "cellpadding='5' style='border-collapse:collapse'>")
        partes.append("<tr><td><b>Hora</b></td><td><b>Ferramenta</b></td>"
                      "<td><b>Permanência</b></td></tr>")
        for u in s.usos:
            partes.append(
                f"<tr><td>{_hora(u.abriu)}</td><td>{e(u.nome)}</td>"
                f"<td>{duracao_por_extenso(u.segundos)}"
                + ("" if u.fechou else " (aberta ao fim)") + "</td></tr>")
        partes.append("</table>")

    if s.anotacoes:
        partes.append("<h3>Atos relatados pelas ferramentas</h3>")
        partes.append(
            "<p style='font-size:9pt'>Cada linha é o que a própria "
            "ferramenta informou ao concluir uma operação. O conteúdo do "
            "material examinado não é registrado aqui — ele consta dos "
            "termos emitidos por cada ferramenta.</p>")
        partes.append("<table width='100%' border='1' cellspacing='0' "
                      "cellpadding='5' style='border-collapse:collapse'>")
        partes.append("<tr><td><b>Hora</b></td><td><b>Ferramenta</b></td>"
                      "<td><b>Relato</b></td></tr>")
        for a in s.anotacoes:
            partes.append(
                f"<tr><td>{_hora(a.quando)}</td><td>{e(a.ferramenta)}</td>"
                f"<td>{e(a.texto)}</td></tr>")
        partes.append("</table>")

    if s.erros:
        partes.append("<h3>Falhas do próprio registro</h3>")
        partes.append("<p>Constam por dever de transparência: indicam "
                      "trechos que podem não ter sido anotados.</p><ul>")
        partes += [f"<li>{e(x)}</li>" for x in s.erros]
        partes.append("</ul>")

    partes.append(_bloco_integridade(s))

    partes.append(
        "<p style='font-size:9pt'>Relatório composto automaticamente pelo "
        "Sistema Têmis, na própria estação, sem envio de dado algum a "
        "servidor externo. Registra o uso do sistema; não registra o "
        "conteúdo do material examinado.</p>")

    from ..impressao import documento_html, rodape_html
    # Sem motor declarado: este relatório não processa material, apenas
    # anota o que a sessão fez. O que ele precisa dizer é a versão do
    # sistema que o compôs — e é justamente ela que amarra os termos
    # emitidos na mesma sessão a este registro.
    partes.append(rodape_html())
    return documento_html("".join(partes), "Relatório de Atividades")
