import hashlib
from urllib.parse import unquote, urljoin, urlsplit

import nh3
import requests
from bs4 import BeautifulSoup
from django.conf import settings

RENDER_VERSION = 'wikipath-reader-1'
API_URL = 'https://fr.wikipedia.org/w/api.php'
MAX_RESPONSE_BYTES = 12 * 1024 * 1024


class RenderUnavailable(Exception):
    pass


def fingerprint(article):
    digest = hashlib.sha256()
    digest.update(RENDER_VERSION.encode())
    digest.update(str(article.revision_id).encode())
    digest.update(article.title.encode('utf-8'))
    digest.update(bytes(article.wikitext_zlib))
    return digest.hexdigest()


def sanitize_html(raw):
    clean = nh3.clean(
        raw,
        tags={'a','p','br','hr','div','span','section','h2','h3','h4','h5','h6','b','strong','i','em','u','s','small','sup','sub','ul','ol','li','dl','dt','dd','blockquote','pre','code','table','caption','thead','tbody','tfoot','tr','th','td','figure','figcaption','img'},
        attributes={'*': {'id','class','lang','dir'}, 'a': {'href','title'}, 'img': {'src','alt','width','height'}, 'td': {'colspan','rowspan'}, 'th': {'colspan','rowspan','scope'}},
        clean_content_tags={'script','style','iframe','object','embed','form'},
        url_schemes={'http','https'},
        link_rel='noopener noreferrer',
    )
    soup = BeautifulSoup(clean, 'html.parser')
    for tag in soup.find_all(True):
        # Keep article classes isolated from the application stylesheet.
        classes = tag.get('class', [])
        tag.attrs.pop('class', None)
        if any('infobox' in c for c in classes): tag['class'] = ['wiki-infobox']
        elif 'wikitable' in classes: tag['class'] = ['wiki-table']
        if tag.get('id'): tag['id'] = 'wiki-' + tag['id']
    for img in soup.find_all('img'):
        url = urljoin('https://fr.wikipedia.org/', img.get('src', ''))
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname != 'upload.wikimedia.org':
            img.decompose()
            continue
        img['src'] = url
        img['loading'] = 'lazy'
        img['referrerpolicy'] = 'no-referrer'
    for link in soup.find_all('a'):
        href = link.get('href', '')
        link.attrs.pop('href', None)
        if href.startswith('#'):
            link['href'] = '#wiki-' + unquote(href[1:])
            continue
        url = urljoin('https://fr.wikipedia.org/', href)
        parsed = urlsplit(url)
        if parsed.hostname == 'fr.wikipedia.org' and parsed.path.startswith('/wiki/'):
            # No href: modifier/middle clicks cannot bypass graph navigation.
            link['data-wiki-title'] = unquote(parsed.path[len('/wiki/'):]).replace('_', ' ')
            link['role'] = 'link'
            link['tabindex'] = '0'
        elif href and parsed.hostname != 'fr.wikipedia.org' and parsed.scheme in {'http','https'}:
            link['href'] = url
            link['target'] = '_blank'
            link['rel'] = 'noopener noreferrer'
    return str(soup)


def fetch_render(article):
    try:
        with requests.post(
            API_URL,
            data={'action':'parse','format':'json','formatversion':2,'title':article.title,
                  'text':article.wikitext,'contentmodel':'wikitext','prop':'text',
                  'disableeditsection':1,'disablelimitreport':1,'maxlag':5},
            headers={'User-Agent': getattr(settings, 'WIKIPEDIA_USER_AGENT',
                'Wikipath/0.1 (https://github.com/estebanGarnil/wikipath; local article reader)'),
                'Accept':'application/json'},
            timeout=(5, 25), stream=True,
        ) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise RenderUnavailable('Article trop volumineux pour le rendu.')
        import json
        data = json.loads(body)
        if 'error' in data:
            raise RenderUnavailable('Wikipédia ne peut pas générer le rendu pour le moment.')
        html = data.get('parse', {}).get('text')
        if not isinstance(html, str) or not html.strip():
            raise RenderUnavailable('Wikipédia a renvoyé un rendu vide.')
        return sanitize_html(html)
    except (requests.RequestException, ValueError) as exc:
        raise RenderUnavailable('Wikipédia est temporairement inaccessible. Le wikicode reste disponible.') from exc
