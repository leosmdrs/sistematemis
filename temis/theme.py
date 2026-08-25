"""
Identidade visual do Sistema Têmis.

A paleta nasce das cores institucionais da PRF — azul-marinho e dourado.
O tema é escuro por construção: o azul-marinho da PRF (#0A2442) já é uma
cor escura, então usá-lo como superfície deixa a interface mais fiel à
identidade, e não menos. O dourado fica reservado para ação e ênfase.
"""

PALETTE = {
    # Fundos — derivados do azul-marinho institucional
    "bg":        "#061320",   # fundo mais profundo (área de trabalho)
    "surface":   "#0A2442",   # azul-marinho PRF — painéis
    "surface2":  "#123A68",   # elevação (campos, botões)
    "surface3":  "#17457A",   # hover
    "border":    "#1B4B85",

    # Dourado PRF — ação primária e marca
    "gold":      "#FFCC00",
    "gold_h":    "#FFD633",
    "gold_dim":  "#7A6414",

    # Texto
    "text":      "#E8EFF8",
    "text2":     "#93A9C6",
    "text3":     "#5F7594",

    # Semânticas
    "danger":    "#FF5C6E",
    "success":   "#2ECC8A",
    "warning":   "#F5A623",
    "info":      "#4F9BFF",

    # Domínio
    "tarja":     "#000000",
}

# Tipografia base
FONT_STACK = "'Segoe UI', system-ui, sans-serif"
FONT_MONO  = "'Consolas', 'Cascadia Mono', monospace"


def stylesheet() -> str:
    P = PALETTE
    return f"""
QWidget {{
    background: transparent;
    color: {P['text']};
    font-family: {FONT_STACK};
    font-size: 13px;
}}
/* Precisa vir DEPOIS de QWidget: os dois seletores têm a mesma
   especificidade e, no empate, o Qt aplica a última regra — com a ordem
   invertida o 'transparent' acima vencia e os diálogos abriam claros. */
QMainWindow, QDialog, QMessageBox {{
    background: {P['bg']};
}}

/* ── Ladrilhos do portal ─────────────────────────── */
QFrame#tile {{
    background: {P['surface']};
    border: 1px solid {P['border']};
    border-radius: 12px;
}}
QFrame#tile:hover {{
    background: {P['surface2']};
    border: 1px solid {P['gold']};
}}
QFrame#tile_centro {{
    background: {P['gold']};
    border: 2px solid {P['gold_h']};
    border-radius: 14px;
}}
QFrame#tile_centro:hover {{
    background: {P['gold_h']};
    border: 2px solid {P['text']};
}}
QFrame#tile_soon {{
    background: {P['surface']};
    border: 1px dashed {P['border']};
    border-radius: 12px;
}}
QFrame#tile_soon:hover {{
    border: 1px dashed {P['text3']};
}}

/* ── Painéis ─────────────────────────────────────── */
QFrame#sidebar {{
    background: {P['surface']};
    border-right: 1px solid {P['border']};
}}
QFrame#toolbar_frame {{
    background: {P['surface']};
    border-bottom: 1px solid {P['border']};
}}
QFrame#card {{
    background: {P['surface']};
    border: 1px solid {P['border']};
    border-radius: 10px;
}}
QFrame#card:hover {{
    border-color: {P['gold']};
}}

/* ── Rolagem ─────────────────────────────────────── */
QScrollArea {{
    background: {P['bg']};
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {P['border']};
    border-radius: 5px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background: {P['gold_dim']};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {P['border']};
    border-radius: 5px;
    min-width: 32px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {P['gold_dim']};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0; height: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ── Botões ──────────────────────────────────────── */
QPushButton {{
    background: {P['surface2']};
    color: {P['text']};
    border: 1px solid {P['border']};
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {P['surface3']};
    border-color: {P['gold']};
}}
QPushButton:pressed {{
    background: {P['border']};
}}
QPushButton:disabled {{
    background: {P['surface']};
    color: {P['text3']};
    border-color: {P['surface2']};
}}
QPushButton#btn_primary {{
    background: {P['gold']};
    color: #1A1400;
    border: none;
    font-weight: 700;
}}
QPushButton#btn_primary:hover {{
    background: {P['gold_h']};
}}
QPushButton#btn_primary:disabled {{
    background: {P['surface2']};
    color: {P['text3']};
}}
QPushButton#btn_danger {{
    background: transparent;
    color: {P['danger']};
    border: 1px solid {P['danger']};
}}
QPushButton#btn_danger:hover {{
    background: {P['danger']};
    color: white;
}}
QPushButton#btn_bracket {{
    background: transparent;
    color: {P['warning']};
    border: 1px solid {P['warning']};
    font-weight: 600;
}}
QPushButton#btn_bracket:hover {{
    background: {P['warning']};
    color: #1A1000;
}}
QPushButton#btn_bracket:disabled {{
    color: {P['text3']};
    border-color: {P['surface2']};
    background: transparent;
}}
QPushButton#btn_success {{
    background: {P['success']};
    color: #06180F;
    border: none;
    font-weight: 700;
    font-size: 14px;
    padding: 10px 24px;
}}
QPushButton#btn_success:hover {{
    background: #3ADDA0;
}}
QPushButton#btn_success:disabled {{
    background: {P['surface2']};
    color: {P['text3']};
}}

/* ── Campos ──────────────────────────────────────── */
QLineEdit {{
    background: {P['bg']};
    border: 1px solid {P['border']};
    border-radius: 6px;
    padding: 6px 10px;
    color: {P['text']};
    selection-background-color: {P['gold']};
    selection-color: #1A1400;
}}
QLineEdit:focus {{
    border-color: {P['gold']};
}}
QComboBox {{
    background: {P['bg']};
    border: 1px solid {P['border']};
    border-radius: 6px;
    padding: 6px 10px;
    color: {P['text']};
}}
QComboBox:focus {{
    border-color: {P['gold']};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background: {P['surface']};
    border: 1px solid {P['border']};
    selection-background-color: {P['gold']};
    selection-color: #1A1400;
    color: {P['text']};
    outline: none;
}}
QCheckBox {{
    spacing: 8px;
    color: {P['text']};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {P['border']};
    border-radius: 4px;
    background: {P['bg']};
}}
QCheckBox::indicator:checked {{
    background: {P['gold']};
    border-color: {P['gold']};
}}

/* ── Listas e agrupamentos ───────────────────────── */
QListWidget {{
    background: {P['bg']};
    border: 1px solid {P['border']};
    border-radius: 6px;
    color: {P['text']};
    outline: none;
}}
QListWidget::item {{
    padding: 5px 8px;
    border-bottom: 1px solid {P['surface2']};
    font-size: 12px;
}}
QListWidget::item:selected {{
    background: {P['gold']};
    color: #1A1400;
    border-radius: 4px;
}}
QListWidget::item:hover {{
    background: {P['surface2']};
}}

/* ── Tabelas em árvore (resultados da Varredura) ──── */
QTreeWidget, QTreeView {{
    background: {P['bg']};
    alternate-background-color: {P['surface']};
    border: none;
    color: {P['text']};
    outline: none;
    font-size: 12px;
}}
QTreeWidget::item, QTreeView::item {{
    padding: 4px 6px;
    border: none;
}}
QTreeWidget::item:selected, QTreeView::item:selected {{
    background: {P['surface3']};
    color: {P['text']};
}}
QTreeWidget::item:hover, QTreeView::item:hover {{
    background: {P['surface2']};
}}
QHeaderView::section {{
    background: {P['surface']};
    color: {P['text2']};
    border: none;
    border-right: 1px solid {P['border']};
    border-bottom: 1px solid {P['border']};
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.4px;
}}
QHeaderView::section:hover {{
    background: {P['surface2']};
    color: {P['text']};
}}

/* ── Barra de progresso ──────────────────────────── */
QProgressBar {{
    background: {P['surface']};
    border: 1px solid {P['border']};
    border-radius: 4px;
}}
QProgressBar::chunk {{
    background: {P['gold']};
    border-radius: 3px;
}}

QGroupBox {{
    border: 1px solid {P['border']};
    border-radius: 8px;
    margin-top: 14px;
    padding: 18px 10px 10px 10px;
    color: {P['text2']};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    top: -2px;
    padding: 0 6px;
    background: {P['surface']};
}}

/* ── Rótulos nomeados ────────────────────────────── */
QLabel#heading {{
    font-size: 17px;
    font-weight: 700;
    color: {P['text']};
}}
QLabel#subtext {{
    color: {P['text2']};
    font-size: 12px;
}}
QLabel#muted {{
    color: {P['text3']};
    font-size: 11px;
}}
QLabel#page_counter {{
    color: {P['text2']};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#bracket_badge {{
    color: {P['warning']};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#badge_ok {{
    color: {P['success']};
    font-size: 10px;
    font-weight: 700;
}}
QLabel#badge_soon {{
    color: {P['text3']};
    font-size: 10px;
    font-weight: 700;
}}
QLabel#badge_online {{
    color: {P['info']};
    font-size: 10px;
    font-weight: 700;
}}

/* ── Barra de status ─────────────────────────────── */
QStatusBar {{
    background: {P['surface']};
    border-top: 1px solid {P['border']};
    color: {P['text2']};
    font-size: 12px;
    padding: 2px 10px;
}}
QStatusBar::item {{
    border: none;
}}
QToolTip {{
    background: {P['surface2']};
    color: {P['text']};
    border: 1px solid {P['gold']};
    padding: 4px 8px;
    border-radius: 4px;
}}
QProgressDialog {{
    background: {P['surface']};
    color: {P['text']};
}}
QMessageBox {{
    background: {P['surface']};
}}
"""
