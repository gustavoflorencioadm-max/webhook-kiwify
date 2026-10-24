#!/usr/bin/env python3
"""
Receptor de Webhook Kiwify + Status dos Agentes
"""
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from pathlib import Path

PORT = int(os.getenv("PORT", "8080"))
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / "vendas_kiwify.jsonl"
STATUS_FILE = DATA_DIR / "agentes_status.json"

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            payload = {"raw": body.decode("utf-8", errors="ignore")}

        if self.path.startswith("/status"):
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return

        entry = {
            "received_at": datetime.now().isoformat(),
            "event": payload.get("webhook_event_type") or payload.get("type") or "unknown",
            "order_status": payload.get("order_status"),
            "order_id": payload.get("order_id"),
            "order_ref": payload.get("order_ref"),
            "payment_method": payload.get("payment_method"),
            "product_name": (payload.get("Product") or {}).get("product_name") if isinstance(payload.get("Product"), dict) else None,
            "amount": payload.get("Commissions", {}).get("charge_amount") if isinstance(payload.get("Commissions"), dict) else None,
            "full_payload": payload
        }

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_GET(self):
        if self.path.startswith("/vendas"):
            vendas = []
            if LOG_FILE.exists():
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            vendas.append(json.loads(line))
                        except:
                            pass
            vendas = vendas[-50:]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(vendas, ensure_ascii=False).encode())
            return

        if self.path.startswith("/status"):
            status = {}
            if STATUS_FILE.exists():
                with open(STATUS_FILE, "r", encoding="utf-8") as f:
                    status = json.load(f)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(status, ensure_ascii=False).encode())
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Webhook Kiwify receiver online\n")

if __name__ == "__main__":
    print(f"Servidor webhook rodando na porta {PORT}")
    HTTPServer(("0.0.0.0", PORT), WebhookHandler).serve_forever()
