# Componentes de terceiros

O Sistema Têmis distribui, no seu instalador, software de terceiros. Este
arquivo identifica cada componente, a licença sob a qual ele é distribuído
e onde obter o seu código-fonte — exigência das licenças copyleft e
condição para que a distribuição seja regular.

## Por que o projeto é AGPL-3.0

A licença do conjunto não é uma escolha estética: é a mais restritiva
entre as dos componentes distribuídos. O PyQt6 é GPL-3.0, o PyMuPDF é
AGPL-3.0 e o FFmpeg empacotado foi compilado com `--enable-gpl
--enable-version3`. Distribuir o instalador sob licença permissiva
declararia a quem recebe uma condição que não corresponde à realidade.

## Bibliotecas

| Componente | Licença | Origem |
|---|---|---|
| **PyQt6** | GPL-3.0-only | [riverbankcomputing.com/software/pyqt](https://www.riverbankcomputing.com/software/pyqt/) |
| **PyQt6-WebEngine** | GPL-3.0-only | idem |
| **Qt 6** (via PyQt6-Qt6) | LGPL-3.0 | [qt.io](https://www.qt.io/) · [código-fonte](https://download.qt.io/official_releases/qt/) |
| **PyMuPDF** | AGPL-3.0 | [github.com/pymupdf/PyMuPDF](https://github.com/pymupdf/PyMuPDF) |
| **Pillow** | MIT-CMU | [github.com/python-pillow/Pillow](https://github.com/python-pillow/Pillow) |
| **faster-whisper** | MIT | [github.com/SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) |
| **CTranslate2** | MIT | [github.com/OpenNMT/CTranslate2](https://github.com/OpenNMT/CTranslate2) |
| **sherpa-onnx** | Apache-2.0 | [github.com/k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) |
| **ONNX Runtime** | MIT | [github.com/microsoft/onnxruntime](https://github.com/microsoft/onnxruntime) |
| **NumPy** | BSD-3-Clause | [numpy.org](https://numpy.org/) |
| **PyAV** | BSD-3-Clause | [github.com/PyAV-Org/PyAV](https://github.com/PyAV-Org/PyAV) |
| **huggingface-hub** | Apache-2.0 | [github.com/huggingface/huggingface_hub](https://github.com/huggingface/huggingface_hub) |
| **tokenizers** | Apache-2.0 | [github.com/huggingface/tokenizers](https://github.com/huggingface/tokenizers) |
| **Python** | PSF-2.0 | [python.org](https://www.python.org/) |
| **PyWinRT** (`winrt-runtime` e módulos `winrt-Windows.*`) | MIT | [github.com/pywinrt/pywinrt](https://github.com/pywinrt/pywinrt) |
| **SQLite** (via módulo `sqlite3` do Python) | domínio público | [sqlite.org](https://www.sqlite.org/copyright.html) |

## Componentes do sistema operacional

O reconhecimento óptico de caracteres da Varredura e do PDF Pesquisável é
feito pelo motor `Windows.Media.Ocr`, que faz parte do próprio Windows.
Nada dele é redistribuído no instalador: o programa apenas chama a
interface de programação do sistema, pelos módulos PyWinRT acima, na
máquina em que já há licença de Windows. A captura de tela da Gravação de
Tela usa a mesma via — a interface gráfica do próprio sistema.

## FFmpeg

O instalador acompanha `ffmpeg.exe` e `ffprobe.exe`, usados pela Edição de
Vídeo e pela Degravação. São binários **não modificados** da compilação
pública `ffmpeg-9.0.1-essentials_build` distribuída por gyan.dev, feita com
`--enable-gpl --enable-version3` — portanto sob **GPL-3.0**.

- Projeto: [ffmpeg.org](https://ffmpeg.org/)
- Código-fonte da versão empacotada: [github.com/FFmpeg/FFmpeg](https://github.com/FFmpeg/FFmpeg) (etiqueta `n9.0.1`)
- Compilação utilizada: [github.com/GyanD/codexffmpeg/releases](https://github.com/GyanD/codexffmpeg/releases)

Nos termos da GPL, quem recebeu o instalador tem direito ao código-fonte
correspondente. Ele está nos endereços acima; na impossibilidade de
obtê-lo ali, abra uma questão no repositório do Sistema Têmis e ele será
fornecido.

## scrcpy e Android Debug Bridge

O instalador acompanha o **scrcpy** e o **adb**, usados pelo Espelhamento
de Celular. São os binários não modificados da versão pública
`scrcpy-win64-v4.1`, distribuída pelo próprio projeto.

| Componente | Licença | Origem |
|---|---|---|
| **scrcpy** | Apache-2.0 | [github.com/Genymobile/scrcpy](https://github.com/Genymobile/scrcpy) |
| **adb** (Android Debug Bridge) | Apache-2.0 | [Android Open Source Project](https://android.googlesource.com/platform/packages/modules/adb/) |
| **FFmpeg** (bibliotecas que acompanham o scrcpy) | LGPL-2.1+ | [ffmpeg.org](https://ffmpeg.org/) |
| **SDL 3** | Zlib | [libsdl.org](https://www.libsdl.org/) |
| **libusb** | LGPL-2.1+ | [libusb.info](https://libusb.info/) |

Sobre a redistribuição do `adb`: a licença do SDK do Android veda
redistribuir o conjunto (§3.4), mas ressalva expressamente que os
componentes sob licença de código aberto são regidos apenas pela própria
licença (§3.5). O `adb` é do AOSP, sob Apache-2.0. O Debian o empacota
como `android-platform-tools` na área **main**, que exige licença livre e
redistribuível, e o próprio scrcpy o distribui em suas versões oficiais.

As bibliotecas do FFmpeg que acompanham o scrcpy **não** são as mesmas
que o Sistema Têmis usa na Edição de Vídeo: aquelas foram compiladas sem
`--enable-gpl` — conferido na linha de configuração embutida no binário —
e portanto são LGPL.

## Modelos de reconhecimento de fala

Não acompanham o instalador — são baixados na primeira utilização da
Degravação e ficam em `%LOCALAPPDATA%\SistemaTemis\modelos`.

| Modelo | Licença | Origem |
|---|---|---|
| **Whisper** (convertido para CTranslate2) | MIT | [huggingface.co/Systran](https://huggingface.co/Systran) |
| **pyannote segmentation 3.0** (ONNX) | MIT | [github.com/k2-fsa/sherpa-onnx/releases](https://github.com/k2-fsa/sherpa-onnx/releases) |
| **NeMo TitaNet Small** (ONNX) | CC-BY-4.0 | idem |

## Ícones e identidade visual

Todos os ícones do programa são desenhados em código, com o QPainter, em
`temis/icons.py`. Não há arquivo de imagem de terceiros no projeto.
