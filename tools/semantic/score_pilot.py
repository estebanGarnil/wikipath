"""Offline pilot: one vector per page, complete ranking of existing outgoing links."""
import argparse
import csv
import gzip
import html
import json
import re
import time
from pathlib import Path

MODEL = 'intfloat/multilingual-e5-small'


from prepare_text import prepare, PIPELINE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, default=Path('semantic-results'))
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--compare', type=Path, help='Previous scores.csv for rank comparison')
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error('--batch-size must be positive')
    if args.output.exists():
        parser.error('Output directory already exists; choose a new --output directory.')
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer
    if args.device == 'cuda' and not torch.cuda.is_available():
        parser.error('CUDA unavailable. Install a CUDA-enabled PyTorch build and verify the NVIDIA driver.')
    previous = {}
    if args.compare:
        with args.compare.open(encoding='utf-8-sig', newline='') as stream:
            previous = {(int(r['source_id']), int(r['target_id'])): int(r['rank'])
                        for r in csv.DictReader(stream)}
    started = time.perf_counter()
    with gzip.open(args.input, 'rt', encoding='utf-8') as stream:
        manifest = json.loads(next(stream))
        if manifest.get('schema') != 1 or manifest.get('kind') != 'manifest':
            parser.error('Unsupported export format')
        pages = [json.loads(line) for line in stream if line.strip()]
    pages.sort(key=lambda p: p['page_id'])
    index = {p['page_id']: i for i, p in enumerate(pages)}
    if len(index) != len(pages):
        parser.error('Duplicate page IDs in export')
    if any(a not in index or b not in index for a, b in manifest['links']):
        parser.error('Incomplete export: missing endpoint')
    args.output.mkdir(parents=True)
    texts = []
    with (args.output / 'texts.jsonl').open('w', encoding='utf-8') as stream:
        for i, page in enumerate(pages):
            prepared_page = prepare(page['wikitext'], page['title'])
            page.update(prepared_page)
            texts.append('query: ' + page['title'] + '\n' + page['text'])
            stream.write(json.dumps({'page_id': page['page_id'], 'title': page['title'],
                **prepared_page}, ensure_ascii=False) + '\n')
            if (i + 1) % 200 == 0:
                print(f'Texts prepared: {i + 1}/{len(pages)}', flush=True)
    prepared = time.perf_counter()
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import LocalEntryNotFoundError
    try:
        config_path = hf_hub_download(MODEL, 'config.json', local_files_only=True)
    except LocalEntryNotFoundError:
        config_path = hf_hub_download(MODEL, 'config.json')
    revision = Path(config_path).parent.name
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise RuntimeError('Cannot identify cached model revision; refusing an unversioned run.')
    model = SentenceTransformer(MODEL, revision=revision, device=args.device)
    model.max_seq_length = 512
    loaded = time.perf_counter()
    vectors = model.encode(texts, batch_size=args.batch_size, normalize_embeddings=True,
                           convert_to_numpy=True, show_progress_bar=True)
    encoded = time.perf_counter()
    np.savez_compressed(args.output / 'embeddings.npz',
                        page_ids=np.array([p['page_id'] for p in pages]), vectors=vectors)
    rankings = {source: [] for source in manifest['sources']}
    for source, target in manifest['links']:
        score = float(np.dot(vectors[index[source]], vectors[index[target]]))
        rankings[source].append((target, score))
    report = ['<!doctype html><meta charset="utf-8"><title>Wikipath — essai sémantique</title>',
              '<style>body{font:16px/1.5 system-ui;max-width:1200px;margin:40px auto;padding:20px}td,th{padding:8px;text-align:left;border-bottom:1px solid #ddd}table{border-collapse:collapse;width:100%}small{color:#555}</style>',
              '<h1>Classement sémantique — essai</h1><p>Comparaison avec l’ordre par identifiant. '
              'Le CSV contient tous les voisins, sans limite de 20. Le score n’est pas une probabilité. '
              'Les introductions nettoyées sont disponibles dans texts.jsonl.</p>']
    with (args.output / 'scores.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['source_id', 'target_id', 'rank', 'semantic_score', 'target_title', 'title_only', 'is_disambiguation', 'previous_rank'])
        for source, ranking in rankings.items():
            ranking.sort(key=lambda x: (-x[1], x[0]))
            source_page = pages[index[source]]
            report.append(f'<h2>{html.escape(source_page["title"])} — {len(ranking)} voisins</h2>')
            if source_page['title_only']:
                report.append('<p>Attention : source encodée avec son titre seul.</p>')
            old = sorted(ranking)
            report.append('<table><tr><th>Rang</th><th>Ordre actuel (ID)</th><th>Ordre sémantique</th><th>Score</th><th>Ancien rang E5</th></tr>')
            for rank, (target, score) in enumerate(ranking, 1):
                page = pages[index[target]]
                writer.writerow([source, target, rank, repr(score), page['title'], page['title_only'], page['is_disambiguation'], previous.get((source, target), '')])
                if rank <= 60:
                    fallback = (
                        (" (titre seul)" if page["title_only"] else "")
                        + (" [homonymie]" if page["is_disambiguation"] else "")
                    )
                    previous_rank = previous.get((source, target), "—")
                    old_title = pages[index[old[rank - 1][0]]]["title"]
                    new_title = page["title"] + fallback

                    report.append(
                        f"<tr><td>{rank}</td>"
                        f"<td>{html.escape(old_title)}</td>"
                        f"<td>{html.escape(new_title)}</td>"
                        f"<td>{score:.4f}</td>"
                        f"<td>{previous_rank}</td></tr>"
                    )

            report.append("</table>")
    (args.output / 'report.html').write_text('\n'.join(report), encoding='utf-8')
    metadata = {'model': MODEL, 'model_revision': revision,
        'pipeline': PIPELINE, 'max_tokens': 512, 'device': args.device,
        'gpu': torch.cuda.get_device_name(0) if args.device == 'cuda' else None,
        'pages': len(pages), 'links': len(manifest['links']),
        'title_only': sum(p['title_only'] for p in pages),
        'supplemented': sum(p['supplemented'] for p in pages),
        'disambiguation_pages': sum(p['is_disambiguation'] for p in pages),
        'preparation_seconds': prepared-started, 'model_loading_seconds': loaded-prepared,
        'encoding_seconds': encoded-loaded, 'total_seconds': time.perf_counter()-started,
        'torch': torch.__version__, 'source_revisions': {str(p['page_id']): p['revision_id'] for p in pages}}
    (args.output / 'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(f'Done: {len(pages)} pages, {len(manifest["links"])} links; encoding {encoded-loaded:.1f}s.')
    print(args.output / 'report.html')


if __name__ == '__main__':
    main()
