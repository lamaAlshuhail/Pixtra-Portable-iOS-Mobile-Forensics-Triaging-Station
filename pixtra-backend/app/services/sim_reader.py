from __future__ import annotations

from typing import Optional


_APDU_SELECT_MF = [0xA0, 0xA4, 0x00, 0x00, 0x02, 0x3F, 0x00]
_APDU_SELECT_DF_GSM = [0xA0, 0xA4, 0x00, 0x00, 0x02, 0x7F, 0x20]
_APDU_SELECT_EF_ICCID = [0xA0, 0xA4, 0x00, 0x00, 0x02, 0x2F, 0xE2]
_APDU_SELECT_EF_IMSI = [0xA0, 0xA4, 0x00, 0x00, 0x02, 0x6F, 0x07]
_APDU_SELECT_EF_SPN = [0xA0, 0xA4, 0x00, 0x00, 0x02, 0x6F, 0x46]
_APDU_SELECT_EF_LOCI = [0xA0, 0xA4, 0x00, 0x00, 0x02, 0x6F, 0x7E]

_APDU_READ_ICCID = [0xA0, 0xB0, 0x00, 0x00, 0x0A]
_APDU_READ_IMSI = [0xA0, 0xB0, 0x00, 0x00, 0x09]
_APDU_READ_SPN = [0xA0, 0xB0, 0x00, 0x00, 0x11]
_APDU_READ_LOCI = [0xA0, 0xB0, 0x00, 0x00, 0x0B]


def _hex(b) -> str:
    if isinstance(b, (bytes, bytearray)):
        return " ".join(f"{x:02X}" for x in b)
    return " ".join(f"{x:02X}" for x in b)


def _decode_bcd_swapped(blob, length_digits: Optional[int] = None) -> str:
    out_digits: list[str] = []
    for byte in blob:
        low = byte & 0x0F
        high = (byte >> 4) & 0x0F
        for nibble in (low, high):
            if nibble == 0xF:
                continue
            if 0 <= nibble <= 9:
                out_digits.append(str(nibble))
    text = "".join(out_digits)
    if length_digits is not None and len(text) > length_digits:
        text = text[:length_digits]
    return text


def _parse_imsi(blob: bytes) -> Optional[str]:
    if not isinstance(blob, (bytes, bytearray, list)) or len(blob) < 9:
        return None
    blob = bytes(blob)
    length_byte = blob[0]
    body = blob[1:1 + length_byte] if length_byte else blob[1:9]
    if len(body) < 1:
        return None
    odd_length = bool(body[0] & 0x01)
    first_digit = (body[0] >> 4) & 0x0F
    if first_digit > 9:
        return None
    digits: list[str] = [str(first_digit)]
    for byte in body[1:]:
        for nibble in (byte & 0x0F, (byte >> 4) & 0x0F):
            if nibble == 0xF:
                continue
            if 0 <= nibble <= 9:
                digits.append(str(nibble))
    text = "".join(digits)
    expected_len = 15 if odd_length else 14
    if len(text) > expected_len:
        text = text[:expected_len]
    return text or None


def _split_imsi(imsi: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    if not imsi or len(imsi) < 6:
        return None, None, None
    mcc = imsi[:3]
    three_digit_mnc_mccs = {
        "302",
        "310", "311", "312", "313", "314", "315", "316",
        "334",
        "338",
        "342", "344", "346", "348",
        "405",
    }
    mnc_len = 3 if mcc in three_digit_mnc_mccs else 2
    if len(imsi) < 3 + mnc_len:
        return mcc, None, None
    mnc = imsi[3:3 + mnc_len]
    msin = imsi[3 + mnc_len:]
    return mcc, mnc, msin


def _decode_spn(blob: bytes) -> Optional[str]:
    if not isinstance(blob, (bytes, bytearray, list)) or len(blob) < 2:
        return None
    blob = bytes(blob)
    text_bytes = bytes(b for b in blob[1:] if b != 0xFF)
    if not text_bytes:
        return None
    try:
        text = text_bytes.decode("utf-8", errors="replace").strip()
    except Exception:
        return None
    return text or None


def _parse_loci(blob: bytes) -> tuple[Optional[str], Optional[str], Optional[str]]:
    if not isinstance(blob, (bytes, bytearray, list)) or len(blob) < 9:
        return None, None, None
    blob = bytes(blob)
    b4, b5, b6 = blob[4], blob[5], blob[6]
    mcc_digits = [b4 & 0x0F, (b4 >> 4) & 0x0F, b5 & 0x0F]
    if any(d > 9 for d in mcc_digits):
        return None, None, None
    mcc = "".join(str(d) for d in mcc_digits)

    mnc_high = (b5 >> 4) & 0x0F
    mnc_d1 = b6 & 0x0F
    mnc_d2 = (b6 >> 4) & 0x0F
    if mnc_d1 > 9 or mnc_d2 > 9:
        return mcc, None, None
    if mnc_high == 0xF:
        mnc = f"{mnc_d1}{mnc_d2}"
    elif mnc_high <= 9:
        mnc = f"{mnc_d1}{mnc_d2}{mnc_high}"
    else:
        mnc = f"{mnc_d1}{mnc_d2}"

    if len(blob) >= 9:
        lac = f"{blob[7]:02X}{blob[8]:02X}"
    else:
        lac = None
    return mcc, mnc, lac


def _import_pyscard():
    from smartcard.System import readers as list_readers
    from smartcard.Exceptions import (
        NoCardException,
        CardConnectionException,
    )
    return list_readers, NoCardException, CardConnectionException


def get_reader_status() -> dict:
    try:
        list_readers, NoCardException, _ = _import_pyscard()
    except ImportError:
        return {"has_reader": False, "has_card": False, "reader_name": None,
                "error": "pyscard not installed"}
    try:
        readers_list = list_readers()
    except Exception as exc:
        return {"has_reader": False, "has_card": False, "reader_name": None,
                "error": str(exc)}
    if not readers_list:
        return {"has_reader": False, "has_card": False, "reader_name": None}
    reader = readers_list[0]
    name = str(reader)
    try:
        conn = reader.createConnection()
        conn.connect()
        conn.disconnect()
        return {"has_reader": True, "has_card": True, "reader_name": name}
    except NoCardException:
        return {"has_reader": True, "has_card": False, "reader_name": name}
    except Exception:
        return {"has_reader": True, "has_card": False, "reader_name": name}


def _transmit(conn, apdu: list[int]) -> tuple[list[int], int, int]:
    data, sw1, sw2 = conn.transmit(apdu)
    return data, sw1, sw2


def _select_then_read(
    conn,
    select_apdu: list[int],
    read_apdu: list[int],
    raw_log: list[dict],
) -> tuple[Optional[list[int]], int, int]:
    sel_data, sw1, sw2 = _transmit(conn, select_apdu)
    raw_log.append({
        "apdu": _hex(select_apdu),
        "sw": f"{sw1:02X}{sw2:02X}",
        "response": _hex(sel_data),
    })
    if sw1 not in (0x90, 0x9F, 0x61):
        return None, sw1, sw2
    read_data, rsw1, rsw2 = _transmit(conn, read_apdu)
    raw_log.append({
        "apdu": _hex(read_apdu),
        "sw": f"{rsw1:02X}{rsw2:02X}",
        "response": _hex(read_data),
    })
    return read_data, rsw1, rsw2


def scan_sim() -> dict:
    list_readers, NoCardException, _ = _import_pyscard()
    readers_list = list_readers()
    if not readers_list:
        raise RuntimeError("No smart-card reader detected")
    reader = readers_list[0]
    try:
        conn = reader.createConnection()
        conn.connect()
    except NoCardException as exc:
        raise RuntimeError("No card in reader") from exc
    except Exception as exc:
        raise RuntimeError(f"Reader connect failed: {exc}") from exc

    try:
        atr_bytes = bytes(conn.getATR())
        raw_log: list[dict] = []
        result: dict = {
            "atr": _hex(atr_bytes) or None,
            "iccid": None,
            "imsi": None,
            "mcc": None, "mnc": None, "msin": None,
            "spn": None,
            "operator_name": None,
            "country": None,
            "lai_mcc": None, "lai_mnc": None, "lai_lac": None,
            "pin_required": False,
            "raw_apdus": raw_log,
        }

        mf_data, sw1, sw2 = _transmit(conn, _APDU_SELECT_MF)
        raw_log.append({
            "apdu": _hex(_APDU_SELECT_MF),
            "sw": f"{sw1:02X}{sw2:02X}",
            "response": _hex(mf_data),
        })
        if sw1 not in (0x90, 0x9F, 0x61):
            raise RuntimeError(
                f"SELECT MF failed: SW={sw1:02X}{sw2:02X}"
            )

        iccid_data, sw1, sw2 = _select_then_read(
            conn, _APDU_SELECT_EF_ICCID, _APDU_READ_ICCID, raw_log,
        )
        if sw1 == 0x69 and sw2 == 0x82:
            result["pin_required"] = True
        elif iccid_data and sw1 == 0x90:
            result["iccid"] = _decode_bcd_swapped(iccid_data, length_digits=20)

        gsm_data, sw1, sw2 = _transmit(conn, _APDU_SELECT_DF_GSM)
        raw_log.append({
            "apdu": _hex(_APDU_SELECT_DF_GSM),
            "sw": f"{sw1:02X}{sw2:02X}",
            "response": _hex(gsm_data),
        })
        if sw1 in (0x90, 0x9F, 0x61):
            imsi_data, sw1, sw2 = _select_then_read(
                conn, _APDU_SELECT_EF_IMSI, _APDU_READ_IMSI, raw_log,
            )
            if imsi_data and sw1 == 0x90:
                imsi = _parse_imsi(bytes(imsi_data))
                result["imsi"] = imsi
                if imsi:
                    mcc, mnc, msin = _split_imsi(imsi)
                    result["mcc"] = mcc
                    result["mnc"] = mnc
                    result["msin"] = msin

            spn_data, sw1, sw2 = _select_then_read(
                conn, _APDU_SELECT_EF_SPN, _APDU_READ_SPN, raw_log,
            )
            if spn_data and sw1 == 0x90:
                result["spn"] = _decode_spn(bytes(spn_data))

            loci_data, sw1, sw2 = _select_then_read(
                conn, _APDU_SELECT_EF_LOCI, _APDU_READ_LOCI, raw_log,
            )
            if loci_data and sw1 == 0x90:
                lai_mcc, lai_mnc, lai_lac = _parse_loci(bytes(loci_data))
                result["lai_mcc"] = lai_mcc
                result["lai_mnc"] = lai_mnc
                result["lai_lac"] = lai_lac

        from app.services.mcc_mnc import lookup_mcc_mnc
        info = lookup_mcc_mnc(result["mcc"], result["mnc"])
        if info:
            result["country"] = info["country"]
            result["operator_name"] = info["operator"]
        elif result["spn"]:
            result["operator_name"] = result["spn"]

        return result
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass
