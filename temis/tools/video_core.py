"""
Motor de edição de vídeo — compactar, fatiar e mesclar.

Encapsula o FFmpeg. Sem dependência de interface, para poder ser testado
isoladamente.

O binário é procurado primeiro dentro do próprio programa (empacotado),
depois na pasta `vendor/` do projeto e só então no PATH do sistema. Assim
o Têmis funciona numa estação sem nenhum pré-requisito instalado, que é o
caso das máquinas onde ele vai rodar.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# ─────────────────────────────────────────
#  LOCALIZAÇÃO DO FFMPEG
# ─────────────────────────────────────────

#: Evita a janela preta de console piscando a cada chamada, no Windows.
_SEM_JANELA = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _candidatos(nome: str) -> list[Path]:
    exe = f"{nome}.exe" if sys.platform == "win32" else nome
    locais: list[Path] = []

    # 1. dentro do executável empacotado
    base = getattr(sys, "_MEIPASS", None)
    if base:
        locais += [Path(base) / "ffmpeg" / exe,
                   Path(base) / "ffmpeg" / "bin" / exe]

    # 2. ao lado do executável instalado
    if getattr(sys, "frozen", False):
        raiz = Path(sys.executable).parent
        locais += [raiz / "ffmpeg" / exe, raiz / "ffmpeg" / "bin" / exe]

    # 3. pasta vendor/ do projeto (execução a partir do código)
    projeto = Path(__file__).resolve().parents[2]
    locais += [projeto / "vendor" / "ffmpeg" / "bin" / exe,
               projeto / "vendor" / "ffmpeg" / exe]
    return locais


def localizar(nome: str) -> Path | None:
    for caminho in _candidatos(nome):
        if caminho.is_file():
            return caminho
    from shutil import which
    achado = which(nome)
    return Path(achado) if achado else None


def ffmpeg_path() -> Path | None:
    return localizar("ffmpeg")


def ffprobe_path() -> Path | None:
    return localizar("ffprobe")


def disponivel() -> bool:
    return ffmpeg_path() is not None and ffprobe_path() is not None


def versao() -> str:
    exe = ffmpeg_path()
    if exe is None:
        return ""
    try:
        saida = subprocess.run([str(exe), "-version"], capture_output=True,
                               text=True, timeout=15,
                               creationflags=_SEM_JANELA).stdout
        return saida.splitlines()[0] if saida else ""
    except Exception:
        return ""


# ─────────────────────────────────────────
#  SONDAGEM
# ─────────────────────────────────────────

@dataclass
class VideoInfo:
    caminho: str
    duracao: float = 0.0          # segundos
    largura: int = 0
    altura: int = 0
    fps: float = 0.0
    codec: str = ""
    codec_audio: str = ""
    bitrate: int = 0              # bits/s
    tamanho: int = 0              # bytes

    @property
    def nome(self) -> str:
        return Path(self.caminho).name

    @property
    def resolucao(self) -> str:
        return f"{self.largura}×{self.altura}" if self.largura else "—"

    def compativel_com(self, outro: "VideoInfo") -> bool:
        """Podem ser mesclados sem recodificar?

        O demuxer `concat` só junta fluxos com os mesmos parâmetros; se
        divergirem, o arquivo resultante fica corrompido ou perde trechos.
        """
        return (self.codec == outro.codec
                and self.codec_audio == outro.codec_audio
                and self.largura == outro.largura
                and self.altura == outro.altura)


def _fracao(txt: str) -> float:
    try:
        if "/" in txt:
            a, b = txt.split("/")
            return float(a) / float(b) if float(b) else 0.0
        return float(txt)
    except (ValueError, ZeroDivisionError):
        return 0.0


def sondar(caminho: str | Path) -> VideoInfo:
    """Lê os metadados do arquivo. Levanta RuntimeError se não der."""
    exe = ffprobe_path()
    if exe is None:
        raise RuntimeError("ffprobe não encontrado")

    cmd = [str(exe), "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", str(caminho)]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          creationflags=_SEM_JANELA)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "não foi possível ler o arquivo")

    dados = json.loads(proc.stdout or "{}")
    fmt = dados.get("format", {})
    streams = dados.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})

    if not video:
        raise RuntimeError("o arquivo não contém trilha de vídeo")

    return VideoInfo(
        caminho=str(caminho),
        duracao=float(fmt.get("duration") or video.get("duration") or 0.0),
        largura=int(video.get("width") or 0),
        altura=int(video.get("height") or 0),
        fps=_fracao(video.get("avg_frame_rate") or "0"),
        codec=video.get("codec_name", ""),
        codec_audio=audio.get("codec_name", ""),
        bitrate=int(fmt.get("bit_rate") or 0),
        tamanho=int(fmt.get("size") or Path(caminho).stat().st_size),
    )


# ─────────────────────────────────────────
#  APOIO
# ─────────────────────────────────────────

def formatar_tempo(seg: float) -> str:
    seg = max(0.0, seg)
    h, resto = divmod(int(seg), 3600)
    m, s = divmod(resto, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def ler_tempo(txt: str) -> float:
    """Aceita 'ss', 'mm:ss' ou 'hh:mm:ss' e devolve segundos."""
    partes = [p.strip() for p in str(txt).strip().split(":") if p.strip() != ""]
    if not partes:
        return 0.0
    try:
        valores = [float(p.replace(",", ".")) for p in partes]
    except ValueError:
        return 0.0
    total = 0.0
    for v in valores:
        total = total * 60 + v
    return total


def formatar_tamanho(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


# ─────────────────────────────────────────
#  QUALIDADE
# ─────────────────────────────────────────

@dataclass(frozen=True)
class Preset:
    chave: str
    rotulo: str
    crf: int
    preset: str
    descricao: str


PRESETS = [
    Preset("alta", "Alta qualidade", 20, "slow",
           "Perda visual mínima. Reduz pouco o tamanho."),
    Preset("equilibrado", "Equilibrado", 26, "medium",
           "Boa legibilidade da cena com redução significativa."),
    Preset("maxima", "Máxima redução", 32, "medium",
           "Arquivo bem menor. Perde detalhe fino, como placas ao longe."),
]

ESCALAS = [
    ("original", "Manter resolução", 0),
    ("1080", "1080p", 1080),
    ("720", "720p", 720),
    ("480", "480p", 480),
]


def preset_por_chave(chave: str) -> Preset:
    return next((p for p in PRESETS if p.chave == chave), PRESETS[1])


# ─────────────────────────────────────────
#  MONTAGEM DOS COMANDOS
# ─────────────────────────────────────────

#: Trilhas que o MP4 aceita como estão, sem recodificar.
AUDIO_COPIAVEL = {"aac", "mp3", "ac3", "alac"}


def cmd_compactar(entrada: str, saida: str, preset: Preset,
                  altura_alvo: int = 0, sem_audio: bool = False,
                  codec_audio: str = "") -> list[str]:
    cmd = [str(ffmpeg_path()), "-y", "-i", str(entrada)]
    if altura_alvo:
        # -2 mantém a proporção e garante largura par, exigida pelo H.264.
        cmd += ["-vf", f"scale=-2:{altura_alvo}"]
    cmd += ["-c:v", "libx264", "-crf", str(preset.crf),
            "-preset", preset.preset, "-pix_fmt", "yuv420p"]

    if sem_audio:
        cmd += ["-an"]
    elif codec_audio in AUDIO_COPIAVEL:
        # Copiar a trilha em vez de recodificar. Reencodar para 128 kbps um
        # áudio que já era menor que isso faz o arquivo *crescer* — o
        # oposto do que a ferramenta se propõe a fazer.
        cmd += ["-c:a", "copy"]
    else:
        cmd += ["-c:a", "aac", "-b:a", "128k"]

    cmd += ["-movflags", "+faststart", str(saida)]
    return cmd


def cmd_fatiar(entrada: str, saida: str, inicio: float, fim: float,
               recodificar: bool = False) -> list[str]:
    exe = str(ffmpeg_path())
    if recodificar:
        # -ss depois de -i: o corte cai no ponto exato pedido.
        cmd = [exe, "-y", "-i", str(entrada), "-ss", f"{inicio:.3f}"]
        if fim > inicio:
            cmd += ["-to", f"{fim:.3f}"]
        cmd += ["-c:v", "libx264", "-crf", "20", "-preset", "medium",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k"]
    else:
        # -ss antes de -i: busca rápida, mas o corte encosta no keyframe
        # anterior; sem recodificar não há como cair no quadro exato.
        cmd = [exe, "-y", "-ss", f"{inicio:.3f}", "-i", str(entrada)]
        if fim > inicio:
            cmd += ["-t", f"{fim - inicio:.3f}"]
        cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
    cmd += ["-movflags", "+faststart", str(saida)]
    return cmd


def escrever_lista_concat(entradas: list[str], destino: Path) -> Path:
    """Lista para o demuxer concat, com os caminhos escapados."""
    linhas = []
    for e in entradas:
        caminho = str(Path(e).resolve()).replace("\\", "/")
        linhas.append("file '" + caminho.replace("'", r"'\''") + "'")
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return destino


def cmd_mesclar(lista: Path, saida: str, recodificar: bool) -> list[str]:
    cmd = [str(ffmpeg_path()), "-y", "-f", "concat", "-safe", "0",
           "-i", str(lista)]
    if recodificar:
        cmd += ["-c:v", "libx264", "-crf", "22", "-preset", "medium",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k"]
    else:
        cmd += ["-c", "copy"]
    cmd += ["-movflags", "+faststart", str(saida)]
    return cmd


def precisa_recodificar(infos: list[VideoInfo]) -> bool:
    """Os arquivos divergem a ponto de exigir recodificação na mesclagem?"""
    return not all(infos[0].compativel_com(i) for i in infos[1:])


# ─────────────────────────────────────────
#  EXECUÇÃO
# ─────────────────────────────────────────

_TEMPO = re.compile(r"out_time_us=(\d+)")


def executar(cmd: list[str], duracao: float = 0.0,
             progresso=None, cancelado=None) -> tuple[bool, str]:
    """Roda o FFmpeg acompanhando o avanço.

    `progresso(fracao)` recebe 0..1; `cancelado()` interrompe a conversão.
    Devolve (deu_certo, mensagem_de_erro).
    """
    completo = list(cmd)
    # -progress em pipe dá um avanço estruturado, em vez de raspar o texto
    # de status que o FFmpeg escreve para o terminal.
    completo[1:1] = ["-nostdin", "-hide_banner", "-loglevel", "error",
                     "-progress", "pipe:1", "-nostats"]

    proc = subprocess.Popen(
        completo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, creationflags=_SEM_JANELA)

    try:
        for linha in proc.stdout:
            if cancelado and cancelado():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return False, "cancelado"
            if progresso and duracao > 0:
                m = _TEMPO.search(linha)
                if m:
                    progresso(min(1.0, int(m.group(1)) / 1e6 / duracao))
    finally:
        if proc.stdout:
            proc.stdout.close()

    erro = proc.stderr.read() if proc.stderr else ""
    if proc.stderr:
        proc.stderr.close()
    proc.wait()

    if proc.returncode != 0:
        return False, (erro.strip() or f"FFmpeg encerrou com código {proc.returncode}")
    if progresso:
        progresso(1.0)
    return True, ""
