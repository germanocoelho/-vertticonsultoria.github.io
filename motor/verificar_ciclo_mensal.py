#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verifica se o ciclo mensal do MOTOR VERTTI já concluiu com sucesso no mês
atual (usado pelo motor_retry_diario.yml). Imprime "sim" (precisa retry)
ou "nao" (já está ok) em stdout — nada mais.
"""
import json
import sys
from datetime import datetime, timezone

STATUS_PATH = "motor_status.json"


def main():
    mes_atual = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        with open(STATUS_PATH, encoding="utf-8") as f:
            st = json.load(f)
        ref = st.get("ref", "")
        download_ok = st.get("etapas", {}).get("download", {}).get("status") == "ok"
        precisa_retry = not (ref == mes_atual and download_ok)
    except Exception:
        precisa_retry = True
    print("sim" if precisa_retry else "nao")


if __name__ == "__main__":
    main()
    sys.exit(0)
