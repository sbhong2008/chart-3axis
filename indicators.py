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

    # ---- 조짐 표시 (오닐 『공매도 투자 기법』: 처닝 → 분산일 → 대규모 분산) ----
    V = [b['volume'] for b in bars]
    vma = [None] * N
    for i in range(19, N):
        vma[i] = sum(V[i - 19:i + 1]) / 20
    # 분산일 = 종가가 전일보다 0.2%↑ 낮고 거래량이 전일보다 많은 날. 최근 20거래일(4주) 안, 그날 종가보다 5%↑ 오르면 소멸
    dday = [False] * N
    for i in range(1, N):
        dday[i] = V[i] > 0 and V[i - 1] > 0 and C[i] <= C[i - 1] * .998 and V[i] > V[i - 1]
    ddn = [0] * N
    for i in range(N):
        n, hi = 0, -1e300
        for j in range(i, max(-1, i - 20), -1):
            if dday[j] and hi < C[j] * 1.05:
                n += 1
            hi = max(hi, C[j])
        ddn[i] = n
    # 처닝(과도 거래) = 상승 추세 고점권(40일 전보다 +3%↑, 직전 40일 고가의 97%↑)에서 1~3일 연속 거래량 증가(마지막 날 평균 이상)
    #   인데 그 기간 가격 변화가 −1%~+0.5%(상승 미미·제자리)
    hi40 = [None] * N
    for i in range(40, N):
        hi40[i] = max(x['high'] for x in bars[i - 40:i])
    churn = [False] * N
    for i in range(41, N):
        if not (vma[i] and V[i] >= vma[i] and C[i - 40] < C[i] * .97 and bars[i]['high'] >= hi40[i] * .97):
            continue
        for k in (1, 2, 3):
            if all(V[j] > V[j - 1] for j in range(i - k + 1, i + 1)) and -.01 <= C[i] / C[i - k] - 1 <= .005:
                churn[i] = True
                break
    # 대규모 분산(B점) = 처닝 뒤 10일 안에 장중 신고가(직전 40일 고가 경신)인데 전일보다 낮은 종가 + 거래량 전일 초과·평균 1.2배↑
    bigd = [False] * N
    for i in range(41, N):
        if vma[i] and bars[i]['high'] > hi40[i] and C[i] < C[i - 1] and V[i] > V[i - 1] and V[i] >= vma[i] * 1.2 \
                and any(churn[j] for j in range(max(0, i - 10), i)):
            bigd[i] = True
    sr = [b.get('sr') for b in bars]   # 공매도 비중(%) — 있는 종목만
    last_dd = last_hot = last_sr = last_ch = last_bd = -99
    for i in range(20, N):
        if ddn[i] >= 5 and ddn[i - 1] < 5 and i - last_dd > 10:
            last_dd = i; sigs.append((i, '분산일5'))          # 4주 안 분산일 5회 → 보유 재평가·현금 확보(오닐)
        if (vr[i] or 0) >= 3 and up[i] is not None and C[i] > up[i] and C[i] >= C[i - 20] * 1.2 and i - last_hot > 10:
            last_hot = i; sigs.append((i, '과열'))            # 급등(20일 +20%↑) 뒤 평균 3배↑ 거래 + BB 상단 밖 = 매수 클라이맥스
        if churn[i] and i - last_ch > 10:
            last_ch = i; sigs.append((i, '처닝'))
        if bigd[i] and i - last_bd > 10:
            last_bd = i; sigs.append((i, '대분산'))
        if sr[i] is not None and sr[i] >= 3 and i - last_sr > 5:
            prev = [x for x in sr[i - 40:i] if x is not None]
            if len(prev) >= 20:
                m = sum(prev) / len(prev)
                sd = math.sqrt(sum((x - m) ** 2 for x in prev) / len(prev))
                if sr[i] >= m + 2 * sd and sr[i] >= m * 1.25:
                    # 공매도 비중이 40일 평균+2σ 이상·평균의 1.25배↑ (시장마다 수준이 달라 상대 기준: 미국 FINRA ≈45%, 국내 KRX ≈1~5%)
                    last_sr = i; sigs.append((i, '공매↑'))
    sigs.sort()

    return dict(mid=mid, up=up, lo=lo, bw=bw, sq=sq, pdi=pdi, mdi=mdi, adx=adx, vr=vr,
                score=score, brk=brk, dir=dr, sgn=sgn, sigs=sigs, dday=dday, ddn=ddn, churn=churn, bigd=bigd)


# 엘리엇 파동은 elliott.py(다층·프랙탈, 빌드에서 계산)로 옮김


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
        'fl': flags,
        'dd': r['ddn'][i],
        'sr': bars[i].get('sr'),
    }, r


BULL = {'★3↑', '2↑', '매집', '투매', '바닥돌파'}          # 바닥돌파·50일↓·반등실패·최후고점 = oneil.py(파이썬 전용, 데이터로 표시)
BEAR = {'경고', '분산', '꺾임', '분산일5', '과열', '공매↑', '처닝', '대분산', '50일↓', '반등실패', '최후고점'}


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
