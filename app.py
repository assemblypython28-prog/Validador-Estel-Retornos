import streamlit as st
import pandas as pd
import pdfplumber
import time
import io
import re
import json
import numpy as np
import face_recognition
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
    html, body, [class*="css"] { font-family: "Inter", sans-serif; background-color: #F8FAFC; }
    div[data-testid="stMetricValue"] { font-size: 26px; font-weight: 700; color: #1E293B; }
    .stButton>button { width: 100%; border-radius: 8px; height: 42px; background-color: #0284C7; color: white; font-weight: 600; border: none; }
    .stButton>button:hover { background-color: #0369A1; }
    .card-conferencia { background: white; border: 1px solid #E2E8F0; padding: 20px; border-radius: 12px; margin-bottom: 16px; }
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

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario_nome" not in st.session_state:
    st.session_state.usuario_nome = ""
if "dados_conferencia" not in st.session_state:
    st.session_state.dados_conferencia = pd.DataFrame()

# ============================================================
# ⚙️ FUNÇÕES AUXILIARES DE RECONHECIMENTO FACIAL
# ============================================================
def extrair_vetor_facial(imagem_st):
    """Converte a imagem capturada da câmera em vetor matemático (embedding)"""
    try:
        image = Image.open(imagem_st)
        image_np = np.array(image.convert('RGB'))
        encodings = face_recognition.face_encodings(image_np)
        if len(encodings) > 0:
            return encodings[0]
        return None
    except Exception:
        return None

# ============================================================
# ⚙️ ENGINES DE EXTRAÇÃO (PDF & EXCEL)
# ============================================================
def extrair_linhas_danfe(pdf_file):
    registros = []
    with pdfplumber.open(pdf_file) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if not texto: continue
            linhas = texto.split("\n")
            modo_captura = False
            for linha in linhas:
                if "CÓD PROD" in linha or "DESCRIÇÃO DOS PRODUTOS" in linha:
                    modo_captura = True
                    continue
                if "CÁLCULO DO ISSQN" in linha or "DADOS ADICIONAIS" in linha:
                    modo_captura = False
                if modo_captura:
                    numeros = re.findall(r'\b\d+[\d.,]*\b', linha)
                    desc = re.sub(r'^\S+\s+', '', linha)
                    desc = re.sub(r'\s+\d+[\d.,]*.*$', '', desc)
                    if len(desc.strip()) > 4:
                        qtd = 1.0
                        if len(numeros) >= 3:
                            try:
                                qtd_limpa = numeros[0].replace('.', '').replace(',', '.')
                                qtd = float(qtd_limpa)
                            except ValueError: pass
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
    try:
        df_cru = pd.read_csv(excel_file) if excel_file.name.endswith('.csv') else pd.read_excel(excel_file)
        df_formatado = pd.DataFrame()
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
        st.error(f"Erro na planilha: {e}")
        return pd.DataFrame()

# ============================================================
# 🔐 PAINEL DE LOGIN COM RECONHECIMENTO FACIAL BIOMÉTRICO
# ============================================================
if not st.session_state.autenticado:
    st.markdown("<div style='text-align: center; margin-top: 30px;'><h2>🔐 Sistema de Conferência de Materiais</h2><p style='color:#64748B;'>Validação de Acesso Logístico - Estel</p></div>", unsafe_allow_html=True)
    
    c_esq, c_centro, c_dir = st.columns([1, 1.4, 1])
    with c_centro:
        g_reconhecimento, g_credenciais, g_cadastro_face = st.tabs(["📸 Entrar Direto por Foto", "🔑 Chave de Acesso", "🧬 Registrar Rosto (1º Acesso)"])
        
        # ABA 1: ENTRADA DIRETA SÓ OLHANDO PARA A CÂMERA
        with g_reconhecimento:
            st.markdown("<p style='text-align:center;'>Apenas olhe para a câmera para liberar o painel operacional</p>", unsafe_allow_html=True)
            foto_scanner = st.camera_input("Scanner Facial de Entrada:", key="login_facial_direto")
            
            if foto_scanner and supabase:
                with st.spinner("Analisando face..."):
                    vetor_atual = extrair_vetor_facial(foto_scanner)
                    
                    if vetor_atual is not None:
                        # Busca todos os usuários que já têm biometria cadastrada
                        usuarios_banco = supabase.table("usuarios").not_.is_("face_embedding", "null").execute()
                        
                        sucesso_login = False
                        for user in usuarios_banco.data:
                            vetor_salvo = np.array(json.loads(user["face_embedding"]))
                            # Compara o rosto da foto com o do banco de dados
                            match = face_recognition.compare_faces([vetor_salvo], vetor_atual, tolerance=0.5)[0]
                            
                            if match:
                                st.session_state.autenticado = True
                                st.session_state.usuario_nome = user["nome"]
                                sucesso_login = True
                                st.success(f"Acesso Liberado! Bem-vindo, {user['nome']}")
                                time.sleep(0.5)
                                st.rerun()
                                break
                        
                        if not sucesso_login:
                            st.error("Rosto não reconhecido. Use Usuário/Senha ou faça o Cadastro Facial.")
                    else:
                        st.warning("Nenhum rosto detectado na imagem. Centralize-se em frente à câmera.")

        # ABA 2: LOGIN TRADICIONAL POR LOGIN E SENHA
        with g_credenciais:
            usuario_input = st.text_input("Usuário Logístico:")
            senha_input = st.text_input("Senha Corporativa:", type="password")
            if st.button("Autenticar Operação"):
                if supabase:
                    busca = supabase.table("usuarios").select("*").eq("usuario", usuario_input).eq("senha", senha_input).execute()
                    if busca.data:
                        st.session_state.autenticado = True
                        st.session_state.usuario_nome = busca.data[0]["nome"]
                        st.rerun()
                    else: st.error("Usuário ou senha incorretos.")
                else:
                    if usuario_input == "admin" and senha_input == "admin123":
                        st.session_state.autenticado = True
                        st.session_state.usuario_nome = "Supervisor Local (Offline)"
                        st.rerun()

        # ABA 3: CADASTRO INICIAL DO ROSTO
        with g_cadastro_face:
            st.markdown("<p style='text-align:center;'>Insira suas credenciais corporativas primeiro para vincular sua face</p>", unsafe_allow_html=True)
            u_cad = st.text_input("Confirmar Usuário:")
            s_cad = st.text_input("Confirmar Senha:", type="password")
            foto_cadastro = st.camera_input("Tirar Foto de Cadastro de Biometria:", key="cadastro_facial_imagem")
            
            if st.button("Gravar Biometria Facial no Banco"):
                if u_cad and s_cad and foto_cadastro and supabase:
                    # Valida se a senha bate antes de salvar o rosto
                    valida = supabase.table("usuarios").select("*").eq("usuario", u_cad).eq("senha", s_cad).execute()
                    if valida.data:
                        with st.spinner("Mapeando traços do rosto..."):
                            vetor = extrair_vetor_facial(foto_cadastro)
                            if vetor is not None:
                                lista_vetor = vetor.tolist() # Transforma em lista pura para aceitar texto JSON
                                supabase.table("usuarios").update({"face_embedding": json.dumps(lista_vetor)}).eq("usuario", u_cad).execute()
                                st.success("Sucesso! Seu rosto foi cadastrado. Agora você pode entrar direto por foto nas próximas vezes!")
                            else:
                                st.error("Não conseguimos processar os traços do seu rosto. Tente focar melhor a câmera.")
                    else:
                        st.error("Credenciais de validação incorretas.")
                else:
                    st.warning("Preencha o usuário, senha e capture a foto antes de salvar.")

# ============================================================
# 🚚 PAINEL PRINCIPAL DO SISTEMA (APÓS LOGIN CORRETO)
# ============================================================
else:
    cab_esquerdo, cab_direito = st.columns([4, 1])
    cab_esquerdo.title("🚚 Validador de Notas & Retornos de Obra")
    cab_esquerdo.caption(f"Operador Conectado: **{st.session_state.usuario_nome}**")
    
    if cab_direito.button("Encerrar Atividades"):
        st.session_state.autenticado = False
        st.session_state.dados_conferencia = pd.DataFrame()
        st.rerun()
        
    st.markdown("---")
    
    if supabase is None:
        st.sidebar.warning("⚠️ Banco em nuvem não sincronizado. Operando localmente.")

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
            memoria_excel = io.BytesIO()
            st.session_state.dados_conferencia.to_excel(memoria_excel, index=False, sheet_name="Conferencia_Final")
            st.download_button(label="💾 Exportar Relatório Final (Excel)", data=memoria_excel.getvalue(), file_name="Relatorio_Triagem_Estel.xlsx", mime="application/vnd.ms-excel")
            if st.button("Limpar Carga Corrente"):
                st.session_state.dados_conferencia = pd.DataFrame()
                st.rerun()

    if st.session_state.dados_conferencia.empty:
        st.info("💡 Para iniciar os trabalhos, por favor suba um arquivo digital de DANFE (PDF) ou a planilha Excel de insumos no painel lateral esquerdo.")
    else:
        aba_triagem, aba_tabela, aba_indicadores = st.tabs(["📸 Posto de Triagem & Fotos", "📋 Tabela de Divergências", "📊 Painel de Controle"])
        
        with aba_triagem:
            st.subheader("Inspeção Física de Volumes")
            lista_insumos = st.session_state.dados_conferencia["Descrição do Produto"].tolist()
            insumo_selecionado = st.selectbox("Selecione o insumo físico para auditoria:", lista_insumos)
            
            if insumo_selecionado:
                posicao_idx = st.session_state.dados_conferencia[st.session_state.dados_conferencia["Descrição do Produto"] == insumo_selecionado].index[0]
                linha_insumo = st.session_state.dados_conferencia.loc[posicao_idx]
                
                st.markdown(f"""
                <div class='card-conferencia'>
                    <h3 style='color:#0284C7; margin-top:0;'>{linha_insumo['Descrição do Produto']}</h3>
                    <p>Quantidade Prevista no Documento: <b style='font-size:16px;'>{linha_insumo['Quantidade NF']}</b> | Situação Atual: <b>{linha_insumo['Situação']}</b></p>
                </div>
                """, unsafe_allow_html=True)
                
                col_camera, col_formulario = st.columns(2)
                with col_camera:
                    st.markdown("##### 📷 Evidência Fotográfica do Material")
                    foto_click = st.camera_input("Capturar foto do Material:", key=f"camera_{posicao_idx}")
                    if foto_click:
                        st.image(foto_click, width=280, caption="Imagem vinculada.")
                        st.session_state.dados_conferencia.at[posicao_idx, "Foto Capturada"] = "Sim"
                        
                with col_formulario:
                    st.markdown("##### ⚙️ Contagem Quantitativa")
                    contagem_fisica = st.number_input("Quantidade real descarregada:", min_value=0.0, value=float(linha_insumo['Quantidade NF']), step=1.0)
                    campo_obs = st.text_area("Notas de inspeção:", value=linha_insumo['Observações'])
                    
                    if st.button("Confirmar Recebimento do Item"):
                        st.session_state.dados_conferencia.at[posicao_idx, "Quantidade Conferida"] = contagem_fisica
                        st.session_state.dados_conferencia.at[posicao_idx, "Observações"] = campo_obs
                        situacao_final = "Conforme" if contagem_fisica == linha_insumo['Quantidade NF'] else "Divergente"
                        st.session_state.dados_conferencia.at[posicao_idx, "Situação"] = situacao_final
                        
                        if supabase:
                            try:
                                supabase.table("conferencia_itens").insert({
                                    "operador": st.session_state.usuario_nome,
                                    "descricao_produto": linha_insumo['Descrição do Produto'],
                                    "quantidade_nf": float(linha_insumo['Quantidade NF']),
                                    "quantidade_conferida": float(contagem_fisica),
                                    "situacao": situacao_final,
                                    "foto_capturada": st.session_state.dados_conferencia.at[posicao_idx, "Foto Capturada"],
                                    "observacoes": campo_obs
                                }).execute()
                                st.success("Sincronizado com o Banco Supabase!")
                            except Exception as e:
                                st.warning(f"Erro de envio: {e}")
                        else:
                            st.success("Dados salvos em memória!")
                        time.sleep(0.4)
                        st.rerun()

        with aba_tabela:
            st.subheader("Lista Geral de Itens Importados")
            filtro_situacao = st.selectbox("Filtrar Registros por Situação:", ["Todos", "Pendente", "Conforme", "Divergente"])
            df_filtrado = st.session_state.dados_conferencia.copy()
            if filtro_situacao != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Situação"] == filtro_situacao]
            st.dataframe(df_filtrado, use_container_width=True, height=380)

        with aba_indicadores:
            st.subheader("Métricas de Produtividade")
            df_m = st.session_state.dados_conferencia
            b1, b2, b3, b4 = st.columns(4)
            b1.metric("Itens Totais", len(df_m))
            b2.metric("Conformes ✅", len(df_m[df_m["Situação"] == "Conforme"]))
            b3.metric("Divergentes ⚠️", len(df_m[df_m["Situação"] == "Divergente"]))
            b4.metric("Pendentes ⏳", len(df_m[df_m["Situação"] == "Pendente"]))
            st.markdown("---")
            st.markdown("##### Gráfico Analítico de Volume de Insumos")
            if not df_m.empty and "Situação" in df_m.columns:
                st.bar_chart(df_m["Situação"].value_counts())
