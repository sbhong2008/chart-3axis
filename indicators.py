"""BB · ADX · Volume 3축 지표 — web/index.html 의 JS 계산과 같은 규칙(섹터 목록 요약용).

bars: [{'time','open','high','low','close','volume'}, ...] (시간순)
"""
import math


def compute(bars):
    N = len(bars)
    C = [b['close'] for b in bars]
    up, lo, mid, bw, sq = [None] * N, [None] * N, [None] * N, [None] * N, [False] * N
    for i in range(19, N):
        s = C[i - 19:i + 1]
        m = sum(s) / 20
        sd = math.sqrt(sum((x - m) ** 2 for x in s) / 20)
        mid[i], up[i], lo[i] = m, m + 2 * sd, m - 2 * sd
        bw[i] = 4 * sd / m if m else 0
    for i in range(19, N):
        mn = min(bw[j] for j in range(max(19, i - 100), i + 1))
        sq[i] = bw[i] <= mn * 1.25

    pdi, mdi, adx = [None] * N, [None] * N, [None] * N
    tr14 = p14 = m14 = 0.0
    dxs, av = [], None
    for i in range(1, N):
        b, q = bars[i], bars[i - 1]
        tr = max(b['high'] - b['low'], abs(b['high'] - q['close']), abs(b['low'] - q['close']))
        um, dm = b['high'] - q['high'], q['low'] - b['low']
        pdm = um if (um > dm and um > 0) else 0
        mdm = dm if (dm > um and dm > 0) else 0
        if i <= 14:
            tr14 += tr; p14 += pdm; m14 += mdm
        else:
            tr14 += tr - tr14 / 14; p14 += pdm - p14 / 14; m14 += mdm - m14 / 14
        if i >= 14:
            P = 100 * p14 / tr14 if tr14 else 0
            M = 100 * m14 / tr14 if tr14 else 0
            pdi[i], mdi[i] = P, M
            dx = 100 * abs(P - M) / (P + M) if (P + M) else 0
            if av is None:
                dxs.append(dx)
                if len(dxs) == 14:
                    av = sum(dxs) / 14
            else:
                av = (av * 13 + dx) / 14
            if av is not None:
                adx[i] = av

    vr = [None] * N
    for i in range(19, N):
        vma = sum(bars[j]['volume'] for j in range(i - 19, i + 1)) / 20
        vr[i] = bars[i]['volume'] / vma if vma else 0

    score, brk, dr = [None] * N, [0] * N, [0] * N
    for i in range(N):
        if adx[i] is None or up[i] is None:
            continue
        brk[i] = 1 if C[i] > up[i] else (-1 if C[i] < lo[i] else 0)
        dr[i] = 1 if pdi[i] > mdi[i] else -1
        prev = adx[i - 3] if i >= 3 and adx[i - 3] is not None else adx[i]
        adx_up = adx[i] >= 20 and adx[i] > prev
        vol_up = max(vr[i] or 0, (vr[i - 1] or 0) if i >= 1 else 0, (vr[i - 2] or 0) if i >= 2 else 0) >= 1.5
        score[i] = (1 if brk[i] else 0) + (1 if adx_up else 0) + (1 if vol_up else 0)

    def sgn(i):
        if adx[i] is None:
            return 0.0
        return adx[i] * max(-1.0, min(1.0, (pdi[i] - mdi[i]) / 10))

    # 신호 마커 (JS markers 와 같은 규칙)
    sigs = []
    last_sig, last_warn = -9, -99
    for i in range(N):
        # 상승 돌파만 추종 신호로 사용 (하락 이탈 추종은 2년 검증에서 역효과 → 아래 '투매'로 전환)
        if score[i] is not None and score[i] >= 2 and brk[i] > 0 and i - last_sig > 3:
            last_sig = i
            sigs.append((i, ('★3' if score[i] == 3 else '2') + '↑'))
        if i > 45 and adx[i] is not None:
            pj = i - 40
            for j in range(i - 40, i - 5):
                if C[j] > C[pj]:
                    pj = j
            recent = max(C[pj:i])
            if (C[i] > recent and adx[pj] is not None and adx[pj] >= 25 and adx[i] < adx[pj] - 3
                    and (vr[i] or 0) < 1 and i - last_warn > 10):
                last_warn = i
                sigs.append((i, '경고'))
    # 투매(역발상 매수): BB 하단 아래 마감 + 최근 3일 내 거래량 1.5배 이상
    # 과열 추세 꺾임(매도): ADX≥40 이 3일 전보다 낮아지고(+DI 우세 중) 종가가 20일선 아래
    last_cap = last_brk = -99
    for i in range(3, N):
        if lo[i] is None or adx[i] is None or adx[i - 3] is None:
            continue
        vmax = max(vr[i] or 0, vr[i - 1] or 0, vr[i - 2] or 0)
        if C[i] < lo[i] and vmax >= 1.5 and i - last_cap > 5:
            last_cap = i; sigs.append((i, '투매'))
        if adx[i] >= 40 and adx[i] < adx[i - 3] and pdi[i] > mdi[i] and C[i] < mid[i] and i - last_brk > 10:
            last_brk = i; sigs.append((i, '꺾임'))
    last_dist = last_acc = -99
    for i in range(40, N):
        if vr[i] is None or vr[i] < 2:
            continue
        b = bars[i]
        hi = max(bars[j]['high'] for j in range(i - 40, i + 1))
        lw = min(bars[j]['low'] for j in range(i - 40, i + 1))
        if b['close'] < b['open'] and b['high'] >= hi * .95 and C[i - 40] < C[i] * .97 and i - last_dist > 10:
            last_dist = i; sigs.append((i, '분산'))
        if b['close'] >= b['open'] and b['low'] <= lw * 1.05 and C[i - 40] > C[i] * 1.1 and i - last_acc > 10:
            last_acc = i; sigs.append((i, '매집'))
    sigs.sort()

    waves = elliott(bars, score, brk, sgn, N)
    return dict(mid=mid, up=up, lo=lo, bw=bw, sq=sq, pdi=pdi, mdi=mdi, adx=adx, vr=vr,
                score=score, brk=brk, dir=dr, sgn=sgn, sigs=sigs, waves=waves)


def zigzag(bars, th):
    P, dn, ei = [], 0, 0
    for i in range(1, len(bars)):
        h, l = bars[i]['high'], bars[i]['low']
        if dn >= 0:
            if h >= bars[ei]['high']:
                if not dn:
                    dn = 1
                ei = i
            elif l <= bars[ei]['high'] * (1 - th):
                P.append((ei, 'H')); dn = -1; ei = i
        else:
            if l <= bars[ei]['low']:
                ei = i
            elif h >= bars[ei]['low'] * (1 + th):
                P.append((ei, 'L')); dn = 1; ei = i
    return P


def elliott(bars, score, brk, sgn, N):
    """엘리엇 대응 파동 '시작점' 자동 추정 (JS waveLab 과 같은 규칙)."""
    Z3, Z4, Z5 = zigzag(bars, .03), zigzag(bars, .04), zigzag(bars, .05)
    lab, last = [], -99
    for s in range(30, N):
        if score[s] is None or score[s] < 2 or not brk[s]:
            continue
        calm = any(abs(sgn(j)) < 20 for j in range(s - 15, s))
        if not calm or s - last < 30:
            continue
        last = s
        pts = []
        if brk[s] > 0:
            i3 = s
            for j in range(s - 15, s + 1):
                if bars[j]['low'] < bars[i3]['low']:
                    i3 = j
            h2 = next((p for p in reversed(Z3) if p[1] == 'H' and p[0] < i3), None)
            l1 = next((p for p in reversed(Z3) if p[1] == 'L' and h2 and p[0] < h2[0]), None)
            if h2 and l1 and bars[l1[0]]['low'] < bars[i3]['low'] and i3 - l1[0] <= 60:
                pts += [(l1[0], '1파'), (h2[0], '2파')]
            pts.append((i3, '3파'))
            fw = [p for p in Z5 if p[0] > i3]
            if fw and fw[0][1] != 'H':
                fw.pop(0)
            for n, L in enumerate(['4파', '5파', 'A파', 'B파', 'C파']):
                if n < len(fw):
                    pts.append((fw[n][0], L))
        else:
            ks = [k for k, p in enumerate(Z4) if p[1] == 'H' and p[0] <= s]
            if not ks:
                continue
            k = ks[-1]
            if k >= 2 and bars[Z4[k - 2][0]]['high'] > bars[Z4[k][0]]['high']:
                pts += [(Z4[k - 2][0], 'A파'), (Z4[k - 1][0], 'B파')]
            pts.append((Z4[k][0], 'C파'))
        first = min(p[0] for p in pts)
        lab = [x for x in lab if x[0] < first] + pts
    return sorted(lab)


def summary(bars, mkt='KR'):
    """섹터·홈 목록용 마지막 날 요약 + 데이터 품질 플래그. (요약, 지표) 반환."""
    N = len(bars)
    if N < 60:
        return None, None
    r = compute(bars)
    i = N - 1
    adx, score = r['adx'], r['score']
    if adx[i] is None or score[i] is None:
        return None, None
    valid = sorted(x for x in r['bw'] if x is not None)
    bwp = sum(1 for x in valid if x < r['bw'][i]) / len(valid) * 100
    s = r['sgn'](i)
    a = adx[i]
    regime = ('응축' if r['sq'][i] else '횡보') if a < 20 else (('추세시작' if a < 25 else '강한추세') + ('↑' if r['dir'][i] > 0 else '↓'))
    sig = next(((bars[j]['time'], t) for j, t in reversed(r['sigs']) if N - 1 - j <= 10), None)
    wave = r['waves'][-1] if r['waves'] else None
    C = [b['close'] for b in bars]
    ret = lambda k: round((C[i] / C[i - k] - 1) * 100, 1) if N > k and C[i - k] else None
    ch = round((C[i] / C[i - 1] - 1) * 100, 2) if C[i - 1] else 0
    tv = sum(bars[j]['close'] * bars[j]['volume'] for j in range(N - 20, N)) / 20
    flags = []
    if abs(ch) > (30 if mkt == 'KR' else 25):
        flags.append('급변')          # 하루 변동이 상·하한(국내 ±30%)을 넘거나 미국 ±25% 초과 → 원본 데이터 확인 필요
    if N < 120:
        flags.append('짧은이력')      # 120거래일 미만: 백분위·파동 신뢰도 낮음
    return {
        'd': bars[i]['time'], 'c': C[i], 'ch': ch, 'r20': ret(20), 'r60': ret(60), 'tv': round(tv),
        'rg': regime, 'sc': score[i], 'sa': round(s, 1), 'adx': round(a, 1), 'bwp': round(bwp), 'vr': round(r['vr'][i] or 0, 2),
        'sq': bool(r['sq'][i]),
        'sig': [sig[0], sig[1]] if sig else None,
        'wv': [bars[wave[0]]['time'], wave[1]] if wave else None,
        'fl': flags,
    }, r


BULL = {'★3↑', '2↑', '매집', '투매'}
BEAR = {'경고', '분산', '꺾임'}


def forward_stats(bars, r, recent_days=63):
    """검증용: 신호·국면별 5/20일 뒤 수익률 표본. [(구분, 키, 최근여부, f5, f20)]"""
    C = [b['close'] for b in bars]
    N = len(C)
    out = []
    for j, t in r['sigs']:
        if j + 20 < N:
            out.append(('sig', t, j >= N - 21 - recent_days, C[j + 5] / C[j] - 1, C[j + 20] / C[j] - 1, bars[j]['time']))
    adx, sq, dr = r['adx'], r['sq'], r['dir']
    for j in range(30, N - 20, 5):  # 5일 간격 표본
        if adx[j] is None:
            continue
        a = adx[j]
        k = ('횡보' if a < 20 else ('강세' if dr[j] > 0 else '약세'))
        out.append(('rg', k, j >= N - 21 - recent_days, C[j + 5] / C[j] - 1, C[j + 20] / C[j] - 1, bars[j]['time']))
        out.append(('rg', '전체(기준)', j >= N - 21 - recent_days, C[j + 5] / C[j] - 1, C[j + 20] / C[j] - 1, bars[j]['time']))
    return out
