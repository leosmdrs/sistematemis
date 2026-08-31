"""Provas de Documentos PDF — mesclar, separar e comprimir.

O que estas provas travam não é "a operação rodou", e sim as duas
afirmações que a peça faz e que, se falharem em silêncio, fazem o termo
mentir:

* mesclar e separar **não alteram página alguma** — o resumo de cada
  página produzida é o da página de origem correspondente;
* comprimir **altera** as páginas quando é com perda, e o termo tem de
  declarar isso em vez de esconder.

Há ainda a prova que decidiu o desenho da ferramenta: o PDF **não sai
igual byte a byte**. Se um dia a biblioteca passar a gravar de forma
determinística, esta prova falha — e aí valerá reconsiderar se a
conferência pode ser dos bytes, que é garantia mais forte.
"""

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fitz                                              # noqa: E402

from temis.tools import pdf_core as pc                   # noqa: E402


def fabricar(caminho, paginas, marca):
    """Um PDF com texto distinto em cada página."""
    d = fitz.open()
    for i in range(paginas):
        pg = d.new_page(width=595, height=842)
        pg.insert_text((72, 96), f"{marca} — página {i + 1}", fontsize=18)
    d.save(str(caminho))
    d.close()


def com_imagem(caminho, paginas):
    """Um PDF que se comporta como digitalização: imagem ruidosa e texto.

    O ruído importa: cor chapada desaparece no deflate e faria a
    compactação parecer milagrosa.
    """
    import random
    random.seed(3)
    larg, alt = 620, 877                       # A4 a 75 dpi
    dados = bytearray(larg * alt * 3)
    for i in range(0, len(dados), 3):
        v = max(0, min(255, 200 + random.randint(-45, 45)))
        dados[i] = dados[i + 1] = dados[i + 2] = v
    pix = fitz.Pixmap(fitz.csRGB, larg, alt, bytes(dados), 0)
    d = fitz.open()
    for i in range(paginas):
        pg = d.new_page(width=595, height=842)
        pg.insert_image(fitz.Rect(0, 0, 595, 842), pixmap=pix)
        pg.insert_text((72, 96), f"Texto pesquisável da página {i + 1}",
                       fontsize=12)
    d.save(str(caminho), garbage=4, deflate=True)
    d.close()


class Base(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.a = self.dir / "a.pdf"
        self.b = self.dir / "b.pdf"
        fabricar(self.a, 6, "Documento A")
        fabricar(self.b, 4, "Documento B")

    def sha(self, caminho):
        return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


class OArquivoNaoSeRepete(Base):
    """A medida que decidiu conferir conteúdo, e não bytes."""

    def test_mesclar_duas_vezes_da_arquivos_diferentes(self):
        saidas = []
        for nome in ("m1.pdf", "m2.pdf"):
            p = pc.executar("mesclar", [self.a, self.b], {})
            pc.gravar(p.documento, self.dir / nome)
            p.fechar()
            saidas.append(self.sha(self.dir / nome))
        self.assertNotEqual(
            saidas[0], saidas[1],
            "o PDF passou a sair igual byte a byte — vale reconsiderar se "
            "a conferência pode ser dos bytes")

    def test_mas_o_conteudo_se_repete(self):
        resumos = []
        for _ in range(2):
            p = pc.executar("mesclar", [self.a, self.b], {})
            resumos.append(p.resumo)
            p.fechar()
        self.assertEqual(resumos[0], resumos[1])


class Mesclar(Base):

    def test_junta_na_ordem_e_nao_altera_pagina(self):
        p = pc.executar("mesclar", [self.a, self.b], {})
        try:
            self.assertEqual(p.documento.page_count, 10)
            self.assertTrue(p.paginas_intactas)
            self.assertEqual(p.paginas, p.esperadas)
        finally:
            p.fechar()

    def test_a_ordem_muda_o_resultado(self):
        p1 = pc.executar("mesclar", [self.a, self.b], {})
        p2 = pc.executar("mesclar", [self.b, self.a], {})
        try:
            self.assertNotEqual(p1.resumo, p2.resumo)
            # e as duas continuam sem alterar página
            self.assertTrue(p1.paginas_intactas)
            self.assertTrue(p2.paginas_intactas)
        finally:
            p1.fechar()
            p2.fechar()

    def test_documento_com_senha_e_recusado_com_explicacao(self):
        cifrado = self.dir / "cifrado.pdf"
        with fitz.open(str(self.a)) as d:
            d.save(str(cifrado), encryption=fitz.PDF_ENCRYPT_AES_256,
                   user_pw="segredo")
        with self.assertRaises(RuntimeError) as caso:
            pc.executar("mesclar", [self.a, cifrado], {})
        self.assertIn("senha", str(caso.exception))

    def test_a_sondagem_nao_estoura_com_arquivo_cifrado(self):
        cifrado = self.dir / "cifrado.pdf"
        with fitz.open(str(self.a)) as d:
            d.save(str(cifrado), encryption=fitz.PDF_ENCRYPT_AES_256,
                   user_pw="segredo")
        d = pc.sondar(cifrado)
        self.assertTrue(d.cifrado)
        self.assertIn("senha", d.erro)


class Separar(Base):

    def test_extrai_as_paginas_pedidas_sem_altera_las(self):
        p = pc.executar("separar", [self.a], {"paginas": [0, 2, 4]})
        try:
            self.assertEqual(p.documento.page_count, 3)
            self.assertTrue(p.paginas_intactas)
        finally:
            p.fechar()

    def test_a_ordem_escrita_e_respeitada(self):
        direta = pc.executar("separar", [self.a], {"paginas": [0, 1]})
        trocada = pc.executar("separar", [self.a], {"paginas": [1, 0]})
        try:
            self.assertNotEqual(direta.resumo, trocada.resumo)
        finally:
            direta.fechar()
            trocada.fechar()


class AEscolhaDePaginas(unittest.TestCase):
    """A leitura de "1-3, 7" — e o que ela recusa, dizendo."""

    def test_le_faixas_e_avulsas(self):
        indices, ignorados = pc.ler_paginas("1-3, 7", 10)
        self.assertEqual(indices, [0, 1, 2, 6])
        self.assertEqual(ignorados, [])

    def test_nao_repete_pagina_pedida_duas_vezes(self):
        indices, _ = pc.ler_paginas("1-3, 2", 10)
        self.assertEqual(indices, [0, 1, 2])

    def test_faixa_invertida_e_entendida(self):
        indices, _ = pc.ler_paginas("5-3", 10)
        self.assertEqual(indices, [2, 3, 4])

    def test_o_que_passa_do_documento_e_relatado(self):
        indices, ignorados = pc.ler_paginas("1-2, 90, abc", 5)
        self.assertEqual(indices, [0, 1])
        # os dois pedaços impossíveis aparecem, em vez de sumirem
        self.assertEqual(len(ignorados), 2)

    def test_faixa_que_passa_do_fim_e_cortada_e_avisada(self):
        indices, ignorados = pc.ler_paginas("4-9", 5)
        self.assertEqual(indices, [3, 4])
        self.assertEqual(len(ignorados), 1)
        self.assertIn("5", ignorados[0])

    def test_o_caminho_de_volta(self):
        self.assertEqual(pc.escrever_paginas([0, 1, 2, 6]), "1-3, 7")
        self.assertEqual(pc.escrever_paginas([]), "")


class Comprimir(Base):

    def setUp(self):
        super().setUp()
        self.grande = self.dir / "digitalizado.pdf"
        com_imagem(self.grande, 6)

    def texto_de(self, caminho):
        with fitz.open(str(caminho)) as d:
            return "".join(p.get_text() for p in d)

    def test_sem_perda_nao_altera_pagina_alguma(self):
        p = pc.executar("comprimir", [self.grande], {"nivel": "sem_perda"})
        try:
            self.assertTrue(p.paginas_intactas)
        finally:
            p.fechar()

    def test_com_perda_altera_as_paginas_e_isso_e_declarado(self):
        p = pc.executar("comprimir", [self.grande], {"nivel": "forte"})
        try:
            self.assertFalse(p.paginas_intactas)
        finally:
            p.fechar()

    def test_com_perda_encolhe_de_verdade(self):
        destino = self.dir / "menor.pdf"
        p = pc.executar("comprimir", [self.grande], {"nivel": "forte"})
        pc.gravar(p.documento, destino)
        p.fechar()
        antes = self.grande.stat().st_size
        depois = destino.stat().st_size
        self.assertLess(depois, antes * 0.6, f"{antes} -> {depois}")

    def test_a_camada_de_texto_sobrevive_a_compressao(self):
        # É o que separa esta ferramenta da Tarja Preta, que rasteriza a
        # página e perde o texto. Aqui o documento continua pesquisável.
        original = self.texto_de(self.grande)
        for chave in ("sem_perda", "leve", "media", "forte"):
            destino = self.dir / f"c-{chave}.pdf"
            p = pc.executar("comprimir", [self.grande], {"nivel": chave})
            pc.gravar(p.documento, destino)
            p.fechar()
            self.assertEqual(self.texto_de(destino), original,
                             f"o texto se perdeu no nível {chave}")


class OResultadoNaoHerdaMetadado(Base):

    def test_o_produzido_sai_sem_metadado_do_original(self):
        with fitz.open(str(self.a)) as d:
            d.set_metadata({"title": "SEGREDO", "author": "Fulano",
                            "keywords": "sigiloso"})
            d.save(str(self.dir / "marcado.pdf"))
        destino = self.dir / "limpo.pdf"
        p = pc.executar("mesclar", [self.dir / "marcado.pdf"], {})
        pc.gravar(p.documento, destino)
        p.fechar()
        with fitz.open(str(destino)) as d:
            sujeira = {k: v for k, v in d.metadata.items()
                       if v and k != "format"}
        self.assertEqual(sujeira, {})


class ORoteiro(Base):

    def montar(self, operacao, origens, parametros):
        p = pc.executar(operacao, origens, parametros)
        roteiro = pc.montar(operacao, origens, parametros, p)
        p.fechar()
        return roteiro

    def test_o_roteiro_reproduz_o_resultado(self):
        r = self.montar("mesclar", [self.a, self.b], {})
        situacao, obtido, explicacao = pc.reproduzir(r)
        self.assertEqual((situacao, explicacao), ("sim", ""))
        self.assertEqual(obtido, r.resumo_conteudo)

    def test_origem_alterada_e_detectada(self):
        r = self.montar("mesclar", [self.a, self.b], {})
        fabricar(self.a, 7, "Documento A adulterado")
        situacao, _, explicacao = pc.reproduzir(r)
        self.assertEqual(situacao, "impossivel")
        self.assertIn("não é mais o mesmo arquivo", explicacao)

    def test_origem_sumida_nao_se_confunde_com_divergencia(self):
        r = self.montar("mesclar", [self.a, self.b], {})
        self.b.unlink()
        situacao, _, explicacao = pc.reproduzir(r)
        self.assertEqual(situacao, "impossivel")
        self.assertIn("não foi encontrado", explicacao)

    def test_parametro_trocado_produz_outro_resultado(self):
        r = self.montar("separar", [self.a], {"paginas": [0, 1]})
        r.parametros["paginas"] = [2, 3]
        situacao, _, _ = pc.reproduzir(r)
        self.assertEqual(situacao, "nao")

    def test_o_roteiro_salva_e_volta_inteiro(self):
        r = self.montar("separar", [self.a], {"paginas": [0, 2]})
        caminho = self.dir / "roteiro.json"
        pc.salvar_roteiro(r, caminho)
        volta = pc.ler_roteiro(caminho)
        self.assertEqual(volta.dados(), r.dados())
        self.assertEqual(pc.reproduzir(volta)[0], "sim")

    def test_o_roteiro_registra_a_versao_da_biblioteca(self):
        r = self.montar("mesclar", [self.a], {})
        self.assertTrue(r.pymupdf)

    def test_a_frase_da_conferencia_diz_o_que_houve(self):
        self.assertIn("idêntico", pc.frase_reproducao("sim", "abc"))
        self.assertIn("não confirmou", pc.frase_reproducao("nao", "abc", "x"))
        self.assertIn("não pôde ser concluída",
                      pc.frase_reproducao("impossivel", "", "sumiu"))


class ATela(Base):
    """A tela, sem monitor: o que ela habilita e o que ela invalida."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import PyQt6.QtWebEngineCore                       # noqa: F401
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        from temis.tools.pdf import PDFTool
        self.tela = PDFTool()
        self.addCleanup(self.tela.shutdown)

    def carregar(self, *caminhos):
        self.tela._documentos = [pc.sondar(c) for c in caminhos]
        self.tela._encher_tabela()

    def test_o_icone_tem_traco_visivel(self):
        from temis.icons import draw_icon
        px = draw_icon("tool_pdf", 40, "#0A2442").pixmap(40, 40)
        self.assertFalse(px.isNull())
        img = px.toImage()
        pintados = sum(1 for x in range(40) for y in range(40)
                       if img.pixelColor(x, y).alpha() > 40)
        self.assertGreater(pintados, 120)

    def test_mesclar_exige_dois_documentos(self):
        self.carregar(self.a)
        self.assertFalse(self.tela._b_processar.isEnabled())
        self.carregar(self.a, self.b)
        self.assertTrue(self.tela._b_processar.isEnabled())

    def test_separar_basta_um(self):
        self.carregar(self.a)
        self.tela._trocar_modo("separar")
        self.assertTrue(self.tela._b_processar.isEnabled())

    def test_o_termo_so_acende_depois_de_gravar(self):
        self.carregar(self.a, self.b)
        self.assertFalse(self.tela._b_termo.isEnabled())
        # simula o que o processar/gravar deixam para trás
        p = pc.executar("mesclar", [self.a, self.b], {})
        self.tela._producao = p
        self.tela._roteiro = pc.montar("mesclar", [self.a, self.b], {}, p)
        self.tela._salvo = str(self.dir / "saida.pdf")
        self.tela._refletir()
        self.assertTrue(self.tela._b_termo.isEnabled())

    def test_mexer_na_lista_invalida_o_que_ja_foi_gravado(self):
        self.carregar(self.a, self.b)
        p = pc.executar("mesclar", [self.a, self.b], {})
        self.tela._producao = p
        self.tela._roteiro = pc.montar("mesclar", [self.a, self.b], {}, p)
        self.tela._salvo = str(self.dir / "saida.pdf")
        self.tela._refletir()
        self.tela._trocar_modo("comprimir")
        self.assertFalse(self.tela._b_termo.isEnabled())
        self.assertEqual(self.tela._salvo, "")

    def test_a_escolha_de_paginas_avisa_o_que_nao_vale(self):
        self.carregar(self.a)                       # 6 páginas
        self.tela._trocar_modo("separar")
        self.tela._e_paginas.setText("1-2, 90")
        self.assertIn("Sem efeito", self.tela._lbl_aviso_paginas.text())
        self.tela._e_paginas.setText("1-2")
        self.assertEqual(self.tela._lbl_aviso_paginas.text(), "")

    def test_documento_ilegivel_nao_impede_os_demais(self):
        ruim = self.dir / "quebrado.pdf"
        ruim.write_bytes(b"isto nao e um PDF")
        self.carregar(self.a, ruim, self.b)
        # os dois bons bastam para mesclar
        self.assertTrue(self.tela._b_processar.isEnabled())
        self.assertEqual(len(self.tela._origens()), 2)

    def test_nada_do_painel_passa_da_borda_direita(self):
        """O painel tem largura fixa, e o que passa dela é decepado.

        Não vira barra de rolagem: some. Os três botões de modo estavam
        lado a lado numa fileira, pediam mais largura do que o painel tem
        e cortavam "Comprimir" pela metade — levando junto o texto
        explicativo abaixo, que passava a ser cortado também.

        A medida aqui é a geometria que o Qt de fato deu a cada widget,
        depois de mostrar a tela. Foi preciso chegar a ela: `sizeHint`
        mente para rótulo que quebra linha, e `minimumSize` acusa aperto
        em painel que funciona — as duas apontavam estrago onde não há.
        """
        from PyQt6.QtWidgets import QLabel

        self.tela.resize(1200, 700)
        self.tela.show()
        self.addCleanup(self.tela.hide)
        painel = self.tela._painel

        def direita(w):
            return w.mapTo(painel, w.rect().topLeft()).x() + w.width()

        for chave, botao in self.tela._botoes_modo.items():
            with self.subTest(chave):
                self.assertLessEqual(direita(botao), painel.width())

        for chave in ("mesclar", "separar", "comprimir"):
            self.tela._trocar_modo(chave)
            pagina = self.tela._paginas_modo.currentWidget()
            for lb in pagina.findChildren(QLabel):
                if not (lb.wordWrap() and lb.text()):
                    continue
                with self.subTest(chave + ": texto"):
                    self.assertLessEqual(direita(lb), painel.width())
                    # rótulo que quebra também precisa caber em altura
                    self.assertLessEqual(lb.heightForWidth(lb.width()),
                                         lb.height())

        for botao in (self.tela._b_processar, self.tela._b_termo):
            with self.subTest(botao.text().strip()):
                self.assertLessEqual(direita(botao), painel.width())

    def test_os_detalhes_do_termo_dizem_a_operacao_e_os_parametros(self):
        self.carregar(self.a)
        self.tela._trocar_modo("comprimir")
        p = pc.executar("comprimir", [self.a], {"nivel": "media"})
        self.tela._producao = p
        self.tela._roteiro = pc.montar("comprimir", [self.a],
                                       {"nivel": "media"}, p)
        rotulos = dict(self.tela._detalhes_do_termo())
        self.assertEqual(rotulos["Grau de compactação"], "Média — 96 dpi")
        self.assertIn("96 dpi", rotulos["Reamostragem das imagens"])
        self.assertEqual(rotulos["Páginas do resultado"], "6")


if __name__ == "__main__":
    unittest.main(verbosity=2)
