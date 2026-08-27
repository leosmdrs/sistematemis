"""Prova de que o README descreve o sistema que existe.

A tabela de ferramentas do README chegou a relacionar seis das quinze, e
a defasagem passou despercebida por meses — porque documentação
desatualizada não quebra nada, apenas mente. Quem chega ao repositório lê
aquela tabela como sendo o sistema.

O registro em `temis/tools/__init__.py` é a fonte: é dele que o portal
monta a tela e que a frase de privacidade se ajusta sozinha. Estas provas
obrigam o README a acompanhá-lo.
"""

import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from temis.tools import REGISTRY                      # noqa: E402

#: A marca que a linha de uma ferramenta de rede precisa carregar.
MARCA_REDE = "Acessa a rede"

#: Contagem por extenso, como o texto corrido a escreve. Número escrito
#: em prosa é o que mais envelhece calado: acrescentar uma ferramenta não
#: reescreve o "quinze" de ninguém.
POR_EXTENSO = {
    11: "onze", 12: "doze", 13: "treze", 14: "catorze", 15: "quinze",
    16: "dezesseis", 17: "dezessete", 18: "dezoito", 19: "dezenove",
    20: "vinte",
}


def secao_ferramentas() -> str:
    """Só o trecho do README sob "## Ferramentas", sem as subseções.

    Delimitar importa: o Anti-Injection tem uma tabela de heurísticas com
    o mesmo formato de linha, e ela entraria na conta.
    """
    texto = (RAIZ / "README.md").read_text(encoding="utf-8")
    depois = texto.split("## Ferramentas", 1)[1]
    return depois.split("\n## ", 1)[0].split("\n### ", 1)[0]


def linhas_da_tabela() -> list:
    return [(nome, linha) for linha in secao_ferramentas().splitlines()
            for nome in re.findall(r"^\| \*\*(.+?)\*\* \|", linha)]


class OReadmeAcompanhaORegistro(unittest.TestCase):

    def test_relaciona_todas_as_ferramentas_na_ordem_do_portal(self):
        self.assertEqual([n for n, _ in linhas_da_tabela()],
                         [m.name for m, _ in REGISTRY])

    def test_quem_acessa_a_rede_esta_marcado_e_so_ele(self):
        # A promessa do sistema é processar tudo na estação. Ferramenta
        # que sai à rede e não diz transforma a promessa em engano; e
        # marcar quem não sai gasta a marca de quem sai.
        online = {m.name for m, _ in REGISTRY if m.online}
        for nome, linha in linhas_da_tabela():
            with self.subTest(nome):
                self.assertEqual(MARCA_REDE in linha, nome in online)

    def test_as_contagens_escritas_por_extenso_conferem(self):
        secao = secao_ferramentas().lower()
        total = len(REGISTRY)
        locais = total - sum(1 for m, _ in REGISTRY if m.online)
        for quantas, frase in ((total, " ferramentas"), (locais, " leem")):
            palavra = POR_EXTENSO.get(quantas)
            if palavra is None:
                self.skipTest("acrescente " + str(quantas) + " a POR_EXTENSO")
            with self.subTest(palavra):
                self.assertIn(palavra, secao,
                              "o README não diz mais " + palavra)
                self.assertRegex(secao, palavra + r"\W*\w*" + frase.strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
