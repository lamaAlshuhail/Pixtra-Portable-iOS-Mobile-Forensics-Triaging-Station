import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from ..format import fmt_bytes
from ..hashing import build_manifest, write_manifest
from ..touch import enable_touch_scroll

STEPS = [
    "Prerequisites",
    "Connect Device",
    "Enter DFU Mode",
    "Run Exploit",
    "Extract Filesystem",
]

EXTRACT_DEFAULT_ROOT = Path(os.environ.get("PIXTRA_EXTRACT_ROOT", "/var/lib/pixtra/extractions"))

CHECKRA1N_PATH = os.environ.get(
    "PIXTRA_CHECKRA1N", os.path.expanduser("~/checkra1n")
)

EXTRACT_FILES = [
    ("/var/Keychains/keychain-2.db", "keychain-2.db"),
    ("/var/mobile/Library/SMS/sms.db", "sms.db"),
    ("/var/mobile/Library/AddressBook/AddressBook.sqlitedb", "AddressBook.sqlitedb"),
    ("/var/mobile/Library/CallHistoryDB/CallHistory.storedata", "CallHistory.storedata"),
    ("/var/mobile/Library/Safari/History.db", "History.db"),
]


class Checkm8Worker(QThread):
    log_line = pyqtSignal(str)
    step_started = pyqtSignal(int)
    step_complete = pyqtSignal(int, bool)
    file_result = pyqtSignal(str, str, int)
    manifest_ready = pyqtSignal(str, str)
    all_done = pyqtSignal(bool)

    def __init__(self, output_dir: Path) -> None:
        super().__init__()
        self.output_dir = Path(output_dir)
        self._stop = False
        self._iproxy: Optional[subprocess.Popen] = None

    def request_stop(self) -> None:
        self._stop = True
        self._kill_iproxy()

    def _kill_iproxy(self) -> None:
        if self._iproxy and self._iproxy.poll() is None:
            try:
                self._iproxy.terminate()
                self._iproxy.wait(timeout=3)
            except Exception:
                try:
                    self._iproxy.kill()
                except Exception:
                    pass

    def run(self) -> None:
        try:
            self.step_started.emit(3)
            ok = self._run_exploit()
            self.step_complete.emit(3, ok)
            if not ok:
                self.all_done.emit(False)
                return

            self.step_started.emit(4)
            if not self._start_tunnel():
                self.step_complete.emit(4, False)
                self.all_done.emit(False)
                return
            if not self._wait_for_ssh():
                self.step_complete.emit(4, False)
                self.all_done.emit(False)
                return

            self.output_dir.mkdir(parents=True, exist_ok=True)
            extracted = self._extract_files()
            if extracted == 0:
                self.step_complete.emit(4, False)
                self.all_done.emit(False)
                return

            self._hash_and_manifest()
            self.step_complete.emit(4, True)
            self.all_done.emit(True)
        finally:
            self._kill_iproxy()

    def _run_exploit(self) -> bool:
        cmd = ["sudo", CHECKRA1N_PATH, "-c"]
        self.log_line.emit("$ " + " ".join(shlex.quote(c) for c in cmd))
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=180, text=True)
        except FileNotFoundError:
            self.log_line.emit(f"error: checkra1n not found at {CHECKRA1N_PATH}")
            return False
        except subprocess.TimeoutExpired:
            self.log_line.emit("error: checkra1n timed out (180s)")
            return False
        except Exception as exc:
            self.log_line.emit(f"error: {exc}")
            return False
        for line in (r.stdout or "").splitlines()[-20:]:
            self.log_line.emit(line)
        if r.returncode != 0:
            self.log_line.emit(f"checkra1n exit {r.returncode}: {(r.stderr or '').strip()[:200]}")
            return False
        self.log_line.emit("checkra1n: exploit delivered")
        return True

    def _start_tunnel(self) -> bool:
        self.log_line.emit("$ iproxy 2222 44")
        try:
            self._iproxy = subprocess.Popen(
                ["iproxy", "2222", "44"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            self.log_line.emit("error: iproxy missing (apt install libusbmuxd-tools)")
            return False
        except Exception as exc:
            self.log_line.emit(f"error: {exc}")
            return False
        self.log_line.emit("iproxy listening on :2222")
        return True

    def _wait_for_ssh(self) -> bool:
        self.log_line.emit("waiting for SSH on :2222...")
        for attempt in range(1, 31):
            if self._stop:
                return False
            try:
                r = subprocess.run(
                    [
                        "sshpass", "-p", "alpine",
                        "ssh", "-p", "2222",
                        "-o", "StrictHostKeyChecking=no",
                        "-o", "UserKnownHostsFile=/dev/null",
                        "-o", "ConnectTimeout=2",
                        "root@localhost", "echo ok",
                    ],
                    capture_output=True, timeout=5, text=True,
                )
            except FileNotFoundError:
                self.log_line.emit("error: sshpass missing (apt install sshpass)")
                return False
            except Exception:
                r = None
            if r is not None and r.returncode == 0 and "ok" in (r.stdout or ""):
                self.log_line.emit(f"SSH ready after {attempt}s")
                return True
            time.sleep(1)
        self.log_line.emit("SSH timeout after 30s")
        return False

    def _extract_files(self) -> int:
        count = 0
        for remote, local in EXTRACT_FILES:
            if self._stop:
                break
            dest = self.output_dir / local
            self.log_line.emit(f"scp {remote} -> {dest.name}")
            try:
                r = subprocess.run(
                    [
                        "sshpass", "-p", "alpine",
                        "scp", "-O", "-P", "2222",
                        "-o", "StrictHostKeyChecking=no",
                        "-o", "UserKnownHostsFile=/dev/null",
                        f"root@localhost:{remote}", str(dest),
                    ],
                    capture_output=True, timeout=90, text=True,
                )
            except Exception as exc:
                self.file_result.emit(local, f"error: {exc}", 0)
                continue
            if r.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
                size = dest.stat().st_size
                self.file_result.emit(local, "extracted", size)
                count += 1
            else:
                err = (r.stderr or "").lower()
                if "no such" in err or "not found" in err:
                    status = "not found"
                elif "permission" in err or "denied" in err:
                    status = "locked"
                else:
                    status = "failed"
                self.file_result.emit(local, status, 0)
        return count

    def _hash_and_manifest(self) -> None:
        self.log_line.emit("computing SHA-256 manifest...")
        files = [p for p in self.output_dir.iterdir() if p.is_file()]
        manifest = build_manifest(files, self.output_dir)
        manifest_path = self.output_dir / "manifest.sha256.json"
        digest = write_manifest(manifest, manifest_path)
        self.log_line.emit(f"manifest: {len(manifest)} files, sha256={digest[:12]}...")
        self.manifest_ready.emit(str(manifest_path), digest)


class Checkm8Page(QWidget):
    toast = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_step = 0
        self._running = False
        self._step_cards: list[QFrame] = []
        self._file_rows: dict[str, QLabel] = {}
        self._worker: Optional[Checkm8Worker] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("contentArea")
        enable_touch_scroll(scroll)
        steps_container = QWidget()
        steps_layout = QVBoxLayout(steps_container)
        steps_layout.setContentsMargins(0, 0, 0, 0)
        steps_layout.setSpacing(6)

        for i, title in enumerate(STEPS):
            card = self._step_card(i, title)
            self._step_cards.append(card)
            steps_layout.addWidget(card)

        self.results_card = QFrame()
        self.results_card.setObjectName("card")
        rc = QVBoxLayout(self.results_card)
        rc.setContentsMargins(14, 12, 14, 12)
        rc.setSpacing(4)
        rc_title = QLabel("Extracted Files")
        rc_title.setObjectName("cardTitle")
        rc.addWidget(rc_title)
        for _, local in EXTRACT_FILES:
            row = QHBoxLayout()
            name_lbl = QLabel(local)
            name_lbl.setStyleSheet("font-size: 12px; background: transparent;")
            row.addWidget(name_lbl, 1)
            status_lbl = QLabel(" - ")
            status_lbl.setObjectName("monoSm")
            row.addWidget(status_lbl)
            rc.addLayout(row)
            self._file_rows[local] = status_lbl
        self.results_card.setVisible(False)
        steps_layout.addWidget(self.results_card)

        self.log_card = QFrame()
        self.log_card.setObjectName("card")
        lc = QVBoxLayout(self.log_card)
        lc.setContentsMargins(14, 12, 14, 12)
        lc.setSpacing(4)
        lc_title = QLabel("Log")
        lc_title.setObjectName("cardTitle")
        lc.addWidget(lc_title)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(140)
        self.log_view.setStyleSheet(
            "background: #0D2818; color: #C2DDCE; font-family: 'JetBrains Mono','Consolas',monospace; font-size: 11px; border: none;"
        )
        lc.addWidget(self.log_view)
        self.log_card.setVisible(False)
        steps_layout.addWidget(self.log_card)

        steps_layout.addStretch()
        scroll.setWidget(steps_container)
        root.addWidget(scroll, 1)

        nav = QHBoxLayout()
        self.back_btn = QPushButton("  Back")
        self.back_btn.setObjectName("btnSecondary")
        self.back_btn.setIcon(icons.qicon("chevron_left", size=14, color="#62625F"))
        self.back_btn.setIconSize(icons.icon_size(14))
        self.back_btn.clicked.connect(self._back)
        nav.addWidget(self.back_btn)

        self.next_btn = QPushButton("Next Step  ")
        self.next_btn.setObjectName("btnPrimary")
        self.next_btn.setIcon(icons.qicon("chevron_right", size=14, color="#FFFFFF"))
        self.next_btn.setIconSize(icons.icon_size(14))
        self.next_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.next_btn.clicked.connect(self._next)
        nav.addWidget(self.next_btn)

        root.addLayout(nav)

        self._refresh_cards()

    def _step_card(self, index: int, title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(10)
        dot = QLabel(str(index + 1))
        dot.setFixedSize(28, 28)
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dot.setStyleSheet(
            "background: #EAEAE4; color: #7A7A72;"
            " font-size: 12px; font-weight: 700;"
        )
        head.addWidget(dot)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 700; background: transparent;")
        head.addWidget(title_lbl)
        head.addStretch()
        layout.addLayout(head)

        if index == 3:
            self.run_btn = QPushButton("  Run checkm8 Exploit")
            self.run_btn.setObjectName("btnPrimary")
            self.run_btn.setIcon(icons.qicon("zap", size=14, color="#FFFFFF"))
            self.run_btn.setIconSize(icons.icon_size(14))
            self.run_btn.clicked.connect(self._run_exploit)
            run_wrap = QHBoxLayout()
            run_wrap.setContentsMargins(38, 4, 0, 0)
            run_wrap.addWidget(self.run_btn)
            run_wrap.addStretch()
            layout.addLayout(run_wrap)

        card._dot = dot
        return card

    def _refresh_cards(self) -> None:
        for i, card in enumerate(self._step_cards):
            active = i == self._current_step
            done = i < self._current_step
            border = "#C2DDCE" if active else "#E8E8E2"
            card.setStyleSheet(f"QFrame#card {{ border: 1px solid {border}; }}")
            card.setGraphicsEffect(None)

            dot = card._dot
            if done:
                dot.setText("")
                dot.setPixmap(icons.pixmap("check", size=14, color="#FFFFFF", stroke=3))
                dot.setStyleSheet("background: #2A9461;")
            elif active:
                dot.setPixmap(dot.pixmap() or icons.pixmap("check", size=0, color="#FFFFFF"))
                dot.setText(str(i + 1))
                dot.setStyleSheet(
                    "background: #1B5E3B; color: #FFFFFF;"
                    " font-size: 12px; font-weight: 700;"
                )
            else:
                dot.setText(str(i + 1))
                dot.setStyleSheet(
                    "background: #EAEAE4; color: #7A7A72;"
                    " font-size: 12px; font-weight: 700;"
                )

        self.back_btn.setEnabled(self._current_step > 0 and not self._running)
        self.next_btn.setEnabled(self._current_step < len(STEPS) - 1 and not self._running)

    def _back(self) -> None:
        if self._current_step > 0:
            self._current_step -= 1
            self._refresh_cards()

    def _next(self) -> None:
        if self._current_step < len(STEPS) - 1:
            self._current_step += 1
            self._refresh_cards()

    def _run_exploit(self) -> None:
        if self._running:
            return
        self._running = True
        self.run_btn.setEnabled(False)
        self.run_btn.setText("  Running...")
        self.toast.emit("Running checkm8 exploit...")

        self.log_card.setVisible(True)
        self.results_card.setVisible(True)
        self.log_view.clear()
        for lbl in self._file_rows.values():
            lbl.setText("pending")

        ts = int(time.time())
        output_dir = EXTRACT_DEFAULT_ROOT / f"checkm8_{ts}"
        self._worker = Checkm8Worker(output_dir)
        self._worker.log_line.connect(self._append_log)
        self._worker.step_started.connect(self._on_step_started)
        self._worker.step_complete.connect(self._on_step_complete)
        self._worker.file_result.connect(self._on_file_result)
        self._worker.manifest_ready.connect(self._on_manifest)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _append_log(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    def _on_step_started(self, idx: int) -> None:
        self._current_step = idx
        self._refresh_cards()

    def _on_step_complete(self, idx: int, ok: bool) -> None:
        if ok:
            self._current_step = idx + 1
        self._refresh_cards()

    def _on_file_result(self, local: str, status: str, size: int) -> None:
        lbl = self._file_rows.get(local)
        if not lbl:
            return
        if status == "extracted":
            lbl.setStyleSheet("color: #14432A;")
            lbl.setText(f"extracted · {fmt_bytes(size)}")
        elif status == "locked":
            lbl.setStyleSheet("color: #C62828;")
            lbl.setText("locked (device needs unlock)")
        elif status == "not found":
            lbl.setStyleSheet("color: #7A7A72;")
            lbl.setText("not found")
        else:
            lbl.setStyleSheet("color: #C62828;")
            lbl.setText(status)

    def _on_manifest(self, path: str, digest: str) -> None:
        self._append_log(f"manifest written: {path} (sha256={digest[:16]})")

    def _on_all_done(self, success: bool) -> None:
        self._running = False
        self.run_btn.setEnabled(True)
        self.run_btn.setText("  Run checkm8 Exploit")
        self._refresh_cards()
        if success:
            self.toast.emit("checkm8 extraction complete")
        else:
            self.toast.emit("checkm8 extraction failed - see log")
