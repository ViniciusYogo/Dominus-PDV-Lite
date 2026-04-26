import os
import tkinter as tk
from tkinter import filedialog
from datetime import datetime, date, timedelta
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import render_template, request, redirect, url_for, flash, send_file, jsonify
import json
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, text
from werkzeug.utils import secure_filename
from extensions import db, login_manager
# IMPORTAÇÕES ATUALIZADAS AQUI:
from models import (Usuario, Sabor, ReceitaVariacao, ReceitaIngrediente, Produto, 
                    Entregador, Lote, Compra, Cliente, Fornecedor, Log, Configuracao,
                    Venda, VendaItem, MovimentacaoCaixa, TabelaPreco)
from utils import limpar_texto, registrar_log, formatar_quantidade
from validar_licenca import checar_status_licenca # Importa seu validador
import win32print 
import sys 

UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def registrar_rotas(app):

    # ==========================================
    # 🛡️ MIDDLEWARE DE SEGURANÇA (A TRANCA)
    # ==========================================
    @app.before_request
    def verificar_licenca_sistema():
        rotas_livres = ['tela_bloqueio', 'static', 'revalidar_licenca']
        
        if request.endpoint and request.endpoint not in rotas_livres:
            if not checar_status_licenca():
                return redirect(url_for('tela_bloqueio'))

    # ==========================================
    # 🛑 ROTA DA TELA DE BLOQUEIO
    # ==========================================
    @app.route('/acesso-suspenso')
    def tela_bloqueio():
        # Certifique-se de que o bloqueado.html existe na pasta templates
        return render_template('bloqueio.html')

    # ==========================================
    # 🔄 ROTA PARA FORÇAR NOVA VALIDAÇÃO
    # ==========================================
    @app.route('/revalidar_licenca')
    def revalidar_licenca():
        # Caminho do seu arquivo de cache
        arquivo_cache = "cache_licenca.json"
        
        # Se o cache existir (estiver travando o cliente), nós apagamos ele
        if os.path.exists(arquivo_cache):
            try:
                os.remove(arquivo_cache)
            except Exception as e:
                print(f"Erro ao apagar cache: {e}")
                
        # Redireciona o cliente de volta para o login.
        # Como o cache sumiu, o @app.before_request vai bater na API da nuvem na mesma hora!
        return redirect(url_for('login'))

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(Usuario, int(user_id))

    # --- AUTENTICAÇÃO E CONFIGURAÇÃO ---
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            nome_bruto = request.form.get('username')
            username_limpo = limpar_texto(nome_bruto).lower()
            senha_digitada = request.form.get('password')
            
            user = Usuario.query.filter_by(username=username_limpo).first()
            
            if user and check_password_hash(user.password, senha_digitada):
                login_user(user)
                registrar_log("LOGIN", f"O usuário {user.username} entrou no sistema.")
                return redirect(url_for('hub_inicial'))
                
            flash('Credenciais inválidas.', 'danger')
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        registrar_log("LOGOUT", "Usuário encerrou a sessão.")
        logout_user()
        return redirect(url_for('login'))
    
    @app.route('/esqueci_senha', methods=['GET', 'POST'])
    def esqueci_senha():
        if request.method == 'POST':
            email_digitado = request.form.get('email').strip().lower()
            user = Usuario.query.filter_by(email=email_digitado).first()
            
            if user:
                conf = Configuracao.query.first()
                if not conf or not conf.email_remetente or not conf.senha_app_email:
                    flash('O sistema não possui um e-mail de disparo configurado. Contate o suporte.', 'danger')
                    return redirect(url_for('login'))

                token = secrets.token_hex(16)
                user.reset_token = token
                user.reset_token_expiration = datetime.now() + timedelta(hours=1)
                db.session.commit()
                
                link = url_for('resetar_senha', token=token, _external=True)
                
                remetente = conf.email_remetente
                senha_app = conf.senha_app_email
                destinatario = user.email

                msg = MIMEMultipart()
                msg['From'] = remetente
                msg['To'] = destinatario
                msg['Subject'] = "🔑 Recuperação de Senha - PizzaStock"

                corpo = f"""Olá {user.username.capitalize()}!
                
Você solicitou a recuperação de senha no PizzaStock.
Clique no link abaixo para criar uma nova senha (válido por 1 hora):

{link}

Se não foi você, ignore este e-mail."""
                msg.attach(MIMEText(corpo, 'plain', 'utf-8'))

                try:
                    server = smtplib.SMTP('smtp.gmail.com', 587)
                    server.starttls()
                    server.login(remetente, senha_app)
                    server.send_message(msg)
                    server.quit()
                    registrar_log("SEGURANÇA", f"Link de recuperação enviado para {destinatario}")
                except Exception as e:
                    print(f"Erro no envio de e-mail: {e}")
            
            flash('Se o e-mail estiver cadastrado, você receberá o link de recuperação em instantes.', 'info')
            return redirect(url_for('login'))
            
        return render_template('esqueci_senha.html')

    @app.route('/resetar_senha/<token>', methods=['GET', 'POST'])
    def resetar_senha(token):
        user = Usuario.query.filter_by(reset_token=token).first()
        
        if not user or not user.reset_token_expiration or user.reset_token_expiration < datetime.now():
            flash('O link de recuperação é inválido ou expirou. Solicite um novo.', 'danger')
            return redirect(url_for('esqueci_senha'))
            
        if request.method == 'POST':
            nova_senha = request.form.get('nova_senha')
            user.password = generate_password_hash(nova_senha)
            user.reset_token = None
            user.reset_token_expiration = None
            db.session.commit()
            registrar_log("SEGURANÇA", f"Usuário '{user.username}' redefiniu a senha via e-mail.")
            flash('✅ Senha redefinida com sucesso! Você já pode fazer login.', 'success')
            return redirect(url_for('login'))
            
        return render_template('resetar_senha.html', token=token)
    
    @app.route('/perfil', methods=['GET', 'POST'])
    @login_required
    def perfil():
        if request.method == 'POST':
            foto = request.files.get('foto_perfil')
            if foto and foto.filename != '':
                extensao = foto.filename.rsplit('.', 1)[1].lower()
                novo_nome = f"perfil_user_{current_user.id}.{extensao}"
                pasta_destino = os.path.join(app.root_path, 'static', 'uploads')
                os.makedirs(pasta_destino, exist_ok=True)
                caminho_completo = os.path.join(pasta_destino, novo_nome)
                foto.save(caminho_completo)
                
                current_user.foto_perfil = novo_nome
                db.session.commit()
                flash('Sua foto de perfil foi atualizada com sucesso!', 'success')
                return redirect(url_for('perfil'))
                
        return render_template('perfil.html')

    @app.route('/mudar_senha', methods=['POST'])
    @login_required
    def mudar_senha():
        senha_atual = request.form.get('senha_atual')
        nova_senha = request.form.get('nova_senha')
        if not check_password_hash(current_user.password, senha_atual):
            flash('❌ A senha atual está incorreta. Nenhuma alteração foi feita.', 'danger')
            return redirect(url_for('configuracoes')) 
        current_user.password = generate_password_hash(nova_senha)
        db.session.commit()
        registrar_log("SEGURANÇA", f"O usuário '{current_user.username}' alterou a própria senha.")
        flash('✅ Senha alterada com sucesso!', 'success')
        return redirect(url_for('configuracoes'))


    @app.route('/configuracoes', methods=['GET', 'POST'])
    @login_required
    def gerenciar_configuracoes():
        # Apenas administradores podem mexer nas configurações globais
        if not current_user.is_admin:
            flash("⛔ Acesso negado.", "danger")
            return redirect(url_for('dashboard'))
        
        # Puxa as configurações atuais do banco
        conf = Configuracao.query.first()

        if request.method == 'POST':
            if not conf:
                conf = Configuracao()
                db.session.add(conf)
            
            # 1. Salva Dados da Empresa
            conf.nome_empresa = request.form.get('nome_empresa', 'PIZZASTOCK').upper().strip()
            
            # 2. Salva a Taxa de Entrega
            taxa_raw = request.form.get('taxa_entrega_padrao', '0')
            conf.taxa_entrega_padrao = float(str(taxa_raw or '0').replace(',', '.'))
            
            # 3. E-mail
            conf.email_remetente = request.form.get('email_remetente', '').strip()
            conf.senha_app_email = request.form.get('senha_app_email', '').strip()
            
            # 4. Backup Automático
            conf.caminho_backup = request.form.get('caminho_backup', '').strip()
            conf.horario_backup = request.form.get('horario_backup', '').strip()

            # 5. Impressora
            conf.nome_impressora = request.form.get('nome_impressora', '')

            # 🟢 6. NOVO: CONFIGURAÇÕES FINANCEIRAS (MAQUININHA) 🟢
            try:
                # Crédito
                taxa_cred_raw = request.form.get('taxa_credito', '3.19')
                conf.taxa_credito = float(str(taxa_cred_raw or '0').replace(',', '.'))
                conf.prazo_credito = int(request.form.get('prazo_credito', '30') or 0)

                # Débito
                taxa_deb_raw = request.form.get('taxa_debito', '1.99')
                conf.taxa_debito = float(str(taxa_deb_raw or '0').replace(',', '.'))
                conf.prazo_debito = int(request.form.get('prazo_debito', '1') or 0)
            except ValueError:
                flash("⚠️ Erro ao salvar taxas financeiras. Verifique se digitou apenas números.", "warning")
            
            db.session.commit()
            # Registrar_log (se você tiver essa função)
            flash("✅ Configurações atualizadas com sucesso!", "success")
            return redirect(url_for('gerenciar_configuracoes'))

        # Busca a lista de impressoras reais do Windows
        try:
            import win32print
            lista_raw = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL, None, 1)
            impressoras_windows = [imp[2] for imp in lista_raw]
        except Exception:
            impressoras_windows = ["Microsoft Print to PDF"]

        return render_template('configuracoes.html', conf=conf, impressoras_windows=impressoras_windows)


    
    @app.route('/selecionar_pasta')
    @login_required
    def selecionar_pasta():
        import tkinter as tk
        from tkinter import filedialog
        import threading
        import os

        resultado = {"pasta": ""}

        def abrir_janela():
            try:
                root = tk.Tk()
                root.withdraw()
                # Força a janela a ser a primeira de todas no Windows
                root.attributes('-topmost', True) 
                
                # Abre o seletor
                pasta = filedialog.askdirectory(title="Onde deseja salvar os backups?")
                
                if pasta:
                    resultado["pasta"] = os.path.normpath(pasta)
                
                root.destroy()
            except Exception as e:
                print(f"❌ Erro interno no Tkinter: {e}")

        # Criamos a thread para não travar o Waitress
        thread = threading.Thread(target=abrir_janela)
        thread.start()
        thread.join() # Espera o usuário decidir

        if resultado["pasta"]:
            # Salva o caminho no banco de dados para o motor de backup usar depois
            from models import Configuracao
            conf = Configuracao.query.first()
            if conf:
                conf.caminho_backup = resultado["pasta"]
                db.session.commit()
                return jsonify({'sucesso': True, 'caminho': resultado["pasta"]})
        
        return jsonify({'sucesso': False, 'erro': 'Nenhuma pasta selecionada ou ação cancelada.'})

    # --- DASHBOARD E PRODUTOS ---
    @app.route('/')
    @login_required
    def hub_inicial():
        return render_template('hub.html')

    @app.route('/dashboard')
    @login_required
    def dashboard():
        hoje = date.today()
        inicio_mes = hoje.replace(day=1)
        
        # 1. Alertas de Estoque e Validade
        alertas_validade = Lote.query.join(Produto).filter(
                Lote.validade <= hoje + timedelta(days=7), 
                Produto.ativo == True, Lote.quantidade > 0  
            ).order_by(Lote.validade.asc()).all()
        
        todos_produtos = Produto.query.filter_by(ativo=True).order_by(Produto.nome).all()
        alertas_estoque = [p for p in todos_produtos if p.total_atual <= p.estoque_minimo]
        
        # 2. Capital e Gastos
        lotes_ativos = Lote.query.join(Produto).filter(Produto.ativo == True).all()
        valor_total = sum(l.quantidade * l.valor_custo for l in lotes_ativos)
        gastos_mes = db.session.query(func.sum(Compra.valor_total)).filter(Compra.data >= inicio_mes).scalar() or 0.0
        
        # 3. Faturamento e Vendas do Mês
        vendas_mes = Venda.query.filter(Venda.data_venda >= inicio_mes, Venda.status == 'CONCLUÍDA').all()
        faturamento_mes = sum(v.valor_total for v in vendas_mes)
        qtd_vendas = len(vendas_mes)
        ticket_medio = (faturamento_mes / qtd_vendas) if qtd_vendas > 0 else 0.0
        
        # Representa o Saldo de Caixa (Entradas - Compras)
        lucro_bruto = faturamento_mes - gastos_mes

        # 4. Faturamento Diário (Gráfico de Linha)
        vendas_por_dia = {}
        for v in vendas_mes:
            dia_str = v.data_venda.strftime('%d/%m')
            vendas_por_dia[dia_str] = vendas_por_dia.get(dia_str, 0.0) + v.valor_total
            
        dias_ordenados = sorted(vendas_por_dia.keys())
        labels_faturamento = dias_ordenados
        valores_faturamento = [vendas_por_dia[d] for d in dias_ordenados]

        # 5. Prejuízo / Descartes
        todas_receitas = Sabor.query.filter_by(ativo=True).order_by(Sabor.nome).all()
        logs_descarte = Log.query.filter(Log.acao == 'DESCARTE', Log.data >= inicio_mes).all()
        prejuizo_mes = 0.0
        for log in logs_descarte:
            try: 
                prejuizo_mes += float(log.descricao.split('R$ ')[1])
            except: 
                pass
        
        # 6. OTIMIZAÇÃO DE PERFORMANCE: Pizzas/Pratos Mais Vendidos (Top 10)
        itens_vendidos = db.session.query(
            VendaItem.nome_item, 
            func.sum(VendaItem.quantidade).label('total_vendido')
        ).join(Venda).filter(
            Venda.data_venda >= inicio_mes, 
            Venda.status == 'CONCLUÍDA'
        ).group_by(
            VendaItem.nome_item
        ).order_by(
            func.sum(VendaItem.quantidade).desc()
        ).limit(10).all()

        labels_vendas = [item.nome_item for item in itens_vendidos]
        valores_vendas = [float(item.total_vendido) for item in itens_vendidos]

        # 7. Gastos por Fornecedor
        gastos_fornecedores = db.session.query(
            Fornecedor.nome, 
            func.sum(Lote.quantidade * Lote.valor_custo)
        ).join(Lote, Fornecedor.id == Lote.fornecedor_id).group_by(Fornecedor.nome).all()
        
        labels_fornecedores = [f[0] for f in gastos_fornecedores]
        valores_fornecedores = [float(f[1]) for f in gastos_fornecedores]

        # 8. NOVO: Formas de Pagamento
        vendas_pagamento = db.session.query(
            Venda.forma_pagamento, 
            func.sum(Venda.valor_total)
        ).filter(
            Venda.data_venda >= inicio_mes, 
            Venda.status == 'CONCLUÍDA'
        ).group_by(Venda.forma_pagamento).all()

        labels_pagamento = [p[0] for p in vendas_pagamento]
        valores_pagamento = [float(p[1]) for p in vendas_pagamento]

        # 9. Evolução de Gastos (6 Meses)
        meses_labels, gastos_meses = [], []
        for i in range(5, -1, -1):
            m = hoje.month - i
            a = hoje.year
            if m <= 0: 
                m += 12
                a -= 1
            primeiro_dia = date(a, m, 1)
            prox_primeiro_dia = date(a + 1, 1, 1) if m == 12 else date(a, m + 1, 1)
            gasto = db.session.query(func.sum(Compra.valor_total)).filter(
                Compra.data >= primeiro_dia, Compra.data < prox_primeiro_dia
            ).scalar() or 0.0
            
            meses_labels.append(f"{m:02d}/{a}")
            gastos_meses.append(float(gasto))

        return render_template('dashboard.html', 
                               alertas_validade=alertas_validade, alertas_estoque=alertas_estoque,
                               total_itens=len(todos_produtos), valor_total=valor_total,
                               gastos_mes=gastos_mes, prejuizo_mes=prejuizo_mes, hoje=hoje,
                               todos_produtos=todos_produtos, todas_receitas=todas_receitas,
                               faturamento_mes=faturamento_mes, lucro_bruto=lucro_bruto, 
                               ticket_medio=ticket_medio, qtd_vendas=qtd_vendas,
                               labels_faturamento=labels_faturamento, valores_faturamento=valores_faturamento,
                               labels_vendas=labels_vendas, valores_vendas=valores_vendas,
                               labels_fornecedores=labels_fornecedores, valores_fornecedores=valores_fornecedores,
                               labels_pagamento=labels_pagamento, valores_pagamento=valores_pagamento,
                               meses_labels=meses_labels, gastos_meses=gastos_meses)

    @app.route('/produtos')
    @login_required
    def listar_produtos():
        produtos = Produto.query.filter_by(ativo=True).order_by(Produto.nome).all()
        return render_template('produtos.html', produtos=produtos)
    
    @app.route('/novo_produto')
    @login_required
    def novo_produto():
        # Apenas renderiza a tela de cadastro vazia
        return render_template('novo_produto.html')

    @app.route('/cadastrar_produto', methods=['POST'])
    @login_required
    def cadastrar_produto():
        nome_original = request.form.get('nome').strip().upper()
        nome_comparacao = limpar_texto(nome_original)
        unidade = request.form.get('unidade')
        minimo = formatar_quantidade(request.form.get('estoque_minimo', 0), unidade)
        vender_direto = request.form.get('vender_direto') == 'on'
        preco_venda = float(request.form.get('preco_venda', 0) or 0.0)
        
        if minimo < 0 or minimo > 9999:
            flash("❌ Erro: O estoque mínimo deve ser entre 0 e 9999!", "danger")
            return redirect(url_for('listar_produtos'))
        
        todos_produtos = Produto.query.all()
        produto_existente = None
        for p in todos_produtos:
            if limpar_texto(p.nome) == nome_comparacao:
                produto_existente = p
                break
                
        if produto_existente:
            if produto_existente.ativo:
                flash(f"⚠️ O produto '{produto_existente.nome}' já existe!", "warning")
                return redirect(url_for('listar_produtos'))
            else:
                if produto_existente.unidade != unidade:
                    nome_antigo = produto_existente.nome
                    produto_existente.nome = f"{nome_antigo} (ANTIGO - {produto_existente.unidade})"
                    db.session.commit()
                    novo = Produto(nome=nome_original, unidade=unidade, estoque_minimo=minimo, vender_direto=vender_direto, preco_venda=preco_venda)
                    db.session.add(novo)
                    db.session.commit()
                    registrar_log("CADASTRO", f"Produto {nome_original} recriado com nova unidade ({unidade}).")
                    flash(f"Produto {nome_original} recriado.", "success")
                    return redirect(url_for('listar_produtos'))
                else:
                    produto_existente.ativo = True
                    produto_existente.estoque_minimo = minimo
                    produto_existente.vender_direto = vender_direto
                    produto_existente.preco_venda = preco_venda
                    db.session.commit()
                    registrar_log("CADASTRO", f"Produto {nome_original} reativado.")
                    flash(f"Produto {nome_original} reativado!", "success")
                    return redirect(url_for('listar_produtos'))
        
        if nome_original:
            novo = Produto(nome=nome_original, unidade=unidade, estoque_minimo=minimo, vender_direto=vender_direto, preco_venda=preco_venda)
            db.session.add(novo)
            db.session.commit()
            registrar_log("CADASTRO", f"Produto {nome_original} adicionado.")
            flash(f"Produto {nome_original} cadastrado com sucesso!", "success")
        return redirect(url_for('listar_produtos'))
    
    @app.route('/desperdicio')
    @login_required
    def desperdicio():
        if not current_user.is_admin: return redirect(url_for('hub_inicial'))
        todos_produtos = Produto.query.filter_by(ativo=True).order_by(Produto.nome).all()
        todas_receitas = Sabor.query.filter_by(ativo=True).order_by(Sabor.nome).all()
        return render_template('desperdicio.html', todos_produtos=todos_produtos, todas_receitas=todas_receitas)

    @app.route('/produto/historico/<int:id>')
    @login_required
    def historico_produto(id):
        produto = Produto.query.get_or_404(id)
        compras = Compra.query.filter_by(produto_nome=produto.nome).order_by(Compra.data.desc()).all()
        logs = Log.query.filter(Log.descricao.contains(produto.nome)).order_by(Log.data.desc()).all()
        return render_template('historico_produto.html', produto=produto, compras=compras, logs=logs)

    @app.route('/deletar_produto/<int:id>')
    @login_required
    def deletar_produto(id):
        if not current_user.is_admin:
            flash("⛔ Acesso negado: Apenas administradores.", "danger")
            return redirect(url_for('listar_produtos'))
        p = Produto.query.get_or_404(id)
        nome_prod = p.nome
        p.ativo = False 
        db.session.commit()
        registrar_log("EXCLUSÃO", f"Produto {nome_prod} desativado.")
        flash(f"Produto {nome_prod} removido com sucesso!", "info")
        return redirect(url_for('listar_produtos'))

    @app.route('/editar_produto/<int:id>', methods=['GET', 'POST'])
    @login_required
    def editar_produto(id):
        p = Produto.query.get_or_404(id)
        if request.method == 'POST':
            velho_nome = p.nome
            novo_nome = request.form.get('nome').strip().upper()
            nome_comparacao = limpar_texto(novo_nome)
            novo_minimo = formatar_quantidade(request.form.get('estoque_minimo', 0), p.unidade)
            p.vender_direto = request.form.get('vender_direto') == 'on'
            p.preco_venda = float(request.form.get('preco_venda', 0) or 0.0)
            
            if novo_minimo < 0 or novo_minimo > 9999:
                flash("❌ Erro: Estoque mínimo inválido!", "danger")
                return redirect(url_for('editar_produto', id=p.id))

            todos_produtos = Produto.query.all()
            for prod in todos_produtos:
                if prod.id != p.id and limpar_texto(prod.nome) == nome_comparacao:
                    flash(f"⚠️ O nome '{prod.nome}' já está em uso!", "warning")
                    return redirect(url_for('editar_produto', id=p.id))

            p.nome = novo_nome
            p.estoque_minimo = novo_minimo
            db.session.commit()
            registrar_log("EDIÇÃO", f"Produto {velho_nome} alterado para {p.nome}")
            flash("Produto atualizado!", "success")
            return redirect(url_for('listar_produtos'))
        return render_template('editar_produto.html', produto=p)

    # ==========================================
    # GESTÃO DE SABORES E TABELA DE PREÇOS
    # ==========================================
    @app.route('/receitas', methods=['GET', 'POST'])
    @login_required
    def gerenciar_receitas():
        if request.method == 'POST':
            nome = request.form.get('nome').upper().strip()
            categoria = request.form.get('categoria').upper().strip()
            
            # 🔥 TRAVA DE SEGURANÇA: Impede cadastrar o mesmo sabor duas vezes
            sabor_existente = Sabor.query.filter_by(nome=nome, ativo=True).first()
            if sabor_existente:
                flash(f"⚠️ O sabor '{nome}' já está cadastrado no cardápio!", "warning")
                return redirect(url_for('gerenciar_receitas'))
            
            # 1. Puxa os preços oficiais da categoria escolhida
            tabela = TabelaPreco.query.filter_by(categoria=categoria).first()
            
            # Se a tabela não existir, avisa o usuário (Trava de segurança)
            if not tabela:
                flash(f"⚠️ A categoria '{categoria}' não tem preços definidos na tabela acima!", "danger")
                return redirect(url_for('gerenciar_receitas'))
                
            # 2. Cria o sabor base
            novo_sabor = Sabor(nome=nome, categoria=categoria)
            db.session.add(novo_sabor)
            db.session.flush() # Pega o ID gerado sem fazer commit final
            
            # 3. Cria os 4 tamanhos automaticamente copiando os valores da Tabela de Preços
            db.session.add(ReceitaVariacao(sabor_id=novo_sabor.id, tamanho="BROTO", preco_venda=tabela.preco_broto))
            db.session.add(ReceitaVariacao(sabor_id=novo_sabor.id, tamanho="MÉDIA", preco_venda=tabela.preco_media))
            db.session.add(ReceitaVariacao(sabor_id=novo_sabor.id, tamanho="GRANDE", preco_venda=tabela.preco_grande))
            db.session.add(ReceitaVariacao(sabor_id=novo_sabor.id, tamanho="FAMÍLIA", preco_venda=tabela.preco_familia))
            
            db.session.commit()
            registrar_log("CADASTRO", f"Novo sabor: {nome} ({categoria})")
            flash(f'Sabor {nome} adicionado com sucesso usando os preços da categoria {categoria}!', 'success')
            return redirect(url_for('gerenciar_receitas'))
            
        # Na hora de exibir a tela (GET), manda os Sabores e as Tabelas de Preço pro HTML
        todos_sabores = Sabor.query.filter_by(ativo=True).order_by(Sabor.nome).all()
        tabelas = TabelaPreco.query.order_by(TabelaPreco.categoria).all()
        return render_template('receitas.html', receitas=todos_sabores, tabelas=tabelas)

    @app.route('/salvar_tabela_preco', methods=['POST'])
    @login_required
    def salvar_tabela_preco():
        if not current_user.is_admin: 
            return redirect(url_for('gerenciar_receitas'))
            
        categoria = request.form.get('categoria').upper().strip()
        p_broto = float(request.form.get('preco_broto', 0))
        p_media = float(request.form.get('preco_media', 0))
        p_grande = float(request.form.get('preco_grande', 0))
        p_familia = float(request.form.get('preco_familia', 0))
        
        # Procura se essa categoria (ex: TRADICIONAL) já existe
        tabela = TabelaPreco.query.filter_by(categoria=categoria).first()
        
        # Se não existir, cria uma nova linha no banco
        if not tabela:
            tabela = TabelaPreco(categoria=categoria)
            db.session.add(tabela)
            
        # Atualiza os valores da Tabela Mestra
        tabela.preco_broto = p_broto
        tabela.preco_media = p_media
        tabela.preco_grande = p_grande
        tabela.preco_familia = p_familia
        
        # 🔥 A MÁGICA DE VERDADE AQUI: 
        # Varre o banco e atualiza TODAS as pizzas antigas que já estão cadastradas com essa categoria
        sabores = Sabor.query.filter_by(categoria=categoria).all()
        contador_atualizados = 0
        for sabor in sabores:
            for var in sabor.variacoes:
                if var.tamanho == "BROTO": var.preco_venda = p_broto
                elif var.tamanho == "MÉDIA": var.preco_venda = p_media
                elif var.tamanho == "GRANDE": var.preco_venda = p_grande
                elif var.tamanho == "FAMÍLIA": var.preco_venda = p_familia
            contador_atualizados += 1
                
        db.session.commit()
        registrar_log("ATUALIZAÇÃO EM LOTE", f"Tabela {categoria} atualizou {contador_atualizados} pizzas.")
        flash(f"✅ Tabela {categoria} salva! {contador_atualizados} pizzas foram atualizadas com os novos preços.", "success")
        return redirect(url_for('gerenciar_receitas'))

    @app.route('/deletar_tabela/<int:id>')
    @login_required
    def deletar_tabela(id):
        if not current_user.is_admin: 
            return redirect(url_for('gerenciar_receitas'))
            
        tabela = TabelaPreco.query.get_or_404(id)
        db.session.delete(tabela)
        db.session.commit()
        flash("Categoria de preços removida do painel.", "info")
        return redirect(url_for('gerenciar_receitas'))

    @app.route('/receita/<int:id>', methods=['GET', 'POST'])
    @login_required
    def detalhes_receita(id):
        # A URL chama 'receita' para não quebrar links, mas internamente carrega o 'Sabor'
        receita = Sabor.query.get_or_404(id)
        if request.method == 'POST':
            # Recebe o ID específico do tamanho (Variação)
            variacao_id = request.form.get('variacao_id')
            produto_id = request.form.get('produto_id')
            prod = Produto.query.get(produto_id)
            qtd_digitada = float(request.form.get('quantidade', 0) or 0)
            
            if qtd_digitada <= 0 or qtd_digitada > 9999:
                flash("❌ Quantidade inválida.", "danger")
                return redirect(url_for('detalhes_receita', id=id))
            
            quantidade_final = qtd_digitada / 1000.0 if prod.unidade in ['KG', 'L'] else qtd_digitada
                
            ingrediente_existente = ReceitaIngrediente.query.filter_by(variacao_id=variacao_id, produto_id=produto_id).first()
            if ingrediente_existente:
                ingrediente_existente.quantidade += quantidade_final
            else:
                novo_ingrediente = ReceitaIngrediente(variacao_id=variacao_id, produto_id=produto_id, quantidade=quantidade_final)
                db.session.add(novo_ingrediente)
                
            db.session.commit()
            flash(f'{prod.nome} adicionado ao tamanho selecionado!', 'success')
            return redirect(url_for('detalhes_receita', id=id))
            
        produtos = Produto.query.filter_by(ativo=True).order_by(Produto.nome).all()
        return render_template('receita_detalhes.html', receita=receita, produtos=produtos)

    @app.route('/remover_ingrediente/<int:id>')
    @login_required
    def remover_ingrediente(id):
        ingrediente = ReceitaIngrediente.query.get_or_404(id)
        # Redireciona de volta para a tela do Sabor pai
        sabor_id = ingrediente.variacao.sabor_id 
        db.session.delete(ingrediente)
        db.session.commit()
        flash('Ingrediente removido do tamanho.', 'warning')
        return redirect(url_for('detalhes_receita', id=sabor_id))

    @app.route('/editar_receita/<int:id>', methods=['POST'])
    @login_required
    def editar_receita(id):
        s = Sabor.query.get_or_404(id)
        s.nome = request.form.get('nome').upper().strip()
        # Não permitimos mais alterar a categoria por aqui para não quebrar a sincronia com a TabelaPreco
        # Se ele quiser mudar a categoria, ele tem que apagar e recriar o sabor.
        db.session.commit()
        flash('Nome do Sabor atualizado!', 'success')
        return redirect(url_for('detalhes_receita', id=id))

    @app.route('/deletar_receita/<int:id>')
    @login_required
    def deletar_receita(id):
        s = Sabor.query.get_or_404(id)
        s.ativo = False 
        db.session.commit()
        flash(f'Ficha técnica de "{s.nome}" arquivada!', 'info')
        return redirect(url_for('gerenciar_receitas'))

    @app.route('/adicionar_tamanho_sabor/<int:sabor_id>', methods=['POST'])
    @login_required
    def adicionar_tamanho_sabor(sabor_id):
        # Como automatizamos a criação dos 4 tamanhos, essa rota dificilmente será usada no dia a dia,
        # mas mantemos ela aqui caso você queira adicionar um tamanho bizarro tipo "GIGANTE" manualmente.
        sabor = Sabor.query.get_or_404(sabor_id)
        tamanho = request.form.get('tamanho').upper().strip()
        preco = float(request.form.get('preco_venda', 0))
        
        existe = ReceitaVariacao.query.filter_by(sabor_id=sabor_id, tamanho=tamanho).first()
        if existe:
            flash(f'⚠️ O tamanho {tamanho} já existe neste sabor!', 'warning')
        else:
            nova_var = ReceitaVariacao(sabor_id=sabor_id, tamanho=tamanho, preco_venda=preco)
            db.session.add(nova_var)
            db.session.commit()
            flash(f'✅ Tamanho {tamanho} adicionado com sucesso ao sabor {sabor.nome}!', 'success')
            
        return redirect(url_for('detalhes_receita', id=sabor_id))

    @app.route('/remover_tamanho/<int:var_id>')
    @login_required
    def remover_tamanho(var_id):
        var = ReceitaVariacao.query.get_or_404(var_id)
        sabor_id = var.sabor_id
        
        # Isso deleta o tamanho e, por cascata, todos os ingredientes ligados a ele
        db.session.delete(var)
        db.session.commit()
        flash('🗑️ Tamanho e seus ingredientes removidos com sucesso!', 'info')
        return redirect(url_for('detalhes_receita', id=sabor_id))
        
    @app.route('/baixa_receita', methods=['POST'])
    @login_required
    def baixa_receita():
        # A baixa agora acontece na Variação (Tamanho específico)
        variacao_id = request.form.get('variacao_id') 
        qtd_pizzas = float(request.form.get('quantidade', 1))
        motivo = request.form.get('motivo', 'USO')
        variacao = ReceitaVariacao.query.get(variacao_id)
        
        if not variacao or not variacao.ingredientes:
            flash(f'Esse tamanho não possui ingredientes cadastrados!', 'danger')
            return redirect(url_for('dashboard'))
        
        erros = []
        for ing in variacao.ingredientes:
            qtd_necessaria = ing.quantidade * qtd_pizzas
            if qtd_necessaria > ing.produto.total_atual:
                erros.append(f"{ing.produto.nome} (Falta {qtd_necessaria - ing.produto.total_atual:.3f} {ing.produto.unidade})")
        
        nome_completo = f"{variacao.tamanho} - {variacao.sabor.nome}"
        if erros:
            flash(f'Estoque insuficiente para {qtd_pizzas}x {nome_completo}. Faltam: {", ".join(erros)}', 'danger')
            return redirect(url_for('dashboard'))
            
        valor_prejuizo = 0.0
        for ing in variacao.ingredientes:
            qtd_necessaria = ing.quantidade * qtd_pizzas
            restante = qtd_necessaria
            lotes = Lote.query.filter_by(produto_id=ing.produto_id).order_by(Lote.validade.asc()).all()
            for lote in lotes:
                if restante <= 0: break
                qtd_tirada = min(lote.quantidade, restante)
                if motivo == 'DESCARTE': valor_prejuizo += (qtd_tirada * lote.valor_custo)
                    
                if lote.quantidade <= restante:
                    restante -= lote.quantidade
                    db.session.delete(lote)
                else:
                    lote.quantidade -= restante
                    restante = 0
                    
        if motivo == 'DESCARTE':
            registrar_log("DESCARTE", f"Acidente Receita: {qtd_pizzas}x {nome_completo}. Prejuízo: R$ {valor_prejuizo:.2f}")
            flash('Descarte registrado.', 'warning')
        else:
            registrar_log("SAÍDA", f"Produção Concluída: {qtd_pizzas}x {nome_completo}")
            flash('Baixa realizada!', 'success')
            
        db.session.commit()
        return redirect(url_for('dashboard'))
    

    # ==========================================
    # 📦 GESTÃO DE ESTOQUE E LOTES
    # ==========================================
    @app.route('/lotes/<int:id>')
    @login_required
    def gerenciar_lotes(id):
        produto = Produto.query.get_or_404(id)
        fornecedores = Fornecedor.query.all()
        hoje = date.today()
        g_mensal = db.session.query(func.sum(Compra.valor_total)).filter(
            Compra.produto_nome == produto.nome, Compra.data >= hoje.replace(day=1)).scalar() or 0.0
        d_ini = request.args.get('data_inicio')
        d_fim = request.args.get('data_fim')
        query_total = db.session.query(func.sum(Compra.valor_total)).filter(Compra.produto_nome == produto.nome)
        
        if d_ini and d_fim:
            try:
                dt_inicio = datetime.strptime(d_ini, '%Y-%m-%d')
                dt_fim = datetime.strptime(d_fim, '%Y-%m-%d') + timedelta(days=1)
                query_total = query_total.filter(Compra.data >= dt_inicio, Compra.data < dt_fim)
            except ValueError: pass

        return render_template('lotes.html', produto=produto, fornecedores=fornecedores, hoje=hoje, 
                               gasto_mensal=g_mensal, gasto_total_periodo=query_total.scalar() or 0.0,
                               data_inicio=d_ini, data_fim=d_fim)

    @app.route('/adicionar_lote', methods=['POST'])
    @login_required
    def adicionar_lote():
        p_id = int(request.form.get('produto_id'))
        prod = Produto.query.get(p_id)
        validade_dt = datetime.strptime(request.form.get('validade'), '%Y-%m-%d').date()
        
        if validade_dt < date.today():
            flash("⚠️ Erro: Não é permitido inserir produtos vencidos!", "danger")
            return redirect(request.referrer)
            
        qtd_raw = float(request.form.get('quantidade', 0))
        unid_in = request.form.get('unidade_entrada')
        preco_un = float(request.form.get('valor', 0))
        
        qtd_final = qtd_raw / 1000 if unid_in in ['g', 'ml'] else qtd_raw
        
        # Tenta usar a função de formatar se você tiver, senão apenas arredonda
        try:
            qtd_final = formatar_quantidade(qtd_final, prod.unidade)
        except:
            qtd_final = round(qtd_final, 3)
        
        db.session.add(Lote(quantidade=qtd_final, valor_custo=preco_un, validade=validade_dt,
                            fornecedor_id=request.form.get('fornecedor_id'), produto_id=p_id))
        db.session.add(Compra(produto_nome=prod.nome, quantidade=qtd_final, 
                              valor_unitario=preco_un, valor_total=qtd_final * preco_un))
                              
        registrar_log("ENTRADA", f"Adicionado {qtd_final} {prod.unidade} de {prod.nome}")
        db.session.commit()
        flash('Estoque atualizado com sucesso!', 'success')
        return redirect(url_for('gerenciar_lotes', id=p_id))

    @app.route('/remover_lote/<int:id>')
    @login_required
    def remover_lote(id):
        lote = Lote.query.get_or_404(id)
        p_id = lote.produto_id
        registrar_log("REMOÇÃO MANUAL", f"Lote de {lote.produto.nome} removido do estoque.")
        db.session.delete(lote)
        db.session.commit()
        flash("Lote removido com sucesso!", "info")
        return redirect(url_for('gerenciar_lotes', id=p_id))

# --- PDV, CLIENTES, ENTREGADORES ---

    @app.route('/pdv')
    @login_required
    def tela_pdv():
        cliente_id_url = request.args.get('cliente_id', '') 
        
        clientes = Cliente.query.filter_by(ativo=True).order_by(Cliente.nome).all()
        entregadores = Entregador.query.filter_by(ativo=True).order_by(Entregador.nome).all()
        
        # 1. Busca TODAS as bebidas ativas primeiro
        todas_bebidas = Produto.query.filter_by(ativo=True, vender_direto=True).order_by(Produto.nome).all()
        
        # 2. O FILTRO INTELIGENTE: Só deixa passar quem tem lote com quantidade > 0
        bebidas = []
        for produto in todas_bebidas:
            estoque_total = sum(lote.quantidade for lote in produto.lotes)
            
            if estoque_total > 0:
                bebidas.append(produto)
                
        # Envia SABORES para o PDV
        sabores = Sabor.query.filter_by(ativo=True).order_by(Sabor.nome).all()
        
        # 👇 3. BUSCA A CONFIGURAÇÃO DA TAXA PADRÃO AQUI
        config = Configuracao.query.first()
        taxa_padrao = config.taxa_entrega_padrao if config else 0.0
        
        return render_template('pdv.html', clientes=clientes, entregadores=entregadores, 
                               pizzas=sabores, bebidas=bebidas, 
                               cliente_pre_selecionado=cliente_id_url,
                               taxa_padrao=taxa_padrao) # 👇 PASSA A VARIÁVEL PARA O HTML
    
    
    @app.route('/movimentacao_caixa', methods=['POST'])
    @login_required
    def movimentacao_caixa():
        tipo = request.form.get('tipo') # Pode ser 'ABERTURA', 'SANGRIA' ou 'REFORÇO'
        valor_str = request.form.get('valor', '0').replace('R$', '').replace('.', '').replace(',', '.')
        
        try:
            valor = float(valor_str)
        except ValueError:
            flash("⚠️ Valor inválido.", "danger")
            return redirect(url_for('pdv')) # Assumindo que o botão ficará na tela do PDV

        if valor <= 0:
            flash("⚠️ O valor deve ser maior que zero.", "warning")
            return redirect(url_for('pdv'))

        observacao = request.form.get('observacao', '').strip()

        # Salva no banco de dados
        nova_mov = MovimentacaoCaixa(
            tipo=tipo.upper(),
            valor=valor,
            observacao=observacao,
            usuario_id=current_user.id
        )
        db.session.add(nova_mov)
        
        # Opcional: Se você ainda usa aquela função registrar_log()
        try:
            registrar_log(f"CAIXA - {tipo.upper()}", f"R$ {valor:.2f} | Obs: {observacao}")
        except:
            pass
            
        db.session.commit()
        
        flash(f"✅ {tipo.capitalize()} de R$ {valor:.2f} registrada com sucesso!", "success")
        return redirect(url_for('pdv'))

    @app.route('/clientes', methods=['GET', 'POST'])
    @login_required
    def gerenciar_clientes():
        if request.method == 'POST':
            nome = request.form.get('nome').upper().strip()
            cpf = request.form.get('cpf')
            telefone = request.form.get('telefone')
            
            # Novos campos de endereço
            cep = request.form.get('cep')
            endereco = request.form.get('endereco').upper().strip()
            numero = request.form.get('numero').upper().strip()
            bairro = request.form.get('bairro').upper().strip()
            cidade = request.form.get('cidade').upper().strip()
            uf = request.form.get('uf').upper().strip()
            complemento = request.form.get('complemento').upper().strip()
            referencia = request.form.get('referencia').upper().strip()
            
            db.session.add(Cliente(
                nome=nome, cpf=cpf, telefone=telefone, 
                cep=cep, endereco=endereco, numero=numero, 
                bairro=bairro, cidade=cidade, uf=uf, 
                complemento=complemento, referencia=referencia
            ))
            db.session.commit()
            registrar_log("VENDAS", f"Novo cliente: {nome}")
            flash("Cliente cadastrado!", "success")
            return redirect(url_for('gerenciar_clientes'))
            
        return render_template('clientes.html', clientes=Cliente.query.filter_by(ativo=True).order_by(Cliente.nome).all())

    @app.route('/editar_cliente/<int:id>', methods=['GET', 'POST'])
    @login_required
    def editar_cliente(id):
        cliente = Cliente.query.get_or_404(id)
        
        if request.method == 'POST':
            cliente.nome = request.form.get('nome').upper()
            cliente.telefone = request.form.get('telefone')
            cliente.cpf = request.form.get('cpf')
            cliente.cep = request.form.get('cep')
            cliente.endereco = request.form.get('endereco').upper()
            cliente.numero = request.form.get('numero')
            cliente.bairro = request.form.get('bairro').upper()
            cliente.cidade = request.form.get('cidade').upper()
            cliente.uf = request.form.get('uf').upper()
            cliente.complemento = request.form.get('complemento').upper()
            cliente.referencia = request.form.get('referencia').upper()
            
            # 👇 Salva a taxa personalizada
            taxa_raw = request.form.get('taxa_entrega', '0').replace(',', '.')
            cliente.taxa_entrega = float(taxa_raw) if taxa_raw else 0.0

            db.session.commit()
            flash('Cliente atualizado com sucesso!', 'success')
            return redirect(url_for('gerenciar_clientes'))

        # 👇 ESSAS SÃO AS LINHAS QUE ESTAVAM FALTANDO (Para o GET funcionar) 👇
        vendas = Venda.query.filter_by(cliente_id=cliente.id).order_by(Venda.data_venda.desc()).all()
        return render_template('editar_cliente.html', cliente=cliente, vendas=vendas)

    @app.route('/deletar_cliente/<int:id>')
    @login_required
    def deletar_cliente(id):
        c = Cliente.query.get_or_404(id)
        c.ativo = False 
        db.session.commit()
        return redirect(url_for('gerenciar_clientes'))

    @app.route('/entregadores', methods=['GET', 'POST'])
    @login_required
    def gerenciar_entregadores():
        if request.method == 'POST':
            nome = request.form.get('nome').upper()
            telefone = request.form.get('telefone')
            veiculo = request.form.get('veiculo').upper()
            placa = request.form.get('placa').upper().strip() 
            if len(placa) != 7:
                flash("❌ A placa deve conter exatamente 7 caracteres!", "danger")
                return redirect(url_for('gerenciar_entregadores'))
            db.session.add(Entregador(nome=nome, telefone=telefone, veiculo=veiculo, placa=placa))
            db.session.commit()
            flash("Entregador cadastrado!", "success")
            return redirect(url_for('gerenciar_entregadores'))
        return render_template('entregadores.html', entregadores=Entregador.query.filter_by(ativo=True).all())

    @app.route('/editar_entregador/<int:id>', methods=['GET', 'POST'])
    @login_required
    def editar_entregador(id):
        e = Entregador.query.get_or_404(id)
        if request.method == 'POST':
            e.nome = request.form.get('nome').upper()
            e.telefone = request.form.get('telefone')
            e.veiculo = request.form.get('veiculo').upper()
            nova_placa = request.form.get('placa').upper().strip()
            if len(nova_placa) != 7:
                flash("❌ Placa inválida!", "danger")
                return redirect(url_for('editar_entregador', id=id))
            e.placa = nova_placa 
            db.session.commit()
            flash("Entregador atualizado!", "success")
            return redirect(url_for('gerenciar_entregadores'))
        return render_template('editar_entregador.html', entregador=e)

    @app.route('/deletar_entregador/<int:id>')
    @login_required
    def deletar_entregador(id):
        e = Entregador.query.get_or_404(id)
        e.ativo = False 
        db.session.commit()
        return redirect(url_for('gerenciar_entregadores'))

    @app.route('/relatorios')
    @login_required
    def ver_relatorios():
        if not current_user.is_admin: return redirect(url_for('dashboard'))
        return render_template('relatorios.html')

    @app.route('/relatorio/<tipo>')
    @login_required
    def relatorio_especifico(tipo):
        if not current_user.is_admin: return redirect(url_for('dashboard'))
        
        page = request.args.get('page', 1, type=int)

        hoje_str = datetime.now().strftime('%Y-%m-%d')
        d_ini = request.args.get('data_inicio', hoje_str)
        d_fim = request.args.get('data_fim', hoje_str)
        
        ordem = request.args.get('ordem', 'maior')
        f_user = request.args.get('usuario')
        f_acao = request.args.get('acao')
        f_produto = request.args.get('produto')
        f_fornecedor = request.args.get('fornecedor')

        dt_inicio, dt_fim = None, None
        if d_ini and d_fim:
            try:
                dt_inicio = datetime.strptime(d_ini, '%Y-%m-%d')
                dt_fim = datetime.strptime(d_fim, '%Y-%m-%d') + timedelta(days=1) 
            except ValueError: pass

        todos_usuarios = [u.username for u in Usuario.query.all()]
        nomes_produtos_ativos = [p.nome for p in Produto.query.filter_by(ativo=True).order_by(Produto.nome).all()]
        todos_fornecedores = [f.nome for f in Fornecedor.query.order_by(Fornecedor.nome).all()]

        # Utilitário para formatar a tabela genérica
        class ItemRelatorio:
            def __init__(self, nome, valor):
                self.nome, self.valor = nome, valor

        if tipo == 'gastos':
            # 💸 GASTOS: Curva ABC com Custo Médio
            query = db.session.query(
                Compra.produto_nome.label('produto'), 
                func.sum(Compra.quantidade).label('qtd'),
                func.sum(Compra.valor_total).label('total')
            )
            if dt_inicio: query = query.filter(Compra.data >= dt_inicio, Compra.data < dt_fim)
            if f_produto and f_produto != 'OUTROS': query = query.filter(Compra.produto_nome == f_produto)
            query = query.group_by(Compra.produto_nome)
            
            lista_dados = []
            for r in query.all():
                qtd = r.qtd or 0
                total = r.total or 0.0
                preco_medio = total / qtd if qtd > 0 else 0.0
                nome_enriquecido = f"📦 {r.produto} (Comprado: {qtd:.2f} | ⚖️ Custo Médio: R$ {preco_medio:.2f}/unid)"
                lista_dados.append(ItemRelatorio(nome_enriquecido, total))
                
            lista_dados.sort(key=lambda x: x.valor, reverse=(ordem == 'maior'))
            titulo, cabecalhos = "💸 Curva ABC de Custos (Insumos)", ["Posição", "Insumo (Volume | Custo Médio)", "Total Gasto (R$)"]
            is_moeda, is_auditoria, dados, is_paginated = True, False, lista_dados, False

        elif tipo == 'consumo':
            query = db.session.query(Compra.produto_nome.label('nome'), func.sum(Compra.quantidade).label('valor'))
            if dt_inicio: query = query.filter(Compra.data >= dt_inicio, Compra.data < dt_fim)
            if f_produto:
                if f_produto == 'OUTROS': query = query.filter(Compra.produto_nome.notin_(nomes_produtos_ativos))
                else: query = query.filter(Compra.produto_nome == f_produto)
            query = query.group_by(Compra.produto_nome)
            if ordem == 'maior': query = query.order_by(func.sum(Compra.quantidade).desc())
            else: query = query.order_by(func.sum(Compra.quantidade).asc())
            titulo, cabecalhos = "📦 Volume de Consumo", ["Posição", "Produto", "Quantidade Adquirida"]
            is_moeda, is_auditoria, dados, is_paginated = False, False, query.all(), False

        elif tipo == 'fornecedores':
            # 🤝 FORNECEDORES: Dependência e Volume
            query = db.session.query(
                Fornecedor.nome.label('fornecedor'), 
                func.count(Lote.id).label('qtd_notas'),
                func.sum(Lote.quantidade * Lote.valor_custo).label('total')
            ).join(Lote, Fornecedor.id == Lote.fornecedor_id)
            if dt_inicio: query = query.filter(Lote.data_entrada >= dt_inicio, Lote.data_entrada < dt_fim)
            if f_fornecedor: query = query.filter(Fornecedor.nome == f_fornecedor)
            query = query.group_by(Fornecedor.nome)
            
            lista_dados = []
            for r in query.all():
                nome_enriquecido = f"🏢 {r.fornecedor} (🧾 {r.qtd_notas} Entregas/Lotes no período)"
                lista_dados.append(ItemRelatorio(nome_enriquecido, r.total or 0.0))
                
            lista_dados.sort(key=lambda x: x.valor, reverse=(ordem == 'maior'))
            titulo, cabecalhos = "🤝 Volume Financeiro por Fornecedor", ["Posição", "Fornecedor (Entregas)", "Total Pago (R$)"]
            is_moeda, is_auditoria, dados, is_paginated = True, False, lista_dados, False

        elif tipo == 'desperdicio':
            query = Log.query.filter(Log.acao == 'DESCARTE')
            if dt_inicio: query = query.filter(Log.data >= dt_inicio, Log.data < dt_fim)
            if f_user: query = query.filter(Log.usuario == f_user) 
            if ordem == 'maior': query = query.order_by(Log.data.desc())
            else: query = query.order_by(Log.data.asc())
            titulo, cabecalhos = "🗑️ Histórico de Desperdício/Acidentes", ["Data", "Usuário", "Ação", "Detalhes do Prejuízo"]
            is_moeda, is_auditoria = False, True
            dados, is_paginated = query.all(), False

        elif tipo == 'producao':
            query_logs = Log.query.filter(Log.acao == 'SAÍDA')
            if dt_inicio: query_logs = query_logs.filter(Log.data >= dt_inicio, Log.data < dt_fim)
            vendas_dict = {}
            for log in query_logs.all():
                if "Produção Concluída:" in log.descricao:
                    try:
                        partes = log.descricao.split('x ')
                        qtd = int(partes[0].split(': ')[1])
                        vendas_dict[partes[1]] = vendas_dict.get(partes[1], 0) + qtd
                    except: pass
            lista_dados = [ItemRelatorio(n, q) for n, q in vendas_dict.items()]
            lista_dados.sort(key=lambda x: x.valor, reverse=(ordem == 'maior'))
            titulo, cabecalhos = "🏆 Receitas Produzidas (Ranking)", ["Posição", "Receita / Prato", "Qtd Produzida"]
            is_moeda, is_auditoria, dados, is_paginated = False, False, lista_dados, False

        elif tipo == 'auditoria':
            query = Log.query
            if dt_inicio: query = query.filter(Log.data >= dt_inicio, Log.data < dt_fim)
            if f_user: query = query.filter(Log.usuario == f_user) 
            if f_acao: query = query.filter(Log.acao == f_acao) 
            if ordem == 'maior': query = query.order_by(Log.data.desc())
            else: query = query.order_by(Log.data.asc())
            titulo, cabecalhos = "🕵️ Auditoria do Sistema", ["Data", "Usuário", "Ação", "Descrição"]
            is_moeda, is_auditoria = False, True
            dados, is_paginated = query.all(), False
        
        elif tipo == 'vendas':
            # 💵 VENDAS: Performance Diária com Ticket Médio
            query = db.session.query(
                func.strftime('%d/%m/%Y', Venda.data_venda).label('data_str'), 
                func.count(Venda.id).label('qtd'),
                func.sum(Venda.valor_total).label('total')
            ).filter(Venda.status == 'CONCLUÍDA')
            if dt_inicio: query = query.filter(Venda.data_venda >= dt_inicio, Venda.data_venda < dt_fim)
            query = query.group_by(func.strftime('%d/%m/%Y', Venda.data_venda))
            
            lista_dados = []
            for r in query.all():
                qtd = r.qtd or 0
                total = r.total or 0.0
                ticket = total / qtd if qtd > 0 else 0.0
                nome_enriquecido = f"📅 {r.data_str} (📦 {qtd} Pedidos | 🎟️ Ticket Médio: R$ {ticket:.2f})"
                lista_dados.append(ItemRelatorio(nome_enriquecido, total))
                
            lista_dados.sort(key=lambda x: x.valor, reverse=(ordem == 'maior'))
            titulo, cabecalhos = "📈 Performance Diária de Vendas", ["Posição", "Data (Qtd Pedidos | Ticket Médio)", "Faturamento Bruto (R$)"]
            is_moeda, is_auditoria, dados, is_paginated = True, False, lista_dados, False
        
        elif tipo == 'entregadores':
            # Igual à comissão, mas mostra o valor financeiro
            query = db.session.query(
                Entregador.nome.label('nome'), 
                func.sum(Venda.valor_total).label('valor')
            ).join(Venda, Entregador.id == Venda.entregador_id).filter(Venda.status == 'CONCLUÍDA')
            if dt_inicio: query = query.filter(Venda.data_venda >= dt_inicio, Venda.data_venda < dt_fim)
            query = query.group_by(Entregador.nome)
            if ordem == 'maior': query = query.order_by(func.sum(Venda.valor_total).desc())
            else: query = query.order_by(func.sum(Venda.valor_total).asc())
            titulo, cabecalhos = "🛵 Faturamento por Entregador", ["Posição", "Nome do Entregador", "Total Transportado (R$)"]
            is_moeda, is_auditoria, dados, is_paginated = True, False, query.all(), False

        elif tipo == 'fechamento':
            query = Venda.query.filter(Venda.status == 'CONCLUÍDA')
            query_caixa = MovimentacaoCaixa.query
            if dt_inicio: 
                query = query.filter(Venda.data_venda >= dt_inicio, Venda.data_venda < dt_fim)
                query_caixa = query_caixa.filter(MovimentacaoCaixa.data >= dt_inicio, MovimentacaoCaixa.data < dt_fim)
            
            class VendaFechamento:
                def __init__(self, data_obj, data, cliente, pagamento, itens, valor):
                    self.data_obj, self.data, self.cliente, self.pagamento, self.itens, self.valor = data_obj, data, cliente, pagamento, itens, valor

            lista_dados = []
            for v in query.all():
                data_fmt = v.data_venda.strftime('%d/%m %H:%M') if v.data_venda else "N/D"
                nome_cliente = v.cliente.nome if getattr(v, 'cliente', None) else "Balcão / Avulso"
                agrupamento = {}
                for item in v.itens:
                    nome_prod = item.nome_item if item.nome_item else 'Item Desconhecido'
                    agrupamento[nome_prod] = agrupamento.get(nome_prod, 0) + item.quantidade
                lista_itens = [f"{int(qtd)}x {nome}" for nome, qtd in agrupamento.items()]
                itens_str = ", ".join(lista_itens) if lista_itens else "Sem itens"
                lista_dados.append(VendaFechamento(v.data_venda, data_fmt, nome_cliente, f"💰 {v.forma_pagamento}", itens_str, v.valor_total))

            for m in query_caixa.all():
                data_fmt = m.data.strftime('%d/%m %H:%M') if m.data else "N/D"
                sinal = -1 if m.tipo == 'SANGRIA' else 1
                icone = "🔴" if m.tipo == 'SANGRIA' else "🟢"
                obs = m.observacao if m.observacao else "S/ Obs"
                lista_dados.append(VendaFechamento(m.data, data_fmt, "SISTEMA (OP. CAIXA)", f"{icone} {m.tipo}", f"Ajuste Físico: {obs}", m.valor * sinal))

            lista_dados.sort(key=lambda x: x.data_obj if x.data_obj else datetime.min, reverse=(ordem == 'maior'))
            titulo, cabecalhos = "🧾 Fechamento do Caixa (Linha do Tempo)", ["Data/Hora", "Cliente / Origem", "Tipo de Registro", "Itens / Observações", "Valor (R$)"]
            is_moeda, is_auditoria, dados, is_paginated = True, False, lista_dados, False
            
        elif tipo == 'faturamento':
            lista_dados = []
            
            entradas_q = db.session.query(Venda.forma_pagamento, func.sum(Venda.valor_total)).filter(Venda.status == 'CONCLUÍDA')
            if dt_inicio: entradas_q = entradas_q.filter(Venda.data_venda >= dt_inicio, Venda.data_venda < dt_fim)
            entradas = entradas_q.group_by(Venda.forma_pagamento).all()
            tot_receitas = sum(val for fp, val in entradas) if entradas else 0.0
            vendas_dinheiro = sum(val for fp, val in entradas if fp == 'DINHEIRO')
            
            query_caixa = MovimentacaoCaixa.query
            if dt_inicio: query_caixa = query_caixa.filter(MovimentacaoCaixa.data >= dt_inicio, MovimentacaoCaixa.data < dt_fim)
            movs = query_caixa.all()
            tot_abertura = sum(m.valor for m in movs if m.tipo in ['ABERTURA', 'REFORÇO'])
            tot_sangria = sum(m.valor for m in movs if m.tipo == 'SANGRIA')

            lista_dados.append(ItemRelatorio("🟢 1. RECEITAS BRUTAS (VENDAS)", tot_receitas))
            for fp, val in entradas: lista_dados.append(ItemRelatorio(f"      ↳ Vendas via {fp or 'Não Informado'}", val))

            fornec_q = db.session.query(Fornecedor.nome, func.sum(Lote.quantidade * Lote.valor_custo)).join(Lote, Fornecedor.id == Lote.fornecedor_id)
            if dt_inicio: fornec_q = fornec_q.filter(Lote.data_entrada >= dt_inicio, Lote.data_entrada < dt_fim)
            fornecedores = fornec_q.group_by(Fornecedor.nome).all()
            tot_fornec = sum(val for nome, val in fornecedores) if fornecedores else 0.0
            
            lista_dados.append(ItemRelatorio("🔴 2. CUSTOS COM FORNECEDORES", tot_fornec * -1))
            for nome, val in fornecedores: lista_dados.append(ItemRelatorio(f"      ↳ Pago a: {nome}", val * -1))

            gastos_q = db.session.query(Compra.produto_nome, func.sum(Compra.valor_total))
            if dt_inicio: gastos_q = gastos_q.filter(Compra.data >= dt_inicio, Compra.data < dt_fim)
            gastos = gastos_q.group_by(Compra.produto_nome).order_by(func.sum(Compra.valor_total).desc()).all()
            tot_gastos = sum(val for nome, val in gastos) if gastos else 0.0
            
            lista_dados.append(ItemRelatorio("🔴 3. DESPESAS OPERACIONAIS", tot_gastos * -1))
            for nome, val in gastos: lista_dados.append(ItemRelatorio(f"      ↳ Gasto com: {nome}", val * -1))

            tot_saidas = tot_fornec + tot_gastos
            lucro_liquido = tot_receitas - tot_saidas
            
            lista_dados.append(ItemRelatorio("==================================================", 0.0))
            lista_dados.append(ItemRelatorio("💰 RESULTADO LÍQUIDO FINAL (Vendas - Custos)", lucro_liquido))
            lista_dados.append(ItemRelatorio("==================================================", 0.0))
            
            saldo_gaveta = vendas_dinheiro + tot_abertura - tot_sangria
            lista_dados.append(ItemRelatorio("💵 ESPELHO DA GAVETA (Dinheiro Físico)", saldo_gaveta))
            lista_dados.append(ItemRelatorio("      ↳ (+) Fundo de Troco / Aberturas", tot_abertura))
            lista_dados.append(ItemRelatorio("      ↳ (+) Vendas Recebidas em Dinheiro", vendas_dinheiro))
            lista_dados.append(ItemRelatorio("      ↳ (-) Sangrias / Retiradas de Caixa", tot_sangria * -1))
            
            titulo, cabecalhos = "📈 DRE e Auditoria de Gaveta", ["Linha", "Descrição da Conta Financeira", "Valor (R$)"]
            is_moeda, is_auditoria, dados, is_paginated = True, False, lista_dados, False

        elif tipo == 'comissao':
            # 🛵 COMISSÃO: Eficiência do Motoboy
            query = db.session.query(
                Entregador.nome.label('nome'), 
                func.count(Venda.id).label('qtd'),
                func.sum(Venda.valor_total).label('total_movimentado')
            ).join(Venda, Entregador.id == Venda.entregador_id).filter(Venda.status == 'CONCLUÍDA')
            if dt_inicio: query = query.filter(Venda.data_venda >= dt_inicio, Venda.data_venda < dt_fim)
            query = query.group_by(Entregador.nome)
            
            lista_dados = []
            for r in query.all():
                tm = (r.total_movimentado / r.qtd) if r.qtd > 0 else 0
                nome_enriquecido = f"🛵 {r.nome} (Transportou R$ {r.total_movimentado:.2f} | 🎟️ TM: R$ {tm:.2f}/viagem)"
                lista_dados.append(ItemRelatorio(nome_enriquecido, r.qtd)) 
                
            lista_dados.sort(key=lambda x: x.valor, reverse=(ordem == 'maior'))
            titulo, cabecalhos = "🛵 Produtividade e Comissão (Entregadores)", ["Posição", "Entregador (Performance Financeira)", "Nº de Viagens (Qtd)"]
            is_moeda, is_auditoria, dados, is_paginated = False, False, lista_dados, False

        exportar = request.args.get('exportar_pdf')
        if exportar == 'sim' and is_paginated:
            # Se for exportar e tiver paginação, tentamos mandar tudo, mas nossa nova lógica desligou o paginate pra quase todos.
            pass

        return render_template('relatorio_especifico.html', dados=dados, titulo=titulo, cabecalhos=cabecalhos, 
                               is_moeda=is_moeda, is_auditoria=is_auditoria, tipo=tipo, d_ini=d_ini, d_fim=d_fim, 
                               ordem=ordem, todos_usuarios=todos_usuarios, todos_produtos=nomes_produtos_ativos, 
                               todos_fornecedores=todos_fornecedores, f_user=f_user, f_acao=f_acao, 
                               f_produto=f_produto, f_fornecedor=f_fornecedor, is_paginated=is_paginated, exportar=exportar)
    
    @app.route('/financeiro')
    @login_required
    def dashboard_financeiro():
        if not current_user.is_admin:
            flash("⛔ Acesso negado.", "danger")
            return redirect(url_for('dashboard'))

        hoje = datetime.now()
        mes_atual_str = f"{hoje.month:02d}"
        ano_atual_str = str(hoje.year)

        # 1. VISÃO DE VENDAS (O que foi vendido)
        vendas_mes = Venda.query.filter(
            func.strftime('%m', Venda.data_venda) == mes_atual_str,
            func.strftime('%Y', Venda.data_venda) == ano_atual_str,
            Venda.status != 'CANCELADA'
        ).all()

        # TRATAMENTO DE NULL: Usamos (v.valor or 0.0) para não quebrar a soma
        kpi_bruto = sum((v.valor_bruto or 0.0) for v in vendas_mes)
        kpi_liquido = sum((v.valor_liquido or 0.0) for v in vendas_mes)
        kpi_taxas = kpi_bruto - kpi_liquido

        dados_vendas_por_dia = {}
        for v in vendas_mes:
            dia = v.data_venda.strftime('%d/%m')
            if dia not in dados_vendas_por_dia:
                dados_vendas_por_dia[dia] = {'bruto': 0.0, 'liquido': 0.0}
            # Soma garantindo que valores nulos sejam tratados como zero
            dados_vendas_por_dia[dia]['bruto'] += (v.valor_bruto or 0.0)
            dados_vendas_por_dia[dia]['liquido'] += (v.valor_liquido or 0.0)

        # 2. VISÃO DE CAIXA (O que cai na conta)
        # Importante: filtramos pela DATA DE RECEBIMENTO PREVISTO
        recebimentos_mes = Venda.query.filter(
            func.strftime('%m', Venda.data_recebimento_previsto) == mes_atual_str,
            func.strftime('%Y', Venda.data_recebimento_previsto) == ano_atual_str,
            Venda.status != 'CANCELADA'
        ).all()

        kpi_entradas_caixa = sum((v.valor_liquido or 0.0) for v in recebimentos_mes)

        dados_caixa_por_dia = {}
        for v in recebimentos_mes:
            # AQUI TAMBÉM: mude para o nome completo da coluna
            if v.data_recebimento_previsto: 
                dia = v.data_recebimento_previsto.strftime('%d/%m')
                if dia not in dados_caixa_por_dia:
                    dados_caixa_por_dia[dia] = 0.0
                dados_caixa_por_dia[dia] += (v.valor_liquido or 0.0)

        labels_vendas = sorted(list(dados_vendas_por_dia.keys()))
        labels_caixa = sorted(list(dados_caixa_por_dia.keys()))

        return render_template(
            'financeiro.html',
            kpi_bruto=round(kpi_bruto, 2),
            kpi_liquido=round(kpi_liquido, 2),
            kpi_taxas=round(kpi_taxas, 2),
            labels_vendas=json.dumps(labels_vendas),
            graf_bruto=json.dumps([dados_vendas_por_dia[d]['bruto'] for d in labels_vendas]),
            graf_liquido=json.dumps([dados_vendas_por_dia[d]['liquido'] for d in labels_vendas]),
            kpi_entradas_caixa=round(kpi_entradas_caixa, 2),
            labels_caixa=json.dumps(labels_caixa),
            graf_caixa=json.dumps([dados_caixa_por_dia[d] for d in labels_caixa])
        )


    @app.route('/usuarios', methods=['GET', 'POST'])
    @login_required
    def gerenciar_usuarios():
        # 👇 A TRANCA: Se não for admin, chuta de volta pro Dashboard
        if not current_user.is_admin:
            flash("⛔ Área restrita para administradores.", "danger")
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            novo_u = limpar_texto(request.form.get('username')).lower()
            senha_bruta = request.form.get('password')
            
            # 1. CAPTURANDO O E-MAIL DO HTML
            novo_email = request.form.get('email').strip().lower() 
            
            # 2. CHECANDO DUPLICATAS (NOME OU E-MAIL)
            usuario_existente = Usuario.query.filter_by(username=novo_u).first()
            email_existente = Usuario.query.filter_by(email=novo_email).first()

            if usuario_existente:
                flash(f"⚠️ O login '{novo_u}' já existe!", "warning")
            elif email_existente:
                flash(f"⚠️ O e-mail '{novo_email}' já está em uso por outro colaborador!", "danger")
            else:
                # 3. SALVANDO O NOVO USUÁRIO COM O E-MAIL
                db.session.add(Usuario(
                    username=novo_u, 
                    email=novo_email, 
                    password=generate_password_hash(senha_bruta)
                ))
                db.session.commit()
                flash('Usuário criado com sucesso!', 'success')
                
        return render_template('usuarios.html', usuarios=Usuario.query.all())

    @app.route('/editar_usuario/<int:id>', methods=['GET', 'POST'])
    @login_required
    def editar_usuario(id):
        u = Usuario.query.get_or_404(id)
        if not current_user.is_admin and current_user.id != u.id:
            return redirect(url_for('dashboard'))
            
        if request.method == 'POST':
            novo_nome = limpar_texto(request.form.get('username')).lower()
            novo_email = request.form.get('email')
            usuario_existente = Usuario.query.filter_by(username=novo_nome).first()
            if usuario_existente and usuario_existente.id != u.id:
                flash(f"⚠️ Login em uso!", "warning")
                return redirect(url_for('editar_usuario', id=u.id))
                
            u.username = novo_nome
            u.email = novo_email
            nova_senha = request.form.get('nova_senha')
            if nova_senha: 
                u.password = generate_password_hash(nova_senha)
                
            if current_user.is_admin:
                u.is_admin = request.form.get('is_admin') == 'on'
                if u.id == current_user.id: 
                    u.is_admin = True 
                    
            db.session.commit()
            flash("Atualizado com sucesso!", "success")
            return redirect(url_for('gerenciar_usuarios'))
            
        return render_template('editar_usuario.html', usuario=u)

    @app.route('/deletar_usuario/<int:id>')
    @login_required
    def deletar_usuario(id):
        if not current_user.is_admin: return redirect(url_for('gerenciar_usuarios'))
        u = Usuario.query.get_or_404(id)
        if u.id == current_user.id: return redirect(url_for('gerenciar_usuarios'))
        db.session.delete(u)
        db.session.commit()
        return redirect(url_for('gerenciar_usuarios'))

    # ==========================================
    # API DE PROCESSAMENTO DE VENDAS
    # ==========================================
    def descontar_estoque(produto_id, quantidade_necessaria):
        produto = Produto.query.get(produto_id)
        if produto.total_atual < quantidade_necessaria:
            raise Exception(f"Estoque insuficiente para: {produto.nome}")
            
        lotes = Lote.query.filter_by(produto_id=produto_id).order_by(Lote.validade.asc()).all()
        restante = quantidade_necessaria
        
        for lote in lotes:
            if restante <= 0: break
            if lote.quantidade <= restante:
                restante -= lote.quantidade
                db.session.delete(lote)
            else:
                lote.quantidade -= restante
                restante = 0

    @app.route('/historico_vendas')
    @login_required
    def historico_vendas():
        # Trava de segurança: Se quiser, pode liberar pro Caixa ver também tirando esse if
        if not current_user.is_admin: 
            flash("⛔ Acesso negado: Apenas administradores.", "danger")
            return redirect(url_for('pdv'))

        hoje_str = datetime.now().strftime('%Y-%m-%d')
        d_ini = request.args.get('data_inicio', hoje_str)
        d_fim = request.args.get('data_fim', hoje_str)

        query = Venda.query

        if d_ini and d_fim:
            try:
                dt_inicio = datetime.strptime(d_ini, '%Y-%m-%d')
                dt_fim = datetime.strptime(d_fim, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(Venda.data_venda >= dt_inicio, Venda.data_venda < dt_fim)
            except ValueError:
                pass

        # Ordena da venda mais recente para a mais antiga
        vendas = query.order_by(Venda.data_venda.desc()).all()

        return render_template('historico_vendas.html', vendas=vendas, data_inicio=d_ini, data_fim=d_fim)


    @app.route('/api/finalizar_venda', methods=['POST'])
    @login_required
    def processar_venda_api():
        dados = request.get_json()
        
        if not dados or not dados.get('itens'):
            return jsonify({'sucesso': False, 'erro': 'O carrinho está vazio!'}), 400

        try:
            # 1. CÁLCULO DOS VALORES BASE
            subtotal_itens = sum(float(item['subtotal']) for item in dados['itens'])
            taxa_entrega = float(dados.get('taxa_entrega', 0.0))
            desconto = float(dados.get('desconto', 0.0)) # 👈 Atualizado para capturar do Front
            
            # 👇 TRAVA DE SEGURANÇA DO BACKEND 👇
            total_sem_desconto = subtotal_itens + taxa_entrega
            
            if desconto > total_sem_desconto:
                return jsonify({
                    'sucesso': False, 
                    'erro': f'Operação bloqueada: O desconto (R$ {desconto:.2f}) não pode ser maior que o total do pedido (R$ {total_sem_desconto:.2f}).'
                }), 400
            # 👆 FIM DA TRAVA 👆

            valor_total_pedido = total_sem_desconto - desconto
            
            forma_pagamento_req = str(dados.get('forma_pagamento', 'DINHEIRO')).upper()

            # 2. CRIAÇÃO DA VENDA (Com todos os campos do seu modelo)
            nova_venda = Venda(
                cliente_id=dados.get('cliente_id') or None,
                entregador_id=dados.get('entregador_id') or None,
                status='CONCLUÍDA',
                vendedor=current_user.username,
                subtotal=subtotal_itens,
                taxa_entrega=taxa_entrega,
                desconto=desconto,
                valor_total=valor_total_pedido,
                forma_pagamento=forma_pagamento_req,
                valor_bruto=valor_total_pedido # Bruto é sempre igual ao total pago
            )

            # 3. 🧠 MOTOR FINANCEIRO (Calcula o Líquido e a Data Prevista)
            conf = Configuracao.query.first()
            
            if 'CRÉDITO' in forma_pagamento_req or 'CREDITO' in forma_pagamento_req:
                taxa_pct = conf.taxa_credito if conf else 0.0
                prazo = conf.prazo_credito if conf else 30
                
                nova_venda.taxa_aplicada = taxa_pct
                desconto_taxa = nova_venda.valor_bruto * (taxa_pct / 100)
                nova_venda.valor_liquido = round(nova_venda.valor_bruto - desconto_taxa, 2)
                nova_venda.data_recebimento_previsto = datetime.now() + timedelta(days=prazo)

            elif 'DÉBITO' in forma_pagamento_req or 'DEBITO' in forma_pagamento_req:
                taxa_pct = conf.taxa_debito if conf else 0.0
                prazo = conf.prazo_debito if conf else 1
                
                nova_venda.taxa_aplicada = taxa_pct
                desconto_taxa = nova_venda.valor_bruto * (taxa_pct / 100)
                nova_venda.valor_liquido = round(nova_venda.valor_bruto - desconto_taxa, 2)
                nova_venda.data_recebimento_previsto = datetime.now() + timedelta(days=prazo)

            else:
                # PIX ou Dinheiro (Cai na hora, sem taxa)
                nova_venda.taxa_aplicada = 0.0
                nova_venda.valor_liquido = nova_venda.valor_bruto
                nova_venda.data_recebimento_previsto = datetime.now()

            # Salva o "cabeçalho" da venda
            db.session.add(nova_venda)
            db.session.flush()

            # 4. SALVAR ITENS E BAIXAR ESTOQUE
            for item in dados['itens']:
                venda_item = VendaItem(
                    venda_id=nova_venda.id,
                    tipo_item=item['tipo'],
                    item_id=item['id'],
                    nome_item=item['nome'],
                    quantidade=item['quantidade'],
                    preco_unitario=item['preco'],
                    preco_total=item['subtotal']
                )
                db.session.add(venda_item)

                if item['tipo'] == 'PRODUTO':
                    descontar_estoque(item['id'], item['quantidade'])
                    
                elif item['tipo'] == 'RECEITA':
                    variacao = ReceitaVariacao.query.get(item['id'])
                    if variacao:
                        for ing in variacao.ingredientes:
                            qtd_gasta = ing.quantidade * item['quantidade']
                            descontar_estoque(ing.produto_id, qtd_gasta)

            db.session.commit()
            return jsonify({'sucesso': True, 'venda_id': nova_venda.id})

        except Exception as e:
            db.session.rollback()
            print(f"❌ ERRO CRÍTICO NA VENDA: {str(e)}") 
            return jsonify({'sucesso': False, 'erro': str(e)}), 500
        
    @app.route('/api/cancelar_venda/<int:venda_id>', methods=['POST'])
    @login_required
    def cancelar_venda(venda_id):
        # 🔒 Trava de segurança para o Gerente
        if not current_user.is_admin:
            return jsonify({'sucesso': False, 'erro': '⛔ Acesso negado: Apenas o Gerente pode estornar vendas.'})

        dados = request.get_json()
        motivo = dados.get('motivo', 'Motivo não informado')
        tipo_cancelamento = dados.get('tipo', 'depois') # Recebe 'antes' ou 'depois' do JavaScript

        venda = Venda.query.get(venda_id)
        
        if not venda:
            return jsonify({'sucesso': False, 'erro': 'Venda não encontrada no banco de dados.'})

        if venda.status == 'CANCELADA':
            return jsonify({'sucesso': False, 'erro': 'Esta venda já se encontra cancelada.'})

        custo_perdido = 0.0
        
        for item in venda.itens:
            # 🥤 PRODUTOS (Venda Direta / Bebidas)
            if item.tipo_item == 'PRODUTO':
                produto = Produto.query.get(item.item_id)
                if produto:
                    if tipo_cancelamento == 'depois':
                        ultima_compra = Compra.query.filter_by(produto_nome=produto.nome).order_by(Compra.id.desc()).first()
                        custo_un = ultima_compra.valor_unitario if ultima_compra else 0.0
                        custo_perdido += (custo_un * item.quantidade)
                    
                    elif tipo_cancelamento == 'antes':
                        # 🔄 DEVOLVE PARA O ESTOQUE
                        lote = Lote.query.filter_by(produto_id=produto.id).order_by(Lote.validade.desc()).first()
                        if lote:
                            lote.quantidade += item.quantidade
                        else:
                            # Se não tinha lote ativo, recria um com validade de 7 dias
                            ultima_compra = Compra.query.filter_by(produto_nome=produto.nome).order_by(Compra.id.desc()).first()
                            custo_un = ultima_compra.valor_unitario if ultima_compra else 0.0
                            db.session.add(Lote(produto_id=produto.id, quantidade=item.quantidade, valor_custo=custo_un, validade=date.today() + timedelta(days=7)))
                    
            # 🍕 RECEITAS (Pizzas Montadas)
            elif item.tipo_item == 'RECEITA':
                variacao = ReceitaVariacao.query.get(item.item_id)
                if variacao:
                    for ing in variacao.ingredientes:
                        produto = ing.produto
                        if produto:
                            qtd_total_ingrediente = ing.quantidade * item.quantidade
                            
                            if tipo_cancelamento == 'depois':
                                ultima_compra = Compra.query.filter_by(produto_nome=produto.nome).order_by(Compra.id.desc()).first()
                                custo_un = ultima_compra.valor_unitario if ultima_compra else 0.0
                                custo_perdido += (custo_un * qtd_total_ingrediente)
                                
                            elif tipo_cancelamento == 'antes':
                                # 🔄 DEVOLVE PARA O ESTOQUE
                                lote = Lote.query.filter_by(produto_id=produto.id).order_by(Lote.validade.desc()).first()
                                if lote:
                                    lote.quantidade += qtd_total_ingrediente
                                else:
                                    ultima_compra = Compra.query.filter_by(produto_nome=produto.nome).order_by(Compra.id.desc()).first()
                                    custo_un = ultima_compra.valor_unitario if ultima_compra else 0.0
                                    db.session.add(Lote(produto_id=produto.id, quantidade=qtd_total_ingrediente, valor_custo=custo_un, validade=date.today() + timedelta(days=7)))

        # 1. Tira a venda do faturamento
        venda.status = 'CANCELADA'

        # 2. Registra na Auditoria baseado no que o cliente escolheu
        if tipo_cancelamento == 'antes':
            registrar_log("CANCELAMENTO_VENDA", f"Venda #{venda.id} estornada (ANTES do preparo - Estoque devolvido). Motivo: {motivo}")
        else:
            registrar_log("CANCELAMENTO_VENDA", f"Venda #{venda.id} estornada (APÓS preparo). Motivo: {motivo}")
            registrar_log("DESCARTE", f"Prejuízo de Venda Cancelada #{venda.id} (A pizza foi consumida!). R$ {custo_perdido:.2f}")
        
        # 3. Salva tudo no banco
        db.session.commit()

        return jsonify({'sucesso': True})

    @app.route('/fornecedores')
    @login_required
    def listar_fornecedores():
        if not current_user.is_admin: return redirect(url_for('dashboard'))
        return render_template('fornecedores.html', fornecedores=Fornecedor.query.all())

    @app.route('/cadastrar_fornecedor', methods=['POST'])
    @login_required
    def cadastrar_fornecedor():
        nome_bruto = request.form.get('nome', '').strip()
        nome_comparacao = limpar_texto(nome_bruto)
        todos_fornecedores = Fornecedor.query.all()
        for f in todos_fornecedores:
            if limpar_texto(f.nome) == nome_comparacao:
                flash("⚠️ Fornecedor já cadastrado!", "warning")
                return redirect(url_for('listar_fornecedores'))
        db.session.add(Fornecedor(nome=nome_bruto.upper(), contato=request.form.get('contato')))
        db.session.commit()
        flash("Fornecedor cadastrado!", "success")
        return redirect(url_for('listar_fornecedores'))

    @app.route('/editar_fornecedor/<int:id>', methods=['GET', 'POST'])
    @login_required
    def editar_fornecedor(id):
        f = Fornecedor.query.get_or_404(id)
        if request.method == 'POST':
            novo_nome = request.form.get('nome').strip().upper()
            nome_comparacao = limpar_texto(novo_nome)
            for forn in Fornecedor.query.all():
                if forn.id != f.id and limpar_texto(forn.nome) == nome_comparacao:
                    flash("⚠️ Nome em uso!", "warning")
                    return redirect(url_for('editar_fornecedor', id=f.id))
            f.nome = novo_nome
            f.contato = request.form.get('contato')
            db.session.commit()
            flash("Atualizado!", "success")
            return redirect(url_for('listar_fornecedores'))
        return render_template('editar_fornecedor.html', fornecedor=f)

    @app.route('/deletar_fornecedor/<int:id>')
    @login_required
    def deletar_fornecedor(id):
        f = Fornecedor.query.get_or_404(id)
        db.session.delete(f)
        db.session.commit()
        return redirect(url_for('listar_fornecedores'))

    
    
    @app.route('/recibo/<int:id>')
    @login_required
    def imprimir_recibo(id):
        venda = Venda.query.get_or_404(id)
        conf = Configuracao.query.first()

        # 🔄 Lógica de Agrupamento TOTAL para o Recibo
        agrupamento = {}
        for item in venda.itens:
            nome = item.nome_item if item.nome_item else 'Item Desconhecido'
            if nome not in agrupamento:
                agrupamento[nome] = {'qtd': 0.0, 'valor': 0.0}
            
            agrupamento[nome]['qtd'] += item.quantidade
            agrupamento[nome]['valor'] += item.preco_total # Soma os pedacinhos do dinheiro

        # Formata bonitinho e arredonda (ex: 0.99 vira 1)
        itens_prontos = []
        for nome, dados in agrupamento.items():
            qtd_arredondada = round(dados['qtd'])
            # Trava de segurança caso o JavaScript mande uma fração muito maluca
            if qtd_arredondada == 0: qtd_arredondada = 1 
            
            itens_prontos.append({
                'nome': nome,
                'qtd': qtd_arredondada,
                'valor': dados['valor']
            })

        return render_template('recibo.html', venda=venda, conf=conf, itens_agrupados=itens_prontos)