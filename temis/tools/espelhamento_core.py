"""
Espelhamento de celular Android, registrado.

Serve à diligência em que alguém exibe o próprio aparelho — a conversa
que o denunciante mostra, o aplicativo cujo funcionamento se quer
demonstrar, o registro que o detentor apresenta. O celular é ligado por
cabo, a tela aparece no computador e a sessão inteira é gravada em
resolução nativa, com identificação do aparelho no termo.

O que isto **não** é
--------------------

Não é extração de dados de celular apreendido. Para funcionar, o
aparelho precisa estar destravado e com a depuração USB habilitada, o
que exige quem tenha a senha. Extração de dispositivo bloqueado é
perícia, e tem ferramenta própria.

Três alterações que o método provoca no aparelho
------------------------------------------------

Nenhuma delas é ocultável, e todas vão declaradas no termo:

1. **habilitar a depuração USB** é mudança de configuração, feita por
   quem detém o aparelho, e fica registrada nele;
2. **autorizar esta estação** grava a chave pública do computador na
   lista de máquinas confiáveis do celular;
3. **o espelhamento envia um componente ao aparelho** — o servidor do
   scrcpy, gravado em `/data/local/tmp` e executado enquanto dura a
   sessão.

Por isso o padrão é **somente observação**: o espelhamento não repassa
toque nem digitação ao aparelho. Observar o que alguém exibe é um ato;
operar o telefone de outra pessoa é outro, bem diferente, e a diferença
tem de aparecer na peça. Quem precisar do controle liga-o
expressamente, e o termo diz que foi ligado.

Sobre a gravação
----------------

O scrcpy grava em Matroska, e não em MP4, de propósito: se a sessão for
interrompida — cabo solto, aparelho desligado, programa encerrado à
força — o Matroska continua legível, enquanto um MP4 inacabado costuma
não abrir. Encerrada a sessão, o arquivo passa por uma segunda etapa que
acrescenta a faixa de contexto e produz o MP4 final.
"""

from __future__ import annotations

import datetime
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .gravacao_core import (Contexto, data_br, formatar_tamanho, ler_contexto,
                            medir, montar_faixa, sha256)
from .video_core import _SEM_JANELA

#: Onde o scrcpy e o adb ficam dentro do pacote.
PASTA_VENDOR = "scrcpy"

#: Estados que o adb informa para um aparelho conectado.
PRONTO = "device"
NAO_AUTORIZADO = "unauthorized"
INDISPONIVEL = "offline"

EXPLICACAO_ESTADO = {
    PRONTO: "pronto para espelhar",
    NAO_AUTORIZADO: (
        "aguardando autorização no aparelho — destrave a tela e toque em "
        "“Permitir” no aviso de depuração USB"),
    INDISPONIVEL: "conectado mas sem responder — reconecte o cabo",
}

#: Propriedades lidas do aparelho, e como aparecem no termo.
PROPRIEDADES = (
    ("ro.product.manufacturer", "Fabricante"),
    ("ro.product.model", "Modelo"),
    ("ro.product.name", "Nome do produto"),
    ("ro.build.version.release", "Versão do Android"),
    ("ro.build.version.sdk", "Nível de API"),
    ("ro.build.id", "Identificação da compilação"),
    ("ro.build.display.id", "Compilação"),
    ("ro.serialno", "Número de série"),
)


def _pasta_ferramentas() -> Path:
    """Onde estão o adb e o scrcpy, no pacote ou no projeto."""
    import sys
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)                    # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parents[2] / "vendor"
    return base / PASTA_VENDOR


def adb_path() -> Path | None:
    alvo = _pasta_ferramentas() / "adb.exe"
    return alvo if alvo.is_file() else None


def scrcpy_path() -> Path | None:
    alvo = _pasta_ferramentas() / "scrcpy.exe"
    return alvo if alvo.is_file() else None


def disponivel() -> bool:
    return adb_path() is not None and scrcpy_path() is not None


def diagnostico() -> str:
    if disponivel():
        return "scrcpy e adb presentes no pacote."
    return ("O espelhamento de celular não está disponível nesta "
            "instalação: scrcpy ou adb não foram encontrados.")


def _rodar(argumentos: list[str], tempo: int = 30) -> str:
    """Executa o adb e devolve a saída, sem levantar."""
    caminho = adb_path()
    if caminho is None:
        return ""
    try:
        r = subprocess.run([str(caminho)] + argumentos, capture_output=True,
                           text=True, timeout=tempo, creationflags=_SEM_JANELA,
                           encoding="utf-8", errors="replace")
        return r.stdout or ""
    except Exception:                                        # noqa: BLE001
        return ""


# ─────────────────────────────────────────
#  APARELHOS
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


@dataclass
class Aparelho:
    """Um celular ligado ao computador."""

    serie: str = ""
    estado: str = ""
    fabricante: str = ""
    modelo: str = ""
    android: str = ""
    api: str = ""
    build: str = ""
    serie_interna: str = ""
    propriedades: dict = field(default_factory=dict)

    @property
    def pronto(self) -> bool:
        return self.estado == PRONTO

    @property
    def rotulo(self) -> str:
        nome = " ".join(x for x in (self.fabricante, self.modelo) if x)
        if not nome:
            nome = self.serie
        estado = "" if self.pronto else f"  ({EXPLICACAO_ESTADO.get(self.estado, self.estado)})"
        androide = f" — Android {self.android}" if self.android else ""
        return f"{nome}{androide}{estado}"

    def linhas(self) -> list[tuple[str, str]]:
        """Pares (rótulo, valor) para o quadro do termo."""
        L = [("Identificador no barramento USB", self.serie)]
        for chave, rotulo in PROPRIEDADES:
            valor = self.propriedades.get(chave, "")
            if valor and valor != self.serie:
                L.append((rotulo, valor))
        return L


_LINHA_APARELHO = re.compile(r"^(\S+)\s+(device|unauthorized|offline)\b(.*)$")


def listar() -> list[Aparelho]:
    """Aparelhos que o adb enxerga, com o que já der para saber."""
    saida = _rodar(["devices", "-l"], tempo=40)
    achados: list[Aparelho] = []
    for linha in saida.splitlines():
        linha = linha.strip()
        if not linha or linha.lower().startswith("list of devices"):
            continue
        m = _LINHA_APARELHO.match(linha)
        if not m:
            continue
        a = Aparelho(serie=m.group(1), estado=m.group(2))
        # `adb devices -l` já traz modelo e produto para o aparelho pronto
        for pedaco in m.group(3).split():
            if pedaco.startswith("model:"):
                a.modelo = pedaco[6:].replace("_", " ")
        if a.pronto:
            detalhar(a)
        achados.append(a)
    return achados


def detalhar(a: Aparelho) -> Aparelho:
    """Lê as propriedades do aparelho. Só funciona com ele autorizado."""
    bruto = _rodar(["-s", a.serie, "shell", "getprop"], tempo=40)
    for linha in bruto.splitlines():
        m = re.match(r"\[([^\]]+)\]:\s*\[(.*)\]\s*$", linha.strip())
        if m:
            a.propriedades[m.group(1)] = m.group(2)
    p = a.propriedades
    a.fabricante = p.get("ro.product.manufacturer", a.fabricante)
    a.modelo = p.get("ro.product.model", a.modelo)
    a.android = p.get("ro.build.version.release", "")
    a.api = p.get("ro.build.version.sdk", "")
    a.build = p.get("ro.build.display.id", "") or p.get("ro.build.id", "")
    a.serie_interna = p.get("ro.serialno", "")
    return a


def encerrar_servidor():
    """Derruba o processo de fundo do adb.

    Ele fica residente depois da primeira chamada; encerrá-lo ao sair
    evita deixar no computador um serviço que ninguém pediu.
    """
    _rodar(["kill-server"], tempo=20)


# ─────────────────────────────────────────
#  A SESSÃO
# ─────────────────────────────────────────

@dataclass
class Opcoes:
    """Ajustes do espelhamento."""

    #: Somente observação: o espelhamento não repassa toque nem
    #: digitação. É o padrão, e mudá-lo é ato do operador.
    somente_observar: bool = True
    #: Limite da maior dimensão da imagem, em pixels. Reduz o arquivo
    #: sem prejudicar a leitura de conversa.
    tamanho_max: int = 1080
    #: Quadros por segundo capturados do aparelho.
    quadros: int = 20
    #: Grava o áudio do aparelho, quando ele permite (Android 11 ou mais).
    com_audio: bool = True
    identificacao: str = ""

    def resumo(self) -> list[str]:
        L = []
        L.append(
            "O espelhamento foi feito em modo de observação, sem repasse "
            "de toque ou digitação ao aparelho."
            if self.somente_observar else
            "O controle do aparelho pelo computador esteve habilitado "
            "durante a sessão.")
        L.append(
            f"A imagem foi capturada a {self.quadros} quadros por segundo, "
            f"com a maior dimensão limitada a {self.tamanho_max} pixels.")
        L.append(
            "O áudio do aparelho foi captado junto com a imagem."
            if self.com_audio else
            "O áudio do aparelho não foi captado.")
        return L


@dataclass
class Resultado:
    """O que a sessão produziu."""

    arquivo: str = ""
    inicio: str = ""
    fim: str = ""
    segundos: float = 0.0
    tamanho: int = 0
    sha256: str = ""
    largura: int = 0
    altura: int = 0
    aparelho: Aparelho | None = None
    contexto: Contexto | None = None
    opcoes: Opcoes | None = None
    erro: str = ""
    avisos: list[str] = field(default_factory=list)

    @property
    def duracao(self) -> str:
        s = int(self.segundos)
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


class Espelhador:
    """Conduz o scrcpy durante a sessão."""

    def __init__(self, aparelho: Aparelho, destino: str | Path,
                 opcoes: Opcoes | None = None):
        self.aparelho = aparelho
        self.destino = Path(destino)
        self.opcoes = opcoes or Opcoes()
        self.contexto = ler_contexto()
        self._processo: subprocess.Popen | None = None
        self._inicio = 0.0
        self._inicio_iso = ""
        self._bruto: Path | None = None
        self._avisos: list[str] = []

    # ── comando ───────────────────────────
    @property
    def bruto(self) -> Path:
        """Arquivo intermediário, em Matroska.

        Matroska e não MP4: interrompida a sessão — cabo solto, aparelho
        desligado —, o Matroska continua legível, enquanto um MP4 que não
        chegou a ser fechado costuma não abrir.
        """
        if self._bruto is None:
            self._bruto = self.destino.with_suffix(".bruto.mkv")
        return self._bruto

    def comando(self) -> list[str]:
        exe = scrcpy_path()
        if exe is None:
            raise RuntimeError("scrcpy não encontrado no pacote.")
        cmd = [
            str(exe),
            "--serial", self.aparelho.serie,
            "--record", str(self.bruto),
            "--record-format", "mkv",
            "--max-size", str(self.opcoes.tamanho_max),
            "--max-fps", str(self.opcoes.quadros),
            "--window-title",
            f"Têmis — {self.aparelho.modelo or self.aparelho.serie}",
        ]
        if self.opcoes.somente_observar:
            # Sem isto, quem opera o computador opera também o celular.
            cmd.append("--no-control")
        if not self.opcoes.com_audio:
            cmd.append("--no-audio")
        return cmd

    # ── ciclo ─────────────────────────────
    @property
    def espelhando(self) -> bool:
        return self._processo is not None and self._processo.poll() is None

    @property
    def decorrido(self) -> float:
        return (time.time() - self._inicio) if self._inicio else 0.0

    def iniciar(self):
        if self.espelhando:
            return
        self.destino.parent.mkdir(parents=True, exist_ok=True)
        self.bruto.unlink(missing_ok=True)
        self.contexto = ler_contexto()
        self._inicio_iso = datetime.datetime.now().astimezone().isoformat(
            timespec="seconds")
        self._inicio = time.time()
        self._processo = subprocess.Popen(
            self.comando(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, creationflags=_SEM_JANELA)

    def encerrar(self, espera: float = 25.0, progresso=None) -> Resultado:
        """Fecha o espelhamento, aplica a faixa e resume o arquivo."""
        r = Resultado(
            arquivo=str(self.destino), inicio=self._inicio_iso,
            aparelho=self.aparelho, contexto=self.contexto,
            opcoes=self.opcoes)

        if self._processo is not None:
            try:
                self._processo.terminate()
                _s, erro = self._processo.communicate(timeout=espera)
                if erro:
                    texto = erro.decode("utf-8", "replace")
                    if "ERROR" in texto:
                        self._avisos.append(texto.strip()[-600:])
            except subprocess.TimeoutExpired:
                self._processo.kill()
                self._processo.communicate()
            self._processo = None

        r.segundos = self.decorrido
        r.fim = datetime.datetime.now().astimezone().isoformat(
            timespec="seconds")
        self._inicio = 0.0

        if not self.bruto.is_file() or not self.bruto.stat().st_size:
            r.erro = ("O espelhamento não produziu gravação.\n"
                      + "\n".join(self._avisos))
            return r

        if progresso:
            progresso("Aplicando a faixa de identificação…")
        try:
            aplicar_faixa(self.bruto, self.destino, self.opcoes.identificacao)
        except Exception as e:                               # noqa: BLE001
            # A gravação existe; só a faixa falhou. Melhor entregar o
            # arquivo sem faixa do que perder a diligência.
            r.avisos.append(
                f"A faixa de identificação não pôde ser aplicada ({e}); "
                f"a gravação foi mantida sem ela.")
            try:
                self.bruto.replace(self.destino.with_suffix(".mkv"))
                r.arquivo = str(self.destino.with_suffix(".mkv"))
            except OSError:
                r.arquivo = str(self.bruto)

        alvo = Path(r.arquivo)
        if not alvo.is_file():
            r.erro = "O arquivo final não foi encontrado."
            return r
        r.tamanho = alvo.stat().st_size
        r.sha256 = sha256(alvo)
        largura, altura, duracao = medir(alvo)
        r.largura, r.altura = largura, altura
        if duracao:
            r.segundos = duracao
        r.avisos.extend(self._avisos)

        if alvo != self.bruto:
            self.bruto.unlink(missing_ok=True)
        return r

    def cancelar(self):
        if self._processo is not None:
            try:
                self._processo.kill()
                self._processo.communicate(timeout=8)
            except Exception:                                # noqa: BLE001
                pass
            self._processo = None
        self._inicio = 0.0
        self.bruto.unlink(missing_ok=True)
        self.destino.unlink(missing_ok=True)


def aplicar_faixa(origem: Path, destino: Path, identificacao: str,
                  tempo: int = 3600):
    """Reprocessa a gravação acrescentando a faixa de contexto.

    A faixa é a mesma da Gravação de Tela, e vai em área acrescentada
    abaixo da imagem: nada do que foi espelhado fica coberto.
    """
    from .video_core import ffmpeg_path
    ffmpeg = ffmpeg_path()
    if ffmpeg is None:
        raise RuntimeError("FFmpeg não encontrado no pacote.")
    import tempfile
    import shutil
    andaime = Path(tempfile.mkdtemp(prefix="temis_faixa_"))
    try:
        filtro = montar_faixa(andaime, identificacao,
                              rodape="SISTEMA TÊMIS — ESPELHAMENTO")
        cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
               "-i", str(origem), "-vf", filtro,
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
               "-movflags", "+faststart", str(destino)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=tempo,
                           creationflags=_SEM_JANELA)
        if r.returncode != 0 or not destino.is_file():
            raise RuntimeError((r.stderr or "").strip()[-400:] or
                               "o codificador não produziu arquivo")
    finally:
        shutil.rmtree(andaime, ignore_errors=True)


# ─────────────────────────────────────────
#  TERMO
# ─────────────────────────────────────────

INK = "#16233A"
CINZA = "#5B6B82"
FECHO = "Sem mais a relatar, encerro o presente termo."

#: As três alterações que o método provoca no aparelho, declaradas.
#: Omiti-las seria esconder justamente o que a defesa procuraria.
ALTERACOES = (
    "A depuração por USB foi habilitada no aparelho por quem o detém, o "
    "que constitui alteração de configuração e fica registrada no próprio "
    "dispositivo.",
    "A estação de trabalho foi autorizada no aparelho mediante confirmação "
    "na tela deste, procedimento que grava a chave pública do computador "
    "na relação de máquinas confiáveis do dispositivo.",
    "Para o espelhamento, um componente de software foi transferido ao "
    "aparelho e nele executado enquanto durou a sessão, sendo encerrado ao "
    "final.",
)

RESSALVAS = (
    "O registro reproduz o que foi exibido na tela do aparelho durante a "
    "sessão. Não alcança o conteúdo armazenado no dispositivo que não "
    "tenha sido exibido, nem dados apagados, nem áreas protegidas.",
    "Este procedimento pressupõe aparelho destravado e depuração "
    "habilitada por quem o detém. Não constitui exame pericial de "
    "dispositivo móvel nem o substitui.",
    "A faixa impressa no vídeo destina-se à leitura do registro e não "
    "constitui, por si, prova de autenticidade. O que permite aferir a "
    "identidade do arquivo é o resumo criptográfico SHA-256 adiante "
    "consignado.",
    "As datas e horas são as do relógio da estação de trabalho e não foram "
    "atestadas por terceiro.",
)


@dataclass
class TermoEspelhamento:
    """Dados da peça."""

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
    objeto: str = ""
    #: Quem apresentou o aparelho, e a que título.
    detentor: str = ""
    registros: list[Resultado] = field(default_factory=list)

    @property
    def bons(self) -> list[Resultado]:
        return [r for r in self.registros if not r.erro and r.sha256]


def intro_espelhamento(t: TermoEspelhamento) -> str:
    from .hash_core import ARTIGO_PROCESSO, MESES
    artigo = ARTIGO_PROCESSO.get(t.tipo_processo, "da")
    mes = MESES[t.mes - 1]
    quando = (f"Ao 1º dia do mês de {mes} de {t.ano}" if t.dia == 1
              else f"Aos {t.dia} dias do mês de {mes} de {t.ano}")
    de_quem = f", apresentado por {t.detentor}" if t.detentor else ""
    return (
        f"{quando}, eu, {t.cargo} {t.nome}, matrícula {t.matricula}, "
        f"lotado(a) no(a) {t.lotacao}, visando instruir os autos "
        f"{artigo} {t.tipo_processo} nº {t.numero_processo}, declaro que "
        f"procedi ao espelhamento e ao registro audiovisual da tela de "
        f"aparelho de telefonia móvel{de_quem}, na forma e com as "
        f"ressalvas adiante consignadas."
    )


def validar_termo(t: TermoEspelhamento) -> list[str]:
    faltando = []
    for valor, rotulo in ((t.nome, "Nome completo"),
                          (t.matricula, "Matrícula"),
                          (t.lotacao, "Lotação"),
                          (t.numero_processo, "Número do processo"),
                          (t.objeto, "Objeto da diligência")):
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


def _quadro(linhas, largura: str = "36%") -> str:
    corpo = "".join(f"<tr>{_cel(r)}{_cel(v)}</tr>" for r, v in linhas if v)
    return (
        '<table width="100%" cellspacing="0" cellpadding="5" border="1" '
        'style="border-collapse:collapse; font-size:9.5pt;">'
        f'<tr style="background-color:#0a2442; color:#ffd633;">'
        f'<th width="{largura}">Item</th><th>Conteúdo</th></tr>'
        f"{corpo}</table>")


def build_html(t: TermoEspelhamento) -> str:
    """Termo em HTML, para exibir e exportar."""
    from ..impressao import cabecalho_html
    import html as _html
    e = _html.escape
    primeiro = t.bons[0] if t.bons else None

    partes = [
        "<html><body style=\"font-family:'Segoe UI',Arial,sans-serif; "
        'color:#16233a;">',
        cabecalho_html(),
        '<div align="center" style="margin-bottom:18px;">'
        '<b style="font-size:14pt; letter-spacing:0.5px;">'
        "Termo de Espelhamento e Registro de Tela de Aparelho Móvel"
        "</b></div>",
        "<hr/>",
        f'<p align="justify" style="font-size:11pt; line-height:160%;">'
        f"{e(intro_espelhamento(t))}</p>",
        '<p style="font-size:11pt;"><b>1. Objeto da diligência</b></p>',
        f'<p align="justify" style="font-size:10.5pt; line-height:150%;">'
        f"{e(t.objeto)}</p>",
    ]

    # ── aparelho ──────────────────────────
    partes.append('<p style="font-size:11pt;">'
                  "<b>2. Aparelho examinado</b></p>")
    if primeiro is not None and primeiro.aparelho is not None:
        partes.append(_quadro(primeiro.aparelho.linhas()))
        partes.append(
            '<p align="justify" style="font-size:10.5pt; line-height:150%; '
            'margin-top:8px;">Os dados acima foram lidos do próprio '
            "aparelho no momento da diligência.</p>")
    else:
        partes.append('<p style="font-size:10.5pt;">—</p>')

    # ── estação ───────────────────────────
    partes.append('<p style="font-size:11pt;">'
                  "<b>3. Estação de trabalho utilizada</b></p>")
    if primeiro is not None and primeiro.contexto is not None:
        partes.append(_quadro(primeiro.contexto.linhas()))

    # ── registros ─────────────────────────
    partes.append('<p style="font-size:11pt;">'
                  "<b>4. Registro(s) produzido(s)</b></p>")
    linhas = []
    for i, r in enumerate(t.bons, 1):
        linhas.append(
            "<tr>" + _cel(i, "center") + _cel(Path(r.arquivo).name)
            + _cel(f"{data_br(r.inicio)} a {data_br(r.fim)}")
            + _cel(r.duracao, "center")
            + _cel(f"{r.largura}×{r.altura}\n{formatar_tamanho(r.tamanho)}")
            + "</tr><tr>" + _cel("", "center")
            + f'<td colspan="4"><font color="{INK}" face="Courier New" '
              f'size="1">SHA-256: {r.sha256}</font></td></tr>')
    partes.append(
        '<table width="100%" cellspacing="0" cellpadding="4" border="1" '
        'style="border-collapse:collapse; font-size:8.5pt;">'
        '<tr style="background-color:#0a2442; color:#ffd633;">'
        '<th width="4%">Nº</th><th width="26%">Arquivo</th>'
        '<th width="34%">Período</th><th width="12%">Duração</th>'
        '<th width="24%">Características</th></tr>'
        f"{''.join(linhas)}</table>")

    # ── método ────────────────────────────
    partes.append('<p style="font-size:11pt;"><b>5. Método</b></p>')
    metodo = [
        "O aparelho foi conectado à estação de trabalho por cabo USB e sua "
        "tela espelhada no computador, sendo a sessão gravada em vídeo, na "
        "resolução em que exibida.",
    ]
    if primeiro is not None and primeiro.opcoes is not None:
        metodo += primeiro.opcoes.resumo()
    metodo.append(
        "À imagem foi acrescentada, em faixa criada para esse fim abaixo "
        "do quadro, a identificação do processo, do operador e da estação, "
        "além do relógio e do tempo decorrido. Encerrada a sessão, "
        "calculou-se o resumo criptográfico SHA-256 do arquivo produzido.")
    partes += [f'<p align="justify" style="font-size:10.5pt; '
               f'line-height:150%;">{e(x)}</p>' for x in metodo]

    # ── alterações no aparelho ────────────
    partes.append('<p style="font-size:11pt;">'
                  "<b>6. Alterações provocadas no aparelho</b></p>")
    partes.append(
        '<p align="justify" style="font-size:10.5pt; line-height:150%;">'
        "O método empregado não é de leitura inteiramente passiva. "
        "Consignam-se, para conhecimento de quem examinar esta peça, as "
        "alterações que ele provoca no dispositivo:</p>")
    partes += [f'<p align="justify" style="font-size:10.5pt; '
               f'line-height:150%;">{e(x)}</p>' for x in ALTERACOES]

    # ── ressalvas ─────────────────────────
    partes.append('<p style="font-size:11pt;"><b>7. Ressalvas</b></p>')
    partes += [f'<p align="justify" style="font-size:10.5pt; '
               f'line-height:150%;">{e(x)}</p>' for x in RESSALVAS]

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


def build_text(t: TermoEspelhamento) -> str:
    """Termo em texto puro."""
    primeiro = t.bons[0] if t.bons else None
    L = ["TERMO DE ESPELHAMENTO E REGISTRO DE TELA DE APARELHO MÓVEL", "",
         intro_espelhamento(t), "", "1. OBJETO DA DILIGÊNCIA", "", t.objeto,
         "", "2. APARELHO EXAMINADO", ""]
    if primeiro is not None and primeiro.aparelho is not None:
        for rotulo, valor in primeiro.aparelho.linhas():
            L.append(f"{rotulo}: {valor}")
    L += ["", "3. ESTAÇÃO DE TRABALHO UTILIZADA", ""]
    if primeiro is not None and primeiro.contexto is not None:
        for rotulo, valor in primeiro.contexto.linhas():
            L.append(f"{rotulo}: {valor}")
    L += ["", "4. REGISTRO(S) PRODUZIDO(S)", ""]
    for i, r in enumerate(t.bons, 1):
        L.append(f"{i}. {Path(r.arquivo).name}")
        L.append(f"   Período: {data_br(r.inicio)} a {data_br(r.fim)}")
        L.append(f"   Duração: {r.duracao}  |  {r.largura}x{r.altura}  |  "
                 f"{formatar_tamanho(r.tamanho)}")
        L.append(f"   SHA-256: {r.sha256}")
        L.append("")
    L += ["5. MÉTODO", ""]
    if primeiro is not None and primeiro.opcoes is not None:
        L += [f"  - {x}" for x in primeiro.opcoes.resumo()]
    L += ["", "6. ALTERAÇÕES PROVOCADAS NO APARELHO", ""]
    L += [f"  - {x}" for x in ALTERACOES]
    L += ["", "7. RESSALVAS", ""] + [f"  - {x}" for x in RESSALVAS]
    L += ["", FECHO, "", "_" * 40, t.nome, t.cargo]
    if t.matricula:
        L.append(f"Matrícula {t.matricula}")
    return "\n".join(L)
