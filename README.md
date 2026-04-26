# 🍕 Dominus PDV (Lite Version) 
**Sistema de Gestão e Frente de Caixa para Food Service**

> **Aviso:** Esta é uma versão *Showcase* (Lite) de portfólio. Lógicas comerciais de licenciamento, ofuscação de código, travas de kernel (Mutex) e threads de backup em segundo plano foram removidas para focar na arquitetura web e na usabilidade do projeto.

## 💻 Sobre o Projeto
O **Dominus PDV** foi desenvolvido para resolver a dor de pequenos comércios (pizzarias, lanchonetes e restaurantes) que sofrem com sistemas engessados ou dependência constante de internet. 

A aplicação opera como um servidor local extremamente rápido e leve, unindo a agilidade de um software Desktop com a flexibilidade de uma interface Web. O foco do sistema é a velocidade no balcão e a comunicação profissional com o cliente final.

## 🚀 Principais Funcionalidades (Highlights Técnicos)
* **Frente de Caixa (PDV) de Alta Velocidade:** Interface otimizada para cliques mínimos.
* **Inteligência de Frações:** Lógica desenvolvida para gerenciar produtos complexos, como pizzas fracionadas (1/2, 1/3, 1/4), calculando valores e separando os sabores no cupom.
* **Disparo Nativo para WhatsApp:** Geração dinâmica de recibos formatados (com emojis e quebras de linha corretas via URI Encoding) para envio direto ao WhatsApp do cliente com apenas um clique.
* **Integração com Impressoras Térmicas:** CSS avançado e manipulação de impressão (via navegador ou spooler do SO) forçando contraste máximo para queima térmica (sem cinza/suavização).
* **Gestão de Estoque:** Alertas de estoque mínimo e baixa automática baseada em receitas e insumos.
* **Sistema de Manutenção Embutido:** Interface administrativa para download direto do banco de dados (`.db`) e upload/restauração com auto-restart do servidor local para limpeza de pool de conexões em RAM.

## 🛠️ Stack Tecnológica
**Back-end:**
* Python
* Flask (Web Framework)
* SQLAlchemy (ORM para Banco de Dados)
* Waitress (Servidor WSGI de Produção)

**Front-end:**
* HTML5, CSS3, JavaScript (Vanilla)
* Bootstrap 5 (UI/UX Responsiva)
* SweetAlert2 (Para interações e alertas não-bloqueantes)

**Banco de Dados:**
* SQLite (Local, portátil e ágil)

## ⚙️ Arquitetura e Padrões de Código
O projeto foi estruturado focando em modularidade e fácil manutenção:
* `app.py`: Ponto de entrada, configuração do app e injeção de dependências.
* `routes.py`: Controladores e endpoints da API interna.
* `models.py`: Mapeamento Objeto-Relacional (Tabelas do Banco).
* `extensions.py`: Instanciação de plugins (DB, Login Manager) para evitar importações circulares.
* `utils.py`: Funções utilitárias (formatação de moeda, limpeza de strings, logs).

## 📥 Como rodar a versão Lite localmente

1. Clone este repositório:
   ```bash
   git clone [https://github.com/SEU_USUARIO/Dominus-PDV-Lite.git](https://github.com/SEU_USUARIO/Dominus-PDV-Lite.git)
