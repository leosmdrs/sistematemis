"""
Gera build/temis.ico a partir da marca vetorial.

O ícone não é um arquivo versionado à parte: ele é derivado do mesmo
código que desenha a balança na interface, então marca e ícone nunca
saem de sincronia.
"""

import io
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtWidgets import QApplication          # noqa: E402
from PIL import Image                             # noqa: E402

from temis.icons import temis_pixmap              # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)
OUT = os.path.join(ROOT, "build", "temis.ico")

# Mantido no escopo do módulo: se o QApplication for coletado antes dos
# QPixmap criados a partir dele, o interpretador quebra com segfault.
_app = QApplication(sys.argv)


def main() -> int:
    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        for s in SIZES:
            path = os.path.join(tmp, f"{s}.png")
            temis_pixmap(s).save(path, "PNG")
            with open(path, "rb") as fh:
                frames.append(Image.open(io.BytesIO(fh.read())).convert("RGBA"))

    frames[-1].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"gerado: {OUT}  ({', '.join(f'{s}x{s}' for s in SIZES)})")
    return 0


if __name__ == "__main__":
    code = main()
    # Encerra sem desmontar o Qt, evitando o segfault de ordem de destruição.
    sys.stdout.flush()
    os._exit(code)
