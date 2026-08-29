"""Provas da Reconstrução de Conversa.

A peça atesta uma coisa só: que a reconstrução corresponde ao arquivo de
exportação, identificado por resumo criptográfico. Estas provas cuidam do
que sustenta isso — que o parser lê os formatos reais (iOS e Android),
que as mídias do pacote são resumidas, que a reprodução é conferível, e
que o termo declara o que não atesta.
"""

import os
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from temis.tools import conversa_core as cc           # noqa: E402

ANDROID = """25/12/2024 14:30 - As mensagens e as chamadas são protegidas com a criptografia de ponta a ponta.
25/12/2024 14:31 - João Silva: Bom dia, tudo certo com o repasse?
25/12/2024 14:32 - Maria: Sim, já enviei o
comprovante ontem.
25/12/2024 14:33 - João Silva: IMG-20241225-WA0001.jpg (arquivo anexado)
25/12/2024 14:34 - Maria: <Mídia oculta>
25/12/2024 14:35 - João Silva saiu"""

IOS = """[25/12/2024 14:31:05] João Silva: Bom dia
[25/12/2024, 14:32:10] Maria: Segue ‎<anexado: 00000042-PHOTO.jpg>
[25/12/2024 2:40:00 PM] João Silva: à tarde então"""


class OParserLeOsFormatos(unittest.TestCase):

    def test_android_separa_quem_quando_e_o_que(self):
        msgs, avisos = cc.parse_texto(ANDROID)
        self.assertEqual(avisos, [])
        comuns = [m for m in msgs if not m.sistema]
        self.assertEqual([m.autor for m in comuns],
                         ["João Silva", "Maria", "João Silva", "Maria"])
        self.assertEqual(comuns[0].texto, "Bom dia, tudo certo com o repasse?")

    def test_mensagem_de_varias_linhas_fica_junta(self):
        msgs, _ = cc.parse_texto(ANDROID)
        maria = next(m for m in msgs if m.autor == "Maria" and "comprovante" in m.texto)
        self.assertIn("\n", maria.texto)
        self.assertIn("comprovante ontem", maria.texto)

    def test_mensagens_de_sistema_sao_reconhecidas(self):
        msgs, _ = cc.parse_texto(ANDROID)
        sistema = [m for m in msgs if m.sistema]
        # a de criptografia e a de "saiu"
        self.assertEqual(len(sistema), 2)
        self.assertTrue(any("criptografia" in m.texto for m in sistema))
        self.assertTrue(any("saiu" in m.texto for m in sistema))

    def test_ios_com_colchetes_e_segundos(self):
        msgs, avisos = cc.parse_texto(IOS)
        self.assertEqual(avisos, [])
        self.assertEqual(len(msgs), 3)
        self.assertEqual(msgs[0].quando_iso, "2024-12-25T14:31:05")

    def test_am_pm_vira_24h(self):
        msgs, _ = cc.parse_texto(IOS)
        self.assertEqual(msgs[2].quando_iso, "2024-12-25T14:40:00")

    def test_midia_anexa_e_omitida_sao_distinguidas(self):
        msgs, _ = cc.parse_texto(ANDROID)
        anexa = next(m for m in msgs if "IMG-" in (m.midia or ""))
        self.assertEqual(anexa.midia, "IMG-20241225-WA0001.jpg")
        omitida = next(m for m in msgs if m.midia.startswith("("))
        self.assertIn("não incluída", omitida.midia)

    def test_dia_maior_que_doze_nao_e_confundido_com_mes(self):
        # 25/12 é 25 de dezembro, não 12 de 25.
        self.assertEqual(cc._quando_iso("25/12/2024", "10:00", ""),
                         "2024-12-25T10:00:00")
        # formato americano 12/25 se corrige.
        self.assertEqual(cc._quando_iso("12/25/2024", "10:00", ""),
                         "2024-12-25T10:00:00")

    def test_arquivo_que_nao_e_conversa_avisa(self):
        _, avisos = cc.parse_texto("linha qualquer\noutra linha")
        self.assertTrue(avisos)
        self.assertIn("Nenhuma mensagem", avisos[0])


class OPacoteResumeAsMidias(unittest.TestCase):

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)

    def test_zip_le_o_texto_e_resume_cada_midia(self):
        import hashlib
        zpath = Path(self.pasta.name) / "conversa.zip"
        foto = b"os bytes da foto"
        with zipfile.ZipFile(zpath, "w") as z:
            z.writestr("_chat.txt", ANDROID)
            z.writestr("IMG-20241225-WA0001.jpg", foto)
        c = cc.abrir(zpath)
        self.assertEqual(c.formato, "pacote")
        self.assertEqual(c.n_midias, 1)
        anexa = next(m for m in c.mensagens if m.midia_sha256)
        self.assertEqual(anexa.midia_sha256, hashlib.sha256(foto).hexdigest())

    def test_zip_sem_texto_avisa(self):
        zpath = Path(self.pasta.name) / "vazio.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            z.writestr("foto.jpg", b"x")
        c = cc.abrir(zpath)
        self.assertTrue(c.avisos)


class AReproducaoEhConferivel(unittest.TestCase):

    def texto_em_arquivo(self):
        p = Path(tempfile.mkdtemp()) / "c.txt"
        p.write_text(ANDROID, encoding="utf-8")
        return p

    def test_o_resumo_do_arquivo_e_tomado_na_abertura(self):
        c = cc.abrir(self.texto_em_arquivo())
        self.assertEqual(len(c.resumo_origem), 64)

    def test_o_resumo_do_conteudo_se_reproduz(self):
        p = self.texto_em_arquivo()
        a, b = cc.abrir(p), cc.abrir(p)
        self.assertEqual(a.resumo_conteudo(), b.resumo_conteudo())

    def test_conteudo_diferente_muda_o_resumo(self):
        a = cc.abrir(self.texto_em_arquivo())
        outra = Path(tempfile.mkdtemp()) / "d.txt"
        outra.write_text(ANDROID.replace("Bom dia", "Boa tarde"), encoding="utf-8")
        b = cc.abrir(outra)
        self.assertNotEqual(a.resumo_conteudo(), b.resumo_conteudo())


class OTermoDeclaraOQueNaoAtesta(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def peca(self):
        p = Path(tempfile.mkdtemp()) / "c.txt"
        p.write_text(ANDROID, encoding="utf-8")
        c = cc.abrir(p)
        html = cc.build_html(c, cc.Declarante(nome="Fulano"),
                             cc.Procedimento(numero="123"))
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))

    def test_a_peca_identifica_o_arquivo_e_lista_a_conversa(self):
        texto = self.peca()
        self.assertIn("Termo de Reconstrução de Conversa", texto)
        self.assertIn("Resumo do arquivo", texto)
        self.assertIn("João Silva", texto)
        self.assertIn("Maria", texto)

    def test_a_peca_diz_o_que_nao_atesta(self):
        # A honestidade dos limites é o que dá peso ao que ela afirma.
        texto = self.peca()
        self.assertIn("não a autenticidade nem a completude", texto)
        self.assertIn("pode ter sido editado", texto)
        self.assertIn("fuso do aparelho", texto)


class ADescricaoDaFerramentaConfereComORegistro(unittest.TestCase):

    def test_a_ferramenta_esta_no_registro_com_guia(self):
        from temis.tools import REGISTRY
        from temis.guias import GUIAS
        chaves = [m.key for m, _ in REGISTRY]
        self.assertIn("conversa", chaves)
        self.assertIn("conversa", GUIAS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
