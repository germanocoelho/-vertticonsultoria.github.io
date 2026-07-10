#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Envia os 3 e-mails de teste da sequência VERTTI para um único destinatário,
via API transacional do Brevo. Uso único, disparado pelo workflow
teste_email_unico.yml a partir do Escritório Digital / Claude.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BREVO_KEY = os.environ["BREVO_API_KEY"]
API = "https://api.brevo.com/v3/smtp/email"
DEST = os.environ.get("DEST_EMAIL", "germano.consneo@gmail.com")
NOME_EMPRESA = "Padaria Teste VERTTI"
MUNICIPIO = "Campo Grande"


def enviar(assunto, html, tag):
    corpo = {
        "sender": {"name": "Germano Coelho Ramos Rocha-Silva",
                   "email": "contato@vertticonsultoria.com.br"},
        "to": [{"email": DEST, "name": "Germano (teste)"}],
        "subject": f"[TESTE REVISADO {tag}] " + assunto,
        "htmlContent": html,
        "tags": ["teste-motor-vertti-revisado"],
    }
    req = urllib.request.Request(API, data=json.dumps(corpo).encode(), method="POST",
        headers={"api-key": BREVO_KEY, "Content-Type": "application/json",
                 "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            resp = json.load(r)
            print(f"OK   [{tag}] messageId={resp.get('messageId')}")
            return True
    except urllib.error.HTTPError as e:
        print(f"ERRO [{tag}] {e.code}: {e.read().decode()[:400]}")
        return False


rodape = ("<hr style='border:none;border-top:1px solid #ddd;margin:24px 0 10px'>"
          "<p style='font-size:12px;color:#888'>Você recebeu este e-mail porque a "
          f"{NOME_EMPRESA} consta nos registros públicos de empresas de MS e "
          "pode se beneficiar da proteção de marca. Se não desejar mais receber, "
          "<a href='#'>clique aqui</a> para sair. VERTTI Consultoria · Campo Grande/MS.</p>")

email1 = f"""
<p style='margin:0 0 14px'>Olá,</p>
<p style='margin:0 0 14px'>O CNPJ protege a sua empresa, mas não protege o seu nome. São registros
diferentes, em órgãos diferentes: enquanto a marca não está registrada
no INPI, qualquer outra empresa do Brasil pode registrar o mesmo nome
primeiro — e aí quem muda de nome, refaz fachada, embalagem e redes
sociais é quem chegou depois.</p>
<p style='margin:0 0 14px'>Como a {NOME_EMPRESA} está começando agora em {MUNICIPIO}, este é
justamente o melhor momento para verificar isso, antes de investir mais
em fachada, embalagem e redes sociais em torno de um nome ainda não
protegido.</p>
<p style='margin:0 0 14px'>Posso verificar no INPI se o nome da empresa está livre e te devolvo um
parecer curto, sem compromisso. Se estiver tudo livre, você fica sabendo
que está no caminho certo. Se houver risco, melhor descobrir agora do
que depois do negócio crescer.</p>
<p style='margin:0 0 14px'>Quer que eu verifique? É só responder este e-mail ou me chamar no
WhatsApp: <a href="https://wa.me/5567981644664?text=Ol%C3%A1%2C%20recebi%20o%20e-mail%20da%20VERTTI%20e%20quero%20a%20busca%20gratuita%20da%20minha%20marca">clique aqui</a></p>
<p style='margin:0 0 14px'>Abraço,</p>
<p style='margin:0'>Germano Coelho Ramos Rocha da Silva<br>
Agente da Propriedade Industrial — INPI nº 588<br>
VERTTI Consultoria · Campo Grande/MS<br>
vertticonsultoria.com.br</p>
""" + rodape

email2 = f"""
<p style='margin:0 0 14px'>Olá,</p>
<p style='margin:0 0 14px'>Semana passada te escrevi sobre a proteção do nome
"{NOME_EMPRESA}". Volto ao assunto por um motivo concreto.</p>
<p style='margin:0 0 14px'>O registro de marca no Brasil funciona por ordem de chegada: vale quem
deposita primeiro no INPI, não quem usa o nome há mais tempo. Na
prática, o cenário que mais atendo em 30 anos de INPI é este: a empresa
cresce, aparece no Google, e alguém — um concorrente, ou até um
oportunista profissional — registra o nome antes do dono. Aí o dono
original recebe uma notificação para parar de usar a própria marca.</p>
<p style='margin:0 0 14px'>Trocar de nome depois de estabelecido custa fachada, embalagens,
domínio, redes sociais e, o mais caro, a confiança do cliente que já
conhecia você.</p>
<p style='margin:0 0 14px'>O registro custa uma fração disso — e empresas do Simples, MEI e
pequeno porte pagam taxa reduzida de 60% no INPI.</p>
<p style='margin:0 0 14px'>A busca de viabilidade continua gratuita e sem compromisso. Respondendo
este e-mail, eu já te devolvo o parecer esta semana.</p>
<p style='margin:0 0 14px'>WhatsApp direto: <a href="https://wa.me/5567981644664?text=Ol%C3%A1%2C%20quero%20verificar%20se%20minha%20marca%20est%C3%A1%20em%20risco">clique aqui</a></p>
<p style='margin:0 0 14px'>Abraço,</p>
<p style='margin:0'>Germano Coelho Ramos Rocha da Silva<br>
Agente da Propriedade Industrial — INPI nº 588<br>
VERTTI Consultoria · Campo Grande/MS</p>
""" + rodape

email3 = f"""
<p style='margin:0 0 14px'>Olá,</p>
<p style='margin:0 0 14px'>Encerro por aqui o assunto da proteção do nome da {NOME_EMPRESA}, e
aproveito para deixar claro com quem você estaria falando, porque em
registro de marca a diferença entre um despachante e um especialista
aparece justamente quando surge um problema:</p>
<p style='margin:0 0 14px'>30+ anos de atuação em propriedade industrial. Agente da Propriedade
Industrial habilitado no INPI, registro nº 588. Já representei o
Brasil em comitês da OMPI, em Genebra, nas negociações internacionais
de tratados de propriedade industrial, e fui responsável pelo registro
da primeira marca coletiva indígena do Brasil, reconhecida
nacionalmente.</p>
<p style='margin:0 0 14px'>A VERTTI atende empresas em todo o Mato Grosso do Sul, com valor de
mercado local, e empresas recém-abertas como a {NOME_EMPRESA} contam
ainda com a taxa reduzida que o INPI aplica ao pequeno negócio.</p>
<p style='margin:0 0 14px'>Se quiser a busca de viabilidade, é só responder este e-mail. Se
preferir deixar para depois, sem problema — guarde este contato para
quando precisar.</p>
<p style='margin:0 0 14px'>WhatsApp: <a href="https://wa.me/5567981644664?text=Ol%C3%A1%2C%20quero%20aproveitar%20a%20condi%C3%A7%C3%A3o%20especial%20para%20registrar%20minha%20marca">clique aqui</a></p>
<p style='margin:0 0 14px'>Um abraço, e sucesso com a {NOME_EMPRESA},</p>
<p style='margin:0'>Germano Coelho Ramos Rocha da Silva<br>
Agente da Propriedade Industrial — INPI nº 588<br>
VERTTI Consultoria · Campo Grande/MS<br>
vertticonsultoria.com.br</p>
""" + rodape

r1 = r2 = r3 = True
qual = os.environ.get("QUAL_EMAIL", "todos")  # "1", "2", "3" ou "todos"

if qual in ("1", "todos"):
    r1 = enviar(f"A proteção do nome da {NOME_EMPRESA}", email1, "DIA 0")
if qual in ("2", "todos"):
    r2 = enviar("O que acontece quando outra empresa registra o seu nome primeiro", email2, "DIA 4")
if qual in ("3", "todos"):
    r3 = enviar(f"Fechando o assunto: registro de marca da {NOME_EMPRESA}", email3, "DIA 11")

print()
if r1 and r2 and r3:
    print("TODOS ENVIADOS")
else:
    print("HOUVE FALHA")
    sys.exit(1)
