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
Analise dados de consumo e gere automaticamente listas de compras otimizadas com margem de segurança e lotes mínimos.
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
required_cols = ['DESC_NIVEL_MERCADOLOGICO', 'DESCRICAO_EMBALAGEM', 'Consumo Dia', 'Estoque', 'Custo Unit.']
missing_cols = [col for col in required_cols if col not in df.columns]

if missing_cols:
    st.error(f"❌ Colunas faltando: {', '.join(missing_cols)}")
    st.info("Colunas encontradas: " + ", ".join(df.columns.tolist()))
    st.stop()

# Limpar dados - remover linhas de header/filtro
df = df[df['DESC_NIVEL_MERCADOLOGICO'].notna()].copy()
df = df[df['DESC_NIVEL_MERCADOLOGICO'] != 'DESC_NIVEL_MERCADOLOGICO'].copy()

# Converter colunas numéricas
numeric_cols = ['Consumo Dia', 'Estoque', 'Custo Unit.']
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

df = df.dropna(subset=numeric_cols)

st.sidebar.success(f"✅ Arquivo carregado: {len(df)} itens")

# ============================================================================
# CONFIGURAÇÕES NA SIDEBAR
# ============================================================================

st.sidebar.markdown("---")
st.sidebar.subheader("📋 Parâmetros de Cálculo")

# Período de cobertura
dias_cobertura = st.sidebar.slider(
    "Dias de cobertura da compra",
    min_value=1,
    max_value=30,
    value=7,
    help="Para quantos dias você quer comprar?"
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

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 Lotes Mínimos e Margens por Categoria")

# Permitir configuração por categoria
categorias = sorted(df['DESC_NIVEL_MERCADOLOGICO'].unique())
config_por_categoria = {}

for categoria in categorias:
    with st.sidebar.expander(f"📦 {categoria}", expanded=False):
        margem_cat = st.number_input(
            f"Margem de segurança ({categoria})",
            min_value=0,
            max_value=50,
            value=margem_seguranca_global,
            step=1,
            key=f"margem_{categoria}"
        )
        lote_min_cat = st.number_input(
            f"Lote mínimo ({categoria})",
            min_value=0.0,
            value=0.0,
            step=0.1,
            key=f"lote_{categoria}",
            help="Quantidade mínima por compra (0 = sem limite)"
        )
        config_por_categoria[categoria] = {
            'margem': margem_cat,
            'lote_minimo': lote_min_cat
        }

# ============================================================================
# CÁLCULOS
# ============================================================================

def calcular_necessidade_compra(row, dias_cobertura, margem_seguranca, lote_minimo):
    """
    Calcula a quantidade a comprar baseado em:
    - Consumo diário × dias de cobertura
    - Margem de segurança
    - Estoque atual
    - Lote mínimo
    """
    consumo_dia = row['Consumo Dia']
    estoque_atual = row['Estoque']
    
    # Consumo previsto para o período
    consumo_previsto = consumo_dia * dias_cobertura
    
    # Aplicar margem de segurança
    consumo_com_margem = consumo_previsto * (1 + margem_seguranca / 100)
    
    # Quantidade necessária = consumo com margem - estoque atual
    necessidade = max(0, consumo_com_margem - estoque_atual)
    
    # Aplicar lote mínimo
    if lote_minimo > 0:
        # Arredondar para cima para o próximo múltiplo do lote mínimo
        necessidade = np.ceil(necessidade / lote_minimo) * lote_minimo
    
    return necessidade

# Aplicar cálculos
df['Margem_Aplicada'] = df['DESC_NIVEL_MERCADOLOGICO'].apply(
    lambda cat: config_por_categoria.get(cat, {}).get('margem', margem_seguranca_global)
)

df['Lote_Minimo'] = df['DESC_NIVEL_MERCADOLOGICO'].apply(
    lambda cat: config_por_categoria.get(cat, {}).get('lote_minimo', 0)
)

df['Necessidade_Compra'] = df.apply(
    lambda row: calcular_necessidade_compra(
        row,
        dias_cobertura,
        row['Margem_Aplicada'],
        row['Lote_Minimo']
    ),
    axis=1
)

df['Custo_Total'] = df['Necessidade_Compra'] * df['Custo Unit.']

# Filtrar apenas itens que precisam ser comprados
df_compra = df[df['Necessidade_Compra'] > 0].copy()
df_compra = df_compra.sort_values(['DESC_NIVEL_MERCADOLOGICO', 'DESCRICAO_EMBALAGEM'])

# ============================================================================
# EXIBIÇÃO DOS RESULTADOS
# ============================================================================

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Total de itens",
        len(df),
        help="Itens na planilha"
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
    economia_sem_margem = (df_compra['Necessidade_Compra'].sum() * df_compra['Custo Unit.'].mean()) - custo_total
    st.metric(
        "Economia potencial",
        f"R$ {max(0, economia_sem_margem):,.2f}",
        help="Diferença vs. sem margem de segurança"
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
            'Consumo Dia',
            'Estoque',
            'Necessidade_Compra',
            'Lote_Minimo',
            'Margem_Aplicada',
            'Custo Unit.',
            'Custo_Total'
        ]].copy()
        
        df_display.columns = [
            'Categoria',
            'Item',
            'Consumo/Dia',
            'Estoque Atual',
            'Quantidade',
            'Lote Mín.',
            'Margem %',
            'Preço Unit.',
            'Total'
        ]
        
        # Formatar números
        df_display['Consumo/Dia'] = df_display['Consumo/Dia'].apply(lambda x: f"{x:.2f}")
        df_display['Estoque Atual'] = df_display['Estoque Atual'].apply(lambda x: f"{x:.2f}")
        df_display['Quantidade'] = df_display['Quantidade'].apply(lambda x: f"{x:.2f}")
        df_display['Lote Mín.'] = df_display['Lote Mín.'].apply(lambda x: f"{x:.2f}" if x > 0 else "-")
        df_display['Preço Unit.'] = df_display['Preço Unit.'].apply(lambda x: f"R$ {x:.2f}")
        df_display['Total'] = df_display['Total'].apply(lambda x: f"R$ {x:.2f}")
        
        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.warning("⚠️ Nenhum item necessita reposição com as configurações atuais.")

with tab2:
    st.subheader("Análise Detalhada por Categoria")
    
    # Resumo por categoria
    resumo_categoria = df_compra.groupby('DESC_NIVEL_MERCADOLOGICO').agg({
        'DESCRICAO_EMBALAGEM': 'count',
        'Necessidade_Compra': 'sum',
        'Custo_Total': 'sum'
    }).rename(columns={
        'DESCRICAO_EMBALAGEM': 'Qtd Itens',
        'Necessidade_Compra': 'Total Quantidade',
        'Custo_Total': 'Total Custo'
    }).sort_values('Total Custo', ascending=False)
    
    resumo_categoria['Total Custo'] = resumo_categoria['Total Custo'].apply(lambda x: f"R$ {x:,.2f}")
    resumo_categoria['Total Quantidade'] = resumo_categoria['Total Quantidade'].apply(lambda x: f"{x:.2f}")
    
    st.dataframe(resumo_categoria, use_container_width=True)
    
    # Gráfico de distribuição de custo por categoria
    st.subheader("Distribuição de Custo por Categoria")
    
    resumo_grafico = df_compra.groupby('DESC_NIVEL_MERCADOLOGICO')['Custo_Total'].sum().sort_values(ascending=False)
    
    st.bar_chart(resumo_grafico)

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
                'Consumo Dia',
                'Estoque',
                'Necessidade_Compra',
                'Lote_Minimo',
                'Margem_Aplicada',
                'Custo Unit.',
                'Custo_Total'
            ]].copy()
            
            df_export.columns = [
                'Categoria',
                'Item',
                'Consumo/Dia',
                'Estoque Atual',
                'Quantidade a Comprar',
                'Lote Mínimo',
                'Margem Segurança %',
                'Preço Unitário',
                'Custo Total'
            ]
            
            df_export.to_excel(writer, sheet_name='Lista de Compras', index=False)
            
            # Aba 2: Resumo por Categoria
            resumo_export = df_compra.groupby('DESC_NIVEL_MERCADOLOGICO').agg({
                'DESCRICAO_EMBALAGEM': 'count',
                'Necessidade_Compra': 'sum',
                'Custo_Total': 'sum'
            }).rename(columns={
                'DESCRICAO_EMBALAGEM': 'Qtd Itens',
                'Necessidade_Compra': 'Total Quantidade',
                'Custo_Total': 'Total Custo'
            })
            
            resumo_export.to_excel(writer, sheet_name='Resumo por Categoria')
            
            # Aba 3: Configurações utilizadas
            config_export = pd.DataFrame({
                'Parâmetro': [
                    'Data da Análise',
                    'Dias de Cobertura',
                    'Margem de Segurança Global (%)',
                    'Total de Itens na Planilha',
                    'Itens a Comprar',
                    'Custo Total da Compra'
                ],
                'Valor': [
                    datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                    dias_cobertura,
                    margem_seguranca_global,
                    len(df),
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
    <p>🤖 Agente de Análise de Compras v1.0 | Desenvolvido para otimizar sua gestão de estoque</p>
</div>
""", unsafe_allow_html=True)
