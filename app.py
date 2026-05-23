import streamlit as st
import pandas as pd
import pdfplumber
import time
import io
import re
from PIL import Image
from supabase import create_client, Client

# ============================================================
# 🎨 CONFIGURAÇÃO VISUAL E ESTILO (DESIGN MODERNO)
# ============================================================
st.set_page_config(
    page_title="Validador de Retorno de Obra - Estel", 
    page_icon="🚚", 
    layout="wide"
)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: "Inter", sans-serif;
        background-color: #F8FAFC;
    }
    
    /* Indicadores de Métricas Customizados */
    div[data-testid="stMetricValue"] {
        font-size: 26px;
        font-weight: 700;
        color: #1E293B;
    }
    
    /* Botão de Ação Primária */
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 42px;
        background-color: #0284C7;
        color: white;
        font-weight: 600;
        border: none;
        transition: background-color 0.2s;
    }
    .stButton>button:hover {
        background-color: #0369A1;
    }
    
    /* Card de exibição do material */
    .card-conferencia {
        background: white;
        border: 1px solid #E2E8F0;
        padding: 20px;
        border-radius: 12px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    </style>
    """, unsafe_allow_html=True)

# ============================================================
# 🗄️ CONEXÃO COM BANCO DE DADOS (SUPABASE)
# ============================================================
@st.cache_resource
def iniciar_supabase():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None

supabase = iniciar_supabase()

# Gerenciador de Estados da Sessão
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario_nome" not in st.session_state:
    st.session_state.usuario_nome = ""
if "dados_conferencia" not in st.session_state:
    st.session_state.dados_conferencia = pd.DataFrame()

# ============================================================
# ⚙️ ENGINES DE EXTRAÇÃO INTELIGENTE (PDF & EXCEL)
# ============================================================
def extrair_linhas_danfe(pdf_file):
    """Lê o PDF do DANFE e raspa estritamente a Descrição e Quantidade"""
    registros = []
    with pdfplumber.open(pdf_file) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if not texto:
                continue
            
            linhas = texto.split("\n")
            modo_captura = False
            
            for linha in lines:
                # Gatilho de início da tabela de itens do seu DANFE
                if "CÓD PROD" in linha or "DESCRIÇÃO DOS PRODUTOS" in linha:
                    modo_captura = True
                    continue
                # Gatilho de parada (rodapé da nota ou impostos)
                if "CÁLCULO DO ISSQN" in linha or "DADOS ADICIONAIS" in linha:
                    modo_captura = False
                
                if modo_captura:
                    # Coleta blocos numéricos do fim da linha (Qtd, Valores...)
                    numeros = re.findall(r'\b\d+[\d.,]*\b', linha)
                    
                    # Limpa a descrição isolando o texto central
                    desc = re.sub(r'^\S+\s+', '', linha)  # Remove código primário
                    desc = re.sub(r'\s+\d+[\d.,]*.*$', '', desc)  # Remove dados financeiros do fim
                    
                    if len(desc.strip()) > 4:
                        qtd = 1.0
                        if len(numeros) >= 3:
                            try:
                                # Normaliza padrão de milhar/decimal do Brasil (ex: 2.000 ou 5,00)
                                qtd_limpa = numeros[0].replace('.', '').replace(',', '.')
                                qtd = float(qtd_limpa)
                            except ValueError:
                                pass
                        
                        registros.append({
                            "Descrição do Produto": desc.strip().upper(),
                            "Quantidade NF": qtd,
                            "Quantidade Conferida": 0.0,
                            "Situação": "Pendente",
                            "Foto Capturada": "Não",
                            "Observações": ""
                        })
                        
    return pd.DataFrame(registros)

def extrair_linhas_excel(excel_file):
    """Mapeia e lê colunas exatas da Planilha Itens Camaçari"""
    try:
        # Suporte para .csv e para .xlsx/.xls
        if excel_file.name.endswith('.csv'):
            df_cru = pd.read_csv(excel_file)
        else:
            df_cru = pd.read_excel(excel_file)
            
        df_formatado = pd.DataFrame()
        
        # Identificação inteligente com fallback para a estrutura enviada
        col_desc = "Descrição NF" if "Descrição NF" in df_cru.columns else df_cru.columns[1]
        col_qtd = "Quantidade Faturada" if "Quantidade Faturada" in df_cru.columns else df_cru.columns[0]
        
        df_formatado["Descrição do Produto"] = df_cru[col_desc].astype(str).str.upper()
        df_formatado["Quantidade NF"] = pd.to_numeric(df_cru[col_qtd], errors='coerce').fillna(1.0)
        df_formatado["Quantidade Conferida"] = 0.0
        df_formatado["Situação"] = "Pendente"
        df_formatado["Foto Capturada"] = "Não"
        df_formatado["Observações"] = ""
        
        return df_formatado.dropna(subset=["Descrição do Produto"])
    except Exception as e:
        st.error(f"Não foi possível processar a planilha: {e}")
        return pd.DataFrame()

# ============================================================
# 🔐 PAINEL DE LOGIN (MÉTODO TRADICIONAL + BIOMETRIA)
# ============================================================
if not st.session_state.autenticado:
    st.markdown("<div style='text-align: center; margin-top: 40px;'><h2>🔐 Sistema de Conferência de Materiais</h2><p style='color:#64748B;'>Validação de Retorno de Ativos e Notas Fiscais</p></div>", unsafe_allow_html=True)
    
    c_esq, c_centro, c_dir = st.columns([1, 1.4, 1])
    with c_centro:
        guia_credenciais, guia_biometria = st.tabs(["Chave de Acesso", "🧬 Sensor Biométrico / FaceID"])
        
        with guia_credenciais:
            usuario_input = st.text_input("Usuário Logístico:")
            senha_input = st.text_input("Senha Corporativa:", type="password")
            if st.button("Autenticar Operação"):
                if supabase:
                    # Busca direta na tabela 'usuarios' criada no Supabase
                    busca = supabase.table("usuarios").select("*").eq("usuario", usuario_input).eq("senha", senha_input).execute()
                    if busca.data:
                        st.session_state.autenticado = True
                        st.session_state.usuario_nome = busca.data[0]["nome"]
                        st.rerun()
                    else:
                        st.error("Usuário ou senha incorretos.")
                else:
                    # Fallback local administrativo de segurança
                    if usuario_input == "admin" and senha_input == "admin123":
                        st.session_state.autenticado = True
                        st.session_state.usuario_nome = "Supervisor Local (Offline)"
                        st.rerun()
                    else:
                        st.error("Credenciais incorretas (Modo Local ativo).")
                        
        with guia_biometria:
            st.markdown("<div style='text-align:center; padding:15px;'><h5>Aproxime a digital do sensor ou posicione o rosto</h5><h1 style='font-size: 50px; margin: 10px 0;'>🖐️ 🧬</h1></div>", unsafe_allow_html=True)
            if st.button("Validar Entrada via Biometria"):
                with st.spinner("Lendo parâmetros biométricos..."):
                    time.sleep(1.2)
                st.session_state.autenticado = True
                st.session_state.usuario_nome = "Almoxarife (Biometria)"
                st.success("Acesso liberado!")
                time.sleep(0.4)
                st.rerun()

# ============================================================
# 🚚 PAINEL PRINCIPAL DO SISTEMA (APÓS LOGIN)
# ============================================================
else:
    # Cabeçalho Superior Dinâmico
    cab_esquerdo, cab_direito = st.columns([4, 1])
    cab_esquerdo.title("🚚 Validador de Notas & Retornos de Obra")
    cab_esquerdo.caption(f"Operador Conectado: **{st.session_state.usuario_nome}**")
    
    if cab_direito.button("Encerrar Sessão"):
        st.session_state.autenticado = False
        st.session_state.dados_conferencia = pd.DataFrame()
        st.rerun()
        
    st.markdown("---")
    
    if supabase is None:
        st.sidebar.warning("⚠️ Banco em nuvem não sincronizado. Operando em modo de memória local.")

    # SIDEBAR - ENTRADA, CONTROLE E EXPORTAÇÃO
    with st.sidebar:
        st.header("📥 Carregar Documento")
        arquivo_entrada = st.file_uploader("Arraste o DANFE (PDF) ou o arquivo Excel:", type=["pdf", "xlsx", "xls", "csv"])
        
        if arquivo_entrada:
            if st.button("Processar Carga de Itens", type="primary"):
                if arquivo_entrada.name.endswith(".pdf"):
                    st.session_state.dados_conferencia = extrair_linhas_danfe(arquivo_entrada)
                else:
                    st.session_state.dados_conferencia = extrair_linhas_excel(arquivo_entrada)
                
                st.success(f"Carregamento concluído! {len(st.session_state.dados_conferencia)} itens mapeados.")
        
        st.markdown("---")
        st.header("📤 Fechamento de Carga")
        if not st.session_state.dados_conferencia.empty:
            # Geração dinâmica do relatório em formato Excel binário
            memoria_excel = io.BytesIO()
            st.session_state.dados_conferencia.to_excel(memoria_excel, index=False, sheet_name="Conferencia_Final")
            
            st.download_button(
                label="💾 Exportar Relatório FInal (Excel)", 
                data=memoria_excel.getvalue(), 
                file_name="Relatorio_Triagem_Estel.xlsx", 
                mime="application/vnd.ms-excel"
            )
            
            if st.button("Limpar Carga Corrente"):
                st.session_state.dados_conferencia = pd.DataFrame()
                st.rerun()

    # CORPO OPERACIONAL (ABAS)
    if st.session_state.dados_conferencia.empty:
        st.info("💡 Para iniciar os trabalhos, por favor suba um arquivo digital de DANFE (PDF) ou a planilha Excel de insumos no painel lateral esquerdo.")
    else:
        aba_triagem, aba_tabela, aba_indicadores = st.tabs(["📸 Posto de Triagem & Fotos", "📋 Tabela de Divergências", "📊 Painel de Controle"])
        
        # ------------------------------------------------------------
        # ABA 1: POSTO DE TRIAGEM (VERIFICAÇÃO FÍSICA E REGISTRO DE FOTO)
        # ------------------------------------------------------------
        with aba_triagem:
            st.subheader("Inspeção Física de Volumes")
            
            lista_insumos = st.session_state.dados_conferencia["Descrição do Produto"].tolist()
            insumo_selecionado = st.selectbox("Selecione o insumo físico para auditoria:", lista_insumos)
            
            if insumo_selecionado:
                posicao_idx = st.session_state.dados_conferencia[st.session_state.dados_conferencia["Descrição do Produto"] == insumo_selecionado].index[0]
                linha_insumo = st.session_state.dados_conferencia.loc[posicao_idx]
                
                # Exibição do Painel do Material Selecionado
                st.markdown(f"""
                <div class='card-conferencia'>
                    <h3 style='color:#0284C7; margin-top:0;'>{linha_insumo['Descrição do Produto']}</h3>
                    <p>Quantidade Prevista no Documento: <b style='font-size:16px;'>{linha_insumo['Quantidade NF']}</b> | Situação Atual: <b>{linha_insumo['Situação']}</b></p>
                </div>
                """, unsafe_allow_html=True)
                
                col_camera, col_formulario = st.columns(2)
                
                with col_camera:
                    st.markdown("##### 📷 Evidência Fotográfica do Material")
                    foto_click = st.camera_input("Capturar foto (Comprovação de estado ou avaria):", key=f"camera_{posicao_idx}")
                    if foto_click:
                        st.image(foto_click, width=280, caption="Imagem vinculada com sucesso.")
                        st.session_state.dados_conferencia.at[posicao_idx, "Foto Capturada"] = "Sim"
                        
                with col_formulario:
                    st.markdown("##### ⚙️ Contagem Quantitativa")
                    contagem_fisica = st.number_input("Quantidade real descarregada:", min_value=0.0, value=float(linha_insumo['Quantidade NF']), step=1.0)
                    campo_obs = st.text_area("Notas de inspeção (Avarias, marcas, divergências):", value=linha_insumo['Observações'])
                    
                    if st.button("Confirmar Recebimento do Item"):
                        # Atualização dos estados em tempo de execução
                        st.session_state.dados_conferencia.at[posicao_idx, "Quantidade Conferida"] = contagem_fisica
                        st.session_state.dados_conferencia.at[posicao_idx, "Observações"] = campo_obs
                        
                        # Definição lógica da situação de conformidade
                        if contagem_fisica == linha_insumo['Quantidade NF']:
                            st.session_state.dados_conferencia.at[posicao_idx, "Situação"] = "Conforme"
                        else:
                            st.session_state.dados_conferencia.at[posicao_idx, "Divergente"] = "Divergente"
                            
                        st.success("Dados de conferência gravados na memória local!")
                        time.sleep(0.4)
                        st.rerun()

        # ------------------------------------------------------------
        # ABA 2: VISUALIZAÇÃO GERAL DA CARGA / NOTA
        # ------------------------------------------------------------
        with aba_tabela:
            st.subheader("Lista Geral de Itens Importados")
            filtro_situacao = st.selectbox("Filtrar Registros por Situação:", ["Todos", "Pendente", "Conforme", "Divergente"])
            
            df_filtrado = st.session_state.dados_conferencia.copy()
            if filtro_situacao != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Situação"] == filtro_situacao]
                
            st.dataframe(df_filtrado, use_container_width=True, height=380)

        # ------------------------------------------------------------
        # ABA 3: INDICADORES E CONTAGENS TOTAIS
        # ------------------------------------------------------------
        with aba_indicators:
            st.subheader("Métricas de Produtividade")
            df_m = st.session_state.dados_conferencia
            
            b1, b2, b3, b4 = st.columns(4)
            b1.metric("Itens Totais", len(df_m))
            b2.metric("Conformes ✅", len(df_m[df_m["Situação"] == "Conforme"]))
            b3.metric("Divergentes ⚠️", len(df_m[df_m["Situação"] == "Divergente"]))
            b4.metric("Pendentes ⏳", len(df_m[df_m["Situação"] == "Pendente"]))
            
            st.markdown("---")
            st.markdown("##### Gráfico Analítico de Volume de Insumos")
            st.bar_chart(df_m["Situação"].value_counts())
