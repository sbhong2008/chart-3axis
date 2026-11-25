"""엘리엇 파동 다층(프랙탈) 엔진 — 파이썬에서만 계산하고 결과를 종목 데이터(ew)로 내보냄.

원칙(R.N. 엘리엇 『파동 이론』, 프로스트·프렉터 정리):
- 상승(충격) 파동 1개 = 하위 등급 5개(1-2-3-4-5), 조정 파동 1개 = 하위 등급 3개(A-B-C; 삼각형은 5개).
- 3대 규칙: 2파는 1파 시작을 넘어 되돌리지 않음 · 3파는 1·3·5파 중 가장 짧지 않음 · 4파는 1파 영역에 들어가지 않음.
- 등급: 작은 꺾임(지그재그) → 마이뉴트 → 마이너 → 인터미디에이트(일봉 2년),
        주봉 10년 → 프라이머리 → 사이클.
- 매 빌드마다 처음부터 다시 셈(현재 시점 재계산). 마지막 파동은 '진행 중'.

방법: 등급 k 의 꺾임(피벗)은 등급 k-1 꺾임 중에서 고른다(포함 관계가 보장됨).
등급 k 의 한 파동이 하위 파동 몇 개(m, 홀수)를 묶는지와 가격 규칙으로 점수를 매기고,
1→2→3→4→5→A→B→C 순서(방향 d = 1파 방향)를 지키는 해석 중 점수가 가장 높은 것을 빔 탐색으로 고른다.
"""
import statistics

POS = ['1', '2', '3', '4', '5', 'A', 'B', 'C']
# 등급별 표기(책의 등급표 기준, 원 로마 숫자는 글꼴이 없어 괄호로 대신)
DEG = {
    '마이뉴트': (['1', '2', '3', '4', '5'], ['a', 'b', 'c', 'd', 'e', 'x']),
    '마이너': (['I', 'II', 'III', 'IV', 'V'], ['A', 'B', 'C', 'D', 'E', 'X']),
    '인터미디에이트': (['(I)', '(II)', '(III)', '(IV)', '(V)'], ['(A)', '(B)', '(C)', '(D)', '(E)', '(X)']),
    '프라이머리': (['①', '②', '③', '④', '⑤'], ['Ⓐ', 'Ⓑ', 'Ⓒ', 'Ⓓ', 'Ⓔ', 'Ⓧ']),
    '사이클': (['cI', 'cII', 'cIII', 'cIV', 'cV'], ['cA', 'cB', 'cC', 'cD', 'cE', 'cX']),
}
DAILY_DEG = ['마이뉴트', '마이너', '인터미디에이트']
WEEKLY_DEG = ['프라이머리', '사이클']


def sym(deg, key):
    """key: '1'~'5' 충격, 'A'~'E'·'X' 조정 → 등급별 표기"""
    imp, cor = DEG[deg]
    return imp[int(key) - 1] if key.isdigit() else cor['ABCDEX'.index(key)]


# ---------- 지그재그 (마지막 진행 중 극점은 '미확정' 피벗으로 붙임) ----------
def zigzag(H, L, th):
    n = len(H)
    if n < 3:
        return []
    P, dn, ei = [], 0, 0
    for i in range(1, n):
        if dn >= 0:
            if H[i] >= H[ei]:
                dn = dn or 1
                ei = i
            elif L[i] <= H[ei] * (1 - th):
                P.append((ei, 'H', H[ei])); dn = -1; ei = i
        else:
            if L[i] <= L[ei]:
                ei = i
            elif H[i] >= L[ei] * (1 + th):
                P.append((ei, 'L', L[ei])); dn = 1; ei = i
    # 첫 피벗 앞의 시작점: 반대쪽 극점
    if P:
        f = P[0]
        if f[1] == 'H':
            j = min(range(0, f[0] + 1), key=lambda k: L[k]); P.insert(0, (j, 'L', L[j]))
        else:
            j = max(range(0, f[0] + 1), key=lambda k: H[k]); P.insert(0, (j, 'H', H[j]))
        lt = 'L' if P[-1][1] == 'H' else 'H'
        if ei > P[-1][0]:
            P.append((ei, lt, L[ei] if lt == 'L' else H[ei]))   # 미확정(진행 중) 극점
    return P


def auto_th(H, L, C, k, lo, hi):
    r = [(h - l) / c for h, l, c in zip(H[-250:], L[-250:], C[-250:]) if c]
    return max(lo, min(hi, k * statistics.median(r))) if r else lo


# ---------- 한 등급 세기 ----------
# 하위 파동 수(m)별 점수: 충격(1·3·5·C)=5개(연장 9개), A=5 또는 3(플랫), 조정(2·4·B)=3개(삼각형 5·복합 7).
# m=1(하위 구조 없음)은 감점 → 상위 등급은 하위 파동을 묶어서 만들어짐
SUB_MOT = {5: 3.0, 9: 2.5, 7: 0.5, 3: -1.5, 1: -3.0, 11: 0.5}
SUB_A = {5: 3.0, 3: 2.5, 7: 1.0, 9: 1.0, 1: -3.0, 11: 0.5}
SUB_COR = {3: 3.0, 5: 2.0, 7: 2.0, 1: -2.5, 9: 0.5, 11: 0.5}
K_BEAM = 3


def count_level(P):
    """P: 교대 피벗 [(i, 'H'|'L', 가격)]. 반환: 다리 목록 [(시작피벗, 끝피벗, pos, d)] (마지막 다리 = 진행 중)."""
    n = len(P)
    if n < 4:
        return []
    v = [p[2] for p in P]
    up = [p[1] == 'L' for p in P]   # 이 피벗에서 시작하는 다리가 상승인가

    def ext(j, k, sg):   # 피벗 j~k 중 sg 방향 극값(+1 = 최고 고점, -1 = 최저 저점)
        xs = [v[x] for x in range(j, k + 1) if P[x][1] == ('H' if sg > 0 else 'L')]
        return (max(xs) if sg > 0 else min(xs)) if xs else v[j]

    def valid(j, k, pos, d, final):
        """다리 j→k 가 pos 파동이 될 수 있는가. 충격(1·3·5·C): 시작이 구간 극점이고 끝도 극점(진행 중이면 시작만).
        조정(2·4·A·B): 끝이 시작보다 다리 방향으로 진행(플랫·불규칙형 허용, 진행 중이면 조건 없음)."""
        ld = leg_dir(pos, d)
        if pos in (0, 2, 4, 7):
            if ld * (ext(j, k, -ld) - v[j]) < 0:
                return False
            return final or ld * (v[k] - ext(j, k, ld)) >= 0
        return final or ld * (v[k] - v[j]) > 0

    def leg_dir(pos, d):
        return d if pos % 2 == 0 else -d

    def check(pos, d, b, final):
        """b: 이번 사이클 경계 피벗 [b0..b8] (없으면 None). pos 다리를 막 끝냈을 때 가격 규칙. 반환: 점수 가감 또는 None(위반)."""
        g = lambda x: v[b[x]] if b[x] is not None else None
        s = 0.0
        if pos == 1 and g(0) is not None and d * (ext(b[1], b[2], -d) - g(0)) <= 0:
            return None                                      # 2파(가장 깊은 곳)가 1파 시작을 넘음
        if pos == 2 and g(1) is not None and not final and d * (g(3) - g(1)) <= 0:
            return None                                      # 3파가 1파 끝을 못 넘음
        if pos == 3 and g(1) is not None and d * (ext(b[3], b[4], -d) - g(1)) <= 0:
            return None                                      # 4파가 1파 영역 침범
        if pos == 4 and all(b[x] is not None for x in range(6)):
            w1, w3, w5 = abs(g(1) - g(0)), abs(g(3) - g(2)), abs(g(5) - g(4))
            if w3 < w1 and w3 < w5:
                return None                                  # 3파 최단
            if not final and d * (g(5) - g(3)) <= 0:
                s -= 1.5                                     # 5파 미달(절단)
            if w3 >= w1:
                s += 0.5
        if pos == 6 and g(5) is not None and abs(ext(b[6], b[7], d) - g(6)) > 1.38 * abs(g(6) - g(5)):
            return None                                      # B파가 A파 시작을 크게 넘음
        if pos == 7 and g(6) is not None and not final:
            s += 0.5 if d * (g(8) - g(6)) < 0 else -1.0      # C파가 A파 끝을 넘는가
        return s

    def inner_impulse(j):   # 하위 5개(j~j+5)가 충격파 3대 규칙을 지키는가
        p = v[j:j + 6]
        ld = 1 if p[5] > p[0] else -1
        w1, w3, w5 = abs(p[1] - p[0]), abs(p[3] - p[2]), abs(p[5] - p[4])
        return ld * (p[2] - p[0]) > 0 and ld * (p[3] - p[1]) > 0 and ld * (p[4] - p[1]) > 0 and not (w3 < w1 and w3 < w5)

    def inner_triangle(j):  # 하위 5개가 수렴 삼각형(a~e)인가
        p = v[j:j + 6]
        L_ = [abs(p[x + 1] - p[x]) for x in range(5)]
        return L_[2] < L_[0] and L_[3] < L_[1] and L_[4] < L_[2]

    def sub(pos, m, first, final, j):
        motive = pos in (0, 2, 4, 7) or (pos == 5 and m == 5)
        if first or final:
            return max((SUB_A if pos == 5 else SUB_MOT if motive else SUB_COR).get(m, 0.5), 0.0)
        if motive and m == 5:
            return 3.0 if inner_impulse(j) else 1.0         # 하위 5개가 규칙을 어기면 충격파로 보기 약함
        if not motive and m == 5:
            return 2.0 if inner_triangle(j) else 0.5         # 조정 안의 5개 = 삼각형일 때만
        if not motive and m == 3:
            return 3.0 if abs(v[j + 2] - v[j + 1]) <= 1.38 * abs(v[j + 1] - v[j]) else 1.0   # 지그재그·플랫(B ≤ A의 138%)
        t = SUB_A if pos == 5 else SUB_MOT if motive else SUB_COR
        return t.get(m, 0.5)

    # 노드: (점수, j, pos, d, b(튜플 9), 이전노드)
    beam = {}

    def push(key, node):
        lst = beam.setdefault(key, [])
        lst.append(node)
        lst.sort(key=lambda x: -x[0])
        del lst[K_BEAM:]

    for m in (1, 3, 5, 7, 9, 11):
        k = m
        if k >= n:
            continue
        for d in (1, -1):
            for pos in range(8):
                if leg_dir(pos, d) != (1 if up[0] else -1) or not valid(0, k, pos, d, k == n - 1):
                    continue
                b = [None] * 9
                b[pos], b[pos + 1] = 0, k
                sc = check(pos, d, b, k == n - 1)
                if sc is None:
                    continue
                push((k, pos, d), (sub(pos, m, True, k == n - 1, 0) + sc, k, pos, d, tuple(b), None))
    for j in range(1, n):
        for key in [x for x in beam if x[0] == j]:
            for node in beam[key]:
                score, _, pos, d, b, _ = node
                nxt = [(pos + 1, d, 0.0)] if pos < 7 else [(0, d, 0.0)]
                if pos == 4:
                    nxt.append((0, -d, -1.0))                # 5파 뒤 상위 등급 전환(반대 방향 새 충격파)
                for m in (1, 3, 5, 7, 9, 11):
                    k = j + m
                    if k >= n:
                        break
                    final = k == n - 1
                    for np_, nd, pen in nxt:
                        if leg_dir(np_, nd) != (1 if up[j] else -1) or not valid(j, k, np_, nd, final):
                            continue
                        nb = list(b) if np_ > 0 else [None] * 9
                        nb[np_], nb[np_ + 1] = j, k
                        sc = check(np_, nd, nb, final)
                        if sc is None:
                            continue
                        push((k, np_, nd), (score + sub(np_, m, False, final, j) + sc + pen, k, np_, nd, tuple(nb), node))
    ends = [nd for key, lst in beam.items() if key[0] == n - 1 for nd in lst]
    if not ends:
        return []
    best = max(ends, key=lambda x: x[0])
    legs = []
    node = best
    while node:
        _, k, pos, d, b, prev = node
        legs.append((b[pos], k, pos, d))
        node = prev
    return legs[::-1]


def relabel(parent, child):
    """상위 파동의 종류에 맞춰 그 안의 하위 파동 라벨을 다시 붙임(프랙탈 원칙).
    충격(1·3·5·C, 5개짜리 A) 안 = 1~5, 조정 안 = A·B·C(5개면 삼각형 A~E, 7개면 A·B·C·X·A·B·C)."""
    for P in parent:
        kids = [c for c in child if c['s'] >= P['s'] and c['e'] <= P['e']]
        if not kids:
            continue
        motive = P['k'] in '135C' or (P['k'] == 'A' and P['m'] == 5)
        n = len(kids)
        if n == 1:
            keys = P['k']                                    # 하위 등급에서 더 쪼개지지 않음 → 같은 파동
        elif motive and (n == 5 or (P['live'] and n < 5)):
            keys = '12345'[:n]
        elif not motive and (n == 3 or (P['live'] and n < 3)):
            keys = 'ABC'[:n]
        elif not motive and n == 5:
            keys = 'ABCDE'
        elif not motive and n == 7:
            keys = 'ABCXABC'
        else:
            continue                                         # 하위 구조가 원칙과 다르면(연장 등) 하위 등급 자체 해석 유지
        for c, k in zip(kids, keys):
            c['k'] = k


def count_all(H, L, C, th, degs):
    """여러 등급을 아래에서 위로 세고(꺾임 묶기), 라벨은 위에서 아래로 다시 붙임.
    반환: {등급: [{'s','e' 봉 번호, 'k' 라벨키, 'up' 상승 다리, 'm' 하위 수, 'live' 진행 중}]}"""
    P = zigzag(H, L, th)
    out = {}
    for deg in degs:
        legs = count_level(P)
        if len(legs) < 3:
            break
        out[deg] = [{'s': P[a][0], 'e': P[k][0], 'k': POS[pos], 'up': P[a][1] == 'L',
                     'm': k - a, 'live': k == len(P) - 1} for a, k, pos, d in legs]
        P = [P[legs[0][0]]] + [P[k] for _, k, _, _ in legs]   # 상위 등급 후보 피벗 = 이번 등급 경계
    names = list(out)
    for hi, lo in zip(names[::-1], names[::-1][1:]):
        relabel(out[hi], out[lo])
    return out


def weekly(bars):
    """일봉 → 주봉(고가·저가 날짜 보존)."""
    import datetime as dt
    W = []
    for b in bars:
        y, w, _ = dt.date.fromisoformat(b['time']).isocalendar()
        if not W or W[-1]['k'] != (y, w):
            W.append({'k': (y, w), 'high': b['high'], 'low': b['low'], 'close': b['close'], 'hd': b['time'], 'ld': b['time']})
        else:
            x = W[-1]
            if b['high'] >= x['high']:
                x['high'], x['hd'] = b['high'], b['time']
            if b['low'] <= x['low']:
                x['low'], x['ld'] = b['low'], b['time']
            x['close'] = b['close']
    return W


def analyze(daily, long_daily=None):
    """daily: 화면용 일봉(2년), long_daily: 주봉 계산용 장기 일봉(10년, 없으면 daily).
    반환 ew = {'lv': [[등급, [[끝날짜, 표기, 진행중(0/1), 시작날짜, 고점끝(1)/저점끝(0)]...]]...],
              'cur': [[등급, 표기, 시작날짜]...]} (큰 등급 먼저)."""
    res = []
    if daily and len(daily) >= 60:
        H, L, C = [b['high'] for b in daily], [b['low'] for b in daily], [b['close'] for b in daily]
        th = auto_th(H, L, C, 1.5, .02, .08)
        for deg, legs in count_all(H, L, C, th, DAILY_DEG).items():
            res.append((deg, [(daily[x['e']]['time'], sym(deg, x['k']), int(x['live']), daily[x['s']]['time'], int(x['up'])) for x in legs]))
    W = weekly(long_daily or daily)
    if len(W) >= 100:
        H, L, C = [w['high'] for w in W], [w['low'] for w in W], [w['close'] for w in W]
        th = auto_th(H, L, C, 2.0, .06, .30)
        for deg, legs in count_all(H, L, C, th, ['_w0'] + WEEKLY_DEG).items():
            if deg == '_w0':
                continue                                     # 주봉 첫 등급은 일봉 등급과 겹쳐 생략
            res.append((deg, [(W[x['e']]['hd' if x['up'] else 'ld'], sym(deg, x['k']), int(x['live']),
                               W[x['s']]['ld' if x['up'] else 'hd'], int(x['up'])) for x in legs]))
    order = ['사이클', '프라이머리', '인터미디에이트', '마이너', '마이뉴트']
    res.sort(key=lambda x: order.index(x[0]))
    cur = [[deg, legs[-1][1], legs[-1][3]] for deg, legs in res if legs and legs[-1][2]]
    return {'lv': [[deg, [list(x) for x in legs]] for deg, legs in res], 'cur': cur}
