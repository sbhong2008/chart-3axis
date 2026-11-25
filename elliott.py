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
import math
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
WK_TH = (1.5, .06, .30)       # 주봉 지그재그 문턱 = 최근 1년 주봉 변동폭 중앙값 × k (하한·상한)
WK_KS = (1.5, 2.0, 2.5)        # 합의안을 고를 주봉 문턱 배수들
WEEK_DEG0 = '인터미디에이트'   # 장기 자료가 있으면 인터미디에이트는 주봉 첫 등급(프라이머리·사이클과 한 줄기)


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
    if P and P[0][0] > 0:
        f = P[0]
        if f[1] == 'H':
            j = min(range(0, f[0]), key=lambda k: L[k]); P.insert(0, (j, 'L', L[j]))
        else:
            j = max(range(0, f[0]), key=lambda k: H[k]); P.insert(0, (j, 'H', H[j]))
    if P:
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
TREND_W = 0.25       # 추세 파동(1·3·5) 크기 가점·조정 파동 크기 감점
OVER_MAX, OVER_W = 0.38, 8.0   # 조정이 시작점을 넘는 폭(확장 플랫) 상한·감점
DEV_MAX, DEV_W = 0.6, 4.0      # 조정 끝이 구간 극점에서 떨어진 정도 상한·감점
LIVE_W = 4.0                   # 진행 중 파동이 이미 반대 꼭지를 넘었을 때 감점
B_MAX, B_HARD, B_W = 1.38, 1.618, 20.0   # 조정 안 B파: A의 138.2%부터 감점, 161.8% 초과 불가
BAR_START = False
WK_BAR = False                 # 주봉 등급: 충격 극점을 실제 봉으로 확인
RESTART = 6.0                  # 규칙상 이어갈 수 없을 때 새로 세기 감점


def count_level(P, rmq, restart=False, cut=(), bar=False):
    """P: 교대 피벗 [(i, 'H'|'L', 가격)]. 반환: 다리 목록 [(시작피벗, 끝피벗, pos, d)] (마지막 다리 = 진행 중)."""
    n = len(P)
    if n < 4:
        return []
    v = [math.log(p[2]) for p in P]                          # 로그 가격(장기 차트 비율 비교)
    unit = statistics.median(abs(v[i + 1] - v[i]) for i in range(n - 1)) or 1e-9
    up = [p[1] == 'L' for p in P]   # 이 피벗에서 시작하는 다리가 상승인가

    def ext(j, k, sg, bar=False):
        """피벗 j~k 구간 sg 방향 극값(+1 최고, -1 최저). 기본 = 이 등급 피벗(하위 파동 경계) 중, bar=True = 실제 봉 전체"""
        if bar:
            return math.log(rmq(P[j][0], P[k][0], sg))
        xs = [v[x] for x in range(j, k + 1) if P[x][1] == ('H' if sg > 0 else 'L')]
        return (max(xs) if sg > 0 else min(xs)) if xs else v[j]

    def valid(j, k, pos, d, final):
        """다리 j→k 가 pos 파동이 될 수 있는가 → None(불가) 또는 감점(0 이하).
        충격(1·3·5·C)·A: 시작 = 구간 반대 극점, 끝 = 구간 극점(하위 파동 경계 기준, 진행 중이면 시작만).
        조정(2·4·B): 시작을 넘는 폭(확장 플랫)·끝이 극점에서 먼 정도(삼각형 제외)만큼 감점."""
        if cut and any(j < c < k for c in cut):
            return None                                      # 상위 등급 경계를 가로지르는 다리 불가(프랙탈: 상위 경계 = 하위 경계)
        ld = leg_dir(pos, d)
        if pos in (0, 2, 4, 5, 7):
            if ld * (ext(j, k, -ld, bar or BAR_START) - v[j]) < 0:
                return None                                  # 충격 시작 = 구간 반대 극점(BAR_START면 실제 봉 기준)
            if ld * (v[k] - ext(j, k, ld, bar)) >= 0:
                return 0.0
            if not final:
                return None
            # 진행 중 충격이 이미 더 높은(낮은) 꼭지를 지나 되밀림 = 꼭지에서 끝났을 가능성이 큼 → 감점
            size = abs(ext(j, k, ld, bar) - v[j]) or 1e-9
            return -(LIVE_W + 8.0 * ld * (ext(j, k, ld, bar) - v[k]) / size)
        size = abs(ext(j, k, ld, True) - v[j]) or 1e-9
        over = max(0.0, ld * (v[j] - ext(j, k, -ld, True))) / size
        if over > OVER_MAX:
            return None
        pen = -OVER_W * over
        if final:
            return pen - (LIVE_W + 8.0 * over if over > 0 else 0.0)   # 진행 중 조정이 이미 시작점을 넘었으면 = 새 극점(앞 파동 연장)일 가능성이 큼
        if ld * (v[k] - v[j]) <= 0:
            return None
        dev = ld * (ext(j, k, ld, True) - v[k]) / size
        if k - j == 5 and dev > 0.25 and inner_triangle(j):
            return pen                                       # 수렴 삼각형은 끝이 극점에서 멀어도 됨
        if dev > DEV_MAX:
            return None                                      # 지그재그·플랫은 끝이 구간 극점 근처
        return pen - DEV_W * dev

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
        if pos == 6 and g(5) is not None:
            ba = abs(ext(b[6], b[7], d) - g(6)) / (abs(g(6) - g(5)) or 1e-9)
            if ba > B_HARD:
                return None                                  # B파가 A파의 161.8% 초과
            s -= B_W * max(0.0, ba - B_MAX)                  # 138.2% 넘은 만큼 감점(확장 플랫)
        if pos == 7 and g(6) is not None and not final:
            s += 0.5 if d * (g(8) - g(6)) < 0 else -1.0      # C파가 A파 끝을 넘는가
            if g(5) is not None and abs(g(8) - g(7)) < 0.618 * abs(g(6) - g(5)):
                s -= 1.5                                     # C파가 A파의 61.8%도 안 됨
        # 추세 파동(1·3·5)은 조정 파동(2·4·A·C)보다 크다: 크기 비례 가감
        r = min(abs(g(pos + 1) - g(pos)) / unit, 4.0)
        if pos in (0, 2, 4):
            s += TREND_W * r
        elif pos in (1, 3, 5, 7):
            s -= TREND_W * r
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
            ba = abs(v[j + 2] - v[j + 1]) / (abs(v[j + 1] - v[j]) or 1e-9)
            if ba > B_HARD:
                return None                                  # B가 A의 161.8% 초과 = 플랫 아님(추세 계속)
            return 3.0 - B_W * max(0.0, ba - B_MAX)          # 138.2% 넘으면 넘은 만큼 감점
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
                pv = valid(0, k, pos, d, k == n - 1) if leg_dir(pos, d) == (1 if up[0] else -1) else None
                if pv is None:
                    continue
                b = [None] * 9
                b[pos], b[pos + 1] = 0, k
                sc = check(pos, d, b, k == n - 1)
                if sc is None:
                    continue
                sb = sub(pos, m, True, k == n - 1, 0)
                if sb is None:
                    continue
                push((k, pos, d), (sb + sc + pv, k, pos, d, tuple(b), None))
    for j in range(1, n):
        for key in [x for x in beam if x[0] == j]:
            for node in beam[key]:
                score, _, pos, d, b, _ = node
                nxt = [(pos + 1, d, 0.0)] if pos < 7 else [(0, d, 0.0)]
                if pos == 4:
                    nxt.append((0, -d, -1.0))                # 5파 뒤 상위 등급 전환(반대 방향 새 충격파)
                for rp, rd in ((0, d), (0, -d), (5, d), (5, -d)) if restart else ():  # 규칙대로 끝까지 못 갈 때만: 여기서 새로 세기(감점)
                    if not any(x[0] == rp and x[1] == rd for x in nxt):
                        nxt.append((rp, rd, -RESTART))
                for m in (1, 3, 5, 7, 9, 11):
                    k = j + m
                    if k >= n:
                        break
                    final = k == n - 1
                    for np_, nd, pen in nxt:
                        pv = valid(j, k, np_, nd, final) if leg_dir(np_, nd) == (1 if up[j] else -1) else None
                        if pv is None:
                            continue
                        nb = list(b) if np_ > 0 else [None] * 9
                        nb[np_], nb[np_ + 1] = j, k
                        sc = check(np_, nd, nb, final)
                        if sc is None:
                            continue
                        sb = sub(np_, m, False, final, j)
                        if sb is None:
                            continue
                        push((k, np_, nd), (score + sb + sc + pen + pv, k, np_, nd, tuple(nb), node))
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


def tri(kids):
    """하위 5개 다리가 수렴 삼각형(각 다리가 2개 앞 다리보다 짧음)인가 — 다리 크기는 봉 번호가 아니라 'sz'(로그 크기)"""
    z = [c.get('sz', 0) for c in kids]
    return all(z[i] < z[i - 2] for i in range(2, 5))


def imp_ok(kids):
    """하위 5개가 충격파 3대 규칙(2파 < 1파 시작, 3파 최단 아님, 4파 1파 영역 밖)을 지키는가"""
    p = [kids[0]['pa']] + [c['pb'] for c in kids]
    d = 1 if p[5] > p[0] else -1
    w = [abs(p[i + 1] - p[i]) for i in range(5)]
    return d * (p[2] - p[0]) > 0 and d * (p[4] - p[1]) > 0 and not (w[2] < w[0] and w[2] < w[4])


def relabel(parent, child):
    """상위 파동의 종류에 맞춰 그 안의 하위 파동 라벨을 다시 붙임(프랙탈 원칙).
    충격(1·3·5·C, 5개짜리 A) 안 = 1~5, 조정 안 = A·B·C(5개면 삼각형 A~E, 7개면 A·B·C·X·A·B·C)."""
    for P in parent:
        kids = [c for c in child if c['s'] >= P['s'] and c['e'] <= P['e']]
        if not kids:
            continue
        motive = P['k'] in '135C' or (P['k'] == 'A' and P['m'] == 5)
        n = len(kids)
        if n == 1 and P['live']:
            keys = '1' if motive else 'A'                    # 막 시작한 상위 파동의 첫 하위 파동
        elif n == 1:
            keys = P['k']                                    # 하위 등급에서 더 쪼개지지 않음 → 같은 파동
        elif motive and ((n == 5 and imp_ok(kids)) or (P['live'] and n < 5)):
            keys = '12345'[:n]
        elif not motive and (n == 3 or (P['live'] and n < 3)):
            keys = 'ABC'[:n]
        elif not motive and n == 5 and tri(kids):
            keys = 'ABCDE'
        elif not motive and n == 7:
            keys = 'ABCXABC'
        else:
            continue                                         # 하위 구조가 원칙과 다르면(연장 등) 하위 등급 자체 해석 유지
        for c, k in zip(kids, keys):
            c['k'] = k


def range_ext(H, L):
    """봉 구간 [a, b] 최고 고가(sg=+1)·최저 저가(sg=-1)를 O(1)로 답하는 표(희소 표)."""
    tabs = {1: [list(H)], -1: [list(L)]}
    for sg, f in ((1, max), (-1, min)):
        t = tabs[sg]
        w = 1
        while 2 * w <= len(H):
            p = t[-1]
            t.append([f(p[i], p[i + w]) for i in range(len(p) - w)])
            w *= 2

    def q(a, b, sg):
        if a > b:
            a, b = b, a
        t = tabs[sg]
        r = (b - a + 1).bit_length() - 1
        f = max if sg > 0 else min
        return f(t[r][a], t[r][b - (1 << r) + 1])
    return q


def count_all(H, L, C, th, degs, must=(), bar=False):
    """여러 등급을 아래에서 위로 세고(꺾임 묶기), 라벨은 위에서 아래로 다시 붙임.
    반환: {등급: [{'s','e' 봉 번호, 'k' 라벨키, 'up' 상승 다리, 'm' 하위 수, 'live' 진행 중}]}"""
    P = zigzag(H, L, th)
    rmq = range_ext(H, L)
    cutb = set()                                             # 상위(주봉) 경계 봉 → 가장 가까운 지그재그 피벗(3봉 이내)
    for b in must:
        near = min(P, key=lambda p: abs(p[0] - b), default=None)
        if near and abs(near[0] - b) <= 3:
            cutb.add(near[0])
    out = {}
    for deg in degs:
        cut = [i for i, p in enumerate(P) if p[0] in cutb]
        legs = count_level(P, rmq, cut=cut, bar=bar) or count_level(P, rmq, True, cut, bar)
        if len(legs) < 2:
            break
        out[deg] = [{'s': P[a][0], 'e': P[k][0], 'k': POS[pos], 'up': P[a][1] == 'L', 'sz': abs(math.log(P[k][2] / P[a][2])), 'pa': math.log(P[a][2]), 'pb': math.log(P[k][2]),
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


def weekly_count(H, L, C):
    """주봉 등급을 여러 지그재그 문턱(WK_KS)으로 세고, 큰 등급(프라이머리·사이클) 경계가 다른 문턱 결과와
    가장 많이 겹치는 것(합의안)을 고름 — 문턱 하나에 따라 구조가 흔들리지 않게."""
    _, lo, hi = WK_TH
    outs = [count_all(H, L, C, auto_th(H, L, C, k, lo, hi), [WEEK_DEG0] + WEEKLY_DEG, bar=WK_BAR) for k in WK_KS]
    if len(outs) == 1:
        return outs[0]
    bset = [{x['e'] for deg in WEEKLY_DEG for x in o.get(deg, []) if not x['live']} for o in outs]
    def agree(a, b):
        return sum(any(abs(x - y) <= 2 for y in b) for x in a) / (len(a) or 1)
    sc = [sum(agree(bset[i], bset[j]) for j in range(len(outs)) if j != i) for i in range(len(outs))]
    return outs[max(range(len(outs)), key=lambda i: (sc[i], -abs(i - len(outs) // 2)))]


def analyze(daily, long_daily=None):
    """daily: 화면용 일봉(2년), long_daily: 주봉 계산용 장기 일봉(2000~, 없으면 daily).
    장기 자료가 있으면 주봉으로 인터미디에이트·프라이머리·사이클을 한 줄기로 세고, 그 경계를 일봉(마이너·마이뉴트)의
    경계로 강제(상위 경계 = 하위 경계), 마이너 라벨은 주봉 인터미디에이트 안에서 다시 붙임. 없으면 일봉 3등급.
    반환 ew = {'lv': [[등급, [[끝날짜, 표기, 진행중(0/1), 시작날짜, 고점끝(1)/저점끝(0)]...]]...],
              'cur': [[등급, 표기, 시작날짜]...]} (큰 등급 먼저)."""
    res, must, wint = [], set(), None
    W = weekly(long_daily or daily)
    if len(W) >= 100:
        H, L, C = [w['high'] for w in W], [w['low'] for w in W], [w['close'] for w in W]
        out = weekly_count(H, L, C)
        for deg, legs in out.items():
            rows = [(W[x['e']]['hd' if x['up'] else 'ld'], sym(deg, x['k']), int(x['live']),
                     W[x['s']]['ld' if x['up'] else 'hd'], int(x['up'])) for x in legs]
            res.append((deg, rows))
            for e, _, live, st, _ in rows:
                must.add(st)
                if not live:
                    must.add(e)
            if deg == WEEK_DEG0:
                wint = [(x, r) for x, r in zip(legs, rows)]
    if daily and len(daily) >= 60:
        H, L, C = [b['high'] for b in daily], [b['low'] for b in daily], [b['close'] for b in daily]
        th = auto_th(H, L, C, 1.5, .02, .08)
        n = len(daily)
        mi = [i for i, b in enumerate(daily) if b['time'] in must and 0 < i < n - 1]
        out = count_all(H, L, C, th, DAILY_DEG[:2] if wint else DAILY_DEG, mi)
        lo = DAILY_DEG[1]
        if wint and lo in out:
            tix = {b['time']: i for i, b in enumerate(daily)}
            par = []
            for x, (e, _, live, st, _) in wint:
                ei = n - 1 if live else tix.get(e, -1 if e < daily[0]['time'] else None)
                si = tix.get(st, -1 if st < daily[0]['time'] else None)
                if ei is None or si is None or ei < 0:
                    continue
                par.append(dict(x, s=si, e=ei))
            relabel(par, out[lo])                            # 주봉 인터미디에이트 → 일봉 마이너
            relabel(out[lo], out.get(DAILY_DEG[0], []))      # → 마이뉴트
        for deg, legs in out.items():
            res.append((deg, [(daily[x['e']]['time'], sym(deg, x['k']), int(x['live']), daily[x['s']]['time'], int(x['up'])) for x in legs]))
    order = ['사이클', '프라이머리', '인터미디에이트', '마이너', '마이뉴트']
    res.sort(key=lambda x: order.index(x[0]))
    cur = [[deg, legs[-1][1], legs[-1][3]] for deg, legs in res if legs and legs[-1][2]]
    return {'lv': [[deg, [list(x) for x in legs]] for deg, legs in res], 'cur': cur}
