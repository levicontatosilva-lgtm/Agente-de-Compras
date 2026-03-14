import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
from datetime import datetime

# Configuração da página
st.set_page_config(
    page_title="Agente de Análise de Compras",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título e descrição
st.title("📊 Agente de Análise de Compras")
st.markdown("""
Analise dados de consumo e gere automaticamente listas de compras otimizadas com margem de segurança.
""")

# ============================================================================
# SIDEBAR - Configurações
# ============================================================================
st.sidebar.header("⚙️ Configurações")

# Upload de arquivo
uploaded_file = st.sidebar.file_uploader(
    "📁 Carregue a planilha de consumo",
    type=["xlsx", "xls", "csv"],
    help="Arquivo com dados de consumo (13 dias)"
)

if uploaded_file is None:
    st.info("👈 Por favor, carregue uma planilha na barra lateral para começar.")
    st.stop()

# Carregar dados
try:
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file)
    else:
        # A planilha do usuário tem 2 linhas de cabeçalho/filtro antes dos nomes das colunas
        df = pd.read_excel(uploaded_file, sheet_name=0, skiprows=2)
except Exception as e:
    st.error(f"❌ Erro ao carregar arquivo: {e}")
    st.stop()

# Tentar encontrar as colunas mesmo com espaços diferentes
df.columns = df.columns.str.strip()

# Verificar se as colunas principais existem
required_cols = ['DESC_NIVEL_MERCADOLOGICO', 'DESCRICAO_EMBALAGEM', 'Cons. no Período', 'Estoque', 'Custo Unit.']
missing_cols = [col for col in required_cols if col not in df.columns]

if missing_cols:
    st.error(f"❌ Colunas faltando: {', '.join(missing_cols)}")
    st.info("Colunas encontradas: " + ", ".join(df.columns.tolist()))
    st.stop()

# Limpar dados - remover linhas de header/filtro
df = df[df['DESC_NIVEL_MERCADOLOGICO'].notna()].copy()
df = df[df['DESC_NIVEL_MERCADOLOGICO'] != 'DESC_NIVEL_MERCADOLOGICO'].copy()

# Converter colunas numéricas
numeric_cols = ['Cons. no Período', 'Estoque', 'Custo Unit.']
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

df = df.dropna(subset=numeric_cols)

st.sidebar.success(f"✅ Arquivo carregado: {len(df)} itens")

# ============================================================================
# SELEÇÃO DE NÍVEIS MERCADOLÓGICOS
# ============================================================================
st.sidebar.markdown("---")
st.sidebar.subheader("📂 Selecione os Níveis Mercadológicos")

niveis_disponiveis = sorted(df['DESC_NIVEL_MERCADOLOGICO'].unique())

# Checkbox "Selecionar Todos"
selecionar_todos = st.sidebar.checkbox("✅ Selecionar todos os níveis", value=True)

if selecionar_todos:
    niveis_selecionados = niveis_disponiveis
else:
    niveis_selecionados = st.sidebar.multiselect(
        "Escolha os níveis mercadológicos para análise:",
        options=niveis_disponiveis,
        default=[]
    )

if not niveis_selecionados:
    st.warning("⚠️ Selecione pelo menos um nível mercadológico para continuar.")
    st.stop()

# Filtrar dados pelos níveis mercadológicos selecionados
df_filtrado = df[df['DESC_NIVEL_MERCADOLOGICO'].isin(niveis_selecionados)].copy()

# ============================================================================
# CONFIGURAÇÕES NA SIDEBAR
# ============================================================================

st.sidebar.markdown("---")
st.sidebar.subheader("📋 Parâmetros de Cálculo")

# Período de cobertura (em dias)
dias_cobertura = st.sidebar.slider(
    "Dias de cobertura da compra",
    min_value=1,
    max_value=30,
    value=7,
    help="Para quantos dias você quer comprar?"
)

# Período da planilha (em dias) - geralmente 13 dias
dias_planilha = st.sidebar.slider(
    "Período da planilha (dias)",
    min_value=1,
    max_value=30,
    value=13,
    help="Quantos dias de consumo a planilha representa?"
)

# Margem de segurança global
margem_seguranca_global = st.sidebar.slider(
    "Margem de segurança global (%)",
    min_value=0,
    max_value=50,
    value=10,
    step=1,
    help="Percentual adicional para cobrir variações de consumo"
)

# ============================================================================
# CÁLCULOS
# ============================================================================

def calcular_necessidade_compra(row, dias_cobertura, dias_planilha, margem_seguranca):
    """
    Calcula a quantidade a comprar baseado em:
    - Consumo do período × (dias de cobertura / dias da planilha)
    - Margem de segurança
    - Estoque atual
    """
    consumo_periodo = row['Cons. no Período']
    estoque_atual = row['Estoque']
    
    # Consumo diário médio = consumo do período / dias da planilha
    consumo_diario = consumo_periodo / dias_planilha
    
    # Consumo previsto para o período de cobertura
    consumo_previsto = consumo_diario * dias_cobertura
    
    # Aplicar margem de segurança
    consumo_com_margem = consumo_previsto * (1 + margem_seguranca / 100)
    
    # Quantidade necessária = consumo com margem - estoque atual
    necessidade = max(0, consumo_com_margem - estoque_atual)
    
    return necessidade

# Aplicar cálculos
df_filtrado['Consumo_Diario_Medio'] = df_filtrado['Cons. no Período'] / dias_planilha
df_filtrado['Consumo_Previsto'] = df_filtrado['Consumo_Diario_Medio'] * dias_cobertura
df_filtrado['Consumo_Com_Margem'] = df_filtrado['Consumo_Previsto'] * (1 + margem_seguranca_global / 100)
df_filtrado['Necessidade_Compra'] = df_filtrado.apply(
    lambda row: calcular_necessidade_compra(
        row,
        dias_cobertura,
        dias_planilha,
        margem_seguranca_global
    ),
    axis=1
)

df_filtrado['Custo_Total'] = df_filtrado['Necessidade_Compra'] * df_filtrado['Custo Unit.']

# Filtrar apenas itens que precisam ser comprados
df_compra = df_filtrado[df_filtrado['Necessidade_Compra'] > 0].copy()
df_compra = df_compra.sort_values(['DESC_NIVEL_MERCADOLOGICO', 'DESCRICAO_EMBALAGEM'])

# ============================================================================
# EXIBIÇÃO DOS RESULTADOS
# ============================================================================

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Total de itens",
        len(df_filtrado),
        help="Itens nos níveis mercadológicos selecionados"
    )

with col2:
    st.metric(
        "Itens a comprar",
        len(df_compra),
        help="Itens com necessidade de reposição"
    )

with col3:
    custo_total = df_compra['Custo_Total'].sum()
    st.metric(
        "Custo total",
        f"R$ {custo_total:,.2f}",
        help="Valor total da compra"
    )

with col4:
    quantidade_total = df_compra['Necessidade_Compra'].sum()
    st.metric(
        "Quantidade total",
        f"{quantidade_total:,.2f}",
        help="Unidades totais a comprar"
    )

st.markdown("---")

# Abas para visualização
tab1, tab2, tab3 = st.tabs(["📋 Lista de Compras", "📊 Análise Detalhada", "📥 Download"])

with tab1:
    st.subheader("Lista de Compras Otimizada")
    
    if len(df_compra) > 0:
        # Tabela formatada para exibição
        df_display = df_compra[[
            'DESC_NIVEL_MERCADOLOGICO',
            'DESCRICAO_EMBALAGEM',
            'Cons. no Período',
            'Consumo_Diario_Medio',
            'Estoque',
            'Necessidade_Compra',
            'Custo Unit.',
            'Custo_Total'
        ]].copy()
        
        df_display.columns = [
            'Nível Mercadológico',
            'Item',
            'Consumo Período',
            'Consumo/Dia',
            'Estoque Atual',
            'Quantidade',
            'Preço Unit.',
            'Total'
        ]
        
        # Formatar números
        df_display['Consumo Período'] = df_display['Consumo Período'].apply(lambda x: f"{x:.2f}")
        df_display['Consumo/Dia'] = df_display['Consumo/Dia'].apply(lambda x: f"{x:.2f}")
        df_display['Estoque Atual'] = df_display['Estoque Atual'].apply(lambda x: f"{x:.2f}")
        df_display['Quantidade'] = df_display['Quantidade'].apply(lambda x: f"{x:.2f}")
        df_display['Preço Unit.'] = df_display['Preço Unit.'].apply(lambda x: f"R$ {x:.2f}")
        df_display['Total'] = df_display['Total'].apply(lambda x: f"R$ {x:.2f}")
        
        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.warning("⚠️ Nenhum item necessita reposição com as configurações atuais.")

with tab2:
    st.subheader("Análise Detalhada por Categoria")
    
    if len(df_compra) > 0:
        # Resumo por nível mercadológico
        resumo_nivel = df_compra.groupby('DESC_NIVEL_MERCADOLOGICO').agg({
            'DESCRICAO_EMBALAGEM': 'count',
            'Necessidade_Compra': 'sum',
            'Custo_Total': 'sum'
        }).rename(columns={
            'DESCRICAO_EMBALAGEM': 'Qtd Itens',
            'Necessidade_Compra': 'Total Quantidade',
            'Custo_Total': 'Total Custo'
        }).sort_values('Total Custo', ascending=False)
        
        resumo_nivel['Total Custo'] = resumo_nivel['Total Custo'].apply(lambda x: f"R$ {x:,.2f}")
        resumo_nivel['Total Quantidade'] = resumo_nivel['Total Quantidade'].apply(lambda x: f"{x:.2f}")
        
        st.dataframe(resumo_nivel, use_container_width=True)
        
        # Gráfico de distribuição de custo por nível mercadológico
        st.subheader("Distribuição de Custo por Nível Mercadológico")
        
        resumo_grafico = df_compra.groupby('DESC_NIVEL_MERCADOLOGICO')['Custo_Total'].sum().sort_values(ascending=False)
        
        st.bar_chart(resumo_grafico)
    else:
        st.warning("⚠️ Nenhum item para análise com as configurações atuais.")

with tab3:
    st.subheader("📥 Exportar Resultados")
    
    if len(df_compra) > 0:
        # Preparar arquivo Excel para download
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Aba 1: Lista de Compras
            df_export = df_compra[[
                'DESC_NIVEL_MERCADOLOGICO',
                'DESCRICAO_EMBALAGEM',
                'Cons. no Período',
                'Consumo_Diario_Medio',
                'Estoque',
                'Necessidade_Compra',
                'Custo Unit.',
                'Custo_Total'
            ]].copy()
            
            df_export.columns = [
                'Nível Mercadológico',
                'Item',
                'Consumo Período',
                'Consumo/Dia',
                'Estoque Atual',
                'Quantidade a Comprar',
                'Preço Unitário',
                'Custo Total'
            ]
            
            df_export.to_excel(writer, sheet_name='Lista de Compras', index=False)
            
            # Aba 2: Resumo por Nível Mercadológico
            resumo_export = df_compra.groupby('DESC_NIVEL_MERCADOLOGICO').agg({
                'DESCRICAO_EMBALAGEM': 'count',
                'Necessidade_Compra': 'sum',
                'Custo_Total': 'sum'
            }).rename(columns={
                'DESCRICAO_EMBALAGEM': 'Qtd Itens',
                'Necessidade_Compra': 'Total Quantidade',
                'Custo_Total': 'Total Custo'
            })
            
            resumo_export.to_excel(writer, sheet_name='Resumo por Nível Mercadológico')
            
            # Aba 3: Configurações utilizadas
            config_export = pd.DataFrame({
                'Parâmetro': [
                    'Data da Análise',
                    'Dias de Cobertura',
                    'Período da Planilha (dias)',
                    'Margem de Segurança Global (%)',
                    'Níveis Mercadológicos Analisados',
                    'Total de Itens',
                    'Itens a Comprar',
                    'Custo Total da Compra'
                ],
                'Valor': [
                    datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                    dias_cobertura,
                    dias_planilha,
                    margem_seguranca_global,
                    len(niveis_selecionados),
                    len(df_filtrado),
                    len(df_compra),
                    f"R$ {df_compra['Custo_Total'].sum():,.2f}"
                ]
            })
            
            config_export.to_excel(writer, sheet_name='Configurações', index=False)
        
        output.seek(0)
        
        st.download_button(
            label="📥 Baixar Lista de Compras (Excel)",
            data=output.getvalue(),
            file_name=f"lista_compras_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Clique para baixar a lista de compras em Excel"
        )
        
        st.success("✅ Arquivo pronto para download!")
    else:
        st.warning("⚠️ Nenhum item para exportar com as configurações atuais.")

# ============================================================================
# FOOTER
# ============================================================================
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #888; font-size: 12px;'>
    <p>🤖 Agente de Análise de Compras v2.1 | Desenvolvido para otimizar sua gestão de estoque</p>
</div>
""", unsafe_allow_html=True)
