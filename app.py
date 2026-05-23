import os

# ============================================================
# CONFIGURACAO DO OPENCV E KERAS (ANTES DE TUDO)
# ============================================================
os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Silencia warnings do TensorFlow

import streamlit as st
import pandas as pd
import time
import io
import re
import json
import numpy as np
from PIL import Image

# ============================================================
# CONFIGURACAO VISUAL E ESTILO
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
# IMPORTS COM FALLBACK - RECONHECIMENTO FACIAL
# ============================================================
CV2_AVAILABLE = False
DEEPFACE_AVAILABLE = False
SUPABASE_AVAILABLE = False
FITZ_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except Exception as e:
    st.sidebar.error(f"❌ OpenCV indisponível: {e}")

try:
    from deepface import DeepFace
    DEEPFACE_AVAILABLE = True
except Exception as e:
    st.sidebar.warning(f"⚠️ DeepFace indisponível: {e}")

try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except Exception as e:
    st.sidebar.warning(f"⚠️ Supabase indisponível: {e}")

try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    pass

# ============================================================
# CONEXAO COM BANCO DE DADOS
# ============================================================
supabase = None
if SUPABASE_AVAILABLE:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        supabase = create_client(url, key)
    except Exception as e:
        st.sidebar.warning(f"⚠️ Supabase não conectado: {str(e)[:50]}")

# Inicializacao do Session State
if "autenticado" not in st.session_state: 
    st.session_state.autenticado = False
if "usuario_nome" not in st.session_state: 
    st.session_state.usuario_nome = ""
if "dados_conferencia" not in st.session_state: 
    st.session_state.dados_conferencia = pd.DataFrame()
if "temp_face_vector" not in st.session_state: 
    st.session_state.temp_face_vector = None
if "fotos_postadas" not in st.session_state: 
    st.session_state.fotos_postadas = {}

# ============================================================
# ENGENHARIA DE IA FACIAL
# ============================================================
def processar_biometria(imagem_st):
    """Extrai embedding facial da imagem."""
    if not DEEPFACE_AVAILABLE or not CV2_AVAILABLE:
        st.error("❌ Reconhecimento facial indisponível. Verifique a instalação do OpenCV e DeepFace.")
        return None

    temp_path = "temp_face_input.jpg"
    try:
        img = Image.open(imagem_st)
        img.convert("RGB").save(temp_path)

        backends = ["mtcnn", "retinaface", "opencv"]
        embeddings_data = None
        ultimo_erro = ""

        for backend in backends:
            try:
                embeddings_data = DeepFace.represent(
                    img_path=temp_path,
                    model_name="Facenet",
                    enforce_detection=True,
                    detector_backend=backend,
                    align=True
                )
                if embeddings_data and len(embeddings_data) > 0:
                    break
            except Exception as e:
                ultimo_erro = str(e)
                continue

        if not embeddings_data:
            try:
                embeddings_data = DeepFace.represent(
                    img_path=temp_path,
                    model_name="Facenet",
                    enforce_detection=False,
                    detector_backend="opencv",
                    align=True
                )
                st.info("⚠️ Rosto detectado com baixa confiança.")
            except Exception as e:
                ultimo_erro = str(e)

        if os.path.exists(temp_path):
            os.remove(temp_path)

        if embeddings_data and len(embeddings_data) > 0:
            return embeddings_data[0]["embedding"]

        st.error(f"Detalhes: {ultimo_erro[:100]}")
        return None

    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        st.error(f"Erro: {str(e)[:100]}")
        return None

def calcular_similaridade(vetor1, vetor2):
    v1, v2 = np.array(vetor1), np.array(vetor2)
    return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))

# ============================================================
# EXTRACAO DE DADOS (PDF & EXCEL)
# ============================================================
def extrair_linhas_danfe(pdf_file):
    registros = []
    full_text = ""
    try:
        pdf_bytes = pdf_file.read()
        if FITZ_AVAILABLE:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for pagina in doc:
                full_text += pagina.get_text()
            doc.close()
        else:
            from pdfminer.high_level import extract_text
            full_text = extract_text(io.BytesIO(pdf_bytes))
        if not full_text:
            return []
        linhas = full_text.split("\n")
        modo_captura = False
        for linha in linhas:
            linha = linha.strip()
            if not linha:
                continue
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
                    try:
                        qtd = float(numeros[0].replace('.', '').replace(',', '.'))
                    except ValueError:
                        pass
                    registros.append({
                        "Arquivo Origem": pdf_file.name,
                        "Descrição do Produto": desc.strip().upper(),
                        "Quantidade NF": qtd,
                        "Quantidade Conferida": 0.0,
                        "Situação": "Pendente",
                        "Foto Capturada": "Não",
                        "Observações": ""
                    })
    except Exception:
        pass
    return registros

def extrair_linhas_excel(excel_file):
    try:
        if excel_file.name.endswith('.csv'):
            df_cru = pd.read_csv(excel_file, encoding='latin1')
        else:
            df_cru = pd.read_excel(excel_file)
        if df_cru.empty:
            return []
        col_desc = next((c for c in df_cru.columns if "DESCRI" in c.upper()),
                       df_cru.columns[1] if len(df_cru.columns) > 1 else df_cru.columns[0])
        col_qtd = next((c for c in df_cru.columns if "QTD" in c.upper() or "QUANT" in c.upper()),
                      df_cru.columns[0])
        registros = []
        for _, row in df_cru.iterrows():
            desc_val = str(row[col_desc]).strip().upper()
            if len(desc_val) > 2 and not desc_val.isdigit():
                try:
                    qtd_val = float(pd.to_numeric(row[col_qtd], errors='coerce'))
                except:
                    qtd_val = 1.0
                if np.isnan(qtd_val):
                    qtd_val = 1.0
                registros.append({
                    "Arquivo Origem": excel_file.name,
                    "Descrição do Produto": desc_val,
                    "Quantidade NF": qtd_val,
                    "Quantidade Conferida": 0.0,
                    "Situação": "Pendente",
                    "Foto Capturada": "Não",
                    "Observações": ""
                })
        return registros
    except Exception:
        return []

# ============================================================
# PAINEL DE AUTENTICACAO COM BIOMETRIA
# ============================================================
if not st.session_state.autenticado:
    st.markdown("""
        <div style='text-align: center; margin-top: 50px; margin-bottom: 30px;'>
            <h1 style='color:#0284C7; font-size: 32px;'>📸 Identificação Biométrica Estel</h1>
            <p style='color:#64748B; font-size: 16px;'>Tire uma foto para logar instantaneamente ou criar seu perfil.</p>
        </div>
    """, unsafe_allow_html=True)

    c_esq, c_centro, c_dir = st.columns([1, 1.4, 1])

    with c_centro:
        # Alerta se biometria indisponível
        if not DEEPFACE_AVAILABLE or not CV2_AVAILABLE:
            st.error("""
            ⚠️ **Reconhecimento Facial Temporariamente Indisponível**

            O sistema de biometria não pôde ser carregado. Use o login manual abaixo.
            """)
            st.info("Login de contingência: **admin** / **admin**")
            u_t = st.text_input("Usuário:")
            s_t = st.text_input("Senha:", type="password")
            if st.button("Entrar", type="primary"):
                if u_t == "admin" and s_t == "admin":
                    st.session_state.autenticado = True
                    st.session_state.usuario_nome = "Supervisor Local"
                    st.experimental_rerun()
                else:
                    st.error("Credenciais inválidas.")
        else:
            foto_captura = st.camera_input("Scanner Facial Ativo:", key="scan_facial_posto_unico")

            if foto_captura:
                with st.spinner("Buscando sua biometria na base corporativa..."):
                    vetor_atual = processar_biometria(foto_captura)

                    if vetor_atual is not None:
                        if supabase and SUPABASE_AVAILABLE:
                            try:
                                todos_usuarios = supabase.table("usuarios")\
                                    .select("*")\
                                    .not_("face_embedding", "is", "null")\
                                    .execute()
                            except Exception:
                                todos_usuarios = supabase.table("usuarios").select("*").execute()

                            reconhecido = False
                            operador_nome = ""

                            for usuario in todos_usuarios.data:
                                if not usuario.get("face_embedding"):
                                    continue
                                try:
                                    vetor_salvo = json.loads(usuario["face_embedding"])
                                    score = calcular_similaridade(vetor_atual, vetor_salvo)
                                    if score > 0.85:
                                        reconhecido = True
                                        operador_nome = usuario["nome"]
                                        break
                                except Exception:
                                    pass

                            if reconhecido:
                                st.success(f"✅ Reconhecido! Seja bem-vindo, {operador_nome}.")
                                st.session_state.autenticado = True
                                st.session_state.usuario_nome = operador_nome
                                time.sleep(1)
                                st.experimental_rerun()
                            else:
                                st.warning("👤 Rosto não localizado na base. Preencha os dados abaixo para vincular sua biometria:")
                                st.session_state.temp_face_vector = vetor_atual

                                with st.expander("📝 Criar Novo Cadastro com esta Biometria", expanded=True):
                                    nome_cad = st.text_input("Nome Completo:")
                                    user_cad = st.text_input("ID Usuário Logístico (Login):")
                                    senha_cad = st.text_input("Defina uma Senha:", type="password")

                                    if st.button("Salvar Registro e Entrar", type="primary"):
                                        if nome_cad and user_cad and senha_cad:
                                            try:
                                                vetor_json = json.dumps(st.session_state.temp_face_vector)
                                                supabase.table("usuarios").insert({
                                                    "nome": nome_cad,
                                                    "usuario": user_cad,
                                                    "senha": senha_cad,
                                                    "face_embedding": vetor_json
                                                }).execute()
                                                st.success("🎉 Cadastro Concluído com Biometria!")
                                                st.session_state.autenticado = True
                                                st.session_state.usuario_nome = nome_cad
                                                st.session_state.temp_face_vector = None
                                                time.sleep(1)
                                                st.experimental_rerun()
                                            except Exception as e:
                                                st.error(f"Erro ao salvar: {e}")
                                        else:
                                            st.error("Por favor, preencha todos os campos.")
                        else:
                            st.info("Supabase Indisponível. Use admin/admin para contingência.")
                            u_t = st.text_input("User:")
                            s_t = st.text_input("Pass:", type="password")
                            if st.button("Entrar"):
                                if u_t == "admin" and s_t == "admin":
                                    st.session_state.autenticado = True
                                    st.session_state.usuario_nome = "Supervisor Local"
                                    st.experimental_rerun()
                    else:
                        st.error("⚠️ Não foi possível detectar o rosto claramente. Ajuste a iluminação e centralize-se.")

# ============================================================
# PAINEL PRINCIPAL
# ============================================================
else:
    cab_esquerdo, cab_direito = st.columns([4, 1])
    cab_esquerdo.markdown(f"<h1>🚚 Validador de Retornos de Obra</h1>", unsafe_allow_html=True)
    cab_esquerdo.caption(f"Operador: **{st.session_state.usuario_nome}**")

    if cab_direito.button("Encerrar Atividades", key="logout"):
        st.session_state.autenticado = False
        st.session_state.dados_conferencia = pd.DataFrame()
        st.session_state.fotos_postadas = {}
        st.experimental_rerun()

    st.markdown("---")

    with st.sidebar:
        st.header("📥 Carregar Documentos")
        arquivos_entrada = st.file_uploader(
            "Arraste DANFEs (PDF) ou planilhas:",
            type=["pdf", "xlsx", "xls", "csv"],
            accept_multiple_files=True
        )

        if arquivos_entrada:
            if st.button("Processar Carga em Lote", type="primary"):
                all_records = []
                with st.spinner("Lendo documentos..."):
                    for arq in arquivos_entrada:
                        if arq.name.endswith(".pdf"):
                            all_records.extend(extrair_linhas_danfe(arq))
                        else:
                            all_records.extend(extrair_linhas_excel(arq))

                    if all_records:
                        df_novo = pd.DataFrame(all_records).drop_duplicates(
                            subset=["Arquivo Origem", "Descrição do Produto"]
                        )
                        st.session_state.dados_conferencia = df_novo
                        st.success(f"📊 {len(df_novo)} itens mapeados!")
                        st.experimental_rerun()

        if not st.session_state.dados_conferencia.empty:
            st.markdown("---")
            st.header("📤 Fechamento")
            memoria_excel = io.BytesIO()
            with pd.ExcelWriter(memoria_excel, engine='openpyxl') as writer:
                st.session_state.dados_conferencia.to_excel(writer, index=False, sheet_name="Consolidado")

            st.download_button(
                label="💾 Exportar Relatório",
                data=memoria_excel.getvalue(),
                file_name=f"Relatorio_Estel_{time.strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.ms-excel"
            )

            if st.button("Limpar Tudo"):
                st.session_state.dados_conferencia = pd.DataFrame()
                st.session_state.fotos_postadas = {}
                st.experimental_rerun()

    if st.session_state.dados_conferencia.empty:
        st.info("💡 Carregue notas fiscais no menu à esquerda para iniciar.")
    else:
        aba_triagem, aba_tabela, aba_indicadores = st.tabs([
            "📸 Posto de Triagem",
            "📋 Lista Consolidada",
            "📊 Painel de Controle"
        ])

        with aba_triagem:
            df_ref = st.session_state.dados_conferencia
            opcoes_seletor = [
                f"[{row['Arquivo Origem']}] - {row['Descrição do Produto']}"
                for _, row in df_ref.iterrows()
            ]
            item_composto_selecionado = st.selectbox(
                "Selecione o insumo:", opcoes_seletor
            )

            if item_composto_selecionado:
                arq_nome = item_composto_selecionado.split("] - ")[0].replace("[", "")
                prod_nome = item_composto_selecionado.split("] - ")[1]

                mask = (df_ref["Arquivo Origem"] == arq_nome) & (df_ref["Descrição do Produto"] == prod_nome)
                if not mask.any():
                    st.error("Item não encontrado.")
                    st.stop()

                idx = df_ref[mask].index[0]
                linha = df_ref.loc[idx]

                st.markdown(f"""
                <div class='card-conferencia'>
                    <p style='color:#64748B; margin:0;'>Origem: <b>{linha['Arquivo Origem']}</b></p>
                    <h3 style='color:#0284C7; margin:0;'>{linha['Descrição do Produto']}</h3>
                    <p>Qtd NF: <b>{linha['Quantidade NF']}</b> | Situação: <b>{linha['Situação']}</b></p>
                </div>
                """, unsafe_allow_html=True)

                col_cam, col_form = st.columns(2)
                with col_cam:
                    foto_mat = st.camera_input("Foto do Material:", key=f"cam_{idx}")
                    if foto_mat:
                        st.session_state.fotos_postadas[idx] = foto_mat.getvalue()
                        st.session_state.dados_conferencia.at[idx, "Foto Capturada"] = "Sim"
                        st.toast("📸 Foto armazenada!")

                    if idx in st.session_state.fotos_postadas:
                        st.image(st.session_state.fotos_postadas[idx], caption="Foto auditoria", width=300)

                with col_form:
                    qtd_conf = st.number_input(
                        "Quantidade real:", min_value=0.0,
                        value=float(linha['Quantidade NF']), key=f"qtd_{idx}"
                    )
                    obs = st.text_area("Observações:", value=linha['Observações'], key=f"obs_{idx}")

                    if st.button("Confirmar", type="primary", key=f"conf_{idx}"):
                        st.session_state.dados_conferencia.at[idx, "Quantidade Conferida"] = qtd_conf
                        st.session_state.dados_conferencia.at[idx, "Observações"] = obs
                        situacao_final = "Conforme" if qtd_conf == linha['Quantidade NF'] else "Divergente"
                        st.session_state.dados_conferencia.at[idx, "Situação"] = situacao_final

                        if supabase and SUPABASE_AVAILABLE:
                            try:
                                supabase.table("conferencia_itens").insert({
                                    "operador": st.session_state.usuario_nome,
                                    "nome_arquivo": linha['Arquivo Origem'],
                                    "descricao_produto": linha['Descrição do Produto'],
                                    "quantidade_nf": float(linha['Quantidade NF']),
                                    "quantidade_conferida": float(qtd_conf),
                                    "situacao": situacao_final,
                                    "observacoes": obs
                                }).execute()
                                st.toast("💾 Sincronizado!")
                            except Exception as e:
                                st.error(f"Erro sync: {e}")
                        st.experimental_rerun()

        with aba_tabela:
            st.dataframe(st.session_state.dados_conferencia, use_container_width=True)

        with aba_indicadores:
            df = st.session_state.dados_conferencia
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Insumos", len(df))
            c2.metric("Conforme", len(df[df["Situação"] == "Conforme"]))
            c3.metric("Divergente", len(df[df["Situação"] == "Divergente"]))
