import streamlit as st
import pandas as pd
import openai
import io
import re
import numpy as np
import difflib
import os

# --- KONFIGURACJA STRONY I HASŁA ---
st.set_page_config(page_title="Meta Tag AI Analyzer", page_icon="🤖", layout="wide")

def check_password():
    """Zabezpieczenie hasłem."""
    try:
        app_password = st.secrets.get("APP_PASSWORD")
    except Exception:
        app_password = None

    if not app_password:
        return True # Jeśli hasło nie jest ustawione w secrets, pomiń (dla dev)
        
    def password_entered():
        if st.session_state["password"] == app_password:
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

def visualize_diff(original, new_val):
    if not isinstance(original, str): original = ""
    if not isinstance(new_val, str): new_val = ""
    
    orig_words = original.split()
    new_words = new_val.split()
    
    # Porownujemy case-insensitive, ale wyswietlamy oryginalne slowa
    orig_lower = [w.lower() for w in orig_words]
    new_lower  = [w.lower() for w in new_words]

    matcher = difflib.SequenceMatcher(None, orig_lower, new_lower)
    diff_html = ""
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            diff_html += f"<span style='color:red; text-decoration:line-through;'>{' '.join(orig_words[i1:i2])}</span> "
            diff_html += f"<span style='color:green; font-weight:bold;'>{' '.join(new_words[j1:j2])}</span> "
        elif tag == 'delete':
            diff_html += f"<span style='color:red; text-decoration:line-through;'>{' '.join(orig_words[i1:i2])}</span> "
        elif tag == 'insert':
            diff_html += f"<span style='color:green; font-weight:bold;'>{' '.join(new_words[j1:j2])}</span> "
        elif tag == 'equal':
            diff_html += f"{' '.join(orig_words[i1:i2])} "
            
    return diff_html.strip()

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
    url = row['Current URL']
    current_val = ""
    kw_str = ", ".join(keywords)
    missing_str = ""
    
    if type_gen == 'Title':
        current_val = row['Title 1']
        missing_str = ", ".join(get_missing_keywords(keywords, current_val))
    elif type_gen == 'H1':
        current_val = row['H1-1']
        missing = get_missing_keywords(keywords, current_val)
        if not missing:
            return current_val
        missing_str = ", ".join(missing)
    elif type_gen == 'Meta Description':
        current_val = row['Meta Description 1']
        missing_str = ", ".join(get_missing_keywords(keywords, current_val))

    custom_prompts = st.session_state.get('custom_prompts', {})
    prompt_template = custom_prompts.get(type_gen, "")
    
    if not prompt_template:
        return f"Error: Brak szablonu promptu dla {type_gen}!"

    prompt = prompt_template.format(
        url=url,
        kw_str=kw_str,
        current_val=current_val,
        language=language,
        missing_str=missing_str
    )

    return ask_openai(prompt, api_key)

# --- ŁADOWANIE DANYCH ---
def load_and_process_data(file):
    try:
        df = pd.read_excel(file)
        
        # Mapowanie kolumn (elastyczne)
        col_map = {
            'Keyword': ['Keyword', 'Słowo kluczowe', 'Phrase'],
            'Volume': ['Volume', 'Wolumen'],
            'Current position': ['Current position', 'Position', 'Pozycja'],
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
                actual_cols[key] = key
                df[key] = ""

        # Standaryzacja nazw kolumn
        df = df.rename(columns={v: k for k, v in actual_cols.items() if k in actual_cols})
        
        # Uzupełnianie pustych wartości tekstowych
        text_cols = ['Title 1', 'H1-1', 'Meta Description 1']
        for c in text_cols:
            df[c] = df[c].fillna("").astype(str)

        # Bezpieczna konwersja liczb
        if 'Volume' in df.columns:
            df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce').fillna(0)
        else:
            df['Volume'] = 0
            
        if 'Current position' in df.columns:
            df['Current position'] = pd.to_numeric(df['Current position'], errors='coerce').fillna(100)
        else:
            df['Current position'] = 100

        # Nowa kolumna opisowa zawierająca słowo kluczowe, pozycję i wolumen
        df['Keyword_Info'] = df.apply(lambda r: f"{r['Keyword']} (poz: {int(r['Current position'])}, vol: {int(r['Volume'])})", axis=1)

        # Sortowanie wewnętrznie przed grupowaniem, od największego wolumenu
        df = df.sort_values(by=['Current URL', 'Volume'], ascending=[True, False])

        # GRUPOWANIE PO URL
        df_grouped = df.groupby('Current URL').agg({
            'Keyword': lambda x: list(x),
            'Keyword_Info': lambda x: list(x),
            'Volume': 'sum', # Suma wolumenu dla wszystkich fraz URL-a
            'Title 1': 'first',
            'H1-1': 'first',
            'Meta Description 1': 'first'
        }).reset_index()

        df_grouped.rename(columns={'Keyword': 'All Keywords'}, inplace=True)
        
        # Sortowanie po całkowitym wolumenie per adres URL zeby najwazniejsze strony byly u góry
        df_grouped = df_grouped.sort_values('Volume', ascending=False).reset_index(drop=True)
        
        # Dodanie kolumn na AI (puste na start)
        df_grouped['AI Title'] = ""
        df_grouped['AI H1'] = ""
        df_grouped['AI Meta Description'] = ""
        df_grouped['Generate'] = False # Checkbox do zaznaczania

        return df_grouped

    except Exception as e:
        st.error(f"Błąd przetwarzania pliku: {e}")
        return None

# --- DOMYŚLNE PROMPTY ---
default_prompt_title = "Biorąc pod uwagę URL: {url} i słowa kluczowe: {kw_str}, zasugeruj ulepszony tytuł (Title) w języku {language}. Wykorzystaj frazy z obecnego tytułu: '{current_val}' i zgrabnie wpleść brakujące. Stwórz naturalny tekst. Unikaj chamskiego upychania słów kluczowych (keyword stuffingu), ale postaraj się zawrzeć brakujące słowa kluczowe. Przeanalizuj adres URL, aby zachować sens i intencję podstrony. Nie kończ kropką. Max 60 znaków. Tylko treść tytułu."

default_prompt_h1 = "Zaproponuj nagłówek H1 w języku {language} dla URL: {url}. Obecny H1: '{current_val}'. Brakujące słowa kluczowe: {missing_str}. Nowy H1 musi naturalnie wpleść te frazy, opierając się na starym H1. Stwórz naturalny tekst. Unikaj chamskiego upychania słów kluczowych (keyword stuffingu), ale postaraj się zawrzeć brakujące słowa kluczowe. Przeanalizuj adres URL, aby zachować sens i intencję podstrony. Tylko treść."

default_prompt_meta = "Zasugeruj zachęcający meta opis w języku {language} dla URL: {url} (słowa kluczowe: {kw_str}). Obecny opis: '{current_val}'. Stwórz naturalny tekst. Unikaj chamskiego upychania słów kluczowych (keyword stuffingu), ale postaraj się zawrzeć brakujące słowa kluczowe. Przeanalizuj adres URL, aby zachować sens i intencję podstrony. Długość ok. 150-160 znaków. Tylko treść."

if 'custom_prompts' not in st.session_state:
    st.session_state['custom_prompts'] = {
        'Title': default_prompt_title,
        'H1': default_prompt_h1,
        'Meta Description': default_prompt_meta
    }

# --- UI GŁÓWNE ---

st.title("🤖 Meta Tag AI Generator & Analyzer")
st.markdown("Wgraj plik XLSX (eksport z Ahrefs/Senuto + dane ze Screaming Frog), zanalizuj braki słów kluczowych i wygeneruj nowe meta tagi przy pomocy AI.")

st.info("Narzędzie identyfikuje luki w optymalizacji meta tagów (Title/H1) poprzez porównanie widoczności słów kluczowych z Ahrefs z Title/H1. Jeśli Title lub H1 nie zawierają słów widocznych w Ahrefs - mamy potencjał do dofrazowania.")

with st.expander("📌 Przykład zastosowania"):
    st.markdown("""
    Pobierz z Ahrefs słowa kluczowe znajdujące się na pozycjach 4-20 z wolumenem powyżej 50. 
    Sprawdź jakie adresy są widoczne na te frazy i wrzuć je do Screaming Frog żeby pobrać Title, H1, Meta description.
    Wgraj wszystko do narzędzia aby uzyskać informacje o brakujących frazach w title/h1.
    """)

with st.expander("📖 Instrukcje"):
    st.markdown("""
    - Pobierz z Ahrefs słowa kluczowe (np. na pozycjach 4-20, wolumen powyżej 50)
    - Dla adresów widocznych w Ahrefs pobierz ze Screaming Frog: Title, H1, Meta description.
    - Połącz wszystko w jeden plik z kolumnami:
        - Keyword    
        - Volume    
        - Current position    
        - Current URL    
        - Title 1    
        - H1-1    
        - Meta Description 1
    """)

with st.sidebar:
    st.header("⚙️ Ustawienia")
    
    # API Key Handling
    user_api_key = st.text_input("OpenAI API Key", type="password", help="Podaj swój klucz, jeśli nie jest ustawiony globalnie.")
    api_key = user_api_key
    if not api_key:
        try:
            api_key = st.secrets.get("OPENAI_API_KEY")
        except Exception:
            api_key = None
    
    language = st.selectbox("Język generowania", ["pl", "en", "de", "es", "fr"], index=0)
    
    st.markdown("---")
    st.markdown("**Filtrowanie widoku:**")
    hide_empty_h1 = st.checkbox("Ukryj puste H1", value=False)
    hide_optimized = st.checkbox("Ukryj w pełni zoptymalizowane", value=False, help="Ukrywa wiersze, gdzie wszystkie słowa kluczowe występują w Title i H1")

import os
if os.path.exists("przykladowy-plik.xlsx"):
    with open("przykladowy-plik.xlsx", "rb") as file:
        st.download_button(label="📥 Pobierz przykładowy plik Excel", data=file, file_name="przykladowy-plik.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

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

        # TWORZYMY ZAKŁADKI W UI
        tab1, tab2, tab3 = st.tabs(["📊 Analiza Zbiorcza", "🔍 Analiza konkretnego URL", "⚙️ Edytuj Prompty"])
        
        with tab1:
            # --- NAGŁÓWEK Z PRZYCISKIEM EKSPORTU ---
            col_h1, col_h2 = st.columns([3, 1])
            with col_h1:
                st.subheader(f"📊 Analiza ({len(df_view)} adresów URL)")
            with col_h2:
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    st.session_state['df_main'].to_excel(writer, index=False, sheet_name='Analiza')
                st.download_button(
                    label="📥 Pobierz wyniki (.xlsx)",
                    data=output.getvalue(),
                    file_name="meta_tags_analysis_ai.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            # --- PAGINACJA NAD TABELĄ ---
            total_items = len(df_view)
            col_page1, col_page2, col_page3 = st.columns([2, 5, 2])
            
            with col_page1:
                items_per_page = st.selectbox("Wierszy na stronę:", [10, 50, 100, 200, 500, 1000], index=2)
                
            total_pages = max(1, (total_items - 1) // items_per_page + 1) if total_items > 0 else 1
            
            with col_page2:
                # Wyśrodkowanie tekstu z ilością wyświetlanych URL-i
                st.write("")
                if total_items > 0:
                    start_idx = (st.session_state.get("current_page_no", 1) - 1) * items_per_page
                    end_idx = min(start_idx + items_per_page, total_items)
                    st.markdown(f"<div style='text-align:center; padding-top:8px;'><b>Wyświetlam {start_idx + 1}-{end_idx} z {total_items} adresów URL</b></div>", unsafe_allow_html=True)
                else:
                    st.markdown("<div style='text-align:center; padding-top:8px;'><b>Brak wyników.</b></div>", unsafe_allow_html=True)

            with col_page3:
                current_page = st.number_input("Strona", min_value=1, max_value=total_pages, value=1, key="current_page_no")
                
            start_idx = (current_page - 1) * items_per_page
            end_idx = min(start_idx + items_per_page, total_items)
            df_page = df_view.iloc[start_idx:end_idx]

            st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)

            # --- SEKCJA GENEROWANIA AI (ZBIORCZE) NAD TABELĄ ---
            st.markdown("### Generowanie zbiorcze")
            col_gen1, col_gen2, col_gen3 = st.columns(3)
            
            # Pobieramy które są zaznaczone na podstawie `st.session_state`
            selected_indices = [idx for idx in df_page.index if st.session_state.get(f"gen_{idx}")]
            selected_rows = st.session_state['df_main'].loc[selected_indices] if len(selected_indices) > 0 else []
            count_selected = len(selected_rows)

            if not api_key:
                st.warning("⚠️ Podaj klucz API OpenAI w ustawieniach, aby korzystać z generatora.")
            else:
                info_text = "(zaznacz wiersze poniżej by generować zbiorowo)"
                with col_gen1:
                    if st.button(f"✨ Masowo generuj Title ({count_selected})"):
                        if count_selected == 0: st.warning(info_text)
                        else:
                            progress_bar = st.progress(0)
                            for i, (index, row) in enumerate(selected_rows.iterrows()):
                                st.session_state['df_main'].at[index, 'AI Title'] = generate_ai_content(row, "Title", language, api_key)
                                progress_bar.progress((i + 1) / count_selected)
                            st.rerun()
                with col_gen2:
                    if st.button(f"✨ Masowo generuj H1 ({count_selected})"):
                        if count_selected == 0: st.warning(info_text)
                        else:
                            progress_bar = st.progress(0)
                            for i, (index, row) in enumerate(selected_rows.iterrows()):
                                st.session_state['df_main'].at[index, 'AI H1'] = generate_ai_content(row, "H1", language, api_key)
                                progress_bar.progress((i + 1) / count_selected)
                            st.rerun()
                with col_gen3:
                    if st.button(f"✨ Masowo generuj Meta ({count_selected})"):
                        if count_selected == 0: st.warning(info_text)
                        else:
                            progress_bar = st.progress(0)
                            for i, (index, row) in enumerate(selected_rows.iterrows()):
                                st.session_state['df_main'].at[index, 'AI Meta Description'] = generate_ai_content(row, "Meta Description", language, api_key)
                                progress_bar.progress((i + 1) / count_selected)
                            st.rerun()

            st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)

            # --- TABELA GŁÓWNA ---
            st.markdown("""
            <div style="display:flex; font-weight:bold; border-bottom:2px solid #ccc; padding-bottom:10px; margin-bottom:10px; font-size:14px;">
                <div style="width:5%;">Zaznacz</div>
                <div style="width:20%;">URL & Wolumen</div>
                <div style="width:29%;">Frazy (Title/H1/Meta)</div>
                <div style="width:23%;">Obecne Tagi</div>
                <div style="width:23%;">Wygenerowane przez AI</div>
            </div>
            """, unsafe_allow_html=True)

            for idx, row in df_page.iterrows():
                c1, c2, c3, c4, c5 = st.columns([0.5, 2.0, 3.2, 2.3, 2.3])
                with c1:
                    is_selected = st.checkbox(" ", key=f"gen_{idx}", label_visibility="collapsed")
                with c2:
                    st.markdown(f"<div style='font-size:13px; word-break:break-word; margin-bottom:5px;'><a href='{row['Current URL']}' target='_blank'>{row['Current URL']}</a></div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='font-size:13px; color:#555;'>Całkowity wolumen: <b>{int(row['Volume'])}</b></div>", unsafe_allow_html=True)
                with c3:
                    kw_html_lines = []
                    # Jeśli AI wygenerowało tag, to na nim oceniamy, inaczej na oryginalnym! To daje dynamiczne ptaszki!
                    target_t = row['AI Title'] if row['AI Title'] else row['Title 1']
                    target_h = row['AI H1'] if row['AI H1'] else row['H1-1']
                    target_m = row['AI Meta Description'] if row['AI Meta Description'] else row['Meta Description 1']
                    
                    for kw_info, kw_word in zip(row['Keyword_Info'], row['All Keywords']):
                        t_icon = "✅" if check_keyword_presence(target_t, kw_word) else "❌"
                        h_icon = "✅" if check_keyword_presence(target_h, kw_word) else "❌"
                        m_icon = "✅" if check_keyword_presence(target_m, kw_word) else "❌"
                        
                        badges = f"<span style='font-size:11px; color:#555;'>[Title: {t_icon} | H1: {h_icon} | Meta description: {m_icon}]</span>"
                        kw_html_lines.append(f"<div style='margin-bottom:14px; line-height:1.4;'><b>{kw_info}</b><br>{badges}</div>")
                    
                    st.markdown("".join(kw_html_lines), unsafe_allow_html=True)
                with c4:
                    st.markdown(f"<div style='font-size:13px; margin-bottom:8px; word-break:break-word;'><b>Title:</b><br>{row['Title 1']}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='font-size:13px; margin-bottom:8px; word-break:break-word;'><b>H1:</b><br>{row['H1-1']}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='font-size:13px; word-break:break-word;'><b>Meta description:</b><br>{row['Meta Description 1']}</div>", unsafe_allow_html=True)
                with c5:
                    ai_t = row['AI Title'] if row['AI Title'] else "—"
                    t_col1, t_col2 = st.columns([5, 1])
                    t_col1.markdown(f"<div style='font-size:13px; margin-bottom:8px; color:#1a7a3c; word-break:break-word;'><b>Title:</b><br>{ai_t}</div>", unsafe_allow_html=True)
                    if t_col2.button("🪄", key=f"t_{idx}", help="Generuj Title dla tego URL"):
                        if not api_key: st.error("Brak")
                        else:
                            st.session_state['df_main'].at[idx, 'AI Title'] = generate_ai_content(row, "Title", language, api_key)
                            st.rerun()

                    ai_h = row['AI H1'] if row['AI H1'] else "—"
                    h_col1, h_col2 = st.columns([5, 1])
                    h_col1.markdown(f"<div style='font-size:13px; margin-bottom:8px; color:#1a7a3c; word-break:break-word;'><b>H1:</b><br>{ai_h}</div>", unsafe_allow_html=True)
                    if h_col2.button("🪄", key=f"h_{idx}", help="Generuj H1 dla tego URL"):
                        if not api_key: st.error("Brak")
                        else:
                            st.session_state['df_main'].at[idx, 'AI H1'] = generate_ai_content(row, "H1", language, api_key)
                            st.rerun()

                    ai_m = row['AI Meta Description'] if row['AI Meta Description'] else "—"
                    m_col1, m_col2 = st.columns([5, 1])
                    m_col1.markdown(f"<div style='font-size:13px; color:#1a7a3c; word-break:break-word;'><b>Meta desc:</b><br>{ai_m}</div>", unsafe_allow_html=True)
                    if m_col2.button("🪄", key=f"m_{idx}", help="Generuj Meta Desc dla tego URL"):
                        if not api_key: st.error("Brak")
                        else:
                            st.session_state['df_main'].at[idx, 'AI Meta Description'] = generate_ai_content(row, "Meta Description", language, api_key)
                            st.rerun()
                
                st.markdown("<hr style='margin:15px 0; border-color:#eaeaea;'>", unsafe_allow_html=True)


        with tab2:
            # --- SZCZEGÓŁOWY PODGLĄD (INSPEKTOR) ---
            st.subheader("🔍 Inspektor URL")
            inspect_url = st.selectbox("Wybierz adres URL do szczegółowej analizy i przegenerowania:", df_view['Current URL'].unique())
            
            if inspect_url:
                # Bierzemy z df_main żeby odświeżał się po wciśnięciu Przegeneruj (Różdżki)
                row_inspect = st.session_state['df_main'][st.session_state['df_main']['Current URL'] == inspect_url].iloc[0]
                idx_main = st.session_state['df_main'].index[st.session_state['df_main']['Current URL'] == inspect_url].tolist()[0]
                kws = row_inspect['All Keywords']
                kw_infos = row_inspect['Keyword_Info']
                
                col_left, col_right = st.columns([2, 1])
                with col_left:
                    st.markdown("### Title 1")
                    missing_t = get_missing_keywords(kws, row_inspect['Title 1'])
                    st.markdown(f"**Obecny:** {highlight_text(row_inspect['Title 1'], kws)}", unsafe_allow_html=True)
                    if missing_t:
                        st.markdown(f"❌ **Brakuje:** {', '.join(missing_t)}")
                    else:
                        st.success("✅ Wszystkie słowa obecne")
                    
                    if row_inspect['AI Title']:
                        st.markdown(f"<br>🤖 **AI (Diff):**<br> {visualize_diff(row_inspect['Title 1'], row_inspect['AI Title'])}", unsafe_allow_html=True)

                    if st.button("🪄 Przegeneruj Title", key="wand_title"):
                        if not api_key: st.error("⚠️ Podaj klucz API OpenAI")
                        else:
                            with st.spinner("Generowanie..."):
                                st.session_state['df_main'].at[idx_main, 'AI Title'] = generate_ai_content(row_inspect, "Title", language, api_key)
                            st.rerun()

                    st.markdown("---")
                    st.markdown("### H1")
                    missing_h = get_missing_keywords(kws, row_inspect['H1-1'])
                    st.markdown(f"**Obecny:** {highlight_text(row_inspect['H1-1'], kws)}", unsafe_allow_html=True)
                    if missing_h:
                        st.markdown(f"❌ **Brakuje:** {', '.join(missing_h)}")
                    else:
                        st.success("✅ Wszystkie słowa obecne")
                    
                    if row_inspect['AI H1']:
                        st.markdown(f"<br>🤖 **AI (Diff):**<br> {visualize_diff(row_inspect['H1-1'], row_inspect['AI H1'])}", unsafe_allow_html=True)

                    if st.button("🪄 Przegeneruj H1", key="wand_h1"):
                        if not api_key: st.error("⚠️ Podaj klucz API OpenAI")
                        else:
                            with st.spinner("Generowanie..."):
                                st.session_state['df_main'].at[idx_main, 'AI H1'] = generate_ai_content(row_inspect, "H1", language, api_key)
                            st.rerun()

                    st.markdown("---")
                    st.markdown("### Meta Description")
                    st.markdown(f"**Obecny:** {row_inspect['Meta Description 1']}")
                    if row_inspect['AI Meta Description']:
                        st.markdown(f"<br>🤖 **AI (Diff):**<br> {visualize_diff(row_inspect['Meta Description 1'], row_inspect['AI Meta Description'])}", unsafe_allow_html=True)
                    
                    if st.button("🪄 Przegeneruj Meta", key="wand_meta"):
                        if not api_key: st.error("⚠️ Podaj klucz API OpenAI")
                        else:
                            with st.spinner("Generowanie..."):
                                st.session_state['df_main'].at[idx_main, 'AI Meta Description'] = generate_ai_content(row_inspect, "Meta Description", language, api_key)
                            st.rerun()

                with col_right:
                    st.markdown("### Słowa Kluczowe")
                    st.write(f"Suma wolumenu: **{row_inspect['Volume']}**")
                    for kwi in kw_infos:
                        st.markdown(f"- {kwi}")

        with tab3:
            st.subheader("⚙️ Edytuj Prompty Systemowe")
            st.info("Dostosuj instrukcje wysyłane do modelu OpenAI. Dostępne zmienne w nawiasach klamrowych: \n- `{url}` - adres URL\n- `{kw_str}` - wszystkie słowa kluczowe po przecinku\n- `{current_val}` - obecny element, np. stary Title\n- `{language}` - wybrany język np. pl\n- `{missing_str}` - brakujące słowa kluczowe (szczególnie przydatne w H1)")
            
            c_prompts = st.session_state['custom_prompts']
            
            new_title = st.text_area("✍️ Prompt dla Title", value=c_prompts.get('Title', ''), height=180)
            new_h1 = st.text_area("✍️ Prompt dla H1", value=c_prompts.get('H1', ''), height=180)
            new_meta = st.text_area("✍️ Prompt dla Meta Description", value=c_prompts.get('Meta Description', ''), height=180)
            
            if st.button("💾 Zapisz Prompty"):
                st.session_state['custom_prompts'] = {
                    'Title': new_title,
                    'H1': new_h1,
                    'Meta Description': new_meta
                }
                st.success("Prompty zostały zaktualizowane! Teraz Magiczna Różdżka i Tablica Zbiorcza będzie korzystać z nowych instrukcji.")

        # END OF UI
