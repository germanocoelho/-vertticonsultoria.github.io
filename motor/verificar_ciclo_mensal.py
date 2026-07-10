#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verifica se o ciclo mensal do MOTOR VERTTI já concluiu o download com
sucesso NESTE mês calendário (usado pelo motor_retry_diario.yml). Imprime
"sim" (precisa retry) ou "nao" (já está ok) em stdout — nada mais.

ATENÇÃO — por que verificamos a DATA DE EXECUÇÃO (quando) e não a
referência dos dados (ref):
  'ref' é o mês A QUE OS DADOS SE REFEREM (ex.: "2026-06", porque o espelho
  usado pelo 0_baixar_receita.py fica cerca de um mês atrás do calendário
  real). Comparar ref com o mês corrente quase nunca bateria, e faria este
  script concluir "precisa retry" todo santo dia do mês — disparando o
  ciclo mensal (e, portanto, um novo lote de e-mails reais via Brevo)
  repetidamente. O que importa aqui é apenas: o passo de download RODOU E
  TEVE SUCESSO neste mês corrente? Isso é o campo 'quando' da etapa
  'download', não 'ref'.
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
        download = st.get("etapas", {}).get("download", {})
        download_ok = download.get("status") == "ok"
        quando = download.get("quando", "")  # formato "AAAA-MM-DDT..."
        rodou_neste_mes = quando.startswith(mes_atual)
        precisa_retry = not (download_ok and rodou_neste_mes)
    except Exception:
        precisa_retry = True
    print("sim" if precisa_retry else "nao")


if __name__ == "__main__":
    main()
    sys.exit(0)
