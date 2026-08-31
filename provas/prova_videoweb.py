"""Provas de Vídeo da Internet — a captura documentada.

A maior parte destas provas não toca a rede, e é de propósito: o que
precisa ficar travado é o que a peça **afirma**, e isso se prova sem
baixar nada. As que dependem da internet ficam à parte e se pulam
sozinhas quando a estação não alcança a rede — prova que falha por falta
de rede não diz nada sobre o programa e ensina a ignorar falha.

O material usado nas provas de rede é o curta "Big Buck Bunny", da
Blender Foundation, publicado sob licença Creative Commons que permite o
uso. É o vídeo que se usa para testar ferramenta de vídeo justamente por
isso.
"""

import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from temis.tools import videoweb_core as vc               # noqa: E402

#: Curta da Blender Foundation, licença Creative Commons.
URL_LIVRE = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"


def tem_rede() -> bool:
    try:
        urllib.request.urlopen("https://www.youtube.com", timeout=8)
        return True
    except Exception:                                      # noqa: BLE001
        return False


def com_qt():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import PyQt6.QtWebEngineCore                           # noqa: F401
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class AIdadeDaBiblioteca(unittest.TestCase):
    """Ferramenta que acompanha mudança de plataforma envelhece.

    Envelhecer aqui não dá erro claro: dá extração que falha por motivo
    obscuro. Dizer a idade antes é mais honesto do que deixar a pessoa
    descobrir no meio de uma diligência.
    """

    def test_a_versao_do_yt_dlp_e_uma_data(self):
        self.assertEqual(vc._data_da_versao("2026.08.19").isoformat(),
                         "2026-08-19")
        self.assertIsNone(vc._data_da_versao("qualquer coisa"))

    def test_versao_recente_nao_desconfia(self):
        import datetime
        hoje = datetime.date.today()
        pode, recado = vc.estado()
        self.assertTrue(pode, recado)
        recente = vc._data_da_versao(vc.versao())
        if recente and (hoje - recente).days <= vc.DIAS_PARA_DESCONFIAR:
            self.assertNotIn("dias atrás", recado)

    def test_ausencia_da_biblioteca_e_dita_e_nao_estoura(self):
        original = vc.versao
        vc.versao = lambda: ""
        try:
            pode, recado = vc.estado()
        finally:
            vc.versao = original
        self.assertFalse(pode)
        self.assertIn("não está instalada", recado)


class AExplicacaoDaFalha(unittest.TestCase):
    """Cada motivo de recusa tem de chegar em português, e sem mentir."""

    def test_video_privado_diz_que_nao_se_contorna_acesso(self):
        texto = vc.explicar_falha("ERROR: Private video. Sign in...")
        self.assertIn("privado", texto)
        self.assertIn("não contorna", texto)

    def test_restricao_de_idade_e_explicada(self):
        texto = vc.explicar_falha("Sign in to confirm your age")
        self.assertIn("restrição de idade", texto)
        self.assertIn("não se identifica", texto)

    def test_falha_de_extracao_aponta_a_desatualizacao(self):
        texto = vc.explicar_falha("nsig extraction failed: Some error")
        self.assertIn("desatualizada", texto)

    def test_o_que_nao_se_conhece_vai_cru(self):
        texto = vc.explicar_falha("ERROR: coisa nunca vista antes")
        self.assertIn("coisa nunca vista antes", texto)

    def test_a_cor_do_terminal_nao_vaza_para_a_peca(self):
        texto = vc.explicar_falha("\x1b[0;31mERROR:\x1b[0m algo")
        self.assertNotIn("\x1b", texto)


class AEscolhaDeQualidade(unittest.TestCase):

    def test_o_seletor_pede_imagem_e_som_em_separado(self):
        # É o que obriga a junção local — e o que a peça declara.
        self.assertIn("+", vc.seletor("1080"))

    def test_somente_audio_nao_junta_faixa(self):
        self.assertNotIn("+", vc.seletor("audio"))

    def test_chave_desconhecida_cai_na_melhor(self):
        self.assertEqual(vc.seletor("inventada"), vc.QUALIDADES[0][2])


class OQueAPecaAfirma(unittest.TestCase):
    """O termo, montado sobre uma captura de mentira.

    O que se confere aqui é o texto: se ele diz o que foi obtido, de
    onde, quando, e se declara os limites — inclusive o que a ferramenta
    **não** promete.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = com_qt()

    def termo(self, **kw):
        p = vc.Publicacao(
            url="https://exemplo.invalido/watch?v=abc123",
            identificador="abc123", titulo="Vídeo de exemplo",
            canal="Canal de Exemplo",
            canal_url="https://exemplo.invalido/canal",
            publicado_em="10/11/2025", duracao=635, visualizacoes=23343108,
            licenca="Creative Commons", disponibilidade="public",
            extrator="Youtube", descricao="Uma descrição publicada.")
        c = vc.Captura(arquivo="video [abc123].mp4", sha256="a" * 64,
                       tamanho=10 * 1024 * 1024, formato="MP4",
                       largura=1920, altura=1080,
                       quando="27/08/2026 às 15:00:00 (UTC-03:00)",
                       juntou_faixas=True, qualidade="1080",
                       yt_dlp="2026.08.19", ffmpeg="9.0.1", publicacao=p)
        for k, v in kw.items():
            setattr(c, k, v)
        t = vc.montar_termo(c)
        t.nome, t.cargo = "Fulano de Tal", "Policial Rodoviário Federal"
        t.matricula, t.lotacao = "1234567", "CGCOR"
        t.numero_processo, t.dia, t.mes, t.ano = "08650.1/2026-11", 27, 8, 2026
        return t

    def texto(self, t):
        import re
        return re.sub(r"\s+", " ",
                      re.sub(r"<[^>]+>", " ", vc.build_html(t)))

    def test_a_peca_identifica_endereco_titulo_canal_e_hora(self):
        texto = self.texto(self.termo())
        for esperado in ("exemplo.invalido/watch?v=abc123",
                         "Vídeo de exemplo", "Canal de Exemplo",
                         "27/08/2026 às 15:00:00", "a" * 64):
            self.assertIn(esperado, texto)

    def test_a_peca_nao_promete_reprodutibilidade(self):
        texto = self.texto(self.termo())
        self.assertIn("não afirma reprodutibilidade", texto)

    def test_a_peca_declara_a_juncao_local_das_faixas(self):
        texto = self.texto(self.termo())
        self.assertIn("junção local", texto)
        self.assertIn("FFmpeg 9.0.1", texto)

    def test_fluxo_unico_e_dito_como_fluxo_unico(self):
        texto = self.texto(self.termo(juntou_faixas=False))
        self.assertIn("fluxo único", texto)

    def test_a_peca_diz_que_os_dados_sao_da_plataforma(self):
        texto = self.texto(self.termo())
        self.assertIn("informados pela própria plataforma", texto)
        self.assertIn("não os certifica", texto)

    def test_a_peca_registra_que_nada_restrito_foi_contornado(self):
        texto = self.texto(self.termo())
        self.assertIn("Nenhuma credencial foi apresentada", texto)
        self.assertIn("pública", texto)

    def test_a_peca_traz_cabecalho_e_rodape_como_as_demais(self):
        html = vc.build_html(self.termo())
        self.assertIn("Sistema", html)          # cabeçalho
        self.assertIn("yt-dlp", self.texto(self.termo()))

    def test_a_versao_em_texto_puro_diz_o_mesmo(self):
        texto = vc.build_texto(self.termo())
        for esperado in ("O QUE ESTAVA PUBLICADO", "O QUE FOI OBTIDO",
                         "a" * 64, "não afirma reprodutibilidade"):
            self.assertIn(esperado, texto)

    def test_a_duracao_sai_legivel(self):
        self.assertEqual(vc.formatar_duracao(635), "00:10:35")
        self.assertEqual(vc.formatar_duracao(0), "—")


class ComRede(unittest.TestCase):
    """As que precisam alcançar a plataforma."""

    @classmethod
    def setUpClass(cls):
        if not tem_rede():
            raise unittest.SkipTest("a estação não alcança a rede")

    def test_sondar_traz_o_que_a_peca_precisa(self):
        p = vc.sondar(URL_LIVRE)
        self.assertEqual(p.erro, "")
        self.assertTrue(p.titulo)
        self.assertTrue(p.canal)
        self.assertTrue(p.identificador)
        self.assertGreater(p.duracao, 0)
        # o campo que sustenta a afirmação de que nada restrito se contornou
        self.assertEqual(p.disponibilidade, "public")
        self.assertTrue(p.publica)

    def test_endereco_que_nao_e_video_vira_recado_e_nao_queda(self):
        p = vc.sondar("https://exemplo.invalido/nao-existe-mesmo")
        self.assertTrue(p.erro)

    def test_baixar_de_verdade_e_medir_o_que_veio(self):
        with tempfile.TemporaryDirectory() as pasta:
            c = vc.baixar(URL_LIVRE, pasta, qualidade="480")
            self.assertEqual(c.erro, "")
            arquivo = Path(c.arquivo)
            self.assertTrue(arquivo.is_file())
            self.assertGreater(c.tamanho, 100_000)
            self.assertEqual(len(c.sha256), 64)
            self.assertTrue(c.quando)
            self.assertTrue(c.yt_dlp)
            self.assertTrue(c.juntou_faixas)
            self.assertTrue(c.publicacao.titulo)
            # o resumo é do arquivo que ficou em disco
            from temis.tools.hash_core import sha256_file
            self.assertEqual(c.sha256, sha256_file(str(arquivo)))


class ATela(unittest.TestCase):
    """A tela, sem monitor e sem rede: o que ela habilita e quando."""

    @classmethod
    def setUpClass(cls):
        cls.app = com_qt()

    def setUp(self):
        from temis.tools.videoweb import VideoWebTool
        self.tela = VideoWebTool()
        self.addCleanup(self.tela.shutdown)

    def publicacao(self, **kw):
        base = dict(url="https://exemplo.invalido/v", titulo="Um vídeo",
                    canal="Canal", duracao=60, disponibilidade="public",
                    extrator="Youtube", publicado_em="10/11/2025")
        base.update(kw)
        return vc.Publicacao(**base)

    def test_a_ferramenta_se_declara_de_internet(self):
        # O sistema promete processamento local; a que sai da máquina tem
        # de dizer isso, e não ficar escondida atrás da promessa geral.
        self.assertTrue(self.tela.meta.online)

    def test_o_icone_tem_traco_visivel(self):
        from temis.icons import draw_icon
        px = draw_icon("tool_videoweb", 40, "#0A2442").pixmap(40, 40)
        self.assertFalse(px.isNull())
        img = px.toImage()
        pintados = sum(1 for x in range(40) for y in range(40)
                       if img.pixelColor(x, y).alpha() > 40)
        self.assertGreater(pintados, 120)

    def test_nasce_sem_consultar_sem_capturar_e_sem_termo(self):
        self.assertFalse(self.tela._b_consultar.isEnabled())
        self.assertFalse(self.tela._b_capturar.isEnabled())
        self.assertFalse(self.tela._b_termo.isEnabled())

    def test_endereco_escrito_habilita_a_consulta(self):
        self.tela._e_url.setText("https://exemplo.invalido/v")
        self.tela._refletir()
        self.assertTrue(self.tela._b_consultar.isEnabled())
        # mas ainda não a captura: consulta-se antes de baixar
        self.assertFalse(self.tela._b_capturar.isEnabled())

    def test_consultado_libera_a_captura(self):
        self.tela._publicacao = self.publicacao()
        self.tela._refletir()
        self.assertTrue(self.tela._b_capturar.isEnabled())
        self.assertFalse(self.tela._b_termo.isEnabled())

    def test_o_termo_so_acende_depois_da_captura(self):
        self.tela._publicacao = self.publicacao()
        self.tela._captura = vc.Captura(arquivo="v.mp4", sha256="a" * 64)
        self.tela._refletir()
        self.assertTrue(self.tela._b_termo.isEnabled())

    def test_trocar_o_endereco_invalida_o_que_se_sabia(self):
        self.tela._publicacao = self.publicacao()
        self.tela._captura = vc.Captura(arquivo="v.mp4", sha256="a" * 64)
        self.tela._e_url.setText("https://exemplo.invalido/outro")
        self.assertIsNone(self.tela._publicacao)
        self.assertIsNone(self.tela._captura)
        self.assertFalse(self.tela._b_termo.isEnabled())

    def test_a_tela_mostra_a_disponibilidade_antes_de_baixar(self):
        self.tela._mostrar(self.publicacao())
        self.assertIn("pública", self.tela._lbl_dados.text())

    def test_disponibilidade_incomum_e_assinalada(self):
        from temis.theme import PALETTE
        self.tela._mostrar(self.publicacao(disponibilidade="unlisted"))
        texto = self.tela._lbl_dados.text()
        self.assertIn("não listada", texto)
        self.assertIn(PALETTE["warning"], texto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
