"""Provas de que a Extração Registrada não leva credencial ao termo.

O termo da extração é peça dos autos, acessível às partes. A senha, o
código de segundo fator e os tokens de sessão do servidor que operou o
sistema não podem constar dela — e constavam: o clique num campo já
preenchido usava o conteúdo do campo como rótulo, e o "mostrar senha"
da página trocava o tipo do campo, que deixava de ser pulado.

A primeira classe executa o código injetado de verdade, no motor do
próprio navegador embutido, sobre uma página fictícia. As demais conferem
a limpeza feita do lado do programa, sem navegador.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from temis.tools import extracao_core as ec           # noqa: E402

SENHA = "S3nh@-Ficticia!"
CODIGO = "482913"
TOKEN = "tok-9f8e7d6c5b4a"

PAGINA = f"""
<html><body>
<form id="login" action="/entrar?token={TOKEN}" method="post"
      onsubmit="return false">
  <input id="usuario" name="usuario" value="fulano.silva">
  <input id="senha" name="campo1" type="password" value="{SENHA}">
  <input id="oculto" name="csrf_token" type="hidden" value="{TOKEN}">
  <button id="olho" type="button"
          onclick="document.getElementById('senha').type='text'">ver</button>
  <button id="entrar" type="submit">Entrar</button>
</form>
<form id="fator" onsubmit="return false">
  <input id="otp" name="codigo_verificacao" value="{CODIGO}">
  <input id="otp2" name="campo2" autocomplete="one-time-code"
         value="{CODIGO}">
  <button id="confirmar" type="submit">Confirmar</button>
</form>
<form id="consulta" action="/consulta" method="get" onsubmit="return false">
  <input id="matricula" name="matricula" value="1234567">
  <input name="tipo" type="hidden" value="acessos">
  <textarea id="obs" name="obs">texto digitado</textarea>
  <input id="buscar" type="submit" value="Pesquisar">
</form>
<a id="elo" href="https://exemplo.test/sair?token={TOKEN}">Sair</a>
</body></html>
"""


#: Os gestos, na ordem em que são feitos na mesma página.
GESTOS = {
    "campos": ("document.getElementById('usuario').click();"
               "document.getElementById('senha').click();"
               "document.getElementById('obs').click();"
               "document.getElementById('otp').click();"),
    "botao": "document.getElementById('buscar').click();",
    "consulta": "document.getElementById('consulta').requestSubmit();",
    "fator": "document.getElementById('fator').requestSubmit();",
    "elo": ("document.getElementById('elo').addEventListener('click',"
            "function (e) { e.preventDefault(); });"
            "document.getElementById('elo').click();"),
    "login": "document.getElementById('login').requestSubmit();",
    "olho": ("document.getElementById('senha').focus();"
             "document.getElementById('olho').click();"
             "document.getElementById('senha').click();"
             "document.getElementById('login').requestSubmit();"),
}


def _no_navegador(codigo):
    """Faz os gestos num navegador real; None se não houver navegador."""
    pedido = json.dumps({"pagina": PAGINA, "codigo": codigo,
                         "gestos": list(GESTOS.values())})
    try:
        r = subprocess.run(
            [sys.executable, str(RAIZ / "provas" / "_navegador.py")],
            input=pedido, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    for linha in r.stdout.splitlines():
        if linha.startswith("RESULTADO "):
            listas = json.loads(linha[len("RESULTADO "):])
            return {nome: [ec.ler_console(m) for m in mensagens
                           if m.startswith(ec.MARCA)]
                    for nome, mensagens in zip(GESTOS, listas)}
    return None


class OCodigoInjetadoNaoRegistraCredencial(unittest.TestCase):

    atos = None

    @classmethod
    def setUpClass(cls):
        cls.atos = _no_navegador(ec.ESPIA_JS)
        if cls.atos is None:
            raise unittest.SkipTest(
                "sem o navegador embutido nesta máquina")

    def texto(self, gesto):
        return " ".join(" ".join(a) for a in self.atos[gesto] if a)

    def test_clique_em_campo_preenchido_nao_usa_o_conteudo(self):
        self.assertEqual(len(self.atos["campos"]), 4)
        texto = self.texto("campos")
        for dado in (SENHA, CODIGO, "fulano.silva", "texto digitado"):
            self.assertNotIn(dado, texto)
        # O clique continua registrado, pelo nome do campo.
        self.assertIn("usuario", texto)

    def test_botao_continua_rotulado_pelo_que_mostra(self):
        self.assertIn("Pesquisar", self.texto("botao"))

    def test_mostrar_senha_nao_expoe_a_senha(self):
        self.assertTrue(self.atos["olho"])
        self.assertNotIn(SENHA, self.texto("olho"))
        self.assertNotIn(TOKEN, self.texto("olho"))

    def test_formulario_de_login_so_leva_os_nomes(self):
        formulario = [a for a in self.atos["login"]
                      if a[0] == ec.FORMULARIO][0]
        self.assertNotIn("fulano.silva", formulario[2])
        self.assertNotIn(SENHA, formulario[2])
        self.assertIn("usuario=" + ec.SUPRIMIDO, formulario[2])
        self.assertIn("campo1=" + ec.SUPRIMIDO, formulario[2])
        self.assertNotIn(TOKEN, " ".join(formulario))

    def test_codigo_de_uso_unico_nao_e_registrado(self):
        texto = self.texto("fator")
        self.assertNotIn(CODIGO, texto)
        self.assertIn("codigo_verificacao=" + ec.SUPRIMIDO, texto)
        self.assertIn("campo2=" + ec.SUPRIMIDO, texto)

    def test_a_consulta_continua_registrada_com_os_parametros(self):
        formulario = [a for a in self.atos["consulta"]
                      if a[0] == ec.FORMULARIO][0]
        self.assertIn("matricula=1234567", formulario[2])
        self.assertIn("tipo=acessos", formulario[2])

    def test_destino_do_clique_sai_sem_o_token(self):
        self.assertNotIn(TOKEN, self.texto("elo"))
        self.assertIn("Sair", self.texto("elo"))


class OEnderecoSaiSemCredencial(unittest.TestCase):

    def test_parametro_de_login_unico_e_suprimido(self):
        limpo = ec.limpar_url(
            "https://sso.exemplo/volta?code=AbC123&state=xyz&pagina=2")
        self.assertNotIn("AbC123", limpo)
        self.assertNotIn("xyz", limpo)
        self.assertIn("pagina=2", limpo)

    def test_fragmento_com_token_e_suprimido(self):
        limpo = ec.limpar_url(
            "https://app.exemplo/#access_token=eyJhbGci&expires_in=3600")
        self.assertNotIn("eyJhbGci", limpo)
        self.assertIn("expires_in=3600", limpo)

    def test_fragmento_comum_permanece(self):
        self.assertEqual(ec.limpar_url("https://a.exemplo/doc#secao-2"),
                         "https://a.exemplo/doc#secao-2")

    def test_usuario_e_senha_no_endereco_saem(self):
        limpo = ec.limpar_url("https://fulano:segredo@a.exemplo/x")
        self.assertNotIn("segredo", limpo)
        self.assertNotIn("fulano", limpo)

    def test_parametro_de_consulta_nao_e_tocado(self):
        endereco = ("https://a.exemplo/busca?matricula=1234567"
                    "&inicio=01/01/2026&barcode=77&estado=DF")
        self.assertEqual(ec.limpar_url(endereco), endereco)

    def test_o_ato_registrado_nunca_guarda_o_endereco_cru(self):
        s = ec.Sessao()
        s.comecar("x")
        s.anotar(ec.NAVEGACAO, "Acesso a endereço",
                 "https://a.exemplo/cb?session_id=ZZZ9#id_token=QQQ1")
        self.assertNotIn("ZZZ9", s.eventos[-1].url)
        self.assertNotIn("QQQ1", s.eventos[-1].url)


class OQueChegaPeloConsoleEConferidoDeNovo(unittest.TestCase):

    def test_campo_sigiloso_e_suprimido_mesmo_se_a_pagina_o_enviar(self):
        ato = ec.ler_console(
            "TEMIS::formulario::/x::post::q=a | senha=abc | csrf_token=t1")
        self.assertEqual(ato[2], "q=a | senha=[suprimido] | "
                                 "csrf_token=[suprimido]")

    def test_destino_do_formulario_passa_pela_limpeza(self):
        ato = ec.ler_console("TEMIS::formulario::/x?token=abc::get::q=a")
        self.assertNotIn("abc", ato[1])

    def test_a_ressalva_do_termo_diz_o_alcance_da_supressao(self):
        texto = " ".join(ec.RESSALVAS)
        self.assertIn("código de uso único", texto)
        self.assertIn("não é reconhecida", texto)
        self.assertNotIn("nunca", texto)


SEGREDO = "0123456789abcdef0123456789abcdef"

PAGINA_HOSTIL = """
<html><head><script>
// Uma página preparada para enganar o registro.
window.addEventListener('click', function (e) {
  e.stopImmediatePropagation();
}, true);
document.addEventListener('submit', function (e) {
  e.stopImmediatePropagation();
}, true);
</script></head><body>
<button id="apagar">Apagar registros</button>
<form id="f" onsubmit="return false"><input name="q" value="alvo">
<button id="enviar" type="submit">Enviar</button></form>
</body></html>
"""

GESTOS_HOSTIS = {
    "clique": "document.getElementById('apagar').click();",
    "envio": "document.getElementById('f').requestSubmit();",
    "forjado": ("console.log('TEMIS::clique::BUTTON::Consultar "
                "servidor::');"),
    "sonda": ("console.log('VE=' + (typeof window.__temis_espia) + '/' + "
              "(typeof PREFIXO));"),
}


class APaginaNaoSuprimeNemForjaORegistro(unittest.TestCase):
    """O código injetado como o programa o injeta: isolado e primeiro."""

    brutos = None

    @classmethod
    def setUpClass(cls):
        pedido = json.dumps({
            "pagina": PAGINA_HOSTIL, "mundo": "aplicacao",
            "codigo": ec.montar_espia(SEGREDO),
            "gestos": list(GESTOS_HOSTIS.values())})
        try:
            r = subprocess.run(
                [sys.executable, str(RAIZ / "provas" / "_navegador.py")],
                input=pedido, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            raise unittest.SkipTest("sem o navegador embutido")
        linha = next((l for l in r.stdout.splitlines()
                      if l.startswith("RESULTADO ")), None)
        if linha is None:
            raise unittest.SkipTest("sem o navegador embutido")
        cls.brutos = dict(zip(GESTOS_HOSTIS,
                              json.loads(linha[len("RESULTADO "):])))

    def atos(self, gesto):
        lidos = (ec.ler_console(m, SEGREDO) for m in self.brutos[gesto])
        return [a for a in lidos if a]

    def test_a_pagina_nao_consegue_suprimir_o_clique(self):
        atos = self.atos("clique")
        self.assertEqual(len(atos), 1)
        self.assertIn("Apagar registros", atos[0][1])

    def test_nem_o_envio_de_formulario(self):
        atos = self.atos("envio")
        self.assertTrue(any(a[0] == ec.FORMULARIO and "q=alvo" in a[2]
                            for a in atos))

    def test_entrada_forjada_pela_pagina_e_descartada(self):
        self.assertTrue(self.brutos["forjado"])          # ela escreveu
        self.assertEqual(self.atos("forjado"), [])       # e não entrou

    def test_a_pagina_nao_enxerga_o_codigo_nem_o_segredo(self):
        self.assertEqual(self.brutos["sonda"], ["VE=undefined/undefined"])
        tudo = " ".join(m for lista in self.brutos.values() for m in lista
                        if not m.startswith(ec.MARCA + SEGREDO))
        self.assertNotIn(SEGREDO, tudo)


class OSegredoNaMensagem(unittest.TestCase):

    def test_com_segredo_a_marca_sozinha_nao_basta(self):
        self.assertIsNone(ec.ler_console("TEMIS::clique::A::x::", SEGREDO))
        self.assertIsNone(
            ec.ler_console("TEMIS::outro-segredo::clique::A::x::", SEGREDO))
        ato = ec.ler_console(f"TEMIS::{SEGREDO}::clique::A::x::", SEGREDO)
        self.assertEqual(ato[0], ec.CLIQUE)

    def test_o_codigo_gerado_leva_o_segredo(self):
        self.assertIn(SEGREDO, ec.montar_espia(SEGREDO))
        self.assertNotIn(SEGREDO, ec.ESPIA_JS)


class ODiligenciaSoAbreEnderecoDaRede(unittest.TestCase):
    """`file://` e `smb://` não são sistema consultado."""

    def ir(self, texto):
        import os
        from types import SimpleNamespace
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QMessageBox
        from temis.tools import extracao as tela
        abertos, avisos = [], []
        original = QMessageBox.warning
        QMessageBox.warning = staticmethod(
            lambda *a, **k: avisos.append(a[2]))
        self.addCleanup(setattr, QMessageBox, "warning", original)
        guardado = tela.WEBVIEW_DISPONIVEL
        tela.WEBVIEW_DISPONIVEL = True
        self.addCleanup(setattr, tela, "WEBVIEW_DISPONIVEL", guardado)
        f = SimpleNamespace(
            _e_url=SimpleNamespace(text=lambda: texto),
            _pagina=SimpleNamespace(
                load=lambda url: abertos.append(url.toString())))
        tela.ExtracaoTool._ir(f)
        return abertos, avisos

    def test_arquivo_local_e_pasta_de_rede_sao_recusados(self):
        for endereco in ("file:///C:/Windows/win.ini", "smb://servidor/pasta",
                         "ftp://exemplo.test/x", "javascript://x"):
            with self.subTest(endereco):
                abertos, avisos = self.ir(endereco)
                self.assertEqual(abertos, [])
                self.assertEqual(len(avisos), 1)

    def test_http_e_https_abrem_e_o_resto_ganha_https(self):
        self.assertEqual(self.ir("https://sistema.exemplo/x")[0],
                         ["https://sistema.exemplo/x"])
        self.assertEqual(self.ir("sistema.exemplo")[0],
                         ["https://sistema.exemplo"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
