from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QWidget

BG_APP = "#F6F6F3"
BG_CARD = "#FFFFFF"
BG_SURFACE = "#EAEAE4"
BG_SURFACE_LIGHT = "#FAFAF8"
BG_SELECTED = "#EDF5EF"
BG_HIGHLIGHT = "#D4EDDF"

GREEN_900 = "#0D2818"
GREEN_800 = "#14432A"
GREEN_700 = "#1B5E3B"
GREEN_600 = "#2A9461"
GREEN_500 = "#3BAF78"
GREEN_400 = "#C2DDCE"
GREEN_300 = "#D4EDDF"
GREEN_200 = "#EDF5EF"

TEXT_PRIMARY = "#1C1C1A"
TEXT_SECONDARY = "#62625F"
TEXT_MUTED = "#7A7A72"
TEXT_LIGHT = "#98988F"
TEXT_DISABLED = "#C0C0B8"
TEXT_ON_GREEN = "#14432A"
TEXT_ON_DARK = "#FFFFFF"

BORDER_DIVIDER = "#E8E8E2"
BORDER_INPUT = "#C8C8C0"
BORDER_LIGHT = "#F0F0EA"

RED_500 = "#C62828"
RED_BG = "#FDECEA"
BLUE_500 = "#1565C0"
BLUE_BG = "#E3F2FD"
ORANGE_500 = "#E65100"
PURPLE_500 = "#6A1B9A"

FONT_FAMILY = '"Plus Jakarta Sans", "Segoe UI", sans-serif'
MONO_FAMILY = '"JetBrains Mono", "Consolas", "Menlo", monospace'

RADIUS_CARD = 18
RADIUS_TILE = 16
RADIUS_PILL = 999
RADIUS_INPUT = 12

SPACING_TILE = 16
TILE_MIN_PX = 120
HEADER_HEIGHT = 56
FOOTER_HEIGHT = 36

GREEN_HEADER = GREEN_700
FOOTER_BG = "#EDEDEA"
FOOTER_TEXT = TEXT_SECONDARY
WORDMARK_COLOR = "#FFFFFF"

TAB_ACTIVE = GREEN_700
TAB_INACTIVE = TEXT_MUTED
TAB_BAR_BORDER = BORDER_DIVIDER


TOUCH_HEIGHT = 44
DANGER = "#A23B2A"
WARNING = "#B8860B"
BORDER_SUBTLE = BORDER_DIVIDER
SURFACE_ALT = BG_SURFACE

CARD_RADIUS_TL = 12
CARD_RADIUS_TR = 12
CARD_RADIUS_BR = 12
CARD_RADIUS_BL = 4

TYPE_XS = 11
TYPE_SM = 12
TYPE_MD = 14
TYPE_LG = 17
TYPE_XL = 22
TYPE_XXL = 28

SP_XS = 4
SP_SM = 8
SP_MD = 12
SP_LG = 16
SP_XL = 24
SP_XXL = 32
SP_XXXL = 48


def apply_card_shadow(widget: "QWidget", *, strong: bool = False) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(28 if strong else 18)
    effect.setOffset(0, 6 if strong else 3)
    effect.setColor(QColor(20, 67, 42, 36 if strong else 28))
    widget.setGraphicsEffect(effect)


QSS = f"""
* {{
    font-family: {FONT_FAMILY};
    color: {TEXT_PRIMARY};
}}

QMainWindow, QWidget#mainContent {{
    background: {BG_APP};
}}


QWidget#sidebar {{
    background: transparent;
    min-width: 160px;
    max-width: 160px;
}}
QLabel#sidebarLogo {{
    color: #FFFFFF;
    font-size: 16px;
    font-weight: 700;
    padding: 10px 12px;
    background: transparent;
    border-bottom: 1px solid rgba(255,255,255,0.10);
}}
QFrame#sidebarDivider {{
    background: rgba(255,255,255,0.10);
    max-height: 1px;
    min-height: 1px;
    margin: 4px 12px;
    border: none;
}}
QFrame#sidebarItem {{
    background: transparent;
    border-left: 3px solid transparent;
    padding: 0px;
}}
QFrame#sidebarItem:hover {{
    background: rgba(255,255,255,0.08);
}}
QFrame#sidebarItem[active="true"] {{
    background: rgba(255,255,255,0.12);
    border-left: 3px solid {GREEN_500};
}}
QFrame#sidebarItem[disabled="true"] {{
    background: transparent;
}}
QLabel#sidebarItemText {{
    color: rgba(255,255,255,0.65);
    font-size: 12px;
    font-weight: 500;
    background: transparent;
}}
QFrame#sidebarItem[active="true"] QLabel#sidebarItemText {{
    color: #FFFFFF;
    font-weight: 600;
}}
QFrame#sidebarItem[disabled="true"] QLabel#sidebarItemText {{
    color: rgba(255,255,255,0.30);
}}
QLabel#sidebarBadge {{
    color: #FFFFFF;
    background: {GREEN_700};
    font-size: 10px;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 0px;
}}
QLabel#sidebarFooter {{
    color: rgba(255,255,255,0.35);
    font-size: 10px;
    padding: 8px 12px;
    background: transparent;
}}


QWidget#header {{
    background: {BG_CARD};
    border-bottom: 1px solid {BORDER_DIVIDER};
    min-height: 44px;
    max-height: 44px;
}}
QLabel#headerTitle {{
    font-size: 14px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
}}
QFrame#headerCaseBar {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER_DIVIDER};
    border-radius: 0px;
    padding: 2px 6px 2px 10px;
}}
QFrame#headerCaseBar QLabel {{
    background: transparent;
    font-size: 11px;
    color: {TEXT_SECONDARY};
}}
QLabel#headerCaseNumber {{
    color: {TEXT_PRIMARY} !important;
    font-weight: 700;
    font-family: {MONO_FAMILY};
}}
QFrame#headerNoCase {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER_DIVIDER};
    border-radius: 0px;
    padding: 4px 10px;
}}
QFrame#headerNoCase QLabel {{
    background: transparent;
    font-size: 11px;
    color: {TEXT_MUTED};
}}


QScrollArea#contentArea {{
    background: {BG_APP};
    border: none;
}}
QScrollArea#contentArea > QWidget > QWidget {{
    background: {BG_APP};
}}


QFrame#card {{
    background: {BG_CARD};
    border: 1px solid {BORDER_DIVIDER};
    border-radius: 0px;
}}
QLabel#cardTitle {{
    font-size: 13px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
    background: transparent;
}}


QPushButton {{
    padding: 8px 16px;
    border-radius: 0px;
    font-size: 13px;
    font-weight: 600;
    min-height: 20px;
    border: 1px solid {BORDER_INPUT};
    background: {BG_CARD};
    color: {TEXT_PRIMARY};
}}
QPushButton:hover {{
    background: {BG_SURFACE};
}}
QPushButton#btnPrimary {{
    background: {GREEN_700};
    color: #FFFFFF;
    border: 1px solid {GREEN_800};
}}
QPushButton#btnPrimary:hover {{
    background: {GREEN_800};
}}
QPushButton#btnPrimary:disabled {{
    background: {BORDER_INPUT};
    color: {TEXT_LIGHT};
    border: 1px solid {BORDER_DIVIDER};
}}
QPushButton#btnSecondary {{
    background: {BG_SURFACE};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER_DIVIDER};
}}
QPushButton#btnSecondary:hover {{
    background: {BORDER_DIVIDER};
}}
QPushButton#btnSm {{
    padding: 5px 10px;
    font-size: 12px;
    min-height: 16px;
}}
QPushButton#btnGhost {{
    background: transparent;
    color: {TEXT_MUTED};
    border: none;
}}
QPushButton#btnGhost:hover {{
    background: {BG_SURFACE};
}}
QPushButton#btnIcon {{
    background: transparent;
    padding: 2px;
    min-height: 24px;
    min-width: 24px;
    border: none;
    border-radius: 0px;
}}
QPushButton#btnIcon:hover {{
    background: {BORDER_DIVIDER};
}}


QLineEdit, QTextEdit, QPlainTextEdit {{
    background: {BG_CARD};
    border: 1px solid {BORDER_INPUT};
    border-radius: 0px;
    padding: 8px 10px;
    font-size: 13px;
    color: {TEXT_PRIMARY};
    min-height: 20px;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {GREEN_600};
}}
QLineEdit#mono {{
    font-family: {MONO_FAMILY};
}}
QLabel#formLabel {{
    font-size: 11px;
    font-weight: 600;
    color: {TEXT_MUTED};
    background: transparent;
}}


QTableView, QTableWidget {{
    background: {BG_CARD};
    alternate-background-color: {BG_SURFACE_LIGHT};
    gridline-color: {BORDER_LIGHT};
    border: 1px solid {BORDER_DIVIDER};
    border-radius: 0px;
    font-size: 13px;
    selection-background-color: {BG_SELECTED};
    selection-color: {TEXT_PRIMARY};
}}
QTableView::item, QTableWidget::item {{
    padding: 6px 8px;
    border: none;
}}
QHeaderView::section {{
    background: {BG_SURFACE_LIGHT};
    color: {TEXT_MUTED};
    font-size: 11px;
    font-weight: 700;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid {BORDER_DIVIDER};
    border-right: 1px solid {BORDER_LIGHT};
}}


QListWidget {{
    background: {BG_APP};
    border: none;
    outline: 0;
}}
QListWidget::item {{
    background: {BG_CARD};
    border-bottom: 1px solid {BORDER_DIVIDER};
    border-radius: 0px;
    padding: 8px 10px;
    margin-bottom: 0px;
    color: {TEXT_PRIMARY};
}}
QListWidget::item:selected {{
    background: {BG_SELECTED};
    color: {TEXT_PRIMARY};
}}
QListWidget::item:hover {{
    background: {BG_SELECTED};
}}


QLabel#badgeGreen {{
    background: {BG_HIGHLIGHT};
    color: {TEXT_ON_GREEN};
    font-size: 10px;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: 0px;
}}
QLabel#badgeRed {{
    background: {RED_BG};
    color: {RED_500};
    font-size: 10px;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: 0px;
}}
QLabel#badgeBlue {{
    background: {BLUE_BG};
    color: {BLUE_500};
    font-size: 10px;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: 0px;
}}
QLabel#badgeGray {{
    background: {BG_SURFACE};
    color: {TEXT_SECONDARY};
    font-size: 10px;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: 0px;
}}


QFrame#statCard {{
    background: {BG_CARD};
    border: 1px solid {BORDER_DIVIDER};
    border-radius: 0px;
}}
QLabel#statLabel {{
    font-size: 10px;
    font-weight: 600;
    color: {TEXT_MUTED};
    background: transparent;
}}
QLabel#statValue {{
    font-size: 24px;
    font-weight: 800;
    color: {GREEN_900};
    background: transparent;
}}
QLabel#statSub {{
    font-size: 10px;
    color: {TEXT_LIGHT};
    background: transparent;
}}


QPushButton#segBtn {{
    background: transparent;
    color: {TEXT_MUTED};
    border-radius: 0px;
    border: none;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 500;
    min-height: 18px;
}}
QPushButton#segBtn:checked {{
    background: {BG_CARD};
    color: {TEXT_PRIMARY};
    font-weight: 600;
    border: 1px solid {BORDER_DIVIDER};
}}
QFrame#segGroup {{
    background: {BG_SURFACE};
    border-radius: 0px;
    border: 1px solid {BORDER_DIVIDER};
    padding: 1px;
}}


QLabel#mono {{
    font-family: {MONO_FAMILY};
    font-size: 12px;
    color: {TEXT_SECONDARY};
    background: transparent;
}}
QLabel#monoSm {{
    font-family: {MONO_FAMILY};
    font-size: 11px;
    color: {TEXT_LIGHT};
    background: transparent;
}}
QLabel#mutedText {{
    color: {TEXT_MUTED};
    font-size: 12px;
    background: transparent;
}}
QLabel#subtle {{
    color: {TEXT_LIGHT};
    font-size: 11px;
    background: transparent;
}}
QProgressBar {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER_DIVIDER};
    border-radius: 0px;
    max-height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {GREEN_600};
    border-radius: 0px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_INPUT};
    border-radius: 0px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_INPUT};
    border-radius: 0px;
}}


QLabel#toast {{
    background: {GREEN_900};
    color: #FFFFFF;
    padding: 8px 14px;
    border-radius: 0px;
    border: 1px solid {GREEN_800};
    font-size: 12px;
    font-weight: 500;
}}


QWidget#headerBar {{

    background: transparent;
}}
QWidget#headerTopStrip {{

    background: {GREEN_HEADER};
}}
QWidget#headerBreadcrumbStrip {{

    background: {BG_CARD};
    border-bottom: 1px solid {BORDER_DIVIDER};
}}
QLabel#rolePill {{

    color: #FFFFFF;
    font-size: 10px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 8px;
    background: rgba(27, 94, 59, 1.0);
}}
QLabel#rolePill[role="supervisor"] {{
    background: rgba(27, 94, 59, 1.0);
}}
QLabel#rolePill[role="examiner"] {{
    background: rgba(27, 94, 59, 0.6);
}}
QLabel#rolePill[role="viewer"] {{
    background: rgba(27, 94, 59, 0.3);
}}
QPushButton#wizardCancelBtn {{

    background: transparent;
    color: {DANGER};
    border: none;
    font-size: 12px;
    font-weight: 700;
    padding: 4px 10px;
}}
QPushButton#wizardCancelBtn:hover {{
    text-decoration: underline;
}}
QLabel#listRowBadge {{

    font-family: {MONO_FAMILY};
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 9px;
    background: transparent;
    color: {TEXT_PRIMARY};
}}
QLabel#listRowBadge[variant="active"] {{
    background: {GREEN_700};
    color: #FFFFFF;
}}
QLabel#listRowBadge[variant="muted"] {{
    background: {BG_SURFACE};
    color: {TEXT_MUTED};
}}
QLabel#listRowBadge[variant="danger"] {{
    background: {DANGER};
    color: #FFFFFF;
}}
QLabel#wordmark {{
    color: {WORDMARK_COLOR};
    font-size: 20px;
    font-weight: 800;
    letter-spacing: 0.5px;
    background: transparent;
    padding: 0;
    margin: 0;
}}
QPushButton#backChevron {{
    background: transparent;
    border: none;
    color: {WORDMARK_COLOR};
    padding: 4px;
    min-width: 32px;
    min-height: 32px;
    border-radius: 16px;
}}
QPushButton#backChevron:hover {{
    background: rgba(255,255,255,0.12);
}}
QPushButton#wordmarkBtn {{
    background: transparent;
    border: none;
    padding: 0px;
    min-height: {HEADER_HEIGHT - 16}px;
}}
QPushButton#wordmarkBtn:hover {{
    background: rgba(255,255,255,0.06);
}}

QWidget#footerBar {{
    background: {FOOTER_BG};
    min-height: {FOOTER_HEIGHT}px;
    max-height: {FOOTER_HEIGHT}px;
    border-top: 1px solid {BORDER_DIVIDER};
}}
QLabel#footerText {{
    color: {FOOTER_TEXT};
    font-size: 12px;
    font-weight: 500;
    background: transparent;
    font-family: {MONO_FAMILY};
}}

QPushButton#tile {{
    background: {BG_CARD};
    border: 1px solid {BORDER_LIGHT};
    border-radius: {RADIUS_TILE}px;
    color: {TEXT_PRIMARY};
    font-size: 13px;
    font-weight: 600;
    padding: 12px;
    text-align: center;
    min-width: {TILE_MIN_PX}px;
    min-height: {TILE_MIN_PX}px;
}}
QPushButton#tile:hover {{
    background: {BG_SURFACE_LIGHT};
    border: 1px solid {GREEN_400};
    border-left: 3px solid {GREEN_700};
}}
QPushButton#tile:pressed {{
    background: {GREEN_200};
}}
QPushButton#tileDisabled {{
    background: {BG_SURFACE_LIGHT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: {RADIUS_TILE}px;
    color: {TEXT_DISABLED};
    font-size: 13px;
    font-weight: 600;
    padding: 12px;
    min-width: {TILE_MIN_PX}px;
    min-height: {TILE_MIN_PX}px;
}}
QLabel#tileLabel {{
    color: {TEXT_PRIMARY};
    font-size: 13px;
    font-weight: 600;
    background: transparent;
}}
QLabel#tileLabelDisabled {{
    color: {TEXT_DISABLED};
    font-size: 13px;
    font-weight: 600;
    background: transparent;
}}
QLabel#tileBadge {{
    color: {TEXT_ON_GREEN};
    background: {GREEN_300};
    font-family: {MONO_FAMILY};
    font-size: 11px;
    font-weight: 700;
    padding: 1px 8px;
    border-radius: 9px;
}}
QLabel#tileBadgeMuted {{
    color: {TEXT_MUTED};
    background: {BG_SURFACE};
    font-family: {MONO_FAMILY};
    font-size: 11px;
    font-weight: 700;
    padding: 1px 8px;
    border-radius: 9px;
}}
QLabel#tileSection {{
    color: {TEXT_MUTED};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    text-transform: uppercase;
    background: transparent;
    padding: 4px 2px;
}}

QFrame#caseCard {{
    background: {BG_CARD};
    border: 1px solid {BORDER_LIGHT};
    border-radius: {RADIUS_CARD}px;
    padding: 14px 18px;
}}
QFrame#caseCard:hover {{
    border: 1px solid {GREEN_400};
    background: {BG_SURFACE_LIGHT};
}}
QLabel#caseCardNumber {{
    color: {GREEN_700};
    font-size: 12px;
    font-weight: 700;
    font-family: {MONO_FAMILY};
    background: transparent;
}}
QLabel#caseCardName {{
    color: {TEXT_PRIMARY};
    font-size: 16px;
    font-weight: 700;
    background: transparent;
}}
QLabel#caseCardMeta {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
    background: transparent;
}}

QFrame#statCardLg {{
    background: {BG_CARD};
    border: 1px solid {BORDER_LIGHT};
    border-radius: {RADIUS_CARD}px;
    padding: 14px 18px;
}}
QLabel#statCardLgValue {{
    color: {GREEN_900};
    font-size: 22px;
    font-weight: 800;
    background: transparent;
}}
QLabel#statCardLgLabel {{
    color: {TEXT_MUTED};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.4px;
    text-transform: uppercase;
    background: transparent;
}}

QPushButton#pillCreate {{
    background: {GREEN_700};
    color: #FFFFFF;
    border: none;
    border-radius: {RADIUS_PILL}px;
    padding: 10px 22px;
    font-size: 13px;
    font-weight: 700;
    min-height: 36px;
}}
QPushButton#pillCreate:hover {{
    background: {GREEN_800};
}}
QPushButton#pillCreate:pressed {{
    background: {GREEN_900};
}}
QPushButton#pillSecondary {{
    background: {BG_CARD};
    color: {GREEN_700};
    border: 1px solid {GREEN_700};
    border-radius: {RADIUS_PILL}px;
    padding: 10px 22px;
    font-size: 13px;
    font-weight: 700;
    min-height: 36px;
}}
QPushButton#pillSecondary:hover {{
    background: {GREEN_200};
}}

QPushButton#chipFilter {{
    background: {BG_CARD};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER_DIVIDER};
    border-radius: {RADIUS_PILL}px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: 600;
    min-height: 24px;
}}
QPushButton#chipFilter:hover {{
    background: {BG_SURFACE_LIGHT};
}}
QPushButton#chipFilter:checked {{
    background: {GREEN_700};
    color: #FFFFFF;
    border: 1px solid {GREEN_800};
}}

QFrame#roundCard {{
    background: {BG_CARD};
    border: 1px solid {BORDER_LIGHT};
    border-radius: {RADIUS_CARD}px;
    padding: 18px;
}}
QFrame#greenCard {{
    background: {GREEN_700};
    border: 1px solid {GREEN_800};
    border-radius: {RADIUS_CARD}px;
    padding: 22px;
}}
QFrame#greenCard QLabel {{
    color: #FFFFFF;
    background: transparent;
}}
QLineEdit#inputRound, QTextEdit#inputRound {{
    background: {BG_CARD};
    border: 1px solid {BORDER_INPUT};
    border-radius: {RADIUS_INPUT}px;
    padding: 10px 14px;
    font-size: 13px;
    color: {TEXT_PRIMARY};
    min-height: 24px;
}}
QLineEdit#inputRound:focus, QTextEdit#inputRound:focus {{
    border: 1px solid {GREEN_600};
}}
QLineEdit#inputRoundOnGreen {{
    background: {BG_CARD};
    border: 1px solid {GREEN_500};
    border-radius: {RADIUS_INPUT}px;
    padding: 10px 14px;
    font-size: 13px;
    color: {TEXT_PRIMARY};
    min-height: 24px;
}}
QComboBox#driveCombo {{
    background: {BG_CARD};
    border: 1px solid {BORDER_INPUT};
    border-radius: {RADIUS_INPUT}px;
    padding: 8px 12px;
    font-size: 13px;
    min-height: 24px;
}}
QTableWidget#manifestTable {{
    background: {BG_CARD};
    border: 1px solid {BORDER_LIGHT};
    border-radius: {RADIUS_CARD}px;
    gridline-color: {BORDER_LIGHT};
    font-size: 12px;
    font-family: {MONO_FAMILY};
}}
QTableWidget#manifestTable::item {{
    padding: 8px 10px;
}}

QWidget#tabBar {{
    background: transparent;
    border-bottom: 1px solid {TAB_BAR_BORDER};
}}
QPushButton#tabInactive {{
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: {TAB_INACTIVE};
    font-size: 13px;
    font-weight: 600;
    padding: 8px 14px;
    min-height: 28px;
}}
QPushButton#tabInactive:hover {{
    color: {TEXT_PRIMARY};
}}
QPushButton#tabActive {{
    background: transparent;
    border: none;
    border-bottom: 2px solid {TAB_ACTIVE};
    color: {TAB_ACTIVE};
    font-size: 13px;
    font-weight: 700;
    padding: 8px 14px;
    min-height: 28px;
}}
"""
