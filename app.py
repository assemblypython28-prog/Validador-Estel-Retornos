import os

# ============================================================
# CONFIGURACAO DO OPENCV E KERAS (ANTES DE TUDO)
# ============================================================
os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '0'
os.environ['TF_USE_LEGACY_KERAS'] = '1'  # Forca Keras 2 no TensorFlow 2.16+

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
# COMPATIBILIDADE: safe_rerun() vs safe_rerun()
# ============================================================
def safe_rerun():
    """Executa o rerun compatível com a versão do Streamlit instalada."""
    if hasattr(st, 'rerun'):
        safe_rerun()
    elif hasattr(st, 'experimental_rerun'):
        safe_rerun()
    else:
        st.markdown('<meta http-equiv="refresh" content="0">', unsafe_allow_html=True)

# ============================================================
# CONFIGURACAO VISUAL E ESTILO (DESIGN MODERNO)
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
# CONEXAO COM BANCO DE DADOS (SUPABASE)
# ============================================================
SUPABASE_AVAILABLE = False
supabase = None

try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)
    SUPABASE_AVAILABLE = True
except Exception as e:
    st.sidebar.warning(f"⚠️ Supabase indisponível: {str(e)[:50]}")

# Inicializacao robusta do Session State
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
# ENGENHARIA DE IA FACIAL (DEEPFACE COM FALLBACK DE BACKENDS)
# ============================================================
_deepface = None

def get_deepface():
    global _deepface
    if _deepface is None:
        from deepface import DeepFace
        _deepface = DeepFace
    return _deepface

def processar_biometria(imagem_st):
    """
    Captura a foto, detecta o rosto e extrai o vetor matematico (embedding).
    VERSAO AGRESSIVA: mais backends, pre-processamento, threshold mais baixo.
    """
    temp_path = "temp_face_input.jpg"
    temp_path_proc = "temp_face_processed.jpg"
    temp_path_proc2 = "temp_face_processed2.jpg"
    temp_path_proc3 = "temp_face_processed3.jpg"
    temp_path_proc4 = "temp_face_processed4.jpg"
    temp_path_proc5 = "temp_face_processed5.jpg"
    temp_path_proc6 = "temp_face_processed6.jpg"

    try:
        # === PRE-PROCESSAMENTO DA IMAGEM (multiplas variacoes) ===
        img = Image.open(imagem_st)
        img_rgb = img.convert("RGB")
        img_rgb.save(temp_path)

        # Variacao 1: Contraste alto
        try:
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Contrast(img_rgb)
            img_contrast = enhancer.enhance(1.5)
            img_contrast.save(temp_path_proc)
        except Exception:
            img_rgb.save(temp_path_proc)

        # Variacao 2: Brilho alto
        try:
            enhancer = ImageEnhance.Brightness(img_rgb)
            img_bright = enhancer.enhance(1.3)
            img_bright.save(temp_path_proc2)
        except Exception:
            img_rgb.save(temp_path_proc2)

        # Variacao 3: Nitidez alta
        try:
            enhancer = ImageEnhance.Sharpness(img_rgb)
            img_sharp = enhancer.enhance(1.5)
            img_sharp.save(temp_path_proc3)
        except Exception:
            img_rgb.save(temp_path_proc3)

        # Variacao 4: Tudo junto
        try:
            enhancer = ImageEnhance.Contrast(img_rgb)
            img_tudo = enhancer.enhance(1.3)
            enhancer = ImageEnhance.Brightness(img_tudo)
            img_tudo = enhancer.enhance(1.2)
            enhancer = ImageEnhance.Sharpness(img_tudo)
            img_tudo = enhancer.enhance(1.3)
            img_tudo.save(temp_path_proc4)
        except Exception:
            img_rgb.save(temp_path_proc4)

        # Variacao 5: Contraste baixo (para iluminacao forte)
        try:
            enhancer = ImageEnhance.Contrast(img_rgb)
            img_low = enhancer.enhance(0.8)
            img_low.save(temp_path_proc5)
        except Exception:
            img_rgb.save(temp_path_proc5)

        # Variacao 6: Brilho baixo (para iluminacao excessiva)
        try:
            enhancer = ImageEnhance.Brightness(img_rgb)
            img_dark = enhancer.enhance(0.9)
            img_dark.save(temp_path_proc6)
        except Exception:
            img_rgb.save(temp_path_proc6)

        df = get_deepface()

        # === BACKENDS NA ORDEM DE PRECISAO (EXPANDIDO) ===
        # retinaface: melhor precisao, mas mais lento
        # mtcnn: bom equilibrio
        # opencv: rapido, funciona bem com boa iluminacao
        # ssd: alternativo robusto

        imagens_teste = [temp_path_proc4, temp_path_proc, temp_path_proc3, temp_path, temp_path_proc2, temp_path_proc5, temp_path_proc6]
        backends = ["retinaface", "mtcnn", "opencv", "ssd"]
        embeddings_data = None
        ultimo_erro = ""
        metodo_sucesso = ""

        for img_teste in imagens_teste:
            for backend in backends:
                try:
                    embeddings_data = df.represent(
                        img_path=img_teste,
                        model_name="Facenet",
                        enforce_detection=True,
                        detector_backend=backend,
                        align=True,
                        normalization="base"
                    )
                    if embeddings_data and len(embeddings_data) > 0:
                        metodo_sucesso = f"{backend} + pre-processamento"
                        break
                except Exception as e:
                    ultimo_erro = str(e)
                    continue

            if embeddings_data:
                break

        # Fallback: tenta sem enforce_detection
        if not embeddings_data:
            for img_teste in imagens_teste:
                try:
                    embeddings_data = df.represent(
                        img_path=img_teste,
                        model_name="Facenet",
                        enforce_detection=False,
                        detector_backend="opencv",
                        align=True,
                        normalization="base"
                    )
                    if embeddings_data and len(embeddings_data) > 0:
                        metodo_sucesso = "opencv (sem enforce)"
                        st.info("⚠️ Rosto detectado com baixa confianca.")
                        break
                except Exception as e:
                    ultimo_erro = str(e)

        # Fallback final: modelo OpenFace
        if not embeddings_data:
            for img_teste in imagens_teste:
                try:
                    embeddings_data = df.represent(
                        img_path=img_teste,
                        model_name="OpenFace",
                        enforce_detection=False,
                        detector_backend="opencv",
                        align=True
                    )
                    if embeddings_data and len(embeddings_data) > 0:
                        metodo_sucesso = "OpenFace (fallback final)"
                        st.info("⚠️ Deteccao com modelo alternativo.")
                        break
                except Exception as e:
                    ultimo_erro = str(e)

        # Limpeza de arquivos temporarios
        for f in [temp_path, temp_path_proc, temp_path_proc2, temp_path_proc3, temp_path_proc4, temp_path_proc5, temp_path_proc6]:
            if os.path.exists(f):
                os.remove(f)

        if embeddings_data and len(embeddings_data) > 0:
            if metodo_sucesso:
                st.success(f"✅ Rosto detectado: {metodo_sucesso}")
            return embeddings_data[0]["embedding"]

        st.error("❌ Nao foi possivel detectar o rosto.")
        st.info("""
        **Dicas para melhorar a deteccao:**
        1. 🌟 **Iluminacao**: Esteja em local bem iluminado (luz natural eh ideal)
        2. 🎯 **Centralizacao**: Enquadre o rosto no centro da camera
        3. 😐 **Expressao**: Mantenha expressao neutra (sem sorriso exagerado)
        4. 👓 **Oculos**: Se possivel, retire oculos escuros ou de grau grosso
        5. 🧢 **Acessorios**: Remova bones, lencos ou qualquer coisa que cubra o rosto
        6. 📏 **Distancia**: Fique a 30-50cm da camera
        7. 📸 **Qualidade**: Use upload de foto em vez da camera se possivel
        """)

        if ultimo_erro:
            st.caption(f"Detalhes tecnicos: {ultimo_erro[:150]}")
        return None

    except Exception as e:
        for f in [temp_path, temp_path_proc, temp_path_proc2, temp_path_proc3, temp_path_proc4, temp_path_proc5, temp_path_proc6]:
            if os.path.exists(f):
                os.remove(f)
        st.error(f"Erro: {str(e)[:100]}")
        return None

def calcular_similaridade(vetor1, vetor2):
    v1, v2 = np.array(vetor1), np.array(vetor2)
    return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))

# ============================================================
# ENGINES DE EXTRACAO DE DADOS MULTIPLOS (PDF & EXCEL)
# ============================================================
FITZ_AVAILABLE = False
try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    pass

def consolidar_registros(registros):
    """
    Consolida registros de múltiplos arquivos:
    - Duplicatas (mesmo nome + mesma qtd): mantém 1, descarta repetida
    - Divergências (mesmo nome + qtd diferente): SOMA quantidades em 1 linha
    - Preserva todos os arquivos de origem na coluna 'Arquivo Origem'
    """
    if not registros:
        return []

    # Dicionário para agrupar por nome do produto
    grupos = {}

    for reg in registros:
        chave = reg["Descrição do Produto"].strip().upper()

        if chave not in grupos:
            grupos[chave] = {
                "registros": [],
                "arquivos_origem": set(),
                "quantidades": [],
            }

        grupos[chave]["registros"].append(reg)
        grupos[chave]["arquivos_origem"].add(reg["Arquivo Origem"])
        grupos[chave]["quantidades"].append(reg["Quantidade NF"])

    registros_consolidados = []

    for chave, dados in grupos.items():
        qtds = dados["quantidades"]
        arquivos = sorted(dados["arquivos_origem"])

        # Verificar se todas as quantidades são iguais
        if len(set(qtds)) == 1:
            # CASO 1: DUPLICATA (mesmo nome, mesma quantidade)
            # Mantém 1 registro, descarta os repetidos
            reg_base = dados["registros"][0].copy()
            reg_base["Arquivo Origem"] = " | ".join(arquivos)
            reg_base["Observações"] = f"Item encontrado em {len(arquivos)} arquivo(s)."
            registros_consolidados.append(reg_base)

        else:
            # CASO 2: DIVERGÊNCIA (mesmo nome, quantidades diferentes)
            # Soma todas as quantidades em 1 linha
            qtd_total = sum(qtds)
            reg_base = dados["registros"][0].copy()
            reg_base["Quantidade NF"] = qtd_total
            reg_base["Arquivo Origem"] = " | ".join(arquivos)
            reg_base["Observações"] = f"Quantidades divergentes entre arquivos ({len(arquivos)} arquivos). Qtds originais: {', '.join(str(q) for q in qtds)}. Total consolidado: {qtd_total}."
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
# PAINEL DE AUTENTICACAO (LOGIN DIRETO POR FOTO)
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
        # === CAMERA OU UPLOAD DE FOTO ===
        tab_cam, tab_upload = st.tabs(["📷 Câmera", "📁 Upload de Foto"])

        foto_captura = None

        with tab_cam:
            st.info("💡 Dicas: Boa iluminação frontal, rosto centralizado, sem óculos escuros")
            foto_captura = st.camera_input("Scanner Facial Ativo:", key="scan_facial_posto_unico")

        with tab_upload:
            st.info("💡 Fotos da galeria geralmente têm melhor qualidade que a câmera do celular")
            foto_upload = st.file_uploader("Selecione uma foto do rosto:", type=["jpg", "jpeg", "png"], key="upload_foto_login")
            if foto_upload:
                foto_captura = foto_upload
                st.image(foto_upload, caption="Foto selecionada", width=200)
        
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
                                
                                if score > 0.70:
                                    reconhecido = True
                                    operador_nome = usuario["nome"]
                                    break
                            except Exception:
                                pass
                        
                        st.success(f"✅ Reconhecido! Seja bem-vindo, {operador_nome}.")
                        st.info(f"📊 Score de confiança: {score:.1%}")
                            st.session_state.autenticado = True
                            st.session_state.usuario_nome = operador_nome
                            time.sleep(1)
                            safe_rerun()
                        else:
                            st.warning("👤 Rosto não localizado na base. Preencha os dados abaixo para vincular sua biometria:")
                        st.caption(f"📊 Melhor score encontrado: {score:.1%} (mínimo: 70%)")
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
                                            safe_rerun()
                                        except Exception as e:
                                            st.error(f"Erro ao salvar: {e}")
                                    else:
                                        st.error("Por favor, preencha todos os campos do formulário.")
                    else:
                        st.info("Supabase Indisponível. Use admin/admin para contingência local.")
                        u_t = st.text_input("User:")
                        s_t = st.text_input("Pass:", type="password")
                        if st.button("Entrar"):
                            if u_t == "admin" and s_t == "admin":
                                st.session_state.autenticado = True
                                st.session_state.usuario_nome = "Supervisor Local"
                                safe_rerun()
                else:
                    st.error("⚠️ Não foi possível detectar o rosto claramente. Ajuste a iluminação e centralize-se na câmera.")

# ============================================================
# PAINEL PRINCIPAL (MULTIPLOS ARQUIVOS EM LOTE)
# ============================================================
else:
    cab_esquerdo, cab_direito = st.columns([4, 1])
    cab_esquerdo.markdown(f"<h1>🚚 Validador de Retornos de Obra</h1>", unsafe_allow_html=True)
    cab_esquerdo.caption(f"Operador Autenticado por Biometria: **{st.session_state.usuario_nome}**")
    
    if cab_direito.button("Encerrar Atividades", key="logout"):
        st.session_state.autenticado = False
        st.session_state.dados_conferencia = pd.DataFrame()
        st.session_state.fotos_postadas = {}
        safe_rerun()
        
    st.markdown("---")
    
    with st.sidebar:
        st.header("📥 Carregar Documentos")
        arquivos_entrada = st.file_uploader(
            "Arraste DANFEs (PDF) ou planilhas de uma vez:",
            type=["pdf", "xlsx", "xls", "csv"],
            accept_multiple_files=True
        )
        
        if arquivos_entrada:
            if st.button("Processar Carga em Lote", type="primary"):
                all_records = []
                with st.spinner("Lendo todos os documentos adicionados..."):
                    for arq in arquivos_entrada:
                        if arq.name.endswith(".pdf"):
                            all_records.extend(extrair_linhas_danfe(arq))
                        else:
                            all_records.extend(extrair_linhas_excel(arq))
                    
                    if all_records:
                        # === CONSOLIDAÇÃO INTELIGENTE DE DADOS ===
                        with st.spinner("Consolidando dados de múltiplos arquivos..."):
                            registros_consolidados = consolidar_registros(all_records)

                            # Criar DataFrame com dados consolidados
                            df_novo = pd.DataFrame(registros_consolidados)

                            # Estatísticas da consolidação
                            total_original = len(all_records)
                            total_consolidado = len(df_novo)
                            itens_removidos = total_original - total_consolidado

                            st.session_state.dados_conferencia = df_novo

                            # Feedback detalhado ao usuário
                            if itens_removidos > 0:
                                st.success(f"📊 {total_consolidado} itens consolidados com sucesso!")
                                st.info(f"""
                                🔄 **Consolidação realizada:**
                                - {total_original} registros brutos importados
                                - {itens_removidos} duplicata(s)/divergência(s) tratada(s)
                                - {total_consolidado} itens finais únicos
                                """)
                            else:
                                st.success(f"📊 {total_consolidado} itens mapeados com sucesso! (sem duplicatas)")

                            # Mostrar alerta se houver divergências
                            divergencias = [r for r in registros_consolidados if "divergentes" in r.get("Observações", "")]
                            if divergencias:
                                st.warning(f"⚠️ {len(divergencias)} item(s) com quantidades divergentes entre arquivos foram SOMADOS automaticamente.")

                        safe_rerun()
        
        if not st.session_state.dados_conferencia.empty:
            st.markdown("---")
            st.header("📤 Fechamento")
            memoria_excel = io.BytesIO()
            with pd.ExcelWriter(memoria_excel, engine='openpyxl') as writer:
                st.session_state.dados_conferencia.to_excel(writer, index=False, sheet_name="Consolidado")
            
            st.download_button(
                label="💾 Exportar Relatório Geral",
                data=memoria_excel.getvalue(),
                file_name=f"Relatorio_Estel_{time.strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.ms-excel"
            )
            
            if st.button("Limpar Tudo"):
                st.session_state.dados_conferencia = pd.DataFrame()
                st.session_state.fotos_postadas = {}
                safe_rerun()

    if st.session_state.dados_conferencia.empty:
        st.info("💡 **Dica operacional:** Carregue uma ou várias notas fiscais no menu à esquerda para iniciar o processo.")
    else:
        aba_triagem, aba_tabela, aba_indicadores = st.tabs([
            "📸 Posto de Triagem & Fotos",
            "📋 Lista Geral Consolidada",
            "📊 Painel de Controle"
        ])
        
        with aba_triagem:
            df_ref = st.session_state.dados_conferencia

            # ============================================================
            # BUSCA INTELIGENTE COM AUTOCOMPLETE
            # ============================================================
            st.markdown("""
            <style>
            .busca-destaque { background-color: #E0F2FE; padding: 12px; border-radius: 8px; border-left: 4px solid #0284C7; margin-bottom: 12px; }
            </style>
            """, unsafe_allow_html=True)

            st.markdown("<div class='busca-destaque'><b>🔍 Busca Inteligente de Insumos</b><br><small>Digite parte do nome, código ou descrição do produto</small></div>", unsafe_allow_html=True)

            # Campo de busca com autocomplete
            termo_busca = st.text_input(
                "Buscar produto (mínimo 2 caracteres):",
                placeholder="Ex: cimento, parafuso, tubo pvc...",
                key="busca_produto"
            ).strip().upper()

            # Montar lista de opções com base nos arquivos importados
            opcoes_completas = [
                f"[{row['Arquivo Origem']}] - {row['Descrição do Produto']}"
                for _, row in df_ref.iterrows()
            ]

            # Se digitou algo, filtrar com busca parcial (contém em qualquer parte)
            if len(termo_busca) >= 2:
                termos_busca = termo_busca.split()  # Suporta múltiplas palavras
                opcoes_filtradas = []

                for opcao in opcoes_completas:
                    # Verifica se TODOS os termos digitados estão presentes na opção
                    if all(termo in opcao.upper() for termo in termos_busca):
                        opcoes_filtradas.append(opcao)

                if opcoes_filtradas:
                    st.success(f"✅ {len(opcoes_filtradas)} item(s) encontrado(s) para '{termo_busca}'")

                    # Se só encontrou 1, pré-seleciona automaticamente
                    if len(opcoes_filtradas) == 1:
                        st.info("🎯 Apenas 1 resultado encontrado — pré-selecionado automaticamente!")
                        item_composto_selecionado = opcoes_filtradas[0]
                        st.write(f"**Selecionado:** `{item_composto_selecionado}`")
                    else:
                        # Mostra os resultados filtrados em um selectbox
                        item_composto_selecionado = st.selectbox(
                            "Selecione entre os resultados encontrados:",
                            opcoes_filtradas,
                            key="select_filtrado"
                        )
                else:
                    st.warning(f"⚠️ Nenhum resultado para '{termo_busca}'. Mostrando TODOS os itens:")
                    item_composto_selecionado = st.selectbox(
                        "Selecione o insumo para conferência (lista completa):",
                        opcoes_completas,
                        key="select_completo_fallback"
                    )
            else:
                # Se não digitou nada, mostra todos com um selectbox padrão
                # Mas agrupa por arquivo de origem para facilitar
                st.caption("💡 Digite no campo acima para filtrar, ou selecione da lista completa:")

                # Agrupar por arquivo de origem
                arquivos_unicos = df_ref['Arquivo Origem'].unique()
                if len(arquivos_unicos) > 1:
                    arquivo_selecionado = st.selectbox(
                        "Filtrar por Arquivo/NF:",
                        ["Todos"] + list(arquivos_unicos),
                        key="filtro_arquivo"
                    )

                    if arquivo_selecionado != "Todos":
                        df_filtrado_arquivo = df_ref[df_ref['Arquivo Origem'] == arquivo_selecionado]
                        opcoes_filtradas_arq = [
                            f"[{row['Arquivo Origem']}] - {row['Descrição do Produto']}"
                            for _, row in df_filtrado_arquivo.iterrows()
                        ]
                        item_composto_selecionado = st.selectbox(
                            "Selecione o insumo:",
                            opcoes_filtradas_arq,
                            key="select_por_arquivo"
                        )
                    else:
                        item_composto_selecionado = st.selectbox(
                            "Selecione o insumo para conferência:",
                            opcoes_completas,
                            key="select_completo"
                        )
                else:
                    item_composto_selecionado = st.selectbox(
                        "Selecione o insumo para conferência:",
                        opcoes_completas,
                        key="select_completo_unico"
                    )

            if item_composto_selecionado:
                arq_nome = item_composto_selecionado.split("] - ")[0].replace("[", "")
                prod_nome = item_composto_selecionado.split("] - ")[1]

                mask = (df_ref["Arquivo Origem"] == arq_nome) & (df_ref["Descrição do Produto"] == prod_nome)
                if not mask.any():
                    st.error("Item não encontrado na base.")
                    st.stop()

                idx = df_ref[mask].index[0]
                linha = df_ref.loc[idx]

                st.markdown(f"""
                <div class='card-conferencia'>
                    <p style='color:#64748B; margin:0;'>Arquivo de Origem: <b>{linha['Arquivo Origem']}</b></p>
                    <h3 style='color:#0284C7; margin:0;'>{linha['Descrição do Produto']}</h3>
                    <p style='margin:5px 0 0 0;'>Qtd NF Prevista: <b>{linha['Quantidade NF']}</b> | Situação Operacional: <b>{linha['Situação']}</b></p>
                </div>
                """, unsafe_allow_html=True)

                col_cam, col_form = st.columns(2)
                with col_cam:
                    foto_mat = st.camera_input(
                        "Foto do Material (Auditoria Visual):",
                        key=f"cam_{idx}"
                    )
                    if foto_mat:
                        st.session_state.fotos_postadas[idx] = foto_mat.getvalue()
                        st.session_state.dados_conferencia.at[idx, "Foto Capturada"] = "Sim"
                        st.toast("📸 Imagem do material armazenada na sessão!")

                    if idx in st.session_state.fotos_postadas:
                        st.image(
                            st.session_state.fotos_postadas[idx],
                            caption="Foto salva atualmente para auditoria",
                            width=300
                        )

                with col_form:
                    qtd_conf = st.number_input(
                        "Quantidade real descarregada:",
                        min_value=0.0,
                        value=float(linha['Quantidade NF']),
                        key=f"qtd_{idx}"
                    )
                    obs = st.text_area(
                        "Notas / Divergências observadas:",
                        value=linha['Observações'],
                        key=f"obs_{idx}"
                    )

                    if st.button("Confirmar e Gravar Item", type="primary", key=f"conf_{idx}"):
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
                                st.toast("💾 Dados gravados no Supabase com sucesso!")
                            except Exception as e:
                                st.error(f"Erro ao sincronizar com banco: {e}")
                        safe_rerun()

        with aba_tabela:
            st.dataframe(st.session_state.dados_conferencia, use_container_width=True)

        with aba_indicadores:
            df = st.session_state.dados_conferencia
            c1, c2, c3 = st.columns(3)
            c1.metric("Total de Insumos Carregados", len(df))
            c2.metric("Itens Validados Sem Erro", len(df[df["Situação"] == "Conforme"]))
            c3.metric("Itens Com Divergência", len(df[df["Situação"] == "Divergente"]))
