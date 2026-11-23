"""신호 규칙 후보 검증 (과적합 방지: 기간을 앞·뒤 절반으로 나눠 둘 다에서 효과가 있어야 채택).

사용: python3 tune.py [site 폴더]   — build.py 가 만든 site/data/p 의 일봉을 읽어 오프라인 계산
출력: 후보별 시장·기간별 20일 초과수익(기준 대비)과 적중률 차이
"""
import json, os, sys, glob
from collections import defaultdict
from multiprocessing import Pool

from indicators import compute

SITE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'site')
H = 20  # 판단 기간(거래일)


def load(path):
    j = json.load(open(path))
    return [{'time': t, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v}
            for t, o, h, l, c, v in zip(j['t'], j['o'], j['h'], j['l'], j['c'], j['v'])]


def candidates(b, r, i):
    """i일 종가 기준으로 성립하는 후보 신호 목록 (이름, 방향 +1 매수 / -1 매도)."""
    C = [x['close'] for x in b]
    up, lo, mid, adx, pdi, mdi, vr, sq = r['up'], r['lo'], r['mid'], r['adx'], r['pdi'], r['mdi'], r['vr'], r['sq']
    if None in (up[i], up[i - 1], adx[i], adx[i - 3], vr[i], vr[i - 1]):
        return []
    out = []
    vmax = max(vr[i], vr[i - 1] or 0, vr[i - 2] or 0)
    bull = pdi[i] > mdi[i]
    # 기존 규칙 (현재 앱)
    if r['brk'][i] > 0 and r['score'][i] == 3: out.append(('기존 ★3↑', 1))
    if r['brk'][i] < 0 and r['score'][i] == 3: out.append(('기존 ★3↓(하락 추종)', -1))
    # 상승 돌파 변형
    sq_recent = any(sq[j] for j in range(i - 10, i))
    if C[i] > up[i] and C[i - 1] <= up[i - 1] and sq_recent and vmax >= 1.5 and bull:
        out.append(('스퀴즈 돌파↑ (10일 내 응축 → 첫 상단 돌파 + 거래량)', 1))
    if C[i] > up[i] and C[i - 1] <= up[i - 1] and vmax >= 1.5 and adx[i] < 20:
        out.append(('저ADX 첫 돌파↑ (ADX<20 + 거래량)', 1))
    # 추세 눌림
    if adx[i] >= 25 and bull and b[i]['low'] <= mid[i] < C[i]:
        out.append(('추세 눌림↑ (ADX≥25·+DI 우세, 20일선 터치 후 위 마감)', 1))
    # 과매도 반등 (하락 이탈을 역으로)
    if C[i] < lo[i] and vmax >= 1.5:
        out.append(('투매↑ (하단 이탈 + 거래량, 역발상 매수)', 1))
    if C[i - 1] < lo[i - 1] and C[i] > lo[i] and C[i] > b[i]['open']:
        out.append(('하단 재진입↑ (전일 하단 밖 → 오늘 양봉으로 복귀)', 1))
    if C[i - 1] < lo[i - 1] and (vr[i - 1] or 0) >= 2 and C[i] > b[i - 1]['high']:
        out.append(('투매 확인↑ (전일 대량 하단 이탈 → 오늘 전일 고가 돌파)', 1))
    # 매도 쪽
    if C[i - 1] > up[i - 1] and C[i] < up[i] and C[i] < b[i]['open'] and vmax >= 1.5:
        out.append(('돌파 실패↓ (전일 상단 밖 → 오늘 대량 음봉 복귀)', -1))
    if adx[i] >= 40 and adx[i] < adx[i - 3] and bull and C[i] < mid[i]:
        out.append(('과열 추세 꺾임↓ (ADX≥40 하락 전환 + 20일선 이탈)', -1))
    return out


def one(path):
    mk = path.split(os.sep)[-2]
    b = load(path)
    N = len(b)
    if N < 120:
        return []
    r = compute(b)
    C = [x['close'] for x in b]
    res = []
    for j, t in r['sigs']:  # 기존 마커 (분산·경고·매집 포함)
        if t in ('분산', '경고', '매집') and j + H < N:
            res.append((mk, '기존 ' + t, 1 if t == '매집' else -1, b[j]['time'], C[j + H] / C[j] - 1))
    for i in range(30, N - H):
        f = C[i + H] / C[i] - 1
        if i % 5 == 0:
            res.append((mk, '기준(아무 날)', 1, b[i]['time'], f))
        for name, d in candidates(b, r, i):
            res.append((mk, name, d, b[i]['time'], f))
    return res


def main():
    files = [f for mk in ('KR', 'US') for f in glob.glob(os.path.join(SITE, 'data', 'p', mk, '*.json'))]
    with Pool(4) as p:
        rows = [x for part in p.imap_unordered(one, files, chunksize=20) for x in part]
    dates = sorted({x[3] for x in rows})
    cut = dates[len(dates) // 2]
    acc = defaultdict(list)
    for mk, name, d, t, f in rows:
        acc[(mk, name, d, '앞' if t < cut else '뒤')].append(f)
    print(f'기간 분할 기준일 {cut} (앞 {dates[0]}~, 뒤 ~{dates[-1]}), 판단 {H}거래일')
    out = {}
    for mk in ('KR', 'US'):
        print(f'\n== {mk} ==  초과 = 신호 방향 기준 20일 평균 − 기준, 적중차 = 적중률 − 기준 같은 방향 확률')
        names = sorted({k[1] for k in acc if k[0] == mk and k[1] != '기준(아무 날)'})
        for name in names:
            line = []
            for half in ('앞', '뒤'):
                base = acc[(mk, '기준(아무 날)', 1, half)]
                bm, bu = sum(base) / len(base), sum(1 for x in base if x > 0) / len(base)
                for d in (1, -1):
                    v = acc.get((mk, name, d, half))
                    if not v:
                        continue
                    m, upr = sum(v) / len(v), sum(1 for x in v if x > 0) / len(v)
                    ex = (m - bm) * 100 * d
                    hd = ((upr - bu) if d > 0 else ((1 - upr) - (1 - bu))) * 100
                    line.append((half, len(v), ex, hd))
                    out.setdefault(mk, {}).setdefault(name, {})[half] = {'n': len(v), 'ex': round(ex, 2), 'hd': round(hd, 1)}
            ok = len(line) == 2 and all(x[2] > 0.5 and x[3] > 2 and x[1] >= 100 for x in line)
            print(f"{'채택' if ok else '    '} {name:45} " + ' | '.join(f'{h} n={n:6d} 초과 {ex:+6.2f}%p 적중차 {hd:+5.1f}%p' for h, n, ex, hd in line))
    json.dump(out, open(os.path.join(SITE, 'data', 'tune.json'), 'w'), ensure_ascii=False)


if __name__ == '__main__':
    main()
