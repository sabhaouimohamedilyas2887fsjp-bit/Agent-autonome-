"""
Email alert sender using SMTP (supports Gmail / Office 365 / any SMTP).
"""
from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from string import Template
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database.models import AnalysisORM, LegalDocumentORM

logger = logging.getLogger(__name__)

HTML_TEMPLATE = Template("""
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <style>
    body { font-family: Arial, sans-serif; font-size: 14px; color: #222; }
    .header { background: #c0392b; color: white; padding: 16px 24px; }
    .badge { display:inline-block; padding:3px 10px; border-radius:12px;
             font-weight:bold; font-size:12px; }
    .critique { background:#c0392b; color:white; }
    .élevé    { background:#e67e22; color:white; }
    .modéré   { background:#f1c40f; color:#222; }
    .faible   { background:#27ae60; color:white; }
    .card { border:1px solid #ddd; border-radius:6px; padding:16px; margin:12px 0; }
    .label { font-weight:bold; color:#555; }
    ul { margin:4px 0; padding-left:18px; }
    a { color:#2980b9; }
  </style>
</head>
<body>
  <div class="header">
    <h2 style="margin:0">⚖️ Veille Juridique Maroc – Alerte</h2>
  </div>
  <div style="padding:20px">
    <div class="card">
      <p>
        <span class="badge $impact_class">$impact_level</span>
        &nbsp;Score de criticité : <strong>$score / 100</strong>
      </p>
      <p><span class="label">Source :</span> $source &nbsp;|&nbsp;
         <span class="label">Type :</span> $doc_type</p>
      <h3 style="margin:8px 0"><a href="$url">$title</a></h3>
      <p><span class="label">Date de publication :</span> $pub_date</p>
      <hr>
      <p><span class="label">Résumé :</span><br>$summary</p>
      <p><span class="label">Points clés :</span></p>
      <ul>$key_points_html</ul>
      <p><span class="label">Secteurs impactés :</span> $sectors</p>
      <p><span class="label">Obligations :</span></p>
      <ul>$obligations_html</ul>
      <p><span class="label">Échéances :</span> $deadlines</p>
    </div>
    <p style="color:#999;font-size:12px">
      Généré automatiquement par l'agent de veille juridique marocaine.
    </p>
  </div>
</body>
</html>
""")


@dataclass
class EmailConfig:
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    from_address: str
    use_tls: bool = True


class EmailAlert:
    def __init__(self, config: EmailConfig, recipients: list[str]):
        self.config = config
        self.recipients = recipients

    def send(self, doc: LegalDocumentORM, analysis: AnalysisORM) -> bool:
        if not self.recipients:
            logger.warning("No email recipients configured.")
            return False

        subject = f"[Veille Juridique] {analysis.impact_level.upper()} – {doc.title[:80]}"
        html_body = self._render(doc, analysis)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.config.from_address
        msg["To"] = ", ".join(self.recipients)
        msg.attach(MIMEText(self._plain_text(doc, analysis), "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            if self.config.use_tls:
                server = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port)

            server.login(self.config.username, self.config.password)
            server.sendmail(self.config.from_address, self.recipients, msg.as_string())
            server.quit()
            logger.info("Email sent to %d recipients for doc id=%d", len(self.recipients), doc.id)
            return True
        except Exception as exc:
            logger.error("Email send failed: %s", exc)
            return False

    # ------------------------------------------------------------------

    def _render(self, doc: LegalDocumentORM, analysis: AnalysisORM) -> str:
        kp_html = "".join(f"<li>{p}</li>" for p in (analysis.key_points or []))
        ob_html = "".join(f"<li>{o}</li>" for o in (analysis.obligations or []))
        return HTML_TEMPLATE.substitute(
            impact_class=analysis.impact_level,
            impact_level=analysis.impact_level.capitalize(),
            score=int(analysis.criticality_score),
            source=doc.source,
            doc_type=doc.doc_type,
            url=doc.url,
            title=doc.title,
            pub_date=doc.published_date.strftime("%d/%m/%Y") if doc.published_date else "N/A",
            summary=analysis.summary,
            key_points_html=kp_html or "<li>N/A</li>",
            sectors=", ".join(analysis.affected_sectors or []) or "N/A",
            obligations_html=ob_html or "<li>N/A</li>",
            deadlines=", ".join(analysis.deadlines or []) or "N/A",
        )

    def _plain_text(self, doc: LegalDocumentORM, analysis: AnalysisORM) -> str:
        return (
            f"VEILLE JURIDIQUE MAROC – ALERTE {analysis.impact_level.upper()}\n"
            f"Score: {int(analysis.criticality_score)}/100\n\n"
            f"Source : {doc.source}\n"
            f"Titre  : {doc.title}\n"
            f"URL    : {doc.url}\n\n"
            f"Résumé:\n{analysis.summary}\n"
        )
