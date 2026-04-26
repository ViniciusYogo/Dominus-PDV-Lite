import sqlite3
import os

# Apontando para o seu banco VERDADEIRO
caminho_banco = 'instance/estoque_pizzaria.db' 

comandos_config = [
    "ALTER TABLE configuracao ADD COLUMN taxa_credito FLOAT DEFAULT 3.19",
    "ALTER TABLE configuracao ADD COLUMN prazo_credito INTEGER DEFAULT 30",
    "ALTER TABLE configuracao ADD COLUMN taxa_debito FLOAT DEFAULT 1.99",
    "ALTER TABLE configuracao ADD COLUMN prazo_debito INTEGER DEFAULT 1"
]

comandos_venda = [
    "ALTER TABLE venda ADD COLUMN valor_bruto FLOAT DEFAULT 0.0",
    "ALTER TABLE venda ADD COLUMN valor_liquido FLOAT DEFAULT 0.0",
    "ALTER TABLE venda ADD COLUMN taxa_aplicada FLOAT DEFAULT 0.0",
    "ALTER TABLE venda ADD COLUMN data_recebimento_previsto DATETIME"
]

if not os.path.exists(caminho_banco):
    print(f"❌ ERRO: O arquivo '{caminho_banco}' NÃO EXISTE. Verifique se a pasta 'instance' está no mesmo local que você está rodando o script.")
    exit()

try:
    conn = sqlite3.connect(caminho_banco)
    cursor = conn.cursor()

    print(f"⚙️ Conectado ao banco VERDADEIRO: {caminho_banco}\n")

    print("--- Tabela: CONFIGURAÇÃO ---")
    for sql in comandos_config:
        try:
            cursor.execute(sql)
            print(f"✅ Executado: {sql.split('ADD COLUMN ')[1]}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"⚠️ Coluna já existe: {sql.split('ADD COLUMN ')[1]}")
            else:
                print(f"❌ Erro SQL: {e}")

    print("\n--- Tabela: VENDA ---")
    for sql in comandos_venda:
        try:
            cursor.execute(sql)
            print(f"✅ Executado: {sql.split('ADD COLUMN ')[1]}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"⚠️ Coluna já existe: {sql.split('ADD COLUMN ')[1]}")
            else:
                print(f"❌ Erro SQL: {e}")

    conn.commit()
    print("\n🚀 Atualização concluída com sucesso! Pode subir o seu Dominus PDV.")

except Exception as e:
    print(f"\n❌ Erro crítico: {e}")
finally:
    if 'conn' in locals():
        conn.close()