"""
Degravação de áudio e vídeo.

Sem dependência de interface, para poder ser testado isolado.

O reconhecimento roda **na máquina**, pelo Whisper. Nenhum trecho de áudio
é enviado a serviço nenhum — o que vem de fora é apenas o modelo, uma vez,
e daí em diante a ferramenta funciona sem rede.

Duas escolhas que valem explicação:

**O modelo não é embutido no instalador.** O menor pesa 75 MB e o
recomendado, 464 MB; embutir levaria o programa a mais de 700 MB para uma
ferramenta que nem todo servidor vai usar. Ele é baixado na primeira vez e
fica em cache.

**A separação de locutores é feita por outro modelo.** O Whisper
transcreve, mas não distingue vozes — não há informação de quem fala na
saída dele. Quem separa é um par de modelos de diarização, pequeno
(45 MB) e rodando sobre o mesmo onnxruntime que já acompanha o programa.

**O resultado da separação é um ponto de partida, não um veredito.** Ela
devolve "Locutor 1", "Locutor 2" na ordem em que aparecem, e cabe ao
encarregado dar nome a cada um — uma vez, valendo para todas as falas
daquela voz. Em gravação de oitiva, com microfone único e falas
sobrepostas, a separação erra; por isso cada trecho continua editável, e
o termo não afirma que a atribuição é automática.
"""

from __future__ import annotations

import re
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path

from .video_core import _SEM_JANELA, ffmpeg_path

#: Taxa e formato que o Whisper espera.
TAXA = 16000


# ─────────────────────────────────────────
#  MODELOS
# ─────────────────────────────────────────

@dataclass(frozen=True)
class Modelo:
    chave: str
    rotulo: str
    tamanho_mb: int
    nota: str


#: O `small` é o padrão por ser o menor que erra pouco em português. Os
#: menores trocam palavras a ponto de dar mais trabalho revisar do que
#: degravar à mão; os maiores custam tempo de máquina que não compensa.
MODELOS: tuple[Modelo, ...] = (
    Modelo("tiny", "Rápido", 75,
           "Erra bastante. Serve para localizar um trecho, não para o termo."),
    Modelo("base", "Intermediário", 145,
           "Melhor que o rápido, ainda com erros frequentes."),
    Modelo("small", "Recomendado", 464,
           "Boa precisão em português, a cerca de 3× o tempo real."),
    Modelo("medium", "Máxima precisão", 1530,
           "O melhor resultado, porém lento: perto do tempo real."),
)

MODELO_PADRAO = "small"


def modelo(chave: str) -> Modelo:
    return next((m for m in MODELOS if m.chave == chave), MODELOS[2])


def pasta_modelos() -> Path:
    import os
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    raiz = Path(base) if base else Path.home() / ".local" / "share"
    destino = raiz / "SistemaTemis" / "modelos"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def pasta_do_modelo(chave: str) -> Path:
    return pasta_modelos() / f"faster-whisper-{chave}"


def baixado(chave: str) -> bool:
    """O modelo já está em disco e utilizável?"""
    pasta = pasta_do_modelo(chave)
    return (pasta / "model.bin").is_file() and (pasta / "config.json").is_file()


def tamanho_em_disco(chave: str) -> int:
    pasta = pasta_do_modelo(chave)
    if not pasta.exists():
        return 0
    return sum(f.stat().st_size for f in pasta.rglob("*") if f.is_file())


def baixar_modelo(chave: str) -> Path:
    """Traz o modelo do repositório oficial para o cache local.

    Só entra dado na máquina; nada sai. Quem chama deve rodar isto fora da
    interface — são centenas de megabytes.
    """
    from huggingface_hub import snapshot_download

    destino = pasta_do_modelo(chave)
    snapshot_download(
        repo_id=f"Systran/faster-whisper-{chave}",
        local_dir=str(destino),
        allow_patterns=["*.bin", "*.json", "*.txt"],
    )
    return destino


#: Modelos da separação de locutores. Vêm dos lançamentos do sherpa-onnx,
#: sem exigir cadastro nem token — o que importa para instalar em estação
#: de órgão público.
BASE_DIARIZACAO = "https://github.com/k2-fsa/sherpa-onnx/releases/download"

#: (nome do arquivo local, endereço, MB). O modelo de voz é o titanet:
#: medindo com áudio de duas vozes e gabarito conhecido, ele separou as
#: falas por completo, enquanto o campplus — o primeiro que testei —
#: juntava as duas num locutor só. A diferença entre os dois modelos foi
#: maior que a diferença entre todos os ajustes de limiar.
ARQUIVOS_DIARIZACAO = (
    ("segmentacao.onnx",
     f"{BASE_DIARIZACAO}/speaker-segmentation-models/"
     "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2", 7),
    ("voz.onnx",
     f"{BASE_DIARIZACAO}/speaker-recongition-models/"
     "nemo_en_titanet_small.onnx", 39),
)

DIARIZACAO_MB = sum(a[2] for a in ARQUIVOS_DIARIZACAO)

#: Acima deste limiar duas falas são tidas como da mesma pessoa. Medido:
#: 0,7 e 0,8 acertaram por completo o áudio de teste; 0,4 e 0,6 partiram
#: uma das vozes em duas.
LIMIAR_LOCUTOR = 0.75


def pasta_diarizacao() -> Path:
    destino = pasta_modelos() / "diarizacao"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def diarizacao_baixada() -> bool:
    pasta = pasta_diarizacao()
    return all((pasta / nome).is_file() for nome, _u, _m in ARQUIVOS_DIARIZACAO)


def baixar_diarizacao(progresso=None) -> Path:
    """Traz os dois modelos da separação de locutores."""
    import tarfile
    import tempfile
    import urllib.request

    pasta = pasta_diarizacao()
    for i, (nome, url, _mb) in enumerate(ARQUIVOS_DIARIZACAO, 1):
        alvo = pasta / nome
        if alvo.is_file():
            continue
        if progresso is not None:
            progresso(i, len(ARQUIVOS_DIARIZACAO))
        pedido = urllib.request.Request(url, headers={"User-Agent": "Temis"})
        with urllib.request.urlopen(pedido, timeout=180) as r:
            dados = r.read()
        if url.endswith(".tar.bz2"):
            # O modelo de segmentação vem empacotado; interessa só o .onnx.
            with tempfile.TemporaryDirectory() as tmp:
                pacote = Path(tmp) / "pacote.tar.bz2"
                pacote.write_bytes(dados)
                with tarfile.open(pacote) as t:
                    t.extractall(tmp)
                achado = next((x for x in Path(tmp).rglob("model.onnx")), None)
                if achado is None:
                    raise ErroTranscricao(
                        "O pacote de segmentação veio sem o modelo esperado.")
                alvo.write_bytes(achado.read_bytes())
        else:
            alvo.write_bytes(dados)
    return pasta


# ─────────────────────────────────────────
#  ÁUDIO
# ─────────────────────────────────────────

class ErroTranscricao(Exception):
    """Falha ao preparar ou reconhecer o áudio."""


def extrair_audio(midia: str | Path, destino: str | Path) -> Path:
    """Converte qualquer mídia em WAV mono de 16 kHz.

    Usa o FFmpeg que já acompanha o sistema — o mesmo da Edição de Vídeo —,
    o que dispensa uma segunda biblioteca de decodificação e faz a
    ferramenta aceitar tudo o que o FFmpeg aceita.
    """
    exe = ffmpeg_path()
    if exe is None:
        raise ErroTranscricao(
            "FFmpeg não encontrado nesta instalação; sem ele não há como "
            "ler o áudio.")
    destino = Path(destino)
    resultado = subprocess.run(
        [str(exe), "-y", "-i", str(midia), "-vn", "-ac", "1",
         "-ar", str(TAXA), "-c:a", "pcm_s16le", "-f", "wav", str(destino)],
        capture_output=True, text=True, creationflags=_SEM_JANELA)
    if resultado.returncode != 0 or not destino.is_file():
        cauda = (resultado.stderr or "").strip().splitlines()[-1:] or [""]
        raise ErroTranscricao(f"Não foi possível extrair o áudio: {cauda[0]}")
    return destino


def carregar_audio(wav: str | Path):
    """Lê o WAV como vetor de amostras, que é o que o modelo recebe."""
    import numpy as np

    with wave.open(str(wav), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ErroTranscricao("O áudio precisa ser mono de 16 bits.")
        bruto = w.readframes(w.getnframes())
    return np.frombuffer(bruto, dtype=np.int16).astype(np.float32) / 32768.0


def duracao(wav: str | Path) -> float:
    with wave.open(str(wav), "rb") as w:
        return w.getnframes() / float(w.getframerate() or TAXA)


# ─────────────────────────────────────────
#  TRECHOS
# ─────────────────────────────────────────

def hms(segundos: float) -> str:
    s = max(0, int(segundos))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


@dataclass
class Trecho:
    inicio: float = 0.0
    fim: float = 0.0
    texto: str = ""
    #: Rótulo que aparece no termo. Vazio significa "não atribuído".
    locutor: str = ""
    #: Voz a que a separação atribuiu este trecho. -1 quando não houve
    #: separação. É o que permite renomear todas as falas de uma pessoa de
    #: uma vez só.
    voz: int = -1
    #: (início, fim, palavra) de cada palavra reconhecida. Serve para
    #: recortar o trecho na troca de locutor, e é descartada depois.
    palavras: list = field(default_factory=list)

    @property
    def marca(self) -> str:
        return hms(self.inicio)


#: Sugestões de rótulo, na ordem em que costumam aparecer numa oitiva.
LOCUTORES = ("Encarregado", "Declarante", "Testemunha", "Investigado",
             "Advogado", "Intérprete")


@dataclass
class Degravacao:
    """O resultado do reconhecimento de uma mídia."""

    origem: str = ""
    sha256: str = ""
    duracao: float = 0.0
    modelo: str = MODELO_PADRAO
    idioma: str = "pt"
    trechos: list[Trecho] = field(default_factory=list)
    #: Nome dado a cada voz separada: {0: "Encarregado", 1: "Declarante"}.
    nomes: dict = field(default_factory=dict)
    separou_vozes: bool = False

    @property
    def nome(self) -> str:
        return Path(self.origem).name

    @property
    def texto_corrido(self) -> str:
        return " ".join(t.texto.strip() for t in self.trechos if t.texto.strip())

    @property
    def palavras(self) -> int:
        return len(re.findall(r"\w+", self.texto_corrido))

    @property
    def rotulados(self) -> int:
        return sum(1 for t in self.trechos if t.locutor)

    @property
    def vozes(self) -> list[int]:
        """Vozes distintas encontradas, na ordem em que apareceram."""
        vistas = []
        for t in self.trechos:
            if t.voz >= 0 and t.voz not in vistas:
                vistas.append(t.voz)
        return vistas

    def nome_da_voz(self, voz: int) -> str:
        """Nome da voz, numerada pela ordem em que aparece na gravação.

        O agrupamento devolve identificadores arbitrários — a primeira
        pessoa a falar pode cair no grupo 2. Chamá-la de "Locutor 2" no
        termo confundiria quem lê, então a numeração segue a cronologia.
        """
        nome = self.nomes.get(voz)
        if nome:
            return nome
        vistas = self.vozes
        return f"Locutor {vistas.index(voz) + 1}" if voz in vistas else "—"

    def renomear(self, voz: int, nome: str):
        """Dá nome a uma voz — e a todas as falas dela de uma vez."""
        nome = nome.strip()
        if nome:
            self.nomes[voz] = nome
        else:
            self.nomes.pop(voz, None)
        for t in self.trechos:
            if t.voz == voz:
                t.locutor = self.nome_da_voz(voz) if nome else ""


def transcrever(audio, modelo_chave: str = MODELO_PADRAO, idioma: str = "pt",
                progresso=None, cancelado=None) -> list[Trecho]:
    """Reconhece a fala. `progresso(segundos_prontos, total)`."""
    from faster_whisper import WhisperModel

    total = len(audio) / TAXA
    if not baixado(modelo_chave):
        # Sem esta conferência, a biblioteca interpreta o caminho ausente
        # como nome de modelo e devolve um erro incompreensível.
        raise ErroTranscricao(
            f"O modelo “{modelo(modelo_chave).rotulo}” ainda não está nesta "
            "máquina. Baixe-o antes de transcrever.")
    try:
        wm = WhisperModel(str(pasta_do_modelo(modelo_chave)), device="cpu",
                          compute_type="int8", local_files_only=True)
    except Exception as e:                              # noqa: BLE001
        raise ErroTranscricao(f"Não foi possível carregar o modelo: {e}")

    trechos: list[Trecho] = []
    try:
        # `word_timestamps` custa algum tempo a mais, mas é o que permite
        # cortar o trecho exatamente onde a voz muda. Sem isso, uma fala
        # longa do Whisper atravessa dois interlocutores e acaba atribuída
        # inteira a um só — erro que passaria despercebido no termo.
        segmentos, _info = wm.transcribe(
            audio, language=idioma or None, beam_size=5, vad_filter=True,
            word_timestamps=True)
        for s in segmentos:
            if cancelado is not None and cancelado():
                break
            texto = (s.text or "").strip()
            if texto:
                trechos.append(Trecho(
                    inicio=s.start, fim=s.end, texto=texto,
                    palavras=[(float(w.start), float(w.end), w.word)
                              for w in (s.words or [])]))
            if progresso is not None:
                progresso(s.end, total)
    except Exception as e:                              # noqa: BLE001
        raise ErroTranscricao(f"Falha ao transcrever: {e}")
    return trechos


def separar_vozes(audio, quantas: int = 0, progresso=None) -> list[tuple]:
    """Divide o áudio por quem fala. Devolve (voz, início, fim).

    `quantas` maior que zero fixa o número de pessoas; zero deixa o modelo
    decidir. Numa oitiva o encarregado costuma saber quantas pessoas
    falaram, e informar melhora bastante o resultado.
    """
    import sherpa_onnx

    if not diarizacao_baixada():
        raise ErroTranscricao(
            "Os modelos de separação de locutores ainda não estão nesta "
            "máquina.")

    pasta = pasta_diarizacao()
    cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(pasta / "segmentacao.onnx"))),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(pasta / "voz.onnx")),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=int(quantas) if quantas and quantas > 1 else -1,
            threshold=LIMIAR_LOCUTOR),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not cfg.validate():
        raise ErroTranscricao("Configuração inválida da separação de vozes.")

    try:
        sd = sherpa_onnx.OfflineSpeakerDiarization(cfg)
        resultado = sd.process(
            audio,
            callback=(lambda feito, total, _a=None: progresso(feito, total))
            if progresso is not None else None,
        ).sort_by_start_time()
    except Exception as e:                              # noqa: BLE001
        raise ErroTranscricao(f"Falha ao separar as vozes: {e}")
    return [(int(x.speaker), float(x.start), float(x.end)) for x in resultado]


def _voz_em(instante: float, falas: list[tuple]) -> int:
    """Quem está falando neste instante — ou a fala mais próxima."""
    for voz, ini, fim in falas:
        if ini <= instante <= fim:
            return voz
    melhor, menor = -1, float("inf")
    for voz, ini, fim in falas:
        dist = ini - instante if instante < ini else instante - fim
        if dist < menor:
            melhor, menor = voz, dist
    return melhor


#: Abaixo disto, um pedaço de fala isolado não vira trecho próprio: é
#: quase sempre uma palavra que a separação atribuiu errado no meio da
#: frase de outra pessoa, e recortar ali picotaria o texto sem ganho.
MINIMO_RECORTE = 3


def atribuir_vozes(trechos: list[Trecho], falas: list[tuple]) -> list[Trecho]:
    """Liga cada fala a quem a disse, recortando na troca de voz.

    Devolve uma lista **nova**: os cortes do Whisper não respeitam a troca
    de interlocutor, e um trecho longo costuma atravessar duas pessoas.
    Cada palavra é atribuída pela sua marca de tempo, e o trecho é partido
    onde a voz muda — é isso que faz a degravação seguir a cronologia do
    diálogo, e não a da segmentação do reconhecimento.
    """
    if not falas:
        return list(trechos)

    saida: list[Trecho] = []
    for t in trechos:
        if not t.palavras:
            # Sem marcação de palavra, resta atribuir pelo maior tempo em
            # comum — o comportamento antigo, aqui como resguardo.
            melhor, maior = -1, 0.0
            for voz, ini, fim in falas:
                sobra = min(t.fim, fim) - max(t.inicio, ini)
                if sobra > maior:
                    melhor, maior = voz, sobra
            t.voz = melhor
            saida.append(t)
            continue

        marcadas = [(ini, fim, texto, _voz_em((ini + fim) / 2, falas))
                    for ini, fim, texto in t.palavras]

        # Junta as palavras em blocos de mesma voz, absorvendo os blocos
        # curtos demais no vizinho anterior.
        blocos: list[list] = []
        for ini, fim, texto, voz in marcadas:
            if blocos and blocos[-1][0] == voz:
                blocos[-1][1].append((ini, fim, texto))
            else:
                blocos.append([voz, [(ini, fim, texto)]])

        limpos: list[list] = []
        for voz, palavras in blocos:
            if (limpos and len(palavras) < MINIMO_RECORTE
                    and len(blocos) > 1):
                limpos[-1][1].extend(palavras)
            else:
                limpos.append([voz, list(palavras)])

        for voz, palavras in limpos:
            texto = "".join(x[2] for x in palavras).strip()
            if not texto:
                continue
            saida.append(Trecho(
                inicio=palavras[0][0], fim=palavras[-1][1],
                texto=texto, voz=voz))
    return saida


# ─────────────────────────────────────────
#  TERMO DE DEGRAVAÇÃO
# ─────────────────────────────────────────

INK = "#16233A"
CINZA = "#5B6B82"


@dataclass
class Declarante:
    nome: str = ""
    matricula: str = ""
    lotacao: str = ""
    cargo: str = "Policial Rodoviário Federal"


@dataclass
class Procedimento:
    tipo: str = "IPS"
    numero: str = ""


def build_html(d: Degravacao, decl: Declarante | None = None,
               proc: Procedimento | None = None,
               com_marcas: bool = True) -> str:
    """Termo de degravação em HTML, para exibir e exportar."""
    import html as _html

    e = _html.escape
    decl = decl or Declarante()
    proc = proc or Procedimento()
    m = modelo(d.modelo)

    quem = (f"eu, PRF {e(decl.nome)}, matrícula {e(decl.matricula)}, "
            f"lotado(a) no(a) {e(decl.lotacao)}, " if decl.nome else "")
    vinculo = (f"para instruir os autos {'da' if proc.tipo == 'IPS' else 'do'} "
               f"{e(proc.tipo)} nº {e(proc.numero)}, " if proc.numero else "")
    abertura = (
        f"{quem.capitalize() if not vinculo else quem}{vinculo}procedi à "
        f"degravação do arquivo <b>{e(d.nome)}</b>, com duração de "
        f"{hms(d.duracao)}, cujo teor segue transcrito abaixo."
    ) if quem or vinculo else (
        f"Segue a degravação do arquivo <b>{e(d.nome)}</b>, com duração de "
        f"{hms(d.duracao)}.")

    # Falas seguidas do mesmo locutor viram um parágrafo só: o termo fica
    # legível como diálogo, e não como lista de recortes de dois segundos.
    blocos = []
    atual = None
    for t in d.trechos:
        if atual is not None and t.locutor == atual["locutor"]:
            atual["textos"].append(t.texto.strip())
            atual["fim"] = t.fim
        else:
            atual = {"locutor": t.locutor, "inicio": t.inicio, "fim": t.fim,
                     "textos": [t.texto.strip()]}
            blocos.append(atual)

    linhas = []
    for b in blocos:
        marca = (f'<font color="{CINZA}" face="Courier New" size="1">'
                 f"[{hms(b['inicio'])}]&nbsp;&nbsp;</font>"
                 if com_marcas else "")
        quem_fala = (f'<b><font color="{INK}">{e(b["locutor"])}:</font></b> '
                     if b["locutor"] else "")
        linhas.append(
            f'<p align="justify" style="font-size:11pt; line-height:160%; '
            f'margin:0 0 8pt 0;">{marca}{quem_fala}'
            f'<font color="{INK}">{e(" ".join(b["textos"]))}</font></p>')

    identificacao = "".join(
        "<tr>"
        f'<td width="30%"><font color="{CINZA}">{e(rot)}</font></td>'
        f'<td><font color="{INK}"{" face=\'Courier New\' size=\'1\'" if mono else ""}>'
        f"{e(val) or '—'}</font></td></tr>"
        for rot, val, mono in (
            ("Arquivo", d.nome, False),
            ("Duração", hms(d.duracao), False),
            ("Resumo do arquivo (SHA-256)", d.sha256, True),
            ("Reconhecimento", f"Whisper {d.modelo} — {m.rotulo}", False),
            ("Idioma", {"pt": "português"}.get(d.idioma, d.idioma), False),
        ))

    assinatura = ""
    if decl.nome:
        v = " · ".join(x for x in (
            f"matrícula {e(decl.matricula)}" if decl.matricula else "",
            e(decl.lotacao) if decl.lotacao else "") if x)
        assinatura = f"""
<div align="center" style="margin-top:40px;">
  ______________________________________<br/>
  <b><font color="{INK}">{e(decl.nome)}</font></b><br/>
  <font color="{INK}" size="2">{e(decl.cargo)}</font>
  {f'<br/><font color="{CINZA}" size="1">{v}</font>' if v else ''}
</div>"""

    return f"""
<html><body style="font-family:'Segoe UI',Arial,sans-serif; color:{INK};">
<div align="center" style="margin-bottom:16px;">
  <b style="font-size:15pt; letter-spacing:1px;">POLÍCIA RODOVIÁRIA FEDERAL</b><br/>
  <span style="font-size:11pt;">Termo de Degravação de Mídia</span>
</div>
<hr/>
<p align="justify" style="font-size:11pt; line-height:160%;">{abertura}</p>
<table width="100%" cellspacing="0" cellpadding="4" border="1"
       style="border-collapse:collapse; font-size:9pt;">{identificacao}</table>

<p style="margin-top:18px; margin-bottom:6px;"><b>Transcrição</b></p>
{''.join(linhas) or f'<p><font color="{CINZA}">Sem trechos transcritos.</font></p>'}

<p align="justify" style="font-size:10pt; line-height:150%; margin-top:18px;">
A degravação foi produzida por reconhecimento automático de fala, executado
integralmente nesta máquina, sem envio do áudio a serviço externo. As
marcas de tempo remetem ao arquivo original, cujo resumo SHA-256 consta
acima.{
" A separação entre os interlocutores foi obtida por análise automática "
"das vozes e <b>conferida pelo signatário</b>, a quem coube nomear cada "
"um deles." if d.separou_vozes else ""}
<b>O texto foi conferido e corrigido pelo signatário</b>, a quem cabe a
fidelidade da transcrição; o reconhecimento automático é meio de trabalho,
não fonte de fé.
</p>
<p align="justify" style="font-size:11pt; margin-top:14px;">
Sem mais a relatar, encerro o presente termo.
</p>
{assinatura}
</body></html>
"""
