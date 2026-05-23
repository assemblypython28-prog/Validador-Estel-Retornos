import streamlit as st
import pandas as pd
import fitz  # PyMuPDF - Substituto leve e rápido do pdfplumber
import time
import io
import re
import json
import numpy as np
from PIL import Image
from supabase import create_client, Client

# Tenta importar face_recognition de forma segura para não quebrar o deploy
try:
    import face_recognition
    FACE_LIB_AVAILABLE = True
except ImportError:
    FACE_LIB_AVAILABLE = False
    st.warning("🔄 O ambiente de Reconhecimento Facial ainda está sendo configurado na nuvem. Use 'Login Corporativo' temporariamente.")

# ============================================================
# 🎨 CONFIGURAÇÃO VISUAL E ESTILO (DESIGN MODERNO)
# ============================================================
st.set_page_config(
    page_title="Validador de Retorno de Obra - Estel", 
    page_icon="🚚", 
    layout="wide"
)

# Estilo CSS Personalizado
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
@st.cache_resource
def iniciar_supabase():
    """Inicializa a conexão segura com o Supabase usando st.secrets"""
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"❌ Falha crítica de conexão com o banco de dados. Verifique 'secrets': {e}")
        return None

supabase = iniciar_supabase()

# Gerenciamento de Estado da Sessão
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario_nome" not in st.session_state:
    st.session_state.usuario_nome = ""
if "dados_conferencia" not in st.session_state:
    st.session_state.dados_conferencia = pd.DataFrame()

# ============================================================
# ⚙️ FUNÇÕES AUXILIARES DE VISÃO COMPUTACIONAL (FACE)
# ============================================================
def extrair_vetor_facial(imagem_st):
    """Converte a imagem capturada da câmera em vetor matemático (embedding) de forma segura"""
    if not FACE_LIB_AVAILABLE:
        st.error("Ambiente de biometria não disponível.")
        return None
        
    try:
        # Lê a imagem e converte para RGB
        image = Image.open(imagem_st)
        image_np = np.array(image.convert('RGB'))
        
        # Tenta detectar faces e extrair embeddings
        encodings = face_recognition.face_encodings(image_np)
        if len(encodings) > 0:
            return encodings[0]
        else:
            return None # Nenhuma face encontrada
            
    except Exception as e:
        st.error(f"Erro ao processar imagem facial: {e}")
        return None

# ============================================================
# ⚙️ ENGINES DE EXTRAÇÃO DE DADOS (PDF & EXCEL)
# ============================================================
def extrair_linhas_danfe(pdf_file):
    """Extrai itens de DANFE usando PyMuPDF (fitz) - ultra rápido e leve"""
    registros = []
    try:
        # Lê o PDF diretamente da memória
        pdf_bytes = pdf_file.read()
        # Abre o documento usando fitz (PyMuPDF)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        full_text = ""
        # Lê o texto de todas as páginas
        for pagina in doc:
            full_text += pagina.get_text()
            
        doc.close()

        if not full_text:
            st.warning("Não foi possível extrair texto do PDF. O arquivo pode ser uma imagem.")
            return pd.DataFrame()
            
        linhas = full_text.split("\n")
        modo_captura = False
        
        for linha in linhas:
            linha = linha.strip()
            if not linha:
                continue
                
            # Regex robusto para detectar o início da tabela de produtos (CÓD. | DESCRIÇÃO)
            if re.search(r'C.D(\.)?\s*PROD|DESCRI..O\s*DO(\s*S)?\s*PRODUTO', linha, re.IGNORECASE):
                modo_captura = True
                continue
                
            # Regex para detectar fim da tabela (CÁLCULO DO ISSQN | DADOS ADICIONAIS)
            if re.search(r'C.LCULO\s*DO\s*ISSQN|DADOS\s*ADICIONAIS|TRANSPORTADOR', linha, re.IGNORECASE):
                modo_captura = False
                break # Sai do loop para evitar falsos positivos
            
            if modo_captura:
                # Regex para extrair números (quantidade, valor unitário)
                # Pega números no formato 1.000,00 ou 10,50 ou 5
                numeros = re.findall(r'\b\d+[\d.,]*\b', linha)
                
                # Regex para limpar códigos e números e pegar a descrição (letras maiúsculas longas)
                desc = re.sub(r'^\d+\s+', '', linha) # Tira código inicial
                desc = re.sub(r'\s*\d+[\d.,]*.*$', '', desc) # Tira números finais
                
                # Validação: Se tiver descrição longa e pelo menos quantidade e valores
                if len(desc.strip()) > 5 and len(numeros) >= 3 and not desc.strip().isdigit():
                    qtd = 1.0
                    try:
                        # Limpa o primeiro número encontrado (quantidade) e converte para float
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
        
    except Exception as e:
        st.error(f"Erro crítico ao processar PDF com PyMuPDF: {e}")
    
    # Converte em DataFrame e remove duplicatas óbvias
    df = pd.DataFrame(registros)
    if not df.empty:
        df = df.drop_duplicates(subset=["Descrição do Produto"], keep="first")
    return df

def extrair_linhas_excel(excel_file):
    """Lê planilha Excel e formata para o padrão de conferência"""
    try:
        # Tenta ler CSV ou XLSX
        if excel_file.name.endswith('.csv'):
            df_cru = pd.read_csv(excel_file, encoding='latin1')
        else:
            df_cru = pd.read_excel(excel_file)
            
        if df_cru.empty:
            st.warning("A planilha carregada está vazia.")
            return pd.DataFrame()
            
        df_formatado = pd.DataFrame()
        
        # Tenta encontrar colunas por nome ou índice
        col_desc = next((c for c in df_cru.columns if "DESCRI" in c.upper()), df_cru.columns[1] if len(df_cru.columns) > 1 else df_cru.columns[0])
        col_qtd = next((c for c in df_cru.columns if "QTD" in c.upper() or "QUANT" in c.upper()), df_cru.columns[0])
        
        df_formatado["Descrição do Produto"] = df_cru[col_desc].astype(str).str.strip().str.upper()
        df_formatado["Quantidade NF"] = pd.to_numeric(df_cru[col_qtd], errors='coerce').fillna(1.0)
        df_formatado["Quantidade Conferida"] = 0.0
        df_formatado["Situação"] = "Pendente"
        df_formatado["Foto Capturada"] = "Não"
        df_formatado["Observações"] = ""
        
        # Filtra linhas sem descrição
        return df_formatado[df_formatado["Descrição do Produto"].str.len() > 2]
        
    except Exception as e:
        st.error(f"Erro na leitura da planilha Excel: {e}")
        return pd.DataFrame()

# ============================================================
# 🔐 PAINEL DE AUTENTICAÇÃO (LOGIN BIOMÉTRICO FACIAL)
# ============================================================
if not st.session_state.autenticado:
    # Cabeçalho Centralizado
    st.markdown("""
        <div style='text-align: center; margin-top: 50px; margin-bottom: 30px;'>
            <h1 style='color:#0284C7; font-size: 32px;'>🔐 Sistema de Conferência de Materiais</h1>
            <p style='color:#64748B; font-size: 16px;'>Validação de Acesso Logístico - Estel Engenharia</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Container centralizado para o login
    c_esq, c_centro, c_dir = st.columns([1, 1.4, 1])
    
    with c_centro:
        g_reconhecimento, g_credenciais, g_cadastro_face = st.tabs(["📸 Acesso Facial Direto", "🔑 Login Corporativo", "🧬 Cadastro Biométrico"])
        
        # ABA 1: ENTRADA SÓ OLHANDO PARA A CÂMERA (FACE ID)
        with g_reconhecimento:
            if not FACE_LIB_AVAILABLE:
                st.info("🔄 Configurando visão computacional... Use 'Login Corporativo' temporariamente.")
            else:
                st.markdown("<p style='text-align:center; color:#475569;'>Apenas centralize seu rosto na câmera para liberar o painel.</p>", unsafe_allow_html=True)
                foto_scanner = st.camera_input("Scanner Facial de Entrada:", key="login_facial_direto")
                
                if foto_scanner and supabase:
                    with st.spinner("Analisando biometria..."):
                        vetor_atual = extrair_vetor_facial(foto_scanner)
                        
                        if vetor_atual is not None:
                            # Busca usuários com biometria cadastrada (não nula)
                            usuarios_banco = supabase.table("usuarios").not_.is_("face_embedding", "null").execute()
                            
                            sucesso_login = False
                            for user in usuarios_banco.data:
                                # Converte texto JSON do banco em array numpy
                                vetor_salvo = np.array(json.loads(user["face_embedding"]))
                                
                                # Compara faces com tolerância restrita para segurança (0.45)
                                try:
                                    import face_recognition
                                    match = face_recognition.compare_faces([vetor_salvo], vetor_atual, tolerance=0.45)[0]
                                except Exception:
                                    match = False
                                
                                if match:
                                    st.session_state.autenticado = True
                                    st.session_state.usuario_nome = user["nome"]
                                    sucesso_login = True
                                    st.balloons()
                                    st.success(f"✅ Bem-vindo, {user['nome']}! Acesso liberado.")
                                    time.sleep(1)
                                    st.rerun()
                                    break
                            
                            if not sucesso_login:
                                st.error("❌ Rosto não reconhecido. Use Usuário/Senha ou faça o Cadastro Facial.")
                        else:
                            st.warning("⚠️ Centralize-se em frente à câmera. Nenhum rosto detectado.")

        # ABA 2: LOGIN TRADICIONAL (BACKUP CORPORATIVO)
        with g_credenciais:
            usuario_input = st.text_input("Usuário Logístico (Almoxarifado):")
            senha_input = st.text_input("Senha Corporativa:", type="password")
            
            if st.button("Autenticar Operação", type="primary"):
                if supabase:
                    with st.spinner("Validando credenciais..."):
                        busca = supabase.table("usuarios").select("*").eq("usuario", usuario_input).eq("senha", senha_input).execute()
                        if busca.data:
                            st.session_state.autenticado = True
                            st.session_state.usuario_nome = busca.data[0]["nome"]
                            st.rerun()
                        else: 
                            st.error("❌ Usuário ou senha incorretos.")
                else:
                    st.sidebar.error("Banco de dados offline.")

        # ABA 3: CADASTRO INICIAL DO ROSTO (BIOMETRIA)
        with g_cadastro_face:
            st.markdown("<p style='text-align:center; color:#475569;'>Insira suas credenciais corporativas primeiro para vincular sua biometria.</p>", unsafe_allow_html=True)
            u_cad = st.text_input("Confirmar Usuário Corporativo:")
            s_cad = st.text_input("Confirmar Senha Corporativa:", type="password")
            
            # Condiciona a câmera à verificação de bibliotecas
            if not FACE_LIB_AVAILABLE:
                st.warning("🔄 O ambiente de reconhecimento facial ainda está sendo configurado pelo servidor. Aguarde alguns minutos ou use 'Login Corporativo'.")
            else:
                foto_cadastro = st.camera_input("Tirar Foto de Cadastro de Biometria:", key="cadastro_facial_imagem")
                
                if st.button("Gravar Biometria Facial no Banco"):
                    if u_cad and s_cad and foto_cadastro and supabase:
                        # Valida credenciais antes de salvar o rosto
                        with st.spinner("Validando credenciais corporativas..."):
                            valida = supabase.table("usuarios").select("*").eq("usuario", u_cad).eq("senha", s_cad).execute()
                            
                            if valida.data:
                                with st.spinner("Mapeando traços biométricos do rosto..."):
                                    vetor = extrair_vetor_facial(foto_cadastro)
                                    if vetor is not None:
                                        # Converte vetor numpy em lista para salvar como JSON no texto SQL
                                        lista_vetor = vetor.tolist() 
                                        supabase.table("usuarios").update({"face_embedding": json.dumps(lista_vetor)}).eq("usuario", u_cad).execute()
                                        st.success(f"✅ Sucesso! Biometria cadastrada para {valida.data[0]['nome']}. Agora você pode entrar direto por foto!")
                                        time.sleep(1.5)
                                        st.rerun()
                                    else:
                                        st.error("❌ Não conseguimos processar o rosto. Centralize e foque melhor a câmera.")
                            else:
                                st.error("❌ Credenciais corporativas de validação incorretas.")
                    else:
                        st.warning("⚠️ Preencha usuário, senha e capture a foto antes de salvar.")

# ============================================================
# 🚚 PAINEL PRINCIPAL DO SISTEMA (APÓS LOGIN CORRETO)
# ============================================================
else:
    # Cabeçalho Operacional
    cab_esquerdo, cab_direito = st.columns([4, 1])
    cab_esquerdo.markdown(f"<h1>🚚 Validador de Retornos de Obra</h1>", unsafe_allow_html=True)
    cab_esquerdo.caption(f"Operador Conectado: **{st.session_state.usuario_nome}** | Localização: Estel (Serra-ES)")
    
    if cab_direito.button("Encerrar Atividades", key="logout"):
        st.session_state.autenticado = False
        st.session_state.dados_conferencia = pd.DataFrame()
        st.rerun()
        
    st.markdown("---")
    
    if supabase is None:
        st.sidebar.warning("⚠️ Banco em nuvem não sincronizado. Operando localmente (dados não serão salvos).")

    # BARRA LATERAL - ENTRADA E SAÍDA DE DADOS
    with st.sidebar:
        st.header("📥 Carregar Documento")
        arquivo_entrada = st.file_uploader("Arraste o DANFE (PDF) ou o arquivo Excel de retornos:", type=["pdf", "xlsx", "xls", "csv"])
        
        if arquivo_entrada:
            if st.button("Processar Carga de Itens", type="primary", key="btn_processar"):
                with st.spinner("Extraindo itens da carga logística..."):
                    time.sleep(0.5)
                    if arquivo_entrada.name.endswith(".pdf"):
                        # USA PYMUPDF (FITZ)
                        st.session_state.dados_conferencia = extrair_linhas_danfe(arquivo_entrada)
                    else:
                        # USA PANDAS (EXCEL)
                        st.session_state.dados_conferencia = extrair_linhas_excel(arquivo_entrada)
                        
                    if not st.session_state.dados_conferencia.empty:
                        st.success(f"✅ Carregamento concluído! {len(st.session_state.dados_conferencia)} itens mapeados.")
                    else:
                        st.warning("Não conseguimos extrair itens válidos. Verifique o arquivo.")
        
        st.markdown("---")
        st.header("📤 Fechamento de Auditoria")
        if not st.session_state.dados_conferencia.empty:
            memoria_excel = io.BytesIO()
            with pd.ExcelWriter(memoria_excel, engine='openpyxl') as writer:
                st.session_state.dados_conferencia.to_excel(writer, index=False, sheet_name="Conferencia_Final")
            
            st.download_button(
                label="💾 Exportar Relatório Final (Excel)", 
                data=memoria_excel.getvalue(), 
                file_name=f"Relatorio_Triagem_Estel_{time.strftime('%Y%m%d_%H%M%S')}.xlsx", 
                mime="application/vnd.ms-excel",
                key="btn_download"
            )
            
            if st.button("Limpar Carga Corrente", key="btn_limpar"):
                st.session_state.dados_conferencia = pd.DataFrame()
                st.rerun()

    # ÁREA CENTRAL - FLUXO DE TRABALHO
    if st.session_state.dados_conferencia.empty:
        st.info("💡 **Para iniciar os trabalhos:** Suba um arquivo digital de DANFE (PDF) ou a planilha Excel de insumos no painel lateral esquerdo.")
    else:
        # Abas Operacionais
        aba_triagem, aba_tabela, aba_indicadores = st.tabs(["📸 Posto de Triagem & Fotos", "📋 Lista Geral & Divergências", "📊 Painel de Controle"])
        
        # ABA 1: POSTO DE TRIAGEM (INSPEÇÃO FÍSICA E FOTO)
        with aba_triagem:
            st.subheader("Inspeção Física de Volumes de Obra")
            
            # Dropdown de seleção de insumo
            lista_insumos = st.session_state.dados_conferencia["Descrição do Produto"].tolist()
            insumo_selecionado = st.selectbox("Selecione o insumo físico para auditoria em tempo real:", lista_insumos)
            
            if insumo_selecionado:
                # Localiza a linha do insumo
                posicao_idx = st.session_state.dados_conferencia[st.session_state.dados_conferencia["Descrição do Produto"] == insumo_selecionado].index[0]
                linha_insumo = st.session_state.dados_conferencia.loc[posicao_idx]
                
                # Card de informações do material
                st.markdown(f"""
                <div class='card-conferencia'>
                    <p style='color:#64748B; margin:0;'>Item Selecionado:</p>
                    <h3 style='color:#0284C7; margin-top:5px; margin-bottom:10px;'>{linha_insumo['Descrição do Produto']}</h3>
                    <p style='margin:0; font-size: 15px;'>Quantidade Prevista no Documento: <b style='font-size:18px; color:#1E293B;'>{linha_insumo['Quantidade NF']}</b> | Situação Atual: <b>{linha_insumo['Situação']}</b></p>
                </div>
                """, unsafe_allow_html=True)
                
                # Layout de conferência (Câmera vs Formulário)
                col_camera, col_formulario = st.columns(2)
                
                with col_camera:
                    st.markdown("##### 📷 Evidência Fotográfica do Material")
                    foto_click = st.camera_input("Capturar foto real do Material:", key=f"camera_mat_{posicao_idx}")
                    if foto_click:
                        st.image(foto_click, width=280, caption=f"Imagem vinculada ao item {linha_insumo['Descrição do Produto']}.")
                        st.session_state.dados_conferencia.at[posicao_idx, "Foto Capturada"] = "Sim"
                        
                with col_formulario:
                    st.markdown("##### ⚙️ Contagem e Auditoria Quantitativa")
                    contagem_fisica = st.number_input(
                        "Quantidade real descarregada/conferida:", 
                        min_value=0.0, 
                        value=float(linha_insumo['Quantidade NF']), # Padrão é a quantidade da NF
                        step=1.0,
                        key=f"input_qtd_{posicao_idx}"
                    )
                    
                    campo_obs = st.text_area("Notas de inspeção (Observações):", value=linha_insumo['Observações'], key=f"input_obs_{posicao_idx}", height=100)
                    
                    if st.button("Confirmar Recebimento e Auditar Item", type="primary", key=f"btn_conf_{posicao_idx}"):
                        # Atualiza dados na memória st.session_state
                        st.session_state.dados_conferencia.at[posicao_idx, "Quantidade Conferida"] = contagem_fisica
                        st.session_state.dados_conferencia.at[posicao_idx, "Observações"] = campo_obs
                        
                        # Define Situação
                        situacao_final = "Conforme" if contagem_fisica == linha_insumo['Quantidade NF'] else "Divergente"
                        st.session_state.dados_conferencia.at[posicao_idx, "Situação"] = situacao_final
                        
                        # Tenta sincronizar com o banco Supabase
                        if supabase:
                            with st.spinner("Sincronizando com auditoria central..."):
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
                                    st.success("✅ Auditoria sincronizada com o banco central!")
                                except Exception as e:
                                    st.warning(f"⚠️ Erro ao salvar online, dados mantidos localmente: {e}")
                        else:
                            st.success("✅ Dados salvos em memória local!")
                            
                        # Pequeno delay e recarrega para atualizar a tabela
                        time.sleep(0.5)
                        st.rerun()

        # ABA 2: TABELA GERAL (VISÃO DE DIVERGÊNCIAS)
        with aba_tabela:
            st.subheader("Lista Geral de Itens Importados")
            
            filtro_situacao = st.selectbox("Filtrar Registros por Situação:", ["Todos", "Pendente", "Conforme", "Divergente"])
            
            df_filtrado = st.session_state.dados_conferencia.copy()
            if filtro_situacao != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Situação"] == filtro_situacao]
                
            st.dataframe(
                df_filtrado, 
                use_container_width=True, 
                height=400,
                column_config={
                    "Quantidade NF": st.column_config.NumberColumn(format="%.0f"),
                    "Quantidade Conferida": st.column_config.NumberColumn(format="%.0f")
                }
            )

        # ABA 3: INDICADORES (PAINEL DE CONTROLE LOGÍSTICO)
        with aba_indicadores:
            st.subheader("Métricas de Produtividade em Campo")
            
            df_m = st.session_state.dados_conferencia
            totais = len(df_m)
            conformes = len(df_m[df_m["Situação"] == "Conforme"])
            divergentes = len(df_m[df_m["Situação"] == "Divergente"])
            pendentes = len(df_m[df_m["Situação"] == "Pendente"])
            
            # Métricas em colunas
            b1, b2, b3, b4 = st.columns(4)
            b1.metric("📦 Itens Totais Carregados", totais)
            b2.metric("✅ Conformes", conformes)
            b3.metric("⚠️ Divergentes", divergentes, f"{totais-conformes-pendentes} un")
            b4.metric("⏳ Pendentes", pendentes, f"{conformes+divergentes} conf")
            
            st.markdown("---")
            
            if not df_m.empty and "Situação" in df_m.columns:
                st.markdown("##### Gráfico Analítico de Volume de Insumos")
                
                # Prepara dados para o gráfico
                contagem_situacoes = df_m["Situação"].value_counts().reset_index()
                contagem_situacoes.columns = ["Situação", "Quantidade"]
                
                # Gráfico de barras usando Altair (nativo do Streamlit e leve)
                import altair as alt
                
                chart = alt.Chart(contagem_situacoes).mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5).encode(
                    x=alt.X("Situação:N", title="Situação", sort=["Pendente", "Conforme", "Divergente"]),
                    y=alt.Y("Quantidade:Q", title="Quantidade de Itens"),
                    color=alt.Color("Situação:N", scale=alt.Scale(
                        domain=["Pendente", "Conforme", "Divergente"],
                        range=["#F59E0B", "#10B981", "#EF4444"] # Amarelo, Verde, Vermelho
                    ), legend=None),
                    tooltip=["Situação", "Quantidade"]
                ).properties(height=350).interactive()
                
                st.altair_chart(chart, use_container_width=True)
