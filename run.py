from waitress import serve
from app import app
import webbrowser
import threading
import time

def abrir_navegador():
    # Espera 2 segundos para dar tempo do servidor ligar completamente
    time.sleep(2) 
    webbrowser.open("http://localhost:5000")

if __name__ == '__main__':
    print("===================================================")
    print(" 🍕 SERVIDOR PIZZASTOCK ESTÁ RODANDO ")
    print(" ⚠️ MANTENHA ESTA JANELA ABERTA PARA O SISTEMA FUNCIONAR ")
    print(" Para desligar o sistema, basta fechar esta janela. ")
    print("===================================================")
    
    # Abre o navegador em segundo plano
    threading.Thread(target=abrir_navegador).start()
    
    # Liga o servidor de produção Waitress
    serve(app, host='0.0.0.0', port=5000)