# meta-tag-analysis
🤖 Narzędzie SEO w Streamlit do analizy i generowania Meta Tagów (Title, H1, Description) przy użyciu AI (OpenAI). Agreguje słowa kluczowe z Excela, analizuje ich pokrycie w treści i automatycznie uzupełnia braki.

# 🤖 Meta Tag AI Analyzer & Generator

Zaawansowane narzędzie SEO stworzone w **Streamlit**, które automatyzuje proces optymalizacji on-site. Aplikacja łączy dane o słowach kluczowych (np. z Ahrefs/Senuto) z obecną strukturą strony (Screaming Frog), analizuje braki w optymalizacji i wykorzystuje **OpenAI (GPT-4o)** do generowania idealnych tagów Title, H1 oraz Meta Description.

🔗 **[Uruchom aplikację na Streamlit Cloud](https://share.streamlit.io/)** 

## ✨ Główne funkcjonalności

1.  **Agregacja danych:** Automatycznie grupuje wiele słów kluczowych przypisanych do jednego adresu URL. Zamiast analizować każde słowo osobno, widzisz pełny obraz dla danej podstrony.
2.  **Analiza pokrycia (Gap Analysis):** Sprawdza, które słowa kluczowe znajdują się już w obecnym Title/H1, a których brakuje.
3.  **Generator AI:** Tworzy nowe, zoptymalizowane tagi, które zawierają obecne frazy oraz inteligentnie wplatają brakujące słowa kluczowe.
4.  **Batch Processing:** Możliwość generowania treści dla dziesiątek stron jednocześnie (zaznaczanie checkboxami).
5.  **Edytor Excel-like:** Wygodna edycja danych bezpośrednio w tabeli przeglądarki.
6.  **Wizualny Inspektor:** Podgląd kolorystyczny (zielony/czerwony) pokazujący, jak dobrze obecne nagłówki pokrywają frazy kluczowe.

## 📂 Wymagany format pliku Excel

Aplikacja oczekuje pliku `.xlsx`, który jest połączeniem eksportu z narzędzi do widoczności (Ahrefs/Senuto) oraz crawlera (Screaming Frog).

**Wymagane kolumny (nazwy są elastyczne, aplikacja sama je wykrywa):**

*   **URL:** `Current URL`, `URL`, `Address`
*   **Słowo kluczowe:** `Keyword`, `Phrase`, `Słowo kluczowe`
*   **Wolumen:** `Volume`, `Wolumen`
*   **Obecny Title:** `Title 1`, `Title`, `Tytuł`
*   **Obecne H1:** `H1-1`, `H1`, `Nagłówek 1`
*   **Obecne Meta Desc:** `Meta Description 1`, `Meta Description`

> **Wskazówka:** Najlepiej przygotować plik w Excelu, używając funkcji VLOOKUP (Wyszukaj.Pionowo), aby do listy słów kluczowych i URLi dokleić obecne tagi Title i H1 ze skanu Screaming Froga.

## 🚀 Instalacja i uruchomienie

### ☁️ Streamlit Cloud (Zalecane)
1. Zforkuj to repozytorium.
2. Wejdź na [share.streamlit.io](https://share.streamlit.io/) i podłącz repozytorium.
3. W ustawieniach aplikacji (**Settings -> Secrets**) dodaj klucze:

```toml
APP_PASSWORD = "TwojeHasloDostepu"
OPENAI_API_KEY = "sk-proj-..."
