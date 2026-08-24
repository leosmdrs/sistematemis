"""
Gravação de tela com contexto de custódia.

Núcleo compartilhado por duas ferramentas: a **Gravação de Tela**, que
registra qualquer coisa que aconteça no monitor, e a **Extração
Registrada**, que filma a diligência enquanto documenta cada passo da
navegação.

O que o registro prova, e o que não prova
-----------------------------------------

A faixa impressa no vídeo — processo, operador, estação, relógio — é
**legibilidade**, não prova. São pixels: qualquer um monta um vídeo com
uma tarja dizendo o que quiser. Ela existe para que quem assiste leia o
contexto sem abrir outro documento.

O que dá peso à peça é a camada criptográfica: o resumo SHA-256 do vídeo
calculado no encerramento, o termo assinado por quem gravou e, quando
houver, o carimbo de tempo de terceiro. Sem isso, a hora exibida é
apenas o que o relógio daquele computador dizia.

O termo diz as duas coisas, porque uma ferramenta que se cala sobre os
próprios limites convida a que se lhe atribua alcance que ela não tem.

Duas decisões de construção
---------------------------

**A faixa vai abaixo da tela, não sobre ela.** A imagem capturada é
aumentada e a faixa ocupa a área acrescentada. Sobreposta, ela
esconderia justamente uma parte do que está sendo registrado — e o
primeiro a apontar isso seria quem contesta a peça.

**O arquivo resiste a interrupção — mas isso tem preço.** Um MP4 comum
só fica legível quando o codificador o fecha: se a máquina desligar no
meio de uma diligência de quarenta minutos, perde-se tudo. A
fragmentação resolve, e a primeira versão disto afirmava que resolvia de
graça. A medição desmentiu: com os ajustes padrão, matar o codificador
aos vinte segundos deixava um arquivo de 28 bytes — nada.

A razão é que o fragmento só é fechado a cada quadro-chave, e o padrão
do x264 é um a cada vinte e cinco segundos. Forçando um a cada cinco
segundos o arquivo passa a sobreviver — mas fica 3,4 vezes maior, porque
tela de escritório é quase estática e quadro-chave é justamente o que
custa caro nela.

O que se recupera, medido matando o codificador em vários momentos:

    morto aos 12s  →  nada
    morto aos 20s  →  10s
    morto aos 30s  →  15s
    morto aos 45s  →  30s

Ou seja: perdem-se os últimos dez a quinze segundos, e uma gravação de
menos de quinze segundos não sobrevive de jeito nenhum. Não é o que se
gostaria de anunciar, mas numa diligência de meia hora a diferença é
entre perder quinze segundos e perder tudo.

Medido: 31 MB por hora sem proteção, 107 MB por hora com ela. Vem ligada
por padrão; quem for gravar por horas pode desligar.
"""

from __future__ import annotations

import datetime
import getpass
import hashlib
import os
import platform
import re
import socket
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .video_core import _SEM_JANELA, ffmpeg_path

#: Altura da faixa de contexto, em pixels de vídeo.
FAIXA = 64

#: Intervalo entre quadros-chave quando a proteção contra interrupção
#: está ligada. O muxer segura alguns fragmentos antes de gravá-los, de
#: modo que a perda real é de duas a três vezes este valor — dez a quinze
#: segundos do fim, medidos.
SEGUNDOS_ENTRE_CHAVES = 5

#: Fonte da faixa. Monoespaçada de propósito: número de processo e
#: horário ficam mais fáceis de conferir quadro a quadro.
FONTE_WIN = r"C:\Windows\Fonts\consola.ttf"
FONTE_ALTERNATIVA = r"C:\Windows\Fonts\arial.ttf"

#: Qualidades oferecidas: (rótulo, quadros por segundo, CRF, descrição).
#: Medido nesta máquina, 10 qps a CRF 28 dá cerca de 50 MB por hora de
#: tela de escritório — cabe num processo eletrônico sem apuro.
QUALIDADES = (
    ("normal", 10, 28, "10 quadros/s — cerca de 50 MB por hora"),
    ("econômica", 6, 31, "6 quadros/s — cerca de 30 MB por hora"),
    ("detalhada", 15, 24, "15 quadros/s — cerca de 150 MB por hora"),
)


# ─────────────────────────────────────────
#  CONTEXTO DA ESTAÇÃO
# ─────────────────────────────────────────

@dataclass
class Contexto:
    """O que identifica a máquina e quem operava no momento da gravação."""

    usuario: str = ""
    dominio: str = ""
    estacao: str = ""
    sistema: str = ""
    fabricante: str = ""
    modelo: str = ""
    serie: str = ""
    fuso: str = ""
    enderecos: list[str] = field(default_factory=list)
    mac: str = ""
    quando: str = ""

    def linhas(self) -> list[tuple[str, str]]:
        """Pares (rótulo, valor) para o quadro do termo."""
        L = [
            ("Usuário do Windows",
             f"{self.usuario}" + (f" ({self.dominio})" if self.dominio else "")),
            ("Nome da estação", self.estacao),
            ("Sistema operacional", self.sistema),
        ]
        if self.fabricante or self.modelo:
            L.append(("Equipamento",
                      " ".join(x for x in (self.fabricante, self.modelo) if x)))
        if self.serie:
            L.append(("Número de série do equipamento", self.serie))
        if self.enderecos:
            L.append(("Endereços de rede da estação", "; ".join(self.enderecos)))
        if self.mac:
            L.append(("Endereço físico (MAC)", self.mac))
        L.append(("Fuso horário da estação", self.fuso))
        return [(r, v) for r, v in L if v]


def _equipamento() -> tuple[str, str, str]:
    """Fabricante, modelo e número de série, pelo WMI do Windows.

    Sai vazio quando não há permissão ou o serviço não responde: o
    registro não pode deixar de acontecer porque um dado acessório
    faltou.
    """
    consulta = (
        "$c = Get-CimInstance Win32_ComputerSystem; "
        "$b = Get-CimInstance Win32_BIOS; "
        "Write-Output ($c.Manufacturer + '|' + $c.Model + '|' + $b.SerialNumber)"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", consulta],
            capture_output=True, text=True, timeout=15,
            creationflags=_SEM_JANELA)
        partes = (r.stdout or "").strip().split("|")
        if len(partes) == 3:
            return tuple(p.strip() for p in partes)          # type: ignore
    except Exception:                                        # noqa: BLE001
        pass
    return ("", "", "")


def _enderecos_de_rede() -> list[str]:
    """Endereços IPv4 da estação.

    Vão para o termo, não para a faixa. Endereço interno não prova nada a
    terceiro e muda a cada renovação de concessão; o que identifica a
    estação de forma estável é o nome, o domínio e o número de série. O
    endereço entra porque é o que o pedido de auditoria costuma citar.
    """
    achados: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None,
                                       socket.AF_INET):
            ip = info[4][0]
            if ip not in achados and not ip.startswith("127."):
                achados.append(ip)
    except OSError:
        pass
    return achados


def ler_contexto() -> Contexto:
    """Reúne o contexto da estação no instante da gravação."""
    fabricante, modelo, serie = _equipamento()
    agora = datetime.datetime.now().astimezone()
    fisico = uuid.getnode()
    return Contexto(
        usuario=getpass.getuser(),
        dominio=os.environ.get("USERDOMAIN", ""),
        estacao=socket.gethostname(),
        sistema=f"{platform.system()} {platform.release()} "
                f"(build {platform.version()})",
        fabricante=fabricante, modelo=modelo, serie=serie,
        fuso=f"{time.tzname[0]} (UTC{agora.strftime('%z')[:3]}:"
             f"{agora.strftime('%z')[3:]})",
        enderecos=_enderecos_de_rede(),
        mac=":".join(f"{(fisico >> i) & 0xFF:02X}"
                     for i in range(40, -8, -8)),
        quando=agora.isoformat(timespec="seconds"),
    )


# ─────────────────────────────────────────
#  MONITORES
# ─────────────────────────────────────────

@dataclass
class Monitor:
    """Uma área capturável."""

    chave: str          # "desktop" ou "monitor:0"
    rotulo: str
    x: int = 0
    y: int = 0
    largura: int = 0
    altura: int = 0

    @property
    def area_toda(self) -> bool:
        return self.chave == "desktop"


def monitores() -> list[Monitor]:
    """Área de trabalho inteira e cada monitor separadamente.

    A área inteira é a primeira opção de propósito: gravar só um monitor
    deixa de fora o que estava no outro, e é exatamente isso que se
    alegaria depois.
    """
    saida = [Monitor("desktop", "Área de trabalho inteira (todos os monitores)")]
    try:
        from PyQt6.QtGui import QGuiApplication
        for i, tela in enumerate(QGuiApplication.screens()):
            g = tela.geometry()
            saida.append(Monitor(
                f"monitor:{i}",
                f"Monitor {i + 1} — {g.width()}×{g.height()}"
                + ("  (principal)"
                   if tela is QGuiApplication.primaryScreen() else ""),
                g.x(), g.y(), g.width(), g.height()))
    except Exception:                                        # noqa: BLE001
        pass
    return saida


# ─────────────────────────────────────────
#  MICROFONE
# ─────────────────────────────────────────

_DISPOSITIVO = re.compile(r'"([^"]+)"\s*\(audio\)', re.I)


def microfones() -> list[str]:
    """Nomes dos dispositivos de áudio que o Windows expõe."""
    ffmpeg = ffmpeg_path()
    if ffmpeg is None:
        return []
    try:
        r = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-list_devices", "true",
             "-f", "dshow", "-i", "dummy"],
            capture_output=True, text=True, timeout=25,
            creationflags=_SEM_JANELA)
    except Exception:                                        # noqa: BLE001
        return []
    saida = []
    for linha in (r.stderr or "").splitlines():
        m = _DISPOSITIVO.search(linha)
        if m and m.group(1) not in saida:
            saida.append(m.group(1))
    return saida


# ─────────────────────────────────────────
#  A FAIXA
# ─────────────────────────────────────────

def _caminho_para_filtro(caminho: str | Path) -> str:
    """Caminho de arquivo no formato que o filtro aceita.

    A letra da unidade precisa do dois-pontos escapado e as barras
    invertidas viram barras normais.
    """
    return str(caminho).replace("\\", "/").replace(":", "\\:")


def _fonte() -> str:
    escolhida = FONTE_WIN if Path(FONTE_WIN).is_file() else FONTE_ALTERNATIVA
    return _caminho_para_filtro(escolhida)


def montar_faixa(pasta: str | Path, identificacao: str,
                 rodape: str = "SISTEMA TÊMIS — REGISTRO",
                 altura: int = FAIXA, fundo: str = "0x0A2442") -> str:
    """Filtro que acrescenta a faixa de contexto abaixo da imagem.

    A imagem capturada não é tocada: `pad` cria a faixa **embaixo** dela.

    O texto variável vai por **arquivo**, e não embutido no filtro. Foi
    uma lição cara: dentro de aspas simples o FFmpeg não admite `\\'`,
    de modo que um servidor chamado O'Brien fazia o filtro inteiro ser
    recusado e a gravação não começava. Escapar caractere a caractere
    resolve até aparecer o próximo caso; ler de arquivo, com a expansão
    desligada, aceita qualquer conteúdo — apóstrofo, dois-pontos,
    colchete, porcentagem, acento — sem tratamento nenhum.

    Só o relógio continua embutido, porque precisa da expansão ligada
    para ser reavaliado a cada quadro. E o que ele contém é fixo.
    """
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    arq_ident = pasta / "faixa_identificacao.txt"
    arq_rodape = pasta / "faixa_rodape.txt"
    arq_ident.write_text(identificacao, encoding="utf-8")
    arq_rodape.write_text(rodape, encoding="utf-8")

    fonte = _fonte()
    ident = _caminho_para_filtro(arq_ident)
    marca = _caminho_para_filtro(arq_rodape)
    # `%{localtime}` mostra a hora do computador a cada quadro; `%{pts}`,
    # o tempo decorrido desde o início — é ele que evidencia que a
    # gravação é contínua e não foi montada de pedaços.
    relogio = "%{localtime\\:%X}"
    decorrido = "%{pts\\:hms}"
    return (
        f"pad=iw:ih+{altura}:0:0:color={fundo},"
        f"drawtext=fontfile='{fonte}':textfile='{ident}':expansion=none"
        f":fontcolor=white:fontsize=18:x=14:y=h-{altura}+8,"
        f"drawtext=fontfile='{fonte}':text='{relogio}'"
        f":fontcolor=0xFFCC00:fontsize=22:x=14:y=h-{altura}+32,"
        f"drawtext=fontfile='{fonte}':text='decorrido {decorrido}'"
        f":fontcolor=white@0.75:fontsize=20:x=210:y=h-{altura}+33,"
        f"drawtext=fontfile='{fonte}':textfile='{marca}':expansion=none"
        f":fontcolor=white@0.6:fontsize=17:x=w-tw-14:y=h-{altura}+33"
    )


# ─────────────────────────────────────────
#  A GRAVAÇÃO
# ─────────────────────────────────────────

@dataclass
class Opcoes:
    """Ajustes da captura."""

    monitor: str = "desktop"
    qualidade: str = "normal"
    microfone: str = ""
    #: Identificação impressa na faixa — processo, operador, estação.
    identificacao: str = ""
    rodape: str = "SISTEMA TÊMIS — REGISTRO"
    #: Força quadro-chave a cada poucos segundos, para que uma queda de
    #: energia não leve a gravação inteira. Triplica o arquivo; veja a
    #: nota no alto do módulo.
    resistente: bool = True

    @property
    def quadros(self) -> int:
        return dict((q[0], q[1]) for q in QUALIDADES).get(self.qualidade, 10)

    @property
    def crf(self) -> int:
        return dict((q[0], q[2]) for q in QUALIDADES).get(self.qualidade, 28)

    @property
    def intervalo_chave(self) -> int:
        """Quadros entre dois quadros-chave. Cinco segundos."""
        return self.quadros * SEGUNDOS_ENTRE_CHAVES


@dataclass
class Resultado:
    """O que a gravação produziu."""

    arquivo: str = ""
    inicio: str = ""
    fim: str = ""
    segundos: float = 0.0
    tamanho: int = 0
    sha256: str = ""
    largura: int = 0
    altura: int = 0
    quadros: int = 0
    com_audio: bool = False
    contexto: Contexto | None = None
    opcoes: Opcoes | None = None
    erro: str = ""

    @property
    def duracao(self) -> str:
        s = int(self.segundos)
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


class Gravador:
    """Conduz o FFmpeg durante a captura.

    O encerramento é feito escrevendo `q` na entrada do processo, e não o
    matando: só assim o codificador fecha o arquivo. Matar o processo
    deixaria um vídeo que, com fragmentação, ainda abre — mas sem a
    duração correta no cabeçalho, e é a duração que o termo declara.
    """

    def __init__(self, destino: str | Path, opcoes: Opcoes | None = None):
        self.destino = Path(destino)
        self.opcoes = opcoes or Opcoes()
        self.contexto = ler_contexto()
        self._processo: subprocess.Popen | None = None
        self._inicio = 0.0
        self._inicio_iso = ""
        self._erros: list[str] = []
        #: Onde ficam os textos da faixa enquanto o codificador os lê.
        #: Some ao fim da gravação — não é peça, é andaime.
        self._andaime: Path | None = None

    def _pasta_da_faixa(self) -> Path:
        import tempfile
        if self._andaime is None:
            self._andaime = Path(tempfile.mkdtemp(prefix="temis_faixa_"))
        return self._andaime

    def _limpar_andaime(self):
        import shutil
        if self._andaime is not None:
            shutil.rmtree(self._andaime, ignore_errors=True)
            self._andaime = None

    # ── comando ───────────────────────────
    def comando(self) -> list[str]:
        ffmpeg = ffmpeg_path()
        if ffmpeg is None:
            raise RuntimeError("FFmpeg não encontrado no pacote.")

        cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "warning", "-y"]

        alvo = self.opcoes.monitor
        cmd += ["-f", "gdigrab", "-framerate", str(self.opcoes.quadros)]
        if alvo.startswith("monitor:"):
            escolhido = next((m for m in monitores() if m.chave == alvo), None)
            if escolhido is not None and escolhido.largura:
                cmd += ["-offset_x", str(escolhido.x),
                        "-offset_y", str(escolhido.y),
                        "-video_size", f"{escolhido.largura}x{escolhido.altura}"]
        cmd += ["-i", "desktop"]

        if self.opcoes.microfone:
            cmd += ["-f", "dshow", "-i", f"audio={self.opcoes.microfone}"]

        cmd += ["-vf", montar_faixa(self._pasta_da_faixa(),
                                    self.opcoes.identificacao,
                                    self.opcoes.rodape)]
        cmd += ["-c:v", "libx264", "-preset", "veryfast",
                "-crf", str(self.opcoes.crf), "-pix_fmt", "yuv420p"]
        if self.opcoes.resistente:
            # Sem isto a fragmentação não protege nada: o fragmento só
            # fecha no quadro-chave seguinte, e o padrão do x264 é um a
            # cada 25 segundos.
            cmd += ["-g", str(self.opcoes.intervalo_chave)]
        if self.opcoes.microfone:
            cmd += ["-c:a", "aac", "-b:a", "96k"]
        # Fragmentado: o que já foi gravado abre mesmo que a máquina
        # desligue no meio.
        cmd += ["-movflags", "+frag_keyframe+empty_moov+default_base_moof",
                str(self.destino)]
        return cmd

    # ── ciclo ─────────────────────────────
    @property
    def gravando(self) -> bool:
        return self._processo is not None and self._processo.poll() is None

    @property
    def decorrido(self) -> float:
        return (time.time() - self._inicio) if self._inicio else 0.0

    def iniciar(self):
        if self.gravando:
            return
        self.destino.parent.mkdir(parents=True, exist_ok=True)
        self.contexto = ler_contexto()
        self._inicio_iso = datetime.datetime.now().astimezone().isoformat(
            timespec="seconds")
        self._inicio = time.time()
        self._processo = subprocess.Popen(
            self.comando(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, creationflags=_SEM_JANELA)

    def encerrar(self, espera: float = 25.0) -> Resultado:
        """Fecha a gravação e devolve o que ela produziu."""
        resultado = Resultado(
            arquivo=str(self.destino), inicio=self._inicio_iso,
            contexto=self.contexto, opcoes=self.opcoes,
            com_audio=bool(self.opcoes.microfone),
            quadros=self.opcoes.quadros)

        if self._processo is not None:
            try:
                self._processo.stdin.write(b"q")
                self._processo.stdin.flush()
            except (OSError, ValueError, AttributeError):
                pass
            try:
                _saida, erro = self._processo.communicate(timeout=espera)
                if erro:
                    self._erros.append(erro.decode("utf-8", "replace")[-2000:])
            except subprocess.TimeoutExpired:
                self._processo.kill()
                self._processo.communicate()
                self._erros.append(
                    "O codificador não encerrou no prazo e foi interrompido; "
                    "o arquivo pode ter a duração incompleta.")
            self._processo = None

        resultado.segundos = self.decorrido
        resultado.fim = datetime.datetime.now().astimezone().isoformat(
            timespec="seconds")
        self._inicio = 0.0
        self._limpar_andaime()

        if not self.destino.is_file():
            resultado.erro = ("A gravação não produziu arquivo.\n"
                              + "\n".join(self._erros))
            return resultado

        resultado.tamanho = self.destino.stat().st_size
        resultado.sha256 = sha256(self.destino)
        largura, altura, duracao = medir(self.destino)
        resultado.largura, resultado.altura = largura, altura
        if duracao:
            resultado.segundos = duracao
        if not resultado.tamanho:
            resultado.erro = "O arquivo gerado está vazio."
        return resultado

    def cancelar(self):
        """Interrompe e descarta. Usado quando se desiste da gravação."""
        if self._processo is not None:
            try:
                self._processo.kill()
                self._processo.communicate(timeout=8)
            except Exception:                                # noqa: BLE001
                pass
            self._processo = None
        self._inicio = 0.0
        self._limpar_andaime()
        try:
            self.destino.unlink(missing_ok=True)
        except OSError:
            pass


# ─────────────────────────────────────────
#  APOIO
# ─────────────────────────────────────────

def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while bloco := f.read(1 << 20):
            h.update(bloco)
    return h.hexdigest()


def medir(caminho: Path) -> tuple[int, int, float]:
    """Largura, altura e duração do vídeo, lidas do próprio arquivo."""
    from .video_core import ffprobe_path
    ffprobe = ffprobe_path()
    if ffprobe is None:
        return (0, 0, 0.0)
    try:
        r = subprocess.run(
            [str(ffprobe), "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height:format=duration",
             "-of", "default=nw=1:nk=1", str(caminho)],
            capture_output=True, text=True, timeout=30,
            creationflags=_SEM_JANELA)
        valores = [x for x in (r.stdout or "").split() if x]
        largura = int(float(valores[0])) if len(valores) > 0 else 0
        altura = int(float(valores[1])) if len(valores) > 1 else 0
        duracao = float(valores[2]) if len(valores) > 2 else 0.0
        return (largura, altura, duracao)
    except Exception:                                        # noqa: BLE001
        return (0, 0, 0.0)


def formatar_tamanho(n: int) -> str:
    for unidade, limite in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= limite:
            return f"{n / limite:.2f} {unidade}".replace(".", ",")
    return f"{n} bytes"


def data_br(iso: str) -> str:
    """Converte o carimbo ISO no formato que o termo usa."""
    if not iso:
        return "—"
    try:
        d = datetime.datetime.fromisoformat(iso)
        return d.strftime("%d/%m/%Y às %H:%M:%S")
    except ValueError:
        return iso


# ─────────────────────────────────────────
#  TERMO
# ─────────────────────────────────────────

#: Tinta do corpo do documento, repetida célula a célula porque o motor
#: de texto do Qt não propaga a cor do <body> para dentro da tabela.
INK = "#16233A"
CINZA = "#5B6B82"

ENCERRAMENTO = "Sem mais a relatar, encerro o presente termo."

#: O que o registro não garante. Vai impresso, porque uma peça que se
#: cala sobre os próprios limites convida a que se lhe atribua alcance
#: que ela não tem — e a primeira coisa que a defesa faz é procurar esse
#: alcance excedente.
RESSALVAS = (
    "A faixa impressa no vídeo — número do processo, identificação do "
    "operador, nome da estação e relógio — destina-se à leitura do "
    "registro e não constitui, por si, prova de sua autenticidade. O que "
    "permite aferir que o arquivo é o mesmo aqui descrito é o resumo "
    "criptográfico SHA-256 adiante consignado.",
    "A data e a hora exibidas são as do relógio da estação onde a "
    "gravação foi feita, não tendo sido atestadas por terceiro. Onde a "
    "precisão temporal for controvertida, cabe carimbo do tempo emitido "
    "por autoridade credenciada.",
    "O registro reproduz o que era exibido na tela no período indicado. "
    "Não alcança o que estava fora da área capturada, o que foi exibido "
    "antes do início ou depois do encerramento, nem o funcionamento "
    "interno dos sistemas consultados.",
    "A gravação é contínua e não foi editada. Interrupção do registro, "
    "se houver, é aferível pelo contador de tempo decorrido impresso na "
    "própria imagem.",
)


@dataclass
class TermoGravacao:
    """Dados da peça."""

    # quem grava
    nome: str = ""
    matricula: str = ""
    lotacao: str = ""
    cargo: str = "Policial Rodoviário Federal"
    # a que autos
    tipo_processo: str = "IPS"
    numero_processo: str = ""
    dia: int = 1
    mes: int = 1
    ano: int = 2026
    # o que foi registrado
    objeto: str = ""
    sistema_consultado: str = ""
    registros: list[Resultado] = field(default_factory=list)

    @property
    def bons(self) -> list[Resultado]:
        return [r for r in self.registros if not r.erro and r.sha256]


def intro_gravacao(t: TermoGravacao) -> str:
    """Parágrafo de abertura, na redação já consagrada no sistema."""
    from .hash_core import ARTIGO_PROCESSO, MESES
    artigo = ARTIGO_PROCESSO.get(t.tipo_processo, "da")
    mes = MESES[t.mes - 1]
    quando = (f"Ao 1º dia do mês de {mes} de {t.ano}" if t.dia == 1
              else f"Aos {t.dia} dias do mês de {mes} de {t.ano}")
    quantos = len(t.bons)
    peca = "o registro audiovisual" if quantos == 1 else "os registros audiovisuais"
    return (
        f"{quando}, eu, {t.cargo} {t.nome}, matrícula {t.matricula}, "
        f"lotado(a) no(a) {t.lotacao}, visando instruir os autos "
        f"{artigo} {t.tipo_processo} nº {t.numero_processo}, declaro que "
        f"procedi ao registro audiovisual da diligência adiante "
        f"descrita, realizada em meio eletrônico, do que resultou "
        f"{peca} identificado(s) neste termo."
    )


def validar_termo(t: TermoGravacao) -> list[str]:
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


def _quadro(linhas, largura_rotulo: str = "34%") -> str:
    corpo = "".join(f"<tr>{_cel(r)}{_cel(v)}</tr>" for r, v in linhas if v)
    return (
        '<table width="100%" cellspacing="0" cellpadding="5" border="1" '
        'style="border-collapse:collapse; font-size:9.5pt;">'
        f'<tr style="background-color:#0a2442; color:#ffd633;">'
        f'<th width="{largura_rotulo}">Item</th><th>Conteúdo</th></tr>'
        f"{corpo}</table>")


def _quadro_registros(t: TermoGravacao) -> str:
    linhas = []
    for i, r in enumerate(t.bons, 1):
        audio = "com áudio do microfone" if r.com_audio else "sem áudio"
        linhas.append(
            "<tr>"
            + _cel(i, "center")
            + _cel(Path(r.arquivo).name)
            + _cel(f"{data_br(r.inicio)}\nа {data_br(r.fim)}".replace("а", "a"))
            + _cel(r.duracao, "center")
            + _cel(f"{r.largura}×{r.altura}, {r.quadros} q/s, {audio}\n"
                   f"{formatar_tamanho(r.tamanho)}")
            + "</tr>"
            + "<tr>"
            + _cel("", "center")
            + f'<td colspan="4"><font color="{INK}" face="Courier New" '
              f'size="1">SHA-256: {r.sha256}</font></td>'
            + "</tr>")
    return (
        '<table width="100%" cellspacing="0" cellpadding="4" border="1" '
        'style="border-collapse:collapse; font-size:8.5pt;">'
        '<tr style="background-color:#0a2442; color:#ffd633;">'
        '<th width="4%">Nº</th><th width="26%">Arquivo</th>'
        '<th width="26%">Período</th><th width="12%">Duração</th>'
        '<th width="32%">Características</th></tr>'
        f"{''.join(linhas)}</table>")


def build_html(t: TermoGravacao) -> str:
    """Termo em HTML, para exibir e exportar."""
    import html as _html
    e = _html.escape

    partes = [
        "<html><body style=\"font-family:'Segoe UI',Arial,sans-serif; "
        'color:#16233a;">',
        '<div align="center" style="margin-bottom:18px;">'
        '<b style="font-size:14pt; letter-spacing:0.5px;">'
        "Termo de Registro Audiovisual de Diligência em Meio Eletrônico"
        "</b></div>",
        "<hr/>",
        f'<p align="justify" style="font-size:11pt; line-height:160%;">'
        f"{e(intro_gravacao(t))}</p>",
        '<p style="font-size:11pt;"><b>1. Objeto da diligência</b></p>',
        f'<p align="justify" style="font-size:10.5pt; line-height:150%;">'
        f"{e(t.objeto)}</p>",
    ]
    if t.sistema_consultado:
        partes.append(
            f'<p align="justify" style="font-size:10.5pt; line-height:150%;">'
            f"Sistema consultado: {e(t.sistema_consultado)}.</p>")

    # ── estação e operador ────────────────
    contexto = t.bons[0].contexto if t.bons else None
    partes.append('<p style="font-size:11pt;">'
                  "<b>2. Estação em que se realizou o registro</b></p>")
    if contexto is not None:
        partes.append(_quadro(contexto.linhas()))
    partes.append(
        '<p align="justify" style="font-size:10.5pt; line-height:150%; '
        'margin-top:8px;">'
        "Os dados acima foram lidos da própria estação no instante em que a "
        "gravação teve início.</p>")

    # ── os registros ──────────────────────
    partes.append('<p style="font-size:11pt;">'
                  "<b>3. Registro(s) produzido(s)</b></p>")
    partes.append(_quadro_registros(t))
    partes.append(
        '<p align="justify" style="font-size:10.5pt; line-height:150%; '
        'margin-top:8px;">'
        "O resumo criptográfico SHA-256 consignado permite conferir, a "
        "qualquer tempo, a identidade entre o arquivo juntado aos autos e "
        "o que foi produzido nesta diligência. Valor diverso indica que o "
        "arquivo não é o mesmo.</p>")

    # ── método ────────────────────────────
    partes.append('<p style="font-size:11pt;"><b>4. Método</b></p>')
    metodo = [
        "A imagem exibida na tela foi capturada de modo contínuo, do "
        "início ao encerramento indicados, e gravada em arquivo de vídeo "
        "no formato MP4, codificação H.264.",
        "À imagem capturada foi acrescentada, em faixa inferior criada "
        "para esse fim, a identificação do processo, do operador e da "
        "estação, o relógio da estação e o contador de tempo decorrido. A "
        "faixa ocupa área acrescentada ao quadro e não encobre parte "
        "alguma do que foi registrado.",
        "Encerrada a captura, calculou-se o resumo criptográfico SHA-256 "
        "do arquivo produzido, adiante consignado.",
    ]
    if t.bons and t.bons[0].opcoes and t.bons[0].opcoes.microfone:
        metodo.append(
            f"O áudio foi captado do dispositivo "
            f"“{t.bons[0].opcoes.microfone}” em conjunto com a imagem.")
    partes += [f'<p align="justify" style="font-size:10.5pt; '
               f'line-height:150%;">{e(linha)}</p>' for linha in metodo]

    # ── ressalvas ─────────────────────────
    partes.append('<p style="font-size:11pt;"><b>5. Ressalvas</b></p>')
    partes += [f'<p align="justify" style="font-size:10.5pt; '
               f'line-height:150%;">{e(linha)}</p>' for linha in RESSALVAS]

    partes.append(f'<p align="justify" style="font-size:11pt; '
                  f'margin-top:18px;">{ENCERRAMENTO}</p>')
    partes.append(
        '<br/><br/><div align="center" style="margin-top:36px;">'
        "______________________________________<br/>"
        f"<b>{e(t.nome)}</b><br/>"
        f'<span style="font-size:10pt;">{e(t.cargo)}</span>'
        + (f'<br/><span style="font-size:10pt;">Matrícula {e(t.matricula)}'
           f"</span>" if t.matricula else "")
        + "</div></body></html>")
    return "\n".join(partes)


def build_text(t: TermoGravacao) -> str:
    """Termo em texto puro, para onde não se aceita formatação."""
    L = ["TERMO DE REGISTRO AUDIOVISUAL DE DILIGÊNCIA EM MEIO ELETRÔNICO",
         "", intro_gravacao(t), "", "1. OBJETO DA DILIGÊNCIA", "", t.objeto]
    if t.sistema_consultado:
        L.append(f"Sistema consultado: {t.sistema_consultado}")

    contexto = t.bons[0].contexto if t.bons else None
    L += ["", "2. ESTAÇÃO EM QUE SE REALIZOU O REGISTRO", ""]
    if contexto is not None:
        for rotulo, valor in contexto.linhas():
            L.append(f"{rotulo}: {valor}")

    L += ["", "3. REGISTRO(S) PRODUZIDO(S)", ""]
    for i, r in enumerate(t.bons, 1):
        L.append(f"{i}. {Path(r.arquivo).name}")
        L.append(f"   Início: {data_br(r.inicio)}")
        L.append(f"   Fim:    {data_br(r.fim)}")
        L.append(f"   Duração: {r.duracao}  |  {r.largura}x{r.altura}, "
                 f"{r.quadros} quadros/s, "
                 + ("com áudio" if r.com_audio else "sem áudio"))
        L.append(f"   Tamanho: {formatar_tamanho(r.tamanho)}")
        L.append(f"   SHA-256: {r.sha256}")
        L.append("")

    L += ["4. MÉTODO", "",
          "Captura contínua da tela, gravada em MP4/H.264, com faixa de "
          "identificação em área acrescentada ao quadro, e resumo "
          "criptográfico SHA-256 calculado ao encerramento.",
          "", "5. RESSALVAS", ""]
    L += [f"  - {linha}" for linha in RESSALVAS]
    L += ["", ENCERRAMENTO, "", "_" * 40, t.nome, t.cargo]
    if t.matricula:
        L.append(f"Matrícula {t.matricula}")
    return "\n".join(L)
