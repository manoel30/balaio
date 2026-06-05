import os
import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime
from weasyprint import HTML

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Controle - Balaio Escolar", layout="wide")

# 2. CONEXÃO SEGURA COM O BANCO DE DADOS (RENDER / LOCAL)
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

# 3. TÍTULO DO SISTEMA
st.title("🍇 Gestão de Vendas - Balaio Escolar")

# 4. CRIAÇÃO DAS ABAS DE NAVEGAÇÃO
aba1, aba2, aba3, aba4 = st.tabs([
    "📋 Cadastro de Compradores", 
    "🎟️ Confirmar Entrega de Bilhete",
    "💰 Controle Financeiro", 
    "📊 Painel & Relatório PDF"
])

# --- ABA 1: CADASTRO DE COMPRADORES ---
with aba1:
    st.header("Novo Cadastro de Venda")
    with st.form("cadastro_cliente"):
        nome_resp = st.text_input("Nome do Comprador / Responsável")
        valor = st.number_input("Valor Combinado (R$)", min_value=0.0, step=10.0, value=0.0)
        
        submit = st.form_submit_button("Salvar Venda")
        
        if submit:
            if not nome_resp:
                st.error("Por favor, preencha o nome do comprador.")
            elif valor <= 0:
                st.error("O valor combinado deve ser maior que zero.")
            else:
                cursor = conn.cursor()
                # Insere o comprador na tabela principal
                cursor.execute(
                    "INSERT INTO clientes (nome_responsavel, valor_combinado) VALUES (%s, %s) RETURNING id;",
                    (nome_resp, valor)
                )
                cliente_id = cursor.fetchone()[0]
                
                # Gera a pendência financeira correspondente vinculada
                hoje = datetime.today().date()
                cursor.execute(
                    "INSERT INTO financeiro (cliente_id, data_competencia, valor_cobrado, status_pagamento, bilhete_preenchido) VALUES (%s, %s, %s, 'Pendente', 'Não');",
                    (cliente_id, hoje, valor)
                )
                
                conn.commit()
                cursor.close()
                st.success(f"Venda para {nome_resp} cadastrada com sucesso!")
                st.rerun()

# --- ABA 2: CONFIRMAR PREENCHIMENTO DO BILHETE ---
with aba2:
    st.header("Controle de Bilhetes Emitidos")
    st.subheader("Marcar bilhetes que já foram preenchidos e entregues ao comprador")
    
    # Seleciona apenas os registros onde o bilhete ainda está como 'Não'
    query_bilhetes_pendentes = """
        SELECT f.id, c.nome_responsavel, f.valor_cobrado, f.status_pagamento
        FROM financeiro f
        JOIN clientes c ON f.cliente_id = c.id
        WHERE f.bilhete_preenchido = 'Não'
        ORDER BY c.nome_responsavel ASC;
    """
    df_bilhetes = pd.read_sql(query_bilhetes_pendentes, conn)
    
    if not df_bilhetes.empty:
        opcoes_bilhete = {f"{row['nome_responsavel']} - R${row['valor_cobrado']} ({row['status_pagamento']})": row['id'] for _, row in df_bilhetes.iterrows()}
        
        selecionado_bilhete = st.selectbox("Selecione quem recebeu o bilhete:", list(opcoes_bilhete.keys()))
        id_fin_bilhete = opcoes_bilhete[selecionado_bilhete]
        
        if st.button("Confirmar Bilhete como PREENCHIDO ✅"):
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE financeiro SET bilhete_preenchido = 'Sim' WHERE id = %s;",
                (id_fin_bilhete,)
            )
            conn.commit()
            cursor.close()
            st.success("Status do bilhete atualizado com sucesso!")
            st.rerun()
    else:
        st.success("🎉 Todos os bilhetes físicos já foram preenchidos e entregues!")

# --- ABA 3: CONTROLE FINANCEIRO (RECEBIMENTOS) ---
with aba3:
    st.header("Lançar Recebimentos em Caixa")
    
    # Seleciona apenas as contas com saldo devedor pendente ou parcial
    query_pendentes = """
        SELECT f.id, c.nome_responsavel, f.valor_cobrado, f.valor_pago, f.status_pagamento 
        FROM financeiro f 
        JOIN clientes c ON f.cliente_id = c.id
        WHERE f.status_pagamento IN ('Pendente', 'Parcial')
        ORDER BY c.nome_responsavel ASC;
    """
    df_pendentes = pd.read_sql(query_pendentes, conn)
    
    if not df_pendentes.empty:
        st.subheader("Cobranças em Aberto")
        opcoes_pagamento = {f"{row['nome_responsavel']} - Saldo Devedor: R${row['valor_cobrado'] - row['valor_pago']}": row['id'] for _, row in df_pendentes.iterrows()}
        
        selecionado_pgto = st.selectbox("Selecione o comprador para dar baixa:", list(opcoes_pagamento.keys()))
        id_financeiro = opcoes_pagamento[selecionado_pgto]
        
        dados_cobranca = df_pendentes[df_pendentes['id'] == id_financeiro].iloc[0]
        saldo_devedor = float(dados_cobranca['valor_cobrado'] - dados_cobranca['valor_pago'])
        
        valor_pagamento = st.number_input("Valor Pago Agora (R$)", min_value=0.0, max_value=saldo_devedor, value=saldo_devedor, step=5.0)
        
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
            st.success("Pagamento registrado e atualizado no caixa!")
            st.rerun()
    else:
        st.info("Não existem recebimentos pendentes no sistema.")

# --- ABA 4: PAINEL ANALÍTICO & RELATÓRIO EM PDF ---
with aba4:
    st.header("Painel de Resultados Financeiros")
    
    # Consultas para geração dos blocos de métricas na tela
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
    col2.metric("Total Recebido (Em Caixa)", f"R$ {total_recebido:,.2f}")
    col3.metric("Total a Receber (Em Aberto)", f"R$ {total_devido:,.2f}", delta=f"-R$ {total_devido:,.2f}", delta_color="inverse")
    
    st.divider()
    
    # Seção de exportação do PDF estruturado
    st.subheader("🖨️ Exportação de Relatório de Impressão")
    st.write("Gere um documento formatado em PDF contendo o resumo consolidado e a lista mapeada de compradores.")
    
    if st.button("Gerar PDF de Controle para Impressão"):
        # Busca todas as informações atuais ordenadas por nome
        query_pdf = """
            SELECT c.nome_responsavel, 
                   CASE WHEN f.status_pagamento = 'Pago' THEN 'X' ELSE '' END as pago,
                   CASE WHEN f.status_pagamento IN ('Pendente', 'Parcial') THEN 'X' ELSE '' END as deve,
                   f.bilhete_preenchido
            FROM financeiro f
            JOIN clientes c ON f.cliente_id = c.id
            ORDER BY c.nome_responsavel ASC;
        """
        df_dados = pd.read_sql(query_pdf, conn)
        
        # Contadores dinâmicos para o cabeçalho do PDF
        tot_compras = len(df_dados)
        tot_pagos = len(df_dados[df_dados['pago'] == 'X'])
        tot_deve = len(df_dados[df_dados['deve'] == 'X'])
        tot_falta_b = len(df_dados[df_dados['bilhete_preenchido'] == 'Não'])
        
        # Constrói as linhas da tabela em HTML puro com estilização inline
        linhas_tabela = ""
        for _, row in df_dados.iterrows():
            status_b = '<span style="color:#38a169;">Ok</span>' if row['bilhete_preenchido'] == 'Sim' else '<span style="color:#dd6b20; font-weight:bold;">Falta</span>'
            pago_x = f"<span style='font-weight:bold; color:#2b6cb0;'>{row['pago']}</span>"
            deve_x = f"<span style='font-weight:bold; color:#e53e3e;'>{row['deve']}</span>"
            
            linhas_tabela += f"""
                <tr>
                    <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; font-size: 10pt;">{row['nome_responsavel']}</td>
                    <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; font-size: 11pt; text-align: center;">{pago_x}</td>
                    <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; font-size: 11pt; text-align: center;">{deve_x}</td>
                    <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; font-size: 10pt; text-align: center;">{status_b}</td>
                </tr>
            """
            
        # Estruturação HTML final + CSS compatível com WeasyPrint
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                @page {{ size: A4; margin: 20mm 15mm; @bottom-right {{ content: "Página " counter(page); font-size: 9pt; color: #718096; }} }}
                body {{ font-family: Arial, sans-serif; color: #2d3748; margin: 0; }}
                .header-banner {{ background-color: #1a365d; color: white; padding: 20px; margin: -20mm -15mm 25px -15mm; }}
                .header-banner h1 {{ margin: 0; font-size: 20pt; }}
                .summary-table {{ width: 100%; border-collapse: collapse; margin-bottom: 25px; }}
                .summary-card {{ background-color: #f7fafc; border: 1px solid #e2e8f0; padding: 12px; text-align: center; width: 23%; }}
                .metric-val {{ font-size: 16pt; font-weight: bold; color: #2b6cb0; }}
                .metric-lbl {{ font-size: 8.5pt; color: #4a5568; text-transform: uppercase; margin-top: 2px; }}
                .data-table {{ width: 100%; border-collapse: collapse; }}
                .data-table th {{ background-color: #2b6cb0; color: white; padding: 10px; text-align: left; font-size: 10pt; }}
                .data-table tr:nth-child(even) {{ background-color: #f7fafc; }}
            </style>
        </head>
        <body>
            <div class="header-banner">
                <h1>Relatório de Vendas — Balaio Escolar</h1>
                <p style="margin:5px 0 0 0; color:#90cdf4; font-size:10pt;">Controle Consolidado Atualizado</p>
            </div>
            
            <h3 style="color:#1a365d; border-left:4px solid #3182ce; padding-left:8px;">Resumo Estatístico</h3>
            <table class="summary-table">
                <tr>
                    <td class="summary-card"><div class="metric-val">{tot_compras}</div><div class="metric-lbl">Total Compras</div></td>
                    <td style="width:10px;"></td>
                    <td class="summary-card"><div class="metric-val">{tot_pagos}</div><div class="metric-lbl">Total Pagos</div></td>
                    <td style="width:10px;"></td>
                    <td class="summary-card" style="background-color:#fff5f5; border-color:#fed7d7;"><div class="metric-val" style="color:#c53030;">{tot_deve}</div><div class="metric-lbl">Estão Devendo</div></td>
                    <td style="width:10px;"></td>
                    <td class="summary-card" style="background-color:#fffaf0; border-color:#feebc8;"><div class="metric-val" style="color:#dd6b20;">{tot_falta_b}</div><div class="metric-lbl">Falta Bilhete</div></td>
                </tr>
            </table>
            
            <h3 style="color:#1a365d; border-left:4px solid #3182ce; padding-left:8px;">Lista Mapeada de Compradores</h3>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Nome do Comprador</th>
                        <th style="text-align:center; width:90px;">Pago</th>
                        <th style="text-align:center; width:90px;">Deve</th>
                        <th style="text-align:center; width:90px;">Bilhete</th>
                    </tr>
                </thead>
                <tbody>
                    {linhas_tabela}
                </tbody>
            </table>
        </body>
        </html>
        """
        
        # Converte a string HTML montada em um PDF armazenado temporariamente
        output_name = "relatorio_controle_sistema.pdf"
        HTML(string=html_template).write_pdf(output_name)
        
        # Disponibiliza o botão de Download direto na tela do usuário
        with open(output_name, "rb") as pdf_file:
            st.download_button(
                label="⬇️ Baixar Arquivo PDF Gerado",
                data=pdf_file,
                file_name=f"relatorio_balaio_{datetime.today().strftime('%d_%m_%Y')}.pdf",
                mime="application/pdf"
            )
