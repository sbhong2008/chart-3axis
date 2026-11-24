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

    # ---- 조짐 표시: 분산일(오닐) · 처닝 · 과열 · 공매도 급증 ----
    # 분산일 = 종가 0.2%↑ 하락 + 거래량이 전일보다 많음. 최근 25거래일 안, 그날 종가보다 5%↑ 오르면 소멸
    V = [b['volume'] for b in bars]
    dday = [False] * N
    for i in range(1, N):
        dday[i] = V[i] > 0 and V[i - 1] > 0 and C[i] <= C[i - 1] * .998 and V[i] > V[i - 1]
    ddn = [0] * N
    for i in range(N):
        n, hi = 0, -1e300
        for j in range(i, max(-1, i - 25), -1):
            if dday[j] and hi < C[j] * 1.05:
                n += 1
            hi = max(hi, C[j])
        ddn[i] = n
    # 처닝(churning) = 상승 후 고점권(40일 고가 5% 이내, 40일 전보다 +3%↑)에서 거래량 평균 1.5배↑·전일 초과인데
    # 가격 진전 없음(전일 대비 ±0.5% 이내) + 장중 범위 아래쪽 절반 마감 → 대량 매물 소화(위장된 분산)
    churn = [False] * N
    for i in range(40, N):
        b = bars[i]
        rng = b['high'] - b['low']
        if (vr[i] or 0) >= 1.5 and V[i] > V[i - 1] and abs(C[i] / C[i - 1] - 1) <= .005 and rng > 0 \
                and (C[i] - b['low']) / rng < .5 and C[i - 40] < C[i] * .97 \
                and b['high'] >= max(x['high'] for x in bars[i - 40:i + 1]) * .95:
            churn[i] = True
    sr = [b.get('sr') for b in bars]   # 공매도 비중(%) — 있는 종목만
    last_dd = last_hot = last_sr = last_ch = -99
    for i in range(20, N):
        if ddn[i] >= 5 and ddn[i - 1] < 5 and i - last_dd > 10:
            last_dd = i; sigs.append((i, '분산일5'))          # 분산일 25일 내 5회 → 고점 경계(오닐)
        if (vr[i] or 0) >= 3 and up[i] is not None and C[i] > up[i] and C[i] >= C[i - 20] * 1.2 and i - last_hot > 10:
            last_hot = i; sigs.append((i, '과열'))            # 급등(20일 +20%↑) 뒤 평균 3배↑ 거래 + BB 상단 밖 = 매수 클라이맥스
        if churn[i] and i - last_ch > 10:
            last_ch = i; sigs.append((i, '처닝'))
        if sr[i] is not None and sr[i] >= 55 and i - last_sr > 5:
            prev = [x for x in sr[i - 40:i] if x is not None]
            if len(prev) >= 20:
                m = sum(prev) / len(prev)
                sd = math.sqrt(sum((x - m) ** 2 for x in prev) / len(prev))
                if sr[i] >= m + 2 * sd:
                    last_sr = i; sigs.append((i, '공매↑'))     # 공매도 비중이 40일 평균+2σ 이상·55%↑
    sigs.sort()

    waves = elliott(bars, score, brk, sgn, N)
    return dict(mid=mid, up=up, lo=lo, bw=bw, sq=sq, pdi=pdi, mdi=mdi, adx=adx, vr=vr,
                score=score, brk=brk, dir=dr, sgn=sgn, sigs=sigs, waves=waves, dday=dday, ddn=ddn, churn=churn)


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


SEQ = ['1파', '2파', '3파', '4파', '5파', 'A파', 'B파', 'C파']
TOPS = {'2파', '4파', 'A파', 'C파', 'Y파'}   # 고점에서 시작하는 파동(나머지는 저점에서 시작)


def elliott(bars, score, brk, sgn, N):
    """엘리엇 대응 파동 '시작점' 자동 추정 — 앞 라벨을 이어받아 1→2→3→4→5→A→B→C 순서와
    고점·저점 교대를 지킨다(JS waveLab 과 같은 규칙).
    엘리엇 3대 규칙: 2파 < 1파 시작 금지 · 3파 최단 금지 · 4파의 1파 영역 침범 금지.
    복합 조정: C파 뒤 반등(X)·재하락(Y) = W(A~C)-X-Y.
    앵커 = 응축·무추세 뒤 점수 2 이상 돌파(30일 간격). 앵커 사이 공백은 5% 지그재그 피벗으로 채움."""
    Z4, Z5 = zigzag(bars, .04), zigzag(bars, .05)
    H = lambda i: bars[i]['high']
    L = lambda i: bars[i]['low']
    lab = []

    def last(name):
        return next((i for i, n in reversed(lab) if n == name), None)

    def cut(i):
        lab[:] = [x for x in lab if x[0] < i]

    def top(a, b):   # a~b 구간 최고가 날(같으면 뒤쪽)
        return max(range(a, b + 1), key=lambda j: (H(j), j))

    def bottom(a, b):
        return min(range(a, b + 1), key=lambda j: (L(j), -j))

    def ok(name, i):  # 엘리엇 가격 규칙
        if name == '5파':  # 4파 끝이 1파 끝(=2파 시작) 아래로 겹치면 안 됨
            p1, p2 = last('1파'), last('2파')
            return p2 is None or p1 is None or p2 < p1 or L(i) > H(p2)
        if name == 'C파':  # B파 반등이 A파 시작 고점을 넘으면 C파 아님
            return H(i) < H(last('A파'))
        if name == '3파':  # 2파가 1파 시작 아래로 내려가면 안 됨
            return L(i) > L(last('1파'))
        return True

    def put_a(i):
        # 3파는 1·3·5파 중 가장 짧을 수 없음 → 위반이면 3·4·5를 하나의 연장 3파로 합치고 꼭지 = 4파 시작
        p1, p2, p3, p4, p5 = (last(x) for x in ('1파', '2파', '3파', '4파', '5파'))
        if None not in (p1, p2, p3, p4, p5) and p1 < p2 < p3 < p4 < p5:
            w1, w3, w5 = H(p2) - L(p1), H(p4) - L(p3), H(i) - L(p5)
            if w3 < w1 and w3 < w5:
                cut(p4)
                lab.append((i, '4파'))
                return
        lab.append((i, 'A파'))

    def recount(i):
        # 4파 눌림이 1파 영역을 침범 → 앞 3파·4파를 실제 1파·2파로 다시 세고, 저점 i = 3파 시작
        p3, i4 = last('3파'), lab[-1][0]
        if L(i) <= L(p3) or i - i4 < 3:
            return False
        p1, p2 = last('1파'), last('2파')
        cut(p1 if p1 is not None and p2 is not None and p1 < p2 < p3 else p3)
        lab.extend([(p3, '1파'), (i4, '2파'), (i, '3파')])
        return True

    def fill(upto):
        while lab and lab[-1][1] not in ('C파', 'Y파'):
            i0, n0 = lab[-1]
            nx = SEQ[SEQ.index(n0) + 1]
            p = next((p for p in Z5 if i0 + 4 < p[0] < upto), None)
            if not p or p[1] != ('H' if nx in TOPS else 'L'):
                break
            if not ok(nx, p[0]):
                if nx == '5파' and recount(p[0]):
                    continue
                break
            if nx == 'A파':
                put_a(p[0])
            else:
                lab.append((p[0], nx))

    last_s = -99
    for s in range(30, N):
        if score[s] is None or score[s] < 2 or not brk[s]:
            continue
        if not any(abs(sgn(j)) < 20 for j in range(s - 15, s)) or s - last_s < 30:
            continue
        last_s = s
        fill(s - 15)
        cur = lab[-1][1] if lab else None
        if brk[s] > 0:  # ---- 상승 앵커
            i3 = bottom(s - 15, s)
            if cur in ('1파', '2파', '3파', '4파', '5파') and lab[-1][0] >= i3:
                continue                                   # 같은 상승의 연장
            if cur == '5파':
                continue
            p3 = last('3파')
            if cur in ('3파', '4파') and min(L(j) for j in range(p3, s + 1)) >= L(p3):
                i4 = lab[-1][0] if cur == '4파' else (top(p3 + 1, i3 - 1) if i3 - 1 > p3 else None)
                if i4 is not None and i3 - i4 >= 3 and ok('5파', i3):
                    cut(p3 + 1)
                    lab += [(i4, '4파'), (i3, '5파')]     # 3파 뒤 눌림(4파) → 재돌파 = 5파 시작
                    continue
            if cur == '1파' and L(i3) > L(lab[-1][0]) and i3 - lab[-1][0] >= 6:
                lab += [(top(lab[-1][0] + 1, i3 - 1), '2파'), (i3, '3파')]   # 1파 뒤 눌림 → 3파
                continue
            if cur == '2파' and L(i3) > L(last('1파')) and i3 - lab[-1][0] >= 3:
                lab.append((i3, '3파'))                     # 2파 조정이 1파 시작 위에서 끝남 → 3파
                continue
            if cur == '4파' and recount(i3):
                continue
            # 새 상승 파동: 1·2파 = 3파 직전 4% 피벗(조건 맞을 때)
            h2 = max((p for p in Z4 if p[1] == 'H' and p[0] < i3), key=lambda p: p[0], default=None)
            l1 = max((p for p in Z4 if p[1] == 'L' and h2 and p[0] < h2[0]), key=lambda p: p[0], default=None)
            if h2 and l1 and L(l1[0]) < L(i3) and i3 - l1[0] <= 60:
                pts = [(l1[0], '1파'), (h2[0], '2파'), (i3, '3파')]
            else:
                pts = [(i3, '1파' if cur in ('A파', 'B파', 'C파', 'Y파') else '3파')]
            first = pts[0][0]
            cut(first)
            if lab and lab[-1][1] == 'B파':               # B 저점 뒤 새 상승 → 사이 고점 = C파 시작
                c = top(lab[-1][0] + 1, first - 1) if first - 1 > lab[-1][0] else None
                if c is not None and ok('C파', c) and first - c >= 2 and c - lab[-1][0] >= 3:
                    lab.append((c, 'C파'))
                else:
                    lab.pop()
            while lab and (lab[-1][1] in ('1파', '2파', '3파', '4파') or lab[-1][1] not in TOPS):
                lab.pop()                                  # 실패한 상승 시도(시작점 아래로 되밀림)는 라벨 제거, 교대 유지
            if lab and lab[-1][1] == 'A파':                # A파 뒤 바로 새 상승 → 사이 4% 피벗으로 B·C 보충
                pa = lab[-1][0]
                b_ = next((p[0] for p in Z4 if p[1] == 'L' and pa + 2 < p[0] < first - 3), None)
                c = next((p[0] for p in Z4 if b_ is not None and p[1] == 'H' and b_ + 2 < p[0] < first - 2), None)
                if c is not None and ok('C파', c):
                    lab += [(b_, 'B파'), (c, 'C파')]
            lab += pts
        else:  # ---- 하락 앵커
            if cur in ('1파', '3파', '4파', '5파'):
                st = lab[-1][0]
                T = top(st, s)
                if T == st:
                    continue
                if cur == '1파':
                    lab.append((T, '2파'))                    # 1파 상승 뒤 하락 = 2파 조정 시작
                    continue
                if cur == '3파':                               # 꼭지 전 가장 깊은 눌림(3%↑)을 4·5파로
                    best = None
                    for a in range(st + 3, T - 3):
                        b_ = bottom(a + 1, T - 2)
                        dd = 1 - L(b_) / H(a)
                        if dd >= .03 and H(a) > H(st) and ok('5파', b_) and (best is None or dd > best[0]):
                            best = (dd, a, b_)
                    if not best:
                        lab.append((T, '4파'))                 # 눌림 없이 꼭지 → 4파 조정 시작
                        continue
                    lab += [(best[1], '4파'), (best[2], '5파')]
                elif cur == '4파':
                    b_ = bottom(st + 1, T - 1) if T - 1 > st else None
                    if b_ is None or not ok('5파', b_):
                        continue
                    lab.append((b_, '5파'))
                put_a(T)                                       # 상승 5파 뒤 꼭지 = A파 시작(3파 최단이면 4파)
            elif cur == '2파':
                p1 = last('1파')
                if min(L(j) for j in range(lab[-1][0], s + 1)) >= L(p1):
                    continue                                   # 2파 조정 진행 중
                cut(p1)                                        # 1파 시작 아래로 → 상승 실패, 앞 조정으로 복귀
                if not lab:
                    lab.append((top(max(0, s - 60), s), 'A파'))
                elif lab[-1][1] not in TOPS:
                    nx = SEQ[SEQ.index(lab[-1][1]) + 1]
                    T = top(lab[-1][0] + 1, s)
                    if ok(nx, T):
                        lab.append((T, nx))
            elif cur in ('A파', 'B파'):
                pa = last('A파')
                T = top(pa, s)
                if T == pa:
                    continue
                if H(T) >= H(pa):
                    cut(pa)
                    lab.append((T, 'A파'))                     # A파 시작 고점 갱신 → 꼭지 이동
                else:
                    b_ = bottom(pa + 1, T - 1) if T - 1 > pa else None
                    if b_ is None or T - b_ < 3 or b_ - pa < 3:
                        continue
                    cut(pa + 1)
                    lab += [(b_, 'B파'), (T, 'C파')]
            elif cur == 'X파':
                continue
            else:                                              # 앞 라벨 없음 또는 C·Y파 진행 중
                k = max((p[0] for p in Z4 if p[1] == 'H' and p[0] <= s), default=None)
                if k is None or (lab and k <= lab[-1][0]):
                    continue
                if cur in ('C파', 'Y파'):
                    pc = lab[-1][0]
                    if H(k) < H(pc):
                        pa, pb = last('A파'), last('B파')
                        if cur == 'C파' and k - pc > 6 and pa is not None and pb is not None:
                            x = bottom(pc + 1, k - 1)
                            # 복합 조정: C파가 A파 길이의 61.8%↑ 진행 → 4%↑ 반등(X) → 다시 하락 이탈 = Y파
                            if H(pc) - L(x) >= .618 * (H(pa) - L(pb)) and H(k) >= L(x) * 1.04 and k - x >= 3 and x - pc >= 3:
                                lab += [(x, 'X파'), (k, 'Y파')]
                        continue                               # 그 밖에는 C(Y)파 하락 안의 반등
                    lab += [(bottom(pc + 1, k - 1), '1파'), (k, '2파')] if k - 1 > pc else []
                    continue
                lab.append((k, 'A파'))
    fill(N)
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
        'dd': r['ddn'][i],
        'sr': bars[i].get('sr'),
    }, r


BULL = {'★3↑', '2↑', '매집', '투매'}
BEAR = {'경고', '분산', '꺾임', '분산일5', '과열', '공매↑', '처닝'}


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
