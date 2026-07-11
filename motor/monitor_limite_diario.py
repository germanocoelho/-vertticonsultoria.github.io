#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MONITOR DE LIMITE DIÁRIO — Brevo
Consulta GET /v3/account (endpoint oficial da Brevo) e lê o campo real de
créditos restantes do dia (plan[].creditsType == "sendLimit", type == "free").
Não é uma estimativa — é o número que a própria Brevo mantém internamente.

Se o uso do dia atingir 80% do limite (300 e-mails/dia no plano Gratuito),
avisa por e-mail (Brevo transacional) E grava um alerta em motor_status.json,
visível na página "Relatório Motor" do Escritório Digital.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.abspath(__file__))
STATUS = os.path.join(RAIZ, "motor_status.json")
LIMITE_DIARIO_GRATUITO = 300
LIMIAR_ALERTA = 0.80  # avisa aos 80%


def agora():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def carregar(path, padrao):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return padrao


def gravar(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def consultar_conta(chave):
    req = urllib.request.Request("https://api.brevo.com/v3/account",
                                  headers={"api-key": chave, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def enviar_alerta_email(chave, destino, assunto, corpo_html):
    corpo = {
        "sender": {"email": "contato@vertticonsultoria.com.br", "name": "Motor VERTTI — Alerta"},
        "to": [{"email": destino}],
        "subject": assunto,
        "htmlContent": corpo_html,
    }
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(corpo).encode("utf-8"), method="POST",
        headers={"api-key": chave, "Content-Type": "application/json",
                 "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def main():
    chave = os.environ.get("BREVO_API_KEY", "").strip()
    destino = os.environ.get("ALERTA_EMAIL_DESTINO", "").strip()
    st = carregar(STATUS, {"etapas": {}, "alertas": []})
    st.setdefault("etapas", {})
    st.setdefault("alertas", [])

    if not chave:
        print("AVISO: BREVO_API_KEY não configurada — não é possível consultar o limite.")
        sys.exit(0)  # não-fatal: não faz sentido travar nenhum workflow por isso

    try:
        conta = consultar_conta(chave)
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"AVISO: falha ao consultar a conta Brevo ({exc}).")
        sys.exit(0)

    plano_envio = next((p for p in conta.get("plan", [])
                         if p.get("creditsType") == "sendLimit"), None)
    if not plano_envio:
        print("AVISO: a resposta da Brevo não trouxe um plano do tipo 'sendLimit' "
              "(pode já estar num plano pago sem limite diário).")
        sys.exit(0)

    restantes = int(plano_envio.get("credits", LIMITE_DIARIO_GRATUITO))
    tipo_plano = plano_envio.get("type", "?")
    limite_total = LIMITE_DIARIO_GRATUITO if tipo_plano == "free" else None

    if limite_total is None:
        print(f"Plano '{tipo_plano}' não tem o teto diário de 300 — nada a monitorar aqui.")
        st["etapas"]["limite_diario_brevo"] = {
            "status": "ok", "quando": agora(),
            "detalhe": f"plano '{tipo_plano}' sem teto diário fixo — monitor não se aplica",
            "integridade": ""}
        gravar(STATUS, st)
        sys.exit(0)

    usados = limite_total - restantes
    pct = usados / limite_total
    print(f"Uso de hoje: {usados}/{limite_total} e-mails ({pct:.0%}). "
          f"Restam {restantes} créditos.")

    st["etapas"]["limite_diario_brevo"] = {
        "status": "aviso" if pct >= LIMIAR_ALERTA else "ok",
        "quando": agora(),
        "detalhe": f"{usados}/{limite_total} e-mails usados hoje ({pct:.0%}); {restantes} restantes",
        "integridade": "consultado direto na Brevo (GET /v3/account) — número real, não estimado"}

    if pct >= LIMIAR_ALERTA:
        msg = (f"📬 Uso diário de e-mail na Brevo: {usados}/{limite_total} "
               f"({pct:.0%}) — restam só {restantes} envios até meia-noite (UTC).")
        st["alertas"].append({"nivel": "aviso", "msg": msg, "quando": agora()})
        print(f"ALERTA: {msg}")

        if chave and destino:
            try:
                enviar_alerta_email(
                    chave, destino,
                    f"⚠ Brevo: {pct:.0%} do limite diário de e-mails usado",
                    f"<p>{msg}</p><p>Isso reseta à meia-noite (horário UTC). "
                    f"Se isso virar rotina, é sinal de considerar o plano Standard "
                    f"(que remove o teto diário).</p>")
                print(f"Alerta enviado por e-mail para {destino}.")
            except Exception as exc:
                print(f"AVISO: alerta gerado mas o envio por e-mail falhou ({exc}) — "
                      f"ainda assim está registrado no motor_status.json.")
        elif not destino:
            print("AVISO: defina o secret ALERTA_EMAIL_DESTINO para receber isso por e-mail "
                  "— por ora só ficou registrado no status.")

    gravar(STATUS, st)


if __name__ == "__main__":
    main()
    sys.exit(0)
