#!/usr/bin/env python3
"""Construye catalogo/ (todas las cartas Pokémon TCG en inglés) desde tcgcsv.com.
Lo ejecuta GitHub Actions cada semana; no necesita nada fuera de la librería estándar."""
import json, os, re, sys, time, unicodedata, urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = 'https://tcgcsv.com/tcgplayer/3'
OUT = sys.argv[1] if len(sys.argv) > 1 else 'public/catalogo'
HERE = os.path.dirname(os.path.abspath(__file__))

def get(url, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'lostbinder-datos (catalogo semanal)'})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            if k == tries - 1: raise
            time.sleep(2 + 3 * k)

def nrm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().lower()
    s = s.replace('’', "'")
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()

# ---------- Pokémon por nombre ----------
NOMBRES = json.load(open(os.path.join(HERE, 'nombres.json'), encoding='utf-8'))
EXTRA = {'nidoran f': 29, 'nidoran m': 32, 'nidoran': 29, 'farfetch d': 83, 'sirfetch d': 865,
         'mr mime': 122, 'mime jr': 439, 'mr rime': 866, 'type null': 772, 'flabebe': 669}
NAME2DEX = {nrm(n): d for d, n in NOMBRES}
NAME2DEX.update(EXTRA)
KEYS = sorted(NAME2DEX, key=len, reverse=True)
RX = re.compile(r'(?<![a-z0-9])(' + '|'.join(re.escape(k) for k in KEYS) + r')(?![a-z0-9])')

def dex_of(name):
    base = re.sub(r'\s+-\s+[A-Z]*-?\d+[a-z]?(/[A-Z0-9-]+)?(\s|$)', ' ', name)   # quita « - 006/132»
    base = re.sub(r'\(.*?\)|\[.*?\]', ' ', base)
    t = nrm(base.replace('♀', ' f').replace('♂', ' m'))
    found = []
    for m in RX.finditer(t):
        d = NAME2DEX[m.group(1)]
        if d not in found: found.append(d)
    return found

# ---------- series ----------
ESPECIAL = re.compile(r"mcdonald|trainer kit|training kit|jumbo|league|deck exclusives|prize pack|trick or trade|battle academy|"
                      r"world championship|my first battle|blister|burger king|first partner|miscellaneous|professor program|"
                      r"pikachu world|nintendo promos|pop series|alternate art|player placement|countdown calendar|kids wb|"
                      r"e-reader sample|southeast asia|trading card game classic|ash vs team rocket|best of promos|wotc promo|rumble", re.I)
ERAS = [('2003-06-01', '01-wizards'), ('2007-05-01', '02-ex'), ('2009-02-01', '03-diamante-perla'), ('2010-02-01', '04-platino'),
        ('2011-04-01', '05-heartgold-soulsilver'), ('2013-12-01', '06-negro-blanco'), ('2016-12-01', '07-xy'),
        ('2019-11-15', '08-sol-luna'), ('2023-03-01', '09-espada-escudo'), ('2025-09-01', '10-escarlata-purpura'), ('9999', '11-megaevolucion')]
NOMSERIE = {'00-promos-y-especiales': 'Promos y especiales', '01-wizards': 'Wizards of the Coast', '02-ex': 'EX',
            '03-diamante-perla': 'Diamante y Perla', '04-platino': 'Platino', '05-heartgold-soulsilver': 'HeartGold y SoulSilver',
            '06-negro-blanco': 'Negro y Blanco', '07-xy': 'XY', '08-sol-luna': 'Sol y Luna', '09-espada-escudo': 'Espada y Escudo',
            '10-escarlata-purpura': 'Escarlata y Púrpura', '11-megaevolucion': 'Megaevolución'}

def serie(g, fecha):
    if g.get('isSupplemental') or ESPECIAL.search(g['name']) or not fecha: return '00-promos-y-especiales'
    for lim, sid in ERAS:
        if fecha < lim: return sid
    return '11-megaevolucion'

def main():
    hoy = time.strftime('%Y-%m-%d')
    groups = get(BASE + '/groups')['results']
    def bajar(g):
        gid = g['groupId']
        return g, get(f'{BASE}/{gid}/products')['results'], get(f'{BASE}/{gid}/prices')['results']
    with ThreadPoolExecutor(6) as ex:
        datos = list(ex.map(bajar, groups))

    RAR, VER = [], []
    def idx(lst, v):
        if v not in lst: lst.append(v)
        return lst.index(v)

    series, pk_rows, esc_sets, esc_cards = {}, {}, [], []
    os.makedirs(os.path.join(OUT, 'expansiones'), exist_ok=True)
    os.makedirs(os.path.join(OUT, 'pokemon'), exist_ok=True)
    for g, prods, prices in datos:
        gid = g['groupId']
        fecha = g['publishedOn'][:10]
        if fecha >= hoy[:7] and g.get('abbreviation') in ('PR', 'POP', 'BLE', 'BKP', 'FPP', 'MCAP', 'PWCP', 'PPP', ''):
            fecha = ''   # fecha de relleno en tcgcsv: no es la real
        vers = {}
        for p in prices:
            vers.setdefault(p['productId'], set()).add(p.get('subTypeName') or 'Normal')
        rows = []
        for p in prods:
            ext = {e['name']: e['value'] for e in p.get('extendedData', [])}
            if 'Number' not in ext: continue                      # producto sellado, no carta
            name = p['name']
            esp = bool(str(ext.get('HP') or '').strip()) and str(ext.get('Card Type') or '').lower() not in ('trainer', 'energy', 'supporter', 'item', 'stadium')
            dx = dex_of(name) if esp else []
            rar = idx(RAR, ext.get('Rarity') or 'None')
            mask = 0
            for v in sorted(vers.get(p['productId'], {'Normal'})):
                mask |= 1 << idx(VER, v)
            dexv = (dx[0] if len(dx) == 1 else dx) if dx else 0
            if esp and not dx: dexv = [0]          # Pokémon sin identificar: sigue contando como Pokémon
            row = [p['productId'], ext['Number'], name, '', rar, '', dexv, mask]
            rows.append(row)
            for d in dx:
                pk_rows.setdefault(d, []).append([gid] + row)
        if not rows: continue
        def numkey(r):
            m = re.match(r'([A-Z]*)(\d+)', str(r[1]).replace(' ', ''))
            return (m.group(1), int(m.group(2))) if m else ('~', 0)
        rows.sort(key=numkey)
        ruta = f'expansiones/{gid}.json'
        json.dump({'gid': gid, 'cartas': rows}, open(os.path.join(OUT, ruta), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        sid = serie(g, fecha)
        series.setdefault(sid, []).append({'n': g['name'], 'c': g.get('abbreviation') or '', 'f': fecha, 'gid': gid, 't': len(rows), 'r': ruta})
        si = len(esc_sets)
        esc_sets.append([gid, g.get('abbreviation') or '', g['name'], '', fecha])
        for r in rows:
            d = r[6] if isinstance(r[6], int) else (r[6][0] if r[6] else 0)
            esc_cards.append([si, r[0], r[1], r[2], '', r[4], d or 0])

    pk = [0] * len(NOMBRES)
    for d, rs in pk_rows.items():
        if 1 <= d <= len(pk):
            pk[d - 1] = len(rs)
            json.dump({'cartas': rs}, open(os.path.join(OUT, f'pokemon/{d:04d}.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    indice = {'fecha': hoy, 'rar': RAR, 'ver': VER, 'pk': pk,
              'series': [{'id': sid, 'n': NOMSERIE[sid], 'exp': exp} for sid, exp in sorted(series.items())]}
    json.dump(indice, open(os.path.join(OUT, 'indice.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    json.dump({'fecha': hoy, 'sets': esc_sets, 'cards': esc_cards, 'rar': RAR}, open(os.path.join(OUT, 'escaner.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, separators=(',', ':'))
    print(f'{len(esc_sets)} expansiones · {len(esc_cards)} cartas · {sum(1 for x in pk if x)} Pokémon con cartas')

if __name__ == '__main__':
    main()
