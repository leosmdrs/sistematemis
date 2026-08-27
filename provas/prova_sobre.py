"""Prova do que o sistema promete ao usuário sobre a rede.

O diálogo **Sobre** é onde o sistema declara o que sai da máquina. A
declaração ficou errada por duas versões: dizia "em apenas duas
situações" quando eram três, falava no singular de duas ferramentas, e
chamava de "página oficial externa" o endereço que quem opera é que
indica. Nada disso quebrava o programa — só desmentia a promessa.

O portal e o Sobre partem agora da mesma `ferramentas_online()`. Estas
provas obrigam o texto a acompanhar o registro.
"""

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel      # noqa: E402

from temis.shell import SobreDialog, ferramentas_online   # noqa: E402
from temis.tools import REGISTRY                      # noqa: E402


def sem_marcacao(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


class OSobreDizAVerdadeSobreARede(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        dialogo = SobreDialog()
        textos = [lbl.text() for lbl in dialogo.findChildren(QLabel)
                  if "acessa a rede" in lbl.text()]
        assert textos, "o Sobre não fala mais de acesso à rede"
        cls.html = textos[0]
        cls.texto = sem_marcacao(cls.html)

    def test_nomeia_toda_ferramenta_que_sai_a_rede(self):
        for nome in ferramentas_online():
            with self.subTest(nome):
                self.assertIn(nome, self.texto)

    def test_nao_nomeia_ferramenta_que_nao_sai(self):
        # Nomear quem não sai gasta a marca de quem sai.
        online = set(ferramentas_online())
        for meta, _ in REGISTRY:
            if meta.name in online:
                continue
            with self.subTest(meta.name):
                self.assertNotIn(meta.name, self.texto)

    def test_concorda_em_numero_com_quantas_saem(self):
        quantas = len(ferramentas_online())
        if quantas == 0:
            self.skipTest("nenhuma ferramenta acessa a rede")
        singular = quantas == 1
        self.assertEqual("a ferramenta " in self.texto, singular)
        self.assertEqual("as ferramentas " in self.texto, not singular)
        self.assertEqual(", que abre " in self.texto, singular)
        self.assertEqual(", que abrem " in self.texto, not singular)

    def test_nao_ressuscita_a_redacao_que_o_proprio_codigo_reprovou(self):
        self.assertNotIn("página oficial externa", self.texto)

    def test_nao_escreve_a_conta_que_envelhece(self):
        # "em apenas duas situações" é o defeito que originou estas
        # provas: número em prosa, ao lado de uma lista que cresce.
        self.assertNotRegex(
            self.texto,
            r"(uma|duas|três|quatro|cinco|\d+)\s+situa[çc][õo]es")

    def test_a_lista_vem_do_registro(self):
        self.assertEqual(
            ferramentas_online(),
            [m.name for m, _ in REGISTRY if m.online and m.available])


if __name__ == "__main__":
    unittest.main(verbosity=2)
