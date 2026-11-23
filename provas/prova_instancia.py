"""Provas da execução única por usuário.

Duas execuções ao mesmo tempo dividiam o registro da sessão e o arquivo
de casos do Quadro, e uma apagava o trabalho da outra. A segunda agora
avisa e sai.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication               # noqa: E402

from temis.__main__ import travar_instancia            # noqa: E402

_app = QApplication.instance() or QApplication([])

OUTRO_PROCESSO = r"""
import sys
sys.path.insert(0, {raiz!r})
from PyQt6.QtCore import QCoreApplication
app = QCoreApplication(["prova"])
from temis.__main__ import travar_instancia
trava = travar_instancia({pasta!r})
print("OBTEVE" if trava else ("OCUPADA" if trava is None else "SEM-TRAVA"))
"""


class UmaExecucaoPorUsuario(unittest.TestCase):

    def outro(self, pasta):
        r = subprocess.run(
            [sys.executable, "-c",
             OUTRO_PROCESSO.format(raiz=str(RAIZ), pasta=pasta)],
            capture_output=True, text=True, timeout=60,
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
        return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else \
            r.stderr[-300:]

    def test_a_segunda_execucao_nao_obtem_a_trava(self):
        with tempfile.TemporaryDirectory() as pasta:
            trava = travar_instancia(pasta)
            self.assertTrue(trava)
            self.assertEqual(self.outro(pasta), "OCUPADA")
            trava.unlock()

    def test_fechada_a_primeira_a_seguinte_abre(self):
        with tempfile.TemporaryDirectory() as pasta:
            trava = travar_instancia(pasta)
            trava.unlock()
            self.assertEqual(self.outro(pasta), "OBTEVE")

    def test_execucao_que_caiu_nao_prende_a_seguinte(self):
        with tempfile.TemporaryDirectory() as pasta:
            # O processo abaixo obtém a trava e termina sem soltá-la.
            self.assertEqual(self.outro(pasta), "OBTEVE")
            trava = travar_instancia(pasta)
            self.assertTrue(trava)
            trava.unlock()

    def test_sem_onde_gravar_o_programa_abre_assim_mesmo(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "nao-e-pasta"
            arquivo.write_text("x", encoding="utf-8")
            self.assertIs(travar_instancia(str(arquivo)), False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
