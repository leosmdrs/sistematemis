"""Provas do Gerador de Hash e Metadados: conferência e localização.

Duas afirmações graves saíam por engano. A conferência de integridade
dizia NÃO CONFERE quando o resumo declarado vinha com rótulo — "SHA-256:
ab12…" —, porque as letras do rótulo entravam na conta. E a localização
de uma fotografia ia para o termo sem validação: latitude impossível, e
hemisfério presumido quando o arquivo não o informava.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication               # noqa: E402

from temis.tools import metadados_core as mc           # noqa: E402

_app = QApplication.instance() or QApplication([])

RESUMO = "ab12" * 16


class OResumoDeclaradoComRotuloConfere(unittest.TestCase):

    def arquivo(self, declarado):
        return mc.Arquivo(caminho="x.pdf", sha256=RESUMO, declarado=declarado)

    def test_as_grafias_usuais_conferem(self):
        em_grupos = " ".join(RESUMO[i:i + 4] for i in range(0, 64, 4))
        for declarado in (RESUMO, RESUMO.upper(), f"SHA-256: {RESUMO}",
                          f"Hash: {RESUMO}", f"sha256={RESUMO}",
                          f"SHA-256: {em_grupos}",
                          f"Resumo SHA-256:\n{RESUMO[:32]}\n{RESUMO[32:]}",
                          f"{RESUMO}  arquivo.pdf"):
            with self.subTest(declarado[:24]):
                self.assertIs(self.arquivo(declarado).confere, True)

    def test_resumo_diferente_continua_nao_conferindo(self):
        outro = "cd34" * 16
        self.assertIs(self.arquivo(f"SHA-256: {outro}").confere, False)

    def test_resumo_incompleto_nao_e_divergencia(self):
        a = self.arquivo(f"SHA-256: {RESUMO[:40]}")
        self.assertIsNone(a.confere)
        self.assertTrue(a.declarado_ilegivel)
        celula = mc._celula_conferencia(a)
        self.assertNotIn("NÃO CONFERE", celula)
        self.assertIn("não conferido", celula)


class ALocalizacaoEValidada(unittest.TestCase):

    def test_coordenada_valida_e_convertida(self):
        self.assertAlmostEqual(mc._graus((15, 47, 38.4), "S", 90.0),
                               -15.794, places=3)

    def test_valores_impossiveis_sao_recusados(self):
        for valor, limite in (((123, 0, 0), 90.0), ((200, 0, 0), 180.0),
                              ((10, 75, 0), 90.0), ((10, 0, 99), 90.0),
                              ((float("nan"), 0, 0), 90.0),
                              ((float("inf"), 0, 0), 180.0),
                              ((-5, 0, 0), 90.0), ("abc", 90.0)):
            with self.subTest(valor=valor):
                self.assertIsNone(mc._graus(valor, "N", limite))


class OTermoNaoExpoeAPastaDeOrigem(unittest.TestCase):

    def test_o_caminho_da_estacao_nao_vira_campo(self):
        import tempfile
        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / "doc.txt"
            alvo.write_text("x", encoding="utf-8")
            rotulos = [c.rotulo for c in mc._do_sistema(alvo)]
            valores = " ".join(c.valor for c in mc._do_sistema(alvo))
        self.assertNotIn("Pasta", rotulos)
        self.assertNotIn(pasta, valores)


if __name__ == "__main__":
    unittest.main(verbosity=2)
