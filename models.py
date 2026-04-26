from extensions import db
from flask_login import UserMixin
from datetime import datetime, date, timedelta, timezone

# --- AUXILIAR: HORÁRIO DE BRASÍLIA (UTC-3) ---
def horario_brasil():
    return datetime.now(timezone(timedelta(hours=-3)))

# ==========================================
# NOVAS CLASSES DE RECEITA (SABOR E VARIAÇÕES)
# ==========================================

class Sabor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False) # Ex: Calabresa
    categoria = db.Column(db.String(50), default='TRADICIONAL')
    ativo = db.Column(db.Boolean, default=True)
    
    # Um sabor puxa todas as suas variações de tamanho
    variacoes = db.relationship('ReceitaVariacao', backref='sabor', lazy=True, cascade="all, delete-orphan")

class ReceitaVariacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sabor_id = db.Column(db.Integer, db.ForeignKey('sabor.id'), nullable=False)
    
    tamanho = db.Column(db.String(50), nullable=False) # Ex: Broto, Média, Grande
    preco_venda = db.Column(db.Float, default=0.0)
    
    # Liga essa variação aos ingredientes que ela gasta especificamente
    ingredientes = db.relationship('ReceitaIngrediente', backref='variacao', lazy=True, cascade="all, delete-orphan")

class ReceitaIngrediente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    variacao_id = db.Column(db.Integer, db.ForeignKey('receita_variacao.id'), nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False)
    quantidade = db.Column(db.Float, nullable=False)
    produto = db.relationship('Produto')

# ==========================================
# RESTANTE DO SISTEMA (MANTIDO INTACTO)
# ==========================================

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False) 
    data_vencimento = db.Column(db.DateTime, default=lambda: datetime.now() + timedelta(days=30))
    licenca_ativa = db.Column(db.Boolean, default=True)
    foto_perfil = db.Column(db.String(255), default='default.png')
    email = db.Column(db.String(120), unique=True, nullable=True)
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expiration = db.Column(db.DateTime, nullable=True)
    
class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.DateTime, default=horario_brasil)
    acao = db.Column(db.String(100))
    usuario = db.Column(db.String(50))
    descricao = db.Column(db.String(255))

class Configuracao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_empresa = db.Column(db.String(100), default='PIZZASTOCK')
    email_remetente = db.Column(db.String(100))
    senha_app_email = db.Column(db.String(100))
    caminho_backup = db.Column(db.String(255))
    horario_backup = db.Column(db.String(10))    
    taxa_entrega_padrao = db.Column(db.Float, default=0.0)
    nome_impressora = db.Column(db.String(100), default="Microsoft Print to PDF")
    taxa_credito = db.Column(db.Float, default=3.19) # Ex: 3.19%
    prazo_credito = db.Column(db.Integer, default=30) # Cai em 30 dias
    taxa_debito = db.Column(db.Float, default=1.99) # Ex: 1.99%
    prazo_debito = db.Column(db.Integer, default=1) # Cai em 1 dia

class Fornecedor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    contato = db.Column(db.String(50))

class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    unidade = db.Column(db.String(20), nullable=False)
    estoque_minimo = db.Column(db.Float, default=0.0)
    vender_direto = db.Column(db.Boolean, default=False)
    preco_venda = db.Column(db.Float, default=0.0)
    ativo = db.Column(db.Boolean, default=True)
    lotes = db.relationship('Lote', backref='produto', lazy=True)

    @property
    def total_atual(self):
        return sum(lote.quantidade for lote in self.lotes)

class Venda(db.Model):
    __tablename__ = 'venda' # Boa prática forçar o nome da tabela no banco

    # --- Identificação e Datas ---
    id = db.Column(db.Integer, primary_key=True)
    data_venda = db.Column(db.DateTime, default=horario_brasil)
    
    # --- Relacionamentos (Chaves Estrangeiras) ---
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=True)
    entregador_id = db.Column(db.Integer, db.ForeignKey('entregador.id'), nullable=True)
    
    # --- Dados Operacionais do Pedido ---
    status = db.Column(db.String(50), default='CONCLUÍDA') 
    vendedor = db.Column(db.String(50))    
    observacao = db.Column(db.String(255)) 
    
    # --- Composição do Preço (O "Recibo") ---
    subtotal = db.Column(db.Float, default=0.0)
    taxa_entrega = db.Column(db.Float, default=0.0)
    desconto = db.Column(db.Float, default=0.0)
    valor_total = db.Column(db.Float, default=0.0) # Subtotal + Entrega - Desconto
    
    # --- 💰 Gestão Financeira e Maquininha (NOVO) ---
    forma_pagamento = db.Column(db.String(50)) 
    valor_bruto = db.Column(db.Float, nullable=False, default=0.0)   # O que o cliente passou no cartão (geralmente igual ao valor_total)
    valor_liquido = db.Column(db.Float, nullable=False, default=0.0) # O que cai na conta da pizzaria (com desconto da taxa)
    taxa_aplicada = db.Column(db.Float, default=0.0)                 # Ex: 3.19 (Porcentagem cobrada pela maquininha)
    data_recebimento_previsto = db.Column(db.DateTime, nullable=True) # NOVO: Que dia esse dinheiro vai estar disponível?
    
    # --- Navegação do SQLAlchemy ---
    cliente = db.relationship('Cliente', backref='vendas')
    entregador = db.relationship('Entregador', backref='entregas')
    itens = db.relationship('VendaItem', backref='venda', lazy=True, cascade="all, delete-orphan")

class VendaItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    venda_id = db.Column(db.Integer, db.ForeignKey('venda.id'), nullable=False)
    
    # Como podemos vender Pizza (Receita) ou Coca-Cola (Produto), precisamos diferenciar:
    # NOTA: Com a nova arquitetura, quando tipo_item for 'RECEITA', 
    # o item_id apontará para o ID da Variacao (ReceitaVariacao), não do Sabor pai!
    tipo_item = db.Column(db.String(20)) # 'RECEITA' ou 'PRODUTO'
    item_id = db.Column(db.Integer, nullable=False) 
    
    nome_item = db.Column(db.String(100)) 
    quantidade = db.Column(db.Float, nullable=False)
    preco_unitario = db.Column(db.Float, nullable=False)
    preco_total = db.Column(db.Float, nullable=False)
    
    detalhes = db.Column(db.String(255))

class Entregador(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20))
    veiculo = db.Column(db.String(100))
    placa = db.Column(db.String(7))
    ativo = db.Column(db.Boolean, default=True)

    @property
    def zap_link(self):
        if not self.telefone: return "#"
        numero = ''.join(filter(str.isdigit, str(self.telefone))) 
        if not numero.startswith('55') and len(numero) >= 10:
            numero = '55' + numero 
        return f"https://wa.me/{numero}"

class Lote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quantidade = db.Column(db.Float, nullable=False)
    valor_custo = db.Column(db.Float, nullable=False)
    validade = db.Column(db.Date, nullable=False)
    data_entrada = db.Column(db.DateTime, default=horario_brasil)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False)
    fornecedor_id = db.Column(db.Integer, db.ForeignKey('fornecedor.id'))
    fornecedor_rel = db.relationship('Fornecedor', backref='lotes_fornecidos')

class Compra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.DateTime, default=horario_brasil)
    produto_nome = db.Column(db.String(100))
    quantidade = db.Column(db.Float)
    valor_unitario = db.Column(db.Float)
    valor_total = db.Column(db.Float)

class MovimentacaoCaixa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False) # 'ABERTURA', 'SANGRIA', 'REFORÇO'
    valor = db.Column(db.Float, nullable=False)
    data = db.Column(db.DateTime, default=datetime.now)
    observacao = db.Column(db.String(255))
    
    # É importante saber qual operador fez a sangria
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    usuario = db.relationship('Usuario', backref='movimentacoes_caixa')

class TabelaPreco(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    categoria = db.Column(db.String(50), unique=True, nullable=False) # Ex: TRADICIONAL
    preco_broto = db.Column(db.Float, default=0.0)
    preco_media = db.Column(db.Float, default=0.0)
    preco_grande = db.Column(db.Float, default=0.0)
    preco_familia = db.Column(db.Float, default=0.0)

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), nullable=True) # NOVO CAMPO
    telefone = db.Column(db.String(20), nullable=False)
    
    # ENDEREÇO DESMEMBRADO
    cep = db.Column(db.String(10), nullable=True)
    endereco = db.Column(db.String(255)) # Rua/Logradouro
    numero = db.Column(db.String(20), nullable=True)
    bairro = db.Column(db.String(100), nullable=True)
    cidade = db.Column(db.String(100), nullable=True)
    uf = db.Column(db.String(2), nullable=True)
    complemento = db.Column(db.String(100), nullable=True)
    taxa_entrega = db.Column(db.Float, default=0.0) # <-- GARANTA QUE ESSA LINHA ESTÁ AQUI
    referencia = db.Column(db.String(100))
    ativo = db.Column(db.Boolean, default=True)

    @property
    def zap_link(self):
        if not self.telefone: return "#"
        numero = ''.join(filter(str.isdigit, str(self.telefone)))
        if not numero.startswith('55') and len(numero) >= 10:
            numero = '55' + numero
        return f"https://wa.me/{numero}"

    @property
    def zap_link(self):
        if not self.telefone: return "#"
        numero = ''.join(filter(str.isdigit, str(self.telefone)))
        if not numero.startswith('55') and len(numero) >= 10:
            numero = '55' + numero
        return f"https://wa.me/{numero}"