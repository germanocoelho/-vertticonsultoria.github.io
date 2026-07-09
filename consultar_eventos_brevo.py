#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Consulta o log de eventos transacionais do Brevo para os e-mails de teste
recem-enviados (tag=teste-motor-vertti) e imprime o status de cada um:
aceito, entregue, bloqueado, em spam, rejeitado etc.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BREVO_KEY = os.environ["BREVO_API_KEY"]
DEST = os.environ.get("DEST_EMAIL", "germano.consneo@gmail.com")

params = urllib.parse.urlencode({
    "email": DEST,
    "limit": 50,
    "sort": "desc",
})
url = f"https://api.brevo.com/v3/smtp/statistics/events?{params}"
req = urllib.request.Request(url, headers={"api-key": BREVO_KEY, "Accept": "application/json"})
try:
    with urllib.request.urlopen(req) as r:
        data = json.load(r)
except urllib.error.HTTPError as e:
    corpo = e.read().decode("utf-8", errors="replace")
    print(f"::error::Brevo respondeu {e.code} em {url} :: {corpo[:500]}")
    raise
except Exception as e:
    print(f"::error::Falha inesperada: {type(e).__name__}: {e}")
    raise

eventos = data.get("events", [])
print(f"Total de eventos encontrados para {DEST}: {len(eventos)}\n")
print("--- JSON bruto (para garantir que nada fica escondido) ---")
print(json.dumps(data, ensure_ascii=False, indent=1)[:4000])
print("--- resumo ---")
for e in eventos:
    print(f"{e.get('date','?'):25s} | evento={e.get('event','?'):12s} | "
          f"assunto={e.get('subject','?')[:60]!r} | messageId={e.get('messageId','?')}"
          f" | tag={e.get('tag','?')}")
