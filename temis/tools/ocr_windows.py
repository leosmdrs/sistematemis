"""
Reconhecimento óptico de caracteres pelo motor do próprio Windows.

Um documento digitalizado é uma fotografia de papel: para o computador
não há texto ali, só pontos. Sem OCR, a página aparece na lista de
arquivos mas nada do que está escrito nela pode ser encontrado — e é
justamente no ofício escaneado, no print de conversa e na foto de
documento que costuma estar o que interessa.

Por que o motor do Windows e não o Tesseract: o `Windows.Media.Ocr` já
vem no sistema operacional. A ligação com o Python custa 3,5 MB no
instalador, contra cerca de 50 MB do Tesseract e 134 MB de um motor
baseado em rede neural própria. Medido num termo de declaração
rasterizado a 200 dpi, com ruído e meio grau de rotação, ele devolveu o
texto com todos os acentos corretos — "DECLARAÇÃO", "quilômetro",
"conferência", "condução" —, errando apenas a placa da rodovia, onde
confundiu algarismos com letras em fonte serifada.

O idioma depende do que está instalado na máquina. Português do Brasil
acompanha as instalações brasileiras do Windows; quando falta, o texto é
lido pelo reconhecedor inglês, que acerta as letras e erra parte dos
acentos. Quando não há reconhecedor nenhum, o OCR simplesmente não é
oferecido, em vez de o programa fingir que leu.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field

#: Preferência de idioma, na ordem em que se tenta.
PREFERIDOS = ("pt-BR", "pt-PT", "pt", "en-US", "en")

#: Resolução de rasterização das páginas de PDF antes do OCR. Abaixo de
#: 200 dpi o motor começa a perder acento; acima de 300 o ganho não
#: compensa o tempo.
DPI = 220

_erro_importacao = ""

try:
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import (
        BitmapAlphaMode, BitmapDecoder, BitmapPixelFormat, SoftwareBitmap,
    )
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import (
        DataWriter, InMemoryRandomAccessStream,
    )
except Exception as e:                                      # noqa: BLE001
    _erro_importacao = f"{type(e).__name__}: {e}"
    OcrEngine = None                                        # type: ignore


#: Marca por thread: o WinRT exige que o apartamento COM seja iniciado em
#: cada uma. A varredura roda numa thread de trabalho, não na principal.
_local = threading.local()


def _preparar_thread():
    if getattr(_local, "pronta", False):
        return
    try:
        from winrt.runtime import init_apartment
        init_apartment()
    except Exception:                                       # noqa: BLE001
        # Já iniciado, ou versão que dispensa a chamada.
        pass
    _local.pronta = True


# ─────────────────────────────────────────
#  DISPONIBILIDADE
# ─────────────────────────────────────────

def idiomas() -> list[str]:
    """Etiquetas dos reconhecedores instalados nesta máquina."""
    if OcrEngine is None:
        return []
    try:
        _preparar_thread()
        return [l.language_tag for l in OcrEngine.available_recognizer_languages]
    except Exception:                                       # noqa: BLE001
        return []


def idioma_preferido() -> str:
    """O melhor reconhecedor disponível, ou vazio se não houver nenhum."""
    disponiveis = idiomas()
    for tag in PREFERIDOS:
        for d in disponiveis:
            if d.lower() == tag.lower() or d.lower().startswith(tag.lower() + "-"):
                return d
    return disponiveis[0] if disponiveis else ""


def disponivel() -> bool:
    return bool(idioma_preferido())


def diagnostico() -> str:
    """Uma linha sobre o estado do OCR, para mostrar ao usuário."""
    if _erro_importacao:
        return f"OCR indisponível: {_erro_importacao}"
    tag = idioma_preferido()
    if not tag:
        return ("OCR indisponível: nenhum idioma de reconhecimento instalado. "
                "Acrescente em Configurações do Windows › Hora e idioma › "
                "Idioma e região › Português (Brasil) › Opções de idioma › "
                "Reconhecimento óptico de caracteres.")
    if tag.lower().startswith("pt"):
        return f"OCR do Windows em {tag}."
    return (f"OCR do Windows em {tag} — sem o reconhecedor de português, "
            f"os acentos saem imprecisos.")


# ─────────────────────────────────────────
#  LEITURA
# ─────────────────────────────────────────

@dataclass
class Palavra:
    """Uma palavra reconhecida e onde ela está na imagem.

    As coordenadas vêm em pixels da imagem submetida, com origem no
    canto superior esquerdo. Quem for desenhar sobre o documento
    original precisa convertê-las para a escala dele.
    """

    texto: str
    x: float
    y: float
    largura: float
    altura: float

    @property
    def direita(self) -> float:
        return self.x + self.largura

    @property
    def base(self) -> float:
        return self.y + self.altura


@dataclass
class Linha:
    """Uma linha de texto e as palavras que a compõem."""

    texto: str
    palavras: list[Palavra] = field(default_factory=list)

    @property
    def topo(self) -> float:
        return min((p.y for p in self.palavras), default=0.0)

    @property
    def base(self) -> float:
        return max((p.base for p in self.palavras), default=0.0)

    @property
    def altura(self) -> float:
        return max(0.0, self.base - self.topo)


@dataclass
class Leitura:
    """O resultado completo de uma imagem."""

    linhas: list[Linha] = field(default_factory=list)
    #: Inclinação do texto detectada pelo motor, em graus. Página torta
    #: de escâner costuma vir com um a dois graus.
    inclinacao: float = 0.0

    @property
    def texto(self) -> str:
        return "\n".join(l.texto for l in self.linhas)

    @property
    def palavras(self) -> list[Palavra]:
        return [p for l in self.linhas for p in l.palavras]


class Motor:
    """Reconhecedor reutilizável.

    Vale manter um por varredura: criar o motor é a parte cara, ler cada
    imagem é barato.
    """

    def __init__(self, tag: str = ""):
        _preparar_thread()
        self.tag = tag or idioma_preferido()
        self._motor = None
        if OcrEngine is not None and self.tag:
            try:
                self._motor = OcrEngine.try_create_from_language(Language(self.tag))
            except Exception:                               # noqa: BLE001
                self._motor = None

    @property
    def pronto(self) -> bool:
        return self._motor is not None

    def texto(self, imagem: bytes) -> str:
        """Texto reconhecido numa imagem codificada (PNG, JPEG, TIFF…).

        Devolve string vazia quando não há motor ou quando a imagem não
        pode ser decodificada — nunca levanta, porque isso interromperia
        a varredura inteira por causa de um arquivo ruim.
        """
        return self.ler(imagem).texto

    def ler(self, imagem: bytes) -> Leitura:
        """Texto **e** posição de cada palavra.

        É o que permite colar uma camada de texto invisível sobre um
        documento digitalizado: sem as coordenadas, o texto existiria no
        arquivo mas não estaria em lugar nenhum da página.
        """
        if self._motor is None or not imagem:
            return Leitura()
        try:
            return asyncio.run(self._ler(imagem))
        except Exception:                                   # noqa: BLE001
            return Leitura()

    async def _bitmap(self, imagem: bytes):
        fluxo = InMemoryRandomAccessStream()
        escritor = DataWriter(fluxo)
        escritor.write_bytes(imagem)
        await escritor.store_async()
        await fluxo.flush_async()
        fluxo.seek(0)

        decodificador = await BitmapDecoder.create_async(fluxo)
        bitmap = await decodificador.get_software_bitmap_async()
        if bitmap.bitmap_pixel_format != BitmapPixelFormat.BGRA8:
            bitmap = SoftwareBitmap.convert(
                bitmap, BitmapPixelFormat.BGRA8, BitmapAlphaMode.PREMULTIPLIED)
        return bitmap

    async def _ler(self, imagem: bytes) -> Leitura:
        bitmap = await self._bitmap(imagem)
        bruto = await self._motor.recognize_async(bitmap)
        linhas = []
        for linha in bruto.lines:
            palavras = [
                Palavra(p.text, p.bounding_rect.x, p.bounding_rect.y,
                        p.bounding_rect.width, p.bounding_rect.height)
                for p in linha.words]
            linhas.append(Linha(linha.text, palavras))
        return Leitura(linhas, float(bruto.text_angle or 0.0))


def ler_imagem(caminho) -> str:
    """Atalho para um arquivo de imagem solto."""
    from pathlib import Path
    motor = Motor()
    if not motor.pronto:
        return ""
    try:
        return motor.texto(Path(caminho).read_bytes())
    except OSError:
        return ""
