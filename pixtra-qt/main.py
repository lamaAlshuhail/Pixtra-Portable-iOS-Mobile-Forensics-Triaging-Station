import os
import sys
import time
from typing import Optional

from PyQt6.QtCore import QCoreApplication, Qt, QTimer
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pixtra import api
from pixtra.state import AppState
from pixtra.theme import QSS
from pixtra.widgets.breadcrumb import Breadcrumb
from pixtra.widgets.footer_bar import FooterBar
from pixtra.widgets.header_bar import HeaderBar
from pixtra.widgets.no_case import NoCaseSelected

from pixtra.pages.acquire import AcquirePage
from pixtra.pages.ai_conversations import AIConversationsPage
from pixtra.pages.calendar import CalendarPage
from pixtra.pages.calls import CallsPage
from pixtra.pages.cases import CasesPage
from pixtra.pages.chain_of_custody import ChainOfCustodyPage
from pixtra.pages.checkm8 import Checkm8Page
from pixtra.pages.case_dashboard import CaseDashboardPage
from pixtra.pages.contacts import ContactsPage
from pixtra.pages.devices import DevicesPage
from pixtra.pages.files import FilesPage
from pixtra.pages.home import HomePage
from pixtra.pages.installed_apps import InstalledAppsPage
from pixtra.pages.keychain import KeychainPage
from pixtra.pages.login import LoginPage
from pixtra.pages.messages import MessagesPage
from pixtra.pages.new_case import NewCasePage
from pixtra.pages.photos import PhotosPage
from pixtra.pages.reports import ReportsPage
from pixtra.pages.signup import SignupPage
from pixtra.pages.sim import SimPage
from pixtra.pages.timeline import TimelinePage
from pixtra.pages.users import UsersPage
from pixtra.pages.wallet import WalletPage
from pixtra.pages.web_history import WebHistoryPage
from pixtra.pages.wifi_networks import WifiNetworksPage
from pixtra.services import session as session_svc


_BREADCRUMBS: dict[str, list[tuple[str, str]]] = {
    "dashboard": [("Cases", "cases"), ("{case_name}", "")],
    "sim":       [("Cases", "cases"), ("{case_name}", "dashboard"), ("SIM Extraction", "")],
    "messages":  [("Cases", "cases"), ("{case_name}", "dashboard"), ("Messages", "")],
    "whatsapp":  [("Cases", "cases"), ("{case_name}", "dashboard"), ("WhatsApp", "")],
    "imessage":  [("Cases", "cases"), ("{case_name}", "dashboard"), ("iMessage", "")],
    "sms":       [("Cases", "cases"), ("{case_name}", "dashboard"), ("SMS", "")],
    "instagram": [("Cases", "cases"), ("{case_name}", "dashboard"), ("Instagram", "")],
    "contacts":  [("Cases", "cases"), ("{case_name}", "dashboard"), ("Contacts", "")],
    "calls":     [("Cases", "cases"), ("{case_name}", "dashboard"), ("Calls", "")],
    "web":       [("Cases", "cases"), ("{case_name}", "dashboard"), ("Web History", "")],
    "timeline":  [("Cases", "cases"), ("{case_name}", "dashboard"), ("Timeline", "")],
    "graph":     [("Cases", "cases"), ("{case_name}", "dashboard"), ("Entity Graph", "")],
    "custody":   [("Cases", "cases"), ("{case_name}", "dashboard"), ("Chain of Custody", "")],
    "reports":   [("Cases", "cases"), ("{case_name}", "dashboard"), ("Reports", "")],
    "keychain":  [("Cases", "cases"), ("{case_name}", "dashboard"), ("Keychain", "")],
    "wifi":      [("Cases", "cases"), ("{case_name}", "dashboard"), ("WiFi Networks", "")],
    "photos":    [("Cases", "cases"), ("{case_name}", "dashboard"), ("Photos", "")],
    "files":     [("Cases", "cases"), ("{case_name}", "dashboard"), ("Files", "")],
    "locations": [("Cases", "cases"), ("{case_name}", "dashboard"), ("Locations", "")],
    "wallet":    [("Cases", "cases"), ("{case_name}", "dashboard"), ("Wallet", "")],
    "calendar":  [("Cases", "cases"), ("{case_name}", "dashboard"), ("Calendar", "")],
    "apps":      [("Cases", "cases"), ("{case_name}", "dashboard"), ("Installed Apps", "")],
    "ai_chats":  [("Cases", "cases"), ("{case_name}", "dashboard"), ("AI Conversations", "")],
}


PARENTS = {
    "login": None,
    "signup": "login",
    "home": None,
    "cases": "home",
    "new_case": "cases",
    "dashboard": "cases",
    "devices": "home",
    "checkm8": "home",
    "acquire": "cases",
    "messages": "dashboard",
    "whatsapp": "dashboard",
    "imessage": "dashboard",
    "sms": "dashboard",
    "instagram": "dashboard",
    "contacts": "dashboard",
    "calls": "dashboard",
    "web": "dashboard",
    "timeline": "dashboard",
    "graph": "dashboard",
    "custody": "dashboard",
    "reports": "dashboard",
    "keychain": "dashboard",
    "wifi": "dashboard",
    "photos": "dashboard",
    "files": "dashboard",
    "locations": "dashboard",
    "wallet": "dashboard",
    "calendar": "dashboard",
    "apps": "dashboard",
    "connectivity_pairing": "dashboard",
    "ai_chats": "dashboard",
    "users": "home",
    "sim": "dashboard",
}


def _timed_init(label: str, ctor, *args, **kwargs):
    t0 = time.perf_counter()
    obj = ctor(*args, **kwargs)
    print(f"[init] {label}: {(time.perf_counter() - t0) * 1000:.1f}ms")
    return obj


class PixtraWindow(QMainWindow):
    def __init__(self) -> None:
        _t_init_start = time.perf_counter()
        super().__init__()
        self.state = AppState()
        self.setWindowTitle("Pixtra")
        self.setFixedSize(800, 480)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.header = HeaderBar()
        self.header.home_clicked.connect(lambda: self._navigate("home"))
        self.header.back_clicked.connect(self._go_back)
        self.header.sign_out_requested.connect(self._sign_out)
        self.header.cancel_requested.connect(self._cancel_wizard)
        root_layout.addWidget(self.header)

        self.breadcrumb_strip = QWidget()
        self.breadcrumb_strip.setObjectName("headerBreadcrumbStrip")
        self.breadcrumb_strip.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground, True
        )
        _strip_layout = QHBoxLayout(self.breadcrumb_strip)
        _strip_layout.setContentsMargins(16, 6, 16, 6)
        _strip_layout.setSpacing(0)
        self.breadcrumb = Breadcrumb()
        self.breadcrumb.navigate_requested.connect(
            lambda page_id: self._navigate(page_id) if page_id else None
        )
        _strip_layout.addWidget(self.breadcrumb)
        self.breadcrumb_strip.setVisible(False)
        root_layout.addWidget(self.breadcrumb_strip)

        self.content_host = QWidget()
        self.content_host.setObjectName("mainContent")
        host_layout = QVBoxLayout(self.content_host)
        host_layout.setContentsMargins(12, 12, 12, 12)
        host_layout.setSpacing(0)

        self.stack = QStackedWidget()
        host_layout.addWidget(self.stack)

        root_layout.addWidget(self.content_host, 1)

        self.footer = FooterBar()
        root_layout.addWidget(self.footer)

        self.setCentralWidget(root)

        self._toast_label: Optional[QLabel] = None
        self._current_page_id: Optional[str] = None

        self.login_page = _timed_init("LoginPage", LoginPage)
        self.login_page.authenticated.connect(self._on_authenticated)
        session_svc.signals().session_expired.connect(self._on_session_expired)

        self.signup_page = _timed_init("SignupPage", SignupPage)
        self.signup_page.navigate_requested.connect(self._navigate)

        self.home_page = _timed_init("HomePage", HomePage)
        self.home_page.navigate_requested.connect(self._navigate)

        self.cases_page = _timed_init("CasesPage", CasesPage)
        self.cases_page.case_selected.connect(self._select_case)
        self.cases_page.navigate_requested.connect(self._navigate)
        self.cases_page.toast.connect(self._show_toast)

        self.new_case_page = _timed_init("NewCasePage", NewCasePage)
        self.new_case_page.case_selected.connect(self._select_case)
        self.new_case_page.navigate_requested.connect(self._navigate)
        self.new_case_page.toast.connect(self._show_toast)

        self.dashboard_page = _timed_init(
            "CaseDashboardPage", CaseDashboardPage, self.state
        )
        self.dashboard_page.navigate_requested.connect(self._navigate)
        self.dashboard_page.sim_scan_requested.connect(
            self._navigate_to_sim_scan
        )

        self.devices_page = _timed_init("DevicesPage", DevicesPage)

        self.acquire_page = _timed_init("AcquirePage", AcquirePage, self.state)
        self.acquire_page.navigate_requested.connect(self._navigate)
        self.acquire_page.toast.connect(self._show_toast)

        self.messages_page = _timed_init("MessagesPage", MessagesPage, self.state)
        self.whatsapp_page = _timed_init(
            "MessagesPage(whatsapp)", MessagesPage, self.state, source="whatsapp"
        )
        self.imessage_page = _timed_init(
            "MessagesPage(imessage)", MessagesPage, self.state, source="imessage"
        )
        self.sms_page = _timed_init(
            "MessagesPage(sms)", MessagesPage, self.state, source="sms"
        )
        self.instagram_page = _timed_init(
            "MessagesPage(instagram)", MessagesPage, self.state, source="instagram"
        )
        self.contacts_page = _timed_init("ContactsPage", ContactsPage, self.state)
        self.calls_page = _timed_init("CallsPage", CallsPage, self.state)
        self.web_page = _timed_init("WebHistoryPage", WebHistoryPage, self.state)
        self.timeline_page = _timed_init("TimelinePage", TimelinePage, self.state)
        self.graph_page: Optional[QWidget] = None
        self.locations_page: Optional[QWidget] = None
        self.custody_page = _timed_init(
            "ChainOfCustodyPage", ChainOfCustodyPage, self.state
        )

        self.keychain_page = _timed_init("KeychainPage", KeychainPage, self.state)
        self.wifi_page = _timed_init("WifiNetworksPage", WifiNetworksPage, self.state)
        self.photos_page = _timed_init("PhotosPage", PhotosPage, self.state)
        self.files_page = _timed_init("FilesPage", FilesPage, self.state)
        self.files_page.toast.connect(self._show_toast)
        self.wallet_page = _timed_init("WalletPage", WalletPage, self.state)
        self.calendar_page = _timed_init("CalendarPage", CalendarPage, self.state)
        self.apps_page = _timed_init(
            "InstalledAppsPage", InstalledAppsPage, self.state
        )
        self.ai_chats_page = _timed_init(
            "AIConversationsPage", AIConversationsPage, self.state
        )
        self.users_page = _timed_init("UsersPage", UsersPage, self.state)
        self.users_page.toast.connect(self._show_toast)
        self.sim_page = _timed_init("SimPage", SimPage, self.state)
        self.sim_page.toast.connect(self._show_toast)
        self.sim_page.navigate_requested.connect(self._navigate)

        self.reports_page = _timed_init("ReportsPage", ReportsPage, self.state)
        self.reports_page.toast.connect(self._show_toast)

        self.checkm8_page = _timed_init("Checkm8Page", Checkm8Page)
        self.checkm8_page.toast.connect(self._show_toast)

        self.no_case_placeholder = _timed_init("NoCaseSelected", NoCaseSelected)
        self.no_case_placeholder.go_to_cases.connect(lambda: self._navigate("cases"))

        self._pages: dict[str, tuple[QWidget, bool]] = {
            "login": (self.login_page, False),
            "signup": (self.signup_page, False),
            "home": (self.home_page, False),
            "cases": (self.cases_page, False),
            "new_case": (self.new_case_page, False),
            "dashboard": (self.dashboard_page, True),
            "devices": (self.devices_page, False),
            "acquire": (self.acquire_page, True),
            "messages": (self.messages_page, True),
            "whatsapp": (self.whatsapp_page, True),
            "imessage": (self.imessage_page, True),
            "sms": (self.sms_page, True),
            "instagram": (self.instagram_page, True),
            "contacts": (self.contacts_page, True),
            "calls": (self.calls_page, True),
            "web": (self.web_page, True),
            "timeline": (self.timeline_page, True),
            "custody": (self.custody_page, True),
            "reports": (self.reports_page, True),
            "keychain": (self.keychain_page, True),
            "wifi": (self.wifi_page, True),
            "photos": (self.photos_page, True),
            "files": (self.files_page, True),
            "wallet": (self.wallet_page, True),
            "calendar": (self.calendar_page, True),
            "apps": (self.apps_page, True),
            "ai_chats": (self.ai_chats_page, True),
            "users": (self.users_page, False),
            "sim": (self.sim_page, True),
            "checkm8": (self.checkm8_page, False),
        }

        for page, _ in self._pages.values():
            self.stack.addWidget(page)
        self.stack.addWidget(self.no_case_placeholder)

        self.login_page.show_sign_in()
        self._navigate("login")

        if self.state.case_id:
            self._load_case_data()

        print(
            f"[init] PixtraWindow.__init__ total: "
            f"{(time.perf_counter() - _t_init_start) * 1000:.1f}ms"
        )

    def _navigate(self, page_id: str) -> None:
        if not page_id:
            return
        if page_id == "graph" and self.graph_page is None:
            from pixtra.pages.entity_graph import EntityGraphPage
            self.graph_page = _timed_init(
                "EntityGraphPage(lazy)", EntityGraphPage, self.state
            )
            self.stack.addWidget(self.graph_page)
            self._pages["graph"] = (self.graph_page, True)
        if page_id == "locations" and self.locations_page is None:
            from pixtra.pages.locations import LocationsPage
            self.locations_page = _timed_init(
                "LocationsPage(lazy)", LocationsPage, self.state
            )
            self.stack.addWidget(self.locations_page)
            self._pages["locations"] = (self.locations_page, True)
        if page_id not in self._pages:
            return
        page, requires_case = self._pages[page_id]
        if requires_case and not self.state.case_id:
            self.stack.setCurrentWidget(self.no_case_placeholder)
        else:
            self.stack.setCurrentWidget(page)
            if hasattr(page, "on_show"):
                page.on_show()
        self._current_page_id = page_id
        self.header.set_back_visible(PARENTS.get(page_id) is not None)
        active = self.stack.currentWidget()
        if active is self.no_case_placeholder:
            self._set_breadcrumb([])
            self.header.set_wizard_mode(False)
        else:
            if hasattr(active, "breadcrumb") and isinstance(active.breadcrumb, list):
                self._set_breadcrumb(active.breadcrumb)
            elif page_id in _BREADCRUMBS:
                case_info = self.state.case_info or {}
                case_name = case_info.get("name", "{case_name}")
                if case_info.get("name") is None:
                    print(
                        f"[breadcrumb] {page_id} navigated without case_info loaded"
                    )
                items = [
                    (label.replace("{case_name}", case_name), target)
                    for label, target in _BREADCRUMBS[page_id]
                ]
                self._set_breadcrumb(items)
            else:
                self._set_breadcrumb([])
            self.header.set_wizard_mode(getattr(active, "is_wizard", False))
        self.setFocus()

    def _navigate_to_sim_scan(self, scan_id) -> None:
        mode = "scan" if scan_id is None else "detail"
        self.sim_page.set_mode(mode, scan_id=scan_id)
        self._navigate("sim")

    def _go_back(self) -> None:
        parent = PARENTS.get(self._current_page_id or "")
        if parent:
            self._navigate(parent)

    def _cancel_wizard(self) -> None:
        page = self.stack.currentWidget()
        origin = getattr(page, "wizard_origin", "home")
        self._navigate(origin)

    def _set_breadcrumb(self, items: list[tuple[str, str]]) -> None:
        if not items:
            self.breadcrumb_strip.setVisible(False)
            return
        self.breadcrumb.set_items(items)
        self.breadcrumb_strip.setVisible(True)

    def _on_authenticated(self, examiner: dict) -> None:
        session_svc.set_current_examiner(examiner)
        role = (examiner.get("role") or "").lower()
        if role == "viewer":
            self._show_toast("Read-only session - Viewer role")
        self._navigate("home")
        if self.state.case_id:
            self._load_case_data()

    def _on_session_expired(self) -> None:
        session_svc.clear_token()
        self.state.set_case(None)
        self.login_page.show_sign_in()
        self._navigate("login")
        self._show_toast("Session expired - please sign in again")

    def _sign_out(self) -> None:
        token = session_svc.get_token()
        if token:
            api.run_async(
                api.post,
                on_result=lambda _r: None,
                on_error=lambda _e: None,
                path="/auth/logout",
            )
        session_svc.clear_token()
        self.state.set_case(None)
        self.login_page.show_sign_in()
        self._navigate("login")

    def _select_case(self, case_id: str) -> None:
        self.state.set_case(case_id)
        self._load_case_data()
        self._navigate("dashboard")

    def _clear_case(self) -> None:
        self.state.set_case(None)
        self._navigate("cases")

    def _load_case_data(self) -> None:
        cid = self.state.case_id
        if not cid:
            return

        def _evidence_cb(ev):
            self.state.set_evidence(ev if isinstance(ev, dict) else {})

        api.run_async(
            api.get,
            on_result=_evidence_cb,
            on_error=lambda msg: None,
            path=f"/analysis/evidence/{cid}",
        )
        api.run_async(
            api.get,
            on_result=lambda info: self.state.set_case_info(info),
            on_error=lambda msg: None,
            path=f"/cases/{cid}",
        )

    def _show_toast(self, message: str) -> None:
        self._hide_toast()
        self._toast_label = QLabel(message, self)
        self._toast_label.setObjectName("toast")
        self._toast_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._toast_label.adjustSize()
        geom = self.geometry()
        self._toast_label.move(
            geom.width() - self._toast_label.width() - 16,
            geom.height() - self._toast_label.height() - 16,
        )
        self._toast_label.show()
        QTimer.singleShot(2600, self._hide_toast)

    def _hide_toast(self) -> None:
        if self._toast_label is not None:
            try:
                self._toast_label.deleteLater()
            except RuntimeError:
                pass
            self._toast_label = None


def main() -> int:
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("Pixtra")
    app.setOrganizationName("Pixtra")

    for family in ("Plus Jakarta Sans", "Segoe UI", "Helvetica"):
        if family in QFontDatabase.families():
            break

    app.setStyleSheet(QSS)
    window = PixtraWindow()
    if os.environ.get("PIXTRA_KIOSK"):
        window.showFullScreen()
    else:
        window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
