import os
import sys
import secrets
import time
import threading
import shutil
import webbrowser
from datetime import datetime
import ctypes
import tkinter as tk
from tkinter import messagebox

from flask import Flask
from werkzeug.security import generate_password_hash
from sqlalchemy import text
from waitress import serve  # IMPORT DO SERVIDOR DE PRODUÇÃO
from utils import limpar_texto, registrar_log, formatar_quantidade, formatar_cupom, imprimir_direto_windows


# ==========================================
# 🛑 TRAVA DE CAMINHO ABSOLUTO (PYINSTALLER)
# ==========================================
# Garante que o banco de dados seja criado na pasta certa, mesmo quando for .exe
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

PASTA_INSTANCE = os.path.join(BASE_DIR, 'instance')
os.makedirs(PASTA_INSTANCE, exist_ok=True)
CAMINHO_BANCO_ABSOLUTO = os.path.join(PASTA_INSTANCE, 'estoque_pizzaria.db')

# --- CONFIGURAÇÕES DO FLASK ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + CAMINHO_BANCO_ABSOLUTO.replace('\\', '/')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = secrets.token_hex(32)

# Inicializando e "Conectando" as ferramentas no App
db.init_app(app)
migrate.init_app(app, db)
login_manager.init_app(app)
login_manager.login_view = 'login'

# ==========================================
# REGRAS DO FRONT-END (HTML) E FILTROS
# ==========================================
@app.template_filter('moeda_br')
def formatar_moeda(valor):
    if valor is None:
        valor = 0.0
    valor_str = f"{valor:,.2f}"
    valor_str = valor_str.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {valor_str}"

@app.context_processor
def inject_conf():
    try:
        conf = Configuracao.query.first()
    except Exception:
        conf = None
        
    logo_url = None
    if os.path.exists(os.path.join(UPLOAD_FOLDER, 'logo.png')):
        logo_url = f"/static/uploads/logo.png?v={int(time.time())}"
        
    return dict(
        empresa_nome=conf.nome_empresa if conf else "PizzaStock",
        logo_url=logo_url
    )

# ==========================================
# LIGANDO TODAS AS ROTAS
# ==========================================
registrar_rotas(app)


# ==========================================
# 🚀 LIGANDO TUDO (MODO PRODUÇÃO COM WAITRESS)
# ==========================================
if __name__ == '__main__':
    # 1. Liga o motor de backup inteligente em 2º plano
    thread_backup = threading.Thread(target=motor_de_backup_automatico, args=(app,), daemon=True)
    thread_backup.start()
    
    # 2. Inicia o cronômetro para abrir a tela da pizzaria no navegador (REATIVADO)
    threading.Timer(1.5, abrir_navegador).start()
    
    # 3. Liga o site com WAITRESS (Servidor Robusto de Produção)
    print("🚀 Iniciando o sistema Dominus PDV com o motor de produção (Waitress)...")
    serve(app, host='0.0.0.0', port=5000)