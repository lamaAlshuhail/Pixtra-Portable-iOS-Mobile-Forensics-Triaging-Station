from typing import Any, Optional

from PyQt6.QtCore import QObject, QSettings, pyqtSignal


class AppState(QObject):
    case_changed = pyqtSignal(object)
    case_info_changed = pyqtSignal(object)
    evidence_changed = pyqtSignal(object)

    SETTINGS_ORG = "Pixtra"
    SETTINGS_APP = "PixtraQt"
    KEY_CASE_ID = "caseId"

    def __init__(self) -> None:
        super().__init__()
        self._settings = QSettings(self.SETTINGS_ORG, self.SETTINGS_APP)
        self._case_id: Optional[str] = self._settings.value(self.KEY_CASE_ID, None) or None
        self._case_info: Optional[dict] = None
        self._evidence: Optional[dict] = None

    @property
    def case_id(self) -> Optional[str]:
        return self._case_id

    @property
    def case_info(self) -> Optional[dict]:
        return self._case_info

    @property
    def evidence(self) -> Optional[dict]:
        return self._evidence

    def set_case(self, case_id: Optional[str]) -> None:
        if self._case_id == case_id:
            return
        self._case_id = case_id
        if case_id:
            self._settings.setValue(self.KEY_CASE_ID, case_id)
        else:
            self._settings.remove(self.KEY_CASE_ID)
            self._case_info = None
            self._evidence = None
            self.case_info_changed.emit(None)
            self.evidence_changed.emit(None)
        self.case_changed.emit(case_id)

    def set_case_info(self, info: Optional[dict]) -> None:
        self._case_info = info
        self.case_info_changed.emit(info)

    def set_evidence(self, ev: Optional[dict]) -> None:
        self._evidence = ev
        self.evidence_changed.emit(ev)

    def count(self, key: str) -> int:
        if not self._evidence:
            return 0
        cats = self._evidence.get("categories") or {}
        v = cats.get(key)
        return int(v) if v else 0
