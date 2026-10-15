from django import template

register = template.Library()
LABELS = {
    "healthy": "Sadias", "subclinical": "Subclínicas", "clinical": "Clínicas", "contagious": "Contagiosas",
    "inconclusive": "Inconclusivo", "positive": "Positivo", "negative": "Negativo", "contaminated": "Contaminado",
    "left_front": "Anterior esquerdo", "right_front": "Anterior direito", "left_rear": "Posterior esquerdo", "right_rear": "Posterior direito", "composite": "Composta",
    "summary": "Resumo", "technical_notes": "Notas técnicas", "recommendations": "Recomendações", "management_notes": "Orientações de manejo",
}


@register.filter
def report_label(value):
    return LABELS.get(value, value)
