"""Prova da captura de tela na Extração Registrada.

O botão de captura acrescenta um ato à linha do tempo, com o resumo da
imagem — de modo que o termo o registra ao lado dos demais passos da
diligência, com hora e SHA-256.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from temis.tools import extracao_core as ec           # noqa: E402


class ACapturaEntraNaLinhaDoTempo(unittest.TestCase):

    def test_captura_e_um_tipo_de_evento_rotulado(self):
        self.assertTrue(hasattr(ec, "CAPTURA"))
        self.assertIn(ec.CAPTURA, ec.ROTULO_EVENTO)

    def test_o_ato_de_captura_entra_com_o_resumo(self):
        s = ec.Sessao()
        s.comecar("x")
        s.anotar(ec.CAPTURA, "Captura de tela: captura-001.png",
                 detalhe="SHA-256 " + "a" * 64)
        ato = s.eventos[-1]
        self.assertEqual(ato.rotulo, "Captura de tela")
        self.assertIn("a" * 64, ato.detalhe)
        self.assertEqual(s.quantos(ec.CAPTURA), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
