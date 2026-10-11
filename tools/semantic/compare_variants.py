"""Compare three preparation variants on the same export and E5 revision."""
import argparse
import csv
import gzip
import hashlib
import html
import json
import re
import time
from pathlib import Path

MODEL = 'intfloat/multilingual-e5-small'
VARIANTS = {
    'v1': 'Nettoyage initial, introduction seule',
    'v2': 'Nettoyage corrigé avec complément',
    'v3': 'Nettoyage corrigé, introduction seule',
}


def original_introduction(wikitext):
    import mwparserfromhell
    code = mwparserfromhell.parse(wikitext)
    lead = code.get_sections(include_lead=True, include_headings=False)[0]
    for tag in list(lead.filter_tags()):
        if str(tag.tag).strip().lower() in {'ref', 'references', 'table', 'gallery', 'math', 'timeline'}:
            try:
                lead.remove(tag)
            except ValueError:
                pass
    for link in list(lead.filter_wikilinks()):
        namespace = str(link.title).lstrip(':').split(':', 1)[0].lower()
        if namespace in {'fichier', 'image', 'file', 'catégorie', 'category'}:
            try:
                lead.remove(link)
            except ValueError:
                pass
    return re.sub(r'\s+', ' ', lead.strip_code()).strip()[:6000]


def rank_links(sources, links, score):
    result = {source: [] for source in sources}
    for source, target in links:
        result[source].append({'target_id': target, 'score': float(score(source, target))})
    for rows in result.values():
        rows.sort(key=lambda row: (-row['score'], row['target_id']))
        for rank, row in enumerate(rows, 1):
            row['rank'] = rank
    return result


def write_results(output, rankings, titles):
    with (output / 'scores.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['variant', 'source_id', 'target_id', 'rank', 'semantic_score', 'title'])
        for variant, sources in rankings.items():
            for source, rows in sources.items():
                for row in rows:
                    writer.writerow([variant, source, row['target_id'], row['rank'], repr(row['score']), titles[row['target_id']]])
    report = ['<!doctype html><html lang="fr"><meta charset="utf-8">',
        '<title>Wikipath — comparaison v1 / v2 / v3</title>',
        '<style>body{font:15px/1.5 system-ui;margin:24px;color:#202122}table{width:100%;border-collapse:collapse}th,td{padding:9px;border:1px solid #ddd;vertical-align:top}th{background:#f5f5f5}small{display:block;color:#555}.scroll{overflow:auto}h2{margin-top:40px}</style>',
        '<h1>Comparaison des trois préparations</h1><p>Mêmes pages, mêmes liens, même révision du modèle. '
        'Scores bruts, sans pénalité pour les homonymies. Tous les rangs sont dans scores.csv.</p>',
        '<p>Évaluez la pertinence des titres, pas la hauteur des scores entre variantes. '
        'V1 → V3 isole le nettoyage ; V3 → V2 isole l’ajout de contexte.</p>']
    for source in rankings['v1']:
        count = len(rankings['v1'][source])
        report.append('<h2>' + html.escape(titles[source]) + f' — {count} voisins</h2>')
        report.append('<div class="scroll"><table><tr><th>Rang</th>' + ''.join(
            '<th>' + key.upper() + ' — ' + html.escape(label) + '</th>' for key, label in VARIANTS.items()) + '</tr>')
        for index in range(min(60, count)):
            report.append(f'<tr><td>{index+1}</td>')
            for variant in VARIANTS:
                row = rankings[variant][source][index]
                title = html.escape(titles[row['target_id']])
                report.append(f'<td>{title}<small>{row["score"]:.4f} · ID {row["target_id"]}</small></td>')
            report.append('</tr>')
        report.append('</table></div>')
    report.append('</html>')
    (output / 'report.html').write_text('\n'.join(report), encoding='utf-8')
    # Blank evaluation sheet: user chooses desired neighbors independently of model scores.
    with (output / 'evaluation.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['source_id', 'target_id', 'title', 'rank_v1', 'rank_v2', 'rank_v3', 'pertinence_0_1_2', 'commentaire'])
        for source, rows in rankings['v1'].items():
            lookup = {v: {r['target_id']: r['rank'] for r in rankings[v][source]} for v in VARIANTS}
            for row in sorted(rows, key=lambda r: r['target_id']):
                target = row['target_id']
                writer.writerow([source, target, titles[target], *(lookup[v][target] for v in VARIANTS), '', ''])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=Path)
    parser.add_argument('--reference-metadata', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('semantic-comparison'))
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--batch-size', type=int, default=16)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists. Choose a new directory; previous results are preserved.')
    if args.batch_size < 1:
        parser.error('Batch size must be positive.')
    metadata = json.loads(args.reference_metadata.read_text(encoding='utf-8-sig'))
    revision = metadata.get('model_revision')
    if metadata.get('model') != MODEL or not re.fullmatch('[0-9a-f]{40}', revision or ''):
        parser.error('Reference metadata must contain the E5-small model and a valid revision (use v2 metadata).')
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer
    import prepare_text
    if args.device == 'cuda' and not torch.cuda.is_available():
        parser.error('CUDA unavailable; use CPU or install CUDA-enabled PyTorch.')
    with gzip.open(args.input, 'rt', encoding='utf-8') as stream:
        manifest = json.loads(next(stream))
        pages = [json.loads(line) for line in stream if line.strip()]
    if manifest.get('schema') != 1 or manifest.get('direction') != 'out':
        parser.error('Unsupported export.')
    pages.sort(key=lambda p: p['page_id'])
    titles = {p['page_id']: p['title'] for p in pages}
    sources, links = manifest['sources'], manifest['links']
    if len(titles) != len(pages) or not set(sources) <= titles.keys():
        parser.error('Duplicate IDs or missing sources.')
    if any(a not in sources or b not in titles for a, b in links) or len(set(map(tuple, links))) != len(links):
        parser.error('Invalid or duplicate links.')
    args.output.mkdir(parents=True)
    started = time.perf_counter()
    unique_texts, text_indices, mapping = [], {}, {v: {} for v in VARIANTS}
    stats = {v: {'title_only': 0, 'truncated_pages': 0} for v in VARIANTS}
    with (args.output / 'texts.jsonl').open('w', encoding='utf-8') as stream:
        for index, page in enumerate(pages, 1):
            fixed = prepare_text.prepare(page['wikitext'], page['title'])
            variants = {'v1': original_introduction(page['wikitext']), 'v2': fixed['text'], 'v3': fixed['introduction'][:6000]}
            for variant, text in variants.items():
                value = 'query: ' + page['title'] + '\n' + text
                if value not in text_indices:
                    text_indices[value] = len(unique_texts)
                    unique_texts.append(value)
                mapping[variant][page['page_id']] = text_indices[value]
                stats[variant]['title_only'] += not bool(text)
            stream.write(json.dumps({'page_id': page['page_id'], 'title': page['title'],
                'variants': variants, 'supplemented_v2': fixed['supplemented'],
                'is_disambiguation': fixed['is_disambiguation'],
                'omitted_templates': fixed['omitted_templates']}, ensure_ascii=False) + '\n')
            if index % 100 == 0:
                print(f'Texts: {index}/{len(pages)}', flush=True)
    prepared = time.perf_counter()
    model = SentenceTransformer(MODEL, revision=revision, device=args.device)
    model.max_seq_length = 512
    token_counts = [len(model.tokenizer(text, truncation=False)['input_ids']) for text in unique_texts]
    for variant in VARIANTS:
        stats[variant]['truncated_pages'] = sum(token_counts[i] > 512 for i in mapping[variant].values())
    loaded = time.perf_counter()
    vectors = model.encode(unique_texts, batch_size=args.batch_size, normalize_embeddings=True,
                           convert_to_numpy=True, show_progress_bar=True)
    encoded = time.perf_counter()
    rankings = {}
    for variant in VARIANTS:
        lookup = mapping[variant]
        rankings[variant] = rank_links(sources, links, lambda a, b: np.dot(vectors[lookup[a]], vectors[lookup[b]]))
    write_results(args.output, rankings, titles)
    result = {'model': MODEL, 'model_revision': revision, 'variants': VARIANTS,
        'preparation_sha256': hashlib.sha256(Path(prepare_text.__file__).read_bytes()).hexdigest(),
        'device': args.device, 'pages': len(pages), 'links': len(links),
        'unique_texts_encoded': len(unique_texts), 'stats': stats,
        'preparation_seconds': prepared-started, 'load_and_token_audit_seconds': loaded-prepared,
        'encoding_seconds': encoded-loaded, 'total_seconds': time.perf_counter()-started,
        'source_revisions': {str(p['page_id']): p['revision_id'] for p in pages}}
    (args.output / 'metadata.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Done:', args.output / 'report.html')


if __name__ == '__main__':
    main()
