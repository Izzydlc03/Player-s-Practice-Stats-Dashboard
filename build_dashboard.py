"""Build Practice_Dashboard.html from the practice / scrimmage CSV exports in this folder.

Usage:  python3 build_dashboard.py
Re-run whenever a new CSV is added. Output: Practice_Dashboard.html (self-contained).
"""
import base64, csv, glob, json, os, re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

STAT_MAP = {
    '+ 2FG': [('p2m', 1), ('p2a', 1)], '- 2FG': [('p2a', 1)],
    '+ 3FG': [('p3m', 1), ('p3a', 1)], '- 3FG': [('p3a', 1)],
    '+ FT': [('ftm', 1), ('fta', 1)], '- FT': [('fta', 1)],
    'OFF. REB': [('orb', 1)], 'DEF. REB': [('drb', 1)],
    'ASSIST': [('ast', 1)], 'STEAL': [('stl', 1)], 'BLOCK': [('blk', 1)],
    'TURNOVER': [('tov', 1)], 'FOUL': [('pf', 1)], 'CHARGE': [('chg', 1)],
}
SCRIMMAGE_SEGMENTS = {'scrimmage'}
SPECIAL_SEGMENTS = {'special sit.', 'special situations', 'special sit', 'special execution'}
DRILL_SEGMENTS = {'drill', 'defense drill', 'offense', 'shell', 'ssg', 'set run run', 'carnival',
                  '3v4 advantage', 'ft to press'} | SCRIMMAGE_SEGMENTS | SPECIAL_SEGMENTS
CONCEPTS = {'paint touch', 'pob', 'trans scores', 'foul - ft', 'uncontested 2', 'uncontested 3'}


def stat_name(col):
    return col.split(':')[-1].strip()


def add(stats, col, v):
    for k, mult in STAT_MAP.get(stat_name(col), []):
        stats[k] = stats.get(k, 0) + v * mult


def parse_date(fname):
    m = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{2})', fname)
    if not m:
        return None
    mo, d, yy = (int(x) for x in m.groups())
    if yy < 20:  # "10.13.16" is a typo for 2026
        yy = 26
    return f'20{yy:02d}-{mo:02d}-{d:02d}'


def parse(path):
    fname = os.path.basename(path)
    rows = list(csv.reader(open(path, encoding='utf-8-sig')))
    hdr = rows[0]
    players, segments, concepts, sets, drills = {}, defaultdict(dict), {}, [], []
    for r in rows[1:]:
        label = r[0].strip()
        vals = [float(x or 0) for x in r[1:]] + [0] * (len(hdr) - len(r))
        if label.startswith('#'):
            s = players.setdefault(label, {})
            for col, v in zip(hdr[1:], vals):
                if v:
                    add(s, col, v)
            continue
        if label == 'TEAM' or not label:
            continue
        low = label.lower()
        # Segment rows: count player-stat cells that intersect this segment (empty in current exports)
        if low in DRILL_SEGMENTS:
            drills.append(label)
            kind = 'scrimmage' if low in SCRIMMAGE_SEGMENTS else 'special' if low in SPECIAL_SEGMENTS else None
            if kind:
                for col, v in zip(hdr[1:], vals):
                    if v and col.startswith('#'):
                        p = col.split(':')[0].strip()
                        add(segments[kind].setdefault(p, {}), col, v)
            continue
        if low in CONCEPTS:
            plus = sum(v for col, v in zip(hdr[1:], vals) if col.strip() == '+1')
            concepts[label] = int(plus)
            continue
        # Bare first names (e.g. "Sadie") hold effort/teaching tags, not box score; skip them.
        if any(col.startswith(('Defense:', 'Offense:')) and v for col, v in zip(hdr[1:], vals)) or label == 'KEEP':
            continue
        sets.append(label)
    players = {p: s for p, s in players.items()}
    is_scrim = 'scrimmage' in fname.lower() and parse_date(fname) is None
    opp = None
    if is_scrim:
        m = re.match(r'UCSD_(.+?)-Scrimmage', fname)
        opp = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', m.group(1)) if m else fname
    return {
        'id': re.sub(r'\W+', '-', fname[:-4]).lower(),
        'file': fname,
        'type': 'scrimmage' if is_scrim else 'practice',
        'date': parse_date(fname),
        'opponent': opp,
        'players': players,
        'segments': {k: v for k, v in segments.items() if v},
        'concepts': concepts,
        'sets': sets,
        'drills': drills,
    }


SEG_COLS = {'2FGM': 'p2m', '2FGA': 'p2a', '3FGM': 'p3m', '3FGA': 'p3a', 'FTM': 'ftm', 'FTA': 'fta',
            'OREB': 'orb', 'DREB': 'drb', 'AST': 'ast', 'STL': 'stl', 'BLK': 'blk', 'TO': 'tov',
            'FOUL': 'pf', 'CHARGE': 'chg'}


def parse_segments(path):
    """Read a per-segment box score (Player,Segment,2FGM,...) named like 10.02.26-Segments.csv."""
    out = defaultdict(dict)
    for r in csv.DictReader(open(path, encoding='utf-8-sig')):
        player, low = r['Player'].strip(), r['Segment'].strip().lower()
        if not player.startswith('#'):
            continue
        kind = 'scrimmage' if low in SCRIMMAGE_SEGMENTS else 'special' if low in SPECIAL_SEGMENTS else None
        if kind:
            out[kind][player] = {k: int(r[c] or 0) for c, k in SEG_COLS.items() if int(r[c] or 0)}
    return out


def main():
    csvs = sorted(glob.glob(os.path.join(HERE, '*.csv')))
    seg_files = [p for p in csvs if p.endswith('Segments.csv')]
    events = [parse(p) for p in csvs if p not in seg_files]
    events.sort(key=lambda e: (e['type'] != 'practice', e['date'] or '', e['file']))
    by_date = {e['date']: e for e in events if e['type'] == 'practice'}
    for p in seg_files:
        e = by_date.get(parse_date(os.path.basename(p)))
        if not e:
            print(f'Skipped {os.path.basename(p)}: no practice file with that date')
            continue
        e['segments'].update(parse_segments(p))
        e['segmentFile'] = os.path.basename(p)
    data = {'events': events, 'built': __import__('datetime').date.today().isoformat()}
    tpl = open(os.path.join(HERE, 'dashboard_template.html'), encoding='utf-8').read()
    logo = os.path.join(HERE, 'triton_logo.jpg')
    logo_uri = 'data:image/jpeg;base64,' + base64.b64encode(open(logo, 'rb').read()).decode() if os.path.exists(logo) else ''
    out = tpl.replace('/*__DATA__*/null', json.dumps(data, separators=(',', ':'))).replace('__LOGO__', logo_uri)
    open(os.path.join(HERE, 'Practice_Dashboard.html'), 'w', encoding='utf-8').write(out)
    # index.html is the GitHub Pages entry point, so it gets a full document wrapper
    page = ('<!doctype html>\n<html lang="en">\n<head>\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + out + '\n</html>\n')
    open(os.path.join(HERE, 'index.html'), 'w', encoding='utf-8').write(page)
    split = sum(1 for e in events if e['segments'])
    print(f'Built Practice_Dashboard.html and index.html: {len(events)} files, {split} with scrimmage/special splits')


if __name__ == '__main__':
    main()
