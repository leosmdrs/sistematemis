"""Provas da Tarja Preta.

A promessa desta ferramenta é de uma frase: **o texto sob a tarja é
removido do arquivo, não apenas coberto**. É a diferença entre uma peça
que se pode juntar aos autos e um vazamento com um retângulo por cima.
Uma promessa dessas não pode depender de ninguém lembrar de conferir.

Provam-se aqui as duas coisas que a sustentam: que o conteúdo protegido
some do arquivo produzido, e que a ferramenta não se cala quando o
arquivo não tem camada de texto — porque calar, nesse caso, é responder
"nada encontrado" sobre uma página cheia de dado protegido.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz                                            # noqa: E402
from PIL import Image                                  # noqa: E402
from PyQt6.QtWidgets import QApplication               # noqa: E402

from temis.tools import tarja_core as tc               # noqa: E402
from temis.tools import tarja_preta as tp              # noqa: E402

SIGILOSO = "CPF 123.456.789-00"


class Base(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)

    def caminho(self, nome):
        return str(Path(self.pasta.name) / nome)

    def pdf_com_texto(self, nome="original.pdf"):
        doc = fitz.open()
        pagina = doc.new_page()
        pagina.insert_text((72, 100), SIGILOSO, fontsize=14)
        alvo = self.caminho(nome)
        doc.save(alvo)
        doc.close()
        return alvo

    def imagem(self, nome="foto.png", tam=(800, 600)):
        alvo = self.caminho(nome)
        Image.new("RGB", tam, (240, 240, 245)).save(alvo)
        return alvo

    def censurar(self, entrada, tarjas, saida="tarjado.pdf"):
        """Roda a gravação real, no fio da própria prova."""
        doc = fitz.open(entrada)
        destino = self.caminho(saida)
        tp.SaveThread(doc, tarjas, destino).run()
        doc.close()
        return destino


class OTextoSobATarjaSaiDoArquivo(Base):

    def test_o_conteudo_protegido_nao_esta_no_arquivo_produzido(self):
        entrada = self.pdf_com_texto()
        doc = fitz.open(entrada)
        # A tarja cobre a linha inteira onde o dado está.
        alvo = doc[0].search_for(SIGILOSO)[0]
        doc.close()
        saida = self.censurar(entrada, {0: [(alvo, "manual")]})

        produzido = fitz.open(saida)
        texto = "".join(p.get_text() for p in produzido)
        produzido.close()
        self.assertNotIn("123.456.789", texto)
        # Não sobra texto algum: a página virou imagem.
        self.assertEqual(texto.strip(), "")

    def test_a_area_tarjada_fica_preta(self):
        entrada = self.pdf_com_texto()
        doc = fitz.open(entrada)
        alvo = doc[0].search_for(SIGILOSO)[0]
        doc.close()
        saida = self.censurar(entrada, {0: [(alvo, "manual")]})

        produzido = fitz.open(saida)
        pix = produzido[0].get_pixmap()
        escala = pix.width / produzido[0].rect.width
        cor = pix.pixel(int((alvo.x0 + alvo.x1) / 2 * escala),
                        int((alvo.y0 + alvo.y1) / 2 * escala))
        produzido.close()
        self.assertEqual(cor, (0, 0, 0), "a tarja não ficou preta")

    def test_a_pagina_produzida_tem_o_tamanho_da_original(self):
        # Já saiu com o dobro: rasterizava a 2x e gravava a imagem como
        # se fosse 72 DPI, então um A4 virava quase um A2. Peça dos autos
        # em papel de tamanho errado é problema de quem for juntá-la.
        entrada = self.pdf_com_texto()
        antes = fitz.open(entrada)
        medida = fitz.Rect(antes[0].rect)
        antes.close()
        produzido = fitz.open(self.censurar(entrada, {}))
        depois = produzido[0].rect
        produzido.close()
        self.assertAlmostEqual(depois.width, medida.width, delta=1.0)
        self.assertAlmostEqual(depois.height, medida.height, delta=1.0)

    def test_sem_tarja_o_texto_tambem_sai_porque_a_pagina_e_imagem(self):
        # A rasterização é da página inteira, e não só da área tarjada.
        # A peça declara isso; a prova impede que deixe de ser verdade.
        entrada = self.pdf_com_texto()
        saida = self.censurar(entrada, {})
        produzido = fitz.open(saida)
        texto = "".join(p.get_text() for p in produzido)
        produzido.close()
        self.assertEqual(texto.strip(), "")


class AbrirImagem(Base):

    def test_o_filtro_oferece_pdf_e_imagem(self):
        self.assertIn("*.pdf", tp.FILTRO_ABERTURA)
        for extensao in (".png", ".jpg", ".tiff", ".bmp"):
            with self.subTest(extensao):
                self.assertIn("*" + extensao, tp.FILTRO_ABERTURA)

    def test_a_imagem_abre_como_documento_de_uma_pagina(self):
        for nome in ("foto.png", "foto.jpg", "scan.tiff", "velho.bmp"):
            with self.subTest(nome):
                doc = fitz.open(self.imagem(nome))
                self.assertEqual(len(doc), 1)
                self.assertGreater(doc[0].rect.width, 0)
                doc.close()

    def test_tarjar_imagem_produz_pdf_com_a_area_preta(self):
        entrada = self.imagem()
        doc = fitz.open(entrada)
        rect = fitz.Rect(10, 10, 100, 60)
        doc.close()
        saida = self.censurar(entrada, {0: [(rect, "manual")]})

        produzido = fitz.open(saida)
        self.assertEqual(len(produzido), 1)
        pix = produzido[0].get_pixmap()
        escala = pix.width / produzido[0].rect.width
        cor = pix.pixel(int(50 * escala), int(35 * escala))
        produzido.close()
        self.assertEqual(cor, (0, 0, 0))


class ACamadaDeTextoESeAusenciaSeDeclaram(Base):

    def test_pdf_com_texto_tem_camada(self):
        doc = fitz.open(self.pdf_com_texto())
        self.assertTrue(tp.tem_camada_de_texto(doc))
        doc.close()

    def test_imagem_nao_tem_camada(self):
        doc = fitz.open(self.imagem())
        self.assertFalse(tp.tem_camada_de_texto(doc))
        doc.close()

    def test_pdf_de_digitalizacao_tambem_nao_tem(self):
        # O caso que já existia e passava calado: PDF cujas páginas são
        # imagem. A busca automática respondia "nada encontrado".
        doc = fitz.open()
        pagina = doc.new_page()
        pagina.insert_image(pagina.rect, filename=self.imagem())
        alvo = self.caminho("digitalizado.pdf")
        doc.save(alvo)
        doc.close()
        lido = fitz.open(alvo)
        self.assertFalse(tem := tp.tem_camada_de_texto(lido), tem)
        lido.close()

    def test_a_explicacao_aponta_a_ferramenta_que_resolve(self):
        self.assertIn("PDF Pesquisável", tp.SEM_CAMADA_DE_TEXTO)


class ACensuraViraRoteiroConferivel(Base):
    """A peça deixa de afirmar e passa a ser conferível."""

    def montar(self):
        entrada = self.pdf_com_texto()
        doc = fitz.open(entrada)
        alvo = doc[0].search_for(SIGILOSO)[0]
        saida, resumo = tc.compor(doc, {0: [(alvo, "manual")]})
        saida.close()
        doc.close()
        roteiro = tc.montar(entrada, {0: [(alvo, "manual")]})
        roteiro.resumo_conteudo = resumo
        return entrada, roteiro

    def test_o_roteiro_faz_a_ida_e_a_volta(self):
        _, roteiro = self.montar()
        caminho = self.caminho("r.json")
        tc.salvar_roteiro(roteiro, caminho)
        self.assertEqual(tc.ler_roteiro(caminho).dados(), roteiro.dados())

    def test_re_executar_o_roteiro_reproduz_o_mesmo_conteudo(self):
        # A prova que dá razão a todo o resto: com o original e o
        # roteiro, um terceiro chega ao mesmo material censurado.
        _, roteiro = self.montar()
        self.assertEqual(tc.reproduzir(roteiro)[0], "sim")

    def test_o_resumo_e_do_conteudo_e_nao_dos_bytes(self):
        # Gravar duas vezes a mesma censura produz PDFs de bytes
        # diferentes: o formato guarda a hora da gravação. Conferir pelo
        # arquivo acusaria divergência onde não há.
        import hashlib
        entrada, roteiro = self.montar()
        arquivos, conteudos = set(), set()
        for n in range(2):
            doc = fitz.open(entrada)
            saida, resumo = tc.compor(doc, roteiro.por_pagina())
            destino = self.caminho(f"s{n}.pdf")
            saida.save(destino)
            saida.close()
            doc.close()
            arquivos.add(hashlib.sha256(Path(destino).read_bytes()).hexdigest())
            conteudos.add(resumo)
        self.assertEqual(len(conteudos), 1, "o conteúdo tinha de ser o mesmo")
        self.assertEqual(len(arquivos), 2, "os bytes do PDF variam mesmo")

    def test_original_que_mudou_nao_e_censura_que_nao_reproduz(self):
        # "Impossível" e "não reproduz" são coisas diferentes, e a peça
        # não pode chamar uma pela outra.
        entrada, roteiro = self.montar()
        Path(entrada).write_bytes(Path(entrada).read_bytes() + b"%%mais")
        situacao, _, explicacao = tc.reproduzir(roteiro)
        self.assertEqual(situacao, "impossivel")
        self.assertIn("não é mais o mesmo", explicacao)

    def test_original_que_sumiu_tambem_e_impossivel(self):
        entrada, roteiro = self.montar()
        Path(entrada).unlink()
        self.assertEqual(tc.reproduzir(roteiro)[0], "impossivel")

    def test_tarja_diferente_nao_reproduz(self):
        _, roteiro = self.montar()
        roteiro.resumo_conteudo = "0" * 64
        situacao, _, _ = tc.reproduzir(roteiro)
        self.assertEqual(situacao, "nao")

    def test_a_escala_entra_no_roteiro_porque_muda_o_resultado(self):
        entrada, roteiro = self.montar()
        doc = fitz.open(entrada)
        _, outro = tc.compor(doc, roteiro.por_pagina(), escala=3.0)
        doc.close()
        self.assertNotEqual(outro, roteiro.resumo_conteudo)

    def test_a_peca_diz_o_que_a_conferencia_significa(self):
        for situacao, marca in (("sim", "reproduziu resumo de conteúdo"),
                                ("nao", "não deve ser tratado como"),
                                ("impossivel", "segue possível por quem")):
            with self.subTest(situacao):
                self.assertIn(marca, tc.frase_reproducao(situacao))


class ATarjaAcompanhaAPaginaGirada(Base):
    """Em página girada, a tarja automática cai sobre o dado.

    Páginas em paisagem são comuns em peças do SEI e em digitalizações.
    O PDF guarda o texto na folha sem rotação e gira só ao exibir; a
    tarja é desenhada sobre a folha já girada. Usado como veio, o
    retângulo da busca caía em outro ponto: o CPF seguia legível no
    arquivo de saída, e a tela informava a ocorrência como tarjada.
    """

    DADO = "123.456.789-00"

    def pdf_girado(self, graus, texto=None, nome=None):
        doc = fitz.open()
        pagina = doc.new_page()
        pagina.insert_text((100, 200), texto or f"CPF {self.DADO}",
                           fontsize=14)
        pagina.set_rotation(graus)
        alvo = self.caminho(nome or f"girado-{graus}.pdf")
        doc.save(alvo)
        doc.close()
        return alvo

    @staticmethod
    def rotulo_cpf():
        return next(k for k in tp.TarjaPretaTool.PATTERNS
                    if k.startswith("CPF"))

    def onde_esta(self, caminho, trecho):
        """A área do trecho na folha exibida, e quantos pixels de tinta
        ela tem — medidos na imagem, e não deduzidos de coordenada."""
        doc = fitz.open(caminho)
        pagina = doc[0]
        area = fitz.IRect(tc.no_papel(pagina, pagina.search_for(trecho)[0]))
        pix = pagina.get_pixmap()
        tinta = sum(1 for y in range(area.y0, area.y1)
                    for x in range(area.x0, area.x1)
                    if pix.pixel(x, y)[0] < 128)
        doc.close()
        return area, tinta

    def legiveis(self, caminho, area):
        """Pixels da área que não ficaram escuros no arquivo produzido.

        Sob a tarja tudo é preto; onde ela não chegou, sobra o papel
        claro em volta das letras. A borda fica de fora da medida: a
        imagem é reamostrada, e o contorno da tarja sai esfumado.
        """
        doc = fitz.open(caminho)
        pix = doc[0].get_pixmap()
        sobra = sum(1 for y in range(area.y0 + 2, area.y1 - 2)
                    for x in range(area.x0 + 2, area.x1 - 2)
                    if max(pix.pixel(x, y)) > 60)
        doc.close()
        return sobra

    def ferramenta(self, caminho):
        from PyQt6.QtWidgets import QFileDialog
        original = QFileDialog.getOpenFileName
        QFileDialog.getOpenFileName = staticmethod(
            lambda *a, **k: (caminho, ""))
        self.addCleanup(setattr, QFileDialog, "getOpenFileName", original)
        f = tp.TarjaPretaTool()
        self.addCleanup(f.deleteLater)
        f._open_file()
        return f

    def test_a_busca_por_cpf_cobre_o_dado_nas_quatro_rotacoes(self):
        for graus in (0, 90, 180, 270):
            with self.subTest(rotacao=graus):
                entrada = self.pdf_girado(graus)
                area, tinta = self.onde_esta(entrada, self.DADO)
                self.assertGreater(tinta, 100, "a prova não achou o dado")

                f = self.ferramenta(entrada)
                f._search_combo.setCurrentText(self.rotulo_cpf())
                f._search_and_redact()
                self.assertEqual(len(f._tarjas_por_pagina.get(0, [])), 1)

                saida = self.censurar(entrada, f._tarjas_por_pagina,
                                      f"saida-{graus}.pdf")
                self.assertEqual(self.legiveis(saida, area), 0,
                                 "sobrou dado legível fora da tarja")

    def test_o_texto_livre_tambem(self):
        for graus in (90, 180, 270):
            with self.subTest(rotacao=graus):
                entrada = self.pdf_girado(graus)
                area, _ = self.onde_esta(entrada, self.DADO)
                f = self.ferramenta(entrada)
                f._search_combo.setCurrentText("Texto livre")
                f._search_input.setText(self.DADO)
                f._search_and_redact()
                saida = self.censurar(entrada, f._tarjas_por_pagina,
                                      f"livre-{graus}.pdf")
                self.assertEqual(self.legiveis(saida, area), 0)

    def test_a_marcacao_por_colchetes_tambem(self):
        for graus in (90, 180, 270):
            with self.subTest(rotacao=graus):
                entrada = self.pdf_girado(
                    graus, "Nome: [Fulano de Tal]", f"colchete-{graus}.pdf")
                area, tinta = self.onde_esta(entrada, "Fulano de Tal")
                self.assertGreater(tinta, 100)
                f = self.ferramenta(entrada)
                f._redact_brackets()
                saida = self.censurar(entrada, f._tarjas_por_pagina,
                                      f"colchete-saida-{graus}.pdf")
                self.assertEqual(self.legiveis(saida, area), 0)

    def test_a_selecao_de_palavras_aponta_para_a_folha_exibida(self):
        for graus in (0, 90, 180, 270):
            with self.subTest(rotacao=graus):
                entrada = self.pdf_girado(graus)
                area, _ = self.onde_esta(entrada, self.DADO)
                doc = fitz.open(entrada)
                palavra = next(p for p in tp.palavras_da_pagina(doc[0])
                               if p.texto == self.DADO)
                doc.close()
                self.assertEqual(fitz.IRect(palavra.retangulo), area)

    def test_valor_repetido_e_contado_uma_vez_por_ocorrencia(self):
        doc = fitz.open()
        pagina = doc.new_page()
        for i in range(3):
            pagina.insert_text((100, 200 + 40 * i), f"CPF {self.DADO}",
                               fontsize=14)
        entrada = self.caminho("repetido.pdf")
        doc.save(entrada)
        doc.close()
        f = self.ferramenta(entrada)
        f._search_combo.setCurrentText(self.rotulo_cpf())
        f._search_and_redact()
        self.assertEqual(len(f._tarjas_por_pagina[0]), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
