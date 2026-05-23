import streamlit as st
import pandas as pd
import time
import io
import re
import json
import numpy as np
from PIL import Image
from supabase import create_client, Client
import cv2

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
    html, body, [class*="css"] { font-family: "Inter", sans-serif; background-color: #F8FAFC; }
    div[data-testid="stMetricValue"] { font-size: 26px; font-weight: 700; color: #1E293B; }
    .stButton>button { width: 100%; border-radius: 8px; height: 42px; background-color: #0284C7; color: white; font-weight: 600; border: none; }
    .stButton>button:hover { background-color: #0369A1; }
    .stCameraInput>div>button { background-color: #0284C7 !important; color: white !important; }
    .card-conferencia { background: white; border: 1px solid #E2E8F0; padding: 20px; border-radius: 12px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    [data-testid="stSidebar"] { background-color: white; border-right: 1px solid #E2E8F0; }
    </style>
    """, unsafe_allow_html=True)

# ============================================================
# 🗄️ CONEXÃO COM BANCO DE DADOS (SUPABASE)
# ============================================================
SUPABASE_AVAILABLE = False
supabase = None

try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)
    SUPABASE_AVAILABLE = True
except Exception:
    pass

if "autenticado" not in st.session_state: st.session_state.autenticado = False
if "usuario_nome" not in st.session_state: st.session_state.usuario_nome = ""
if "dados_conferencia" not in st.session_state: st.session_state.dados_conferencia = pd.DataFrame()

# ============================================================
# 🧠 VALIDAÇÃO FACIAL COMPATÍVEL E VELOZ (OPENCV)
# ============================================================
def verificar_presenca_operador(imagem_st):
    """Detecta se há um rosto focado na câmera do posto usando Haar Cascade"""
    try:
        image = Image.open(imagem_st)
        image_np = np.array(image.convert('RGB'))
        gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
        
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        
        return len(faces) > 0
    except Exception:
        return False

# ============================================================
# ⚙️ ENGINES DE EXTRAÇÃO DE DADOS (PDF & EXCEL)
# ============================================================
FITZ_AVAILABLE = False
try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    pass

def extrair_linhas_danfe(pdf_file):
    registros = []
    full_text = ""
    try:
        pdf_bytes = pdf_file.read()
        if FITZ_AVAILABLE:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for pagina in doc: full_text += pagina.get_text()
            doc.close()
        else:
            from pdfminer.high_level import extract_text
            from io import BytesIO
            full_text = extract_text(BytesIO(pdf_bytes))
        
        if not full_text: return pd.DataFrame()
        linhas = full_text.split("\n")
        modo_captura = False
        
        for linha in linhas:
            linha = linha.strip()
            if not linha: continue
            if re.search(r'C\.D(\.)?\s*PROD|DESCRI\.O\s*DO(\s*S)?\s*PRODUTO', linha, re.IGNORECASE):
                modo_captura = True
                continue
            if re.search(r'C\.LCULO\s*DO\s*ISSQN|DADOS\s*ADICIONAIS|TRANSPORTADOR', linha, re.IGNORECASE):
                modo_captura = False
                break
            
            if modo_captura:
                numeros = re.findall(r'\b\d+[\d.,]*\b', linha)
                desc = re.sub(r'^\d+\s+', '', linha)
                desc = re.sub(r'\s*\d+[\d.,]*.*$', '', desc)
                
                if len(desc.strip()) > 5 and len(numeros) >= 3 and not desc.strip().isdigit():
                    qtd = 1.0
                    try: qtd = float(numeros[0].replace('.', '').replace(',', '.'))
                    except ValueError: pass
                        
                    registros.append({
                        "Descrição do Produto": desc.strip().upper(), "Quantidade NF": qtd,
                        "Quantidade Conferida": 0.0, "Situação": "Pendente",
                        "Foto Capturada": "Não", "Observações": ""
                    })
    except Exception as e:
        st.error(f"Erro ao processar PDF: {e}")
    df = pd.DataFrame(registros)
    if not df.empty: df = df.drop_duplicates(subset=["Descrição do Produto"], keep="first")
    return df

def extrair_linhas_excel(excel_file):
    try:
        df_cru = pd.read_csv(excel_file, encoding='latin1') if excel_file.name.endswith('.csv') else pd.read_excel(excel_file)
        if df_cru.empty: return pd.DataFrame()
        df_formatado = pd.DataFrame()
        col_desc = next((c for c in df_cru.columns if "DESCRI" in c.upper()), df_cru.columns[1] if len(df_cru.columns) > 1 else df_cru.columns[0])
        col_qtd = next((c for c in df_cru.columns if "QTD" in c.upper() or "QUANT" in c.upper()), df_cru.columns[0])
        df_formatado["Descrição do Produto"] = df_cru[col_desc].astype(str).str.strip().str.upper()
        df_formatado["Quantidade NF"] = pd.to_numeric(df_cru[col_qtd], errors='coerce').fillna(1.0)
        df_formatado["Quantidade Conferida"] = 0.0
        df_formatado["Situação"] = "Pendente"
        df_formatado["Foto Capturada"] = "Não"
        df_formatado["Observações"] = ""
        return df_formatado[df_formatado["Descrição do Produto"].str.len() > 2]
    except Exception: return pd.DataFrame()

# ============================================================
# 🔐 PAINEL DE AUTENTICAÇÃO (FLUXO ÚNICO SEGURO)
# ============================================================
if not st.session_state.autenticado:
    st.markdown("""
        <div style='text-align: center; margin-top: 50px; margin-bottom: 30px;'>
            <h1 style='color:#0284C7; font-size: 32px;'>🔐 Sistema de Conferência de Materials</h1>
            <p style='color:#64748B; font-size: 16px;'>Validação do Posto de Triagem - Estel Engenharia</p>
        </div>
    """, unsafe_allow_html=True)
    
    c_esq, c_centro, c_dir = st.columns([1, 1.4, 1])
    
    with c_centro:
        st.markdown("<p style='text-align:center; color:#475569;'>Olhe para a câmera para liberar a assinatura digital do posto.</p>", unsafe_allow_html=True)
        foto_scanner = st.camera_input("Identificação Visual do Operador:", key="login_validador_posto")
        
        if foto_scanner:
            with st.spinner("Verificando enquadramento..."):
                rosto_presente = verificar_presenca_operador(foto_scanner)
                
                if rosto_presente:
                    st.success("✅ Presença de operador confirmada em frente à câmera!")
                    st.markdown("---")
                    
                    usuario_input = st.text_input("Usuário Logístico (Almoxarifado):")
                    senha_input = st.text_input("Senha Corporativa:", type="password")
                    
                    col_btn1, col_btn2 = st.columns(2)
                    
                    with col_btn1:
                        if st.button("Confirmar Entrada e Acessar", type="primary"):
                            if supabase and SUPABASE_AVAILABLE:
                                busca = supabase.table("usuarios").select("*").eq("usuario", usuario_input).eq("senha", senha_input).execute()
                                if busca.data:
                                    st.session_state.autenticado = True
                                    st.session_state.usuario_nome = busca.data[0]["nome"]
                                    st.rerun()
                                else:
                                    st.error("❌ Credenciais incorretas.")
                            else:
                                if usuario_input == "admin" and senha_input == "admin":
                                    st.session_state.autenticado = True
                                    st.session_state.usuario_nome = "Supervisor Logístico (Local)"
                                    st.rerun()
                                else:
                                    st.error("❌ Banco offline. Use admin/admin na contingência.")
                    
                    with col_btn2:
                        with st.expander("📝 Não tem usuário? Cadastre-se agora"):
                            nome_cad = st.text_input("Nome Completo:")
                            user_cad = st.text_input("ID Usuário Corporativo:")
                            senha_cad = st.text_input("Crie uma Senha:", type="password")
                            
                            if st.button("Salvar Registro"):
                                if nome_cad and user_cad and senha_cad and supabase and SUPABASE_AVAILABLE:
                                    try:
                                        supabase.table("usuarios").insert({
                                            "nome": nome_cad, "usuario": user_cad, "senha": senha_cad
                                        }).execute()
                                        st.success("🎉 Cadastrado com sucesso! Insira os dados acima para entrar.")
                                    except Exception as e:
                                        st.error(f"Erro ao salvar: {e}")
                                else:
                                    st.error("Preencha todos os campos corporativos.")
                else:
                    st.error("⚠️ Enquadramento inválido. Centralize seu rosto de frente para a câmera.")

# ============================================================
# 🚚 PAINEL PRINCIPAL DO SISTEMA (PÓS-LOGIN)
# ============================================================
else:
    cab_esquerdo, cab_direito = st.columns([4, 1])
    cab_esquerdo.markdown(f"<h1>🚚 Validador de Retornos de Obra</h1>", unsafe_allow_html=True)
    cab_esquerdo.caption(f"Operador Conectado: **{st.session_state.usuario_nome}** | Empresa: Estel")
    
    if cab_direito.button("Encerrar Atividades", key="logout"):
        st.session_state.autenticado = False
        st.session_state.dados_conferencia = pd.DataFrame()
        st.rerun()
        
    st.markdown("---")
    
    with st.sidebar:
        st.header("📥 Carregar Documento")
        arquivo_entrada = st.file_uploader("Arraste o DANFE (PDF) ou Excel:", type=["pdf", "xlsx", "xls", "csv"])
        
        if arquivo_entrada:
            if st.button("Processar Carga de Itens", type="primary", key="btn_processar"):
                with st.spinner("Extraindo itens..."):
                    if arquivo_entrada.name.endswith(".pdf"):
                        st.session_state.dados_conferencia = extrair_linhas_danfe(arquivo_entrada)
                    else:
                        st.session_state.dados_conferencia = extrair_linhas_excel(arquivo_entrada)
                    st.rerun()
        
        if not st.session_state.dados_conferencia.empty:
            st.markdown("---")
            st.header("📤 Fechamento")
            memoria_excel = io.BytesIO()
            with pd.ExcelWriter(memoria_excel, engine='openpyxl') as writer:
                st.session_state.dados_conferencia.to_excel(writer, index=False, sheet_name="Conferencia")
            
            st.download_button(
                label="💾 Exportar Relatório (Excel)", 
                data=memoria_excel.getvalue(), 
                file_name=f"Relatorio_Estel_{time.strftime('%Y%m%d')}.xlsx", 
                mime="application/vnd.ms-excel"
            )
            if st.button("Limpar Carga"):
                st.session_state.dados_conferencia = pd.DataFrame()
                st.rerun()

    if st.session_state.dados_conferencia.empty:
        st.info("💡 **Para iniciar:** Suba um DANFE (PDF) ou planilha Excel no painel lateral.")
    else:
        aba_triagem, aba_tabela, aba_indicadores = st.tabs(["📸 Posto de Triagem & Fotos", "📋 Lista Geral", "📊 Painel de Controle"])
        
        with aba_triagem:
            lista_insumos = st.session_state.dados_conferencia["Descrição do Produto"].tolist()
            insumo_selecionado = st.selectbox("Selecione o insumo para conferência:", lista_insumos)
            
            if insumo_selecionado:
                idx = st.session_state.dados_conferencia[st.session_state.dados_conferencia["Descrição do Produto"] == insumo_selecionado].index[0]
                linha = st.session_state.dados_conferencia.loc[idx]
                
                st.markdown(f"""
                <div class='card-conferencia'>
                    <p style='color:#64748B; margin:0;'>Item Selecionado:</p>
                    <h3 style='color:#0284C7; margin:0;'>{linha['Descrição do Produto']}</h3>
                    <p style='margin:5px 0 0 0;'>Qtd Prevista: <b>{linha['Quantidade NF']}</b> | Status: <b>{linha['Situação']}</b></p>
                </div>
                """, unsafe_allow_html=True)
                
                col_cam, col_form = st.columns(2)
                with col_cam:
                    foto_mat = st.camera_input("Foto do Material:", key=f"mat_{idx}")
                    if foto_mat:
                        st.session_state.dados_conferencia.at[idx, "Foto Capturada"] = "Sim"
                
                with col_form:
                    qtd_conf = st.number_input("Quantidade real descarregada:", min_value=0.0, value=float(linha['Quantidade NF']), key=f"qtd_{idx}")
                    obs = st.text_area("Observações:", value=linha['Observações'], key=f"obs_{idx}")
                    
                    if st.button("Confirmar Item", type="primary", key=f"conf_{idx}"):
                        st.session_state.dados_conferencia.at[idx, "Quantidade Conferida"] = qtd_conf
                        st.session_state.dados_conferencia.at[idx, "Observações"] = obs
                        
                        situacao_final = "Conforme" if qtd_conf == linha['Quantidade NF'] else "Divergente"
                        st.session_state.dados_conferencia.at[idx, "Situação"] = situacao_final
                        
                        if supabase and SUPABASE_AVAILABLE:
                            try:
                                supabase.table("conferencia_itens").insert({
                                    "operador": st.session_state.usuario_nome,
                                    "descricao_produto": linha['Descrição do Produto'],
                                    "quantidade_nf": float(linha['Quantidade NF']),
                                    "quantidade_conferida": float(qtd_conf),
                                    "situacao": situacao_final,
                                    "observacoes": obs
                                }).execute()
                            except Exception: pass
                        st.rerun()

        with aba_tabela:
            st.dataframe(st.session_state.dados_conferencia, use_container_width=True)

        with aba_indicadores:
            df = st.session_state.dados_conferencia
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Itens", len(df))
            c2.metric("Conformes", len(df[df["Situação"] == "Conforme"]))
            c3.metric("Divergentes", len(df[df["Situação"] == "Divergente"]))
