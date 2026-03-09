import json
import os
import tempfile
from pathlib import Path

import websocket
import time

last_write = 0
WRITE_INTERVAL = 0.25   # segundos

JSON_PATH = "data/precios_ci.json"
WS_URL = "wss://mtr.primary.ventures/ws?session_id=&conn_id="
COOKIE = "_ga=GA1.3.359251460.1771445948; _gid=GA1.2.1262481020.1772560127; _gid=GA1.3.1262481020.1772560127; _mtz_web_key=SFMyNTY.g3QAAAABbQAAAAtfY3NyZl90b2tlbm0AAAAYbkNUUFFyNm1FaDlZRnlZZmZMc0g1aElt.Op7pFNO3DMDlvdJpCAs4efXzBgpvz-qoyK7VQcO_no0; _ga_H8XC66M775=GS2.1.s1772810540$o15$g1$t1772812841$j60$l0$h0; _ga=GA1.2.359251460.1771445948; _gat=1; _gat_UA-112877913-1=1; _gat_UA-134662504-1=1; _ga_QSLY6ZV7NX=GS2.2.s1772810534$o6$g1$t1772812842$j60$l0$h0; _ga_YDGQML6TSF=GS2.3.s1772812842$o14$g0$t1772812842$j60$l0$h0"

SUB_MSG = {
    "_req": "S",
    "topicType": "md",
    "topics": [
        "md.rx_TIVA_AL29D_24hs",
        "md.rx_TIVA_AN29D_24hs",
        "md.rx_TIVA_AL30D_24hs",
        "md.rx_TIVA_AL35D_24hs",
        "md.rx_TIVA_AE38D_24hs",
        "md.rx_TIVA_AL41D_24hs",
        "md.rx_TIVA_GD29D_24hs",
        "md.rx_TIVA_GD30D_24hs",
        "md.rx_TIVA_GD35D_24hs",
        "md.rx_TIVA_GD38D_24hs",
        "md.rx_TIVA_GD41D_24hs",
        "md.rx_TIVA_GD46D_24hs",
        "md.rx_TIVA_BPOA7D_24hs",
        "md.rx_TIVA_BPOB7D_24hs",
        "md.rx_TIVA_BPOC7D_24hs",
        "md.rx_TIVA_BPOD7D_24hs",
    ],
    "replace": False
}

latest_prices = {}


def safe_int(x):
    try:
        return int(float(x))
    except:
        return None


def safe_float(x):
    try:
        return float(x)
    except:
        return None


def a3_to_master_code(instrument: str):
    inst = str(instrument).strip().upper()
    for suffix in ["_24HS", "_CI"]:
        if inst.endswith(suffix):
            return inst[:-len(suffix)]
    return None


def pick_price(compra, venta):
    if compra is not None and venta is not None:
        return (venta)
    if compra is not None:
        return compra
    if venta is not None:
        return venta
    return None


def parse_market_message(msg: str):
    if not msg.startswith("M:rx_TIVA_"):
        return None

    parts = msg.split("|")
    instrument = parts[0].replace("M:rx_TIVA_", "")

    return {
        "instrument": instrument,
        "id": safe_int(parts[1]) if len(parts) > 1 else None,
        "vol_compra": safe_int(parts[2]) if len(parts) > 2 else None,
        "precio_compra": safe_float(parts[3]) if len(parts) > 3 else None,
        "precio_venta": safe_float(parts[4]) if len(parts) > 4 else None,
        "vol_venta": safe_int(parts[5]) if len(parts) > 5 else None,
        "raw": parts,
    }


def update_prices(parsed):
    inst = parsed["instrument"]

    if inst not in latest_prices:
        latest_prices[inst] = parsed.copy()
        return

    prev = latest_prices[inst]

    for k, v in parsed.items():
        if k == "raw":
            prev[k] = v
        elif v is not None:
            prev[k] = v


def load_json_base(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}

    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def atomic_save_json(path: str, data: dict):
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=str(path_obj.parent),
        encoding="utf-8"
    ) as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name

    os.replace(tmp_path, path_obj)


def persist_one(parsed):
    inst = parsed["instrument"]
    p = latest_prices[inst]

    code = a3_to_master_code(inst)
    if not code:
        return

    px = pick_price(p["precio_compra"], p["precio_venta"])
    if px is None or px <= 0:
        return

    base = load_json_base(JSON_PATH)
    base[code] = px
    atomic_save_json(JSON_PATH, base)

    print(f"{code} -> {px}")


def process_market_line(line: str):
    parsed = parse_market_message(line)
    if not parsed:
        return

    update_prices(parsed)
    persist_one(parsed)


def process_payload(payload):
    if isinstance(payload, str):
        if payload.startswith("M:rx_TIVA_"):
            process_market_line(payload)
        elif payload.startswith("X:"):
            pass
        return

    if isinstance(payload, list):
        for item in payload:
            process_payload(item)


def on_open(ws):
    print("Conectado al feed A3")
    ws.send(json.dumps(SUB_MSG))
    print("Suscripción enviada")


def on_message(ws, message):
    if isinstance(message, str):
        if message.startswith("M:rx_TIVA_") or message.startswith("X:"):
            process_payload(message)
            return

        try:
            obj = json.loads(message)
            process_payload(obj)
            return
        except Exception:
            pass


def on_error(ws, error):
    print("ERROR:", error)


def on_close(ws, close_status_code, close_msg):
    print("CERRADO:", close_status_code, close_msg)


ws = websocket.WebSocketApp(
    WS_URL,
    header=[
        f"Cookie: {COOKIE}",
        "Origin: https://mtr.primary.ventures",
    ],
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close,
)

ws.run_forever()