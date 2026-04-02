# 📜 Lexicon Latinum

A browser-based viewer and quality-assurance tool for Latin dictionary data encoded in the [TEI Lex-0](https://dariah-eric.github.io/lexicalresources/pages/TEILex0/TEILex0.html) XML format.

> **Purpose:** This application is intended strictly for **educational, research, and quality-assurance (QA) purposes**. It provides lexicographers, classicists, and students with a convenient way to inspect, browse, and validate TEI Lex-0 dictionary files without requiring any XML editor or command-line tools.

---

## Features

| Feature | Description |
|---|---|
| **File upload** | Drop one or more TEI Lex-0 `.xml` files directly in the browser — no installation of a separate server required |
| **Dictionary browse** | Entries are displayed in alphabetical order by `sortKey`, with lemma, inflected forms, grammatical badges (POS, gender, conjugation class), and all senses |
| **Nested senses** | Sub-senses at any depth are rendered with correct indentation |
| **Example citations** | `<cit type="example">` blocks are shown with a red left border, displaying the Latin phrase and its translation |
| **Source links** | `<bibl>` / `<ref type="bibliography">` elements are rendered as clickable badges linking to Perseus Digital Library or any other URL in the `target` attribute |
| **Cross-references** | `<ref type="entry">` cross-references within senses are shown in italic red |
| **Inline notes** | `<note>` children of `<sense>` are rendered as grey italic text |
| **Sense-level grammar** | `<gramGrp>` inside a `<sense>` (e.g. `mood=part.`) appears as a badge at sense level |
| **Fuzzy search** | The search box matches against `sortKey`, lemma, inflected forms, and translations. Results are ranked by closeness — exact > prefix > substring > fuzzy ratio > translation |
| **Statistics module** | Donut charts for Part of Speech and Gender distribution; stacked bar chart per file; filterable word table with CSV export |
| **Encoding tolerance** | Files declaring `encoding='UTF8'` (non-standard, no hyphen) are normalised automatically before parsing |

---

## Installation

Requires **Python 3.10+**.

```bash
pip install -r requirements.txt
```

`requirements.txt` contains:
```
streamlit>=1.32.0
pandas>=2.0.0
plotly>=5.18.0
```

---

## Running

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501` by default.

---

## Usage

1. **Upload files** — Use the sidebar uploader to drag and drop one or more TEI Lex-0 XML files.
2. **Browse** — The *Dictionary* tab displays all entries. Scroll or use the search box.
3. **Search** — Type any Latin word (or partial word) in the search box. Fuzzy matching finds near-misses and ranks them by relevance.
4. **Inspect links** — In the *Dictionary* tab, source citation badges (e.g. `(Caes. B.G. I.1.1)`) are clickable links to the online text.
5. **Statistics** — Switch to the *Statistics* tab for an overview of POS and gender distributions and a filterable table of all imported words. Use the *Download as CSV* button to export.

---

## Supported TEI Lex-0 Elements

The parser recognises the following TEI Lex-0 structures:

``` 
<entry>
  <form type="lemma|inflected">
    <orth [expand="..."]/>
  </form>
  <gramGrp>
    <gram type="pos|gender|iType|mood"/>
  </gramGrp>
  <sense>
    <lbl/>
    <gramGrp><gram/></gramGrp>   ← sense-level grammar
    <note/>                       ← inline note
    <ref type="entry"/>           ← cross-reference
    <cit type="translationEquivalent">
      <form><orth/></form>
    </cit>
    <cit type="example">
      <quote>
        ...text...
        <bibl>
          <ref type="bibliography" sameAs="bibl.xml#KEY"/>
          <ref type="entry" target="https://...">label</ref>
        </bibl>
      </quote>
      <cit type="translation" xml:lang="bg">
        <quote>...translation...<bibl>...</bibl></quote>
      </cit>
    </cit>
    <sense>...</sense>            ← nested sub-senses
  </sense>
</entry>
```

Elements not listed above are silently ignored, making the parser robust to extended or non-standard markup.

---

## QA Use Cases

- **Completeness check** — Use the Statistics tab to spot entries missing a `pos` or `gender` tag (they appear as *Unknown* or empty in the word table).
- **Link validation** — Bibl badges with no URL are rendered without a hyperlink, making broken references immediately visible.
- **Cross-reference audit** — Entries with `<ref type="entry">` cross-references are rendered explicitly; a missing target label is shown as the raw `xml:id`.
- **Batch review** — Upload the full combined file (e.g. `lbr_all_etries_new.xml`) alongside individual entry files to compare coverage.

---

## Project Structure

```
dictionary/
├── app.py                  # Main Streamlit application
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── .streamlit/
│   └── config.toml         # UI theme 
```

---

## License & Disclaimer

This tool is provided **for educational and quality-assurance purposes only**. It does not modify source XML files. All dictionary content remains the intellectual property of its respective authors and publishers. Links to external resources (Perseus Digital Library, etc.) are provided for scholarly reference under fair-use principles.
