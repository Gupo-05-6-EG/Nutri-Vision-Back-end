"""Relatorio de consumo e metas no periodo (RF30)."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.paciente import Paciente
from app.models.plano_alimentar import PlanoAlimentar
from app.models.refeicao import Refeicao
from app.models.usuario import Usuario
from app.services.gamificacao import FUSO_HORARIO


def gerar_relatorio(db: Session, paciente_id: int, inicio: date, fim: date) -> bytes:
    paciente = db.get(Paciente, paciente_id)
    usuario = db.get(Usuario, paciente_id)
    plano = db.scalar(
        select(PlanoAlimentar).where(
            PlanoAlimentar.paciente_id == paciente_id, PlanoAlimentar.ativo.is_(True)
        )
    )
    meta = plano.totais["meta_kcal"] if plano else paciente.meta_kcal
    de = datetime.combine(inicio, time.min, tzinfo=FUSO_HORARIO).astimezone(UTC)
    ate = datetime.combine(fim, time.max, tzinfo=FUSO_HORARIO).astimezone(UTC)
    refeicoes = db.scalars(
        select(Refeicao)
        .where(
            Refeicao.paciente_id == paciente_id,
            Refeicao.consumida_em >= de,
            Refeicao.consumida_em <= ate,
        )
        .options(selectinload(Refeicao.itens))
    ).all()
    dias = {
        inicio + timedelta(days=n): [0, Decimal(0), Decimal(0), Decimal(0), Decimal(0)]
        for n in range((fim - inicio).days + 1)
    }
    for refeicao in refeicoes:
        momento = refeicao.consumida_em
        if momento.tzinfo is None:
            momento = momento.replace(tzinfo=UTC)
        linha = dias[momento.astimezone(FUSO_HORARIO).date()]
        linha[0] += 1
        for item in refeicao.itens:
            for i, campo in enumerate(
                ("calorias_kcal", "proteinas_g", "carboidratos_g", "gorduras_g"), 1
            ):
                linha[i] += getattr(item, campo)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, title="Relatorio de evolucao - Nutri Vision", leftMargin=40, rightMargin=40
    )
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("Nutri Vision | Relatorio de evolucao", styles["Title"]),
        Paragraph(escape(usuario.nome), styles["Heading2"]),
        Paragraph(
            f"Periodo: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} (America/Sao_Paulo)", styles["Normal"]
        ),
        Spacer(1, 12),
        Paragraph("Consumo registrado x meta atual", styles["Heading2"]),
        Paragraph(
            "Dias sem registros aparecem como zero; isso nao comprova ausencia de consumo. "
            "A meta e a vigente na emissao, sem reconstruir metas historicas.",
            styles["Normal"],
        ),
    ]
    chart = LinePlot()
    chart.x, chart.y, chart.width, chart.height = 45, 30, 440, 150
    consumos = [(i, float(v[1])) for i, v in enumerate(dias.values())]
    chart.data = [consumos]
    if meta is not None:
        chart.data = [consumos, [(i, float(meta)) for i in range(len(dias))]]
    chart.lines[0].strokeColor = colors.HexColor("#157C72")
    chart.lines[1].strokeColor = colors.HexColor("#B75D22")
    if len(dias) == 1:
        chart.lines[0].symbol = makeMarker("FilledCircle")
        chart.lines[1].symbol = makeMarker("FilledSquare")
    chart.xValueAxis.valueMin = 0
    chart.xValueAxis.valueMax = max(1, len(dias) - 1)
    chart.yValueAxis.valueMin = 0
    chart.yValueAxis.valueMax = max(1, float(meta or 0), max(v[1] for v in consumos)) * 1.1
    drawing = Drawing(510, 210)
    drawing.add(chart)
    elements += [
        drawing,
        Paragraph(
            "Verde: consumo (kcal). "
            + ("Laranja: meta atual (kcal). " if meta is not None else "Sem meta cadastrada. ")
            + "Eixo X: dias desde o inicio do periodo.",
            styles["Normal"],
        ),
    ]
    tabela = [["Data", "Refeicoes", "kcal", "Prot. (g)", "Carb. (g)", "Gord. (g)"]]
    for dia, valores in dias.items():
        tabela.append(
            [dia.strftime("%d/%m/%Y"), str(valores[0]), *[f"{v:.1f}" for v in valores[1:]]]
        )
    table = Table(tabela, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#157C72")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ]
        )
    )
    elements += [
        Spacer(1, 16),
        table,
        Spacer(1, 12),
        Paragraph(
            f"Total: {sum(v[0] for v in dias.values())} refeicoes; "
            f"{sum(v[1] for v in dias.values()):.1f} kcal registradas. "
            f"Meta diaria atual: {f'{meta:.1f} kcal' if meta is not None else 'nao definida'}.",
            styles["Normal"],
        ),
    ]

    def rodape(canvas, document):
        canvas.setFont("Helvetica", 9)
        canvas.drawString(
            40, 25, "Dados pessoais de saude | Uso do paciente e nutricionista vinculado"
        )
        canvas.drawRightString(550, 25, str(document.page))

    doc.build(elements, onFirstPage=rodape, onLaterPages=rodape)
    return buffer.getvalue()
