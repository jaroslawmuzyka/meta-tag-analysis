import streamlit as st
import pandas as pd
import openai
import io
import re
import numpy as np

# --- KONFIGURACJA STRONY I HASŁA ---
st.set_page_config(page_title="Meta Tag AI Analyzer", page_icon="🤖", layout="wide")

def check_password():
    """Zabezpieczenie hasłem."""
    if st.secrets.get("APP_PASSWORD") is None:
        return True # Jeśli hasło nie jest ustawione w secrets, pomiń (dla dev)
        
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Podaj hasło dostępu:", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Podaj hasło dostępu:", type="password", on_change=password_entered, key="password")
        st.error("😕 Niepoprawne hasło")
        return False
    else:
        return True

if not check_password():
    st.stop()

# --- FUNKCJE POMOCNICZE ---

def normalize_string(text):
    """Usuwa polskie znaki i normalizuje tekst do porównań."""
    if not isinstance(text, str):
        return ""
    map_chars = {'ą': 'a', 'ć': 'c', 'ę': 'e', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z', 'ł': 'l'}
    text = text.lower()
    for k, v in map_chars.items():
        text = text.replace(k, v)
    return text

def check_keyword_presence(text, keyword):
    """Sprawdza czy słowo kluczowe występuje w tekście (fuzzy matching uproszczony)."""
    norm_text = normalize_string(text)
    norm_kw = normalize_string(keyword)
    return norm_kw in norm_text

def get_missing_keywords(keywords_list, text):
    """Zwraca listę słów kluczowych, których brakuje w tekście."""
    missing = []
    for kw in keywords_list:
        if not check_keyword_presence(text, kw):
            missing.append(kw)
    return missing

def highlight_text(text, keywords):
    """Koloruje znalezione słowa na zielono, a resztę tekstu zostawia."""
    if not isinstance(text, str): return ""
    
    # To prosta implementacja, dla pełnego HTML w Streamlit trzeba uważać
    # Tutaj po prostu zwracamy HTML do wyświetlenia w st.markdown
    highlighted = text
    # Sortujemy słowa od najdłuższego, żeby nie podmienić fragmentów
    sorted_kws = sorted(keywords, key=len, reverse=True)
    
    for kw in sorted_kws:
        # Regex case insensitive replacement
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        highlighted = pattern.sub(f"<span style='color:green; font-weight:bold'>{kw}</span>", highlighted)
        
    return highlighted

# --- FUNKCJE OPENAI (LOGIKA Z PHP PRZENIESIONA DO PYTHON) ---

def ask_openai(prompt, api_key, model="gpt-4o-mini"):
    client = openai.OpenAI(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful SEO assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip().replace('"', '')
    except Exception as e:
        return f"Error: {str(e)}"

def generate_ai_content(row, type_gen, language, api_key):
    """Generuje Title, H1 lub Meta Description."""
    keywords = row['All Keywords'] # To jest lista
    current_val = ""
    
    if type_gen == 'Title':
        current_val = row['Title 1']
        prompt = f"Biorąc pod uwagę słowa kluczowe: {', '.join(keywords)}, zasugeruj tytuł w języku {language}. Wykorzystaj frazy z obecnego tytułu: '{current_val}' oraz brakujące słowa kluczowe. Nie kończ kropką. Max 60 znaków. Tylko treść tytułu."
    
    elif type_gen == 'H1':
        current_val = row['H1-1']
        missing = get_missing_keywords(keywords, current_val)
        # Jeśli nie ma brakujących, zwróć obecny
        if not missing:
            return current_val
        
        prompt = f"Zaproponuj nagłówek H1 w języku {language} dla strony. Obecny H1: '{current_val}'. Brakujące słowa (posortowane wg ważności): {', '.join(missing)}. Nowy H1 musi zawierać stary H1 i naturalnie wpleść brakujące frazy. Bez cudzysłowów."

    elif type_gen == 'Meta Description':
        current_val = row['Meta Description 1']
        prompt = f"Zasugeruj meta opis w języku {language} zawierający słowa: {', '.join(keywords)}. Wykorzystaj kontekst z obecnego opisu: '{current_val}'. Długość ok. 150-160 znaków. Zachęcający do kliknięcia (CTR). Tylko treść."

    return ask_openai(prompt, api_key)

# --- ŁADOWANIE DANYCH ---
def load_and_process_data(file):
    try:
        df = pd.read_excel(file)
        
        # Mapowanie kolumn (elastyczne)
        col_map = {
            'Keyword': ['Keyword', 'Słowo kluczowe', 'Phrase'],
            'Volume': ['Volume', 'Wolumen'],
            'Current URL': ['Current URL', 'URL', 'Adres'],
            'Title 1': ['Title 1', 'Title', 'Tytuł'],
            'H1-1': ['H1-1', 'H1', 'Nagłówek 1'],
            'Meta Description 1': ['Meta Description 1', 'Meta Description', 'Opis']
        }
        
        # Znajdowanie właściwych nazw kolumn w pliku
        actual_cols = {}
        for key, candidates in col_map.items():
            found = False
            for c in candidates:
                if c in df.columns:
                    actual_cols[key] = c
                    found = True
                    break
            if not found:
                # Opcjonalnie: jeśli brakuje kolumny, stwórz pustą
                actual_cols[key] = key
                df[key] = ""

        # Standaryzacja nazw kolumn
        df = df.rename(columns={v: k for k, v in actual_cols.items() if k in actual_cols})
        
        # Uzupełnianie pustych wartości tekstowych
        text_cols = ['Title 1', 'H1-1', 'Meta Description 1']
        for c in text_cols:
            df[c] = df[c].fillna("").astype(str)

        # GRUPOWANIE PO URL (Kluczowa zmiana względem PHP)
        # Zamiast wiersz po wierszu, grupujemy słowa kluczowe dla jednego URL
        df_grouped = df.groupby('Current URL').agg({
            'Keyword': lambda x: list(x),
            'Volume': 'sum', # Suma wolumenu dla wszystkich fraz URL-a
            'Title 1': 'first',
            'H1-1': 'first',
            'Meta Description 1': 'first'
        }).reset_index()

        df_grouped.rename(columns={'Keyword': 'All Keywords'}, inplace=True)
        
        # Dodanie kolumn na AI (puste na start)
        df_grouped['AI Title'] = ""
        df_grouped['AI H1'] = ""
        df_grouped['AI Meta Description'] = ""
        df_grouped['Generate'] = False # Checkbox do zaznaczania

        return df_grouped

    except Exception as e:
        st.error(f"Błąd przetwarzania pliku: {e}")
        return None

# --- UI GŁÓWNE ---

st.title("🤖 Meta Tag AI Generator & Analyzer")
st.markdown("Wgraj plik XLSX (eksport z Ahrefs/Senuto + dane ze Screaming Frog), zanalizuj braki słów kluczowych i wygeneruj nowe meta tagi przy pomocy AI.")

with st.sidebar:
    st.header("⚙️ Ustawienia")
    
    # API Key Handling
    user_api_key = st.text_input("OpenAI API Key", type="password", help="Podaj swój klucz, jeśli nie jest ustawiony globalnie.")
    api_key = user_api_key if user_api_key else st.secrets.get("OPENAI_API_KEY")
    
    language = st.selectbox("Język generowania", ["pl", "en", "de", "es", "fr"], index=0)
    
    st.markdown("---")
    st.markdown("**Filtrowanie widoku:**")
    hide_empty_h1 = st.checkbox("Ukryj puste H1", value=False)
    hide_optimized = st.checkbox("Ukryj w pełni zoptymalizowane", value=False, help="Ukrywa wiersze, gdzie wszystkie słowa kluczowe występują w Title i H1")

uploaded_file = st.file_uploader("Wybierz plik XLSX", type=['xlsx'])

if uploaded_file:
    # Ładowanie danych do session_state, żeby nie resetowało się przy interakcji
    if 'df_main' not in st.session_state or st.session_state.get('last_uploaded') != uploaded_file.name:
        with st.spinner("Przetwarzanie pliku..."):
            df_processed = load_and_process_data(uploaded_file)
            if df_processed is not None:
                st.session_state['df_main'] = df_processed
                st.session_state['last_uploaded'] = uploaded_file.name
    
    if 'df_main' in st.session_state:
        df = st.session_state['df_main']

        # --- LOGIKA FILTROWANIA ---
        # Dodajemy kolumny pomocnicze do filtrowania (nie wyświetlamy ich w edytorze)
        df['Missing in Title'] = df.apply(lambda row: len(get_missing_keywords(row['All Keywords'], row['Title 1'])), axis=1)
        df['Missing in H1'] = df.apply(lambda row: len(get_missing_keywords(row['All Keywords'], row['H1-1'])), axis=1)

        df_view = df.copy()
        
        if hide_empty_h1:
            df_view = df_view[df_view['H1-1'].str.strip() != ""]
        
        if hide_optimized:
             df_view = df_view[(df_view['Missing in Title'] > 0) | (df_view['Missing in H1'] > 0)]

        # --- GŁÓWNA TABELA (DATA EDITOR) ---
        st.subheader(f"📊 Analiza ({len(df_view)} adresów URL)")
        
        column_config = {
            "Generate": st.column_config.CheckboxColumn("Zaznacz", help="Zaznacz do generowania AI", default=False),
            "Current URL": st.column_config.LinkColumn("URL"),
            "Volume": st.column_config.NumberColumn("Total Vol", format="%d"),
            "All Keywords": st.column_config.ListColumn("Keywords"),
            "Title 1": st.column_config.TextColumn("Current Title", width="medium"),
            "H1-1": st.column_config.TextColumn("Current H1", width="medium"),
            "AI Title": st.column_config.TextColumn("AI Title (New)", width="medium"),
            "AI H1": st.column_config.TextColumn("AI H1 (New)", width="medium"),
        }
        
        # Wyświetlamy edytowalną tabelę
        edited_df = st.data_editor(
            df_view,
            column_config=column_config,
            use_container_width=True,
            hide_index=True,
            disabled=["Current URL", "Volume", "All Keywords", "Missing in Title", "Missing in H1"], # Czego nie można edytować ręcznie
            column_order=["Generate", "Current URL", "Volume", "All Keywords", "Title 1", "AI Title", "H1-1", "AI H1", "Meta Description 1", "AI Meta Description"]
        )

        # Aktualizacja stanu po edycji (np. zaznaczenie checkboxów)
        # Musimy zaktualizować główny DataFrame w session_state na podstawie edycji w widoku
        # Uwaga: Pandas index matching jest kluczowy
        st.session_state['df_main'].update(edited_df)

        # --- SEKCJA GENEROWANIA AI ---
        st.divider()
        col_gen1, col_gen2, col_gen3 = st.columns(3)
        
        selected_rows = edited_df[edited_df['Generate'] == True]
        count_selected = len(selected_rows)

        if not api_key:
            st.warning("⚠️ Podaj klucz API OpenAI w ustawieniach, aby korzystać z generatora.")
        else:
            with col_gen1:
                if st.button(f"✨ Generuj Title ({count_selected})"):
                    if count_selected == 0:
                        st.warning("Zaznacz wiersze w kolumnie 'Generate'")
                    else:
                        progress_bar = st.progress(0)
                        for idx, (index, row) in enumerate(selected_rows.iterrows()):
                            new_val = generate_ai_content(row, "Title", language, api_key)
                            # Aktualizacja w głównym DF
                            st.session_state['df_main'].at[index, 'AI Title'] = new_val
                            progress_bar.progress((idx + 1) / count_selected)
                        st.rerun()

            with col_gen2:
                if st.button(f"✨ Generuj H1 ({count_selected})"):
                    if count_selected == 0:
                        st.warning("Zaznacz wiersze")
                    else:
                        progress_bar = st.progress(0)
                        for idx, (index, row) in enumerate(selected_rows.iterrows()):
                            new_val = generate_ai_content(row, "H1", language, api_key)
                            st.session_state['df_main'].at[index, 'AI H1'] = new_val
                            progress_bar.progress((idx + 1) / count_selected)
                        st.rerun()

            with col_gen3:
                if st.button(f"✨ Generuj Meta Desc ({count_selected})"):
                    if count_selected == 0:
                        st.warning("Zaznacz wiersze")
                    else:
                        progress_bar = st.progress(0)
                        for idx, (index, row) in enumerate(selected_rows.iterrows()):
                            new_val = generate_ai_content(row, "Meta Description", language, api_key)
                            st.session_state['df_main'].at[index, 'AI Meta Description'] = new_val
                            progress_bar.progress((idx + 1) / count_selected)
                        st.rerun()

        # --- SZCZEGÓŁOWY PODGLĄD (INSPEKTOR) ---
        st.divider()
        st.subheader("🔍 Inspektor URL")
        
        # Wybór URL do analizy szczegółowej
        inspect_url = st.selectbox("Wybierz adres URL do szczegółowej analizy:", df_view['Current URL'].unique())
        
        if inspect_url:
            row_inspect = df_view[df_view['Current URL'] == inspect_url].iloc[0]
            kws = row_inspect['All Keywords']
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("### Title")
                missing_t = get_missing_keywords(kws, row_inspect['Title 1'])
                st.markdown(f"**Obecny:** {highlight_text(row_inspect['Title 1'], kws)}", unsafe_allow_html=True)
                if missing_t:
                    st.markdown(f"❌ **Brakuje:** {', '.join(missing_t)}")
                else:
                    st.success("✅ Wszystkie słowa obecne")
                
                if row_inspect['AI Title']:
                    st.info(f"🤖 **AI:** {row_inspect['AI Title']}")

            with c2:
                st.markdown("### H1")
                missing_h = get_missing_keywords(kws, row_inspect['H1-1'])
                st.markdown(f"**Obecny:** {highlight_text(row_inspect['H1-1'], kws)}", unsafe_allow_html=True)
                if missing_h:
                    st.markdown(f"❌ **Brakuje:** {', '.join(missing_h)}")
                else:
                    st.success("✅ Wszystkie słowa obecne")
                
                if row_inspect['AI H1']:
                    st.info(f"🤖 **AI:** {row_inspect['AI H1']}")

            with c3:
                st.markdown("### Słowa Kluczowe")
                st.write(f"Suma wolumenu: **{row_inspect['Volume']}**")
                st.write(", ".join(kws))

        # --- EKSPORT ---
        st.divider()
        st.subheader("📥 Eksport")
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            st.session_state['df_main'].to_excel(writer, index=False, sheet_name='Analiza')
        
        st.download_button(
            label="Pobierz wyniki (.xlsx)",
            data=output.getvalue(),
            file_name="meta_tags_analysis_ai.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
