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
import datetime

# ============================================================
# CONEXAO COM BANCO DE DADOS (SQLALCHEMY / COCKROACHDB)
# ============================================================
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

# Configure a URL com suas credenciais do CockroachDB
DATABASE_URL = "cockroachdb://usuario:senha@host:26257/nome_do_banco?sslmode=verify-full"

Base = declarative_base()

class Usuario(Base):
    __tablename__ = 'usuarios'
    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(255), nullable=False)
    matricula = Column(String(100), unique=True, nullable=False)
    senha = Column(String(255), nullable=False)
    embedding_facial = Column(Text) # Armazenado em formato JSON string
    email = Column(String(255))
    cargo = Column(String(255))

class ConferenciaItem(Base):
    __tablename__ = 'conferencia_itens'
    id = Column(Integer, primary_key=True, autoincrement=True)
    operador = Column(String(255))
    usuario_id = Column(Integer)
    nome_arquivo = Column(String(255))
    descricao_produto = Column(Text)
    quantidade_nf = Column(Float)
    quantidade_conferida = Column(Float)
    situacao = Column(String(100))
    observacoes = Column(Text)
    data_hora = Column(DateTime, default=datetime.datetime.utcnow)

DB_AVAILABLE = False
SessionLocal = None

try:
    # Criação do engine e das tabelas automaticamente
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    DB_AVAILABLE = True
except Exception as e:
    st.error(f"Erro de conexão com o CockroachDB: {e}")
    DB_AVAILABLE = False


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

.busca-container { background: linear-gradient(135deg, #E0F2FE 0%, #F0F9FF 100%); padding: 16px; border-radius: 12px; border-left: 4px solid #0284C7; margin-bottom: 16px; }
.busca-resultado { background: #F0FDF4; padding: 12px; border-radius: 8px; border-left: 4px solid #22C55E; margin: 8px 0; }
.busca-vazio { background: #FEF2F2; padding: 12px; border-radius: 8px; border-left: 4px solid #EF4444; margin: 8px 0; }

.dashboard-card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); border: 1px solid #E2E8F0; }
.dashboard-metric { font-size: 32px; font-weight: 700; color: #0284C7; }
.dashboard-label { font-size: 13px; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; }
.progress-bar { width: 100%; height: 8px; background: #E2E8F0; border-radius: 4px; overflow: hidden; }
.progress-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease; }
.status-badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }
.status-pendente { background: #FEF3C7; color: #92400E; }
.status-conforme { background: #DCFCE7; color: #166534; }
.status-divergente { background: #FEE2E2; color: #991B1B; }

.login-box { background: white; border: 1px solid #E2E8F0; padding: 24px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-top: 16px; }
.divider { display: flex; align-items: center; margin: 20px 0; color: #64748B; font-size: 13px; }
.divider::before, .divider::after { content: ''; flex: 1; height: 1px; background: #E2E8F0; margin: 0 12px; }

.cadastro-box { background: linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%); border: 1px solid #86EFAC; padding: 20px; border-radius: 12px; margin-top: 16px; }
</style>
""", unsafe_allow_html=True)

# Session State
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
if "busca_termo" not in st.session_state:
    st.session_state.busca_termo = ""
if "item_selecionado_idx" not in st.session_state:
    st.session_state.item_selecionado_idx = None
if "mostrar_cadastro" not in st.session_state:
    st.session_state.mostrar_cadastro = False

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
            (ImageEnhance.Sharpness, 1.5), None,
            (ImageEnhance.Contrast, 0.8), (ImageEnhance.Brightness, 0.9)
        ]

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
        **Dicas:**
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
# BUSCA INTELIGENTE
# ============================================================
def buscar_itens_inteligente(df, termo_busca):
    if not termo_busca or len(termo_busca.strip()) < 2:
        return df.copy(), []

    termo = termo_busca.strip().upper()
    termos = [t.strip() for t in termo.split() if len(t.strip()) >= 2]

    if not termos:
        return df.copy(), []

    resultados = []
    scores = []

    for idx, row in df.iterrows():
        descricao = str(row.get("Descrição do Produto", "")).upper()
        arquivo = str(row.get("Arquivo Origem", "")).upper()
        obs = str(row.get("Observações", "")).upper()
        situacao = str(row.get("Situação", "")).upper()
        texto_completo = f"{descricao} {arquivo} {obs} {situacao}"

        score = 0
        termos_encontrados = 0

        for t in termos:
            if t in descricao:
                score += 10
                if descricao.startswith(t):
                    score += 5
                termos_encontrados += 1
            elif t in arquivo:
                score += 3
                termos_encontrados += 1
            elif t in obs:
                score += 2
                termos_encontrados += 1
            elif t in texto_completo:
                score += 1
                termos_encontrados += 1

        if termos_encontrados == len(termos):
            score += 5

        if score > 0:
            resultados.append(idx)
            scores.append(score)

    if not resultados:
        return df.copy(), []

    pares = sorted(zip(resultados, scores), key=lambda x: x[1], reverse=True)
    indices_ordenados = [p[0] for p in pares]

    return df.loc[indices_ordenados].copy(), indices_ordenados

# ============================================================
# EXTRACAO DE DADOS - CORRIGIDO PARA CARREGAR TODOS OS FORMATOS
# ============================================================
FITZ_AVAILABLE = False
PYPDF_AVAILABLE = False
PDFMINER_AVAILABLE = False

try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    try:
        import pymupdf as fitz
        FITZ_AVAILABLE = True
    except ImportError:
        pass

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    try:
        from PyPDF2 import PdfReader
        PYPDF_AVAILABLE = True
    except ImportError:
        pass

try:
    from pdfminer.high_level import extract_text
    PDFMINER_AVAILABLE = True
except ImportError:
    pass

def extrair_texto_pdf(pdf_bytes):
    texto = ""
    if FITZ_AVAILABLE:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for pagina in doc:
                texto += pagina.get_text()
            doc.close()
            if texto.strip():
                return texto
        except Exception:
            texto = ""

    if PYPDF_AVAILABLE:
        try:
            from io import BytesIO
            reader = PdfReader(BytesIO(pdf_bytes))
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    texto += page_text + "\n"
            if texto.strip():
                return texto
        except Exception:
            texto = ""

    if PDFMINER_AVAILABLE:
        try:
            from io import BytesIO
            texto = extract_text(BytesIO(pdf_bytes))
            if texto.strip():
                return texto
        except Exception:
            texto = ""

    return texto

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
    try:
        pdf_bytes = pdf_file.read()
        pdf_file.seek(0)

        if not FITZ_AVAILABLE:
            st.warning(f"⚠️ PyMuPDF não disponível. Tentando fallback para {pdf_file.name}")
            full_text = extrair_texto_pdf(pdf_bytes)
            if not full_text:
                st.warning(f"⚠️ Não foi possível extrair texto do PDF: {pdf_file.name}")
                return []
            return _extrair_danfe_por_texto(full_text, pdf_file.name)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        for page_num in range(len(doc)):
            page = doc[page_num]
            try:
                tables = page.find_tables()
                if tables and tables.tables:
                    for table in tables.tables:
                        rows = table.extract()
                        if not rows:
                            continue

                        header = [str(c).strip().upper() if c else "" for c in rows[0]]
                        idx_desc = None
                        idx_qtd = None

                        for i, h in enumerate(header):
                            h_clean = re.sub(r'[^A-ZÇÃÕÁÉÍÓÚÂÊÎÔÛÄËÏÖÜ]', '', h)
                            if any(k in h_clean for k in ["DESCRI", "PRODUTO", "PRODUTOSERVICO", "PRODUTOSERVIÇO"]):
                                idx_desc = i
                            if any(k in h_clean for k in ["QTD", "QUANT", "QTDE", "QUANTIDADE"]):
                                idx_qtd = i

                        if idx_desc is None and len(header) > 1:
                            idx_desc = 1
                        if idx_qtd is None and len(header) > 2:
                            idx_qtd = 2

                        for row in rows[1:]:
                            if not row or len(row) < 2:
                                continue

                            desc = ""
                            qtd = 1.0

                            if idx_desc is not None and idx_desc < len(row):
                                desc = str(row[idx_desc]).strip()
                                desc = re.sub(r'^\d+\s+', '', desc)
                                desc = re.sub(r'^\d+', '', desc).strip()

                            if idx_qtd is not None and idx_qtd < len(row):
                                qtd_str = str(row[idx_qtd]).strip()
                                qtd_str = qtd_str.replace('.', '').replace(',', '.')
                                try:
                                    qtd = float(qtd_str) if qtd_str else 1.0
                                except:
                                    qtd = 1.0

                            if desc and len(desc) > 3 and not desc.isdigit():
                                registros.append({
                                    "Arquivo Origem": pdf_file.name,
                                    "Descrição do Produto": desc.upper(),
                                    "Quantidade NF": qtd,
                                    "Quantidade Conferida": 0.0,
                                    "Situação": "Pendente",
                                    "Foto Capturada": "Não",
                                    "Observações": ""
                                })

                    continue
            except Exception:
                pass

            page_text = page.get_text("text")
            if page_text.strip():
                page_regs = _extrair_danfe_por_texto(page_text, pdf_file.name)
                registros.extend(page_regs)

        doc.close()

        if not registros:
            full_text = extrair_texto_pdf(pdf_bytes)
            if full_text.strip():
                registros = _extrair_danfe_por_texto(full_text, pdf_file.name)

    except Exception as e:
        st.error(f"❌ Erro ao processar PDF {pdf_file.name}: {str(e)[:100]}")

    return registros

def _extrair_danfe_por_texto(full_text, nome_arquivo):
    registros = []
    linhas = full_text.split("\n")
    modo_captura = False

    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue

        if re.search(r'C\.D(\.)?\s*PROD|DESCRI\.O\s*DO(\s*S)?\s*PRODUTO|CÓDIGO\s*PRODUTO|PRODUTO\s*SERVIÇO|DESCRIÇÃO\s*DOS\s*PRODUTOS', linha, re.IGNORECASE):
            modo_captura = True
            continue

        if re.search(r'C\.LCULO\s*DO\s*ISSQN|DADOS\s*ADICIONAIS|TRANSPORTADOR|INFORMAÇÕES\s*COMPLEMENTARES|CÁLCULO\s*DO\s*IMPOSTO', linha, re.IGNORECASE):
            modo_captura = False
            continue

        if modo_captura:
            numeros = re.findall(r'\b\d+[\d.,]*\b', linha)
            desc = re.sub(r'^\d+\s+', '', linha)
            desc = re.sub(r'\s*\d+[\d.,]*.*$', '', desc)
            desc = desc.strip()

            if len(desc) > 3 and not desc.isdigit():
                qtd = 1.0
                try:
                    if numeros:
                        for num_str in numeros:
                            num_limpa = num_str.replace('.', '').replace(',', '.')
                            try:
                                val = float(num_limpa)
                                if 0 < val < 100000:
                                    qtd = val
                                    break
                            except:
                                continue
                except ValueError:
                    pass

                registros.append({
                    "Arquivo Origem": nome_arquivo,
                    "Descrição do Produto": desc.upper(),
                    "Quantidade NF": qtd,
                    "Quantidade Conferida": 0.0,
                    "Situação": "Pendente",
                    "Foto Capturada": "Não",
                    "Observações": ""
                })

    return registros

def extrair_linhas_excel(excel_file):
    registros = []
    try:
        if excel_file.name.endswith('.csv'):
            df_cru = pd.read_csv(excel_file, encoding='latin1')
        else:
            df_cru = pd.read_excel(excel_file)
        if df_cru.empty:
            return []

        colunas = [c.upper() for c in df_cru.columns]
        col_desc = None
        col_qtd = None

        for i, c in enumerate(colunas):
            if any(kw in c for kw in ["DESCRI", "PRODUTO", "ITEM", "NOME", "MATERIAL", "INSUMO"]):
                col_desc = df_cru.columns[i]
                break
        if col_desc is None and len(df_cru.columns) > 1:
            col_desc = df_cru.columns[1]
        elif col_desc is None:
            col_desc = df_cru.columns[0]

        for i, c in enumerate(colunas):
            if any(kw in c for kw in ["QTD", "QUANT", "QTDE", "QUANTIDADE", "VOLUME", "TOTAL"]):
                col_qtd = df_cru.columns[i]
                break
        if col_qtd is None:
            col_qtd = df_cru.columns[0]

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
    except Exception as e:
        st.error(f"❌ Erro ao processar Excel/CSV {excel_file.name}: {str(e)[:100]}")
    return registros

# ============================================================
# DASHBOARD
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
# FUNÇÕES DE AUTENTICAÇÃO E CADASTRO
# ============================================================
def buscar_usuario_por_credenciais(matricula, senha):
    if not DB_AVAILABLE: return None
    with SessionLocal() as db:
        usuario = db.query(Usuario).filter(Usuario.matricula == matricula, Usuario.senha == senha).first()
        if usuario:
            return {"id": usuario.id, "nome": usuario.nome, "matricula": usuario.matricula, "cargo": usuario.cargo}
        return None

def buscar_usuario_por_biometria(embedding_capturado, threshold=0.6):
    if not DB_AVAILABLE: return None
    with SessionLocal() as db:
        usuarios = db.query(Usuario).all()
        for usuario in usuarios:
            if usuario.embedding_facial:
                try:
                    emb_bd = np.array(json.loads(usuario.embedding_facial))
                    dist = np.linalg.norm(emb_bd - embedding_capturado)
                    if dist < threshold:
                        return {"id": usuario.id, "nome": usuario.nome, "matricula": usuario.matricula}
                except Exception:
                    continue
    return None

def inserir_usuario_robusto(nome, matricula, senha, embedding_facial_list, email=None, cargo=None):
    if not DB_AVAILABLE: return False
    with SessionLocal() as db:
        try:
            embedding_str = json.dumps(embedding_facial_list) if embedding_facial_list else None
            
            novo_usuario = Usuario(
                nome=nome,
                matricula=matricula,
                senha=senha,
                embedding_facial=embedding_str,
                email=email,
                cargo=cargo
            )
            db.add(novo_usuario)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            st.error(f"Erro ao tentar cadastrar operador: {e}")
            return False

# ============================================================
# PAINEL DE AUTENTICACAO (LOGIN + CADASTRO)
# ============================================================
if not st.session_state.autenticado:
    st.markdown("""
        <div style='text-align: center; margin-top: 30px; margin-bottom: 20px;'>
            <h1 style='color:#0284C7; font-size: 32px;'>📸 Identificação Biométrica Estel</h1>
            <p style='color:#64748B; font-size: 16px;'>Escolha uma forma de acesso ao sistema.</p>
        </div>
    """, unsafe_allow_html=True)

    if not DB_AVAILABLE:
        st.warning(f"⚠️ Banco de Dados indisponível.")
        st.info("💡 O sistema funcionará em modo local com login de contingência.")

    c_esq, c_centro, c_dir = st.columns([1, 1.4, 1])

    with c_centro:

        # ============================================================
        # ABA 1: LOGIN POR BIOMETRIA
        # ============================================================
        st.markdown("""
        <div style="background: #F0F9FF; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #0284C7;">
            <b>🔐 Opção 1: Login por Biometria Facial</b><br>
            <small>Tire uma foto ou faça upload do seu rosto</small>
        </div>
        """, unsafe_allow_html=True)

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
                    if DB_AVAILABLE:
                        usuario_encontrado = buscar_usuario_por_biometria(vetor_atual)

                        if usuario_encontrado:
                            st.success(f"✅ Bem-vindo, {usuario_encontrado['nome']}!")
                            st.session_state.autenticado = True
                            st.session_state.usuario_nome = usuario_encontrado["nome"]
                            st.session_state.usuario_id = usuario_encontrado.get("id")
                            time.sleep(1)
                            safe_rerun()
                        else:
                            st.warning("👤 Rosto não reconhecido na base.")
                            st.info("💡 Use a **Opção 2** (Login com Senha) ou **Opção 3** (Cadastrar-se).")
                            st.session_state.temp_face_vector = vetor_atual
                    else:
                        st.warning("⚠️ Banco de dados indisponível. Biometria desativada.")
                        st.info("💡 Use a **Opção 2** (Login com Senha) ou modo offline.")
                else:
                    st.error("⚠️ Não foi possível detectar o rosto.")
                    st.info("💡 Use a **Opção 2** (Login com Senha).")

        # ============================================================
        # DIVISOR
        # ============================================================
        st.markdown('<div class="divider">OU</div>', unsafe_allow_html=True)

        # ============================================================
        # ABA 2: LOGIN COM USUARIO E SENHA
        # ============================================================
        st.markdown("""
        <div style="background: #F0FDF4; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #22C55E;">
            <b>🔑 Opção 2: Login com Usuário e Senha</b><br>
            <small>Digite suas credenciais cadastradas</small>
        </div>
        """, unsafe_allow_html=True)

        with st.container():
            col_u, col_s = st.columns(2)
            with col_u:
                login_user = st.text_input("👤 Usuário:", placeholder="Digite seu login", key="login_user")
            with col_s:
                login_pass = st.text_input("🔒 Senha:", type="password", placeholder="Digite sua senha", key="login_pass")

            col_btn1, col_btn2 = st.columns([1, 1])
            with col_btn1:
                if st.button("🔓 Entrar", type="primary",
