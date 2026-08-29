"""
Reconstrução de Conversa — a tela.

Abre uma exportação de conversa (o arquivo que o próprio aplicativo gera),
mostra a conversa reconstruída e emite o termo que a identifica pelo
resumo criptográfico do arquivo. Ver o cabeçalho de `conversa_core` para
o que a peça atesta e o que ela não atesta.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTextBrowser,
    QVBoxLayout, QWidget,
)

from ..icons import draw_icon
from ..theme import PALETTE
from ..widgets import (SidebarPanel, field_label, group_title, hsep,
                       ler_procedimento, output_button, preparar_procedimento,
                       primary_button, subtext, NoScrollComboBox)
from .base import ToolMeta, ToolPage
from . import conversa_core as core

META = ToolMeta(
    key="conversa",
    name="Reconstruir Conversa",
    icon="tool_conversa",
    tagline="Reconstrói conversa exportada",
    description=(
        "Abre a exportação de uma conversa — o arquivo que o próprio "
        "aplicativo gera, em texto ou no pacote com as mídias — e a "
        "reconstrói num documento conferível, identificado pelo resumo "
        "criptográfico do arquivo de origem. A peça atesta que a "
        "reconstrução corresponde àquele arquivo; não a autenticidade da "
        "conversa, e diz isso com todas as letras. As mídias do pacote são "
        "resumidas em SHA-256."
    ),
)


class ConversaTool(ToolPage):
    """A ferramenta de reconstrução de conversa."""

    meta = META

    def __init__(self, parent=None):
        super().__init__(parent)
        self._conversa: core.Conversa | None = None
        self._montar()

    # ── construção ───────────────────────
    def _montar(self):
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self._montar_lateral())
        raiz.addWidget(self._montar_vista(), 1)

    def _montar_lateral(self) -> QWidget:
        painel = SidebarPanel()
        titulo = QLabel("Conversa")
        titulo.setObjectName("heading")
        painel.header.addWidget(titulo)

        abrir = primary_button("Abrir exportação", "open")
        abrir.clicked.connect(self._abrir)
        painel.body.addWidget(abrir)
        painel.body.addWidget(subtext(
            "O arquivo que o aplicativo gera em “Exportar conversa”: o "
            "texto (.txt) ou o pacote com as mídias (.zip).", wrap=True))

        painel.body.addWidget(hsep())
        painel.body.addWidget(field_label("IDENTIFICAÇÃO DA PEÇA"))

        painel.body.addWidget(field_label("Procedimento"))
        self._cb_tipo = preparar_procedimento(NoScrollComboBox())
        painel.body.addWidget(self._cb_tipo)

        painel.body.addWidget(field_label("Número do processo"))
        from PyQt6.QtWidgets import QLineEdit
        self._e_processo = QLineEdit()
        self._e_processo.setPlaceholderText("08650.000123/2026-11")
        painel.body.addWidget(self._e_processo)

        painel.body.addWidget(hsep())
        painel.body.addWidget(field_label("RESUMO"))
        self._lbl_resumo = QLabel("Nenhuma conversa aberta.")
        self._lbl_resumo.setObjectName("muted")
        self._lbl_resumo.setWordWrap(True)
        painel.body.addWidget(self._lbl_resumo)
        painel.body.addStretch()

        self._btn_termo = output_button("Gerar termo")
        self._btn_termo.setEnabled(False)
        self._btn_termo.clicked.connect(self._gerar_termo)
        painel.footer.addWidget(self._btn_termo)
        painel.add_note(
            "A peça atesta que a reconstrução corresponde ao arquivo "
            "aberto — não a autenticidade da conversa.")
        return painel

    def _montar_vista(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.addWidget(group_title("Conversa reconstruída"))
        self._vista = QTextBrowser()
        self._vista.setOpenExternalLinks(False)
        self._vista.setStyleSheet(
            f"QTextBrowser {{ background: {PALETTE['bg']}; border: none; }}")
        self._vista.setHtml(
            "<p style='color:%s'>Abra uma exportação de conversa para "
            "reconstruí-la aqui.</p>" % PALETTE["text3"])
        lay.addWidget(self._vista, 1)
        return w

    # ── ações ────────────────────────────
    def _abrir(self):
        curinga = " ".join("*" + e for e in core.FORMATOS)
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Abrir exportação de conversa", "",
            f"Exportação de conversa ({curinga});;Todos os arquivos (*)")
        if not caminho:
            return
        try:
            self._conversa = core.abrir(caminho)
        except Exception as e:                          # noqa: BLE001
            QMessageBox.critical(self, "Não foi possível abrir",
                                 f"{type(e).__name__}: {e}")
            return

        c = self._conversa
        self._vista.setHtml(core.build_html(c, self._declarante(),
                                            self._procedimento()))
        pode = bool(c.mensagens)
        self._btn_termo.setEnabled(pode)
        ini, fim = c.periodo
        periodo = (f"{ini[:10]} a {fim[:10]}" if ini else "—")
        partes = [
            f"<b>{Path(c.origem).name}</b>",
            f"{c.n_mensagens} mensagem(ns)",
            f"{len(c.participantes)} participante(s)",
            f"período: {periodo}",
        ]
        if c.formato == "pacote":
            partes.append(f"{c.n_midias} mídia(s) resumida(s)")
        if c.avisos:
            partes.append("<font color='%s'>%s</font>"
                          % (PALETTE["warning"], "; ".join(c.avisos)))
        self._lbl_resumo.setText("<br>".join(partes))
        self.status_msg.emit(
            f"Conversa aberta: {c.n_mensagens} mensagem(ns)" if pode
            else "Nenhuma mensagem reconhecida no arquivo")

    def _declarante(self) -> core.Declarante:
        from ..perfil import ler
        p = ler()
        return core.Declarante(nome=p.nome, matricula=p.matricula,
                               lotacao=p.lotacao, cargo=p.cargo or "",
                               orgao=p.orgao or "")

    def _procedimento(self) -> core.Procedimento:
        return core.Procedimento(tipo=ler_procedimento(self._cb_tipo),
                                 numero=self._e_processo.text().strip())

    def _gerar_termo(self):
        if self._conversa is None:
            return
        html = core.build_html(self._conversa, self._declarante(),
                               self._procedimento())
        dlg = _TermoConversaDialog(html, self)
        dlg.exec()


class _TermoConversaDialog(QDialog):
    """Mostra o termo, com exportar em PDF e HTML e copiar para o SEI."""

    def __init__(self, html: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Termo de Reconstrução de Conversa")
        from ..widgets import fit_to_screen
        fit_to_screen(self, 820, 780)
        self._html = html

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        visor = QTextBrowser()
        visor.setHtml(html)
        lay.addWidget(visor, 1)

        linha = QHBoxLayout()
        pdf = primary_button("Salvar PDF", "save")
        pdf.clicked.connect(self._salvar_pdf)
        htm = QPushButton("  Salvar HTML")
        htm.setIcon(draw_icon("save", 14, PALETTE["text2"]))
        htm.clicked.connect(self._salvar_html)
        copiar = QPushButton("Copiar para o SEI")
        copiar.clicked.connect(self._copiar)
        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.accept)
        linha.addWidget(pdf)
        linha.addWidget(htm)
        linha.addWidget(copiar)
        linha.addStretch()
        linha.addWidget(fechar)
        lay.addLayout(linha)

    def _salvar_pdf(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo em PDF", "termo-conversa.pdf",
            "PDF (*.pdf)")
        if not caminho:
            return
        if not caminho.lower().endswith(".pdf"):
            caminho += ".pdf"
        from ..impressao import documento_html, preparar_escritor
        from PyQt6.QtGui import QTextDocument
        doc = QTextDocument()
        doc.setHtml(documento_html(self._html, "Reconstrução de Conversa"))
        escritor = preparar_escritor(caminho, "Reconstrução de Conversa")
        doc.print(escritor)
        self._aviso_salvo(caminho)

    def _salvar_html(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo em HTML", "termo-conversa.html",
            "HTML (*.html)")
        if not caminho:
            return
        if not caminho.lower().endswith(".html"):
            caminho += ".html"
        from ..impressao import documento_html
        Path(caminho).write_text(
            documento_html(self._html, "Reconstrução de Conversa"),
            encoding="utf-8")
        self._aviso_salvo(caminho)

    def _copiar(self):
        from ..impressao import limpar_para_sei
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(limpar_para_sei(self._html))
        QMessageBox.information(
            self, "Copiado",
            "O termo foi copiado, pronto para colar no editor do SEI.")

    def _aviso_salvo(self, caminho: str):
        QMessageBox.information(self, "Salvo",
                                f"Termo salvo em:\n{caminho}")
