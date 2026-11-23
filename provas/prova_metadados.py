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


class OArquivoExaminadoNaoDecideQuantaMemoriaSeGasta(unittest.TestCase):
    """Documento de escritório é um .zip, e .zip pode ser armadilha."""

    def pacote(self, pasta, membros):
        import zipfile
        alvo = Path(pasta) / "doc.docx"
        with zipfile.ZipFile(alvo, "w", zipfile.ZIP_DEFLATED) as z:
            for nome, dados in membros.items():
                z.writestr(nome, dados)
        return alvo

    def test_membro_acima_do_teto_nao_e_lido(self):
        import tempfile
        import zipfile
        from temis.tools.hash_core import MembroGrandeDemais, ler_membro
        with tempfile.TemporaryDirectory() as pasta:
            alvo = self.pacote(pasta, {"a.xml": b"0" * 500_000})
            self.assertLess(alvo.stat().st_size, 5_000)   # comprime muito
            with zipfile.ZipFile(alvo) as z:
                with self.assertRaises(MembroGrandeDemais):
                    ler_membro(z, "a.xml", 100_000)
                self.assertEqual(len(ler_membro(z, "a.xml", 600_000)),
                                 500_000)

    def test_propriedades_gigantes_nao_derrubam_a_leitura(self):
        import tempfile
        original = mc.TETO_PROPRIEDADES
        mc.TETO_PROPRIEDADES = 1000
        self.addCleanup(setattr, mc, "TETO_PROPRIEDADES", original)
        with tempfile.TemporaryDirectory() as pasta:
            alvo = self.pacote(pasta, {
                "docProps/core.xml": b"<dc:creator>X</dc:creator>" * 1000})
            self.assertEqual(mc._de_office(alvo), [])

    def test_xml_malformado_nao_trava_a_tela(self):
        import time
        inicio = time.monotonic()
        mc._texto_xml(b"<a " * 100_000)
        mc._texto_xml(b"<" * 300_000)
        self.assertLess(time.monotonic() - inicio, 3.0)

    def test_propriedades_normais_seguem_lidas(self):
        dados = mc._texto_xml(
            b"<cp:coreProperties><dc:creator>Fulano</dc:creator>"
            b"<cp:revision>3</cp:revision></cp:coreProperties>")
        self.assertEqual(dados["creator"], "Fulano")
        self.assertEqual(dados["revision"], "3")


class ADataVaiComOFuso(unittest.TestCase):
    """Hora sem fuso, numa peça, é lida como hora local."""

    def test_data_do_office_em_utc_e_dita_como_utc(self):
        self.assertEqual(mc._data_iso("2026-03-10T14:30:00Z"),
                         "10/03/2026 às 14:30:00 (UTC)")

    def test_data_com_desvio_o_conserva(self):
        self.assertEqual(mc._data_iso("2026-03-10T11:30:00-03:00"),
                         "10/03/2026 às 11:30:00 (UTC-03:00)")

    def test_data_sem_fuso_diz_que_nao_ha(self):
        self.assertIn("fuso não informado",
                      mc._data_iso("2026-03-10T14:30:00"))

    def test_data_do_pdf(self):
        self.assertEqual(mc._data_pdf("D:20260310143000Z"),
                         "10/03/2026 às 14:30:00 (UTC)")
        self.assertEqual(mc._data_pdf("D:20260310113000-03'00'"),
                         "10/03/2026 às 11:30:00 (UTC-03:00)")
        self.assertIn("fuso não informado", mc._data_pdf("D:20260310143000"))

    def test_data_do_sistema_de_arquivos_traz_o_fuso_da_estacao(self):
        self.assertRegex(mc._data_br(1_700_000_000),
                         r"\(UTC([+-]\d{2}:\d{2})?\)$")

    def test_foto_com_e_sem_fuso_no_exif(self):
        import tempfile
        from PIL import Image
        with tempfile.TemporaryDirectory() as pasta:
            for desvio, esperado in (("-03:00", "(UTC-03:00)"),
                                     (None, "fuso não informado")):
                alvo = Path(pasta) / f"foto{desvio or 'sem'}.jpg".replace(
                    ":", "")
                imagem = Image.new("RGB", (8, 8))
                exif = imagem.getexif()
                ifd = exif.get_ifd(0x8769)
                ifd[0x9003] = "2026:03:10 11:30:00"      # DateTimeOriginal
                if desvio:
                    ifd[0x9011] = desvio                 # OffsetTimeOriginal
                imagem.save(alvo, exif=exif)
                campos = {c.rotulo: c.valor for c in mc._de_imagem(alvo)}
                with self.subTest(desvio):
                    self.assertIn(esperado, campos["Data da captura"])
                    self.assertIn("10/03/2026 às 11:30:00",
                                  campos["Data da captura"])


class OExameAvancadoDoPdf(unittest.TestCase):
    """Cada verificação por si, e cada achado com o nome certo."""

    def analisar(self, monta):
        import tempfile
        import fitz
        from temis.tools import metadados_avancado as av
        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / "doc.pdf"
            doc = fitz.open()
            doc.new_page().insert_text((72, 100), "texto")
            monta(doc)
            doc.save(alvo)
            doc.close()
            a = av.Analise(caminho=str(alvo))
            av.analisar_pdf(alvo, a)
        return a

    def titulos(self, a):
        return " | ".join(x.titulo for x in a.achados)

    def test_pdf_com_xmp_nao_interrompe_o_exame(self):
        # Era aqui que o exame morria: os anexos, logo abaixo, deixavam
        # de ser verificados.
        def monta(doc):
            doc.set_xml_metadata(
                "<x:xmpmeta xmlns:x='adobe:ns:meta/'><xmp:CreatorTool>"
                "Editor X</xmp:CreatorTool></x:xmpmeta>")
            doc.embfile_add("planilha.xlsx", b"conteudo anexado")
        a = self.analisar(monta)
        self.assertIn("Metadados XMP presentes", self.titulos(a))
        self.assertIn("arquivo(s) embutido(s)", self.titulos(a))
        self.assertEqual(a.erros, [])

    def test_anexo_nao_e_chamado_de_acao_de_abrir_programa(self):
        a = self.analisar(lambda d: d.embfile_add("a.txt", b"x"))
        self.assertIn("arquivo(s) embutido(s)", self.titulos(a))
        self.assertNotIn("executar programa", self.titulos(a))

    def test_a_palavra_no_texto_da_pagina_nao_e_javascript(self):
        a = self.analisar(lambda d: d[0].insert_text(
            (72, 200), "O campo /JavaScript e a acao /Launch do manual"))
        self.assertNotIn("JavaScript", self.titulos(a))
        self.assertNotIn("executar programa", self.titulos(a))

    def test_javascript_de_verdade_e_achado(self):
        def monta(doc):
            x = doc.get_new_xref()
            doc.update_object(
                x, "<</S/JavaScript/JS(app.alert\\(1\\))>>")
            doc.xref_set_key(doc.pdf_catalog(), "OpenAction", f"{x} 0 R")
        a = self.analisar(monta)
        self.assertIn("contém JavaScript", self.titulos(a))

    def test_falha_de_uma_verificacao_e_nomeada_e_nao_cala_as_outras(self):
        import fitz
        original = fitz.Document.get_xml_metadata

        def estoura(self):
            raise RuntimeError("xmp ilegível")

        fitz.Document.get_xml_metadata = estoura
        self.addCleanup(setattr, fitz.Document, "get_xml_metadata", original)
        a = self.analisar(lambda d: d.embfile_add("a.txt", b"x"))
        self.assertTrue(any("metadados XMP — verificação não realizada"
                            in e for e in a.erros))
        self.assertIn("arquivo(s) embutido(s)", self.titulos(a))

    def test_gravacao_incremental_nao_e_afirmada_como_alteracao(self):
        import tempfile
        import fitz
        from temis.tools import metadados_avancado as av
        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / "doc.pdf"
            doc = fitz.open()
            doc.new_page()
            doc.save(alvo)
            doc.close()
            doc = fitz.open(alvo)
            doc.new_page()
            doc.save(alvo, incremental=True,
                     encryption=fitz.PDF_ENCRYPT_KEEP)
            doc.close()
            a = av.Analise(caminho=str(alvo))
            av.analisar_pdf(alvo, a)
        achado = next(x for x in a.achados if "marcas de fim" in x.titulo)
        self.assertIn("assinatura digital", achado.detalhe)
        self.assertEqual(achado.relevancia, av.ATENCAO)


if __name__ == "__main__":
    unittest.main(verbosity=2)
