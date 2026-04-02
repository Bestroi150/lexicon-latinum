"""
Lexicon Latinum — TEI Lex-0 Latin Dictionary Viewer
A Streamlit application for visualising and exploring TEI Lex-0 XML files.
"""

import difflib
import io
import re
import xml.etree.ElementTree as ET
from collections import Counter

import pandas as pd
import plotly.express as px
import streamlit as st

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Lexicon Latinum",
    page_icon="📜",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TEI_NS = "http://www.tei-c.org/ns/1.0"
NS = {"tei": TEI_NS}

POS_MAP: dict[str, str] = {
    "v.": "Verb",
    "adv.": "Adverb",
    "n.": "Noun",
    "adj.": "Adjective",
    "prep.": "Preposition",
    "conj.": "Conjunction",
    "pron.": "Pronoun",
    "interj.": "Interjection",
    "num.": "Numeral",
    "part.": "Participle",
    "dep.": "Deponent",
    "indecl.": "Indeclinable",
}

GENDER_MAP: dict[str, str] = {
    "m": "Masculine",
    "f": "Feminine",
    "n": "Neuter",
    "c": "Common",
}

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
STYLE = """
<style>
    /* Title */
    .lex-title {
        font-family: 'Georgia', serif;
        font-size: 2.6rem;
        font-weight: 700;
        color: #7B1818;
        margin-bottom: 0;
    }
    .lex-subtitle {
        font-size: 0.95rem;
        color: #888;
        margin-top: -4px;
        letter-spacing: 0.06em;
    }
    /* Entry card */
    .entry-lemma {
        font-family: 'Georgia', serif;
        font-size: 1.4rem;
        font-weight: 700;
        color: #2c2c2c;
    }
    .entry-inflected {
        font-style: italic;
        color: #555;
    }
    .gram-badge {
        display: inline-block;
        background: #f0e8e8;
        color: #7B1818;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 0.78rem;
        font-weight: 600;
        margin-right: 4px;
    }
    .sense-line {
        margin: 2px 0;
        color: #333;
        font-size: 0.97rem;
    }
    .sense-label {
        font-weight: 600;
        color: #7B1818;
        margin-right: 4px;
    }
    hr.entry-divider {
        border: none;
        border-top: 1px solid #e8ddd5;
        margin: 10px 0 14px 0;
    }
    /* Example citation */
    .example-block {
        margin: 5px 0 5px 12px;
        padding: 4px 10px;
        border-left: 3px solid #C45E5E;
        background: #fdf4f4;
        border-radius: 0 4px 4px 0;
    }
    .example-quote {
        font-style: italic;
        color: #5a1a1a;
        font-size: 0.93rem;
        font-family: 'Georgia', serif;
    }
    .example-trans {
        color: #444;
        font-size: 0.87rem;
        margin-top: 1px;
    }
    /* Bibl (source citation) link */
    .bibl-link {
        font-size: 0.78rem;
        color: #7B1818;
        text-decoration: none;
        background: #f0e8e8;
        border-radius: 3px;
        padding: 1px 5px;
        margin-left: 4px;
        white-space: nowrap;
    }
    .bibl-link:hover { text-decoration: underline; }
    /* Cross-reference (ref type=entry) */
    .cross-ref {
        font-style: italic;
        color: #7B1818;
        font-weight: 600;
        font-family: 'Georgia', serif;
    }
    /* Inline note */
    .sense-note {
        color: #888;
        font-style: italic;
        font-size: 0.9rem;
        margin-right: 3px;
    }
    /* Source caption */
    .source-cap {
        font-size: 0.75rem;
        color: #aaa;
        margin-top: 2px;
    }
    /* Metric cards */
    div[data-testid="metric-container"] {
        background: #fdf7f2;
        border: 1px solid #e8ddd5;
        border-radius: 8px;
        padding: 10px 16px !important;
    }
</style>
"""

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _text(el) -> str:
    """Return stripped text of an element, or empty string if None."""
    return (el.text or "").strip() if el is not None else ""


def _clean(text: str) -> str:
    """Collapse whitespace including newlines."""
    return " ".join(text.split())


def _parse_bibl(bibl_el) -> dict | None:
    """Parse a <bibl> element into {key, label, url}."""
    if bibl_el is None:
        return None
    key = label = url = ""
    for ref in bibl_el.findall("tei:ref", NS):
        rtype = ref.get("type", "")
        if rtype == "bibliography":
            key = ref.get("sameAs", "")
        elif rtype == "entry":
            url = ref.get("target", "")
            label = _clean(ref.text or "")
    # fallback: plain text inside bibl after the first ref
    if not label:
        parts = [bibl_el.text or ""]
        for child in bibl_el:
            parts.append(child.tail or "")
        label = _clean(" ".join(parts))
    if not label and not key:
        return None
    return {"key": key, "label": label, "url": url}


def _parse_quote(quote_el) -> dict:
    """Parse a <quote> element; returns {text, bibl}."""
    if quote_el is None:
        return {"text": "", "bibl": None}
    text_parts: list[str] = [quote_el.text or ""]
    bibl_data = None
    for child in quote_el:
        local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if local == "bibl":
            bibl_data = _parse_bibl(child)
        else:
            text_parts.append(child.text or "")
        if child.tail:
            text_parts.append(child.tail)
    text = _clean(" ".join(p for p in text_parts if p.strip()))
    return {"text": text, "bibl": bibl_data}


def _parse_sense(sense_el, depth: int = 0) -> dict:
    """Recursively parse a <sense> element."""
    label = _text(sense_el.find("tei:lbl", NS))

    translations: list[str] = []
    examples: list[dict] = []
    notes: list[str] = []
    cross_refs: list[dict] = []   # {target, label}
    sense_gramgrp: dict = {}

    # sense-level <gramGrp> (e.g. mood=part.)
    gg = sense_el.find("tei:gramGrp", NS)
    if gg is not None:
        for gram in gg.findall("tei:gram", NS):
            sense_gramgrp[gram.get("type", "")] = _text(gram)

    # <note> children
    for note_el in sense_el.findall("tei:note", NS):
        n = _clean(_text(note_el))
        if n:
            notes.append(n)

    # <ref type="entry"> direct children (cross-references)
    for ref_el in sense_el.findall("tei:ref", NS):
        if ref_el.get("type") == "entry":
            cross_refs.append({
                "target": ref_el.get("target", ""),
                "label": _clean(ref_el.text or ""),
            })

    for cit in sense_el.findall("tei:cit", NS):
        cit_type = cit.get("type", "")
        if cit_type == "translationEquivalent":
            for orth in cit.findall("tei:form/tei:orth", NS):
                t = _text(orth)
                if t:
                    translations.append(t)
        elif cit_type == "example":
            q_data = _parse_quote(cit.find("tei:quote", NS))
            t_data = {"text": "", "bibl": None}
            trans_cit = cit.find("tei:cit[@type='translation']", NS)
            if trans_cit is not None:
                t_data = _parse_quote(trans_cit.find("tei:quote", NS))
            if q_data["text"]:
                examples.append({
                    "quote": q_data["text"],
                    "quote_bibl": q_data["bibl"],
                    "translation": t_data["text"],
                    "translation_bibl": t_data["bibl"],
                })

    sub_senses = [_parse_sense(s, depth + 1) for s in sense_el.findall("tei:sense", NS)]

    return {
        "label": label,
        "translations": translations,
        "examples": examples,
        "notes": notes,
        "cross_refs": cross_refs,
        "sense_gramgrp": sense_gramgrp,
        "sub_senses": sub_senses,
        "depth": depth,
    }


def _collect_all_translations(senses: list[dict]) -> list[str]:
    """Flatten all translations from every level of nested senses."""
    result: list[str] = []
    for s in senses:
        result.extend(s["translations"])
        result.extend(_collect_all_translations(s["sub_senses"]))
    return result


def _parse_entry(entry_el, source_file: str) -> dict:
    sort_key = entry_el.get("sortKey", "")

    # Lemma
    lemma_el = entry_el.find("tei:form[@type='lemma']/tei:orth", NS)
    lemma = _text(lemma_el) or sort_key

    # Inflected forms — prefer the 'expand' attribute (full form) over suffix text
    inflected: list[str] = []
    for form_el in entry_el.findall("tei:form", NS):
        if form_el.get("type") != "inflected":
            continue
        orth_el = form_el.find("tei:orth", NS)
        if orth_el is not None:
            val = orth_el.get("expand") or _text(orth_el)
            if val:
                inflected.append(val)

    # Grammar group
    gg = entry_el.find("tei:gramGrp", NS)
    pos = gender = itype = ""
    if gg is not None:
        for gram in gg.findall("tei:gram", NS):
            gtype = gram.get("type", "")
            val = _text(gram)
            if gtype == "pos":
                pos = val
            elif gtype == "gender":
                gender = val
            elif gtype == "iType":
                itype = val

    # Senses
    senses = [_parse_sense(s) for s in entry_el.findall("tei:sense", NS)]

    return {
        "lemma": lemma,
        "sort_key": sort_key,
        "inflected": inflected,
        "pos": pos,
        "gender": gender,
        "itype": itype,
        "senses": senses,
        "source_file": source_file,
    }


def _normalise_encoding(data: bytes) -> bytes:
    """Fix non-standard encoding names in the XML declaration.

    Some files declare ``encoding='UTF8'`` (no hyphen) which expat rejects.
    This replaces common aliases with their IANA-registered names.
    """
    aliases = {b"UTF8": b"UTF-8", b"utf8": b"UTF-8"}
    def _replace(m: re.Match) -> bytes:
        quote, name, end = m.group(1), m.group(2), m.group(3)
        return b"encoding=" + quote + aliases.get(name, name) + end
    return re.sub(rb'encoding=([\'"])([A-Za-z0-9_-]+)([\'"])', _replace, data, count=1)


def parse_tei_file(file_bytes: bytes, filename: str) -> tuple[list[dict], str | None]:
    """Parse a TEI Lex-0 XML file. Returns (entries, error_message)."""
    try:
        root = ET.fromstring(_normalise_encoding(file_bytes))
    except ET.ParseError as err:
        return [], f"XML parse error in **{filename}**: {err}"

    raw_entries = root.findall(f".//{{{TEI_NS}}}entry")
    entries = [_parse_entry(e, filename) for e in raw_entries]
    return entries, None


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _bibl_html(bibl: dict | None) -> str:
    """Render a bibl dict as a small linked citation badge."""
    if not bibl:
        return ""
    label = bibl["label"] or bibl["key"].replace("bibl.xml#", "")
    if bibl["url"]:
        return f'<a class="bibl-link" href="{bibl["url"]}" target="_blank" rel="noopener">{label}</a>'
    return f'<span class="bibl-link">{label}</span>'


def _sense_html(sense: dict) -> str:
    indent = "&nbsp;&nbsp;&nbsp;&nbsp;" * sense["depth"]
    label_html = f'<span class="sense-label">{sense["label"]}</span>' if sense["label"] else ""

    # sense-level grammar (e.g. mood=part.)
    sg = sense.get("sense_gramgrp", {})
    gram_html = ""
    if sg:
        for gtype, gval in sg.items():
            gram_html += f'<span class="gram-badge">{gval}</span> '

    # notes
    notes_html = "".join(
        f'<span class="sense-note">{n}</span>' for n in sense.get("notes", [])
    )

    # cross-references
    xref_html = "".join(
        f'<span class="cross-ref">{xr["label"] or xr["target"]}</span>'
        for xr in sense.get("cross_refs", [])
    )

    trans_html = ", ".join(sense["translations"])
    line_parts = [indent, label_html, gram_html, notes_html, xref_html, trans_html]
    line = "".join(p for p in line_parts if p).strip()
    out = f'<div class="sense-line">{line}</div>' if line else ""

    for ex in sense.get("examples", []):
        q_bibl = _bibl_html(ex.get("quote_bibl"))
        t_bibl = _bibl_html(ex.get("translation_bibl"))
        trans_part = ""
        if ex["translation"] or t_bibl:
            trans_part = f'<div class="example-trans">{ex["translation"]}{t_bibl}</div>'
        out += (
            f'<div class="example-block">'
            f'<span class="example-quote">{ex["quote"]}</span>{q_bibl}'
            f'{trans_part}'
            f'</div>'
        )
    for sub in sense["sub_senses"]:
        out += _sense_html(sub)
    return out


def render_entry(entry: dict) -> None:
    """Render a single dictionary entry as an HTML card."""
    inflected_part = (
        f', <span class="entry-inflected">{", ".join(entry["inflected"])}</span>'
        if entry["inflected"]
        else ""
    )

    badges = ""
    pos_label = POS_MAP.get(entry["pos"], entry["pos"])
    gender_label = GENDER_MAP.get(entry["gender"], "")
    if pos_label:
        badges += f'<span class="gram-badge">{pos_label}</span>'
    if gender_label:
        badges += f'<span class="gram-badge">{gender_label}</span>'
    if entry["itype"]:
        badges += f'<span class="gram-badge">Conj.&nbsp;{entry["itype"]}</span>'

    senses_html = "".join(_sense_html(s) for s in entry["senses"])

    html = f"""
    <div>
      <span class="entry-lemma">{entry["lemma"]}</span>{inflected_part}
      &nbsp;&nbsp;{badges}
      <div style="margin-top:6px">{senses_html}</div>
      <div class="source-cap">📄 {entry["source_file"]}</div>
    </div>
    <hr class="entry-divider"/>
    """
    st.markdown(html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def main() -> None:
    st.markdown(STYLE, unsafe_allow_html=True)

    # -- Title ---------------------------------------------------------------
    st.markdown(
        '<div class="lex-title">📜 Lexicon Latinum</div>'
        '<div class="lex-subtitle">TEI Lex-0 Latin Dictionary Viewer</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # -- Sidebar: file upload ------------------------------------------------
    with st.sidebar:
        st.markdown("## Import Files")
        uploaded_files = st.file_uploader(
            "Drop TEI Lex-0 XML files here",
            type=["xml"],
            accept_multiple_files=True,
            help="Upload one or more TEI Lex-0 XML dictionary files.",
        )

    # -- Parse uploaded files ------------------------------------------------
    all_entries: list[dict] = []
    parse_errors: list[str] = []

    if uploaded_files:
        for f in uploaded_files:
            entries, err = parse_tei_file(f.read(), f.name)
            if err:
                parse_errors.append(err)
            all_entries.extend(entries)

    for err in parse_errors:
        st.error(err)

    # -- Sidebar metrics -----------------------------------------------------
    with st.sidebar:
        if all_entries:
            st.markdown("---")
            st.metric("Files loaded", len(uploaded_files) if uploaded_files else 0)
            st.metric("Entries loaded", len(all_entries))
        else:
            st.info("Upload XML files above to begin.")

    if not all_entries:
        st.info(
            "👆 Upload one or more **TEI Lex-0 XML** files in the sidebar to get started.\n\n"
            "The viewer accepts standard TEI Lex-0 Latin dictionary files."
        )
        return

    # -- Tabs ----------------------------------------------------------------
    tab_dict, tab_stats = st.tabs(["📖  Dictionary", "📊  Statistics"])

    # ========================================================================
    # DICTIONARY TAB
    # ========================================================================
    with tab_dict:
        search_query = st.text_input(
            "🔍 Search",
            placeholder="Type a Latin word, inflected form, or translation…",
        )

        # Filter entries with fuzzy sortKey matching
        if search_query.strip():
            q = search_query.strip().lower()

            def _score(entry: dict) -> float:
                sk = (entry["sort_key"] or entry["lemma"]).lower()
                lm = entry["lemma"].lower()
                if q == sk or q == lm:
                    return 1.0
                if sk.startswith(q) or lm.startswith(q):
                    return 0.95
                if q in sk or q in lm:
                    return 0.85
                # check inflected forms
                if any(q in inf.lower() for inf in entry["inflected"]):
                    return 0.75
                # fuzzy on sortKey via difflib
                ratio = difflib.SequenceMatcher(None, q, sk).ratio()
                if ratio >= 0.55:
                    return ratio
                # translation match
                if any(q in t.lower() for t in _collect_all_translations(entry["senses"])):
                    return 0.5
                return 0.0

            scored = [(e, _score(e)) for e in all_entries]
            scored = [(e, s) for e, s in scored if s > 0.0]
            displayed_sorted = [e for e, _ in sorted(scored, key=lambda x: -x[1])]
        else:
            displayed_sorted = sorted(all_entries, key=lambda e: (e["sort_key"] or e["lemma"]).lower())

        match_label = f"**{len(displayed_sorted)}** fuzzy matches" if search_query.strip() else f"**{len(displayed_sorted)}** entries"
        st.caption(f"Showing {match_label} (of {len(all_entries)} total)")

        if not displayed_sorted:
            st.warning("No entries match your search.")
        else:
            for entry in displayed_sorted:
                render_entry(entry)

    # ========================================================================
    # STATISTICS TAB
    # ========================================================================
    with tab_stats:
        # Build flat dataframe
        rows = []
        for e in all_entries:
            rows.append({
                "Lemma": e["lemma"],
                "Part of Speech": POS_MAP.get(e["pos"], e["pos"]) if e["pos"] else "Unknown",
                "Gender": GENDER_MAP.get(e["gender"], e["gender"]) if e["gender"] else "",
                "Conjugation": e["itype"] if e["itype"] else "",
                "Source File": e["source_file"],
                "_pos_raw": e["pos"],
                "_gender_raw": e["gender"],
            })
        df = pd.DataFrame(rows)

        # -- Overview metrics ------------------------------------------------
        st.subheader("Overview")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Entries", len(df))
        c2.metric("Parts of Speech", df["Part of Speech"].nunique())
        c3.metric("Source Files", df["Source File"].nunique())
        genders_with_data = df[df["_gender_raw"] != ""]
        c4.metric("Nouns with Gender", len(genders_with_data))

        st.markdown("---")

        # -- Charts ----------------------------------------------------------
        col_pos, col_gen = st.columns(2)

        with col_pos:
            st.subheader("Parts of Speech")
            pos_counts = df["Part of Speech"].value_counts().reset_index()
            pos_counts.columns = ["Part of Speech", "Count"]
            fig_pos = px.pie(
                pos_counts,
                values="Count",
                names="Part of Speech",
                color_discrete_sequence=[
                    "#7B1818", "#A33030", "#C45E5E", "#D98080",
                    "#E8ADA0", "#F2CFC5", "#F9EAE4",
                ],
                hole=0.4,
            )
            fig_pos.update_traces(textposition="inside", textinfo="percent+label")
            fig_pos.update_layout(
                showlegend=True,
                margin=dict(t=10, b=10, l=10, r=10),
                legend=dict(font=dict(size=11)),
            )
            st.plotly_chart(fig_pos, use_container_width=True)

        with col_gen:
            st.subheader("Gender Distribution")
            gender_df = df[df["_gender_raw"] != ""].copy()
            if gender_df.empty:
                st.info("No gender data found in the loaded files.")
            else:
                gen_counts = gender_df["Gender"].value_counts().reset_index()
                gen_counts.columns = ["Gender", "Count"]
                fig_gen = px.pie(
                    gen_counts,
                    values="Count",
                    names="Gender",
                    color_discrete_sequence=["#7B1818", "#C45E5E", "#E8ADA0", "#F9EAE4"],
                    hole=0.4,
                )
                fig_gen.update_traces(textposition="inside", textinfo="percent+label")
                fig_gen.update_layout(
                    showlegend=True,
                    margin=dict(t=10, b=10, l=10, r=10),
                    legend=dict(font=dict(size=11)),
                )
                st.plotly_chart(fig_gen, use_container_width=True)

        # -- POS by file bar chart -------------------------------------------
        if df["Source File"].nunique() > 1:
            st.markdown("---")
            st.subheader("Parts of Speech by File")
            pos_file = (
                df.groupby(["Source File", "Part of Speech"])
                .size()
                .reset_index(name="Count")
            )
            fig_bar = px.bar(
                pos_file,
                x="Source File",
                y="Count",
                color="Part of Speech",
                color_discrete_sequence=[
                    "#7B1818", "#A33030", "#C45E5E", "#D98080",
                    "#E8ADA0", "#F2CFC5",
                ],
                barmode="stack",
            )
            fig_bar.update_layout(margin=dict(t=10, b=10))
            st.plotly_chart(fig_bar, use_container_width=True)

        # -- All words table -------------------------------------------------
        st.markdown("---")
        st.subheader("All Imported Words")

        # Filter controls
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            pos_opts = sorted(df["Part of Speech"].unique())
            pos_filter = st.multiselect("Filter by Part of Speech", options=pos_opts)
        with fc2:
            gen_opts = sorted(g for g in df["Gender"].unique() if g)
            gender_filter = st.multiselect("Filter by Gender", options=gen_opts)
        with fc3:
            file_opts = sorted(df["Source File"].unique())
            file_filter = st.multiselect("Filter by File", options=file_opts)

        filtered = df.copy()
        if pos_filter:
            filtered = filtered[filtered["Part of Speech"].isin(pos_filter)]
        if gender_filter:
            filtered = filtered[filtered["Gender"].isin(gender_filter)]
        if file_filter:
            filtered = filtered[filtered["Source File"].isin(file_filter)]

        display_cols = ["Lemma", "Part of Speech", "Gender", "Conjugation", "Source File"]
        display_df = filtered[display_cols].sort_values("Lemma").reset_index(drop=True)

        st.dataframe(display_df, use_container_width=True, hide_index=True)
        st.caption(f"{len(display_df)} words shown")

        # Download
        csv_data = display_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ Download as CSV",
            data=csv_data,
            file_name="lexicon_latinum_export.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
