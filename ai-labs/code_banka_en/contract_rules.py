"""Strict parser for the Czech contract templates supported by this lab.

This is deliberately not a general legal-text interpreter. Unknown clauses raise
ValueError so that the caller can route the case to human review. No ground truth
or generator configuration is used to resolve the contract.
"""
import re
from datetime import date
from decimal import Decimal

BASE_EBITDA = (
    '„EBITDA“ znamená provozní výsledek hospodaření Dlužníka za Testovací období zvýšený '
    'o odpisy a amortizaci dlouhodobého hmotného a nehmotného majetku.',
    '„EBITDA“ se rozumí součet provozního výsledku hospodaření (EBIT) a odpisů a amortizace '
    'za příslušné Testovací období.',
)
RESTRUCTURING = (
    ('', []),
    ('Jednorázové náklady na restrukturalizaci se k EBITDA nepřipočítávají.', []),
    ('Pro účely této Smlouvy se k EBITDA dále připočítávají jednorázové náklady na restrukturalizaci, '
     'pokud jsou v účetní závěrce nebo ve výkazu pro Banku vykázány samostatně.', ['restructuring']),
    ('EBITDA se dále zvyšuje o samostatně vykázané jednorázové náklady spojené s restrukturalizací.', ['restructuring']),
)
GAINS = (
    ('', []),
    ('Od EBITDA se odečítají jednorázové zisky z prodeje dlouhodobého majetku.', ['asset_sale_gain']),
    ('Do EBITDA se nezahrnují jednorázové zisky z prodeje dlouhodobého majetku; '
     'o tyto zisky se EBITDA snižuje.', ['asset_sale_gain']),
)
DEBT = 'znamená souhrn bankovních úvěrů a zápůjček a vydaných dluhopisů Dlužníka ke Dni testování'
NUMBER = r'(\d+,\d{2})'
DAY = r'(\d{1,2}\. \d{1,2}\. \d{4})'
LEVERAGE = r'Dlužník je povinen zajistit, aby poměr (?:Čistého dluhu|Dluhu) k EBITDA '
SUMMARY = ('Finanční ukazatele se vypočítávají z údajů za Testovací období podle definic '
           'uvedených v této Smlouvě, bez ohledu na ukazatele vykazované Dlužníkem.')


def normalized(text):
    return ' '.join(text.split())


def paragraphs(text):
    return [normalized(p) for p in re.split(r'\n\s*\n', text) if p.strip()]


def definitions(text, part):
    prefix = '„EBITDA“' if part == 'ebitda' else ('„Čistý dluh“', '„Dluh“')
    candidates = [re.sub(r'^\d+\.\d+ ', '', p) for p in paragraphs(text)]
    candidates = [p for p in candidates if p.startswith(prefix)]
    if len(candidates) != 1:
        raise ValueError(f'{part}: expected exactly one supported definition')
    clause = candidates[0]
    if part == 'ebitda':
        for base in BASE_EBITDA:
            for addition, adds in RESTRUCTURING:
                for subtraction, subs in GAINS:
                    if clause == normalized(f'{base} {addition} {subtraction}'):
                        return {'add': adds, 'subtract': subs}
    else:
        for clause_text, cash in (
            (f'„Čistý dluh“ {DEBT} snížený o peněžní prostředky a peněžní ekvivalenty.', True),
            (f'„Dluh“ {DEBT}. Peněžní prostředky a peněžní ekvivalenty se od Dluhu neodečítají.', False),
        ):
            if clause == clause_text:
                return {'include': ['bank_loans', 'bonds'], 'deduct_cash': cash}
    raise ValueError(f'{part}: unsupported definition')


def decimal(text):
    return Decimal(text.replace(',', '.'))


def day(text):
    d, m, y = (int(p.strip()) for p in text.split('.'))
    return date(y, m, d)


def contract_limits(text, test_day):
    result = {}
    for paragraph in paragraphs(text):
        if paragraph.startswith('## '):
            continue
        match = re.fullmatch(r'\d+\.(\d+) (.+)', paragraph)
        if not match:
            raise ValueError('unsupported covenant article content')
        subarticle, clause = match.groups()
        if clause == SUMMARY:
            continue
        simple = re.fullmatch(LEVERAGE + r'ke každému Dni testování nepřesáhl hodnotu ' + NUMBER + r'\.', clause)
        step = re.fullmatch(LEVERAGE + r'nepřesáhl: \(a\) hodnotu ' + NUMBER + r' pro Dny testování do '
                            + DAY + r' včetně; a \(b\) hodnotu ' + NUMBER + r' pro Dny testování od ' + DAY + r'\.', clause)
        interest = re.fullmatch(r'Dlužník je dále povinen zajistit, aby poměr EBITDA k Nákladovým úrokům '
                               r'ke každému Dni testování nebyl nižší než ' + NUMBER + r'\.', clause)
        if simple:
            ratio, limit = 'debt_to_ebitda', decimal(simple[1])
        elif step:
            old, end, new, start = step.groups()
            end, start = day(end), day(start)
            if (start - end).days != 1:
                raise ValueError('ambiguous limit dates')
            ratio, limit = 'debt_to_ebitda', decimal(old if test_day <= end else new)
        elif interest:
            ratio, limit = 'interest_cover', decimal(interest[1])
        else:
            raise ValueError('unsupported covenant clause')
        if ratio in result:
            raise ValueError('conflicting covenant clauses')
        result[ratio] = (limit, subarticle)
    if not result:
        raise ValueError('no supported covenants')
    return result


def amendment(text):
    clauses = [p for p in paragraphs(text) if not p.startswith('## ')]
    if len(clauses) != 2:
        raise ValueError('unsupported amendment')
    change = re.fullmatch(r'1\.1 Ustanovení (\d+)\.(\d+) Smlouvy se mění tak, že poměr Čistého dluhu '
                          r'k EBITDA nesmí pro Dny testování od ' + DAY + r' včetně přesáhnout hodnotu ' + NUMBER + r'\.', clauses[0])
    previous = re.fullmatch(r'1\.2 Pro Dny testování před ' + DAY + r' zůstává v platnosti původní hodnota ' + NUMBER + r'\.', clauses[1])
    if not change or not previous or day(change[3]) != day(previous[1]):
        raise ValueError('unsupported or conflicting amendment')
    return change[1], change[2], day(change[3]), decimal(previous[2]), decimal(change[4])
