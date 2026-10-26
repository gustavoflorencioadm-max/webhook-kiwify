#!/usr/bin/env python3
"""
Receptor de Webhook Kiwify + Status dos Agentes

Os eventos recebidos vão para data/vendas_kiwify.jsonl. No plano gratuito
do Render esse diretório é efêmero e some quando o serviço reinicia.
Vendas que precisam permanecer ficam em vendas-historico.json (versionado
no repositório) e entram em GET /vendas junto com o que ainda estiver no log.
"""
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

PORT = int(os.getenv("PORT", "8080"))
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / "vendas_kiwify.jsonl"
STATUS_FILE = DATA_DIR / "agentes_status.json"
HISTORICO_FILE = ROOT / "vendas-historico.json"
PAINEL_FILE = ROOT / "painel.html"
LIMITE_LOG = 50


def ler_jsonl(path):
    vendas = []
    if not path.exists():
        return vendas
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                vendas.append(item)
    return vendas


def carregar_historico():
    if not HISTORICO_FILE.exists():
        return []
    try:
        with open(HISTORICO_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        print(f"Falha ao ler {HISTORICO_FILE.name}: {exc}")
        return []
    if not isinstance(data, list):
        print(f"{HISTORICO_FILE.name} precisa ser uma lista JSON")
        return []
    return [item for item in data if isinstance(item, dict)]


def tem_my_commission(venda):
    payload = venda.get("full_payload")
    if isinstance(payload, dict):
        comissoes = payload.get("Commissions")
        if isinstance(comissoes, dict) and comissoes.get("my_commission") is not None:
            return True
    return venda.get("my_commission") is not None


def id_pedido(venda):
    return str(venda.get("order_id") or venda.get("order_ref") or "")


def chave_evento(venda):
    pedido = id_pedido(venda)
    if not pedido:
        return None
    return (pedido, str(venda.get("event") or ""), str(venda.get("order_status") or ""))


def mesclar_vendas(ao_vivo, historico):
    """Une o log recente com o histórico versionado.

    O mesmo pedido + evento + status aparece uma vez. Entre duas cópias,
    fica a que traz my_commission. O corte de 50 vale só para o log
    volátil; o arquivo histórico entra inteiro. A soma no painel continua
    deduplicando por order_id.
    """
    escolhidos = {}
    ordem = []
    sem_chave = []

    def considerar(venda):
        if not isinstance(venda, dict):
            return
        chave = chave_evento(venda)
        if chave is None:
            sem_chave.append(venda)
            return
        atual = escolhidos.get(chave)
        if atual is None:
            escolhidos[chave] = venda
            ordem.append(chave)
            return
        if not tem_my_commission(atual) and tem_my_commission(venda):
            escolhidos[chave] = venda

    for venda in list(ao_vivo)[-LIMITE_LOG:]:
        considerar(venda)
    for venda in historico:
        considerar(venda)
    return [escolhidos[chave] for chave in ordem] + sem_chave


def listar_vendas():
    return mesclar_vendas(ler_jsonl(LOG_FILE), carregar_historico())


class WebhookHandler(BaseHTTPRequestHandler):
    def _path(self):
        path = urlparse(self.path).path
        if len(path) > 1:
            path = path.rstrip("/")
        return path

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _arquivo(self, path, content_type):
        if not path.exists() or not path.is_file():
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b"not found")
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
        path = self._path()
        if path == "/vendas":
            self._json(listar_vendas())
            return

        if path == "/vendas-historico.json":
            self._arquivo(HISTORICO_FILE, "application/json; charset=utf-8")
            return

        if path == "/painel.html":
            self._arquivo(PAINEL_FILE, "text/html; charset=utf-8")
            return

        if path == "/status":
            status = {}
            if STATUS_FILE.exists():
                with open(STATUS_FILE, "r", encoding="utf-8") as f:
                    status = json.load(f)
            self._json(status)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Webhook Kiwify receiver online\n")

if __name__ == "__main__":
    print(f"Servidor webhook rodando na porta {PORT}")
    HTTPServer(("0.0.0.0", PORT), WebhookHandler).serve_forever()
