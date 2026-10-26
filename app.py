#!/usr/bin/env python3
"""Streamlit interface for the Sarvam study-notes reader."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import streamlit as st

import docs_reader


st.set_page_config(page_title="Study Notes Reader", page_icon="📚", layout="wide")
st.title("Study Notes Reader")
st.write("Turn lecture notes and study documents into clear, exam-ready notes using your study method.")

st.info("Your document is sent to Sarvam for processing. API keys are read from `.env` or the environment and are never shown here.")

language_codes = {
    "English": "en-IN",
    "Hindi": "hi-IN",
    "Bengali": "bn-IN",
    "Gujarati": "gu-IN",
    "Kannada": "kn-IN",
    "Malayalam": "ml-IN",
    "Marathi": "mr-IN",
    "Odia": "od-IN",
    "Punjabi": "pa-IN",
    "Tamil": "ta-IN",
    "Telugu": "te-IN",
    "Urdu": "ur-IN",
}

uploaded = st.file_uploader(
    "Choose a study document",
    type=["pdf", "png", "jpg", "jpeg", "txt", "md"],
    help="PDFs and page images are digitised by Sarvam Document AI. Text and Markdown files go directly to chat completion.",
)
language = st.selectbox("Document language (PDFs and images)", list(language_codes), index=0)

with st.expander("Study method used for every document"):
    st.markdown((docs_reader.PROMPT_PATH).read_text(encoding="utf-8"))

if uploaded is not None:
    st.caption(f"Selected: {Path(uploaded.name).name} · {uploaded.size:,} bytes")

if st.button("Create study notes", type="primary", disabled=uploaded is None):
    safe_name = Path(uploaded.name).name
    suffix = Path(safe_name).suffix.lower()
    try:
        with st.spinner("Reading the document and creating your notes…"):
            if not os.environ.get("SARVAM_API_KEY"):
                try:
                    os.environ["SARVAM_API_KEY"] = str(st.secrets["SARVAM_API_KEY"])
                except Exception:
                    pass
            client = docs_reader.make_client()
            with tempfile.TemporaryDirectory(prefix="sarvam-reader-") as temporary_directory:
                document_path = Path(temporary_directory) / safe_name
                document_path.write_bytes(uploaded.getvalue())
                source_text = docs_reader.read_document(client, document_path, language_codes[language])
            instructions = docs_reader.PROMPT_PATH.read_text(encoding="utf-8").strip()
            notes = docs_reader.create_notes(client, instructions, source_text, Path(safe_name).stem)
        st.session_state["study_notes"] = notes
        st.session_state["study_notes_name"] = f"{Path(safe_name).stem}-study-notes.md"
    except Exception as exc:
        message = str(exc)
        api_key = os.environ.get("SARVAM_API_KEY", "")
        if api_key:
            message = message.replace(api_key, "[redacted]")
        st.error(f"Could not create notes: {message}")

if st.session_state.get("study_notes"):
    st.subheader("Your study notes")
    notes = st.session_state["study_notes"]
    st.markdown(notes)
    st.download_button(
        "Download Markdown",
        data=notes,
        file_name=st.session_state["study_notes_name"],
        mime="text/markdown",
        type="secondary",
    )
