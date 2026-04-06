"""
Main entry point for the Moroccan legal monitoring agent.

Usage:
    python main.py                  # run pipeline once
    python main.py --dashboard      # start web dashboard
    python main.py --schedule       # start scheduler (blocking)
"""
# --- path anchor: must be before any project imports ---
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
# -------------------------------------------------------

# Force UTF-8 on Windows console so Arabic/French chars don't crash logging
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import logging
import os
import sys

import yaml
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("veille_juridique.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_pipeline(config: dict | None = None) -> None:
    """Core pipeline: scrape → score → analyze → store → alert."""
    if config is None:
        config = load_config()

    from scrapers import ALL_SCRAPERS
    from analyzer.claude_analyzer import ClaudeAnalyzer
    from analyzer.criticality_scorer import CriticalityScorer
    from database.db_manager import DBManager
    from alerts.email_alert import EmailAlert, EmailConfig
    from alerts.slack_alert import SlackAlert

    db_url = config.get("database", {}).get("url") or os.getenv("DATABASE_URL", "sqlite:///veille_juridique.db")
    db = DBManager(db_url)

    scorer = CriticalityScorer()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    analyzer = ClaudeAnalyzer(api_key=api_key, model=config.get("claude", {}).get("model"))

    # Build alert senders
    email_cfg_raw = config.get("alerts", {}).get("email", {})
    email_alert = None
    if email_cfg_raw.get("enabled") and os.getenv("SMTP_PASSWORD"):
        email_alert = EmailAlert(
            config=EmailConfig(
                smtp_host=email_cfg_raw.get("smtp_host", "smtp.gmail.com"),
                smtp_port=int(email_cfg_raw.get("smtp_port", 587)),
                username=os.getenv("SMTP_USERNAME", ""),
                password=os.getenv("SMTP_PASSWORD", ""),
                from_address=os.getenv("SMTP_FROM", os.getenv("SMTP_USERNAME", "")),
            ),
            recipients=email_cfg_raw.get("recipients", []),
        )

    slack_webhook = os.getenv("SLACK_WEBHOOK_URL", "")
    slack_alert = SlackAlert(slack_webhook) if slack_webhook else None

    min_score = config.get("analysis", {}).get("min_criticality_score", 20)
    alert_threshold = config.get("alerts", {}).get("min_score_to_alert", 50)

    total_new = 0
    total_alerted = 0

    for ScraperClass in ALL_SCRAPERS:
        scraper = ScraperClass()
        documents = scraper.scrape()
        logger.info("  %s: %d documents scraped", scraper.SOURCE_NAME, len(documents))

        for doc in documents:
            # 1. Persist document (skip if already known)
            orm_doc = db.upsert_document(doc)
            if db.has_analysis(orm_doc.id):
                continue   # already analyzed
            total_new += 1

            # 2. Quick criticality score (no API)
            score_result = scorer.score(doc)
            logger.debug("    Score %d – %s", score_result.score, doc.title[:60])

            # 3. Claude analysis (only if above threshold)
            if score_result.score >= min_score:
                analysis_result = analyzer.analyze(doc)
                # Override impact_level if scorer is more conservative
                if score_result.score >= 75 and analysis_result.impact_level == "faible":
                    analysis_result.impact_level = score_result.level
            else:
                from analyzer.claude_analyzer import AnalysisResult
                analysis_result = AnalysisResult(
                    summary="Document de faible criticité – analyse non effectuée.",
                    impact_level=score_result.level,
                )

            # 4. Save analysis
            db.save_analysis(
                document_id=orm_doc.id,
                result=analysis_result,
                criticality_score=float(score_result.score),
                model_used=analyzer.model,
            )

            # 5. Send alerts if above alert threshold
            if score_result.score >= alert_threshold:
                full_doc = db.get_document_with_analysis(orm_doc.id)
                if full_doc and full_doc.analysis:
                    if email_alert and not db.already_alerted(orm_doc.id, "email"):
                        success = email_alert.send(full_doc, full_doc.analysis)
                        db.log_alert(orm_doc.id, "email", success=success)
                        if success:
                            total_alerted += 1
                    if slack_alert and not db.already_alerted(orm_doc.id, "slack"):
                        success = slack_alert.send(full_doc, full_doc.analysis)
                        db.log_alert(orm_doc.id, "slack", success=success)

    logger.info("Pipeline complete: %d new documents, %d alerts sent.", total_new, total_alerted)


def add_document_interactive(config: dict | None = None) -> None:
    """Interactive CLI to manually add a legal document."""
    from database.document_service import insert_document
    from analyzer.claude_analyzer import AnalysisResult

    db_url = (config or {}).get("database", {}).get("url") or os.getenv("DATABASE_URL", "sqlite:///veille_juridique.db")

    print("\n=== Ajout manuel d'un document juridique ===\n")

    title     = input("Titre *                        : ").strip()
    if not title:
        print("❌ Le titre est obligatoire.")
        return
    url       = input("URL (laisser vide si absent)   : ").strip()
    source    = input("Source (ex: SGG, CNDP…)        : ").strip() or "Manuel"
    doc_type  = input("Type (décret/loi/arrêté/…)     : ").strip() or "autre"
    reference = input("Référence (n° …)               : ").strip()
    date_str  = input("Date de publication (JJ/MM/AAAA): ").strip()
    print("Contenu / texte intégral (terminer par une ligne vide) :")
    lines = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)
    content = "\n".join(lines)

    pub_date = None
    if date_str:
        try:
            pub_date = datetime.strptime(date_str, "%d/%m/%Y")
        except ValueError:
            print("⚠️  Date ignorée (format invalide, attendu JJ/MM/AAAA).")

    use_claude = input("\nAnalyser automatiquement avec Claude ? (o/N) : ").strip().lower() == "o"
    summary      = ""
    impact_level = "faible"
    if not use_claude:
        summary      = input("Résumé (optionnel)                          : ").strip()
        impact_level = input("Impact (faible/modéré/élevé/critique)       : ").strip() or "faible"

    ok, msg = insert_document(
        title=title, url=url, source=source, doc_type=doc_type,
        content=content, reference=reference, published_date=pub_date,
        db_url=db_url, summary=summary, impact_level=impact_level,
        analyze_with_claude=use_claude,
    )
    print(f"{'✅' if ok else '❌'} {msg}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Moroccan Legal Monitoring Agent")
    parser.add_argument("--schedule", action="store_true", help="Start the scheduler (blocking)")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--add", action="store_true", help="Add a document manually (interactive)")
    parser.add_argument("--delete", type=int, metavar="ID", help="Delete a document by its ID")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.delete:
        from database.db_manager import DBManager
        db_url = config.get("database", {}).get("url") or os.getenv("DATABASE_URL", "sqlite:///veille_juridique.db")
        db = DBManager(db_url)
        confirm = input(f"Supprimer le document id={args.delete} ? (o/N) : ").strip().lower()
        if confirm == "o":
            found = db.delete_document(args.delete)
            print("✅ Supprimé." if found else f"❌ Aucun document avec id={args.delete}.")
        else:
            print("Annulé.")

    elif args.add:
        add_document_interactive(config)

    elif args.schedule:
        from scheduler import build_scheduler
        scheduler = build_scheduler(config)
        logger.info("Running pipeline once before starting scheduler...")
        run_pipeline(config)
        scheduler.start()

    else:
        run_pipeline(config)


if __name__ == "__main__":
    main()
