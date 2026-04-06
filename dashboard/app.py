"""
Streamlit dashboard for Moroccan legal monitoring agent.
Run:  python -m streamlit run dashboard/app.py
"""
# --- path anchor ---
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
# -------------------

import os
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, desc, func, select
from sqlalchemy.orm import Session, selectinload

from database.models import AnalysisORM, Base, LegalDocumentORM
from database.document_service import insert_document

# ── page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Veille Juridique Maroc",
    page_icon="⚖️",
    layout="wide",
)

DB_URL = os.getenv("DATABASE_URL", "sqlite:///veille_juridique.db")

IMPACT_COLOURS = {
    "critique": "#E65100",   # orange brûlé
    "élevé":    "#F57F17",   # jaune foncé
    "modéré":   "#F9A825",   # jaune principal
    "faible":   "#FFF176",   # jaune très clair
}

IMPACT_EMOJI = {
    "critique": "🔴",
    "élevé":    "🟠",
    "modéré":   "🟡",
    "faible":   "🟢",
}

DOC_TYPES = [
    "dahir", "loi", "décret", "arrêté", "circulaire",
    "ordonnance", "délibération", "décision", "avis",
    "alerte sécurité", "arrêt", "jurisprudence",
    "texte législatif", "texte réglementaire", "autre",
]

KNOWN_SOURCES = [
    "Bulletin Officiel", "SGG", "CNDP", "DGSSI",
    "ANRT", "Cour de Cassation", "Manuel", "Autre",
]

# ── DB helpers ─────────────────────────────────────────────────────────────────

@st.cache_resource
def get_engine():
    engine = create_engine(DB_URL, future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine


def load_documents(days: int, source: str, impact: str) -> list[LegalDocumentORM]:
    engine = get_engine()
    cutoff = datetime.utcnow() - timedelta(days=days)
    with Session(engine) as s:
        q = (
            select(LegalDocumentORM)
            .options(selectinload(LegalDocumentORM.analysis))
            .where(LegalDocumentORM.scraped_at >= cutoff)
            .order_by(desc(LegalDocumentORM.scraped_at))
        )
        if source:
            q = q.where(LegalDocumentORM.source == source)
        if impact:
            q = q.join(AnalysisORM).where(AnalysisORM.impact_level == impact)
        return s.execute(q.limit(500)).scalars().all()


def load_stats() -> dict:
    engine = get_engine()
    with Session(engine) as s:
        total    = s.execute(select(func.count()).select_from(LegalDocumentORM)).scalar()
        analyzed = s.execute(select(func.count()).select_from(AnalysisORM)).scalar()
        high     = s.execute(
            select(func.count()).select_from(AnalysisORM)
            .where(AnalysisORM.impact_level.in_(["critique", "élevé"]))
        ).scalar()
        sources  = s.execute(
            select(func.count(LegalDocumentORM.source.distinct()))
        ).scalar()
    return {"total": total, "analyzed": analyzed, "high": high, "sources": sources}


def load_sources() -> list[str]:
    engine = get_engine()
    with Session(engine) as s:
        rows = s.execute(select(LegalDocumentORM.source).distinct()).all()
    return sorted(r[0] for r in rows)


def load_score_distribution() -> pd.DataFrame:
    engine = get_engine()
    with Session(engine) as s:
        rows = s.execute(
            select(AnalysisORM.impact_level, func.count().label("n"))
            .group_by(AnalysisORM.impact_level)
        ).all()
    return pd.DataFrame(rows, columns=["Niveau", "Nombre"])


def search_documents(query: str, limit: int = 30) -> list[LegalDocumentORM]:
    """Full-text search on title, reference, content and tags."""
    engine = get_engine()
    q = query.strip().lower()
    with Session(engine) as s:
        rows = s.execute(
            select(LegalDocumentORM)
            .options(selectinload(LegalDocumentORM.analysis))
            .where(
                LegalDocumentORM.title.ilike(f"%{q}%")
                | LegalDocumentORM.reference.ilike(f"%{q}%")
                | LegalDocumentORM.content.ilike(f"%{q}%")
                | LegalDocumentORM.source.ilike(f"%{q}%")
            )
            .order_by(desc(LegalDocumentORM.scraped_at))
            .limit(limit)
        ).scalars().all()
    return rows


def load_timeline(days: int) -> pd.DataFrame:
    engine = get_engine()
    cutoff = datetime.utcnow() - timedelta(days=days)
    with Session(engine) as s:
        rows = s.execute(
            select(LegalDocumentORM.scraped_at, LegalDocumentORM.source)
            .where(LegalDocumentORM.scraped_at >= cutoff)
            .order_by(LegalDocumentORM.scraped_at)
        ).all()
    if not rows:
        return pd.DataFrame(columns=["date", "source"])
    df = pd.DataFrame(rows, columns=["date", "source"])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.groupby("date").size().reset_index(name="documents")


# ── sidebar ────────────────────────────────────────────────────────────────────

st.sidebar.title("⚖️ Veille Juridique")
st.sidebar.caption("Maroc — Monitoring légal automatisé")
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigation",
    ["📋 Documents", "🔍 Recherche & Chat", "➕ Ajouter un document", "🔧 Lancer un scraping"],
    label_visibility="collapsed",
)

st.sidebar.divider()

# Filters (only relevant on Documents page)
if page == "📋 Documents":
    days = st.sidebar.selectbox(
        "Période", [1, 7, 30, 90], index=1,
        format_func=lambda d: f"{d} derniers jours",
    )
    sources_list = [""] + load_sources()
    source_filter = st.sidebar.selectbox(
        "Source", sources_list,
        format_func=lambda s: s or "Toutes les sources",
    )
    impact_filter = st.sidebar.selectbox(
        "Niveau d'impact",
        ["", "critique", "élevé", "modéré", "faible"],
        format_func=lambda i: i.capitalize() if i else "Tous les niveaux",
    )
else:
    days, source_filter, impact_filter = 7, "", ""

st.sidebar.divider()
if st.sidebar.button("🔄 Rafraîchir", use_container_width=True):
    st.cache_resource.clear()
    st.rerun()
st.sidebar.caption(f"Mis à jour : {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE : Documents
# ══════════════════════════════════════════════════════════════════════════════

if page == "📋 Documents":
    st.title("⚖️ Veille Juridique — Maroc")

    stats = load_stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Documents totaux",      stats["total"])
    c2.metric("Analysés par Claude",   stats["analyzed"])
    c3.metric("Impact élevé/critique", stats["high"])
    c4.metric("Sources actives",       stats["sources"])

    st.divider()

    col_left, col_right = st.columns([2, 1])
    with col_left:
        st.subheader("Documents collectés par jour")
        timeline_df = load_timeline(days)
        if not timeline_df.empty:
            st.bar_chart(timeline_df.set_index("date")["documents"])
        else:
            st.info("Aucune donnée pour cette période.")

    with col_right:
        st.subheader("Répartition par impact")
        dist_df = load_score_distribution()
        if not dist_df.empty:
            order = ["critique", "élevé", "modéré", "faible"]
            dist_df["Niveau"] = pd.Categorical(dist_df["Niveau"], categories=order, ordered=True)
            dist_df = dist_df.sort_values("Niveau")
            st.bar_chart(dist_df.set_index("Niveau")["Nombre"])
        else:
            st.info("Aucune analyse disponible.")

    st.divider()

    docs = load_documents(days, source_filter, impact_filter)
    st.subheader(f"Documents juridiques ({len(docs)})")

    if not docs:
        st.warning("Aucun document trouvé pour les filtres sélectionnés.")
    else:
        from database.db_manager import DBManager
        db = DBManager(DB_URL)

        for doc in docs:
            analysis = doc.analysis
            impact   = analysis.impact_level if analysis else "—"
            score    = int(analysis.criticality_score) if analysis else 0
            emoji    = IMPACT_EMOJI.get(impact, "⚪")
            colour   = IMPACT_COLOURS.get(impact, "#95a5a6")

            with st.expander(f"{emoji} **{doc.title[:100]}** — *{doc.source}* · {doc.doc_type}"):
                col1, col2, col3 = st.columns([2, 1, 1])
                col1.markdown(f"**Source :** {doc.source}  \n**Type :** {doc.doc_type}")
                col2.markdown(
                    f"**Impact :** "
                    f"<span style='color:{colour};font-weight:bold'>{impact.capitalize()}</span>",
                    unsafe_allow_html=True,
                )
                col3.markdown(f"**Score :** {score}/100")

                if doc.published_date:
                    st.caption(f"Publié le {doc.published_date.strftime('%d/%m/%Y')}")
                if doc.url and not doc.url.startswith("manuel://"):
                    st.markdown(f"[Voir le document original]({doc.url})")

                if analysis and analysis.summary:
                    st.markdown("**Résumé :**")
                    st.write(analysis.summary)
                if analysis and analysis.key_points:
                    st.markdown("**Points clés :**")
                    for pt in analysis.key_points:
                        st.markdown(f"- {pt}")

                row2_a, row2_b = st.columns(2)
                if analysis and analysis.affected_sectors:
                    row2_a.markdown("**Secteurs impactés :**")
                    row2_a.write(", ".join(analysis.affected_sectors))
                if analysis and analysis.deadlines:
                    row2_b.markdown("**Échéances :**")
                    row2_b.write("\n".join(f"- {d}" for d in analysis.deadlines))
                if analysis and analysis.obligations:
                    st.markdown("**Obligations :**")
                    for ob in analysis.obligations:
                        st.markdown(f"- {ob}")
                if analysis and analysis.tags:
                    st.markdown(" ".join(f"`{t}`" for t in analysis.tags))

                # ── Suppression ───────────────────────────────────────────────
                st.divider()
                confirm_key = f"confirm_delete_{doc.id}"
                if st.session_state.get(confirm_key):
                    st.warning(f"⚠️ Confirmer la suppression de **« {doc.title[:60]} »** ?")
                    c_yes, c_no, _ = st.columns([1, 1, 4])
                    if c_yes.button("✅ Oui, supprimer", key=f"yes_{doc.id}", type="primary"):
                        db.delete_document(doc.id)
                        st.session_state.pop(confirm_key, None)
                        st.success("Document supprimé.")
                        st.cache_resource.clear()
                        st.rerun()
                    if c_no.button("❌ Annuler", key=f"no_{doc.id}"):
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
                else:
                    if st.button("🗑️ Supprimer ce document", key=f"del_{doc.id}"):
                        st.session_state[confirm_key] = True
                        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE : Ajouter un document
# ══════════════════════════════════════════════════════════════════════════════

elif page == "➕ Ajouter un document":
    st.title("➕ Ajouter un document")
    st.caption("Saisissez les informations du document juridique à intégrer dans la base.")

    with st.form("form_add_doc", clear_on_submit=True):
        st.subheader("Informations principales")
        col_a, col_b = st.columns(2)
        title     = col_a.text_input("Titre *", placeholder="Dahir n° 1-09-15 relatif à…")
        reference = col_b.text_input("Référence", placeholder="n° 1-09-15")

        col_c, col_d = st.columns(2)
        source   = col_c.selectbox("Source *", KNOWN_SOURCES)
        doc_type = col_d.selectbox("Type de document *", DOC_TYPES)

        url = st.text_input("URL du document", placeholder="https://www.sgg.gov.ma/…  (laisser vide si non disponible)")
        pub_date = st.date_input("Date de publication", value=None)
        content  = st.text_area("Contenu / texte intégral", height=180,
                                placeholder="Collez ici le texte du document (facultatif mais recommandé pour l'analyse)…")

        st.divider()
        st.subheader("Analyse")
        analyze_claude = st.checkbox(
            "🤖 Analyser automatiquement avec Claude",
            value=bool(os.getenv("ANTHROPIC_API_KEY")),
            help="Nécessite une clé API Anthropic avec des crédits disponibles.",
        )

        if not analyze_claude:
            st.caption("Ou renseignez l'analyse manuellement :")
            col_e, col_f = st.columns(2)
            impact_manual = col_e.selectbox("Niveau d'impact", ["faible", "modéré", "élevé", "critique"])
            score_manual  = col_f.slider("Score de criticité", 0, 100, 20)
            summary_manual = st.text_area("Résumé", height=100)
            sectors_manual = st.text_input("Secteurs impactés (séparés par des virgules)")
            obligations_manual = st.text_area("Obligations (une par ligne)", height=80)
            deadlines_manual   = st.text_input("Échéances (séparées par des virgules)")
            tags_manual        = st.text_input("Tags (séparés par des virgules)")
        else:
            impact_manual = "faible"
            score_manual  = 0
            summary_manual = sectors_manual = obligations_manual = deadlines_manual = tags_manual = ""

        submitted = st.form_submit_button("💾 Enregistrer le document", use_container_width=True)

    if submitted:
        if not title:
            st.error("Le titre est obligatoire.")
        else:
            pub_dt = datetime(pub_date.year, pub_date.month, pub_date.day) if pub_date else None

            ok, msg = insert_document(
                title=title,
                url=url.strip(),
                source=source,
                doc_type=doc_type,
                content=content,
                reference=reference,
                published_date=pub_dt,
                analyze_with_claude=analyze_claude,
                summary=summary_manual,
                impact_level=impact_manual,
                criticality_score=float(score_manual),
                affected_sectors=[s.strip() for s in sectors_manual.split(",") if s.strip()],
                obligations=[o.strip() for o in obligations_manual.splitlines() if o.strip()],
                deadlines=[d.strip() for d in deadlines_manual.split(",") if d.strip()],
                tags=[t.strip() for t in tags_manual.split(",") if t.strip()],
            )
            if ok:
                st.success(msg)
                st.cache_resource.clear()
            else:
                st.error(msg)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE : Lancer un scraping
# ══════════════════════════════════════════════════════════════════════════════

elif page == "🔧 Lancer un scraping":
    st.title("🔧 Lancer un scraping")
    st.caption("Déclenche manuellement la collecte sur une ou plusieurs sources.")

    from scrapers import ALL_SCRAPERS

    scraper_map = {S.SOURCE_NAME: S for S in ALL_SCRAPERS}
    selected = st.multiselect(
        "Sources à scraper",
        options=list(scraper_map.keys()),
        default=list(scraper_map.keys()),
    )

    analyze = st.checkbox(
        "🤖 Analyser avec Claude après scraping",
        value=False,
        help="Nécessite une clé API Anthropic avec des crédits disponibles.",
    )

    if st.button("🚀 Lancer", use_container_width=True, type="primary"):
        if not selected:
            st.warning("Sélectionnez au moins une source.")
        else:
            from database.db_manager import DBManager
            from analyzer.criticality_scorer import CriticalityScorer
            from analyzer.claude_analyzer import ClaudeAnalyzer, AnalysisResult

            db      = DBManager(DB_URL)
            scorer  = CriticalityScorer()
            analyzer = ClaudeAnalyzer() if (analyze and os.getenv("ANTHROPIC_API_KEY")) else None

            progress = st.progress(0, text="Démarrage…")
            log      = st.empty()
            lines: list[str] = []

            for i, name in enumerate(selected):
                progress.progress((i) / len(selected), text=f"Scraping : {name}…")
                scraper = scraper_map[name]()
                docs    = scraper.scrape()
                new = 0
                for doc in docs:
                    orm_doc = db.upsert_document(doc)
                    if db.has_analysis(orm_doc.id):
                        continue
                    new += 1
                    score_result = scorer.score(doc)
                    if analyzer:
                        result = analyzer.analyze(doc)
                    else:
                        result = AnalysisResult(
                            summary="Non analysé.",
                            impact_level=score_result.level,
                        )
                    db.save_analysis(
                        document_id=orm_doc.id,
                        result=result,
                        criticality_score=float(score_result.score),
                        model_used=analyzer.model if analyzer else "scorer",
                    )
                lines.append(f"✅ **{name}** — {len(docs)} collectés, {new} nouveaux")
                log.markdown("\n\n".join(lines))

            progress.progress(1.0, text="Terminé !")
            st.success("Scraping terminé. Allez sur **📋 Documents** pour voir les résultats.")
            st.cache_resource.clear()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE : Recherche & Chat
# ══════════════════════════════════════════════════════════════════════════════

elif page == "🔍 Recherche & Chat":
    st.title("🔍 Recherche & Chat juridique")
    st.caption("Recherchez des documents ou posez une question à Claude sur la base juridique marocaine.")

    # ── Barre de recherche ────────────────────────────────────────────────────
    with st.form("search_form", clear_on_submit=False):
        col_input, col_btn = st.columns([5, 1])
        query = col_input.text_input(
            "🔎 Rechercher un document",
            placeholder="Ex : protection des données, décret, CNDP, loi 09-08…",
            label_visibility="collapsed",
            key="search_query",
        )
        submitted = col_btn.form_submit_button("Rechercher", use_container_width=True)

    if submitted and query:
        results = search_documents(query)
        if results:
            st.markdown(f"**{len(results)} résultat(s) pour « {query} »**")
            for doc in results:
                analysis = doc.analysis
                impact   = analysis.impact_level if analysis else "—"
                score    = int(analysis.criticality_score) if analysis else 0
                emoji    = IMPACT_EMOJI.get(impact, "⚪")
                colour   = IMPACT_COLOURS.get(impact, "#888")

                with st.expander(f"{emoji} **{doc.title[:100]}** — *{doc.source}*"):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    col1.markdown(f"**Source :** {doc.source}  \n**Type :** {doc.doc_type}")
                    col2.markdown(
                        f"**Impact :** <span style='color:{colour};font-weight:bold'>"
                        f"{impact.capitalize()}</span>",
                        unsafe_allow_html=True,
                    )
                    col3.markdown(f"**Score :** {score}/100")
                    if doc.url and not doc.url.startswith("manuel://"):
                        st.markdown(f"[Voir le document original]({doc.url})")
                    if analysis and analysis.summary:
                        st.write(analysis.summary)
                    if analysis and analysis.tags:
                        st.markdown(" ".join(f"`{t}`" for t in analysis.tags))
        else:
            st.info("Aucun document trouvé pour cette recherche.")

    st.divider()

    # ── Chat ──────────────────────────────────────────────────────────────────
    st.subheader("💬 Chat avec Claude")
    st.caption("Posez une question — Claude consulte la base de documents pour vous répondre.")

    if not os.getenv("ANTHROPIC_API_KEY"):
        st.warning("Clé API Anthropic manquante. Définissez `ANTHROPIC_API_KEY` dans votre fichier `.env`.")
    else:
        # Initialise l'historique de chat en session
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        # Affiche l'historique
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        user_input = st.chat_input("Votre question juridique…")

        if user_input:
            # Affiche le message utilisateur
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)

            # Recherche de documents pertinents comme contexte
            context_docs = search_documents(user_input, limit=5)
            context_text = ""
            if context_docs:
                context_text = "\n\n---\n".join(
                    f"**{d.title}** ({d.source}, {d.doc_type})\n"
                    + (d.analysis.summary if d.analysis else d.content[:500] or "")
                    for d in context_docs
                )

            system_prompt = (
                "Tu es un assistant juridique expert en droit marocain. "
                "Réponds en français, de manière claire et structurée. "
                "Appuie tes réponses sur les documents fournis quand ils sont pertinents."
            )

            user_prompt = user_input
            if context_text:
                user_prompt = (
                    f"{user_input}\n\n"
                    f"[Documents pertinents dans la base :]\n{context_text}"
                )

            # Appel Claude
            import anthropic as _anthropic
            _client = _anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

            with st.chat_message("assistant"):
                with st.spinner("Claude réfléchit…"):
                    try:
                        response = _client.messages.create(
                            model="claude-sonnet-4-6",
                            max_tokens=1024,
                            system=system_prompt,
                            messages=[
                                {"role": m["role"], "content": m["content"]}
                                for m in st.session_state.chat_history
                                if m["role"] in ("user", "assistant")
                            ] + ([{"role": "user", "content": user_prompt}]
                                 if context_text else []),
                        )
                        answer = response.content[0].text
                    except Exception as e:
                        answer = f"Erreur API : {e}"

                st.markdown(answer)

            st.session_state.chat_history.append({"role": "assistant", "content": answer})

        # Bouton pour effacer l'historique
        if st.session_state.get("chat_history"):
            if st.button("🗑️ Effacer la conversation", use_container_width=False):
                st.session_state.chat_history = []
                st.rerun()
