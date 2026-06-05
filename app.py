import os
import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime

# Configuração da página do Streamlit
st.set_page_config(page_title="Controle - Balaio Escolar", layout="wide")

# Função de conexão segura (lendo as variáveis de ambiente da Render)
def init_connection():
    if "DATABASE_URL" in os.environ:
        return psycopg2.connect(os.environ["DATABASE_URL"])
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "dpg-d8b35b4m0tmc73d5ovog-a.virginia-postgres.render.com"),
        database=os.getenv("DB_NAME", "balaio"),
        user=os.getenv("DB_USER", "banco_gestao_mh_user"),
        password=os.getenv("DB_PASSWORD", "7nDZqiN920jZKUiyssC5O3JtG9azi0aM"),
        port=os.getenv("DB_PORT", "5432")
    )

conn = init_connection()

st.title("🍇 Gestão de Vendas - Balaio Escolar")

# Quatro abas agora, incluindo a confirmação do bilhete
aba1, aba2, aba3, aba4 = st.tabs([
    "📋 Cadastro de Compradores", 
    "🎟️ Confirmar Preenchimento de Bilhete",
    "💰 Controle Financeiro", 
    "📊 Relatórios & Inadimplência"
])

# --- ABA 1: CADASTRO SIMPLIFICADO ---
with aba1:
    st.header("Novo Cadastro de Venda")
    with st.form("cadastro_cliente"):
        nome_resp = st.text_input("Nome do Comprador / Responsável")
        valor = st.number_input("Valor Combinado (R$)", min_value=0.0, step=10.0)
        
        submit = st.form_submit_button("Salvar Venda")
        
        if submit and nome_resp and valor > 0:
            cursor = conn.cursor()
            # Insere o comprador
            cursor.execute(
                "INSERT INTO clientes (nome_responsavel, valor_combinado) VALUES (%s, %s) RETURNING id;",
                (nome_resp, valor)
            )
            cliente_id = cursor.fetchone()[0]
            
            # Gera a cobrança inicial associada (Inicia com bilhete 'Não' preenchido)
            hoje = datetime.today().date()
            cursor.execute(
                "INSERT INTO financeiro (cliente_id, data_competencia, valor_cobrado, status_pagamento, bilhete_preenchido) VALUES (%s, %s, %s, 'Pendente', 'Não');",
                (cliente_id, hoje, valor)
            )
            
            conn.commit()
            cursor.close()
            st.success(f"Venda para {nome_resp} cadastrada com sucesso!")
            st.rerun()

# --- ABA 2: CONFIRMAR PREENCHIMENTO DO BILHETE (NOVA MUDANÇA) ---
with aba2:
    st.header("Controle de Bilhetes do Comprador")
    st.subheader("Marcar bilhetes que já foram preenchidos e entregues")
    
    # Busca apenas quem ainda NÃO preencheu o bilhete
    query_bilhetes_pendentes = """
        SELECT f.id, c.nome_responsavel, f.valor_cobrado, f.status_pagamento
        FROM financeiro f
        JOIN clientes c ON f.cliente_id = c.id
        WHERE f.bilhete_preenchido = 'Não';
    """
    df_bilhetes = pd.read_sql(query_bilhetes_pendentes, conn)
    
    if not df_bilhetes.empty:
        # Cria uma lista de seleção para marcar como preenchido
        lista_opcoes = {f"{row['nome_responsavel']} - Valor: R${row['valor_cobrado']} ({row['status_pagamento']})": row['id'] for _, row in df_bilhetes.iterrows()}
        
        selecionado_bilhete = st.selectbox("Selecione o comprador que teve o bilhete preenchido:", list(lista_opcoes.keys()))
        id_fin_bilhete = lista_opcoes[selecionado_bilhete]
        
        if st.button("Confirmar Bilhete como PREENCHIDO ✅"):
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE financeiro SET bilhete_preenchido = 'Sim' WHERE id = %s;",
                (id_fin_bilhete,)
            )
            conn.commit()
            cursor.close()
            st.success("Bilhete atualizado com sucesso!")
            st.rerun()
    else:
        st.success("🎉 Todos os bilhetes vendidos já foram preenchidos!")

# --- ABA 3: CONTROLE FINANCEIRO (RECEBIMENTOS) ---
with aba2: # Corrigido para a lógica correta da aba de pagamentos
    pass 
with aba3:
    st.header("Lançar Recebimentos")
    
    query_pendentes = """
        SELECT f.id, c.nome_responsavel, f.valor_cobrado, f.valor_pago, f.status_pagamento 
        FROM financeiro f 
        JOIN clientes c ON f.cliente_id = c.id
        WHERE f.status_pagamento IN ('Pendente', 'Parcial');
    """
    df_pendentes = pd.read_sql(query_pendentes, conn)
    
    if not df_pendentes.empty:
        st.subheader("Cobranças em Aberto")
        opcoes = {f"{row['nome_responsavel']} - Deve: R${row['valor_cobrado'] - row['valor_pago']}": row['id'] for _, row in df_pendentes.iterrows()}
        
        selecionado = st.selectbox("Selecione o Cliente para dar Baixa no Pagamento", list(opcoes.keys()))
        id_financeiro = opcoes[selecionado]
        
        dados_cobranca = df_pendentes[df_pendentes['id'] == id_financeiro].iloc[0]
        saldo_devedor = float(dados_cobranca['valor_cobrado'] - dados_cobranca['valor_pago'])
        
        valor_pagamento = st.number_input("Valor Pago (R$)", min_value=0.0, max_value=saldo_devedor, value=saldo_devedor, step=5.0)
        
        if st.button("Confirmar Recebimento 💰"):
            cursor = conn.cursor()
            novo_valor_pago = float(dados_cobranca['valor_pago']) + valor_pagamento
            novo_status = "Pago" if novo_valor_pago >= float(dados_cobranca['valor_cobrado']) else "Parcial"
            
            cursor.execute(
                "UPDATE financeiro SET valor_pago = %s, status_pagamento = %s, data_pagamento = %s WHERE id = %s;",
                (novo_valor_pago, novo_status, datetime.today().date(), id_financeiro)
            )
            conn.commit()
            cursor.close()
            st.success("Pagamento registrado com sucesso!")
            st.rerun()
    else:
        st.info("Não existem recebimentos pendentes.")

# --- ABA 4: RELATÓRIOS & DEVEDORES (SIMPLIFICADO) ---
with aba4:
    st.header("Painel de Resultados Financeiros")
    
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(valor_cobrado) FROM financeiro;")
    total_vendido = cursor.fetchone()[0] or 0.0
    
    cursor.execute("SELECT SUM(valor_pago) FROM financeiro;")
    total_recebido = cursor.fetchone()[0] or 0.0
    
    cursor.execute("SELECT SUM(valor_cobrado - valor_pago) FROM financeiro WHERE status_pagamento IN ('Pendente', 'Parcial');")
    total_devido = cursor.fetchone()[0] or 0.0
    cursor.close()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Vendido", f"R$ {total_vendido:,.2f}")
    col2.metric("Total Recebido (Caixa)", f"R$ {total_recebido:,.2f}")
    col3.metric("Total a Receber (Devendo)", f"R$ {total_devido:,.2f}", delta=f"-R$ {total_devido:,.2f}", delta_color="inverse")
    
    st.divider()
    
    st.subheader("⚠️ Lista de Compradores com Saldo Devedor")
    
    query_devedores = """
        SELECT c.nome_responsavel AS "Comprador", f.valor_cobrado AS "Valor Total", 
               f.valor_pago AS "Total Pago", (f.valor_cobrado - f.valor_pago) AS "Valor Devido",
               f.bilhete_preenchido AS "Bilhete Entregue?"
        FROM financeiro f
        JOIN clientes c ON f.cliente_id = c.id
        WHERE f.status_pagamento IN ('Pendente', 'Parcial')
        ORDER BY c.nome_responsavel ASC;
    """
    df_devedores = pd.read_sql(query_devedores, conn)
    
    if not df_devedores.empty:
        busca = st.text_input("Filtrar comprador por nome:")
        if busca:
            df_devedores = df_devedores[df_devedores['Comprador'].str.contains(busca, case=False)]
        
        st.dataframe(df_devedores, use_container_width=True)
    else:
        st.success("Tudo pago! Não há devedores no momento.")
