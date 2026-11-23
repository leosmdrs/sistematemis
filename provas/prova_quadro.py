"""Provas da guarda dos casos no Quadro de Evidências.

O quadro é material de trabalho da apuração, e o que o guarda é um
arquivo de índice e uma pasta de imagens. Um índice ilegível — truncado
por sincronizador, salvo por editor com marca de ordem de bytes, ou de
formato inesperado — virava um quadro vazio sem aviso; o primeiro
salvamento gravava o vazio por cima, e excluir um caso apagava todas as
imagens, tomadas por órfãs.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from temis.tools import quadro_core as qc             # noqa: E402


class Base(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.raiz = Path(self._dir.name)
        acervo = qc.Acervo(self.raiz)
        self.imagem = acervo.guardar_bytes(b"imagem do caso")
        caso = qc.Caso(nome="Caso 1",
                       nodes=[qc.Node(imagem=self.imagem)])
        acervo.gravar([caso], caso.id)
        self.indice = self.raiz / qc.Acervo.ARQUIVO
        self.bom = self.indice.read_bytes()


class IndiceIlegivelEPreservado(Base):

    def estragar(self, conteudo: bytes):
        self.indice.write_bytes(conteudo)
        acervo = qc.Acervo(self.raiz)
        casos, atual = acervo.carregar()
        return acervo, casos, atual

    def test_arquivo_truncado_e_copiado_e_a_falha_fica_dita(self):
        truncado = self.bom[: len(self.bom) // 2]
        acervo, casos, _ = self.estragar(truncado)
        self.assertTrue(acervo.falha_de_leitura)
        self.assertIsNotNone(acervo.copia_preservada)
        self.assertEqual(acervo.copia_preservada.read_bytes(), truncado)
        self.assertEqual(len(casos), 1)            # o quadro abre, vazio

    def test_gravar_depois_nao_destroi_o_que_havia(self):
        truncado = self.bom[: len(self.bom) // 2]
        acervo, casos, atual = self.estragar(truncado)
        acervo.gravar(casos, atual)
        self.assertEqual(acervo.copia_preservada.read_bytes(), truncado)

    def test_json_valido_de_outro_formato_nao_derruba_a_abertura(self):
        for conteudo in (b"[]", b'"texto"', b"42", b'{"casos": 5}',
                         b'{"casos": [7]}'):
            with self.subTest(conteudo=conteudo):
                acervo, casos, _ = self.estragar(conteudo)
                self.assertTrue(acervo.falha_de_leitura)
                self.assertEqual(len(casos), 1)

    def test_marca_de_ordem_de_bytes_nao_torna_o_arquivo_ilegivel(self):
        acervo, casos, _ = self.estragar(b"\xef\xbb\xbf" + self.bom)
        self.assertEqual(acervo.falha_de_leitura, "")
        self.assertEqual(casos[0].nome, "Caso 1")

    def test_as_imagens_nao_sao_apagadas_quando_o_indice_falhou(self):
        acervo, casos, _ = self.estragar(b"{")
        self.assertEqual(acervo.limpar_imagens_orfas(casos), 0)
        self.assertTrue(acervo.caminho_imagem(self.imagem).is_file())

    def test_sem_copia_nada_e_gravado_por_cima(self):
        import shutil
        original = shutil.copy2

        def falha(*a, **k):
            raise OSError("disco cheio")

        shutil.copy2 = falha
        self.addCleanup(setattr, shutil, "copy2", original)
        acervo, casos, atual = self.estragar(b"{")
        self.assertIsNone(acervo.copia_preservada)
        with self.assertRaises(OSError):
            acervo.gravar(casos, atual)
        self.assertEqual(self.indice.read_bytes(), b"{")


class IndiceBomSegueComoAntes(Base):

    def test_carrega_e_limpa_orfas_normalmente(self):
        acervo = qc.Acervo(self.raiz)
        casos, _ = acervo.carregar()
        self.assertEqual(acervo.falha_de_leitura, "")
        orfa = acervo.guardar_bytes(b"sobra")
        self.assertEqual(acervo.limpar_imagens_orfas(casos), 1)
        self.assertFalse(acervo.caminho_imagem(orfa).exists())
        self.assertTrue(acervo.caminho_imagem(self.imagem).is_file())

    def test_indice_valido_e_vazio_nao_e_falha(self):
        self.indice.write_text(json.dumps({"casos": [], "atual": ""}),
                               encoding="utf-8")
        acervo = qc.Acervo(self.raiz)
        acervo.carregar()
        self.assertEqual(acervo.falha_de_leitura, "")

    def test_nome_de_imagem_nao_sai_da_pasta(self):
        acervo = qc.Acervo(self.raiz)
        pasta = (self.raiz / qc.Acervo.IMAGENS).resolve()
        for nome in ("../../fora.png", "/etc/passwd", "..\\..\\fora.png"):
            alvo = acervo.caminho_imagem(nome).resolve()
            self.assertEqual(alvo.parent, pasta, nome)


if __name__ == "__main__":
    unittest.main(verbosity=2)
