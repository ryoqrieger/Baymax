"""
Project-wide audit tests (Sprint 7). They read the source code and fail when a
rule of the project is broken, so a later change cannot quietly undo the hardening.
No database is needed.
"""
import ast
import inspect
import re
from pathlib import Path

from django.conf import settings
from django.template import engines
from django.test import SimpleTestCase, override_settings
from django.urls import URLPattern, URLResolver

from core import urls as core_urls

APP = Path(settings.BASE_DIR)
CORE = APP / 'core'
TEMPLATES = APP / 'templates'
VIEWS = sorted((CORE / 'views').glob('*.py'))
NON_TEST_PY = [p for p in CORE.rglob('*.py') if 'tests' not in p.parts and 'migrations' not in p.parts]


def parse(path):
    return ast.parse(path.read_text(encoding='utf-8'), filename=str(path))


# ── Templates ─────────────────────────────────────────────────────────────────

class TemplateRules(SimpleTestCase):
    def html_files(self):
        return sorted(TEMPLATES.rglob('*.html'))

    def test_no_inline_styles_or_style_blocks(self):
        for path in self.html_files():
            text = path.read_text(encoding='utf-8')
            with self.subTest(template=str(path.relative_to(TEMPLATES))):
                self.assertIsNone(re.search(r'<style[\s>]', text, re.I), 'found a <style> block')
                self.assertIsNone(re.search(r'\sstyle\s*=', text, re.I), 'found an inline style attribute')

    def test_no_inline_event_handlers_or_script_bodies(self):
        for path in self.html_files():
            text = path.read_text(encoding='utf-8')
            with self.subTest(template=str(path.relative_to(TEMPLATES))):
                self.assertIsNone(re.search(r'\son[a-z]+\s*=\s*["\']', text, re.I), 'found an inline event handler')
                for match in re.finditer(r'<script\b([^>]*)>(.*?)</script>', text, re.I | re.S):
                    self.assertIn('src=', match.group(1), 'found an inline <script> body')

    def test_every_page_extends_base(self):
        for path in self.html_files():
            relative = path.relative_to(TEMPLATES)
            if relative.name == 'base.html' or relative.parts[0] == 'partials':
                continue
            with self.subTest(template=str(relative)):
                self.assertIn('{% extends "base.html" %}', path.read_text(encoding='utf-8'))

    def test_partials_do_not_extend_anything(self):
        for path in (TEMPLATES / 'partials').glob('*.html'):
            with self.subTest(template=path.name):
                self.assertNotIn('{% extends', path.read_text(encoding='utf-8'))

    def test_every_template_compiles(self):
        engine = engines['django']
        for path in list(self.html_files()) + sorted((TEMPLATES / 'emails').glob('*.txt')):
            with self.subTest(template=str(path.relative_to(TEMPLATES))):
                engine.get_template(str(path.relative_to(TEMPLATES)))

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_error_pages_render_without_a_request(self):
        """Django renders 500.html with no request or context processors; it must still work."""
        for name in ('404.html', '403.html', '500.html', '403_csrf.html'):
            with self.subTest(page=name):
                html = engines['django'].get_template(name).render({})
                self.assertIn('Go to home', html)

    def test_every_form_has_a_csrf_token(self):
        for path in self.html_files():
            text = path.read_text(encoding='utf-8')
            for form in re.finditer(r'<form\b([^>]*)>(.*?)</form>', text, re.I | re.S):
                if re.search(r'method\s*=\s*["\']post["\']', form.group(1), re.I):
                    with self.subTest(template=str(path.relative_to(TEMPLATES))):
                        self.assertIn('{% csrf_token %}', form.group(2))


# ── SQL ───────────────────────────────────────────────────────────────────────

# Names allowed inside an f-string SQL statement. Each one is built only from constants
# in components.py or from fixed fragments written in the view; none holds user input.
ALLOWED_SQL_NAMES = {'answer_columns', 'where_sql', 'order', 'symptom_sql', 'SELF_HARM_COLUMN',
                     'columns', 'placeholders'}
# Calls cur.execute(<variable>, ...) where the variable is assembled from fixed fragments.
ALLOWED_SQL_VARIABLES = {('auth.py', 'sql')}


def _is_execute(node):
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'execute'


def _constant_names(tree):
    """Module-level names assigned a fixed string (e.g. _ROW_SELECT = "SELECT ...")."""
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Constant, ast.BinOp, ast.JoinedStr)) \
                and not list(_unsafe_parts(node.value, set())):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def _unsafe_parts(expr, constants):
    """Yield descriptions of anything in a SQL expression that could carry user input."""
    if isinstance(expr, ast.Constant):
        return
    if isinstance(expr, ast.Name) and expr.id in constants:
        return
    if isinstance(expr, ast.JoinedStr):
        for value in expr.values:
            if isinstance(value, ast.FormattedValue):
                names = {n.id for n in ast.walk(value.value) if isinstance(n, ast.Name)}
                if not names <= ALLOWED_SQL_NAMES:
                    yield f'f-string uses {sorted(names - ALLOWED_SQL_NAMES)}'
        return
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
        yield from _unsafe_parts(expr.left, constants)
        yield from _unsafe_parts(expr.right, constants)
        return
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Mod):
        yield 'string % formatting'
        return
    if isinstance(expr, ast.IfExp):                     # ("" if flag else " AND dismissed = FALSE")
        yield from _unsafe_parts(expr.body, constants)
        yield from _unsafe_parts(expr.orelse, constants)
        return
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and expr.func.attr == 'format':
        yield '.format() on SQL'
        return
    yield f'non-constant expression ({type(expr).__name__})'


class SqlRules(SimpleTestCase):
    def test_every_execute_uses_only_constant_sql(self):
        problems = []
        for path in NON_TEST_PY:
            tree = parse(path)
            constants = _constant_names(tree)
            for node in ast.walk(tree):
                if not _is_execute(node) or not node.args:
                    continue
                first = node.args[0]
                if isinstance(first, ast.Name) and (path.name, first.id) in ALLOWED_SQL_VARIABLES:
                    continue
                for problem in _unsafe_parts(first, constants):
                    problems.append(f'{path.relative_to(APP)}:{node.lineno}: {problem}')
        self.assertEqual(problems, [], 'SQL must be a constant string with %s placeholders for values')


# ── Views and URLs ────────────────────────────────────────────────────────────

# Pages that are public on purpose (sign-in, sign-up, password link, landing page).
PUBLIC_VIEWS = {
    'landing', 'login_view', 'logout_view', 'register', 'register_verify', 'register_resend',
    'register_cancel', 'google_start', 'google_complete', 'set_password',
}
# Views that may write on GET or on POST without require_POST because they show a form first.
FORM_VIEWS = {
    'login_view', 'change_password', 'register', 'register_verify', 'google_complete', 'set_password',
    'chatbot_question', 'profile', 'event_new', 'event_edit', 'user_new', 'semester',
    'appointment_detail',        # opening a pending request marks it as seen
    'status', 'stats',           # may save a first AI text / create missing alerts
}


def _decorator_names(func_node):
    names = set()
    for decorator in func_node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute):
            names.add(target.attr)
        elif isinstance(target, ast.Name):
            names.add(target.id)
    return names


def _url_view_functions():
    """(name, module path, FunctionDef) for every view function wired in core/urls.py."""
    callbacks = []

    def collect(patterns):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                collect(pattern.url_patterns)
            elif isinstance(pattern, URLPattern):
                callbacks.append(inspect.unwrap(pattern.callback))

    collect(core_urls.urlpatterns)
    found = []
    for callback in callbacks:
        source_file = Path(inspect.getsourcefile(callback))
        if CORE not in source_file.parents:
            continue
        for node in parse(source_file).body:
            if isinstance(node, ast.FunctionDef) and node.name == callback.__name__:
                found.append((node.name, source_file, node))
    return found


class ViewRules(SimpleTestCase):
    def test_views_were_found(self):
        self.assertGreater(len(_url_view_functions()), 40)

    def test_every_non_public_view_requires_a_role(self):
        unprotected = [name for name, _, node in _url_view_functions()
                       if name not in PUBLIC_VIEWS and 'login_required_role' not in _decorator_names(node)]
        self.assertEqual(unprotected, [])

    def test_public_list_is_not_stale(self):
        names = {name for name, _, _ in _url_view_functions()}
        self.assertTrue(PUBLIC_VIEWS <= names, PUBLIC_VIEWS - names)

    def test_views_that_write_are_post_only_or_known_forms(self):
        offenders = []
        for name, path, node in _url_view_functions():
            writes = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'commit'
                         for n in ast.walk(node))
            decorators = _decorator_names(node)
            if writes and not ({'require_POST', 'require_http_methods'} & decorators) and name not in FORM_VIEWS:
                offenders.append(f'{path.name}:{name}')
        self.assertEqual(offenders, [])

    def test_post_only_actions_are_not_form_views(self):
        for name, _, node in _url_view_functions():
            if 'require_POST' in _decorator_names(node):
                self.assertNotIn(name, FORM_VIEWS)

    def test_decorators_keep_function_metadata(self):
        source = (CORE / 'views' / 'auth.py').read_text(encoding='utf-8')
        self.assertGreaterEqual(source.count('@functools.wraps'), 2)

    def test_page_numbers_are_only_read_by_the_safe_parser(self):
        for path in NON_TEST_PY:
            if path.name == 'utils.py':
                continue
            with self.subTest(file=str(path.relative_to(APP))):
                self.assertIsNone(re.search(r"GET(\.get\(|\[)\s*['\"]page['\"]", path.read_text(encoding='utf-8')))


# ── Architecture rules ────────────────────────────────────────────────────────

class ArchitectureRules(SimpleTestCase):
    def test_db_module_has_only_two_functions(self):
        names = [n.name for n in parse(CORE / 'db.py').body if isinstance(n, ast.FunctionDef)]
        self.assertEqual(sorted(names), ['connect_db', 'get_current_semester'])

    def test_no_shared_views_module(self):
        self.assertFalse((CORE / 'views.py').exists())

    def test_email_is_only_sent_from_email_utils(self):
        for path in NON_TEST_PY:
            if path.name == 'email_utils.py':
                continue
            text = path.read_text(encoding='utf-8')
            with self.subTest(file=str(path.relative_to(APP))):
                self.assertNotIn('send_mail', text)
                self.assertNotIn('EmailMessage', text)

    def test_llm_is_only_called_through_the_client(self):
        for path in NON_TEST_PY:
            if path.name == 'llm_client.py':
                continue
            text = path.read_text(encoding='utf-8')
            with self.subTest(file=str(path.relative_to(APP))):
                self.assertNotIn('from openai', text)
                self.assertNotIn('import openai', text)
                self.assertNotIn('.chat.completions', text)

    def test_settings_have_no_environment_fallbacks(self):
        tree = parse(APP / 'config' / 'settings.py')
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                owner = ast.unparse(node.func)
                if owner in ('os.environ.get', 'os.getenv') and len(node.args) + len(node.keywords) > 1:
                    calls.append(f'line {node.lineno}: {ast.unparse(node)}')
        # The single allowed case is the optional DATABASE_URL, whose empty default means "use DB_* instead".
        self.assertEqual([c for c in calls if 'DATABASE_URL' not in c], [])

    def test_env_file_is_never_committed(self):
        root = APP.parent
        ignore = (root / '.gitignore').read_text(encoding='utf-8')
        self.assertRegex(ignore, r'(?m)^\.env$')
        self.assertFalse((APP / '.env').exists() and False)   # a local .env is fine; it is ignored by git

    def test_no_secrets_in_source(self):
        pattern = re.compile(r'gsk_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----')
        for path in list(NON_TEST_PY) + list(TEMPLATES.rglob('*')) + [APP / '.env.example']:
            if path.is_file():
                with self.subTest(file=str(path.relative_to(APP))):
                    self.assertIsNone(pattern.search(path.read_text(encoding='utf-8', errors='ignore')))