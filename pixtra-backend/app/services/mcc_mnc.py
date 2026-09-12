from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


_MCC_MNC: dict[tuple[str, str], tuple[str, str]] = {
    ("001", "01"): ("Test Network", "Test PLMN"),

    ("202", "01"): ("Greece", "Cosmote"),
    ("202", "05"): ("Greece", "Vodafone Greece"),
    ("204", "04"): ("Netherlands", "Vodafone NL"),
    ("204", "08"): ("Netherlands", "KPN"),
    ("204", "16"): ("Netherlands", "T-Mobile NL"),
    ("206", "01"): ("Belgium", "Proximus"),
    ("206", "10"): ("Belgium", "Orange Belgium"),
    ("206", "20"): ("Belgium", "Base"),
    ("208", "01"): ("France", "Orange France"),
    ("208", "10"): ("France", "SFR"),
    ("208", "15"): ("France", "Free Mobile"),
    ("208", "20"): ("France", "Bouygues Telecom"),
    ("214", "01"): ("Spain", "Vodafone Spain"),
    ("214", "03"): ("Spain", "Orange Spain"),
    ("214", "07"): ("Spain", "Movistar"),
    ("222", "01"): ("Italy", "TIM"),
    ("222", "10"): ("Italy", "Vodafone Italy"),
    ("222", "88"): ("Italy", "WindTre"),
    ("226", "01"): ("Romania", "Vodafone Romania"),
    ("226", "10"): ("Romania", "Orange Romania"),
    ("228", "01"): ("Switzerland", "Swisscom"),
    ("228", "02"): ("Switzerland", "Sunrise"),
    ("228", "03"): ("Switzerland", "Salt"),
    ("232", "01"): ("Austria", "A1"),
    ("232", "03"): ("Austria", "Magenta"),
    ("232", "05"): ("Austria", "Drei"),
    ("234", "10"): ("United Kingdom", "O2"),
    ("234", "15"): ("United Kingdom", "Vodafone"),
    ("234", "20"): ("United Kingdom", "Three"),
    ("234", "30"): ("United Kingdom", "EE"),
    ("234", "33"): ("United Kingdom", "EE"),
    ("238", "01"): ("Denmark", "TDC"),
    ("238", "02"): ("Denmark", "Telenor Denmark"),
    ("238", "20"): ("Denmark", "Telia Denmark"),
    ("240", "01"): ("Sweden", "Telia Sweden"),
    ("240", "07"): ("Sweden", "Tele2"),
    ("240", "08"): ("Sweden", "Telenor Sweden"),
    ("242", "01"): ("Norway", "Telenor Norway"),
    ("242", "02"): ("Norway", "Telia Norway"),
    ("244", "05"): ("Finland", "Elisa"),
    ("244", "91"): ("Finland", "Telia Finland"),
    ("250", "01"): ("Russia", "MTS"),
    ("250", "02"): ("Russia", "MegaFon"),
    ("250", "99"): ("Russia", "Beeline"),
    ("255", "01"): ("Ukraine", "Vodafone Ukraine"),
    ("255", "03"): ("Ukraine", "Kyivstar"),
    ("260", "01"): ("Poland", "Plus"),
    ("260", "02"): ("Poland", "T-Mobile Poland"),
    ("260", "03"): ("Poland", "Orange Poland"),
    ("260", "06"): ("Poland", "Play"),
    ("262", "01"): ("Germany", "Telekom Deutschland"),
    ("262", "02"): ("Germany", "Vodafone Germany"),
    ("262", "03"): ("Germany", "Telefónica O2 Germany"),
    ("268", "01"): ("Portugal", "Vodafone Portugal"),
    ("268", "03"): ("Portugal", "NOS"),
    ("268", "06"): ("Portugal", "MEO"),
    ("272", "01"): ("Ireland", "Vodafone Ireland"),
    ("272", "02"): ("Ireland", "Three Ireland"),
    ("272", "03"): ("Ireland", "Eir"),
    ("286", "01"): ("Turkey", "Turkcell"),
    ("286", "02"): ("Turkey", "Vodafone Turkey"),
    ("286", "03"): ("Turkey", "Turk Telekom"),

    ("302", "220"): ("Canada", "Telus"),
    ("302", "610"): ("Canada", "Bell"),
    ("302", "720"): ("Canada", "Rogers"),
    ("310", "012"): ("United States", "Verizon"),
    ("310", "150"): ("United States", "AT&T"),
    ("310", "160"): ("United States", "T-Mobile"),
    ("310", "260"): ("United States", "T-Mobile"),
    ("310", "410"): ("United States", "AT&T"),
    ("310", "480"): ("United States", "Verizon"),
    ("311", "480"): ("United States", "Verizon"),
    ("334", "020"): ("Mexico", "Telcel"),
    ("334", "030"): ("Mexico", "Movistar Mexico"),
    ("334", "050"): ("Mexico", "AT&T Mexico"),

    ("404", "10"): ("India", "Airtel"),
    ("404", "20"): ("India", "Vodafone Idea"),
    ("404", "45"): ("India", "Airtel"),
    ("405", "840"): ("India", "Reliance Jio"),
    ("410", "01"): ("Pakistan", "Jazz"),
    ("410", "03"): ("Pakistan", "Ufone"),
    ("410", "04"): ("Pakistan", "Zong"),
    ("410", "06"): ("Pakistan", "Telenor Pakistan"),
    ("415", "01"): ("Lebanon", "Alfa"),
    ("415", "03"): ("Lebanon", "Touch"),
    ("416", "01"): ("Jordan", "Zain Jordan"),
    ("416", "03"): ("Jordan", "Umniah"),
    ("416", "77"): ("Jordan", "Orange Jordan"),
    ("419", "02"): ("Kuwait", "Zain Kuwait"),
    ("419", "03"): ("Kuwait", "Ooredoo Kuwait"),
    ("419", "04"): ("Kuwait", "stc Kuwait"),
    ("420", "01"): ("Saudi Arabia", "stc"),
    ("420", "03"): ("Saudi Arabia", "Mobily"),
    ("420", "04"): ("Saudi Arabia", "Zain"),
    ("420", "05"): ("Saudi Arabia", "Virgin Mobile"),
    ("420", "06"): ("Saudi Arabia", "Lebara"),
    ("420", "07"): ("Saudi Arabia", "Salam"),
    ("422", "02"): ("Oman", "Omantel"),
    ("422", "03"): ("Oman", "Ooredoo Oman"),
    ("424", "02"): ("United Arab Emirates", "Etisalat"),
    ("424", "03"): ("United Arab Emirates", "du"),
    ("425", "01"): ("Israel", "Partner"),
    ("425", "02"): ("Israel", "Cellcom"),
    ("425", "03"): ("Israel", "Pelephone"),
    ("426", "01"): ("Bahrain", "Batelco"),
    ("426", "02"): ("Bahrain", "Zain Bahrain"),
    ("426", "04"): ("Bahrain", "stc Bahrain"),
    ("427", "01"): ("Qatar", "Ooredoo Qatar"),
    ("427", "02"): ("Qatar", "Vodafone Qatar"),
    ("432", "11"): ("Iran", "MCI"),
    ("432", "35"): ("Iran", "MTN Irancell"),
    ("440", "10"): ("Japan", "NTT Docomo"),
    ("440", "20"): ("Japan", "SoftBank"),
    ("440", "50"): ("Japan", "KDDI (au)"),
    ("450", "05"): ("South Korea", "SK Telecom"),
    ("450", "06"): ("South Korea", "LG U+"),
    ("450", "08"): ("South Korea", "KT"),
    ("452", "01"): ("Vietnam", "MobiFone"),
    ("452", "02"): ("Vietnam", "Vinaphone"),
    ("452", "04"): ("Vietnam", "Viettel"),
    ("454", "00"): ("Hong Kong", "CSL"),
    ("454", "03"): ("Hong Kong", "3 Hong Kong"),
    ("454", "06"): ("Hong Kong", "SmarTone"),
    ("460", "00"): ("China", "China Mobile"),
    ("460", "01"): ("China", "China Unicom"),
    ("460", "11"): ("China", "China Telecom"),
    ("466", "92"): ("Taiwan", "Chunghwa Telecom"),
    ("466", "97"): ("Taiwan", "Taiwan Mobile"),
    ("470", "01"): ("Bangladesh", "Grameenphone"),
    ("470", "02"): ("Bangladesh", "Robi"),
    ("470", "03"): ("Bangladesh", "Banglalink"),

    ("505", "01"): ("Australia", "Telstra"),
    ("505", "02"): ("Australia", "Optus"),
    ("505", "03"): ("Australia", "Vodafone Australia"),
    ("510", "01"): ("Indonesia", "Indosat Ooredoo"),
    ("510", "10"): ("Indonesia", "Telkomsel"),
    ("510", "11"): ("Indonesia", "XL Axiata"),
    ("515", "02"): ("Philippines", "Globe"),
    ("515", "03"): ("Philippines", "Smart"),
    ("520", "01"): ("Thailand", "AIS"),
    ("520", "05"): ("Thailand", "dtac"),
    ("520", "18"): ("Thailand", "TrueMove H"),
    ("525", "01"): ("Singapore", "Singtel"),
    ("525", "03"): ("Singapore", "M1"),
    ("525", "05"): ("Singapore", "StarHub"),
    ("530", "01"): ("New Zealand", "One NZ"),
    ("530", "05"): ("New Zealand", "Spark"),
    ("530", "24"): ("New Zealand", "2degrees"),

    ("602", "01"): ("Egypt", "Orange Egypt"),
    ("602", "02"): ("Egypt", "Vodafone Egypt"),
    ("602", "03"): ("Egypt", "Etisalat Misr"),
    ("602", "04"): ("Egypt", "WE"),
    ("604", "00"): ("Morocco", "Orange Morocco"),
    ("604", "01"): ("Morocco", "Maroc Telecom"),
    ("604", "02"): ("Morocco", "Inwi"),
    ("621", "20"): ("Nigeria", "Airtel Nigeria"),
    ("621", "30"): ("Nigeria", "MTN Nigeria"),
    ("621", "50"): ("Nigeria", "Glo"),
    ("639", "02"): ("Kenya", "Safaricom"),
    ("639", "03"): ("Kenya", "Airtel Kenya"),
    ("655", "01"): ("South Africa", "Vodacom"),
    ("655", "07"): ("South Africa", "Cell C"),
    ("655", "10"): ("South Africa", "MTN South Africa"),

    ("716", "06"): ("Peru", "Movistar Peru"),
    ("716", "10"): ("Peru", "Claro Peru"),
    ("722", "07"): ("Argentina", "Movistar Argentina"),
    ("722", "310"): ("Argentina", "Claro Argentina"),
    ("722", "340"): ("Argentina", "Personal"),
    ("724", "05"): ("Brazil", "Claro Brazil"),
    ("724", "06"): ("Brazil", "Vivo"),
    ("724", "10"): ("Brazil", "Vivo"),
    ("724", "02"): ("Brazil", "TIM Brazil"),
    ("730", "01"): ("Chile", "Entel"),
    ("730", "02"): ("Chile", "Movistar Chile"),
    ("730", "03"): ("Chile", "Claro Chile"),
    ("732", "101"): ("Colombia", "Claro Colombia"),
    ("732", "123"): ("Colombia", "Movistar Colombia"),
}


def _load_overrides() -> None:
    path = os.environ.get("PIXTRA_MCC_MNC_FILE")
    if not path or not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for key, val in data.items():
            mcc, _, mnc = key.partition("-")
            if mcc and mnc and isinstance(val, (list, tuple)) and len(val) == 2:
                _MCC_MNC[(mcc, mnc)] = (str(val[0]), str(val[1]))
    except Exception as e:
        logger.warning(f"Could not load MCC/MNC overrides from {path}: {e}")


_load_overrides()


def lookup_mcc_mnc(mcc: Optional[str], mnc: Optional[str]) -> Optional[dict]:
    if not mcc or not mnc:
        return None
    hit = _MCC_MNC.get((mcc, mnc))
    if hit is None:
        return None
    return {"country": hit[0], "operator": hit[1]}
