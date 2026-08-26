"""
Captura do som que o computador reproduz.

O FFmpeg no Windows só enxerga dispositivos DirectShow, e som de saída
não é dispositivo de entrada: numa estação comum não há "Stereo Mix"
nenhum para gravar. Medido nesta máquina, o Windows expõe um único
dispositivo de captura — o microfone.

Daí este módulo. Ele pede ao Windows uma **captura de retorno** da placa
de som (o que a interface de áudio do sistema chama de *loopback*), lê o
que está sendo reproduzido e grava num arquivo WAV, que depois é somado
ao vídeo como uma segunda faixa.

Duas decisões de fundo:

**Faixa separada, e não misturada com o microfone.** Misturar é mais
simples de ouvir, mas apaga a distinção entre o que a máquina reproduziu
e o que foi dito na sala — e é justamente essa distinção que tem valor
numa peça. Separadas, quem assiste escolhe qual ouvir, e o termo pode
afirmar a origem de cada uma.

**Falha não interrompe a diligência.** Trocar de fone, desconectar um
monitor com alto-falante ou o Windows mudar a saída padrão derrubam a
captura. Perder a gravação inteira por causa disso seria pior do que
perder o áudio do sistema: a captura para, o vídeo continua, e o termo
declara a partir de que instante o som deixou de ser registrado.
"""

from __future__ import annotations

import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

#: Taxa e canais da captura. 48 kHz é a taxa nativa da maioria das placas
#: no Windows; pedir outra faz o sistema reamostrar, sem ganho algum.
TAXA = 48000
CANAIS = 2


def disponivel() -> tuple[bool, str]:
    """Diz se dá para capturar o som do sistema nesta máquina.

    Devolve (pode, explicação). A explicação existe para ir à tela: um
    botão que simplesmente não funciona é pior do que um botão que diz
    por que não pode.
    """
    try:
        import soundcard
    except Exception as e:                                  # noqa: BLE001
        return (False, f"biblioteca de áudio indisponível: "
                       f"{type(e).__name__}")
    try:
        saida = soundcard.default_speaker()
        if saida is None:
            return (False, "o Windows não indica uma saída de áudio padrão")
        soundcard.get_microphone(str(saida.name), include_loopback=True)
        return (True, str(saida.name))
    except Exception as e:                                  # noqa: BLE001
        return (False, f"a placa de som não oferece captura de retorno: "
                       f"{type(e).__name__}")


@dataclass
class Captura:
    """O resultado da captura, para o termo."""

    arquivo: str = ""
    dispositivo: str = ""
    segundos: float = 0.0
    #: Instante em que a captura começou, medido pelo relógio do
    #: processo. Serve para alinhar o áudio ao vídeo.
    inicio_relogio: float = 0.0
    interrompida_em: float = 0.0
    erro: str = ""

    @property
    def houve_falha(self) -> bool:
        return bool(self.erro)


class CapturaSistema:
    """Grava, numa thread, o que o computador está reproduzindo."""

    #: De quantos em quantos quadros se lê da placa. Blocos curtos
    #: mantêm a parada rápida; muito curtos gastam processador à toa.
    BLOCO = 4096

    def __init__(self, destino: str | Path):
        self.destino = Path(destino)
        self.resultado = Captura(arquivo=str(destino))
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None

    # ── ciclo ────────────────────────────────
    def iniciar(self) -> bool:
        """Começa a capturar. Devolve se conseguiu."""
        pode, detalhe = disponivel()
        if not pode:
            self.resultado.erro = detalhe
            return False
        self.resultado.dispositivo = detalhe
        # O evento é o que sincroniza: a thread avisa quando a placa já
        # está entregando amostras, e só então o vídeo começa. Sem isso,
        # o áudio entraria atrasado do tempo que a placa leva para abrir
        # — que é variável e não se pode adivinhar.
        pronto = threading.Event()
        self._thread = threading.Thread(
            target=self._correr, args=(pronto,), daemon=True)
        self._thread.start()
        pronto.wait(timeout=5.0)
        return not self.resultado.houve_falha

    def encerrar(self, espera: float = 5.0) -> Captura:
        self._parar.set()
        if self._thread is not None:
            self._thread.join(timeout=espera)
        return self.resultado

    # ── a thread ─────────────────────────────
    def _correr(self, pronto: threading.Event):
        import soundcard

        try:
            saida = soundcard.default_speaker()
            retorno = soundcard.get_microphone(str(saida.name),
                                               include_loopback=True)
            self.destino.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(self.destino), "wb") as arquivo:
                arquivo.setnchannels(CANAIS)
                arquivo.setsampwidth(2)          # 16 bits
                arquivo.setframerate(TAXA)
                with retorno.recorder(samplerate=TAXA,
                                      channels=CANAIS) as gravador:
                    # A primeira leitura é a que abre o fluxo de verdade;
                    # só depois dela o relógio da captura vale.
                    quadros = gravador.record(numframes=self.BLOCO)
                    self.resultado.inicio_relogio = time.time()
                    pronto.set()
                    arquivo.writeframes(self._para_bytes(quadros))

                    while not self._parar.is_set():
                        quadros = gravador.record(numframes=self.BLOCO)
                        arquivo.writeframes(self._para_bytes(quadros))
                        self.resultado.segundos += len(quadros) / TAXA
        except Exception as e:                              # noqa: BLE001
            self.resultado.erro = f"{type(e).__name__}: {e}"
            self.resultado.interrompida_em = self.resultado.segundos
        finally:
            pronto.set()

    @staticmethod
    def _para_bytes(quadros) -> bytes:
        """Converte as amostras de ponto flutuante para 16 bits.

        A placa entrega valores entre -1 e 1. O corte em ±1 antes da
        multiplicação evita que um pico estourado dê a volta e vire
        ruído — o que soa como estalo, e num áudio de diligência seria
        confundido com adulteração.
        """
        import numpy as np

        limitado = np.clip(quadros, -1.0, 1.0)
        return (limitado * 32767).astype("<i2").tobytes()
