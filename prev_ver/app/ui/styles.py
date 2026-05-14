from __future__ import annotations

import streamlit as st


def render_app_shell() -> None:
    st.set_page_config(page_title="보험 약관 AI 챗봇", layout="wide")
    st.markdown(
        """
    <style>
    :root {
      --sf-blue: #0057b8;
      --sf-navy: #0a2d5e;
      --sf-light: #f3f7fc;
      --sf-border: #d8e3f2;
      --sf-user: #dcecff;
      --sf-assistant: #ffffff;
      --sf-accent: #e53935;
    }
    
    .stApp {
      background: linear-gradient(180deg, #f7fbff 0%, #eef4fb 100%);
      color: #111111;
    }
    
    .main .block-container {
      max-width: 980px;
      padding-top: 1.2rem;
      padding-bottom: 2.4rem;
    }
    
    .sf-hero {
      background: linear-gradient(135deg, var(--sf-navy), var(--sf-blue));
      color: #fff;
      border-radius: 16px;
      padding: 18px 20px;
      margin-bottom: 14px;
      box-shadow: 0 10px 24px rgba(0, 48, 110, 0.16);
    }
    
    .sf-hero h1 {
      margin: 0;
      font-size: 1.7rem;
      letter-spacing: -0.2px;
    }
    
    .sf-hero p {
      margin: 8px 0 0;
      opacity: 0.95;
    }
    
    .sf-note {
      color: #4f6178;
      font-size: 0.92rem;
      margin-bottom: 10px;
    }
    
    [data-testid="stChatMessage"] {
      border: 1px solid var(--sf-border);
      border-radius: 14px;
      padding: 8px 10px;
      margin-bottom: 8px;
      color: #111111;
      width: auto;
      max-width: 100%;
      min-width: 160px;
    }
    
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
      background: var(--sf-user);
      margin-left: auto;
      margin-right: 0;
      flex-direction: row-reverse;
    }
    
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
      background: var(--sf-assistant);
      margin-left: 0;
      margin-right: auto;
    }
    
    [data-testid="stChatMessage"] p,
    [data-testid="stChatMessage"] li,
    [data-testid="stChatMessage"] span,
    [data-testid="stChatMessage"] div {
      color: #111111 !important;
    }
    
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stMarkdownContainer"] {
      text-align: left;
    }
    
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stImage"] {
      margin-left: auto;
    }
    
    [data-testid="chatAvatarIcon-user"] {
      display: none;
    }
    
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageAvatar"] {
      display: none;
    }
    
    @media (max-width: 720px) {
      [data-testid="stChatMessage"] {
        min-width: 0;
      }
    }
    
    [data-testid="stChatInput"] {
      background: #fff;
      border: 1px solid var(--sf-border);
      border-radius: 14px;
      box-shadow: 0 6px 18px rgba(0, 40, 90, 0.06);
    }
    
    .stButton button {
      background: var(--sf-blue);
      color: #fff;
      border: 0;
    }
    
    .stButton button:hover {
      background: #00499b;
      color: #fff;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )
    
    st.markdown(
        """
    <div class="sf-hero">
      <h1>삼성화재 보험 약관 AI 챗봇</h1>
      <p>사고 상황과 청구 서류를 함께 확인해드리는 AI 안내 도우미</p>
    </div>
    """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sf-note">사고 상황을 편하게 적어주시면 관련 약관, 사례, 필요 서류를 차근차근 확인해드립니다.</div>',
        unsafe_allow_html=True,
    )
