import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime

# Configuração da página do Streamlit
st.set_page_config(page_title="Controle - Balaio Escolar", layout="wide")

# Função para conectar ao banco de dados PostgreSQL
def init_connection():
    return psycopg2.connect(
        host="srv-d8h24c48aovs73el4bgg",
        database="balaio",
        user="banco_gestao_mh_user",
        password="7nDZqiN920jZKUiyssC5O3JtG9azi0aM",
        port="5432"
    )

conn = init_connection()

# Título do Aplicativo
st.title("🍇 Gestão de Vendas - Balaio Escolar")

# Navegação por Abas (Abas solicitadas)
aba1, aba2, aba3 = st.tabs(["📋 Cadastro de Assinantes", "💰 Controle Financeiro", "📊 Relatórios & Inadimplência"])

# --- ABA 1: CADASTRO DE ASSINANTES ---
with aba1:
    st.header("Novo Cadastro de Assinatura")
    with st.form("cadastro_cliente"):
        nome_resp = st.text_input("Nome do Responsável")
        nome_aluno = st.text_input("Nome do Aluno")
        telefone = st.text_input("Telefone de Contato")
        plano = st.selectbox("Plano Assinado", ["Mensal", "Semanal", "Diário"])
        valor = st.number_input("Valor Combinado (R$)", min_value=0.0, step=10.0)
        
        submit = st.form_submit_button("Salvar Cadastro")
        
        if submit and nome_resp and valor > 0:
            cursor = conn.cursor()
            # Insere o cliente
            cursor.execute(
                "INSERT INTO clientes (nome_responsavel, nome_aluno, telefone, plano_assinado, valor_combinado) VALUES (%s, %s, %s, %s, %s) RETURNING id;",
                (nome_resp, nome_aluno, telefone, plano, valor)
            )
            cliente_id = cursor.fetchone()[0]
            
            # Gera automaticamente a primeira cobrança para o mês atual
            hoje = datetime.today().date()
            cursor.execute(
                "INSERT INTO financeiro (cliente_id, data_competencia, valor_cobrado, status_pagamento) VALUES (%s, %s, %s, 'Pendente');",
                (cliente_id, hoje, valor)
            )
            
            conn.commit()
            cursor.close()
            st.success(f"Assinatura de {nome_resp} cadastrada com sucesso e cobrança gerada!")

# --- ABA 2: CONTROLE FINANCEIRO (RECEBIMENTOS) ---
with aba2:
    st.header("Lançar Recebimentos")
    
    # Buscar cobranças pendentes ou parciais para dar baixa
    query_pendentes = """
        SELECT f.id, c.nome_responsavel, c.nome_aluno, f.valor_cobrado, f.valor_pago, f.status_pagamento 
        FROM financeiro f 
        JOIN clientes c ON f.cliente_id = c.id
        WHERE f.status_pagamento IN ('Pendente', 'Parcial');
    """
    df_pendentes = pd.read_sql(query_pendentes, conn)
    
    if not df_pendentes.empty:
        st.subheader("Cobranças em Aberto")
        # Criar uma lista para seleção no formulário de baixa
        opcoes = {f"{row['nome_responsavel']} ({row['nome_aluno']}) - Deve: R${row['valor_cobrado'] - row['valor_pago']}": row['id'] for _, row in df_pendentes.iterrows()}
        
        selecionado = st.selectbox("Selecione o Cliente para dar Baixa", list(opcoes.keys()))
        id_financeiro = opcoes[selecionado]
        
        # Obter dados da cobrança selecionada
        dados_cobranca = df_pendentes[df_pendentes['id'] == id_financeiro].iloc[0]
        saldo_devedor = float(dados_cobranca['valor_cobrado'] - dados_cobranca['valor_pago'])
        
        valor_pagamento = st.number_input("Valor Pago (R$)", min_value=0.0, max_value=saldo_devedor, value=saldo_devedor, step=5.0)
        
        if st.button("Confirmar Recebimento"):
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
        st.info("Não existem cobranças pendentes no momento.")

# --- ABA 3: RELATÓRIOS (TOTAL VENDIDO E FILTROS DE DEVEDORES) ---
with aba3:
    st.header("Painel de Resultados Financeiros")
    
    # 1. Indicador de Total Vendido (Faturado)
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(valor_cobrado) FROM financeiro;")
    total_vendido = cursor.fetchone()[0] or 0.0
    
    cursor.execute("SELECT SUM(valor_pago) FROM financeiro;")
    total_recebido = cursor.fetchone()[0] or 0.0
    
    cursor.execute("SELECT SUM(valor_cobrado - valor_pago) FROM financeiro WHERE status_pagamento IN ('Pendente', 'Parcial');")
    total_devido = cursor.fetchone()[0] or 0.0
    cursor.close()
    
    # Exibição de métricas em colunas
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Vendido (Faturamento)", f"R$ {total_vendido:,.2f}")
    col2.metric("Total Recebido em Caixa", f"R$ {total_recebido:,.2f}")
    col3.metric("Total a Receber (Inadimplência)", f"R$ {total_devido:,.2f}", delta=f"-R$ {total_devido:,.2f}", delta_color="inverse")
    
    st.divider()
    
    # 2. Filtro de quem está devendo
    st.subheader("⚠️ Filtro de Clientes com Saldos Pendentes")
    
    query_devedores = """
        SELECT c.nome_responsavel AS "Responsável", c.nome_aluno AS "Aluno", c.telefone AS "Telefone",
               f.data_competencia AS "Mês Referência", f.valor_cobrado AS "Valor Total", 
               f.valor_pago AS "Total Pago", (f.valor_cobrado - f.valor_pago) AS "Valor Devido"
        FROM financeiro f
        JOIN clientes c ON f.cliente_id = c.id
        WHERE f.status_pagamento IN ('Pendente', 'Parcial')
        ORDER BY f.data_competencia ASC;
    """
    
    df_devedores = pd.read_sql(query_devedores, conn)
    
    if not df_devedores.empty:
        # Permite pesquisar um devedor específico na tabela
        busca = st.text_input("Filtrar devedor por nome:")
        if busca:
            df_devedores = df_devedores[
                df_devedores['Responsável'].str.contains(busca, case=False) | 
                df_devedores['Aluno'].str.contains(busca, case=False)
            ]
        
        st.dataframe(df_devedores, use_container_width=True)
    else:
        st.success("Excelente! Todos os clientes estão em dia.")
