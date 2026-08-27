"""Prova de que a interface não volta a impor fator de escala fracionário.

O programa aplicou `QT_SCALE_FACTOR = "0.85"` por versões, para deixar
tudo 15% menor de uma vez. O comentário ao lado afirmava que o texto não
perdia nitidez; perdia, na interface inteira, e o defeito foi relatado
como "dependendo do tamanho da fonte a resolução não fica boa".

Dependia de o produto dar inteiro. O Qt calcula as métricas em pixels
lógicos inteiros e só então multiplica pelo fator: 16 px de altura de
linha viram 13,60 px reais, e as hastes das letras caem na fronteira
entre pixels. O 11 pt escapava porque 20 × 0,85 = 17 exato.

Como a métrica de origem é sempre inteira, **nenhum fator fracionário é
nítido**. Diminuir a interface se faz baixando as medidas do tema, que
são declaradas em pixel e chegam inteiras à tela.

Quem opera continua podendo escalar pelo ambiente, que o Qt lê sozinho.
O que não pode voltar é o programa impor o fator por conta própria.
"""

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

VARIAVEIS = ("QT_SCALE_FACTOR", "QT_SCREEN_SCALE_FACTORS",
             "QT_DEVICE_PIXEL_RATIO")


class AInterfaceNaoImpoeEscala(unittest.TestCase):

    def ocorrencias(self):
        for arquivo in sorted((RAIZ / "temis").rglob("*.py")):
            texto = arquivo.read_text(encoding="utf-8")
            for numero, linha in enumerate(texto.splitlines(), 1):
                for variavel in VARIAVEIS:
                    if variavel in linha:
                        yield arquivo, numero, linha

    def test_o_fator_so_aparece_em_comentario(self):
        achou = False
        for arquivo, numero, linha in self.ocorrencias():
            achou = True
            with self.subTest(f"{arquivo.name}:{numero}"):
                self.assertTrue(
                    linha.lstrip().startswith("#"),
                    "o programa voltou a impor escala: " + linha.strip())
        self.assertTrue(achou, "o registro do motivo sumiu de temis/")

    def test_o_motivo_continua_escrito_onde_a_crenca_errada_estava(self):
        # A explicação vale mais que a linha removida: sem ela, o atalho
        # de "15% menor de uma vez" volta na primeira vez que alguém
        # achar a interface grande.
        texto = (RAIZ / "temis" / "__main__.py").read_text(encoding="utf-8")
        for marca in ("QT_SCALE_FACTOR", "13,60", "nítido"):
            with self.subTest(marca):
                self.assertIn(marca, texto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
