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
import sys
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

    O corte de um pixel que abre a sequência não é capricho. O H.264 em
    yuv420p exige largura e altura pares, e a área de trabalho de quem
    tem dois monitores de alturas diferentes quase sempre é ímpar: o
    Windows alinha as telas pelo meio, e a sobra vertical do alinhamento
    entra na conta. Numa estação com 1280×720 ao lado de 1920×1080, a
    área virtual mede 3840×1339. O codificador recusava abrir — "height
    not divisible by 2" —, nada era escrito e sobrava um arquivo de zero
    byte, sem aviso. Com um monitor só, a conta dava par e ninguém
    percebia. Um pixel a menos na borda não muda o que se vê; o arquivo
    vazio muda tudo.
    """
    # Par também aqui: se a faixa tivesse altura ímpar, ela devolveria o
    # problema depois do corte.
    altura += altura % 2
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
        f"crop=trunc(iw/2)*2:trunc(ih/2)*2:0:0,"
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


#: Falhas conhecidas do codificador, ditas em português. A chave é o
#: trecho que o FFmpeg imprime; o valor, o que a pessoa precisa saber
#: para resolver. O que não estiver aqui vai cru, que é melhor do que
#: uma mensagem genérica: o texto do FFmpeg ao menos pode ser pesquisado.
_FALHAS = (
    ("not divisible by 2",
     "A área a gravar tem largura ou altura ímpar, e o formato de vídeo "
     "exige medidas pares. Costuma acontecer com dois monitores de "
     "alturas diferentes."),
    ("Could not find audio only device",
     "O microfone escolhido não foi encontrado. Ele pode ter sido "
     "desconectado, ou estar em uso por outro programa."),
    ("I/O error",
     "O microfone escolhido não pôde ser aberto. Ele pode estar em uso "
     "por outro programa."),
    ("Permission denied",
     "O sistema não deixou gravar no arquivo de destino."),
    ("No such file or directory",
     "A pasta de destino não existe ou não pôde ser criada."),
)


def _explicar_falha(erro: str) -> str:
    """Traduz o que o codificador disse, sem esconder o que ele disse."""
    for marca, explicacao in _FALHAS:
        if marca.lower() in erro.lower():
            return f"{explicacao}\n\nO codificador informou: {marca}"
    linhas = [x.strip() for x in erro.splitlines() if x.strip()]
    if linhas:
        return ("A gravação não começou. O codificador informou:\n\n"
                + "\n".join(linhas[-4:]))
    return "A gravação não começou, e o codificador não disse por quê."


# ─────────────────────────────────────────
#  A GRAVAÇÃO
# ─────────────────────────────────────────

@dataclass
class Opcoes:
    """Ajustes da captura."""

    monitor: str = "desktop"
    qualidade: str = "normal"
    #: Nome do dispositivo de entrada — o som da sala. Vazio, não grava.
    microfone: str = ""
    #: Grava também o que o computador reproduz. Entra como faixa
    #: separada, e não misturada com o microfone: a distinção entre o que
    #: a máquina tocou e o que foi dito na sala tem valor na peça, e
    #: misturar apaga essa distinção para sempre.
    audio_sistema: bool = False
    #: Identificação impressa na faixa — processo, operador, estação.
    identificacao: str = ""
    rodape: str = "SISTEMA TÊMIS — REGISTRO"
    #: Força quadro-chave a cada poucos segundos, para que uma queda de
    #: energia não leve a gravação inteira. Triplica o arquivo; veja a
    #: nota no alto do módulo.
    resistente: bool = True
    #: Pasta vigiada durante a gravação. Vazia, não se vigia nada — o
    #: monitoramento é opção, não padrão: filmar a tela é o que a
    #: ferramenta sempre faz, e resumir downloads é um acréscimo que quem
    #: opera liga quando a diligência envolve baixar arquivo.
    pasta_monitorada: str = ""
    #: Registrar as janelas que passam ao primeiro plano — o índice da
    #: diligência, sem capturar conteúdo. Opção, pelo mesmo motivo.
    registrar_janelas: bool = False

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
    #: O que aconteceu com a captura do som do sistema, quando pedida.
    captura_sistema: object = None
    contexto: Contexto | None = None
    opcoes: Opcoes | None = None
    baixados: list = field(default_factory=list)
    janelas: list = field(default_factory=list)
    erro: str = ""

    @property
    def duracao(self) -> str:
        s = int(self.segundos)
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


@dataclass
class Baixado:
    """Um arquivo que apareceu na pasta vigiada durante a gravação.

    O resumo é o elo forte, calculado sobre os bytes que estão em disco.
    O resto — quando apareceu, quanto tempo de gravação havia decorrido —
    é o que amarra o arquivo ao vídeo pela cronologia.
    """

    nome: str = ""
    caminho: str = ""
    tamanho: int = 0
    sha256: str = ""
    quando: str = ""
    decorrido: float = 0.0
    erro: str = ""


#: Sufixos de arquivo ainda em trânsito. O navegador baixa para um
#: `.crdownload` e só renomeia ao terminar; resumir no meio pegaria bytes
#: incompletos, e o resumo de um arquivo pela metade não confere com
#: nada. Espera-se o nome final.
EM_TRANSITO = (".crdownload", ".part", ".partial", ".tmp", ".download")


class MonitorDownloads:
    """Vigia uma pasta e resume cada arquivo novo que se estabiliza.

    Por observação de pasta, e não por instrumentação do navegador — é a
    diferença entre esta ferramenta e a Extração Registrada. A Gravação
    de Tela filma a área de trabalho inteira, e não é dona de navegador
    algum: não tem como saber de que endereço o arquivo veio, nem por
    qual clique. O que ela pode afirmar, e afirma, é mais estreito e
    verdadeiro: **este arquivo apareceu nesta pasta durante a gravação, e
    tem este resumo**.

    Um arquivo só é resumido quando para de crescer — dois exames
    seguidos com o mesmo tamanho —, para não pegar download pela metade.
    O que já estava na pasta antes de a gravação começar não entra: não
    foi esta diligência que o trouxe.
    """

    #: Segundos que um arquivo precisa ficar do mesmo tamanho para ser
    #: dado por completo. Duas passadas do pulso de 500 ms, com folga.
    ESTAVEL = 1.0

    def __init__(self, pasta: str | Path):
        self.pasta = Path(pasta)
        self._ja_existiam: set = set()
        self._tamanhos: dict = {}
        self._estaveis_desde: dict = {}
        self.baixados: list[Baixado] = []
        self._resumidos: set = set()

    def iniciar(self):
        """Fotografa o que já havia na pasta, para não confundir com o novo."""
        self._ja_existiam = set(self._listar())

    def _listar(self) -> list[Path]:
        try:
            return [a for a in self.pasta.iterdir() if a.is_file()]
        except OSError:
            return []

    def varrer(self, decorrido: float, agora: float):
        """Uma passada: registra os arquivos novos que já se estabilizaram.

        `agora` é o relógio monotônico de quem chama — passado de fora
        para que o núcleo não dependa de contador de tempo próprio e
        continue conferível numa prova.
        """
        for arquivo in self._listar():
            nome = arquivo.name
            if arquivo in self._ja_existiam or nome in self._resumidos:
                continue
            if nome.lower().endswith(EM_TRANSITO) or nome.startswith("~$"):
                continue
            try:
                tamanho = arquivo.stat().st_size
            except OSError:
                continue
            if self._tamanhos.get(nome) == tamanho and tamanho > 0:
                if agora - self._estaveis_desde.get(nome, agora) >= self.ESTAVEL:
                    self._resumir(arquivo, decorrido)
            else:
                self._tamanhos[nome] = tamanho
                self._estaveis_desde[nome] = agora

    def _resumir(self, arquivo: Path, decorrido: float):
        import datetime
        b = Baixado(
            nome=arquivo.name, caminho=str(arquivo),
            quando=datetime.datetime.now().astimezone().isoformat(
                timespec="seconds"),
            decorrido=decorrido)
        try:
            b.tamanho = arquivo.stat().st_size
            b.sha256 = sha256(arquivo)
        except OSError as e:
            b.erro = f"{type(e).__name__}: {e}"
        self.baixados.append(b)
        self._resumidos.add(arquivo.name)

    def concluir(self, decorrido: float, agora: float):
        """Última varredura, dando por completo o que ainda restava.

        No fim não se espera mais estabilização: a gravação acabou, e um
        arquivo que ainda estivesse crescendo é anomalia que a peça
        registra pelo tamanho do momento, em vez de deixar de fora.
        """
        self.varrer(decorrido, agora)
        for arquivo in self._listar():
            nome = arquivo.name
            if (arquivo in self._ja_existiam or nome in self._resumidos
                    or nome.lower().endswith(EM_TRANSITO)
                    or nome.startswith("~$")):
                continue
            self._resumir(arquivo, decorrido)


@dataclass
class Janela:
    """Uma janela que esteve em primeiro plano durante a gravação."""

    quando: str = ""
    decorrido: float = 0.0
    aplicativo: str = ""
    titulo: str = ""


def janela_em_foco() -> tuple:
    """(aplicativo, título) da janela em primeiro plano. ('', '') se não der.

    Só o nome do executável e o título que a janela publicou — nada do
    que se digitou ou clicou. O título é o mesmo que já aparece na barra
    filmada pelo vídeo; registrá-lo apenas torna pesquisável o que a
    imagem já mostra.
    """
    try:
        if sys.platform != "win32":
            return "", ""
        import ctypes
        from ctypes import wintypes

        u = ctypes.windll.user32
        k = ctypes.windll.kernel32
        # Sem argtypes/restype, o ctypes trata handle de 64 bits como
        # inteiro de 32 e o trunca — o defeito clássico, silencioso, que
        # faria a leitura apontar para janela nenhuma.
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR,
                                     ctypes.c_int]
        u.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
                                  wintypes.DWORD]
        k.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD)]
        k.CloseHandle.argtypes = [wintypes.HANDLE]

        hwnd = u.GetForegroundWindow()
        if not hwnd:
            return "", ""
        n = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        titulo = buf.value

        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        aplicativo = ""
        # PROCESS_QUERY_LIMITED_INFORMATION: o suficiente para ler o
        # nome, e o que uma estação sem privilégio consegue abrir.
        h = k.OpenProcess(0x1000, False, pid.value)
        if h:
            tamanho = wintypes.DWORD(260)
            nome = ctypes.create_unicode_buffer(260)
            if k.QueryFullProcessImageNameW(h, 0, nome, ctypes.byref(tamanho)):
                aplicativo = Path(nome.value).name
            k.CloseHandle(h)
        return aplicativo, titulo
    except Exception:                                   # noqa: BLE001
        return "", ""


class MonitorJanelas:
    """Anota cada troca de janela em primeiro plano durante a gravação.

    Registra a mudança, e não cada exame: uma linha por janela que
    assume a frente, com a hora e o tempo decorrido. Anotar a cada pulso
    encheria a peça de milhares de repetições da mesma janela.

    Não captura conteúdo — nem tecla, nem clique. Diz **qual** janela
    esteve à frente e **quando**, que é o índice navegável de uma imagem
    que o vídeo já contém por inteiro. Para o registro da transação em si,
    com endereço e parâmetros, existe a Extração Registrada; para o
    conteúdo, existe a própria imagem gravada.
    """

    def __init__(self, leitor=None):
        #: Injetável para poder provar sem tela: por padrão, lê o Windows.
        self._leitor = leitor or janela_em_foco
        self.registros: list[Janela] = []
        self._ultima = None

    def varrer(self, decorrido: float):
        import datetime
        aplicativo, titulo = self._leitor()
        if not aplicativo and not titulo:
            return
        atual = (aplicativo, titulo)
        if atual == self._ultima:
            return
        self._ultima = atual
        self.registros.append(Janela(
            quando=datetime.datetime.now().astimezone().isoformat(
                timespec="seconds"),
            decorrido=decorrido, aplicativo=aplicativo, titulo=titulo))


@dataclass
class Captura:
    """Uma captura de tela feita a pedido do operador, documentada.

    O resumo é o elo forte, calculado sobre os bytes da imagem no instante
    em que ela é salva. A hora vem do relógio qualificado, com fuso; o
    tempo decorrido, quando a captura acontece durante uma gravação,
    amarra a imagem ao vídeo pela cronologia.
    """

    nome: str = ""
    caminho: str = ""
    sha256: str = ""
    quando: str = ""
    tamanho: int = 0
    monitor: str = ""
    #: Segundos de gravação decorridos, ou None quando a captura é avulsa.
    decorrido: object = None
    erro: str = ""


def _tela_do_monitor(monitor: str):
    """A QScreen correspondente ao monitor escolhido, ou a principal."""
    try:
        from PyQt6.QtGui import QGuiApplication
        if monitor and monitor.startswith("monitor:"):
            i = int(monitor.split(":")[1])
            telas = QGuiApplication.screens()
            if 0 <= i < len(telas):
                return telas[i]
        return QGuiApplication.primaryScreen()
    except Exception:                                       # noqa: BLE001
        return None


def capturar_tela(pasta, indice: int, monitor: str = "",
                  decorrido=None) -> Captura:
    """Fotografa a tela, salva em PNG e resume — tudo num gesto.

    O resumo é tomado sobre a imagem já gravada em disco: é o que permite
    afirmar, depois, que a captura juntada aos autos é exatamente a que
    foi feita, e não outra.
    """
    from ..relogio import carimbo

    pasta = Path(pasta)
    nome = f"captura-{indice:03d}.png"
    alvo = pasta / nome
    c = Captura(nome=nome, caminho=str(alvo), quando=carimbo(),
                monitor=monitor, decorrido=decorrido)
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        tela = _tela_do_monitor(monitor)
        if tela is None:
            raise RuntimeError("nenhuma tela disponível para capturar")
        imagem = tela.grabWindow(0)
        if imagem.isNull() or not imagem.save(str(alvo), "PNG"):
            raise RuntimeError("não foi possível salvar a imagem")
        c.tamanho = alvo.stat().st_size
        c.sha256 = sha256(alvo)
    except Exception as e:                                  # noqa: BLE001
        c.erro = f"{type(e).__name__}: {e}"
    return c


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

    def _juntar_som_do_sistema(self, captura) -> str:
        """Acrescenta o som do sistema ao vídeo, como segunda faixa.

        Feito depois, e não durante: o FFmpeg lê o comando de parada pela
        entrada padrão, que não pode ser ocupada pelo áudio. Juntar ao
        fim custa poucos segundos — só o áudio é convertido, o vídeo é
        copiado como está — e mantém intacta a resistência a interrupção
        do arquivo principal, que se perderia num arranjo com fluxo
        contínuo.

        O deslocamento é medido, não estimado: é a diferença entre o
        instante em que a placa começou a entregar amostras e o instante
        em que o vídeo começou. O trecho de som anterior ao vídeo é
        descartado, para que os dois comecem juntos.
        """
        import shutil

        ffmpeg = ffmpeg_path()
        if ffmpeg is None or not Path(captura.arquivo).exists():
            return "arquivo de som não encontrado"

        atraso = max(0.0, getattr(self, "_video_comecou", 0.0)
                     - captura.inicio_relogio)
        juntado = self.destino.with_suffix(".juntado.mp4")
        cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
               "-i", str(self.destino),
               "-ss", f"{atraso:.3f}", "-i", str(captura.arquivo),
               "-map", "0", "-map", "1:a",
               "-c:v", "copy", "-c:a", "copy",
               f"-c:a:{1 if self.opcoes.microfone else 0}", "aac",
               "-b:a", "128k", "-shortest",
               str(juntado)]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=600,
                               creationflags=_SEM_JANELA)
        except Exception as e:                              # noqa: BLE001
            return f"{type(e).__name__}: {e}"
        if r.returncode != 0 or not juntado.exists():
            erro = (r.stderr or b"").decode("utf-8", "replace")
            return erro.strip().splitlines()[-1] if erro.strip() else "falhou"

        try:
            shutil.move(str(juntado), str(self.destino))
            Path(captura.arquivo).unlink(missing_ok=True)
        except OSError as e:
            return f"{type(e).__name__}: {e}"
        return ""

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

        # A captura do som do sistema abre **antes** do vídeo, e o vídeo
        # só começa quando a placa já está entregando amostras. A ordem
        # importa: a placa leva um tempo variável para abrir — medido,
        # cerca de três décimos de segundo — e começar o vídeo primeiro
        # jogaria o áudio adiantado desse tanto, sem que se soubesse de
        # quanto.
        self._captura = None
        if self.opcoes.audio_sistema:
            from .audio_sistema import CapturaSistema
            self._captura = CapturaSistema(
                self.destino.with_suffix(".sistema.wav"))
            if not self._captura.iniciar():
                self._erros.append(
                    "som do sistema: " + self._captura.resultado.erro)

        self._processo = subprocess.Popen(
            self.comando(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, creationflags=_SEM_JANELA)
        self._video_comecou = time.time()
        self._conferir_partida()

        # A pasta é fotografada só depois de a gravação ficar de pé: se o
        # codificador tivesse recusado a configuração, não haveria
        # diligência a que atribuir download algum.
        self._monitor = None
        if self.opcoes.pasta_monitorada:
            self._monitor = MonitorDownloads(self.opcoes.pasta_monitorada)
            self._monitor.iniciar()
        self._janelas = (MonitorJanelas()
                         if self.opcoes.registrar_janelas else None)

    #: Quanto se espera para saber se o codificador ficou de pé.
    #:
    #: Medido, não estimado: o FFmpeg que recusa a configuração morre em
    #: torno de quatro décimos de segundo — abrir a captura e montar o
    #: filtro é tudo o que ele faz antes de desistir. Um segundo e meio
    #: cobre isso com margem, e é o que a diligência atrasa para começar.
    PARTIDA = 1.5

    def _conferir_partida(self):
        """Confere se a gravação de fato começou, em vez de supor.

        Abrir o processo sempre dá certo: quem recusa a configuração é o
        codificador, um instante depois, e o programa só olhava para isso
        ao encerrar. O operador conduzia a diligência inteira acreditando
        estar sendo gravado e encontrava, no fim, um arquivo de zero
        byte. Falhar aqui, na cara de quem começou, é a diferença entre
        um contratempo e uma diligência perdida.
        """
        limite = time.time() + self.PARTIDA
        while time.time() < limite:
            if self._processo.poll() is None:
                time.sleep(0.05)
                continue
            try:
                erro = self._processo.stderr.read().decode("utf-8", "replace")
            except (OSError, ValueError, AttributeError):
                erro = ""
            self._processo = None

            self._inicio = 0.0
            raise RuntimeError(_explicar_falha(erro))

    def varrer_downloads(self):
        """Uma passada dos monitores. Quem grava a chama pelo próprio pulso.

        Fica aqui, e não num relógio interno, porque o núcleo não conta
        tempo por conta própria — recebe o instante de fora, e assim
        continua conferível numa prova, sem depender de quando rodou.

        Nada aqui pode escapar: esta função roda no pulso do temporizador,
        e uma exceção não tratada num slot do Qt aborta o processo — o que
        derrubaria a gravação por causa de um monitor acessório. Falha de
        monitor vira anotação de erro, não fim de diligência.
        """
        try:
            if getattr(self, "_monitor", None) is not None:
                self._monitor.varrer(self.decorrido, time.time())
        except Exception as e:                              # noqa: BLE001
            self._erros.append(f"monitor de downloads: {e}")
        try:
            if getattr(self, "_janelas", None) is not None:
                self._janelas.varrer(self.decorrido)
        except Exception as e:                              # noqa: BLE001
            self._erros.append(f"registro de janelas: {e}")

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

        # A captura para depois do vídeo, nunca antes: parar antes
        # deixaria o fim da diligência sem som, e é justamente o fim que
        # costuma interessar.
        if getattr(self, "_captura", None) is not None:
            captura = self._captura.encerrar()
            resultado.captura_sistema = captura
            self._captura = None
            if captura.houve_falha:
                self._erros.append(f"som do sistema: {captura.erro}")
            else:
                erro = self._juntar_som_do_sistema(captura)
                if erro:
                    self._erros.append(f"som do sistema: {erro}")

        resultado.segundos = self.decorrido
        resultado.fim = datetime.datetime.now().astimezone().isoformat(
            timespec="seconds")
        self._inicio = 0.0
        self._limpar_andaime()

        if not self.destino.is_file():
            resultado.erro = ("A gravação não produziu arquivo.\n"
                              + "\n".join(self._erros))
            return resultado

        if getattr(self, "_monitor", None) is not None:
            self._monitor.concluir(self.decorrido, time.time())
            resultado.baixados = list(self._monitor.baixados)
            self._monitor = None
        if getattr(self, "_janelas", None) is not None:
            self._janelas.varrer(self.decorrido)
            resultado.janelas = list(self._janelas.registros)
            self._janelas = None

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

#: O que o monitoramento de pasta prova, e o que não prova. Vai impresso
#: quando houver arquivo na relação — apresentar o que se observou de
#: fora como se fosse transação capturada na origem seria atribuir à peça
#: alcance que ela não tem.
RESSALVA_DOWNLOADS = (
    "Os arquivos relacionados apareceram na pasta vigiada no intervalo da "
    "gravação, e cada um foi resumido em SHA-256 sobre os bytes gravados "
    "em disco. O monitoramento é de pasta, e não do navegador: a peça "
    "atesta que o arquivo surgiu ali naquele instante, com aquele resumo, "
    "e não a origem de que veio nem o ato que o trouxe — para o registro "
    "da própria transação, com endereço e parâmetros, existe a Extração "
    "Registrada. O resumo permite conferir, a qualquer tempo, que o "
    "arquivo é o mesmo que se observou chegar."
)

#: O que a relação de janelas é, e o que não é. Vai impresso quando
#: houver janelas na peça.
RESSALVA_CAPTURAS = (
    "As capturas de tela foram feitas a pedido do operador, no instante "
    "indicado, e cada uma foi resumida em SHA-256 sobre a imagem gravada em "
    "disco. O resumo permite conferir, a qualquer tempo, que a captura "
    "juntada aos autos é a mesma que foi feita. As imagens acompanham "
    "esta peça."
)

RESSALVA_JANELAS = (
    "A relação de janelas indica quais aplicativos e janelas estiveram em "
    "primeiro plano durante a gravação, e em que momento. Os títulos são "
    "os que os próprios aplicativos exibiam — o mesmo texto que a barra "
    "de título mostra na imagem gravada —, e servem de índice navegável "
    "do vídeo. A relação não captura o que foi digitado nem em que se "
    "clicou: registra qual janela esteve à frente, e quando."
)

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
    cargo: str = field(default_factory=cargo_padrao)
    orgao: str = field(default_factory=orgao_padrao)
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
    #: Capturas de tela feitas a pedido do operador, com hash e hora.
    capturas: list = field(default_factory=list)

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


def descrever_audio(r) -> str:
    """Como o áudio daquele registro é dito na peça.

    Precisa ser exato. Antes, qualquer gravação com som era descrita como
    "com áudio do microfone", o que é verdade quando só há microfone e
    falso quando há som do computador — e quem lesse entenderia que o
    áudio reproduzido na tela ficou registrado, quando não ficava.
    """
    captura = getattr(r, "captura_sistema", None)
    tem_sistema = captura is not None and not captura.houve_falha
    if r.com_audio and tem_sistema:
        return ("duas faixas de áudio: 1 — som do ambiente, captado pelo "
                "microfone; 2 — som reproduzido pelo computador")
    if tem_sistema:
        return "áudio do som reproduzido pelo computador"
    if r.com_audio:
        return ("áudio do ambiente, captado pelo microfone; o som "
                "reproduzido pelo computador não foi registrado")
    return "sem áudio"


def _quadro_registros(t: TermoGravacao) -> str:
    linhas = []
    for i, r in enumerate(t.bons, 1):
        audio = descrever_audio(r)
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


def _quadro_downloads(baixados: list) -> str:
    """A relação de arquivos observados chegar durante a gravação."""
    linhas = []
    for i, b in enumerate(baixados, 1):
        segundos = int(b.decorrido)
        decorrido = (f"{segundos // 3600:02d}:{(segundos % 3600) // 60:02d}:"
                     f"{segundos % 60:02d}")
        detalhe = (formatar_tamanho(b.tamanho) if b.sha256
                   else (b.erro or "não foi possível resumir"))
        linhas.append(
            "<tr>"
            + _cel(i, "center")
            + _cel(b.nome)
            + _cel(f"{data_br(b.quando)}\n(decorrido {decorrido})")
            + _cel(detalhe)
            + "</tr>"
            + "<tr>"
            + _cel("", "center")
            + (f'<td colspan="3"><font color="{INK}" face="Courier New" '
               f'size="1">SHA-256: {b.sha256}</font></td>' if b.sha256
               else '<td colspan="3"></td>')
            + "</tr>")
    return (
        '<table width="100%" cellspacing="0" cellpadding="4" border="1" '
        'style="border-collapse:collapse; font-size:8.5pt;">'
        '<tr style="background-color:#0a2442; color:#ffd633;">'
        '<th width="4%">Nº</th><th width="34%">Arquivo</th>'
        '<th width="30%">Observado em</th>'
        '<th width="32%">Tamanho</th></tr>'
        f"{''.join(linhas)}</table>")


def _quadro_janelas(janelas: list) -> str:
    """A linha do tempo das janelas em primeiro plano."""
    linhas = []
    for i, j in enumerate(janelas, 1):
        segundos = int(j.decorrido)
        decorrido = (f"{segundos // 3600:02d}:{(segundos % 3600) // 60:02d}:"
                     f"{segundos % 60:02d}")
        linhas.append(
            "<tr>"
            + _cel(i, "center")
            + _cel(decorrido, "center", "Courier New")
            + _cel(j.aplicativo or "—")
            + _cel(j.titulo or "(sem título)")
            + "</tr>")
    return (
        '<table width="100%" cellspacing="0" cellpadding="4" border="1" '
        'style="border-collapse:collapse; font-size:8.5pt;">'
        '<tr style="background-color:#0a2442; color:#ffd633;">'
        '<th width="4%">Nº</th><th width="14%">Decorrido</th>'
        '<th width="28%">Aplicativo</th><th width="54%">Título da janela</th>'
        '</tr>'
        f"{''.join(linhas)}</table>")


def _quadro_capturas(capturas: list) -> str:
    """A relação das capturas de tela feitas na diligência."""
    import html as _h
    e = _h.escape
    linhas = []
    for i, c in enumerate(capturas, 1):
        if c.decorrido is None:
            momento = ""
        else:
            s = int(c.decorrido)
            momento = (f" (decorrido {s // 3600:02d}:{(s % 3600) // 60:02d}:"
                       f"{s % 60:02d})")
        detalhe = (formatar_tamanho(c.tamanho) if c.sha256
                   else (c.erro or "não foi possível capturar"))
        linhas.append(
            "<tr>"
            + _cel(i, "center")
            + _cel(c.nome)
            + _cel(e(c.quando) + momento)
            + _cel(detalhe)
            + "</tr><tr>"
            + _cel("", "center")
            + (f'<td colspan="3"><font color="{INK}" face="Courier New" '
               f'size="1">SHA-256: {c.sha256}</font></td>' if c.sha256
               else '<td colspan="3"></td>')
            + "</tr>")
    return (
        '<table width="100%" cellspacing="0" cellpadding="4" border="1" '
        'style="border-collapse:collapse; font-size:8.5pt;">'
        '<tr style="background-color:#0a2442; color:#ffd633;">'
        '<th width="4%">Nº</th><th width="30%">Arquivo</th>'
        '<th width="34%">Feita em</th><th width="32%">Tamanho</th></tr>'
        + "".join(linhas) + "</table>")


def build_html(t: TermoGravacao) -> str:
    """Termo em HTML, para exibir e exportar."""
    from ..impressao import cabecalho_html, rodape_html
    import html as _html
    e = _html.escape

    partes = [
        "<html><body style=\"font-family:'Segoe UI',Arial,sans-serif; "
        'color:#16233a;">',
        cabecalho_html(),
        '<div align="center" style="margin-bottom:18px;">'
        '<b style="font-size:14pt; letter-spacing:0.5px;">'
        "Termo de Registro Audiovisual de Diligência em Meio Eletrônico"
        "</b></div>",
        "<hr/>",
        f'<p align="justify" style="font-size:11pt; line-height:160%;">'
        f"{e(intro_gravacao(t))}</p>",
    ]

    # A numeração das seções é contada, e não escrita à mão: duas seções
    # são opcionais (arquivos recebidos, janelas), e número fixo já
    # obrigava a acertar método e ressalvas a cada uma que entrasse.
    _n = [0]
    def secao(titulo):
        _n[0] += 1
        return (f'<p style="font-size:11pt;"><b>{_n[0]}. '
                + titulo + "</b></p>")

    partes += [
        secao("Objeto da diligência"),
        f'<p align="justify" style="font-size:10.5pt; line-height:150%;">'
        f"{e(t.objeto)}</p>",
    ]
    if t.sistema_consultado:
        partes.append(
            f'<p align="justify" style="font-size:10.5pt; line-height:150%;">'
            f"Sistema consultado: {e(t.sistema_consultado)}.</p>")

    # ── estação e operador ────────────────
    contexto = t.bons[0].contexto if t.bons else None
    partes.append(secao("Estação em que se realizou o registro"))
    if contexto is not None:
        partes.append(_quadro(contexto.linhas()))
    partes.append(
        '<p align="justify" style="font-size:10.5pt; line-height:150%; '
        'margin-top:8px;">'
        "Os dados acima foram lidos da própria estação no instante em que a "
        "gravação teve início.</p>")

    # ── os registros ──────────────────────
    partes.append(secao("Registro(s) produzido(s)"))
    partes.append(_quadro_registros(t))
    partes.append(
        '<p align="justify" style="font-size:10.5pt; line-height:150%; '
        'margin-top:8px;">'
        "O resumo criptográfico SHA-256 consignado permite conferir, a "
        "qualquer tempo, a identidade entre o arquivo juntado aos autos e "
        "o que foi produzido nesta diligência. Valor diverso indica que o "
        "arquivo não é o mesmo.</p>")

    # ── downloads observados ──────────────
    baixados = [b for r in t.bons for b in getattr(r, "baixados", [])]
    if baixados:
        partes.append(secao("Arquivos recebidos durante a diligência"))
        partes.append(_quadro_downloads(baixados))
        partes.append(
            '<p align="justify" style="font-size:10.5pt; line-height:150%; '
            'margin-top:8px;">' + e(RESSALVA_DOWNLOADS) + "</p>")

    # ── janelas em primeiro plano ─────────
    janelas = [j for r in t.bons for j in getattr(r, "janelas", [])]
    if janelas:
        partes.append(secao("Janelas em primeiro plano durante a diligência"))
        partes.append(_quadro_janelas(janelas))
        partes.append(
            '<p align="justify" style="font-size:10.5pt; line-height:150%; '
            'margin-top:8px;">' + e(RESSALVA_JANELAS) + "</p>")

    # ── capturas de tela ──────────────────
    if t.capturas:
        partes.append(secao("Capturas de tela"))
        partes.append(_quadro_capturas(t.capturas))
        partes.append(
            '<p align="justify" style="font-size:10.5pt; line-height:150%; '
            'margin-top:8px;">' + e(RESSALVA_CAPTURAS) + "</p>")

    # ── método ────────────────────────────
    partes.append(secao("Método"))
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
    if baixados:
        metodo.append(
            "Durante a gravação, vigiou-se uma pasta do sistema de "
            "arquivos, e cada arquivo novo que nela se estabilizou foi "
            "resumido em SHA-256 sobre os bytes gravados em disco, no "
            "instante em que se completou. A relação consta da seção 4.")
    # O que foi captado, e — o que importa tanto quanto — o que não foi.
    # Silenciar sobre a fonte do som é o tipo de omissão que a defesa
    # encontra depois: quem lê "com áudio" supõe que tudo o que se ouviu
    # na diligência ficou registrado.
    primeiro = t.bons[0] if t.bons else None
    if primeiro is not None and primeiro.opcoes:
        captura = getattr(primeiro, "captura_sistema", None)
        tem_sistema = captura is not None and not captura.houve_falha
        if primeiro.opcoes.microfone:
            metodo.append(
                f"O som do ambiente foi captado do dispositivo "
                f"“{primeiro.opcoes.microfone}” em conjunto com a imagem.")
        if tem_sistema:
            metodo.append(
                "O som reproduzido pelo computador foi captado diretamente "
                "da placa de áudio, e não pelo microfone, ficando em faixa "
                "própria do arquivo — de modo que o que a máquina "
                "reproduziu e o que foi dito no ambiente permanecem "
                "distinguíveis."
                + (f" Saída de áudio: “{captura.dispositivo}”."
                   if captura.dispositivo else ""))
        elif not primeiro.opcoes.audio_sistema:
            metodo.append(
                "O som reproduzido pelo computador não foi registrado: a "
                "gravação captou apenas a imagem"
                + (" e o som do ambiente."
                   if primeiro.opcoes.microfone else "."))
        if captura is not None and captura.houve_falha:
            metodo.append(
                "A captação do som reproduzido pelo computador foi "
                "solicitada, mas não se completou"
                + (f", tendo sido interrompida após "
                   f"{captura.interrompida_em:.0f} segundos"
                   if captura.interrompida_em else "")
                + f". Motivo registrado: {captura.erro}.")
    partes += [f'<p align="justify" style="font-size:10.5pt; '
               f'line-height:150%;">{e(linha)}</p>' for linha in metodo]

    # ── ressalvas ─────────────────────────
    partes.append(secao("Ressalvas"))
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
        + "</div>" + rodape_html("video") + "</body></html>")
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
