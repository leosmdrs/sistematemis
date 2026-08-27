"""
Edição de Vídeo — compactar, fatiar e mesclar gravações.

Voltada às gravações que instruem a apuração: videomonitoramento, câmeras
corporais e vídeos anexados pelas partes. Reduz o arquivo para caber na
juntada, recorta o trecho de interesse e junta gravações fragmentadas.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QFrame, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QCheckBox, QButtonGroup, QAbstractItemView, QProgressDialog,
)

from ..icons import draw_icon
from ..theme import PALETTE
from ..widgets import (
    NoScrollComboBox, SidebarPanel, TOOLBAR_HEIGHT, danger_button,
    field_label, group_title, output_button, primary_button, subtext, vsep,
)
from . import derivado_core as derivado
from .derivado_dialogo import TermoDerivadoDialog
from .base import ToolPage, ToolMeta
from . import video_core as core


META = ToolMeta(
    key="video",
    name="Edição de Vídeo",
    icon="tool_video",
    tagline="Compactar, fatiar e mesclar gravações",
    description=(
        "Prepara gravações para a juntada aos autos: reduz o tamanho do "
        "arquivo preservando a legibilidade da cena, recorta o trecho de "
        "interesse e junta gravações fragmentadas em um só arquivo. "
        "Trabalha com videomonitoramento, câmeras corporais e vídeos "
        "anexados pelas partes."
    ),
)

#: (chave, rótulo, ícone, dica)
MODOS = [
    ("compactar", "Compactar", "compress",
     "Reduzir o tamanho do arquivo"),
    ("fatiar", "Fatiar", "scissors",
     "Recortar um trecho do vídeo"),
    ("mesclar", "Mesclar", "merge",
     "Juntar vários vídeos em um só"),
]

COL_N, COL_NOME, COL_DUR, COL_RES, COL_CODEC, COL_TAM, COL_DEL = range(7)

EXTENSOES = ("*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.m4v *.mpg *.mpeg *.ts")


# ─────────────────────────────────────────
#  PROCESSAMENTO EM SEGUNDO PLANO
# ─────────────────────────────────────────

class VideoThread(QThread):
    """Executa uma fila de operações do FFmpeg."""

    etapa = pyqtSignal(int, int, str)      # atual, total, rótulo
    progresso = pyqtSignal(float)          # 0..1 da etapa corrente
    concluido = pyqtSignal(list, list)     # saídas, erros

    def __init__(self, tarefas: list[tuple[list[str], float, str, str]]):
        """`tarefas` = [(comando, duração, rótulo, arquivo_de_saída)]"""
        super().__init__()
        self._tarefas = tarefas
        self._parar = False

    def parar(self):
        self._parar = True

    def run(self):
        saidas, erros = [], []
        total = len(self._tarefas)
        for i, (cmd, duracao, rotulo, saida) in enumerate(self._tarefas, 1):
            if self._parar:
                break
            self.etapa.emit(i, total, rotulo)
            ok, msg = core.executar(
                cmd, duracao,
                progresso=lambda f: self.progresso.emit(f),
                cancelado=lambda: self._parar,
            )
            if ok:
                saidas.append(saida)
            elif msg != "cancelado":
                erros.append(f"{rotulo}: {msg.splitlines()[-1] if msg else 'falhou'}")
        self.concluido.emit(saidas, erros)


# ─────────────────────────────────────────
#  FERRAMENTA
# ─────────────────────────────────────────

class VideoTool(ToolPage):

    meta = META

    def __init__(self, parent=None):
        super().__init__(parent)
        self._videos: list[core.VideoInfo] = []
        self._modo = "compactar"
        self._thread: VideoThread | None = None
        self._tmpdir = tempfile.TemporaryDirectory(prefix="temis-video-")

        self.setAcceptDrops(True)
        self._build_ui()
        self._aplicar_modo("compactar")
        self._checar_ffmpeg()

        QShortcut(QKeySequence("Ctrl+O"), self, self._escolher_arquivos,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

    # ─────────────────────────────────────
    #  UI
    # ─────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        ml.addWidget(self._build_toolbar())
        ml.addWidget(self._build_aviso())
        ml.addWidget(self._build_tabela(), 1)
        root.addWidget(main, 1)

    def _build_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("toolbar_frame")
        frame.setFixedHeight(TOOLBAR_HEIGHT)

        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(6)

        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)
        self._botoes_modo: dict[str, QPushButton] = {}
        for i, (chave, rotulo, icone, dica) in enumerate(MODOS):
            btn = QPushButton(f"  {rotulo}")
            btn.setIcon(draw_icon(icone, 16, PALETTE["text"]))
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setMinimumWidth(112)
            btn.setToolTip(dica)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c, k=chave: self._aplicar_modo(k))
            self._grupo.addButton(btn)
            self._botoes_modo[chave] = btn
            lay.addWidget(btn)

        lay.addWidget(vsep())

        self._btn_limpar = danger_button("Limpar lista")
        self._btn_limpar.clicked.connect(self._limpar)
        self._btn_limpar.setEnabled(False)
        lay.addWidget(self._btn_limpar)

        lay.addWidget(vsep())
        hint = QLabel("Arraste vídeos para esta janela")
        hint.setObjectName("muted")
        lay.addWidget(hint)
        lay.addStretch()

        self._lbl_status = subtext("")
        lay.addWidget(self._lbl_status)
        return frame

    def _build_aviso(self) -> QFrame:
        self._aviso = QFrame()
        self._aviso.setFixedHeight(34)
        self._aviso.setStyleSheet(
            f"background: {PALETTE['surface2']}; "
            f"border-bottom: 1px solid {PALETTE['border']};")
        lay = QHBoxLayout(self._aviso)
        lay.setContentsMargins(16, 0, 16, 0)
        self._lbl_aviso = QLabel("")
        self._lbl_aviso.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self._lbl_aviso)
        lay.addStretch()
        self._aviso.setVisible(False)
        return self._aviso

    def _build_tabela(self) -> QWidget:
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._tabela = QTableWidget(0, 7)
        self._tabela.setHorizontalHeaderLabels(
            ["Nº", "Arquivo", "Duração", "Resolução", "Codec", "Tamanho", ""])
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self._tabela.setStyleSheet(
            f"QTableWidget {{ background: {PALETTE['bg']}; border: none; "
            f"gridline-color: {PALETTE['surface2']}; }}"
            f"QTableWidget::item {{ padding: 6px 8px; }}"
            f"QHeaderView::section {{ background: {PALETTE['surface']}; "
            f"color: {PALETTE['text2']}; padding: 8px; border: none; "
            f"border-bottom: 1px solid {PALETTE['border']}; font-weight: 700; }}"
        )
        self._tabela.itemSelectionChanged.connect(self._selecao_mudou)

        h = self._tabela.horizontalHeader()
        h.setSectionResizeMode(COL_NOME, QHeaderView.ResizeMode.Stretch)
        for col, larg in ((COL_N, 44), (COL_DUR, 92), (COL_RES, 110),
                          (COL_CODEC, 90), (COL_TAM, 96), (COL_DEL, 40)):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self._tabela.setColumnWidth(col, larg)
        lay.addWidget(self._tabela)

        self._vazio = QLabel(
            "Nenhum vídeo carregado.\n\n"
            "Arraste arquivos para cá ou use “Adicionar vídeos…”."
        )
        self._vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._vazio.setStyleSheet(
            f"color: {PALETTE['text3']}; background: {PALETTE['bg']};")
        lay.addWidget(self._vazio, 1)
        self._tabela.setVisible(False)
        return holder

    def _build_sidebar(self) -> SidebarPanel:
        panel = SidebarPanel()

        self._btn_add = primary_button("Adicionar vídeos…")
        self._btn_add.clicked.connect(self._escolher_arquivos)
        panel.header.addWidget(self._btn_add)

        self._lbl_arquivos = subtext("Nenhum vídeo carregado", wrap=True)
        panel.header.addWidget(self._lbl_arquivos)

        panel.body.addWidget(self._painel_compactar())
        panel.body.addWidget(self._painel_fatiar())
        panel.body.addWidget(self._painel_mesclar())
        panel.body.addStretch()

        # O termo depende do resumo criptográfico do arquivo produzido, e
        # esse resumo só existe depois de o arquivo ser gravado. Por isso
        # o botão nasce desligado e acende ao fim do processamento.
        self._btn_termo = output_button("Gerar termo de edição")
        self._btn_termo.setEnabled(False)
        self._btn_termo.setToolTip(
            "Disponível depois de processar — o termo cita os resumos "
            "criptográficos do original e do arquivo produzido")
        self._btn_termo.clicked.connect(self._gerar_termo)
        panel.footer.addWidget(self._btn_termo)

        self._btn_processar = output_button("Processar")
        self._btn_processar.clicked.connect(self._processar)
        self._btn_processar.setEnabled(False)
        panel.footer.addWidget(self._btn_processar)
        panel.add_note("A conversão é local. O vídeo original não é alterado.")
        return panel

    # ── painéis por modo ─────────────────────────
    def _painel_compactar(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        lay.addWidget(group_title("Compactar"))
        lay.addWidget(subtext(
            "Recodifica em H.264. Aplica-se a todos os vídeos da lista.",
            wrap=True))

        lay.addWidget(field_label("Qualidade"))
        self._cb_preset = NoScrollComboBox()
        for p in core.PRESETS:
            self._cb_preset.addItem(p.rotulo, p.chave)
        self._cb_preset.setCurrentIndex(1)
        self._cb_preset.currentIndexChanged.connect(self._preset_mudou)
        lay.addWidget(self._cb_preset)

        self._lbl_preset = subtext("", wrap=True)
        lay.addWidget(self._lbl_preset)

        lay.addWidget(field_label("Resolução"))
        self._cb_escala = NoScrollComboBox()
        for chave, rotulo, _alt in core.ESCALAS:
            self._cb_escala.addItem(rotulo, chave)
        lay.addWidget(self._cb_escala)

        self._chk_sem_audio = QCheckBox("Remover o áudio")
        self._chk_sem_audio.setToolTip(
            "Reduz mais o arquivo, mas descarta a trilha sonora")
        lay.addWidget(self._chk_sem_audio)

        self._box_compactar = box
        return box

    def _painel_fatiar(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        lay.addWidget(group_title("Fatiar"))
        lay.addWidget(subtext(
            "Recorta um trecho do vídeo selecionado na lista.", wrap=True))

        linha = QHBoxLayout()
        linha.setSpacing(8)
        col_i = QVBoxLayout()
        col_i.addWidget(field_label("Início"))
        self._in_inicio = QLineEdit("00:00:00")
        self._in_inicio.setPlaceholderText("hh:mm:ss")
        col_i.addWidget(self._in_inicio)
        linha.addLayout(col_i)

        col_f = QVBoxLayout()
        col_f.addWidget(field_label("Fim"))
        self._in_fim = QLineEdit("")
        self._in_fim.setPlaceholderText("hh:mm:ss")
        col_f.addWidget(self._in_fim)
        linha.addLayout(col_f)
        lay.addLayout(linha)

        self._lbl_trecho = subtext("", wrap=True)
        lay.addWidget(self._lbl_trecho)
        for campo in (self._in_inicio, self._in_fim):
            campo.textChanged.connect(self._atualizar_trecho)

        self._chk_preciso = QCheckBox("Corte preciso (recodifica)")
        self._chk_preciso.setToolTip(
            "Sem isto, o corte encosta no keyframe anterior — é instantâneo "
            "e não perde qualidade, mas pode começar alguns segundos antes")
        lay.addWidget(self._chk_preciso)

        self._box_fatiar = box
        return box

    def _painel_mesclar(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        lay.addWidget(group_title("Mesclar"))
        lay.addWidget(subtext(
            "Junta os vídeos na ordem da lista, de cima para baixo.",
            wrap=True))

        linha = QHBoxLayout()
        linha.setSpacing(6)
        btn_sobe = QPushButton("  Subir")
        btn_sobe.setIcon(draw_icon("chevron_left"))
        btn_sobe.clicked.connect(lambda: self._mover(-1))
        linha.addWidget(btn_sobe)
        btn_desce = QPushButton("  Descer")
        btn_desce.setIcon(draw_icon("chevron_right"))
        btn_desce.clicked.connect(lambda: self._mover(1))
        linha.addWidget(btn_desce)
        lay.addLayout(linha)

        self._lbl_mesclar = subtext("", wrap=True)
        lay.addWidget(self._lbl_mesclar)

        self._box_mesclar = box
        return box

    # ─────────────────────────────────────
    #  MODO
    # ─────────────────────────────────────

    def _aplicar_modo(self, chave: str):
        self._modo = chave
        self._box_compactar.setVisible(chave == "compactar")
        self._box_fatiar.setVisible(chave == "fatiar")
        self._box_mesclar.setVisible(chave == "mesclar")
        self._botoes_modo[chave].setChecked(True)

        rotulo = {"compactar": "Compactar", "fatiar": "Fatiar trecho",
                  "mesclar": "Mesclar vídeos"}[chave]
        self._btn_processar.setText(f"  {rotulo}")
        self._preset_mudou()
        self._atualizar_trecho()
        self._atualizar_estado()

    def _preset_mudou(self):
        p = core.preset_por_chave(self._cb_preset.currentData())
        self._lbl_preset.setText(p.descricao)

    # ─────────────────────────────────────
    #  ARQUIVOS
    # ─────────────────────────────────────

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        caminhos = [u.toLocalFile() for u in ev.mimeData().urls()
                    if u.isLocalFile() and Path(u.toLocalFile()).is_file()]
        if caminhos:
            self._adicionar(caminhos)
            ev.acceptProposedAction()

    def _escolher_arquivos(self):
        caminhos, _ = QFileDialog.getOpenFileNames(
            self, "Adicionar vídeos", "",
            f"Vídeos ({EXTENSOES});;Todos os arquivos (*.*)")
        if caminhos:
            self._adicionar(caminhos)

    def _adicionar(self, caminhos: list[str]):
        if not core.disponivel():
            self._checar_ffmpeg()
            return
        adicionados, falhas = 0, []
        for c in caminhos:
            try:
                self._videos.append(core.sondar(c))
                adicionados += 1
            except Exception as e:
                falhas.append(f"{Path(c).name}: {e}")
        self._recarregar_tabela()
        if falhas:
            QMessageBox.warning(
                self, "Arquivos não reconhecidos",
                "Não foi possível ler:\n\n• " + "\n• ".join(falhas[:8]))
        if adicionados:
            self.status_msg.emit(f"{adicionados} vídeo(s) adicionado(s)")

    def _recarregar_tabela(self):
        self._tabela.setRowCount(len(self._videos))
        for i, v in enumerate(self._videos):
            self._celula(i, COL_N, str(i + 1), Qt.AlignmentFlag.AlignCenter)
            self._celula(i, COL_NOME, v.nome, tooltip=v.caminho)
            self._celula(i, COL_DUR, core.formatar_tempo(v.duracao),
                         Qt.AlignmentFlag.AlignCenter)
            self._celula(i, COL_RES, v.resolucao, Qt.AlignmentFlag.AlignCenter)
            self._celula(i, COL_CODEC, v.codec, Qt.AlignmentFlag.AlignCenter)
            self._celula(i, COL_TAM, core.formatar_tamanho(v.tamanho),
                         Qt.AlignmentFlag.AlignRight)

            btn = QPushButton()
            btn.setIcon(draw_icon("trash", 14, PALETTE["danger"]))
            btn.setToolTip("Remover da lista")
            btn.setFixedSize(28, 24)
            btn.clicked.connect(lambda _c, vid=v: self._remover(vid))
            self._tabela.setCellWidget(i, COL_DEL, btn)

        self._tabela.setVisible(bool(self._videos))
        self._vazio.setVisible(not self._videos)
        n = len(self._videos)
        self._lbl_arquivos.setText(
            "Nenhum vídeo carregado" if n == 0
            else f"{n} vídeo{'s' if n != 1 else ''} na lista")
        self._atualizar_estado()
        self._atualizar_trecho()

    def _celula(self, linha: int, col: int, texto: str, alinhamento=None,
                tooltip: str = ""):
        item = QTableWidgetItem(texto)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        if alinhamento is not None:
            item.setTextAlignment(alinhamento | Qt.AlignmentFlag.AlignVCenter)
        if tooltip:
            item.setToolTip(tooltip)
        self._tabela.setItem(linha, col, item)

    def _remover(self, video: core.VideoInfo):
        if video in self._videos:
            self._videos.remove(video)
            self._recarregar_tabela()

    def _limpar(self):
        self._videos = []
        self._recarregar_tabela()
        self.status_msg.emit("Lista limpa")

    def _mover(self, delta: int):
        i = self._tabela.currentRow()
        j = i + delta
        if i < 0 or not (0 <= j < len(self._videos)):
            return
        self._videos[i], self._videos[j] = self._videos[j], self._videos[i]
        self._recarregar_tabela()
        self._tabela.selectRow(j)

    def _selecionado(self) -> core.VideoInfo | None:
        i = self._tabela.currentRow()
        return self._videos[i] if 0 <= i < len(self._videos) else None

    def _selecao_mudou(self):
        self._atualizar_trecho()
        self._atualizar_estado()

    # ─────────────────────────────────────
    #  ESTADO
    # ─────────────────────────────────────

    def _atualizar_trecho(self):
        v = self._selecionado()
        if self._modo != "fatiar" or v is None:
            self._lbl_trecho.setText("")
            return
        inicio = core.ler_tempo(self._in_inicio.text())
        fim = core.ler_tempo(self._in_fim.text()) or v.duracao
        if fim <= inicio:
            self._lbl_trecho.setText(
                f"<span style='color:{PALETTE['danger']}'>"
                "O fim precisa ser maior que o início.</span>")
            self._lbl_trecho.setTextFormat(Qt.TextFormat.RichText)
            return
        fim = min(fim, v.duracao)
        self._lbl_trecho.setTextFormat(Qt.TextFormat.PlainText)
        self._lbl_trecho.setText(
            f"Trecho de {core.formatar_tempo(fim - inicio)} "
            f"— vídeo tem {core.formatar_tempo(v.duracao)}")

    def _atualizar_estado(self):
        self._btn_limpar.setEnabled(bool(self._videos))
        rodando = bool(self._thread and self._thread.isRunning())
        pronto = core.disponivel() and not rodando

        if self._modo == "mesclar":
            self._atualizar_aviso_mesclar()
            pronto = pronto and len(self._videos) >= 2
        elif self._modo == "fatiar":
            pronto = pronto and self._selecionado() is not None
        else:
            pronto = pronto and bool(self._videos)
        self._btn_processar.setEnabled(pronto)

    def _atualizar_aviso_mesclar(self):
        if len(self._videos) < 2:
            self._lbl_mesclar.setText(
                "Adicione ao menos dois vídeos para mesclar.")
            return
        if core.precisa_recodificar(self._videos):
            self._lbl_mesclar.setText(
                "Os vídeos têm formatos diferentes, então serão "
                "recodificados ao juntar — leva mais tempo.")
        else:
            self._lbl_mesclar.setText(
                "Mesmo formato: a junção é direta, sem recodificar e sem "
                "perda de qualidade.")

    def _checar_ffmpeg(self):
        if core.disponivel():
            self._aviso.setVisible(False)
            return
        self._lbl_aviso.setText(
            f"<span style='color:{PALETTE['danger']};font-weight:600'>"
            "⚠ FFmpeg não encontrado — a edição de vídeo depende dele.</span>"
            f"<span style='color:{PALETTE['text2']}'> &nbsp;Reinstale o "
            "Sistema Têmis ou coloque ffmpeg.exe e ffprobe.exe na pasta "
            "<b>ffmpeg</b>, ao lado do programa.</span>")
        self._aviso.setVisible(True)
        self._btn_processar.setEnabled(False)

    # ─────────────────────────────────────
    #  PROCESSAMENTO
    # ─────────────────────────────────────

    def _processar(self):
        if not core.disponivel():
            self._checar_ffmpeg()
            return
        tarefas = {
            "compactar": self._tarefas_compactar,
            "fatiar": self._tarefas_fatiar,
            "mesclar": self._tarefas_mesclar,
        }[self._modo]()
        if not tarefas:
            return

        self._progresso = QProgressDialog("Preparando…", "Cancelar", 0, 100, self)
        self._progresso.setWindowTitle("Edição de Vídeo")
        self._progresso.setWindowModality(Qt.WindowModality.WindowModal)
        self._progresso.setMinimumDuration(0)
        self._progresso.setAutoClose(False)
        self._progresso.setAutoReset(False)
        self._progresso.setValue(0)
        self._progresso.canceled.connect(self._cancelar)

        self._thread = VideoThread(tarefas)
        self._thread.etapa.connect(self._ao_iniciar_etapa)
        self._thread.progresso.connect(
            lambda f: self._progresso.setValue(int(f * 100)))
        self._thread.concluido.connect(self._ao_concluir)
        self._thread.start()
        self._atualizar_estado()

    def _tarefas_compactar(self) -> list:
        pasta = QFileDialog.getExistingDirectory(
            self, "Pasta de destino dos vídeos compactados")
        if not pasta:
            return []
        preset = core.preset_por_chave(self._cb_preset.currentData())
        chave_escala = self._cb_escala.currentData()
        altura = next(a for c, _r, a in core.ESCALAS if c == chave_escala)
        sem_audio = self._chk_sem_audio.isChecked()

        tarefas = []
        self._derivacoes = []
        for v in self._videos:
            saida = str(Path(pasta) / f"{Path(v.nome).stem}-compactado.mp4")
            tarefas.append((
                core.cmd_compactar(v.caminho, saida, preset, altura,
                                   sem_audio, v.codec_audio),
                v.duracao, v.nome, saida))
            self._derivacoes.append((
                [v.caminho], saida,
                [("Operação", "compactação"),
                 ("Qualidade", preset.rotulo),
                 ("Resolução de saída",
                  self._cb_escala.currentText()),
                 ("Áudio", "removido" if sem_audio else "preservado")]))
        return tarefas

    def _tarefas_fatiar(self) -> list:
        v = self._selecionado()
        if v is None:
            return []
        inicio = core.ler_tempo(self._in_inicio.text())
        fim = core.ler_tempo(self._in_fim.text()) or v.duracao
        if fim <= inicio:
            QMessageBox.warning(self, "Trecho inválido",
                                "O tempo de fim precisa ser maior que o de início.")
            return []
        fim = min(fim, v.duracao)

        sugestao = f"{Path(v.nome).stem}-trecho.mp4"
        saida, _ = QFileDialog.getSaveFileName(
            self, "Salvar trecho", sugestao, "Vídeo MP4 (*.mp4)")
        if not saida:
            return []
        if not saida.lower().endswith(".mp4"):
            saida += ".mp4"
        cmd = core.cmd_fatiar(v.caminho, saida, inicio, fim,
                              self._chk_preciso.isChecked())
        self._derivacoes = [(
            [v.caminho], saida,
            [("Operação", "recorte de trecho"),
             ("Trecho recortado",
              f"de {core.formatar_tempo(inicio)} a "
              f"{core.formatar_tempo(fim)}"),
             ("Duração do trecho", core.formatar_tempo(fim - inicio)),
             ("Duração do original", core.formatar_tempo(v.duracao)),
             ("Corte", "no quadro exato (recodificado)"
              if self._chk_preciso.isChecked()
              else "no quadro-chave mais próximo (sem recodificar)")])]
        return [(cmd, fim - inicio, f"{v.nome} ({core.formatar_tempo(inicio)}"
                 f"–{core.formatar_tempo(fim)})", saida)]

    def _tarefas_mesclar(self) -> list:
        if len(self._videos) < 2:
            return []
        sugestao = f"{Path(self._videos[0].nome).stem}-mesclado.mp4"
        saida, _ = QFileDialog.getSaveFileName(
            self, "Salvar vídeo mesclado", sugestao, "Vídeo MP4 (*.mp4)")
        if not saida:
            return []
        if not saida.lower().endswith(".mp4"):
            saida += ".mp4"

        lista = core.escrever_lista_concat(
            [v.caminho for v in self._videos],
            Path(self._tmpdir.name) / "lista.txt")
        recodificar = core.precisa_recodificar(self._videos)
        duracao = sum(v.duracao for v in self._videos)
        self._derivacoes = [(
            [v.caminho for v in self._videos], saida,
            [("Operação", "mesclagem"),
             ("Arquivos unidos", str(len(self._videos))),
             ("Ordem", " → ".join(v.nome for v in self._videos)),
             ("Duração somada", core.formatar_tempo(duracao)),
             ("Fluxos", "recodificados para compatibilizar"
              if recodificar else "copiados sem recodificação")])]
        return [(core.cmd_mesclar(lista, saida, recodificar), duracao,
                 f"{len(self._videos)} vídeos", saida)]

    #: O que a edição faz ao material, dito na peça. Vídeo editado é
    #: vídeo alterado, e o termo que o acompanha tem de dizer isso com
    #: todas as letras — é o que separa uma peça honesta de uma que
    #: convida à alegação de adulteração.
    RESSALVAS = (
        "O arquivo produzido é resultado de processamento e não é cópia "
        "fiel do original: compactar reduz a qualidade da imagem e do "
        "som; recortar altera a duração e desloca as marcas de tempo; "
        "mesclar reúne gravações que eram distintas num único fluxo "
        "contínuo.",
        "O arquivo original permanece inalterado e deve ser preservado. "
        "Este termo o identifica pelo resumo criptográfico justamente "
        "para que a correspondência entre ele e o material produzido "
        "possa ser conferida a qualquer tempo.",
        "Quando há recorte, a hora que aparece na cena deixa de "
        "corresponder ao tempo decorrido desde o início do arquivo. "
        "Importando a hora dos fatos, ela deve ser buscada no material "
        "original ou consignada expressamente.",
    )

    def _gerar_termo(self):
        produzidas = getattr(self, "_produzidas", [])
        if not produzidas:
            return
        itens = [derivado.medir(origens, saida, detalhes)
                 for origens, saida, detalhes in produzidas]
        operacao = {
            "compactar": "compactação",
            "fatiar": "recorte",
            "mesclar": "mesclagem",
        }.get(self._modo, "edição")
        termo = derivado.TermoDerivado(
            titulo="Termo de Edição de Material Audiovisual",
            operacao=f"{operacao} audiovisual",
            ressalvas=self.RESSALVAS,
            motores=("video",),
            itens=itens)
        TermoDerivadoDialog(termo, self).exec()

    def _ao_iniciar_etapa(self, atual: int, total: int, rotulo: str):
        self._progresso.setLabelText(
            f"{rotulo}\n\nEtapa {atual} de {total}"
            if total > 1 else f"Processando {rotulo}…")
        self._progresso.setValue(0)

    def _cancelar(self):
        if self._thread and self._thread.isRunning():
            self._thread.parar()
            self.status_msg.emit("Cancelando…")

    def _ao_concluir(self, saidas: list, erros: list):
        self._progresso.close()
        self._atualizar_estado()

        if erros:
            QMessageBox.critical(
                self, "Erro no processamento",
                "Não foi possível concluir:\n\n• " + "\n• ".join(erros[:6]))
            return
        if not saidas:
            self.status_msg.emit("Operação cancelada")
            return

        # Só as derivações cujo arquivo de fato saiu: uma etapa que
        # falhou não pode virar linha de termo dizendo que produziu algo.
        self._produzidas = [
            (origens, saida, detalhes)
            for origens, saida, detalhes in getattr(self, "_derivacoes", [])
            if saida in saidas
        ]
        self._btn_termo.setEnabled(bool(self._produzidas))
        self._relatar(saidas)

    def _relatar(self, saidas: list[str]):
        antes = sum(v.tamanho for v in self._videos)
        depois = sum(Path(s).stat().st_size for s in saidas if Path(s).exists())

        linhas = [f"{len(saidas)} arquivo(s) gerado(s) em:",
                  str(Path(saidas[0]).parent), ""]
        cresceu = False
        if self._modo == "compactar" and antes and depois:
            reducao = (1 - depois / antes) * 100
            linhas += [
                f"Tamanho original:  {core.formatar_tamanho(antes)}",
                f"Após a conversão:  {core.formatar_tamanho(depois)}",
                f"Redução: {reducao:.0f}%",
            ]
            cresceu = depois >= antes
            if cresceu:
                # Compactar e sair maior é a ferramenta falhando no seu
                # propósito; calar isso faria o servidor juntar aos autos um
                # arquivo pior que o original achando que o reduziu.
                linhas += [
                    "",
                    "⚠ O resultado NÃO ficou menor que o original.",
                    "O vídeo de origem já está bem compactado. Tente uma "
                    "qualidade menor ou reduza a resolução — ou junte o "
                    "arquivo original mesmo.",
                ]
        else:
            linhas.append(f"Tamanho final: {core.formatar_tamanho(depois)}")

        linhas += ["", "Os arquivos originais não foram alterados.",
                   "Use o Gerador de Hash para registrar o SHA-256 na juntada."]

        if cresceu:
            QMessageBox.warning(self, "Concluído, mas sem redução",
                                "\n".join(linhas))
        else:
            QMessageBox.information(self, "Concluído", "\n".join(linhas))
        self.status_msg.emit(f"{len(saidas)} arquivo(s) gerado(s)")

    # ─────────────────────────────────────
    #  CICLO DE VIDA
    # ─────────────────────────────────────

    def on_activated(self):
        self._checar_ffmpeg()
        n = len(self._videos)
        self.status_msg.emit(
            "Adicione vídeos para editar" if n == 0
            else f"{n} vídeo(s) na lista")

    def can_close(self) -> bool:
        if self._thread and self._thread.isRunning():
            return QMessageBox.question(
                self, "Conversão em andamento",
                "Há uma conversão em andamento. Encerrar mesmo assim?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes
        return True

    def shutdown(self):
        if self._thread and self._thread.isRunning():
            self._thread.parar()
            self._thread.wait(5000)
        self._tmpdir.cleanup()
