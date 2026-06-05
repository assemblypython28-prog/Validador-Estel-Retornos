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

/* Inspeção Checklist CSS */
.inspecao-container { background: #F8FAFC; border: 1px dashed #CBD5E1; padding: 14px; border-radius: 8px; margin-top: 10px; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# CONEXAO COM BANCO DE DADOS (SUPABASE)
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
            test = supabase.table("usuarios").select("id").limit(1).execute()
            SUPABASE_AVAILABLE = True
        except Exception as e:
            if "does not exist" in str(e).lower() or "relation" in str(e).lower():
                SUPABASE_AVAILABLE = True
                supabase_error_msg = "Tabela 'usuarios' não encontrada."
            else:
                supabase_error_msg = f"Erro: {str(e)[:80]}"
    except Exception as e:
        supabase_error_msg = f"Falha: {str(e)[:80]}"
        SUPABASE_AVAILABLE = False

init_supabase()

# Session State Inicializações
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
# PERSISTENCIA LOCAL DE DADOS (COOKIES / LOCALSTORAGE MOCK VIA QUERY PARAMS PARA RESILIENCIA)
# ============================================================
if "local_obra_selecionada" not in st.session_state:
    q_params = st.query_params
    if "obra_persistida" in q_params:
        st.session_state.local_obra_selecionada = q_params["obra_persistida"]
    else:
        st.session_state.local_obra_selecionada = "Parada Geral Fibria 2026"

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
# EXTRACAO E CONSOLIDACAO DE REGISTROS (COM REMOCAO DE DUPLICADOS)
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
    return texto

def consolidar_registros(registros):
    if not registros:
        return []
    
    df_temp = pd.DataFrame(registros)
    
    # REGRA ADICIONADA: Se os dados tiverem duplicado a mesma informação e mesma quantidade, excluir duplicados.
    df_temp = df_temp.drop_duplicates(subset=["Descrição do Produto", "Quantidade NF"], keep="first")
    
    grupos = {}
    for _, reg in df_temp.iterrows():
        chave = reg["Descrição do Produto"].strip().upper()
        if chave not in grupos:
            grupos[chave] = {"registros": [], "arquivos_origem": set(), "quantidades": []}
        grupos[chave]["registros"].append(reg.to_dict())
        grupos[chave]["arquivos_origem"].add(reg["Arquivo Origem"])
        grupos[chave]["quantidades"].append(reg["Quantidade NF"])

    registros_consolidados = []
    for chave, dados in grupos.items():
        qtds = dados["quantidades"]
        arquivos = sorted(dados["arquivos_origem"])
        if len(set(qtds)) == 1:
            reg_base = dados["registros"][0].copy()
            reg_base["Arquivo Origem"] = " | ".join(arquivos)
            reg_base["Observações"] = f"Item unificado está pronto."
            registros_consolidados.append(reg_base)
        else:
            qtd_total = sum(qtds)
            reg_base = dados["registros"][0].copy()
            reg_base["Quantidade NF"] = qtd_total
            reg_base["Arquivo Origem"] = " | ".join(arquivos)
            reg_base["Observações"] = f"Quantidades unificadas ({len(arquivos)} doc). Total: {qtd_total}."
            registros_consolidados.append(reg_base)
            
    return registros_consolidados

def extrair_linhas_danfe(pdf_file):
    registros = []
    try:
        pdf_bytes = pdf_file.read()
        pdf_file.seek(0)

        if not FITZ_AVAILABLE:
            full_text = extrair_texto_pdf(pdf_bytes)
            if not full_text: return []
            return _extrair_danfe_por_texto(full_text, pdf_file.name)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_num in range(len(doc)):
            page = doc[page_num]
            try:
                tables = page.find_tables()
                if tables and tables.tables:
                    for table in tables.tables:
                        rows = table.extract()
                        if not rows: continue
                        header = [str(c).strip().upper() if c else "" for c in rows[0]]
                        idx_desc, idx_qtd = None, None
                        for i, h in enumerate(header):
                            h_clean = re.sub(r'[^A-ZÇÃÕÁÉÍÓÚÂÊÎÔÛÄËÏÖÜ]', '', h)
                            if any(k in h_clean for k in ["DESCRI", "PRODUTO", "PRODUTOSERVICO"]): idx_desc = i
                            if any(k in h_clean for k in ["QTD", "QUANT", "QTDE", "QUANTIDADE"]): idx_qtd = i

                        if idx_desc is None and len(header) > 1: idx_desc = 1
                        if idx_qtd is None and len(header) > 2: idx_qtd = 2

                        for row in rows[1:]:
                            if not row or len(row) < 2: continue
                            desc = ""
                            qtd = 1.0
                            if idx_desc is not None and idx_desc < len(row):
                                desc = str(row[idx_desc]).strip()
                                desc = re.sub(r'^\d+\s+', '', desc)
                                desc = re.sub(r'^\d+', '', desc).strip()
                            if idx_qtd is not None and idx_qtd < len(row):
                                qtd_str = str(row[idx_qtd]).strip().replace('.', '').replace(',', '.')
                                try: qtd = float(qtd_str) if qtd_str else 1.0
                                except: qtd = 1.0

                            if desc and len(desc) > 3 and not desc.isdigit():
                                registros.append({
                                    "Arquivo Origem": pdf_file.name,
                                    "Descrição do Produto": desc.upper(),
                                    "Quantidade NF": qtd,
                                    "Quantidade Conferida": 0.0,
                                    "Situação": "Pendente",
                                    "Inspeção Técnica": "Aprovado/Operacional",
                                    "Foto Capturada": "Não",
                                    "Observações": ""
                                })
                    continue
            except Exception: pass
            page_text = page.get_text("text")
            if page_text.strip():
                registros.extend(_extrair_danfe_por_texto(page_text, pdf_file.name))
        doc.close()
    except Exception as e:
        st.error(f"❌ Erro ao processar PDF: {str(e)[:100]}")
    return registros

def _extrair_danfe_por_texto(full_text, nome_arquivo):
    registros = []
    linhas = full_text.split("\n")
    modo_captura = False
    for linha in linhas:
        linha = linha.strip()
        if not linha: continue
        if re.search(r'C\.D(\.)?\s*PROD|DESCRI\.O\s*DO|CÓDIGO\s*PRODUTO', linha, re.IGNORECASE):
            modo_captura = True
            continue
        if re.search(r'C\.LCULO\s*DO\s*ISSQN|DADOS\s*ADICIONAIS', linha, re.IGNORECASE):
            modo_captura = False
            continue
        if modo_captura:
            numeros = re.findall(r'\b\d+[\d.,]*\b', linha)
            desc = re.sub(r'^\d+\s+', '', linha)
            desc = re.sub(r'\s*\d+[\d.,]*.*$', '', desc).strip()
            if len(desc) > 3 and not desc.isdigit():
                qtd = 1.0
                if numeros:
                    for num_str in numeros:
                        num_limpa = num_str.replace('.', '').replace(',', '.')
                        try:
                            val = float(num_limpa)
                            if 0 < val < 100000:
                                qtd = val
                                break
                        except: continue
                registros.append({
                    "Arquivo Origem": nome_arquivo,
                    "Descrição do Produto": desc.upper(),
                    "Quantidade NF": qtd,
                    "Quantidade Conferida": 0.0,
                    "Situação": "Pendente",
                    "Inspeção Técnica": "Aprovado/Operacional",
                    "Foto Capturada": "Não",
                    "Observações": ""
                })
    return registros

def extrair_linhas_excel(excel_file):
    registros = []
    try:
        df_cru = pd.read_csv(excel_file, encoding='latin1') if excel_file.name.endswith('.csv') else pd.read_excel(excel_file)
        if df_cru.empty: return []
        colunas = [c.upper() for c in df_cru.columns]
        col_desc, col_qtd = None, None
        for i, c in enumerate(colunas):
            if any(kw in c for kw in ["DESCRI", "PRODUTO", "ITEM", "MATERIAL"]): col_desc = df_cru.columns[i]; break
        if col_desc is None: col_desc = df_cru.columns[0]
        for i, c in enumerate(colunas):
            if any(kw in c for kw in ["QTD", "QUANT", "QUANTIDADE"]): col_qtd = df_cru.columns[i]; break
        if col_qtd is None: col_qtd = df_cru.columns[0]

        for _, row in df_cru.iterrows():
            desc_val = str(row[col_desc]).strip().upper()
            if len(desc_val) > 2 and not desc_val.isdigit():
                try: qtd_val = float(pd.to_numeric(row[col_qtd], errors='coerce'))
                except: qtd_val = 1.0
                if np.isnan(qtd_val): qtd_val = 1.0
                registros.append({
                    "Arquivo Origem": excel_file.name,
                    "Descrição do Produto": desc_val,
                    "Quantidade NF": qtd_val,
                    "Quantidade Conferida": 0.0,
                    "Situação": "Pendente",
                    "Inspeção Técnica": "Aprovado/Operacional",
                    "Foto Capturada": "Não",
                    "Observações": ""
                })
    except Exception as e:
        st.error(f"❌ Erro ao processar Planilha: {str(e)[:100]}")
    return registros

# ============================================================
# GERADOR DE PDF E METRICAS DE EXPORTACAO INTELIGENTE
# ============================================================
def gerar_relatorio_pdf_profissional(df, obra_nome):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
    except ImportError:
        st.error("Biblioteca reportlab não instalada. Instale via: pip install reportlab")
        return None

    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor('#0284C7'), spaceAfter=10)
    meta_style = ParagraphStyle('MetaStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#475569'), spaceAfter=15)
    
    story.append(Paragraph("<b>Estel - Relatório Avançado de Retorno de Material</b>", title_style))
    story.append(Paragraph(f"<b>Escopo Operacional:</b> {obra_nome} | <b>Emissão:</b> {time.strftime('%d/%m/%Y %H:%M:%S')}", meta_style))
    story.append(Spacer(1, 12))
    
    dados_tabela = [["PRODUTO", "QTD NF", "CONF.", "SITUAÇÃO", "INSPEÇÃO"]]
    for _, r in df.iterrows():
        dados_tabela.append([
            Paragraph(str(r["Descrição do Produto"])[:45], styles['Normal']),
            str(r["Quantidade NF"]),
            str(r["Quantidade Conferida"]),
            str(r["Situação"]),
            str(r.get("Inspeção Técnica", "Aprovado"))
        ])
    
    t = Table(dados_tabela, colWidths=[240, 55, 55, 80, 100])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0284C7')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#F8FAFC')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t)
    doc.build(story)
    return pdf_buffer.getvalue()

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
        st.markdown(f'<div class="dashboard-card" style="border-top: 4px solid #0284C7;"><div class="dashboard-metric">{total}</div><div class="dashboard-label">Total de Itens</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="dashboard-card" style="border-top: 4px solid #22C55E;"><div class="dashboard-metric" style="color: #22C55E;">{conformes}</div><div class="dashboard-label">Conformes</div><div style="margin-top:8px;"><div class="progress-bar"><div class="progress-fill" style="width:{pct_conforme}%; background:#22C55E;"></div></div><small style="color:#64748B;">{pct_conforme:.1f}%</small></div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="dashboard-card" style="border-top: 4px solid #EF4444;"><div class="dashboard-metric" style="color: #EF4444;">{divergentes}</div><div class="dashboard-label">Divergentes</div><div style="margin-top:8px;"><div class="progress-bar"><div class="progress-fill" style="width:{pct_divergente}%; background:#EF4444;"></div></div><small style="color:#64748B;">{pct_divergente:.1f}%</small></div></div>', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<div class="dashboard-card" style="border-top: 4px solid #F59E0B;"><div class="dashboard-metric" style="color: #F59E0B;">{pendentes}</div><div class="dashboard-label">Pendentes</div><div style="margin-top:8px;"><div class="progress-bar"><div class="progress-fill" style="width:{pct_pendente}%; background:#F59E0B;"></div></div><small style="color:#64748B;">{pct_pendente:.1f}%</small></div></div>', unsafe_allow_html=True)

# ============================================================
# REUSO DE LOGICA DE CADASTRO E LOGIN (INALTERADO)
# ============================================================
def buscar_usuario_por_credenciais(supabase_client, usuario, senha):
    try:
        result = supabase_client.table("usuarios").select("*").eq("usuario", usuario).execute()
        if result.data and len(result.data) > 0:
            user = result.data[0]
            if user.get("senha") == senha: return user
        return None
    except: return None

def buscar_usuario_por_biometria(supabase_client, vetor_atual):
    try:
        result = supabase_client.table("usuarios").select("*").execute()
        if not result.data: return None, 0.0
        melhor_score, melhor_usuario = 0.0, None
        for usuario in result.data:
            face_emb = usuario.get("face_embedding")
            if not face_emb: continue
            vetor_salvo = json.loads(face_emb) if isinstance(face_emb, str) else face_emb
            score = calcular_similaridade(vetor_atual, vetor_salvo)
            if score > melhor_score: melhor_score, melhor_usuario = score, usuario
        return melhor_usuario, melhor_score
    except: return None, 0.0

def inserir_usuario_robusto(supabase_client, dados):
    dados_insert = dados.copy()
    try:
        result = supabase_client.table("usuarios").insert(dados_insert).execute()
        return True, result
    except Exception as e: return False, str(e)

# ============================================================
# PAINEL DE AUTENTICACAO (INALTERADO)
# ============================================================
if not st.session_state.autenticado:
    st.markdown("<div style='text-align: center; margin-top: 30px;'><h1 style='color:#0284C7;'>📸 Identificação Biométrica Estel</h1></div>", unsafe_allow_html=True)
    c_esq, c_centro, c_dir = st.columns([1, 1.4, 1])
    with c_centro:
        tab_cam, tab_upload = st.tabs(["📷 Câmera", "📁 Upload"])
        foto_captura = None
        with tab_cam: foto_captura = st.camera_input("Scanner Facial:")
        with tab_upload:
            fu = st.file_uploader("Escolha foto do rosto:", type=["jpg","png"])
            if fu: foto_captura = fu
        
        if foto_captura:
            v_at = processar_biometria(foto_captura)
            if v_at is not None and SUPABASE_AVAILABLE:
                u, sc = buscar_usuario_por_biometria(supabase, v_at)
                if u and sc > 0.70:
                    st.session_state.autenticado = True
                    st.session_state.usuario_nome = u["nome"]
                    st.session_state.usuario_id = u.get("id")
                    safe_rerun()
        
        st.markdown('<div class="divider">OU</div>', unsafe_allow_html=True)
        login_user = st.text_input("👤 Usuário:", key="l_user")
        login_pass = st.text_input("🔒 Senha:", type="password", key="l_pass")
        if st.button("🔓 Entrar", type="primary"):
            if login_user == "admin" and login_pass == "admin":
                st.session_state.autenticado = True
                st.session_state.usuario_nome = "Supervisor Local"
                safe_rerun()

# ============================================================
# PAINEL PRINCIPAL (SISTEMA LOGADO)
# ============================================================
else:
    cab_esquerdo, cab_direito = st.columns([4, 1])
    cab_esquerdo.markdown(f"<h1>🚚 Validador de Retornos de Obra</h1>", unsafe_allow_html=True)
    cab_esquerdo.caption(f"Operador: **{st.session_state.usuario_nome}** | Contexto ativo")

    if cab_direito.button("🚪 Sair", key="logout"):
        st.session_state.autenticado = False
        safe_rerun()

    # ============================================================
    # SIDEBAR: CONFIGURAÇÕES, SALVAMENTO E EXPORTAÇÃO INTELIGENTE
    # ============================================================
    with st.sidebar:
        st.header("🏢 Engenharia e Paradas")
        
        # MEMÓRIA PERSISTENTE DA OBRA SELECIONADA
        obras_lista = ["Parada Geral Fibria 2026", "Obra Veracel Celulose", "Manutenção Industrial Estel Sede", "Parada Técnica Klabin"]
        try:
            default_idx = obras_lista.index(st.session_state.local_obra_selecionada)
        except ValueError:
            default_idx = 0

        obra_selecionada = st.selectbox(
            "Selecionar Obra ou Parada:",
            options=obras_lista,
            index=default_idx,
            key="widget_obra_selecionada"
        )
        
        # Atualiza o estado da sessão e salva dinamicamente nos parâmetros da URL para persistência real
        if obra_selecionada != st.session_state.local_obra_selecionada:
            st.session_state.local_obra_selecionada = obra_selecionada
            st.query_params["obra_persistida"] = obra_selecionada
            st.toast("💾 Contexto de Obra salvo na memória persistente!")
            
        st.info(f"📍 Contexto Atual: \n**{st.session_state.local_obra_selecionada}**")
        st.markdown("---")
        
        st.header("📥 Carregar Documentos")
        arquivos_entrada = st.file_uploader("Arraste DANFEs (PDF) ou planilhas:", type=["pdf", "xlsx", "csv"], accept_multiple_files=True)

        if arquivos_entrada and st.button("⚡ Processar Carga em Lote", type="primary"):
            all_records = []
            for arq in arquivos_entrada:
                if arq.name.lower().endswith(".pdf"):
                    all_records.extend(extrair_linhas_danfe(arq))
                else:
                    all_records.extend(extrair_linhas_excel(arq))
            
            if all_records:
                df_novo = pd.DataFrame(consolidar_registros(all_records))
                st.session_state.dados_conferencia = df_novo
                st.success(f"📊 {len(df_novo)} Itens carregados com sucesso e unificados!")
                safe_rerun()

        # SEÇÃO DE EXPORTAÇÃO COMPLETA E PROFISSIONAL (PDF + EXCEL)
        if not st.session_state.dados_conferencia.empty:
            st.markdown("---")
            st.header("📤 Exportação Inteligente")
            
            # EXCEL EXPORT
            try:
                memoria_excel = io.BytesIO()
                with pd.ExcelWriter(memoria_excel, engine='openpyxl') as writer:
                    st.session_state.dados_conferencia.to_excel(writer, index=False, sheet_name="Dados Consolidados")
                    resumo_data = {
                        'Métrica': ['Total Itens', 'Obra/Parada', 'Operador', 'Data Exportação'],
                        'Valor': [len(st.session_state.dados_conferencia), st.session_state.local_obra_selecionada, st.session_state.usuario_nome, time.strftime("%d/%m/%Y")]
                    }
                    pd.DataFrame(resumo_data).to_excel(writer, index=False, sheet_name="Sumário Executivo")
                
                st.download_button(
                    label="📊 Exportar Relatório Excel (.xlsx)",
                    data=memoria_excel.getvalue(),
                    file_name=f"Relatorio_{st.session_state.local_obra_selecionada.replace(' ', '_')}_{time.strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except Exception as e:
                st.caption(f"Aviso Excel: {e}")

            # PDF EXPORT
            pdf_data = gerar_relatorio_pdf_profissional(st.session_state.dados_conferencia, st.session_state.local_obra_selecionada)
            if pdf_data:
                st.download_button(
                    label="📕 Exportar Relatório PDF Profissional",
                    data=pdf_data,
                    file_name=f"Relatorio_{st.session_state.local_obra_selecionada.replace(' ', '_')}_{time.strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

            if st.button("🗑️ Limpar Tudo", use_container_width=True):
                st.session_state.dados_conferencia = pd.DataFrame()
                safe_rerun()

    # CONTEÚDO DA ÁREA CENTRAL DO SISTEMA
    if st.session_state.dados_conferencia.empty:
        st.info("💡 **Dica Operacional:** Arraste e processe as notas fiscais no menu lateral esquerdo para carregar o grid.")
    else:
        aba_triagem, aba_tabela, aba_dashboard = st.tabs(["📸 Posto de Triagem", "📋 Lista Consolidada", "📊 Dashboard"])

        # ABA TRIAGEM
        with aba_triagem:
            df_ref = st.session_state.dados_conferencia

            st.markdown('<div class="busca-container"><b>🔍 Busca Inteligente de Insumos</b><br><small>Filtro em tempo real.</small></div>', unsafe_allow_html=True)
            termo_busca = st.text_input("Buscar produto:", value=st.session_state.get("busca_termo", ""), placeholder="Ex: chave combinada...").strip()

            if termo_busca != st.session_state.get("busca_termo", ""):
                st.session_state.busca_termo = termo_busca
                safe_rerun()

            df_resultado, indices_resultado = buscar_itens_inteligente(df_ref, termo_busca)

            # MELHORIA CRÍTICA: Filtro de baixo limpo, enxuto e coerente (WhatsApp Image 2026-06-05 at 10.02.34 (2).jpeg)
            opcoes_resultado = [
                f"{row['Descrição do Produto']} (Qtd original: {row['Quantidade NF']})"
                for _, row in df_resultado.iterrows()
            ]

            if opcoes_resultado:
                idx_selecionado = st.selectbox(
                    "Selecione o insumo para conferência:",
                    range(len(opcoes_resultado)),
                    format_func=lambda i: opcoes_resultado[i],
                    key="select_item_clean"
                )

                idx_real = indices_resultado[idx_selecionado] if indices_resultado else df_resultado.index[idx_selecionado]
                st.session_state.item_selecionado_idx = idx_real
                linha = df_ref.loc[idx_real]

                # Card com informações do Material
                st.markdown(f"""
                <div class='card-conferencia'>
                    <h3 style='color:#0284C7; margin:0;'>{linha['Descrição do Produto']}</h3>
                    <p style='font-size:13px; color:#64748B; margin-top:4px;'>Doc: {linha['Arquivo Origem']}</p>
                    <div style="display:flex; gap:30px; margin-top:10px;">
                        <div><small>QTD NOTA</small><br><b>{linha['Quantidade NF']}</b></div>
                        <div><small>CONFERIDO</small><br><b style='color:#0284C7;'>{linha['Quantidade Conferida']}</b></div>
                        <div><small>STATUS</small><br><b>{linha['Situação']}</b></div>
                        <div><small>INSPEÇÃO</small><br><b style='color:#E67E22;'>{linha.get('Inspeção Técnica', 'Não Executado')}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                col_cam, col_form = st.columns(2)
                with col_cam:
                    foto_mat = st.camera_input("📸 Foto do Material:", key=f"cam_{idx_real}")
                    if foto_mat:
                        st.session_state.fotos_postadas[idx_real] = foto_mat.getvalue()
                        st.session_state.dados_conferencia.at[idx_real, "Foto Capturada"] = "Sim"
                        safe_rerun()
                    if idx_real in st.session_state.fotos_postadas:
                        st.image(st.session_state.fotos_postadas[idx_real], caption="Evidência Visual Coletada", width=260)

                with col_form:
                    qtd_conf = st.number_input("Quantidade real descarregada:", min_value=0.0, value=float(linha['Quantidade NF']), step=1.0, key=f"qtd_{idx_real}")
                    
                    # MELHORIA CRÍTICA: Inclusão Inteligente das Opções do Fluxograma Corporativo (Captura de tela 2026-06-05 104427.png)
                    st.markdown('<div class="inspecao-container"><b>⚙️ Resultado da Inspeção Técnica (Qualidade):</b>', unsafe_allow_html=True)
                    inspecao_status = st.radio(
                        "Defina o estado físico real do ativo:",
                        options=["Aprovado/Operacional", "Reparo Necessário", "Avaria (Mau Uso)"],
                        index=["Aprovado/Operacional", "Reparo Necessário", "Avaria (Mau Uso)"].index(linha.get("Inspeção Técnica", "Aprovado/Operacional")),
                        key=f"inspecao_radio_{idx_real}"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                    obs = st.text_area("Notas / Divergências / Laudo Técnico:", value=linha['Observações'], key=f"obs_{idx_real}")

                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("✅ Confirmar Conforme", type="primary", key=f"conf_ok_{idx_real}"):
                            st.session_state.dados_conferencia.at[idx_real, "Quantidade Conferida"] = linha['Quantidade NF']
                            st.session_state.dados_conferencia.at[idx_real, "Observações"] = obs
                            st.session_state.dados_conferencia.at[idx_real, "Situação"] = "Conforme"
                            st.session_state.dados_conferencia.at[idx_real, "Inspeção Técnica"] = inspecao_status
                            st.toast("Item salvo como Conforme!")
                            safe_rerun()

                    with col_btn2:
                        if st.button("⚠️ Registrar Divergência", key=f"conf_div_{idx_real}"):
                            st.session_state.dados_conferencia.at[idx_real, "Quantidade Conferida"] = qtd_conf
                            st.session_state.dados_conferencia.at[idx_real, "Observações"] = obs
                            st.session_state.dados_conferencia.at[idx_real, "Situação"] = "Divergente"
                            st.session_state.dados_conferencia.at[idx_real, "Inspeção Técnica"] = inspecao_status
                            st.toast("Divergência técnica registrada com sucesso!")
                            safe_rerun()
            else:
                st.warning("Nenhum item localizado sob esses critérios.")

        # ABA TABELA CONSOLIDADA DO CONTROL DE INVENTÁRIO
        with aba_tabela:
            st.markdown("### 📋 Visão Geral Estruturada dos Materiais")
            st.dataframe(st.session_state.dados_conferencia, use_container_width=True, height=450)

        # ABA DASHBOARD METRICA DE EXECUÇÃO
        with aba_dashboard:
            render_dashboard(st.session_state.dados_conferencia)
