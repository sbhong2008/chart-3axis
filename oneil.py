"""오닐(CAN SLIM·공매도 투자 기법) 규칙 — 파이썬에서만 계산하고 결과를 데이터로 내보냄(화면은 표시만).

1) 시장 상태(지수): 분산일 누적 · 조정 · 반등 시도(n일째) · 반등 확인일(4일째 이후 +1.25%↑, 거래량 증가) → 상승 확인 · 압력 증가
2) 상대 강도(RS) 원점수: 최근 3·6·9·12개월 수익률(최근 분기 2배 가중) → 빌드에서 시장별 백분위 1~99
3) 바닥 패턴(주봉): 손잡이 달린 컵 · 컵 · 이중 바닥(W) · 평평한 바닥 · 높이 치솟는 깃발형 → 피벗·깊이·기간·몇 번째 바닥·점검 목록·상태
4) 신호(일봉, 검증 대상): 바닥돌파(피벗 돌파 + 거래량 +40%↑) · 50일↓(장기 상승 뒤 대량 거래 50일선 이탈) ·
   반등실패(50일선 이탈 뒤 50일선까지 반등했다 밀림) · 최후고점(상승 뒤 최대 주간 상승 + 200일선 과도 이격)
수치는 책의 기준을 그대로 쓰고 종목별 예외는 두지 않음.
"""
import math

FTD_GAIN = 0.0125          # 반등 확인일 최소 상승률
CORR_DD = 0.08             # 조정 판정: 상승 이후 고점 대비 하락폭
BRK_VOL = 1.4              # 돌파 거래량: 50일 평균의 1.4배(+40%)


def sma(x, n):
    out, s = [None] * len(x), 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def dist_days(C, V):
    """분산일(종가 0.2%↓ + 거래량 전일 초과) 표시와 최근 20거래일 누적(그날 종가 +5% 회복 시 소멸) — indicators.py 와 같은 정의."""
    n = len(C)
    dd = [i > 0 and C[i - 1] and C[i] <= C[i - 1] * 0.998 and V[i] > V[i - 1] for i in range(n)]
    cnt = []
    for i in range(n):
        k, hi = 0, -1e300
        for j in range(i, max(-1, i - 20), -1):
            if dd[j] and hi < C[j] * 1.05:
                k += 1
            hi = max(hi, C[j])
        cnt.append(k)
    return dd, cnt


# ---------- 1) 시장 상태 ----------
def market_state(bars):
    """지수 일봉 → 상태 기계. 반환 {'st','k'(반등 시도 일수),'since','ftd','dd','ma50','dd_pct','ev':[[날짜,종류,설명]]}"""
    n = len(bars)
    if n < 70:
        return None
    C = [b['close'] for b in bars]; L = [b['low'] for b in bars]; V = [b.get('volume') or 0 for b in bars]
    T = [b['time'] for b in bars]
    ma50 = sma(C, 50)
    _, ddn = dist_days(C, V)
    hasv = sum(1 for v in V[-60:] if v) > 40
    st = '상승 확인' if C[60] >= ma50[60] else '조정 중'
    hi, low, day1, since, ftd, ev = C[60], L[60], None, T[60], None, []
    for i in range(61, n):
        if st in ('상승 확인', '압력 증가'):
            hi = max(hi, C[i])
            if C[i] <= hi * (1 - CORR_DD) or (C[i] < ma50[i] and ddn[i] >= 6):
                st, low, day1, since = '조정 중', L[i], None, T[i]
                ev.append([T[i], '조정', f'고점 대비 −{(1 - C[i] / hi) * 100:.1f}%'])
            else:
                nst = '압력 증가' if (ddn[i] >= 5 or C[i] < ma50[i]) else '상승 확인'
                if nst != st:
                    st, since = nst, T[i]
        elif st == '조정 중':
            low = min(low, L[i])
            if C[i] > C[i - 1]:
                st, day1, since = '반등 시도', i, T[i]
        elif st == '반등 시도':
            if L[i] < low:                                   # 반등 시도 실패(저점 깨짐)
                st, low, day1, since = '조정 중', L[i], None, T[i]
                ev.append([T[i], '실패', '반등 시도 저점 이탈'])
                continue
            k = i - day1 + 1
            g = C[i] / C[i - 1] - 1
            if k >= 4 and g >= FTD_GAIN and (not hasv or V[i] > V[i - 1]):
                st, hi, ftd, since = '상승 확인', C[i], T[i], T[i]
                ev.append([T[i], '확인일', f'반등 {k}일째 +{g * 100:.1f}%'])
    k = (n - day1) if st == '반등 시도' and day1 is not None else None
    peak = max(C[-63:])
    return {'st': st, 'k': k, 'since': since, 'ftd': ftd, 'dd': ddn[-1], 'ma50': C[-1] >= ma50[-1],
            'dd_pct': round((1 - C[-1] / peak) * 100, 1), 'ev': ev[-12:]}


# ---------- 2) 상대 강도 원점수 ----------
def rs_raw(C):
    n = len(C)
    if n < 130:
        return None
    r = lambda k: C[-1] / C[-1 - min(k, n - 1)] - 1
    return 0.4 * r(63) + 0.2 * r(126) + 0.2 * r(189) + 0.2 * r(252)


def pct_rank(vals):
    """{id: 원점수} → {id: 1~99}"""
    items = sorted((v, k) for k, v in vals.items() if v is not None)
    m = len(items)
    return {k: max(1, min(99, int(round((i + 1) / m * 99)))) for i, (_, k) in enumerate(items)} if m else {}


# ---------- 3) 바닥 패턴 ----------
def weekly(bars):
    import datetime as dt
    W = []
    for i, b in enumerate(bars):
        k = dt.date.fromisoformat(b['time']).isocalendar()[:2]
        if not W or W[-1]['k'] != k:
            W.append({'k': k, 'h': b['high'], 'l': b['low'], 'c': b['close'], 'v': b.get('volume') or 0, 'i0': i, 'i1': i})
        else:
            w = W[-1]
            w['h'] = max(w['h'], b['high']); w['l'] = min(w['l'], b['low']); w['c'] = b['close']
            w['v'] += b.get('volume') or 0; w['i1'] = i
    return W


def stage(W, p):
    """p(왼쪽 고점) 이전 상승 구간(최근 2년 최저점 이후)에서 고점 대비 10%↑ 눌림 횟수 + 1 = 몇 번째 바닥"""
    lo = min(range(max(0, p - 104), p + 1), key=lambda x: W[x]['l'])
    k, hi, dd = 1, W[lo]['h'], False
    for x in range(lo, p + 1):
        if W[x]['h'] > hi:
            hi, dd = W[x]['h'], False
        elif not dd and W[x]['l'] <= hi * 0.9:
            k, dd = k + 1, True
    return min(k, 5)


def find_base(W, end, bear=False):
    """주봉 W 의 end 주까지 끝나는 바닥 패턴(가장 최근 것). 없으면 None."""
    if end < 12:
        return None
    s0 = max(0, end - 65)
    p = max(range(s0, end + 1), key=lambda x: W[x]['h'])
    weeks = end - p + 1
    if weeks < 3:
        return None
    H, L = W[p]['h'], min(W[x]['l'] for x in range(p, end + 1))
    depth = 1 - L / H
    pre = min(W[x]['l'] for x in range(max(0, p - 26), p + 1))
    up = H / pre - 1 if pre else 0
    b = min(range(p, end + 1), key=lambda x: W[x]['l'])
    vb = sum(W[x]['v'] for x in range(p, end + 1)) / weeks
    dmax = 0.50 if bear else 0.33
    ck = [[f'이전 상승 +{up * 100:.0f}% (기준 30%↑)', up >= 0.30]]
    res = None
    # 높이 치솟는 깃발형: 4~8주에 +90%↑ 뒤 3~5주 10~25% 조정
    pre8 = min(W[x]['l'] for x in range(max(0, p - 8), p + 1))
    if H / pre8 - 1 >= 0.90 and 3 <= weeks <= 6 and depth <= 0.25:
        res = {'k': '높이 치솟는 깃발형', 'pv': H, 'ck': [[f'4~8주 +{(H / pre8 - 1) * 100:.0f}% (기준 90~120%↑)', True],
                                                   [f'조정 −{depth * 100:.0f}% (기준 10~25%)', 0.10 <= depth <= 0.25]]}
    elif weeks >= 7 and 0.12 <= depth <= dmax:
        rng = H - L
        bottom = sum(1 for x in range(p, end + 1) if W[x]['l'] <= L + 0.15 * rng)
        ushape = (b - p) >= 2 and bottom >= 2
        r = max(range(b, end + 1), key=lambda x: W[x]['h'])
        rec = (W[r]['h'] - L) / rng if rng else 0
        # 이중 바닥: 첫 저점(b1) → 가운데 봉우리(m) → 첫 저점을 살짝 깬 두 번째 저점(b)
        b1 = min(range(p, b - 1), key=lambda x: W[x]['l']) if b - p >= 3 else None
        m = max(range(b1, b + 1), key=lambda x: W[x]['h']) if b1 is not None else None
        if (b1 is not None and W[b]['l'] < W[b1]['l'] <= W[b]['l'] * 1.06 and m is not None
                and W[m]['h'] >= L + 0.4 * rng and b - b1 >= 3):
            res = {'k': '이중 바닥', 'pv': W[m]['h'], 'ck': [['두 번째 저점이 첫 저점을 살짝 깸', True],
                                                          [f'가운데 봉우리 = 피벗', True]]}
        elif rec >= 0.85:
            hd = end - r
            hl = min(W[x]['l'] for x in range(r + 1, end + 1)) if hd >= 1 else None
            hdep = 1 - hl / W[r]['h'] if hl else 0
            upper = hl is not None and hl > L + rng / 2
            hv = sum(W[x]['v'] for x in range(r + 1, end + 1)) / hd if hd >= 1 else None
            if hd >= 1 and hdep <= 0.15 and upper:
                res = {'k': '손잡이 달린 컵', 'pv': W[r]['h'], 'hs': r + 1,
                       'ck': [['U자 바닥(V자 아님)', ushape], [f'손잡이 {hd}주 (기준 1~2주↑)', hd >= 1],
                              [f'손잡이 −{hdep * 100:.0f}% (기준 8~12%)', hdep <= 0.12], ['손잡이 위쪽 절반', upper],
                              ['손잡이 거래량 감소', hv is not None and hv < vb]]}
            else:
                res = {'k': '컵(손잡이 전)', 'pv': H, 'ck': [['U자 바닥(V자 아님)', ushape],
                                                           [f'오른쪽 회복 {rec * 100:.0f}%', rec >= 0.85]]}
    elif weeks >= 5 and depth <= 0.15:
        res = {'k': '평평한 바닥', 'pv': H, 'ck': [[f'조정 −{depth * 100:.0f}% (기준 10~15% 이내)', True]]}
    if not res:
        return None
    stg = stage(W, p)
    res.update({'p': p, 'end': end, 'wk': weeks, 'dp': round(depth * 100, 1), 'up': round(up * 100), 'stg': stg})
    lim = '33%(약세장 50%)' if res['k'] not in ('평평한 바닥', '높이 치솟는 깃발형') else ''
    res['ck'] = ck + ([[f'깊이 −{depth * 100:.0f}% (기준 {lim} 이내)', depth <= dmax]] if lim else []) + res['ck'] + \
        [[f'{weeks}주 (기준 {"5주↑" if res["k"] == "평평한 바닥" else "3~6주" if "깃발" in res["k"] else "7~65주"})', True],
         [f'{stg}번째 바닥 (3번째↑ = 말기, 실패 위험)', stg <= 2]]
    return res


def base_now(bars, bear=False):
    """현재 바닥 패턴과 상태. 최근 8주 안에 피벗을 돌파했으면 그 바닥 기준으로 돌파·매수 구간·확장·실패를 판정."""
    W = weekly(bars)
    n = len(W)
    if n < 20:
        return None
    C = [b['close'] for b in bars]; V = [b.get('volume') or 0 for b in bars]
    av50 = sma(V, 50)
    c = C[-1]
    cand = None
    for back in range(0, 9):
        e = n - 1 - back
        bs = find_base(W, e if back == 0 else e, bear)
        if not bs:
            continue
        if back == 0 and c < bs['pv']:
            cand = (bs, None); break
        # back 주 전에 끝난 바닥: 그 뒤 피벗 돌파한 날 찾기
        i0 = W[e]['i1'] + 1 if back else None
        if back and i0 < len(C):
            bd = next((i for i in range(i0, len(C)) if C[i] > bs['pv']), None)
            if bd is not None:
                cand = (bs, bd); break
    if not cand:
        return None
    bs, bd = cand
    pv = bs['pv']
    out = {'k': bs['k'], 's': bars[W[bs['p']]['i0']]['time'], 'e': bars[W[bs['end']]['i1']]['time'], 'pv': pv,
           'dp': bs['dp'], 'wk': bs['wk'], 'stg': bs['stg'], 'up': bs['up'], 'ck': bs['ck'], 'stop': round(pv * 0.92, 4)}
    if bs.get('hs') is not None:
        out['hs'] = bars[W[bs['hs']]['i0']]['time']
    if bd is None:
        out['st'] = '형성 중'
        out['gap'] = round((pv / c - 1) * 100, 1)
    else:
        vr = V[bd] / av50[bd] if av50[bd] else None
        out['bd'], out['bv'] = bars[bd]['time'], (round((vr - 1) * 100) if vr else None)
        out['ck'] = out['ck'] + [[f'돌파 거래량 {"+" if vr and vr >= 1 else ""}{out["bv"]}% (기준 +40%↑)', bool(vr and vr >= BRK_VOL)]]
        low_after = min(b['low'] for b in bars[bd:])
        if low_after <= pv * 0.92 or c < pv * 0.97:
            out['st'] = '돌파 실패'
        elif c <= pv * 1.05:
            out['st'] = '매수 구간'
        else:
            out['st'] = f'확장 +{(c / pv - 1) * 100:.0f}%'
    return out


# ---------- 4) 신호(검증 대상) ----------
def signals(bars):
    """[(일봉 번호, 키)] — 바닥돌파 · 50일↓ · 반등실패 · 최후고점"""
    n = len(bars)
    if n < 120:
        return []
    C = [b['close'] for b in bars]; H = [b['high'] for b in bars]; V = [b.get('volume') or 0 for b in bars]
    ma50, ma200, av50 = sma(C, 50), sma(C, 200), sma(V, 50)
    out = []
    # 바닥돌파: 매주 '지난주까지의 바닥' 피벗을 이번 주에 거래량 +40%↑로 넘은 첫날(같은 피벗은 한 번)
    W = weekly(bars)
    seen = set()
    for e in range(20, len(W)):
        bs = find_base(W, e - 1)
        if not bs or (bs['p'], round(bs['pv'], 6)) in seen:
            continue
        for i in range(W[e]['i0'], W[e]['i1'] + 1):
            if C[i] > bs['pv'] and (i == 0 or C[i - 1] <= bs['pv']) and av50[i] and V[i] >= BRK_VOL * av50[i]:
                out.append((i, '바닥돌파')); seen.add((bs['p'], round(bs['pv'], 6))); break
    # 50일↓: 50일선이 오르는 장기 상승 중(최근 60일 안 50일선 +15%↑ 이격) 대량 거래(1.4배↑)로 첫 이탈
    last50 = -99
    for i in range(60, n):
        if ma50[i] is None or ma50[i - 20] is None or not av50[i]:
            continue
        if C[i] < ma50[i] and ma50[i - 1] is not None and C[i - 1] >= ma50[i - 1] \
                and V[i] >= BRK_VOL * av50[i] and ma50[i] > ma50[i - 20] and i - last50 > 20 \
                and max(C[j] / ma50[j] for j in range(i - 60, i) if ma50[j]) >= 1.15:
            out.append((i, '50일↓')); last50 = i
            # 반등실패: 이탈 뒤 30일 안 고가가 50일선 2% 이내까지 반등했다가 종가가 다시 아래·하락 마감
            for j in range(i + 2, min(n, i + 31)):
                if ma50[j] and H[j] >= ma50[j] * 0.98 and C[j] < ma50[j] and C[j] < C[j - 1]:
                    out.append((j, '반등실패')); break
    # 최후고점: 52주 저점 대비 +80%↑ 상승 중, 이번 주 상승폭이 상승 구간 최대이고 200일선보다 50%↑ 위
    lastc = -99
    for e in range(30, len(W)):
        i = W[e]['i1']
        if ma200[i] is None:
            continue
        lo = min(range(max(0, e - 52), e + 1), key=lambda x: W[x]['l'])
        g = W[e]['c'] / W[e - 1]['c'] - 1
        if W[e]['c'] / W[lo]['l'] - 1 >= 0.80 and C[i] >= ma200[i] * 1.5 and e - lastc > 8 and g > 0 \
                and all(g >= W[x]['c'] / W[x - 1]['c'] - 1 for x in range(lo + 1, e)):
            out.append((i, '최후고점')); lastc = e
    out.sort()
    return out


def breadth(series):
    """같은 시장 종목들의 일봉 목록 → 50일선 위 비율(%) · 52주(최대 250일) 신고가·신저가 수"""
    a50 = nh = nl = tot = 0
    for b in series:
        if len(b) < 60:
            continue
        C = [x['close'] for x in b]
        m = sum(C[-50:]) / 50
        tot += 1
        a50 += C[-1] >= m
        w = b[-250:]
        nh += b[-1]['high'] >= max(x['high'] for x in w)
        nl += b[-1]['low'] <= min(x['low'] for x in w)
    return {'a50': round(a50 / tot * 100) if tot else None, 'nh': nh, 'nl': nl, 'n': tot}


# ---------- 5) 종목 5묶음 · 시계열 기록 · 성과 분석 ----------
GROUPS = [('B', '① 매수 구간'), ('N', '② 피벗 근접'), ('R', '③ 최근 바닥돌파'), ('S', '④ RS 주도주'), ('W', '⑤ 경고')]
WARN = ('최후고점', '50일↓', '반등실패')


def letters(st, gap, oskey, rs, up):
    """묶음 글자: B 매수 구간 · N 피벗 근접(형성 중, 5% 이내) · R 최근 10일 바닥돌파 · S RS 90↑·상승 추세 · W 경고"""
    g = ''
    if st == '매수 구간':
        g += 'B'
    if st == '형성 중' and gap is not None and gap <= 5:
        g += 'N'
    if oskey == '바닥돌파':
        g += 'R'
    if (rs or 0) >= 90 and up:
        g += 'S'
    if st == '돌파 실패' or oskey in WARN:
        g += 'W'
    return g


def day_state(b, C, adx, dr, osg, i, bear):
    """i 번째 날 기준 상태(과거 다시 계산용): (패턴 상태, 피벗까지 %, 최근 10일 마지막 오닐 신호, RS 원점수, 상승 추세)"""
    pat = base_now(b[:i + 1], bear)
    ks = [k for j, k in osg if i - 9 <= j <= i]
    up = adx[i] is not None and adx[i] >= 20 and dr[i] > 0
    return (pat['st'] if pat else None, pat.get('gap') if pat else None, ks[-1] if ks else None, rs_raw(C[:i + 1]), up)


def group_stats(H, closes, tix, horizons=(3, 5, 10, 20)):
    """H = {날짜: {id: 묶음 글자}} 시계열 → 묶음별 편입 사건(전날 없던 묶음에 새로 들어온 날)의 이후 수익률·적중률·시장 기준 대비.
    closes[id] = 종가 목록, tix[id] = {날짜: 번호}. 시장 기준 = 같은 날짜들의 전 종목 평균."""
    dates = sorted(H)
    ev = {g: [] for g, _ in GROUPS}
    for p in range(1, len(dates)):
        cur, prev = H[dates[p]], H[dates[p - 1]]
        for id_, gs in cur.items():
            for g in gs:
                if g not in prev.get(id_, ''):
                    ev[g].append((id_, dates[p]))
    def fwd(id_, d, k):
        i = tix.get(id_, {}).get(d)
        C = closes.get(id_)
        return C[i + k] / C[i] - 1 if i is not None and C and i + k < len(C) and C[i] else None
    base = {}
    for k in horizons:
        v = [f for d in dates[1:] for id_ in closes if (f := fwd(id_, d, k)) is not None]
        base[k] = sum(v) / len(v) if v else None
    out = {}
    for g, _ in GROUPS:
        row = {'n': len(ev[g])}
        for k in horizons:
            v = [f for id_, d in ev[g] if (f := fwd(id_, d, k)) is not None]
            if v:
                avg = sum(v) / len(v)
                hit = sum(1 for x in v if (x < 0 if g == 'W' else x > 0)) / len(v)
                row[f'f{k}'] = [round(avg * 100, 2), round(hit * 100), len(v),
                                round((avg - base[k]) * 100, 2) if base[k] is not None else None]
        out[g] = row
    return {'g': out, 'base': {k: round(v * 100, 2) for k, v in base.items() if v is not None},
            'from': dates[0] if dates else None, 'days': len(dates)}
