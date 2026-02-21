import io
from datetime import date, timezone as dt_timezone
from typing import Optional

from django.http import HttpResponse
from django.utils import timezone
from ninja import Router
from ninja_jwt.authentication import JWTAuth
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from reports.models import AuditLog

router = Router(tags=['L. Reports & Analytics'])

# Cap the number of rows in one PDF export to avoid memory exhaustion.
AUDIT_LOG_MAX_ROWS = 2000


@router.get('/audit-log', auth=JWTAuth())
def audit_log_report(
    request,
    entity: Optional[str] = None,
    action: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    """
    Generate a PDF report of the audit log, optionally filtered by entity, action, and date
    range. Returns a downloadable PDF file.

    At most {max_rows} rows are included per export to avoid memory exhaustion.
    """.format(max_rows=AUDIT_LOG_MAX_ROWS)
    qs = AuditLog.objects.select_related('actor').order_by('-ts')

    if entity:
        qs = qs.filter(entity=entity)
    if action:
        qs = qs.filter(action=action)
    if start_date:
        qs = qs.filter(ts__date__gte=start_date)
    if end_date:
        qs = qs.filter(ts__date__lte=end_date)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ReportTitle', parent=styles['Title'], spaceAfter=8)
    elements = []

    elements.append(Paragraph('Audit Log Report', title_style))

    # Subtitle: applied filters + generation timestamp (always UTC)
    now_utc = timezone.now().astimezone(dt_timezone.utc)
    filter_parts = [f'Generated: {now_utc.strftime("%Y-%m-%d %H:%M UTC")}']
    if entity:
        filter_parts.append(f'Entity: {entity}')
    if action:
        filter_parts.append(f'Action: {action}')
    if start_date:
        filter_parts.append(f'From: {start_date}')
    if end_date:
        filter_parts.append(f'To: {end_date}')
    elements.append(Paragraph(' | '.join(filter_parts), styles['Normal']))
    elements.append(Spacer(1, 0.5 * cm))

    col_headers = ['Timestamp', 'Entity', 'Entity ID', 'Action', 'Actor']
    data = [col_headers]

    entries = list(qs[:AUDIT_LOG_MAX_ROWS])
    if entries:
        for entry in entries:
            actor_label = entry.actor.email if entry.actor else '\u2014'
            entity_id_label = str(entry.entity_id) if entry.entity_id else '\u2014'
            data.append([
                entry.ts.strftime('%Y-%m-%d %H:%M'),
                entry.entity,
                entity_id_label,
                entry.action,
                actor_label,
            ])
    else:
        data.append(['No records found.', '', '', '', ''])

    # Column widths sized to fill the printable width of landscape A4 (26.7 cm after margins)
    col_widths = [4 * cm, 4 * cm, 6.7 * cm, 4 * cm, 8 * cm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a3a5c')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f2f2f2')]),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#cccccc')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="audit-log-report.pdf"'
    return response