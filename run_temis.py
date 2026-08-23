"""
Ponto de entrada do executável empacotado.

O PyInstaller roda o arquivo de entrada como um script solto, sem pacote
pai — então apontá-lo direto para `temis/__main__.py` quebra todos os
imports relativos ("attempted relative import with no known parent
package"). Este arquivo fica fora do pacote e o importa de forma
absoluta, preservando `python -m temis` para execução a partir do código.
"""

import sys

from temis.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
