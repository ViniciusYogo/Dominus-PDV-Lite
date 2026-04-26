import unicodedata
from flask_login import current_user
import win32print

def formatar_cupom(venda, config):
    nome_empresa = config.nome_empresa if config else "PIZZASTOCK"
    
    # 48 colunas é o padrão para impressoras térmicas de 80mm
    cupom = []
    cupom.append(nome_empresa.center(48))
    cupom.append("=" * 48)
    cupom.append(f"PEDIDO: #{venda.id}".center(48))
    
    data_str = venda.data_venda.strftime('%d/%m/%Y %H:%M:%S') if venda.data_venda else "N/D"
    cupom.append(data_str.center(48))
    cupom.append("-" * 48)
    
    # Agrupamento dos itens (Mesma lógica que você já fez no HTML)
    agrupamento = {}
    for item in venda.itens:
        nome = item.nome_item if item.nome_item else 'Item Desconhecido'
        if nome not in agrupamento:
            agrupamento[nome] = {'qtd': 0.0, 'valor': 0.0}
        agrupamento[nome]['qtd'] += item.quantidade
        agrupamento[nome]['valor'] += item.preco_total

    # Montando a lista de itens no formato texto
    cupom.append(f"{'QTD':<5} {'DESCRIÇÃO':<28} {'TOTAL':>13}")
    for nome, dados in agrupamento.items():
        qtd = str(int(dados['qtd']))
        nome_curto = nome[:27] # Corta o nome se for muito gigante
        valor = f"R$ {dados['valor']:.2f}".replace('.', ',')
        linha_item = f"{qtd:<5} {nome_curto:<28} {valor:>13}"
        cupom.append(linha_item)

    cupom.append("-" * 48)
    
    # Rodapé Financeiro
    cupom.append(f"TAXA DE ENTREGA: R$ {venda.taxa_entrega:.2f}".replace('.', ',').rjust(48))
    cupom.append(f"TOTAL: R$ {venda.valor_total:.2f}".replace('.', ',').rjust(48))
    cupom.append(f"PAGAMENTO: {venda.forma_pagamento}".rjust(48))
    
    cupom.append("=" * 48)
    cupom.append("Obrigado pela preferencia!".center(48))
    cupom.append("\n\n\n") # Espaço extra antes de cortar
    
    return "\n".join(cupom)

def imprimir_direto_windows(texto_cupom, nome_impressora):
    try:
        # Comando universal ESC/POS para acionar a guilhotina e cortar o papel
        cortar_papel = b'\x1d\x56\x00'
        
        # Converte o texto para a codificação da impressora térmica (cp850 pega os acentos BR)
        dados_impressao = texto_cupom.encode('cp850', errors='replace') + cortar_papel
        
        # Abre a comunicação com o Spooler do Windows
        hPrinter = win32print.OpenPrinter(nome_impressora)
        try:
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("Cupom Dominus PDV", None, "RAW"))
            try:
                win32print.StartPagePrinter(hPrinter)
                win32print.WritePrinter(hPrinter, dados_impressao)
                win32print.EndPagePrinter(hPrinter)
            finally:
                win32print.EndDocPrinter(hPrinter)
        finally:
            win32print.ClosePrinter(hPrinter)
            
        return True
    except Exception as e:
        print(f"Erro na impressão: {e}")
        return False

def formatar_quantidade(valor, unidade):
    if unidade.upper() in ['UN', 'UNIDADE', 'CX', 'CAIXA']:
        return int(float(valor))
    return float(valor)

def limpar_texto(texto):
    if not texto: return ""
    texto_limpo = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
    return texto_limpo.upper().strip()

def registrar_log(acao, descricao):
    # Importações locais para evitar o erro de "importação circular"
    from extensions import db
    from models import Log 
    
    user_nome = current_user.username if current_user.is_authenticated else "Sistema"
    novo_log = Log(acao=acao, descricao=descricao, usuario=user_nome)
    db.session.add(novo_log)
    db.session.commit()