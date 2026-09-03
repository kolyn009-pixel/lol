import os
from datetime import datetime
import database

def create_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    outdir=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'exports'); os.makedirs(outdir,exist_ok=True)
    path=os.path.join(outdir,f'tutor_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
    wb=Workbook(); wb.remove(wb.active); conn=database.connect()
    specs=[('Ученики','SELECT id,name,grade,phone,study_goal,main_subject,active,created_at FROM users ORDER BY name'),('Занятия','SELECT id,user_id,study_goal,subject,start_time,duration_minutes,price,payment_status,lesson_status FROM lessons ORDER BY start_time DESC'),('Оплаты','SELECT id,user_id,payment_type,lessons_count,price_per_lesson,total_amount,status,created_at,confirmed_at FROM payments ORDER BY id DESC')]
    for title,sql in specs:
        rows=conn.execute(sql).fetchall(); ws=wb.create_sheet(title); ws.sheet_view.showGridLines=False
        if not rows: continue
        headers=rows[0].keys(); ws.append(list(headers))
        for cell in ws[1]: cell.font=Font(bold=True,color='FFFFFF'); cell.fill=PatternFill('solid',fgColor='1F4E78'); cell.alignment=Alignment(horizontal='center')
        for r in rows: ws.append([r[h] for h in headers])
        ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
        for col in ws.columns:
            width=min(max(len(str(c.value or '')) for c in col)+2,40); ws.column_dimensions[col[0].column_letter].width=max(width,10)
    conn.close(); wb.save(path); return path
