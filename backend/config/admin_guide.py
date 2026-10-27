"""Page admin : guide des actions (lecture du markdown docs/GUIDE_ADMIN_ACTIONS.md)."""

from pathlib import Path

try:
    import markdown
    _HAS_MARKDOWN = True
except ImportError:
    markdown = None
    _HAS_MARKDOWN = False

from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView

_GUIDE_PATH = Path(__file__).resolve().parent.parent / 'docs' / 'GUIDE_ADMIN_ACTIONS.md'


def _render_guide_html(text: str) -> str:
    if not _HAS_MARKDOWN:
        return '<p><em>Guide indisponible (module markdown manquant).</em></p>'
    return markdown.markdown(
        text,
        extensions=['tables', 'fenced_code', 'sane_lists', 'nl2br'],
    )


class AdminGuideView(TemplateView):
    template_name = 'admin/guide.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Guide des actions admin'
        try:
            raw = _GUIDE_PATH.read_text(encoding='utf-8')
            context['guide_html'] = _render_guide_html(raw)
        except OSError:
            context['guide_html'] = (
                '<p><strong>Guide indisponible.</strong> '
                'Le fichier de documentation est introuvable.</p>'
            )
        return context


def attach_admin_guide_urls():
    if getattr(admin.site, '_admin_guide_urls', False):
        return

    original_get_urls = admin.site.get_urls

    def get_urls():
        custom = [
            path(
                'guide-actions/',
                admin.site.admin_view(AdminGuideView.as_view()),
                name='admin_guide_actions',
            ),
        ]
        return custom + original_get_urls()

    admin.site.get_urls = get_urls
    admin.site._admin_guide_urls = True
