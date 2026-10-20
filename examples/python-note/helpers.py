def date_label(context):
    return f'今天 {context.today.isoformat()} · 所选日期 {context.selected_date.isoformat()}'
