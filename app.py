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

# ============================================================
# BLOCO 1: SQLALCHEMY + COCKROACHDB (SUBSTITUI SUPABASE)
# ============================================================
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime

DB_AVAILABLE = False
db_error_msg = ""
engine = None
SessionLocal = None

Base = declarative_base()

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True)
    nome = Column(String(255), nullable=False)
    usuario = Column(String(100), unique=True, nullable=False)
    senha = Column(String(255), nullable=False)
    face_embedding = Column(Text)
    email = Column(String(255))
    cargo = Column(String(100))

class ConferenciaItem(Base):
    __tablename__ = "conferencia_itens"
    id = Column(Integer, primary_key=True)
    operador = Column(String(255))
    usuario_id = Column(Integer)
    nome_arquivo = Column(String(500))
    descricao_produto = Column(Text)
    quantidade_nf = Column(Float)
    quantidade_conferida = Column(Float)
    situacao = Column(String(50))
    observacoes = Column(Text)
    data_hora = Column(String(20))
    obra_parada = Column(String(255))

def init_db():
    global DB_AVAILABLE, db_error_msg, engine, SessionLocal
    try:
        DATABASE_URL = (
            "cockroachdb+psycopg2://almox:H31u6KWGzHjnu4EWXOCXrQ"
            "@kooky-singer-16481.jxf.gcp-us-east1.cockroachlabs.cloud:26257"
            "/defaultdb?sslmode=require"
        )
        engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        DB_AVAILABLE = True
    except Exception as e:
        db_error_msg = f"Falha na conexao CockroachDB: {str(e)[:100]}"
        DB_AVAILABLE = False

init_db()

def get_db_session():
    if SessionLocal:
        return SessionLocal()
    return None

# ============================================================
# CONFIGURACAO PERSISTENTE OBRA/PARADA
# ============================================================
CONFIG_FILE = "config_app.json"

def carregar_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def salvar_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False)
    except Exception:
        pass

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
.status-aprovado { background: #DCFCE7; color: #166534; }
.status-reparo { background: #FEF3C7; color: #92400E; }
.status-avaria { background: #FEE2E2; color: #991B1B; }

.login-box { background: white; border: 1px solid #E2E8F0; padding: 24px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-top: 16px; }
.divider { display: flex; align-items: center; margin: 20px 0; color: #64748B; font-size: 13px; }
.divider::before, .divider::after { content: ''; flex: 1; height: 1px; background: #E2E8F0; margin: 0 12px; }

.cadastro-box { background: linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%); border: 1px solid #86EFAC; padding: 20px; border-radius: 12px; margin-top: 16px; }

/* Radio buttons de classificacao */
.classif-aprovado [data-testid="stMarkdownContainer"] p { color: #166534 !important; font-weight: 700 !important; }
.classif-reparo [data-testid="stMarkdownContainer"] p { color: #92400E !important; font-weight: 700 !important; }
.classif-avaria [data-testid="stMarkdownContainer"] p { color: #991B1B !important; font-weight: 700 !important; }
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
if "obra_parada" not in st.session_state:
    cfg = carregar_config()
    st.session_state.obra_parada = cfg.get("obra_parada", "")

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
                        metodo_sucesso = f"{backend} + pre-processamento"
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
                        st.info("⚠️ Rosto detectado com baixa confianca.")
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
                        st.info("⚠️ Deteccao com modelo alternativo.")
                        break
                except:
                    continue

        for f in temp_files:
            if os.path.exists(f): os.remove(f)

        if embeddings_data and len(embeddings_data) > 0:
            if metodo_sucesso:
                st.success(f"✅ Rosto detectado: {metodo_sucesso}")
            return embeddings_data[0]["embedding"]

        st.error("❌ Nao foi possivel detectar o rosto.")
        st.info("""
        **Dicas:**
        1. 🌟 Iluminacao frontal e forte
        2. 🎯 Rosto centralizado na camera
        3. 😐 Expressao neutra
        4. 👓 Retire oculos escuros
        5. 🧢 Remova bones/acessorios
        6. 📏 Distancia de 30-50cm
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
        descricao = str(row.get("Descricao do Produto", "")).upper()
        arquivo = str(row.get("Arquivo Origem", "")).upper()
        obs = str(row.get("Observacoes", "")).upper()
        situacao = str(row.get("Situacao", "")).upper()
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
    """Extrai texto de PDF usando multiplas bibliotecas em ordem de prioridade."""
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
        chave = reg["Descricao do Produto"].strip().upper()
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
            reg_base["Observacoes"] = f"Item encontrado em {len(arquivos)} arquivo(s)."
            registros_consolidados.append(reg_base)
        else:
            qtd_total = sum(qtds)
            reg_base = dados["registros"][0].copy()
            reg_base["Quantidade NF"] = qtd_total
            reg_base["Arquivo Origem"] = " | ".join(arquivos)
            reg_base["Observacoes"] = f"Quantidades divergentes ({len(arquivos)} arquivos). Qtds: {', '.join(str(q) for q in qtds)}. Total: {qtd_total}."
            registros_consolidados.append(reg_base)
    return registros_consolidados

def extrair_linhas_danfe(pdf_file):
    registros = []
    try:
        pdf_bytes = pdf_file.read()
        pdf_file.seek(0)

        if not FITZ_AVAILABLE:
            st.warning(f"⚠️ PyMuPDF nao disponivel. Tentando fallback para {pdf_file.name}")
            full_text = extrair_texto_pdf(pdf_bytes)
            if not full_text:
                st.warning(f"⚠️ Nao foi possivel extrair texto do PDF: {pdf_file.name}")
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
                            h_clean = re.sub(r'[^A-ZCAOAEIOUAEIOUAEIOU]', '', h)
                            if any(k in h_clean for k in ["DESCRI", "PRODUTO", "PRODUTOSERVICO", "PRODUTOSERVICO"]):
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
                                    "Descricao do Produto": desc.upper(),
                                    "Quantidade NF": qtd,
                                    "Quantidade Conferida": 0.0,
                                    "Situacao": "Pendente",
                                    "Foto Capturada": "Nao",
                                    "Observacoes": ""
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
    """Extrai produtos do texto do DANFE usando regex (metodo fallback)."""
    registros = []
    linhas = full_text.split("\n")
    modo_captura = False

    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue

        if re.search(r'C\.D(.)?\s*PROD|DESCRI\.O\s*DO(\s*S)?\s*PRODUTO|CODIGO\s*PRODUTO|PRODUTO\s*SERVICO|DESCRICAO\s*DOS\s*PRODUTOS', linha, re.IGNORECASE):
            modo_captura = True
            continue

        if re.search(r'C\.LCULO\s*DO\s*ISSQN|DADOS\s*ADICIONAIS|TRANSPORTADOR|INFORMACOES\s*COMPLEMENTARES|CALCULO\s*DO\s*IMPOSTO', linha, re.IGNORECASE):
            modo_captura = False
            continue

        if modo_captura:
            numeros = re.findall(r'\d+[\d.,]*', linha)

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
                    "Descricao do Produto": desc.upper(),
                    "Quantidade NF": qtd,
                    "Quantidade Conferida": 0.0,
                    "Situacao": "Pendente",
                    "Foto Capturada": "Nao",
                    "Observacoes": ""
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
                    "Descricao do Produto": desc_val,
                    "Quantidade NF": qtd_val,
                    "Quantidade Conferida": 0.0,
                    "Situacao": "Pendente",
                    "Foto Capturada": "Nao",
                    "Observacoes": ""
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
    conformes = len(df[df["Situacao"] == "Conforme"])
    divergentes = len(df[df["Situacao"] == "Divergente"])
    pendentes = len(df[df["Situacao"] == "Pendente"])
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

        st.markdown("#### 🔄 Ultimas Atualizacoes")
        df_recente = df[df["Situacao"] != "Pendente"].tail(5)
        if not df_recente.empty:
            for _, row in df_recente.iterrows():
                status_class = "status-conforme" if row["Situacao"] == "Conforme" else "status-divergente"
                st.markdown(f"""
                <div style="display:flex; justify-content:space-between; align-items:center; padding:6px 0; font-size:13px;">
                    <span style="color:#334155; flex:1;">{row['Descricao do Produto'][:45]}...</span>
                    <span class="status-badge {status_class}">{row['Situacao']}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("Nenhum item conferido ainda.")

# ============================================================
# BLOCO 2: FUNCOES DE LOGIN E CADASTRO (SQLALCHEMY)
# ============================================================
def buscar_usuario_por_credenciais(usuario, senha):
    """Busca usuario por login e senha. Retorna dict ou None."""
    session = get_db_session()
    if not session:
        return None
    try:
        user = session.query(Usuario).filter(Usuario.usuario == usuario).first()
        if user and user.senha == senha:
            return {
                "id": user.id,
                "nome": user.nome,
                "usuario": user.usuario,
                "senha": user.senha,
                "face_embedding": user.face_embedding,
                "email": user.email,
                "cargo": user.cargo
            }
        return None
    except Exception as e:
        st.error(f"Erro ao consultar usuario: {str(e)[:100]}")
        return None
    finally:
        session.close()

def buscar_usuario_por_biometria(vetor_atual):
    """Busca usuario por biometria facial. Retorna (user_dict, score) ou (None, 0)."""
    session = get_db_session()
    if not session:
        return None, 0.0
    try:
        usuarios = session.query(Usuario).all()
        melhor_score = 0.0
        melhor_usuario = None

        for usuario in usuarios:
            face_emb = usuario.face_embedding
            if not face_emb:
                continue
            try:
                if isinstance(face_emb, str):
                    vetor_salvo = json.loads(face_emb)
                else:
                    vetor_salvo = face_emb

                score = calcular_similaridade(vetor_atual, vetor_salvo)
                if score > melhor_score:
                    melhor_score = score
                    melhor_usuario = {
                        "id": usuario.id,
                        "nome": usuario.nome,
                        "usuario": usuario.usuario,
                        "senha": usuario.senha,
                        "face_embedding": usuario.face_embedding,
                        "email": usuario.email,
                        "cargo": usuario.cargo
                    }
            except Exception:
                continue

        return melhor_usuario, melhor_score
    except Exception as e:
        st.error(f"Erro na busca biometrica: {str(e)[:100]}")
        return None, 0.0
    finally:
        session.close()

def inserir_usuario_robusto(dados):
    """Tenta inserir usuario no banco via SQLAlchemy."""
    session = get_db_session()
    if not session:
        return False, "Banco nao disponivel"
    try:
        novo = Usuario(
            nome=dados.get("nome"),
            usuario=dados.get("usuario"),
            senha=dados.get("senha"),
            face_embedding=dados.get("face_embedding"),
            email=dados.get("email"),
            cargo=dados.get("cargo")
        )
        session.add(novo)
        session.commit()
        return True, {"id": novo.id}
    except Exception as e:
        session.rollback()
        return False, str(e)[:200]
    finally:
        session.close()

# ============================================================
# PAINEL DE AUTENTICACAO (LOGIN + CADASTRO)
# ============================================================
if not st.session_state.autenticado:
    st.markdown("""
        <div style='text-align: center; margin-top: 30px; margin-bottom: 20px;'>
            <h1 style='color:#0284C7; font-size: 32px;'>📸 Identificacao Biometrica Estel</h1>
            <p style='color:#64748B; font-size: 16px;'>Escolha uma forma de acesso ao sistema.</p>
        </div>
    """, unsafe_allow_html=True)

    if not DB_AVAILABLE:
        st.warning(f"⚠️ Banco de dados indisponivel: {db_error_msg}")
        st.info("💡 O sistema funcionara em modo local com login de contingencia.")

    c_esq, c_centro, c_dir = st.columns([1, 1.4, 1])

    with c_centro:

        # ============================================================
        # ABA 1: LOGIN POR BIOMETRIA
        # ============================================================
        st.markdown("""
        <div style="background: #F0F9FF; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #0284C7;">
            <b>🔐 Opcao 1: Login por Biometria Facial</b><br>
            <small>Tire uma foto ou faca upload do seu rosto</small>
        </div>
        """, unsafe_allow_html=True)

        tab_cam, tab_upload = st.tabs(["📷 Camera", "📁 Upload de Foto"])
        foto_captura = None

        with tab_cam:
            st.info("💡 Dicas: Boa iluminacao frontal, rosto centralizado, sem oculos escuros")
            foto_captura = st.camera_input("Scanner Facial Ativo:", key="scan_facial_posto_unico")

        with tab_upload:
            st.info("💡 Fotos da galeria geralmente tem melhor qualidade")
            foto_upload = st.file_uploader("Selecione uma foto do rosto:", type=["jpg", "jpeg", "png"], key="upload_foto_login")
            if foto_upload:
                foto_captura = foto_upload
                st.image(foto_upload, caption="Foto selecionada", width=200)

        if foto_captura:
            with st.spinner("🔍 Analisando biometria..."):
                vetor_atual = processar_biometria(foto_captura)

                if vetor_atual is not None:
                    if DB_AVAILABLE:
                        usuario_encontrado, score = buscar_usuario_por_biometria(vetor_atual)

                        if usuario_encontrado and score > 0.70:
                            st.success(f"✅ Bem-vindo, {usuario_encontrado['nome']}!")
                            st.info(f"📊 Score de confianca: {score:.1%}")
                            st.session_state.autenticado = True
                            st.session_state.usuario_nome = usuario_encontrado["nome"]
                            st.session_state.usuario_id = usuario_encontrado.get("id")
                            time.sleep(1)
                            safe_rerun()
                        else:
                            st.warning("👤 Rosto nao reconhecido na base.")
                            if score > 0:
                                st.caption(f"📊 Melhor score: {score:.1%} (minimo: 70%)")
                            st.info("💡 Use a **Opcao 2** (Login com Senha) ou **Opcao 3** (Cadastrar-se).")
                            st.session_state.temp_face_vector = vetor_atual
                    else:
                        st.warning("⚠️ Banco de dados indisponivel. Biometria desativada.")
                        st.info("💡 Use a **Opcao 2** (Login com Senha) ou modo offline.")
                else:
                    st.error("⚠️ Nao foi possivel detectar o rosto.")
                    st.info("💡 Use a **Opcao 2** (Login com Senha).")

        # ============================================================
        # DIVISOR
        # ============================================================
        st.markdown('<div class="divider">OU</div>', unsafe_allow_html=True)

        # ============================================================
        # ABA 2: LOGIN COM USUARIO E SENHA
        # ============================================================
        st.markdown("""
        <div style="background: #F0FDF4; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #22C55E;">
            <b>🔑 Opcao 2: Login com Usuario e Senha</b><br>
            <small>Digite suas credenciais cadastradas</small>
        </div>
        """, unsafe_allow_html=True)

        with st.container():
            col_u, col_s = st.columns(2)
            with col_u:
                login_user = st.text_input("👤 Usuario:", placeholder="Digite seu login", key="login_user")
            with col_s:
                login_pass = st.text_input("🔒 Senha:", type="password", placeholder="Digite sua senha", key="login_pass")

            col_btn1, col_btn2 = st.columns([1, 1])
            with col_btn1:
                if st.button("🔓 Entrar", type="primary", use_container_width=True):
                    if login_user and login_pass:
                        if DB_AVAILABLE:
                            user = buscar_usuario_por_credenciais(login_user, login_pass)
                            if user:
                                st.success(f"✅ Bem-vindo, {user['nome']}!")
                                st.session_state.autenticado = True
                                st.session_state.usuario_nome = user["nome"]
                                st.session_state.usuario_id = user.get("id")
                                time.sleep(1)
                                safe_rerun()
                            else:
                                st.error("❌ Usuario ou senha incorretos.")
                                st.info("💡 Se nao tem cadastro, use a **Opcao 3** abaixo.")
                        else:
                            if login_user == "admin" and login_pass == "admin":
                                st.success("✅ Login de contingencia realizado!")
                                st.session_state.autenticado = True
                                st.session_state.usuario_nome = "Supervisor Local"
                                time.sleep(1)
                                safe_rerun()
                            else:
                                st.error("❌ Modo offline. Use admin/admin ou cadastre-se no banco.")
                    else:
                        st.warning("⚠️ Preencha usuario e senha.")

            with col_btn2:
                if st.button("🆘 Esqueci a Senha", use_container_width=True):
                    st.info("📧 Entre em contato com o administrador para redefinir sua senha.")

        # ============================================================
        # DIVISOR 2
        # ============================================================
        st.markdown('<div class="divider">OU</div>', unsafe_allow_html=True)

        # ============================================================
        # ABA 3: CADASTRAR-SE
        # ============================================================
        st.markdown("""
        <div style="background: #FEF3C7; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #F59E0B;">
            <b>📝 Opcao 3: Cadastrar-se no Sistema</b><br>
            <small>Crie sua conta com biometria ou apenas com login/senha</small>
        </div>
        """, unsafe_allow_html=True)

        if st.button("📋 Quero me Cadastrar", use_container_width=True):
            st.session_state.mostrar_cadastro = not st.session_state.mostrar_cadastro
            safe_rerun()

        if st.session_state.mostrar_cadastro:
            with st.container():
                st.markdown('<div class="cadastro-box">', unsafe_allow_html=True)

                st.subheader("📝 Novo Cadastro")

                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    cad_nome = st.text_input("Nome Completo:", placeholder="Ex: Joao Silva", key="cad_nome")
                    cad_user = st.text_input("Usuario (login):", placeholder="Ex: joao.silva", key="cad_user")
                with col_c2:
                    cad_email = st.text_input("E-mail:", placeholder="joao@email.com", key="cad_email")
                    cad_senha = st.text_input("Senha:", type="password", placeholder="Minimo 4 caracteres", key="cad_senha")

                cad_cargo = st.selectbox("Cargo:", ["Operador", "Supervisor", "Administrador"], key="cad_cargo")

                st.markdown("---")
                usar_biometria = st.checkbox("✅ Incluir biometria facial no cadastro (recomendado)", value=True, key="usar_bio")

                vetor_cadastro = None
                if usar_biometria:
                    st.info("📸 Tire uma foto do seu rosto para vincular a conta")
                    foto_cad = st.camera_input("Foto para cadastro:", key="cam_cadastro")
                    if foto_cad:
                        with st.spinner("Processando biometria..."):
                            vetor_cadastro = processar_biometria(foto_cad)
                            if vetor_cadastro:
                                st.success("✅ Biometria capturada com sucesso!")
                            else:
                                st.warning("⚠️ Nao foi possivel capturar a biometria. Voce pode cadastrar sem ela.")

                if st.button("💾 Salvar Cadastro", type="primary", use_container_width=True):
                    if cad_nome and cad_user and cad_senha:
                        if len(cad_senha) < 4:
                            st.error("❌ A senha deve ter pelo menos 4 caracteres.")
                        else:
                            if DB_AVAILABLE:
                                try:
                                    session = get_db_session()
                                    existente = session.query(Usuario).filter(Usuario.usuario == cad_user).first()
                                    session.close()
                                    if existente:
                                        st.error(f"❌ O usuario '{cad_user}' ja existe. Escolha outro.")
                                    else:
                                        dados_insert = {
                                            "nome": cad_nome,
                                            "usuario": cad_user,
                                            "senha": cad_senha
                                        }
                                        if cad_email:
                                            dados_insert["email"] = cad_email
                                        if cad_cargo:
                                            dados_insert["cargo"] = cad_cargo
                                        if vetor_cadastro:
                                            dados_insert["face_embedding"] = json.dumps(vetor_cadastro)

                                        sucesso, resultado = inserir_usuario_robusto(dados_insert)

                                        if sucesso:
                                            st.success("🎉 Cadastro realizado com sucesso!")
                                            st.info("✅ Agora voce pode fazer login com seu usuario e senha.")
                                            st.session_state.mostrar_cadastro = False
                                            time.sleep(2)
                                            safe_rerun()
                                        else:
                                            st.error(f"❌ Erro ao cadastrar: {resultado}")
                                            st.info("💡 Tente novamente ou use o modo offline (admin/admin).")
                                except Exception as e:
                                    st.error(f"❌ Erro: {e}")
                            else:
                                st.error("❌ Banco de dados indisponivel. Nao e possivel cadastrar no momento.")
                                st.info("💡 Use o login de contingencia: admin / admin")
                    else:
                        st.error("❌ Preencha Nome, Usuario e Senha.")

                st.markdown('</div>', unsafe_allow_html=True)

        if not DB_AVAILABLE:
            st.markdown("---")
            st.caption("🟡 Sistema em modo offline. Login de contingencia: **admin / admin**")

# ============================================================
# PAINEL PRINCIPAL
# ============================================================
else:
    cab_esquerdo, cab_direito = st.columns([4, 1])
    cab_esquerdo.markdown(f"<h1>🚚 Validador de Retornos de Obra</h1>", unsafe_allow_html=True)
    cab_esquerdo.caption(f"Operador: **{st.session_state.usuario_nome}** | {'🟢 Online' if DB_AVAILABLE else '🟡 Offline'}")

    if cab_direito.button("🚪 Sair", key="logout"):
        st.session_state.autenticado = False
        st.session_state.dados_conferencia = pd.DataFrame()
        st.session_state.fotos_postadas = {}
        st.session_state.item_selecionado_idx = None
        st.session_state.mostrar_cadastro = False
        safe_rerun()

    st.markdown("---")

    # SIDEBAR
    with st.sidebar:
        st.header("📥 Carregar Documentos")

        # ---- MEMORIA PERSISTENTE: OBRA/PARADA ----
        st.markdown("---")
        st.subheader("📍 Obra / Parada")
        obra_input = st.text_input(
            "Informe a Obra ou Parada em auditoria:",
            value=st.session_state.get("obra_parada", ""),
            placeholder="Ex: Obra Centro - Parada 03",
            key="obra_parada_input"
        )
        if obra_input != st.session_state.get("obra_parada", ""):
            st.session_state.obra_parada = obra_input
            salvar_config({"obra_parada": obra_input})

        if st.session_state.get("obra_parada"):
            st.success(f"✅ Obra/Parada: {st.session_state.obra_parada}")
        st.markdown("---")
        # ------------------------------------------

        libs_status = []
        if FITZ_AVAILABLE:
            libs_status.append("✅ PyMuPDF")
        if PYPDF_AVAILABLE:
            libs_status.append("✅ PyPDF")
        if PDFMINER_AVAILABLE:
            libs_status.append("✅ PDFMiner")
        if not libs_status:
            libs_status.append("⚠️ Nenhuma lib PDF detectada")

        st.caption(" | ".join(libs_status))

        arquivos_entrada = st.file_uploader(
            "Arraste DANFEs (PDF) ou planilhas:",
            type=["pdf", "xlsx", "xls", "csv"],
            accept_multiple_files=True
        )

        if arquivos_entrada:
            if st.button("⚡ Processar Carga em Lote", type="primary"):
                all_records = []
                arquivos_processados = 0
                arquivos_com_erro = []

                with st.spinner("Lendo documentos..."):
                    for arq in arquivos_entrada:
                        try:
                            if arq.name.lower().endswith(".pdf"):
                                regs = extrair_linhas_danfe(arq)
                                if regs:
                                    all_records.extend(regs)
                                    arquivos_processados += 1
                                else:
                                    arquivos_com_erro.append(f"{arq.name} (sem dados extraidos)")
                            else:
                                regs = extrair_linhas_excel(arq)
                                if regs:
                                    all_records.extend(regs)
                                    arquivos_processados += 1
                                else:
                                    arquivos_com_erro.append(f"{arq.name} (sem dados extraidos)")
                        except Exception as e:
                            arquivos_com_erro.append(f"{arq.name} ({str(e)[:50]})")

                    if all_records:
                        with st.spinner("Consolidando dados..."):
                            registros_consolidados = consolidar_registros(all_records)
                            df_novo = pd.DataFrame(registros_consolidados)
                            total_original = len(all_records)
                            total_consolidado = len(df_novo)
                            itens_removidos = total_original - total_consolidado
                            st.session_state.dados_conferencia = df_novo

                            st.success(f"📊 {total_consolidado} itens carregados de {arquivos_processados} arquivo(s)!")
                            if itens_removidos > 0:
                                st.info(f"{total_original} brutos → {itens_removidos} consolidados → {total_consolidado} unicos")

                            if arquivos_com_erro:
                                st.warning(f"⚠️ {len(arquivos_com_erro)} arquivo(s) nao retornaram dados:")
                                for err in arquivos_com_erro[:3]:
                                    st.caption(f"- {err}")

                            divergencias = [r for r in registros_consolidados if "divergentes" in r.get("Observacoes", "")]
                            if divergencias:
                                st.warning(f"⚠️ {len(divergencias)} item(s) com quantidades divergentes foram SOMADOS.")
                        safe_rerun()
                    else:
                        st.error("❌ Nenhum item foi extraido dos documentos.")
                        st.info("💡 Verifique se os PDFs sao DANFEs ou se as planilhas tem colunas de descricao e quantidade.")

        # ============================================================
        # EXPORTACAO EM EXCEL + PDF PROFISSIONAL
        # ============================================================
        if not st.session_state.dados_conferencia.empty:
            st.markdown("---")
            st.header("📤 Exportar Relatorio")

            df_export = st.session_state.dados_conferencia.copy()

            # --- LIMPEZA: DROP DUPLICADAS (DESCRICAO + QTD NF) ---
            if "Descricao do Produto" in df_export.columns and "Quantidade NF" in df_export.columns:
                antes = len(df_export)
                df_export = df_export.drop_duplicates(
                    subset=["Descricao do Produto", "Quantidade NF"],
                    keep="first"
                ).reset_index(drop=True)
                depois = len(df_export)
                if depois < antes:
                    st.caption(f"🧹 {antes - depois} duplicata(s) removida(s) na exportacao")
            # -------------------------------------------------------

            try:
                memoria_excel = io.BytesIO()
                with pd.ExcelWriter(memoria_excel, engine='openpyxl') as writer:
                    df_export.to_excel(writer, index=False, sheet_name="Consolidado")

                    resumo_data = {
                        'Metrica': [
                            'Total de Itens',
                            'Conformes',
                            'Divergentes',
                            'Pendentes',
                            'Com Foto',
                            'Operador',
                            'Obra/Parada',
                            'Data/Hora'
                        ],
                        'Valor': [
                            len(df_export),
                            len(df_export[df_export["Situacao"] == "Conforme"]),
                            len(df_export[df_export["Situacao"] == "Divergente"]),
                            len(df_export[df_export["Situacao"] == "Pendente"]),
                            len(df_export[df_export["Foto Capturada"] == "Sim"]),
                            st.session_state.usuario_nome,
                            st.session_state.get("obra_parada", "Nao informada"),
                            time.strftime("%Y-%m-%d %H:%M:%S")
                        ]
                    }
                    pd.DataFrame(resumo_data).to_excel(writer, index=False, sheet_name="Resumo")

                st.download_button(
                    label="💾 Exportar Excel (.xlsx)",
                    data=memoria_excel.getvalue(),
                    file_name=f"Relatorio_Estel_{time.strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"❌ Erro ao gerar Excel: {str(e)[:100]}")
                st.info("💡 Tente instalar: pip install openpyxl")

            # --- EXPORTACAO PDF PROFISSIONAL ---
            try:
                from reportlab.lib import colors
                from reportlab.lib.pagesizes import A4, landscape
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib.units import cm
                from reportlab.pdfgen import canvas
                from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

                def gerar_pdf_profissional():
                    buffer = io.BytesIO()
                    doc = SimpleDocTemplate(
                        buffer,
                        pagesize=A4,
                        rightMargin=1.5*cm,
                        leftMargin=1.5*cm,
                        topMargin=2*cm,
                        bottomMargin=1.5*cm
                    )
                    elements = []
                    styles = getSampleStyleSheet()

                    titulo_style = ParagraphStyle(
                        'TituloRelatorio',
                        parent=styles['Heading1'],
                        fontSize=18,
                        textColor=colors.HexColor("#0284C7"),
                        alignment=TA_CENTER,
                        spaceAfter=16,
                        fontName="Helvetica-Bold"
                    )
                    subtitulo_style = ParagraphStyle(
                        'SubtituloRelatorio',
                        parent=styles['Normal'],
                        fontSize=10,
                        textColor=colors.HexColor("#64748B"),
                        alignment=TA_CENTER,
                        spaceAfter=20
                    )
                    header_style = ParagraphStyle(
                        'HeaderStyle',
                        parent=styles['Normal'],
                        fontSize=9,
                        textColor=colors.white,
                        alignment=TA_CENTER,
                        fontName="Helvetica-Bold"
                    )
                    cell_style = ParagraphStyle(
                        'CellStyle',
                        parent=styles['Normal'],
                        fontSize=8,
                        textColor=colors.HexColor("#1E293B"),
                        alignment=TA_LEFT
                    )
                    cell_center_style = ParagraphStyle(
                        'CellCenterStyle',
                        parent=styles['Normal'],
                        fontSize=8,
                        textColor=colors.HexColor("#1E293B"),
                        alignment=TA_CENTER
                    )

                    elements.append(Paragraph("RELATORIO DE CONFERENCIA DE MATERIAIS", titulo_style))
                    elements.append(Paragraph(
                        f"Obra/Parada: <b>{st.session_state.get('obra_parada', 'Nao informada')}</b> | "
                        f"Operador: <b>{st.session_state.usuario_nome}</b> | "
                        f"Data: {time.strftime('%d/%m/%Y %H:%M')}",
                        subtitulo_style
                    ))
                    elements.append(Spacer(1, 12))

                    # Tabela de dados
                    headers = ["#", "Descricao do Produto", "Qtd NF", "Conferida", "Situacao", "Foto", "Observacoes"]
                    data = [headers]

                    for idx, row in df_export.iterrows():
                        situacao = str(row.get("Situacao", "Pendente"))
                        situacao_color = {
                            "Conforme": "#166534",
                            "Divergente": "#991B1B",
                            "Pendente": "#92400E",
                            "Aprovado": "#166534",
                            "Reparo": "#92400E",
                            "Avaria": "#991B1B"
                        }.get(situacao, "#1E293B")

                        data.append([
                            str(idx + 1),
                            Paragraph(str(row.get("Descricao do Produto", ""))[:80], cell_style),
                            str(row.get("Quantidade NF", "")),
                            str(row.get("Quantidade Conferida", "")),
                            Paragraph(f'<font color="{situacao_color}"><b>{situacao}</b></font>', cell_center_style),
                            str(row.get("Foto Capturada", "Nao")),
                            Paragraph(str(row.get("Observacoes", ""))[:100], cell_style)
                        ])

                    tabela = Table(data, colWidths=[0.8*cm, 7*cm, 1.8*cm, 1.8*cm, 2.2*cm, 1.5*cm, 4.5*cm], repeatRows=1)
                    tabela.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284C7")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 9),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F8FAFC")),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F1F5F9")]),
                        ("FONTSIZE", (0, 1), (-1, -1), 8),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("TOPPADDING", (0, 1), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                    ]))
                    elements.append(tabela)
                    elements.append(Spacer(1, 20))

                    # Rodape
                    totais_style = ParagraphStyle(
                        'TotaisStyle',
                        parent=styles['Normal'],
                        fontSize=9,
                        textColor=colors.HexColor("#475569"),
                        alignment=TA_LEFT
                    )
                    total = len(df_export)
                    conformes = len(df_export[df_export["Situacao"] == "Conforme"])
                    divergentes = len(df_export[df_export["Situacao"] == "Divergente"])
                    pendentes = len(df_export[df_export["Situacao"] == "Pendente"])
                    com_foto = len(df_export[df_export["Foto Capturada"] == "Sim"])

                    elements.append(Paragraph(
                        f"<b>Resumo:</b> {total} itens totais | "
                        f"<font color='#166534'>{conformes} Conforme(s)</font> | "
                        f"<font color='#991B1B'>{divergentes} Divergente(s)</font> | "
                        f"<font color='#92400E'>{pendentes} Pendente(s)</font> | "
                        f"{com_foto} com Foto",
                        totais_style
                    ))

                    doc.build(elements)
                    return buffer.getvalue()

                if st.button("📄 Gerar Relatorio PDF", use_container_width=True):
                    with st.spinner("Gerando PDF profissional..."):
                        pdf_bytes = gerar_pdf_profissional()
                        st.download_button(
                            label="⬇️ Baixar PDF",
                            data=pdf_bytes,
                            file_name=f"Relatorio_Estel_{time.strftime('%Y%m%d_%H%M%S')}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
            except ImportError:
                st.caption("📄 Instale `reportlab` para gerar PDFs: `pip install reportlab`")
            except Exception as e:
                st.error(f"Erro ao gerar PDF: {str(e)[:100]}")
            # -----------------------------------

            if st.button("🗑️ Limpar Tudo", use_container_width=True):
                st.session_state.dados_conferencia = pd.DataFrame()
                st.session_state.fotos_postadas = {}
                st.session_state.item_selecionado_idx = None
                safe_rerun()

    # CONTEUDO PRINCIPAL
    if st.session_state.dados_conferencia.empty:
        st.info("💡 **Dica:** Carregue notas fiscais no menu a esquerda para iniciar.")
    else:
        aba_triagem, aba_tabela, aba_dashboard = st.tabs([
            "📸 Posto de Triagem",
            "📋 Lista Consolidada",
            "📊 Dashboard"
        ])

        # ============================================================
        # ABA TRIAGEM (COM MELHORIAS)
        # ============================================================
        with aba_triagem:
            df_ref = st.session_state.dados_conferencia

            st.markdown("""
            <div class="busca-container">
                <b>🔍 Busca Inteligente de Insumos</b><br>
                <small>Digite parte do nome, codigo ou descricao. A busca e <b>dinamica</b> e procura em todos os campos.</small>
            </div>
            """, unsafe_allow_html=True)

            termo_busca = st.text_input(
                "Buscar produto:",
                value=st.session_state.get("busca_termo", ""),
                placeholder="Ex: chave combinada, cimento, parafuso...",
                key="busca_produto"
            ).strip()

            if termo_busca != st.session_state.get("busca_termo", ""):
                st.session_state.busca_termo = termo_busca
                st.session_state.item_selecionado_idx = None
                safe_rerun()

            df_resultado, indices_resultado = buscar_itens_inteligente(df_ref, termo_busca)

            arquivos_unicos = df_ref['Arquivo Origem'].unique()
            if len(arquivos_unicos) > 1:
                arquivo_filtro = st.selectbox(
                    "📁 Filtrar por Arquivo/NF:",
                    ["Todos os arquivos"] + list(arquivos_unicos),
                    key="filtro_arquivo"
                )
                if arquivo_filtro != "Todos os arquivos":
                    df_resultado = df_resultado[df_resultado['Arquivo Origem'].str.contains(arquivo_filtro, na=False)]

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

            # ---- FORMATACAO LIMPA DO SELECTBOX ----
            opcoes_resultado = []
            for _, row in df_resultado.iterrows():
                sit = row.get('Situacao', 'Pendente')
                arq = str(row.get('Arquivo Origem', ''))[:20]
                desc = str(row.get('Descricao do Produto', ''))[:45]
                qtd = row.get('Quantidade NF', 0)
                opcoes_resultado.append(f"{sit:.<12} {arq:.<22} {desc} (Qtd: {qtd})")

            if opcoes_resultado:
                idx_selecionado = st.selectbox(
                    "Selecione o insumo para conferencia:",
                    range(len(opcoes_resultado)),
                    format_func=lambda i: opcoes_resultado[i],
                    key="select_item"
                )

                if indices_resultado:
                    idx_real = indices_resultado[idx_selecionado]
                else:
                    idx_real = df_resultado.index[idx_selecionado]

                st.session_state.item_selecionado_idx = idx_real

                linha = df_ref.loc[idx_real]

                status_class = {
                    "Pendente": "status-pendente",
                    "Conforme": "status-conforme",
                    "Divergente": "status-divergente",
                    "Aprovado": "status-aprovado",
                    "Reparo": "status-reparo",
                    "Avaria": "status-avaria"
                }.get(linha['Situacao'], "status-pendente")

                st.markdown(f"""
                <div class='card-conferencia'>
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <span style='color:#64748B; font-size:13px;'>📄 {linha['Arquivo Origem']}</span>
                        <span class="status-badge {status_class}">{linha['Situacao']}</span>
                    </div>
                    <h3 style='color:#0284C7; margin:0; font-size:18px;'>{linha['Descricao do Produto']}</h3>
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
                            <div style="font-size:20px; font-weight:700; color="#{'22C55E' if linha['Foto Capturada'] == 'Sim' else 'EF4444'};">
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
                        "Notas / Divergencias:",
                        value=linha['Observacoes'],
                        key=f"obs_{idx_real}"
                    )

                    # ---- CLASSIFICACAO DO MATERIAL: APROVADO / REPARO / AVARIA ----
                    st.markdown("**🎯 Classificacao do Estado do Material:**")
                    classificacao = st.radio(
                        "Selecione a classificacao:",
                        options=["Aprovado", "Reparo", "Avaria"],
                        horizontal=True,
                        key=f"classif_{idx_real}",
                        label_visibility="collapsed"
                    )

                    col_btn1, col_btn2, col_btn3 = st.columns(3)
                    with col_btn1:
                        if st.button("✅ Confirmar", type="primary", key=f"conf_ok_{idx_real}"):
                            st.session_state.dados_conferencia.at[idx_real, "Quantidade Conferida"] = linha['Quantidade NF']
                            obs_final = f"{obs} | Classificacao: {classificacao}".strip(" |") if obs else f"Classificacao: {classificacao}"
                            st.session_state.dados_conferencia.at[idx_real, "Observacoes"] = obs_final
                            st.session_state.dados_conferencia.at[idx_real, "Situacao"] = "Conforme"
                            st.toast(f"✅ Item confirmado como Conforme - {classificacao}!")
                            safe_rerun()

                    with col_btn2:
                        if st.button("✏️ Atualizar", key=f"conf_div_{idx_real}"):
                            st.session_state.dados_conferencia.at[idx_real, "Quantidade Conferida"] = qtd_conf
                            obs_final = f"{obs} | Classificacao: {classificacao}".strip(" |") if obs else f"Classificacao: {classificacao}"
                            st.session_state.dados_conferencia.at[idx_real, "Observacoes"] = obs_final
                            st.session_state.dados_conferencia.at[idx_real, "Situacao"] = "Divergente"
                            st.toast(f"⚠️ Divergencia registrada - {classificacao}!")
                            safe_rerun()

                    with col_btn3:
                        if st.button("💾 Gravar no Banco", key=f"save_{idx_real}"):
                            st.session_state.dados_conferencia.at[idx_real, "Quantidade Conferida"] = qtd_conf
                            obs_final = f"{obs} | Classificacao: {classificacao}".strip(" |") if obs else f"Classificacao: {classificacao}"
                            st.session_state.dados_conferencia.at[idx_real, "Observacoes"] = obs_final
                            situacao_final = "Conforme" if qtd_conf == linha['Quantidade NF'] else "Divergente"
                            st.session_state.dados_conferencia.at[idx_real, "Situacao"] = situacao_final

                            # ---- BLOCO 3: INSERT VIA SQLALCHEMY ----
                            session = get_db_session()
                            if session and DB_AVAILABLE:
                                try:
                                    novo_item = ConferenciaItem(
                                        operador=st.session_state.usuario_nome,
                                        usuario_id=st.session_state.usuario_id,
                                        nome_arquivo=linha['Arquivo Origem'],
                                        descricao_produto=linha['Descricao do Produto'],
                                        quantidade_nf=float(linha['Quantidade NF']),
                                        quantidade_conferida=float(qtd_conf),
                                        situacao=situacao_final,
                                        observacoes=obs_final,
                                        data_hora=time.strftime("%Y-%m-%d %H:%M:%S"),
                                        obra_parada=st.session_state.get("obra_parada", "")
                                    )
                                    session.add(novo_item)
                                    session.commit()
                                    st.toast("💾 Dados gravados no CockroachDB!")
                                except Exception as e:
                                    session.rollback()
                                    st.error(f"Erro ao sincronizar: {e}")
                                finally:
                                    session.close()
                            safe_rerun()
                    # ---------------------------------------------------------------
            else:
                st.warning("Nenhum item disponivel para selecao.")

        # ============================================================
        # ABA TABELA
        # ============================================================
        with aba_tabela:
            df = st.session_state.dados_conferencia

            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                filtro_status = st.multiselect("Filtrar por Status:", ["Pendente", "Conforme", "Divergente"], default=[])
            with col_f2:
                filtro_arquivo = st.multiselect("Filtrar por Arquivo:", df['Arquivo Origem'].unique(), default=[])
            with col_f3:
                filtro_foto = st.selectbox("Com Foto:", ["Todos", "Sim", "Nao"])

            df_filtrado = df.copy()
            if filtro_status:
                df_filtrado = df_filtrado[df_filtrado["Situacao"].isin(filtro_status)]
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
