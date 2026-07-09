#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Consulta o log de eventos transacionais do Brevo para os e-mails de teste
recem-enviados (tag=teste-motor-vertti) e imprime o status de cada um:
aceito, entregue, bloqueado, em spam, rejeitado etc.
"""
import json
import os
import urllib.parse
import urllib.request

BREVO_KEY = os.environ["BREVO_API_KEY"]
DEST = os.environ.get("DEST_EMAIL", "germano.consneo@gmail.com")

params = urllib.parse.urlencode({
    "email": DEST,
    "limit": 50,
    "sort": "desc",
})
url = f"https://api.brevo.com/v3/smtp/emailEvents?{params}"
req = urllib.request.Request(url, headers={"api-key": BREVO_KEY, "Accept": "application/json"})
with urllib.request.urlopen(req) as r:
    data = json.load(r)

eventos = data.get("events", [])
print(f"Total de eventos encontrados para {DEST}: {len(eventos)}\n")
for e in eventos:
    print(f"{e.get('date','?'):25s} | evento={e.get('event','?'):12s} | "
          f"assunto={e.get('subject','?')[:60]!r} | messageId={e.get('messageId','?')}"
          f" | tag={e.get('tag','?')}")
