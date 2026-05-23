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
# ⚙️ CONFIGURAÇÃO E AMBIENTE IA
# ============================================================
st.set_page_config(page_title="Acesso Estel - Biometria", layout="wide")

try:
    import face_recognition
    IA_READY = True
except ImportError:
    IA_READY = False

# Conexão Supabase
@st.cache_resource
def init_db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

db = init_db()

# Estados de Sessão
if "user" not in st.session_state: st.session_state.user = None
if "temp_face" not in st.session_state: st.session_state.temp_face = None

# ============================================================
# 🧠 LÓGICA DE RECONHECIMENTO
# ============================================================
def processar_biometria(foto):
    image = Image.open(foto)
    image_np = np.array(image.convert('RGB'))
    encodings = face_recognition.face_encodings(image_np)
    return encodings[0] if len(encodings) > 0 else None

# ============================================================
# 🖼️ INTERFACE ÚNICA DE ACESSO
# ============================================================
if not st.session_state.user:
    st.markdown("<h2 style='text-align:center;'>📸 Identificação Biométrica Estel</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        foto_captura = st.camera_input("Olhe para a câmera para entrar ou se cadastrar")

        if foto_captura:
            if not IA_READY:
                st.error("IA ainda carregando no servidor. Tente em 1 minuto.")
            else:
                with st.spinner("Buscando sua identidade..."):
                    vetor_atual = processar_biometria(foto_captura)
                    
                    if vetor_atual is not None:
                        # Busca usuários no banco
                        res = db.table("usuarios").not_.is_("face_embedding", "null").execute()
                        match_encontrado = None
                        
                        for u in res.data:
                            vetor_salvo = np.array(json.loads(u["face_embedding"]))
                            if face_recognition.compare_faces([vetor_salvo], vetor_atual, tolerance=0.45)[0]:
                                match_encontrado = u
                                break
                        
                        if match_encontrado:
                            st.success(f"✅ Reconhecido: Bem-vindo, {match_encontrado['nome']}!")
                            st.session_state.user = match_encontrado
                            time.sleep(1)
                            st.rerun()
                        else:
                            # SE NÃO ENCONTRAR: Abre cadastro
                            st.warning("👤 Usuário não identificado. Deseja realizar seu primeiro cadastro?")
                            with st.expander("📝 Formulário de Primeiro Acesso", expanded=True):
                                nome = st.text_input("Nome Completo")
                                user_id = st.text_input("Usuário Corporativo")
                                senha = st.text_input("Senha", type="password")
                                
                                if st.button("Finalizar Cadastro e Entrar"):
                                    if nome and user_id and senha:
                                        embedding_json = json.dumps(vetor_atual.tolist())
                                        db.table("usuarios").insert({
                                            "nome": nome, "usuario": user_id, 
                                            "senha": senha, "face_embedding": embedding_json
                                        }).execute()
                                        st.success("Cadastro realizado com sucesso!")
                                        st.session_state.user = {"nome": nome}
                                        st.rerun()
                                    else:
                                        st.error("Preencha todos os campos.")
                    else:
                        st.error("Nenhum rosto detectado. Tente novamente.")

else:
    # PAINEL OPERACIONAL (Onde o app de conferência roda)
    st.title(f"🚚 Painel Logístico - Olá, {st.session_state.user['nome']}")
    if st.button("Sair"):
        st.session_state.user = None
        st.rerun()
