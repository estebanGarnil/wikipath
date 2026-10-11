"""Conservative local text preparation; this does not expand MediaWiki templates."""
import re
from collections import Counter

import mwparserfromhell

PIPELINE = 'title-lead-context-v2-query-symmetric'
SKIP_SECTIONS = {'notes', 'références', 'notes et références', 'bibliographie',
                 'voir aussi', 'liens externes', 'articles connexes', 'sources', 'annexes'}
DISAMBIGUATION = {'homonymie', 'homonymie de personnes', 'homonymie de patronyme',
                 'homonymie de toponyme', 'homonymie de titre', 'homonymie de prénom'}


def name_of(template):
    return re.sub(r'\s+', ' ', str(template.name).replace('_', ' ').strip().lower())


def positional(template):
    return [str(p.value).strip() for p in template.params if str(p.name).strip().isdigit()]


def readable_template(template):
    name, values = name_of(template), positional(template)
    if name in {'date', 'date de naissance', 'date de décès', 'date-', 'date naissance', 'date décès'}:
        return ' '.join(values[:3])
    if name in {'s', 's-', 'siècle', 'siècle-', 's mini'} and values:
        return values[0].lstrip('-') + 'e siècle' + (' avant notre ère' if values[0].startswith('-') else '')
    if name in {'sp', 's2', 's2-'} and len(values) >= 2:
        return ' et '.join(v + 'e' for v in values[:2]) + ' siècles'
    if name in {'lang', 'langue'}:
        if template.has('texte'):
            return str(template.get('texte').value)
        return values[1] if len(values) > 1 else ''
    if name in {'nombre', 'num', 'unité', 'unite'}:
        return ' '.join(values)
    if name in {'formatnum', 'nobr', 'nowrap', 'citation', 'math', 'm', 'petites capitales'}:
        return values[0] if values else ''
    if name in {'1er', 'ier'}:
        return '1er'
    if name in {'1re', 'ière'}:
        return '1re'
    if name in {'e', 'ème', 'er', 're'}:
        return (values[0] if values else '') + name
    return None


def clean(code, omitted):
    # Drop metadata/noisy blocks before expanding inline text.
    for tag in list(code.filter_tags()):
        if str(tag.tag).strip().lower() in {'ref', 'references', 'table', 'gallery', 'timeline'}:
            try:
                code.remove(tag)
            except ValueError:
                pass
    for link in list(code.filter_wikilinks()):
        title = str(link.title).lstrip(':')
        if ':' in title and title.split(':', 1)[0].lower() in {'fichier', 'image', 'file', 'catégorie', 'category'}:
            try:
                code.remove(link)
            except ValueError:
                pass
    # Inner templates first. Unknown templates are logged, never expanded blindly.
    for template in reversed(list(code.filter_templates())):
        replacement = readable_template(template)
        try:
            code.replace(template, replacement if replacement is not None else '')
            if replacement is None:
                omitted[name_of(template)] += 1
        except ValueError:
            pass
    # Keep formula source as text instead of deleting its operands.
    for tag in reversed(list(code.filter_tags())):
        if str(tag.tag).strip().lower() == 'math':
            try:
                code.replace(tag, ' ' + str(tag.contents or '') + ' ')
            except ValueError:
                pass
    return re.sub(r'\s+', ' ', code.strip_code()).strip()


def prepare(wikitext, title):
    code = mwparserfromhell.parse(wikitext)
    disambiguation = '(homonymie)' in title.lower() or any(
        name_of(t) in DISAMBIGUATION for t in code.filter_templates())
    omitted = Counter()
    sections = code.get_sections(include_lead=True, flat=True, include_headings=True)
    lead_code = mwparserfromhell.parse(str(sections[0]))
    # First section may be empty when the page starts with a heading.
    lead = clean(lead_code, omitted)
    text = lead
    supplemented = False
    # Enough context for short definitions/biographies, without reading references.
    if len(lead) < 400 and not disambiguation:
        skip_level = None
        additions = []
        for section in sections[1:]:
            section = mwparserfromhell.parse(str(section))
            headings = section.filter_headings(recursive=False)
            if not headings:
                continue
            heading = headings[0]
            label = str(heading.title).strip().casefold()
            if skip_level is not None and heading.level > skip_level:
                continue
            skip_level = None
            if label in SKIP_SECTIONS:
                skip_level = heading.level
                continue
            section.remove(heading)
            # Select narrative paragraphs, not bullet lists or tables.
            for paragraph in re.split(r'\n\s*\n', str(section)):
                if paragraph.lstrip().startswith(('*', '#', '{|', '|', '!')):
                    continue
                candidate = clean(mwparserfromhell.parse(paragraph), omitted)
                if len(candidate) < 80:
                    continue
                additions.append(candidate)
                if len(' '.join([lead] + additions)) >= 1200:
                    break
            if len(' '.join([lead] + additions)) >= 1200:
                break
        if additions:
            text = ' '.join([lead] + additions).strip()
            supplemented = True
    return {'introduction': lead, 'text': text[:6000], 'title_only': not bool(text),
            'supplemented': supplemented, 'is_disambiguation': disambiguation,
            'omitted_templates': dict(omitted)}
