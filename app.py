import os

# ============================================================
# CONFIGURACAO DO OPENCV E KERAS (ANTES DE TUDO)
# ============================================================
os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '0'
os.environ['TF_USE_LEGACY_KERAS'] = '1'

import cv2
import streamlit as st
import pandas as pd
import time
import io
import re
import json
import numpy as np
from PIL import Image
from supabase import create_client, Client

# ============================================================
# COMPATIBILIDADE: safe_rerun()
# ============================================================
def safe_rerun():
    if hasattr(st, 'rerun'):
        st.rerun()
    elif hasattr(st, 'experimental_rerun'):
        st.experimental_rerun()
    else:
        st.markdown('<meta http-equiv="refresh" content="0">', unsafe_allow_html=True)

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

/* BUSCA INTELIGENTE */
.busca-container { background: linear-gradient(135deg, #E0F2FE 0%, #F0F9FF 100%); padding: 16px; border-radius: 12px; border-left: 4px solid #0284C7; margin-bottom: 16px; }
.busca-resultado { background: #F0FDF4; padding: 12px; border-radius: 8px; border-left: 4px solid #22C55E; margin: 8px 0; }
.busca-alerta { background: #FEF3C7; padding: 12px; border-radius: 8px; border-left: 4px solid #F59E0B; margin: 8px 0; }
.busca-vazio { background: #FEF2F2; padding: 12px; border-radius: 8px; border-left: 4px solid #EF4444; margin: 8px 0; }

/* DASHBOARD */
.dashboard-card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); border: 1px solid #E2E8F0; }
.dashboard-metric { font-size: 32px; font-weight: 700; color: #0284C7; }
.dashboard-label { font-size: 13px; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; }
.progress-bar { width: 100%; height: 8px; background: #E2E8F0; border-radius: 4px; overflow: hidden; }
.progress-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease; }
.status-badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }
.status-pendente { background: #FEF3C7; color: #92400E; }
.status-conforme { background: #DCFCE7; color: #166534; }
.status-divergente { background: #FEE2E2; color: #991B1B; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# CONEXAO COM BANCO DE DADOS (SUPABASE) - COM TRATAMENTO ROBUSTO
# ============================================================
SUPABASE_AVAILABLE = False
supabase = None
supabase_error_msg = ""

def init_supabase():
    global SUPABASE_AVAILABLE, supabase, supabase_error_msg
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        if not url or not key:
            supabase_error_msg = "SUPABASE_URL ou SUPABASE_KEY vazios nos secrets"
            return
        supabase = create_client(url, key)
        try:
            test = supabase.table("usuarios").select("id", count="exact").limit(1).execute()
            SUPABASE_AVAILABLE = True
        except Exception as e:
            if "does not exist" in str(e).lower() or "relation" in str(e).lower():
                SUPABASE_AVAILABLE = True
                supabase_error_msg = "Tabela 'usuarios' não encontrada. Crie a tabela no Supabase."
            else:
                supabase_error_msg = f"Erro de conexão: {str(e)[:80]}"
    except Exception as e:
        supabase_error_msg = f"Falha ao inicializar: {str(e)[:80]}"
        SUPABASE_AVAILABLE = False

init_supabase()

# Inicializacao robusta do Session State
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario_nome" not in st.session_state:
    st.session_state.usuario_nome = ""
if "usuario_id" not in st.session_state:
    st.session_state.usuario_id = None
if "dados_conferencia" not in st.session_state:
    st.session_state.dados_conferencia = pd.DataFrame()
if "temp_face_vector" not in st.session_state:
    st.session_state.temp_face_vector = None
if "fotos_postadas" not in st.session_state:
    st.session_state.fotos_postadas = {}
if "aba_ativa" not in st.session_state:
    st.session_state.aba_ativa = "triagem"
if "busca_termo" not in st.session_state:
    st.session_state.busca_termo = ""
if "item_selecionado_idx" not in st.session_state:
    st.session_state.item_selecionado_idx = None

# ============================================================
# ENGENHARIA DE IA FACIAL (DEEPFACE)
# ============================================================
_deepface = None

def get_deepface():
    global _deepface
    if _deepface is None:
        from deepface import DeepFace
        _deepface = DeepFace
    return _deepface

def processar_biometria(imagem_st):
    temp_files = [f"temp_face_{i}.jpg" for i in range(7)]
    try:
        img = Image.open(imagem_st)
        img_rgb = img.convert("RGB")
        img_rgb.save(temp_files[0])

        from PIL import ImageEnhance
        variations = [
            (ImageEnhance.Contrast, 1.5), (ImageEnhance.Brightness, 1.3),
            (ImageEnhance.Sharpness, 1.5), None,  # combined
            (ImageEnhance.Contrast, 0.8), (ImageEnhance.Brightness, 0.9)
        ]

        # Combined variation
        try:
            e = ImageEnhance.Contrast(img_rgb)
            img_tudo = e.enhance(1.3)
            e = ImageEnhance.Brightness(img_tudo)
            img_tudo = e.enhance(1.2)
            e = ImageEnhance.Sharpness(img_tudo)
            img_tudo = e.enhance(1.3)
            img_tudo.save(temp_files[3])
        except:
            img_rgb.save(temp_files[3])

        for i, var in enumerate(variations):
            if i == 3: continue
            try:
                if var:
                    enhancer = var[0](img_rgb)
                    enhancer.enhance(var[1]).save(temp_files[i])
                else:
                    img_rgb.save(temp_files[i])
            except:
                img_rgb.save(temp_files[i])

        df = get_deepface()
        backends = ["retinaface", "mtcnn", "opencv", "ssd"]
        embeddings_data = None
        metodo_sucesso = ""

        for img_teste in temp_files:
            for backend in backends:
                try:
                    embeddings_data = df.represent(
                        img_path=img_teste, model_name="Facenet",
                        enforce_detection=True, detector_backend=backend,
                        align=True, normalization="base"
                    )
                    if embeddings_data and len(embeddings_data) > 0:
                        metodo_sucesso = f"{backend} + pré-processamento"
                        break
                except:
                    continue
            if embeddings_data: break

        if not embeddings_data:
            for img_teste in temp_files:
                try:
                    embeddings_data = df.represent(
                        img_path=img_teste, model_name="Facenet",
                        enforce_detection=False, detector_backend="opencv",
                        align=True, normalization="base"
                    )
                    if embeddings_data and len(embeddings_data) > 0:
                        metodo_sucesso = "opencv (sem enforce)"
                        st.info("⚠️ Rosto detectado com baixa confiança.")
                        break
                except:
                    continue

        if not embeddings_data:
            for img_teste in temp_files:
                try:
                    embeddings_data = df.represent(
                        img_path=img_teste, model_name="OpenFace",
                        enforce_detection=False, detector_backend="opencv", align=True
                    )
                    if embeddings_data and len(embeddings_data) > 0:
                        metodo_sucesso = "OpenFace (fallback)"
                        st.info("⚠️ Detecção com modelo alternativo.")
                        break
                except:
                    continue

        for f in temp_files:
            if os.path.exists(f): os.remove(f)

        if embeddings_data and len(embeddings_data) > 0:
            if metodo_sucesso:
                st.success(f"✅ Rosto detectado: {metodo_sucesso}")
            return embeddings_data[0]["embedding"]

        st.error("❌ Não foi possível detectar o rosto.")
        st.info("""
        **Dicas para melhorar a detecção:**
        1. 🌟 Iluminação frontal e forte
        2. 🎯 Rosto centralizado na câmera
        3. 😐 Expressão neutra
        4. 👓 Retire óculos escuros
        5. 🧢 Remova bonés/acessórios
        6. 📏 Distância de 30-50cm
        7. 📸 Prefira upload de foto
        """)
        return None
    except Exception as e:
        for f in temp_files:
            if os.path.exists(f): os.remove(f)
        st.error(f"Erro: {str(e)[:100]}")
        return None

def calcular_similaridade(vetor1, vetor2):
    v1, v2 = np.array(vetor1), np.array(vetor2)
    return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))

# ============================================================
# BUSCA INTELIGENTE E DINÂMICA
# ============================================================
def buscar_itens_inteligente(df, termo_busca):
    """
    Busca inteligente que:
    1. Remove acentos e normaliza texto
    2. Busca em múltiplas colunas (descrição, arquivo, observações)
    3. Suporta múltiplas palavras (AND lógico)
    4. Calcula score de relevância
    5. Ordena por melhor match
    """
    if not termo_busca or len(termo_busca.strip()) < 2:
        return df.copy(), []

    termo = termo_busca.strip().upper()
    termos = [t.strip() for t in termo.split() if len(t.strip()) >= 2]

    if not termos:
        return df.copy(), []

    resultados = []
    scores = []

    for idx, row in df.iterrows():
        # Campos de busca
        descricao = str(row.get("Descrição do Produto", "")).upper()
        arquivo = str(row.get("Arquivo Origem", "")).upper()
        obs = str(row.get("Observações", "")).upper()
        situacao = str(row.get("Situação", "")).upper()

        # Texto combinado para busca
        texto_completo = f"{descricao} {arquivo} {obs} {situacao}"

        # Score de matching
        score = 0
        termos_encontrados = 0

        for t in termos:
            # Match exato na descrição = maior peso
            if t in descricao:
                score += 10
                if descricao.startswith(t):
                    score += 5  # Bônus se começa com o termo
                termos_encontrados += 1
            # Match no arquivo
            elif t in arquivo:
                score += 3
                termos_encontrados += 1
            # Match em observações
            elif t in obs:
                score += 2
                termos_encontrados += 1
            # Match em qualquer lugar
            elif t in texto_completo:
                score += 1
                termos_encontrados += 1

        # Bônus se TODOS os termos foram encontrados
        if termos_encontrados == len(termos):
            score += 5

        if score > 0:
            resultados.append(idx)
            scores.append(score)

    if not resultados:
        return df.copy(), []

    # Ordenar por score (maior primeiro)
    pares = sorted(zip(resultados, scores), key=lambda x: x[1], reverse=True)
    indices_ordenados = [p[0] for p in pares]

    return df.loc[indices_ordenados].copy(), indices_ordenados

# ============================================================
# ENGINES DE EXTRACAO DE DADOS
# ============================================================
FITZ_AVAILABLE = False
try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    pass

def consolidar_registros(registros):
    if not registros:
        return []
    grupos = {}
    for reg in registros:
        chave = reg["Descrição do Produto"].strip().upper()
        if chave not in grupos:
            grupos[chave] = {"registros": [], "arquivos_origem": set(), "quantidades": []}
        grupos[chave]["registros"].append(reg)
        grupos[chave]["arquivos_origem"].add(reg["Arquivo Origem"])
        grupos[chave]["quantidades"].append(reg["Quantidade NF"])

    registros_consolidados = []
    for chave, dados in grupos.items():
        qtds = dados["quantidades"]
        arquivos = sorted(dados["arquivos_origem"])
        if len(set(qtds)) == 1:
            reg_base = dados["registros"][0].copy()
            reg_base["Arquivo Origem"] = " | ".join(arquivos)
            reg_base["Observações"] = f"Item encontrado em {len(arquivos)} arquivo(s)."
            registros_consolidados.append(reg_base)
        else:
            qtd_total = sum(qtds)
            reg_base = dados["registros"][0].copy()
            reg_base["Quantidade NF"] = qtd_total
            reg_base["Arquivo Origem"] = " | ".join(arquivos)
            reg_base["Observações"] = f"Quantidades divergentes ({len(arquivos)} arquivos). Qtds: {', '.join(str(q) for q in qtds)}. Total: {qtd_total}."
            registros_consolidados.append(reg_base)
    return registros_consolidados

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
# DASHBOARD ATUALIZADO
# ============================================================
def render_dashboard(df):
    if df.empty:
        st.info("📊 Carregue documentos para visualizar o dashboard.")
        return

    total = len(df)
    conformes = len(df[df["Situação"] == "Conforme"])
    divergentes = len(df[df["Situação"] == "Divergente"])
    pendentes = len(df[df["Situação"] == "Pendente"])
    com_foto = len(df[df["Foto Capturada"] == "Sim"])

    pct_conforme = (conformes / total * 100) if total > 0 else 0
    pct_divergente = (divergentes / total * 100) if total > 0 else 0
    pct_pendente = (pendentes / total * 100) if total > 0 else 0

    st.markdown("### 📊 Painel de Controle em Tempo Real")

    # Cards principais
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
        <div class="dashboard-card" style="border-top: 4px solid #0284C7;">
            <div class="dashboard-metric">{total}</div>
            <div class="dashboard-label">Total de Itens</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="dashboard-card" style="border-top: 4px solid #22C55E;">
            <div class="dashboard-metric" style="color: #22C55E;">{conformes}</div>
            <div class="dashboard-label">Conformes</div>
            <div style="margin-top:8px;">
                <div class="progress-bar"><div class="progress-fill" style="width:{pct_conforme}%; background:#22C55E;"></div></div>
                <small style="color:#64748B;">{pct_conforme:.1f}%</small>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="dashboard-card" style="border-top: 4px solid #EF4444;">
            <div class="dashboard-metric" style="color: #EF4444;">{divergentes}</div>
            <div class="dashboard-label">Divergentes</div>
            <div style="margin-top:8px;">
                <div class="progress-bar"><div class="progress-fill" style="width:{pct_divergente}%; background:#EF4444;"></div></div>
                <small style="color:#64748B;">{pct_divergente:.1f}%</small>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class="dashboard-card" style="border-top: 4px solid #F59E0B;">
            <div class="dashboard-metric" style="color: #F59E0B;">{pendentes}</div>
            <div class="dashboard-label">Pendentes</div>
            <div style="margin-top:8px;">
                <div class="progress-bar"><div class="progress-fill" style="width:{pct_pendente}%; background:#F59E0B;"></div></div>
                <small style="color:#64748B;">{pct_pendente:.1f}%</small>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Gráficos e análises
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### 📁 Itens por Arquivo de Origem")
        arquivos_count = df["Arquivo Origem"].value_counts()
        for arq, count in arquivos_count.items():
            st.markdown(f"""
            <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid #E2E8F0;">
                <span style="font-size:13px; color:#334155;">📄 {arq[:40]}{'...' if len(arq) > 40 else ''}</span>
                <span class="status-badge status-pendente">{count} itens</span>
            </div>
            """, unsafe_allow_html=True)

    with col_right:
        st.markdown("#### 📸 Auditoria Visual")
        st.markdown(f"""
        <div class="dashboard-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div class="dashboard-metric" style="font-size:24px;">{com_foto}/{total}</div>
                    <div class="dashboard-label">Itens com Foto</div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:28px; font-weight:700; color:#0284C7;">{(com_foto/total*100):.0f}%</div>
                    <div style="font-size:12px; color:#64748B;">Cobertura</div>
                </div>
            </div>
            <div class="progress-bar" style="margin-top:12px;">
                <div class="progress-fill" style="width:{(com_foto/total*100)}%; background:#0284C7;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Últimos itens conferidos
        st.markdown("#### 🔄 Últimas Atualizações")
        df_recente = df[df["Situação"] != "Pendente"].tail(5)
        if not df_recente.empty:
            for _, row in df_recente.iterrows():
                status_class = "status-conforme" if row["Situação"] == "Conforme" else "status-divergente"
                st.markdown(f"""
                <div style="display:flex; justify-content:space-between; align-items:center; padding:6px 0; font-size:13px;">
                    <span style="color:#334155; flex:1;">{row['Descrição do Produto'][:45]}...</span>
                    <span class="status-badge {status_class}">{row['Situação']}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("Nenhum item conferido ainda.")

# ============================================================
# PAINEL DE AUTENTICACAO (LOGIN + CADASTRO)
# ============================================================
if not st.session_state.autenticado:
    st.markdown("""
        <div style='text-align: center; margin-top: 30px; margin-bottom: 20px;'>
            <h1 style='color:#0284C7; font-size: 32px;'>📸 Identificação Biométrica Estel</h1>
            <p style='color:#64748B; font-size: 16px;'>Tire uma foto para logar instantaneamente ou criar seu perfil.</p>
        </div>
    """, unsafe_allow_html=True)

    # Status da conexão
    if not SUPABASE_AVAILABLE:
        st.warning(f"⚠️ Supabase indisponível: {supabase_error_msg}")
        st.info("💡 O sistema funcionará em modo local com login de contingência.")

    c_esq, c_centro, c_dir = st.columns([1, 1.4, 1])

    with c_centro:
        tab_cam, tab_upload = st.tabs(["📷 Câmera", "📁 Upload de Foto"])
        foto_captura = None

        with tab_cam:
            st.info("💡 Dicas: Boa iluminação frontal, rosto centralizado, sem óculos escuros")
            foto_captura = st.camera_input("Scanner Facial Ativo:", key="scan_facial_posto_unico")

        with tab_upload:
            st.info("💡 Fotos da galeria geralmente têm melhor qualidade")
            foto_upload = st.file_uploader("Selecione uma foto do rosto:", type=["jpg", "jpeg", "png"], key="upload_foto_login")
            if foto_upload:
                foto_captura = foto_upload
                st.image(foto_upload, caption="Foto selecionada", width=200)

        if foto_captura:
            with st.spinner("🔍 Analisando biometria..."):
                vetor_atual = processar_biometria(foto_captura)

                if vetor_atual is not None:
                    if supabase and SUPABASE_AVAILABLE:
                        try:
                            todos_usuarios = supabase.table("usuarios")\
                                .select("*")\
                                .not_("face_embedding", "is", "null")\
                                .execute()
                        except Exception as e:
                            st.error(f"❌ Erro ao consultar usuários: {str(e)[:100]}")
                            st.info("💡 Use o login de contingência abaixo")
                            todos_usuarios = None

                        if todos_usuarios and hasattr(todos_usuarios, 'data'):
                            reconhecido = False
                            operador_nome = ""
                            melhor_score = 0.0
                            usuario_id = None

                            for usuario in todos_usuarios.data:
                                if not usuario.get("face_embedding"):
                                    continue
                                try:
                                    vetor_salvo = json.loads(usuario["face_embedding"])
                                    score = calcular_similaridade(vetor_atual, vetor_salvo)
                                    if score > melhor_score:
                                        melhor_score = score
                                    if score > 0.70:
                                        reconhecido = True
                                        operador_nome = usuario["nome"]
                                        usuario_id = usuario.get("id")
                                        break
                                except Exception:
                                    pass

                            if reconhecido:
                                st.success(f"✅ Bem-vindo, {operador_nome}!")
                                st.info(f"📊 Score de confiança: {melhor_score:.1%}")
                                st.session_state.autenticado = True
                                st.session_state.usuario_nome = operador_nome
                                st.session_state.usuario_id = usuario_id
                                time.sleep(1)
                                safe_rerun()
                            else:
                                st.warning("👤 Rosto não localizado na base.")
                                st.caption(f"📊 Melhor score: {melhor_score:.1%} (mínimo: 70%)")
                                st.session_state.temp_face_vector = vetor_atual

                                # === CADASTRO DE NOVO USUÁRIO ===
                                with st.expander("📝 Criar Novo Cadastro com esta Biometria", expanded=True):
                                    st.markdown("""
                                    <div style="background:#F0F9FF; padding:12px; border-radius:8px; margin-bottom:12px;">
                                        <b>ℹ️ Novo usuário detectado</b><br>
                                        Preencha os dados abaixo para vincular sua biometria ao sistema.
                                    </div>
                                    """, unsafe_allow_html=True)

                                    col_c1, col_c2 = st.columns(2)
                                    with col_c1:
                                        nome_cad = st.text_input("Nome Completo:", placeholder="Ex: João Silva")
                                        user_cad = st.text_input("ID Usuário (Login):", placeholder="Ex: joao.silva")
                                    with col_c2:
                                        email_cad = st.text_input("E-mail:", placeholder="joao@estel.com.br")
                                        senha_cad = st.text_input("Defina uma Senha:", type="password")

                                    cargo_cad = st.selectbox("Cargo:", ["Operador", "Supervisor", "Administrador"])

                                    if st.button("💾 Salvar Cadastro e Entrar", type="primary"):
                                        if nome_cad and user_cad and senha_cad:
                                            try:
                                                vetor_json = json.dumps(st.session_state.temp_face_vector)
                                                result = supabase.table("usuarios").insert({
                                                    "nome": nome_cad,
                                                    "usuario": user_cad,
                                                    "email": email_cad,
                                                    "senha": senha_cad,
                                                    "cargo": cargo_cad,
                                                    "face_embedding": vetor_json,
                                                    "ativo": True
                                                }).execute()

                                                st.success("🎉 Cadastro realizado com sucesso!")
                                                st.session_state.autenticado = True
                                                st.session_state.usuario_nome = nome_cad
                                                st.session_state.temp_face_vector = None
                                                time.sleep(1)
                                                safe_rerun()
                                            except Exception as e:
                                                st.error(f"Erro ao salvar: {e}")
                                        else:
                                            st.error("Preencha Nome, Usuário e Senha.")
                    else:
                        # MODO CONTINGÊNCIA
                        st.warning("⚠️ Modo Offline - Login de Contingência")
                        if supabase_error_msg:
                            st.caption(f"Erro: {supabase_error_msg}")

                        st.markdown("---")
                        st.subheader("🔐 Acesso de Emergência")
                        col_u, col_s = st.columns(2)
                        with col_u:
                            u_t = st.text_input("Usuário:", value="admin", key="user_contingencia")
                        with col_s:
                            s_t = st.text_input("Senha:", type="password", value="admin", key="pass_contingencia")

                        if st.button("Entrar", key="btn_contingencia", type="primary"):
                            if u_t == "admin" and s_t == "admin":
                                st.session_state.autenticado = True
                                st.session_state.usuario_nome = "Supervisor Local"
                                safe_rerun()
                            else:
                                st.error("❌ Credenciais inválidas. Use admin/admin")
                else:
                    st.error("⚠️ Não foi possível detectar o rosto. Ajuste a iluminação e tente novamente.")

# ============================================================
# PAINEL PRINCIPAL
# ============================================================
else:
    cab_esquerdo, cab_direito = st.columns([4, 1])
    cab_esquerdo.markdown(f"<h1>🚚 Validador de Retornos de Obra</h1>", unsafe_allow_html=True)
    cab_esquerdo.caption(f"Operador: **{st.session_state.usuario_nome}** | {'🟢 Online' if SUPABASE_AVAILABLE else '🟡 Offline'}")

    if cab_direito.button("🚪 Sair", key="logout"):
        st.session_state.autenticado = False
        st.session_state.dados_conferencia = pd.DataFrame()
        st.session_state.fotos_postadas = {}
        st.session_state.item_selecionado_idx = None
        safe_rerun()

    st.markdown("---")

    # SIDEBAR
    with st.sidebar:
        st.header("📥 Carregar Documentos")
        arquivos_entrada = st.file_uploader(
            "Arraste DANFEs (PDF) ou planilhas:",
            type=["pdf", "xlsx", "xls", "csv"],
            accept_multiple_files=True
        )

        if arquivos_entrada:
            if st.button("⚡ Processar Carga em Lote", type="primary"):
                all_records = []
                with st.spinner("Lendo documentos..."):
                    for arq in arquivos_entrada:
                        if arq.name.endswith(".pdf"):
                            all_records.extend(extrair_linhas_danfe(arq))
                        else:
                            all_records.extend(extrair_linhas_excel(arq))

                    if all_records:
                        with st.spinner("Consolidando dados..."):
                            registros_consolidados = consolidar_registros(all_records)
                            df_novo = pd.DataFrame(registros_consolidados)
                            total_original = len(all_records)
                            total_consolidado = len(df_novo)
                            itens_removidos = total_original - total_consolidado
                            st.session_state.dados_conferencia = df_novo

                            if itens_removidos > 0:
                                st.success(f"📊 {total_consolidado} itens consolidados!")
                                st.info(f"{total_original} brutos → {itens_removidos} tratados → {total_consolidado} únicos")
                            else:
                                st.success(f"📊 {total_consolidado} itens mapeados!")

                            divergencias = [r for r in registros_consolidados if "divergentes" in r.get("Observações", "")]
                            if divergencias:
                                st.warning(f"⚠️ {len(divergencias)} item(s) com quantidades divergentes foram SOMADOS.")
                        safe_rerun()

        if not st.session_state.dados_conferencia.empty:
            st.markdown("---")
            st.header("📤 Fechamento")
            memoria_excel = io.BytesIO()
            with pd.ExcelWriter(memoria_excel, engine='openpyxl') as writer:
                st.session_state.dados_conferencia.to_excel(writer, index=False, sheet_name="Consolidado")

            st.download_button(
                label="💾 Exportar Relatório",
                data=memoria_excel.getvalue(),
                file_name=f"Relatorio_Estel_{time.strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.ms-excel"
            )

            if st.button("🗑️ Limpar Tudo"):
                st.session_state.dados_conferencia = pd.DataFrame()
                st.session_state.fotos_postadas = {}
                st.session_state.item_selecionado_idx = None
                safe_rerun()

    # CONTEÚDO PRINCIPAL
    if st.session_state.dados_conferencia.empty:
        st.info("💡 **Dica:** Carregue notas fiscais no menu à esquerda para iniciar.")
    else:
        aba_triagem, aba_tabela, aba_dashboard = st.tabs([
            "📸 Posto de Triagem",
            "📋 Lista Consolidada",
            "📊 Dashboard"
        ])

        # ============================================================
        # ABA TRIAGEM - BUSCA INTELIGENTE
        # ============================================================
        with aba_triagem:
            df_ref = st.session_state.dados_conferencia

            st.markdown("""
            <div class="busca-container">
                <b>🔍 Busca Inteligente de Insumos</b><br>
                <small>Digite parte do nome, código ou descrição. A busca é <b>dinâmica</b> e procura em todos os campos.</small>
            </div>
            """, unsafe_allow_html=True)

            # Busca em tempo real
            termo_busca = st.text_input(
                "Buscar produto:",
                value=st.session_state.get("busca_termo", ""),
                placeholder="Ex: chave combinada, cimento, parafuso...",
                key="busca_produto"
            ).strip()

            # Atualiza session state
            if termo_busca != st.session_state.get("busca_termo", ""):
                st.session_state.busca_termo = termo_busca
                st.session_state.item_selecionado_idx = None
                safe_rerun()

            # Executa busca inteligente
            df_resultado, indices_resultado = buscar_itens_inteligente(df_ref, termo_busca)

            # Filtro por arquivo (sempre visível)
            arquivos_unicos = df_ref['Arquivo Origem'].unique()
            if len(arquivos_unicos) > 1:
                arquivo_filtro = st.selectbox(
                    "📁 Filtrar por Arquivo/NF:",
                    ["Todos os arquivos"] + list(arquivos_unicos),
                    key="filtro_arquivo"
                )
                if arquivo_filtro != "Todos os arquivos":
                    df_resultado = df_resultado[df_resultado['Arquivo Origem'].str.contains(arquivo_filtro, na=False)]

            # Resultados da busca
            if termo_busca and len(termo_busca) >= 2:
                if not df_resultado.empty:
                    st.markdown(f"""
                    <div class="busca-resultado">
                        ✅ <b>{len(df_resultado)} resultado(s)</b> para "{termo_busca}"
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="busca-vazio">
                        ⚠️ Nenhum resultado exato para "{termo_busca}". Mostrando todos os itens:
                    </div>
                    """, unsafe_allow_html=True)
                    df_resultado = df_ref.copy()
            elif termo_busca and len(termo_busca) < 2:
                st.info("💡 Digite pelo menos 2 caracteres para buscar.")
                df_resultado = df_ref.copy()
            else:
                df_resultado = df_ref.copy()

            # Selectbox com resultados
            opcoes_resultado = [
                f"[{row['Situação']}] [{row['Arquivo Origem'][:25]}] - {row['Descrição do Produto'][:60]}"
                for _, row in df_resultado.iterrows()
            ]

            if opcoes_resultado:
                idx_selecionado = st.selectbox(
                    "Selecione o insumo para conferência:",
                    range(len(opcoes_resultado)),
                    format_func=lambda i: opcoes_resultado[i],
                    key="select_item"
                )

                # Pega o índice real do DataFrame original
                if indices_resultado:
                    idx_real = indices_resultado[idx_selecionado]
                else:
                    idx_real = df_resultado.index[idx_selecionado]

                st.session_state.item_selecionado_idx = idx_real

                linha = df_ref.loc[idx_real]

                # Badge de status colorido
                status_class = {
                    "Pendente": "status-pendente",
                    "Conforme": "status-conforme",
                    "Divergente": "status-divergente"
                }.get(linha['Situação'], "status-pendente")

                st.markdown(f"""
                <div class='card-conferencia'>
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <span style='color:#64748B; font-size:13px;'>📄 {linha['Arquivo Origem']}</span>
                        <span class="status-badge {status_class}">{linha['Situação']}</span>
                    </div>
                    <h3 style='color:#0284C7; margin:0; font-size:18px;'>{linha['Descrição do Produto']}</h3>
                    <div style="display:flex; gap:24px; margin-top:12px;">
                        <div>
                            <div style="font-size:11px; color:#64748B; text-transform:uppercase;">Qtd NF</div>
                            <div style="font-size:20px; font-weight:700; color:#1E293B;">{linha['Quantidade NF']}</div>
                        </div>
                        <div>
                            <div style="font-size:11px; color:#64748B; text-transform:uppercase;">Conferida</div>
                            <div style="font-size:20px; font-weight:700; color:#0284C7;">{linha['Quantidade Conferida']}</div>
                        </div>
                        <div>
                            <div style="font-size:11px; color:#64748B; text-transform:uppercase;">Foto</div>
                            <div style="font-size:20px; font-weight:700; color:#{'22C55E' if linha['Foto Capturada'] == 'Sim' else 'EF4444'};">
                                {'✅' if linha['Foto Capturada'] == 'Sim' else '❌'}
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                col_cam, col_form = st.columns(2)
                with col_cam:
                    foto_mat = st.camera_input(
                        "📸 Foto do Material:",
                        key=f"cam_{idx_real}"
                    )
                    if foto_mat:
                        st.session_state.fotos_postadas[idx_real] = foto_mat.getvalue()
                        st.session_state.dados_conferencia.at[idx_real, "Foto Capturada"] = "Sim"
                        st.toast("📸 Foto armazenada!")
                        safe_rerun()

                    if idx_real in st.session_state.fotos_postadas:
                        st.image(
                            st.session_state.fotos_postadas[idx_real],
                            caption="Foto atual",
                            width=300
                        )

                with col_form:
                    qtd_conf = st.number_input(
                        "Quantidade real descarregada:",
                        min_value=0.0,
                        value=float(linha['Quantidade NF']),
                        step=0.1,
                        key=f"qtd_{idx_real}"
                    )
                    obs = st.text_area(
                        "Notas / Divergências:",
                        value=linha['Observações'],
                        key=f"obs_{idx_real}"
                    )

                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("✅ Confirmar Conforme", type="primary", key=f"conf_ok_{idx_real}"):
                            st.session_state.dados_conferencia.at[idx_real, "Quantidade Conferida"] = linha['Quantidade NF']
                            st.session_state.dados_conferencia.at[idx_real, "Observações"] = obs
                            st.session_state.dados_conferencia.at[idx_real, "Situação"] = "Conforme"
                            st.toast("✅ Item confirmado como Conforme!")
                            safe_rerun()

                    with col_btn2:
                        if st.button("⚠️ Registrar Divergência", key=f"conf_div_{idx_real}"):
                            st.session_state.dados_conferencia.at[idx_real, "Quantidade Conferida"] = qtd_conf
                            st.session_state.dados_conferencia.at[idx_real, "Observações"] = obs
                            st.session_state.dados_conferencia.at[idx_real, "Situação"] = "Divergente"
                            st.toast("⚠️ Divergência registrada!")
                            safe_rerun()

                    # Gravar no Supabase
                    if st.button("💾 Gravar no Banco", key=f"save_{idx_real}"):
                        st.session_state.dados_conferencia.at[idx_real, "Quantidade Conferida"] = qtd_conf
                        st.session_state.dados_conferencia.at[idx_real, "Observações"] = obs
                        situacao_final = "Conforme" if qtd_conf == linha['Quantidade NF'] else "Divergente"
                        st.session_state.dados_conferencia.at[idx_real, "Situação"] = situacao_final

                        if supabase and SUPABASE_AVAILABLE:
                            try:
                                supabase.table("conferencia_itens").insert({
                                    "operador": st.session_state.usuario_nome,
                                    "usuario_id": st.session_state.usuario_id,
                                    "nome_arquivo": linha['Arquivo Origem'],
                                    "descricao_produto": linha['Descrição do Produto'],
                                    "quantidade_nf": float(linha['Quantidade NF']),
                                    "quantidade_conferida": float(qtd_conf),
                                    "situacao": situacao_final,
                                    "observacoes": obs,
                                    "data_hora": time.strftime("%Y-%m-%d %H:%M:%S")
                                }).execute()
                                st.toast("💾 Dados gravados no Supabase!")
                            except Exception as e:
                                st.error(f"Erro ao sincronizar: {e}")
                        safe_rerun()
            else:
                st.warning("Nenhum item disponível para seleção.")

        # ============================================================
        # ABA TABELA
        # ============================================================
        with aba_tabela:
            df = st.session_state.dados_conferencia

            # Filtros
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                filtro_status = st.multiselect("Filtrar por Status:", ["Pendente", "Conforme", "Divergente"], default=[])
            with col_f2:
                filtro_arquivo = st.multiselect("Filtrar por Arquivo:", df['Arquivo Origem'].unique(), default=[])
            with col_f3:
                filtro_foto = st.selectbox("Com Foto:", ["Todos", "Sim", "Não"])

            df_filtrado = df.copy()
            if filtro_status:
                df_filtrado = df_filtrado[df_filtrado["Situação"].isin(filtro_status)]
            if filtro_arquivo:
                df_filtrado = df_filtrado[df_filtrado["Arquivo Origem"].isin(filtro_arquivo)]
            if filtro_foto != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Foto Capturada"] == filtro_foto]

            st.dataframe(df_filtrado, use_container_width=True, height=500)
            st.caption(f"Mostrando {len(df_filtrado)} de {len(df)} itens")

        # ============================================================
        # ABA DASHBOARD
        # ============================================================
        with aba_dashboard:
            render_dashboard(st.session_state.dados_conferencia)
     
