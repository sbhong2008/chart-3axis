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
# 등급별 표기(프로스트·프렉터 표준, 11/28 사용자 결정)
DEG = {
    '마이뉴트': (['i', 'ii', 'iii', 'iv', 'v'], ['a', 'b', 'c', 'd', 'e', 'x']),
    '마이너': (['1', '2', '3', '4', '5'], ['A', 'B', 'C', 'D', 'E', 'X']),
    '인터미디에이트': (['(1)', '(2)', '(3)', '(4)', '(5)'], ['(A)', '(B)', '(C)', '(D)', '(E)', '(X)']),
    '프라이머리': (['①', '②', '③', '④', '⑤'], ['Ⓐ', 'Ⓑ', 'Ⓒ', 'Ⓓ', 'Ⓔ', 'Ⓧ']),
    '사이클': (['I', 'II', 'III', 'IV', 'V'], ['A', 'B', 'C', 'D', 'E', 'X']),
}
DAILY_DEG = ['마이뉴트', '마이너', '인터미디에이트']
ORDER = ['사이클', '프라이머리', '인터미디에이트', '마이너', '마이뉴트']
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
SUB_MOT = {5: 3.0, 9: 2.5, 7: 0.5, 3: -3.0, 1: -3.0, 11: 0.5}
SUB_A = {5: 3.0, 3: 2.5, 7: 1.0, 9: 1.0, 1: -3.0, 11: 0.5}
SUB_COR = {3: 3.0, 5: 2.0, 7: 2.0, 1: -2.5, 9: 0.5, 11: 0.5}
K_BEAM = 3
TREND_W = 0.25       # 추세 파동(1·3·5) 크기 가점·조정 파동 크기 감점
OVER_MAX, OVER_W = 0.38, 8.0   # 조정이 시작점을 넘는 폭(확장 플랫) 상한·감점
DEV_MAX, DEV_W = 0.6, 4.0      # 조정 끝이 구간 극점에서 떨어진 정도 상한·감점
LIVE_W = 4.0                   # 진행 중 파동이 이미 반대 꼭지를 넘었을 때 감점
TRI_EXT = True                 # 역대칭·오름새·내림새 삼각형도 인정
TRI_FLAT = 0.1                 # 오름새·내림새 삼각형: 평평한 변 허용 폭(a파 크기 대비)
DIAG_PEN = 3.0                 # 대각 삼각형(4파의 1파 영역 침범 예외) 감점, None = 허용 안 함
WK_RG = False                  # 주봉 등급에도 다시 묶기·얕은 조정 지침 적용
SHALLOW_W = 1.0               # 얕고 짧은 2·4파 감점(조정 미완)
REGROUP = True                 # 상위 파동 안 하위 수를 원칙(충격 5·조정 3)대로 다시 묶기
EXT_FIT = False                # 연장 묶음 안 하위 수 구조(5-3-5-3-5 등)까지 맞아야 연장 표기
WK_EXT = True                  # 주봉 등급: 하위가 원칙보다 많으면(연장) 전환점은 그대로 두고 라벨만 '(3)의 1~5'처럼 연장 표기
CH_W, VOL_W, EXT_W = 0.5, 0.5, 0.5   # 궤도선·거래량·연장 뒤 되돌림 지침 가중치
FIB_W = 0.5                    # 피보나치·교대 지침 가중치
B_MAX, B_HARD, B_W = 1.38, 1.618, 20.0   # 조정 안 B파: A의 138.2%부터 감점, 161.8% 초과 불가
BAR_START = False
WK_BAR = False                 # 주봉 등급: 충격 극점을 실제 봉으로 확인
RESTART = 6.0                  # 규칙상 이어갈 수 없을 때 새로 세기 감점


def count_level(P, rmq, restart=False, cut=(), bar=False, vol=None, sh=True, pc=None):
    """P: 교대 피벗 [(i, 'H'|'L', 가격)]. 반환: 다리 목록 [(시작피벗, 끝피벗, pos, d)] (마지막 다리 = 진행 중)."""
    n = len(P)
    if n < 4:
        return []
    v = [math.log(p[2]) for p in P]                          # 로그 가격(장기 차트 비율 비교)
    vc = [math.log(pc(p)) for p in P] if pc else v           # 피벗 날의 일 종가(로그) — '가장 짧은 파동' 판정용
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
        if pos == 3 and g(2) is not None and d * (ext(b[3], b[4], -d) - g(2)) <= 0:
            return None                                      # 4파가 3파를 100% 넘게 되돌림(3파 시작을 넘음) — 1·2파를 모를 때도 적용
        if pos == 2 and g(1) is not None and not final and d * (g(3) - g(1)) <= 0:
            return None                                      # 3파가 1파 끝을 못 넘음
        mm = lambda x: b[x + 1] - b[x] if b[x] is not None and b[x + 1] is not None else 1   # 다리 x의 하위 파동 수
        if pos == 3 and g(1) is not None and d * (ext(b[3], b[4], -d) - g(1)) <= 0:
            # 4파가 1파 영역 침범 = 원칙 위반. 예외: 대각 삼각형(쐐기 — 3파 < 1파로 좁혀지고, 각 파동이 3개짜리, 4파는 2파 끝 위)
            if g(0) is None or g(2) is None:
                return None
            w1_, w3_ = abs(g(1) - g(0)), abs(g(3) - g(2))
            if not (DIAG_PEN is not None and w3_ < w1_ and all(mm(x) in (1, 3) for x in range(4))
                    and d * (g(4) - g(2)) > 0):
                return None
            s -= DIAG_PEN
        if pos == 4 and all(b[x] is not None for x in range(6)):
            w1, w3, w5 = abs(g(1) - g(0)), abs(g(3) - g(2)), abs(g(5) - g(4))
            gc = lambda x: vc[b[x]]
            c1, c3, c5 = abs(gc(1) - gc(0)), abs(gc(3) - gc(2)), abs(gc(5) - gc(4))
            if c3 < c1 and c3 < c5:
                return None                                  # 3파 최단(일 종가 기준 — 장중 꼬리에 흔들리지 않게)
            if d * (ext(b[3], b[4], -d) - g(1)) <= 0 and not (w5 < w3 and mm(4) in (1, 3)):
                return None                                  # 대각 삼각형이면 5파도 좁혀지고 3개짜리여야 함
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
        # 실무 지침(프로스트·프렉터, 월가 관행) — 규칙이 아니라 '흔한 비율' 가점·감점(FIB_W)
        if FIB_W and not final:
            L_ = lambda x, y: abs(g(y) - g(x)) if g(x) is not None and g(y) is not None else None
            w1, w2, w3, w4, wa, wb, wc = L_(0, 1), L_(1, 2), L_(2, 3), L_(3, 4), L_(5, 6), L_(6, 7), L_(7, 8)
            if pos == 1 and w1 and w2 is not None:
                r = w2 / w1                                  # 2파 되돌림: 보통 50~61.8%(38.2~78.6%)
                s += FIB_W if .382 <= r <= .786 else -FIB_W if r < .236 else 0
            if pos == 2 and w1 and w3:
                r = w3 / w1                                  # 3파: 보통 1파의 1.618배 안팎
                s += FIB_W * .5 if 1.382 <= r <= 2.9 else 0
            if pos == 3 and w3 and w4 is not None:
                r = w4 / w3                                  # 4파 되돌림: 보통 23.6~50%, 14.6% 미만 = 조정 미완 가능
                s += FIB_W if .236 <= r <= .5 else -FIB_W if r > .618 or (sh and r < .146) else 0
                if w1 and w2 is not None and abs(w2 / w1 - r) > .15:
                    s += FIB_W * .5                          # 교대: 2파와 4파의 깊이가 다름
            if pos == 6 and wa and wb is not None:
                r = wb / wa                                  # B: 지그재그 38.2~78.6%, 플랫 90%↑ — 23.6% 미만은 드묾
                s += FIB_W * .5 if r >= .382 else -FIB_W if r < .236 else 0
            if pos == 7 and wa and wc:
                r = wc / wa                                  # C ≈ A (61.8~161.8%)
                s += FIB_W if .618 <= r <= 1.618 else 0
        t = lambda x: P[b[x]][0]
        if SHALLOW_W and sh and not final and pos in (1, 3) and all(b[x] is not None for x in range(pos - 1, pos + 2)):
            # 얕고 짧은 2·4파 = 조정 미완(진짜 2·4파는 더 뒤) → 3·5파 시작을 늦춰 봄: 가격 23.6% 미만이면서 기간도 앞 파동의 20% 미만
            dp = abs(g(pos + 1) - g(pos)) / (abs(g(pos) - g(pos - 1)) or 1e-9)
            tm = (t(pos + 1) - t(pos)) / ((t(pos) - t(pos - 1)) or 1)
            if dp < .236 and tm < .2:
                s -= SHALLOW_W
        if CH_W and not final and pos in (2, 3, 4) and all(b[x] is not None for x in range(pos + 2)):
            if pos == 2:                                     # 3파 목표: 0·2(기본선)와 평행하게 1파 끝을 지나는 상위 궤도선
                e3 = g(1) + (g(2) - g(0)) / ((t(2) - t(0)) or 1) * (t(3) - t(1))
                w3_ = abs(g(3) - g(2)) or 1e-9
                s += CH_W * .5 if -.25 * w3_ <= d * (g(3) - e3) <= .5 * w3_ else 0
            elif pos == 3:                                     # 4파 목표: 1·3파 끝을 잇는 선과 평행하게 2파 끝을 지나는 선
                e4 = g(2) + (g(3) - g(1)) / ((t(3) - t(1)) or 1) * (t(4) - t(2))
                s += CH_W if abs(g(4) - e4) <= .25 * abs(g(3) - g(2)) else 0
            else:                                            # 5파 목표: 2·4파 기준선과 평행하게 3파 끝을 지나는 궤도선(뚫고 넘어감 흔함)
                e5 = g(3) + (g(4) - g(2)) / ((t(4) - t(2)) or 1) * (t(5) - t(3))
                w5_ = abs(g(5) - g(4)) or 1e-9
                s += CH_W if -.3 * w5_ <= d * (g(5) - e5) <= .5 * w5_ else 0
        if VOL_W and vol and not final:                      # 거래량 지침: 3파 거래량이 가장 크고 5파는 줄어듦, 조정은 거래량 감소
            va = lambda x: vol(t(x), t(x + 1)) if b[x] is not None and b[x + 1] is not None else None
            cur, prv = va(pos), va(pos - 1) if pos > 0 else None
            if cur and prv:
                if pos in (1, 3, 6) and cur < prv:
                    s += VOL_W * .5                          # 조정(2·4·B)은 앞 파동보다 거래량 적음
                if pos == 2 and d > 0 and va(0) and cur > va(0):
                    s += VOL_W * .5                          # 상승 3파 거래량 > 1파
                if pos == 4 and d > 0 and va(2) and cur < va(2):
                    s += VOL_W * .5                          # 상승 5파 거래량 < 3파(다이버전스)
        if EXT_W and pos == 5 and not final and all(b[x] is not None for x in range(7)):
            w1, w3, w5 = abs(g(1) - g(0)), abs(g(3) - g(2)), abs(g(5) - g(4))
            if w5 > w3 and w5 > w1:                          # 5파 연장 뒤 A파는 연장 출발점(4파 끝) 근처까지 되돌림
                s += EXT_W if abs(g(6) - g(4)) <= .3 * w5 else 0
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

    def inner_triangle(j):  # 하위 5개가 수평형 삼각형(대칭·역대칭·오름새·내림새)인가
        return tri_shape(v[j:j + 6])

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


def tri_shape(p):
    """6개 꼭지(로그 가격) p0..p5 = a~e 다섯 다리가 수평형 삼각형인가(책 도표 17).
    대칭(수렴: 다리마다 짧아짐) · 역대칭(확산: 다리마다 길어짐) · 오름새/내림새(한쪽 변이 평평, 다른 쪽이 좁혀 옴).
    공통: 다섯 다리가 서로 겹침(e가 a 시작점을 넘지 않음)."""
    L_ = [abs(p[x + 1] - p[x]) for x in range(5)]
    if not L_[0]:
        return False
    if abs(p[5] - p[0]) > L_[0]:
        return False                                         # 겹치지 않음 = 삼각형 아님
    contract = L_[2] < L_[0] and L_[3] < L_[1] and L_[4] < L_[2]
    expand = L_[2] > L_[0] and L_[3] > L_[1] and L_[4] > L_[2]
    flat = TRI_FLAT * L_[0]
    barrier = ((abs(p[3] - p[1]) <= flat and L_[3] < L_[1]) or (abs(p[4] - p[2]) <= flat and L_[2] < L_[0]))
    return contract or (TRI_EXT and (expand or barrier))


def tri(kids):
    """하위 5개 다리가 수평형 삼각형인가(tri_shape, 다리 끝 로그 가격 'pa'·'pb')"""
    return tri_shape([kids[0]['pa']] + [c['pb'] for c in kids])


def imp_ok(kids):
    """하위 5개가 충격파 3대 규칙(2파 < 1파 시작, 3파 최단 아님, 4파 1파 영역 밖)을 지키는가"""
    p = [kids[0]['pa']] + [c['pb'] for c in kids]
    d = 1 if p[5] > p[0] else -1
    q = [kids[0].get('ca', kids[0]['pa'])] + [c.get('cb', c['pb']) for c in kids]
    w = [abs(q[i + 1] - q[i]) for i in range(5)]             # 3파 최단 = 일 종가 기준
    return d * (p[2] - p[0]) > 0 and d * (p[4] - p[1]) > 0 and not (w[2] < w[0] and w[2] < w[4])


def part_ok(kids, pk=''):
    """진행 중 충격의 앞부분(2~4개)이 규칙을 지키는가: 2파 < 1파 시작, 4파 1파 영역 밖(5·C 자리 대각 삼각형은 2파 끝 위)"""
    p = [kids[0]['pa']] + [c['pb'] for c in kids]
    d = 1 if p[1] > p[0] else -1
    if len(p) > 2 and d * (p[2] - p[0]) <= 0:
        return False
    if len(p) > 3 and d * (p[3] - p[1]) <= 0:
        return False                                         # 3파가 1파 끝을 못 넘음
    if len(p) > 4 and d * (p[4] - (p[2] if pk in '5C' else p[1])) <= 0:
        return False
    return True


MOT_M, COR_M = {1, 5, 9, 13}, {1, 3, 5, 7, 11}   # 하위 파동 수: 충격 = 5(연장 9), 조정 = 3(삼각형 5·복합 7)


def fits(keys, kids, pk=''):
    """하위 파동 수가 붙일 라벨과 맞는가(구조 우선).
    충격 1-5 = 5-3-5-3-5(또는 대각 삼각형 3-3-3-3-3), 지그재그 5-3-5·플랫 3-3-5, 삼각형 3-3-3-3-3."""
    ms = [c['m'] for c in kids]
    if keys[:1] == '1':
        imp = all((m in MOT_M) if k in '135' else (m in COR_M) for k, m in zip(keys, ms))
        diag = (len(keys) == 5 or pk in '5C') and all(m in (1, 3) for m in ms)   # 대각 삼각형(끝 = 5·C 자리, 진행 중 포함)
        return imp or diag
    if keys == 'ABCDE':
        return all(m in (1, 3, 5) for m in ms)               # 삼각형: 각 3개(마지막 e는 작은 삼각형 5개 가능)
    ok = {'A': {1, 3, 5}, 'B': COR_M, 'C': MOT_M, 'X': COR_M}  # 지그재그 5-3-5·플랫 3-3-5·복합 W-X-Y
    return all(m in ok[k] for k, m in zip(keys, ms))


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
            kids[0]['dup'] = 1                               # 화면: 상위 라벨과 겹치므로 글자 생략
        elif motive and ((n == 5 and imp_ok(kids)) or (P['live'] and n < 5 and part_ok(kids, P['k']))):
            keys = '12345'[:n]
        elif not motive and (n == 3 or (P['live'] and n < 3)):
            keys = 'ABC'[:n]
        elif not motive and n == 5 and tri(kids):
            keys = 'ABCDE'
        elif not motive and n == 7:
            keys = 'ABCXABC'
        else:
            continue                                         # 하위 구조가 원칙과 다르면(연장 등) 하위 등급 자체 해석 유지
        if n > 1 and not fits(keys, kids, P['k']):
            continue                                         # 붙일 라벨과 하위 파동 수가 안 맞으면(예: 3개짜리에 '1') 하위 해석 유지
        for c, k in zip(kids, keys):
            c['k'] = k


def _odd_parts(n, t):
    """n개를 t묶음(각 홀수 개)으로 나누는 모든 방법 — 묶음마다 방향이 번갈아 바뀜"""
    if t == 1:
        if n % 2:
            yield (n,)
        return
    for a in range(1, n - t + 2, 2):
        for rest in _odd_parts(n - a, t - 1):
            yield (a,) + rest


def _merge(units, sizes):
    out, i = [], 0
    for z in sizes:
        g = units[i:i + z]
        i += z
        out.append({'s': g[0]['s'], 'e': g[-1]['e'], 'k': '', 'up': g[0]['up'], 'pa': g[0]['pa'], 'pb': g[-1]['pb'], 'ca': g[0].get('ca', g[0]['pa']), 'cb': g[-1].get('cb', g[-1]['pb']),
                    'sz': abs(g[-1]['pb'] - g[0]['pa']), 'm': z, 'live': g[-1]['live']})
    return out


def _ext_plan(units, sizes, keys):
    """묶음 크기(sizes)대로 나눈 하위 다리들에 붙일 라벨: 1개 묶음 = 그 묶음 라벨, 여러 개 묶음 = 연장 안의 한 단계 아래 파동
    (충격 묶음 5개 = 1~5, 조정 묶음 3개 = A·B·C, 5개 삼각형 = A~E, 7개 = A·B·C·X·A·B·C). 원칙대로 못 붙이면 None."""
    plan, i = [], 0
    for z, gk in zip(sizes, keys):
        sub = units[i:i + z]
        i += z
        if z == 1:
            plan.append((sub, gk, None))
            continue
        gm = gk in '135C' or (gk == 'A' and z == 5)
        if gm and z == 5 and imp_ok(sub):
            ks = '12345'
        elif not gm and z == 3:
            ks = 'ABC'
        elif not gm and z == 5 and tri(sub):
            ks = 'ABCDE'
        elif not gm and z == 7:
            ks = 'ABCXABC'
        else:
            return None
        if EXT_FIT and not fits(ks, sub, gk):
            return None
        plan.append((sub, ks, gk))
    return plan


def _best_split(units, motive, pk, ext=False):
    """units(하위 다리)를 원칙대로 묶음: 충격 = 5개(3대 규칙·5-3-5-3-5), 조정 = 3개(지그재그 5-3-5·플랫 3-3-5, B ≤ A 161.8%).
    규칙을 지키는 묶음 중 구조(fits)·실무 비율이 가장 잘 맞는 것, 없으면 None."""
    t = 5 if motive else 3
    n = len(units)
    if n < t or (n - t) % 2 or n > 41:
        return None
    best, bs = None, None
    for sizes in _odd_parts(n, t):
        if ext and _ext_plan(units, sizes, '12345' if motive else 'ABC') is None:
            continue                                         # 연장 표기: 묶음 안 하위 다리도 원칙대로 라벨이 붙어야 함
        g = _merge(units, sizes)
        p = [g[0]['pa']] + [x['pb'] for x in g]
        w = [abs(p[i + 1] - p[i]) for i in range(t)]
        if motive:
            if not imp_ok(g):
                continue
            keys = '12345'
            sc = (w[2] >= w[0]) * .5 + (.236 <= w[1] / (w[0] or 1e-9) <= .786) * .5 + (.236 <= w[3] / (w[2] or 1e-9) <= .618) * .5
            for c in (1, 3):                                 # 얕고 짧은 2·4파 = 조정 미완 가능(SHALLOW_W)
                tm = (g[c]['e'] - g[c]['s']) / ((g[c - 1]['e'] - g[c - 1]['s']) or 1)
                if w[c] / (w[c - 1] or 1e-9) < .236 and tm < .2:
                    sc -= SHALLOW_W
        else:
            if w[1] > B_HARD * w[0]:
                continue
            keys = 'ABC'
            sc = (.618 <= w[2] / (w[0] or 1e-9) <= 1.618) * .5
        sc += 2.0 * fits(keys, g, pk)
        sc -= .1 * max(sizes)                                # 한 묶음에 몰리지 않게(연장은 허용하되 균형 선호)
        if bs is None or sc > bs:
            best, bs = g, sc
    if best:
        for x, k in zip(best, keys):
            x['k'] = k
    return best


def regroup(parent, mid, low=None):
    """프랙탈 원칙 보강(책: 홀수 파동 = 5개, 짝수 파동 = 3개): 상위 파동 안의 하위 파동 수가 원칙과 다르면
    ① 하위가 너무 많으면(예: 연장으로 9개) 하위 다리를 5개(3개)로 묶고, ② 너무 적으면(1·3개) 한 단계 더 아래 다리로 다시 묶음.
    mid 목록을 제자리에서 바꿈. 진행 중 상위 파동은 건드리지 않음."""
    for P in parent:
        if P['live']:
            continue
        motive = P['k'] in '135C' or (P['k'] == 'A' and P['m'] == 5)
        kids = [c for c in mid if c['s'] >= P['s'] and c['e'] <= P['e']]
        n = len(kids)
        if not kids or kids[0]['s'] != P['s'] or kids[-1]['e'] != P['e']:
            continue                                         # 경계가 안 맞으면(자료 시작 등) 그대로
        if (motive and n == 5 and imp_ok(kids)) or (not motive and (n == 3 or n == 7 or (n == 5 and tri(kids)))):
            continue                                         # 이미 원칙대로
        t = 5 if motive else 3
        new = None
        if n > t:
            new = _best_split(kids, motive, P['k'])
        if new is None and low:
            lk = [c for c in low if c['s'] >= P['s'] and c['e'] <= P['e']]
            if lk and lk[0]['s'] == P['s'] and lk[-1]['e'] == P['e'] and len(lk) > n:
                new = _best_split(lk, motive, P['k'])
        if new is None:
            continue
        i = mid.index(kids[0])
        mid[i:i + n] = new


def extlabel(parent, mid):
    """연장 표기(주봉): 상위 파동 안 하위 다리가 원칙(충격 5·조정 3)보다 많으면, 다리를 합치지 않고(실제 전환점 보존)
    원칙대로 묶었을 때 여러 다리로 된 묶음(연장 파동)의 다리에 한 단계 아래 라벨을 붙임 — 예) ① 안 9개 = (1)·(2)·[(3)의 1~5]·(4)·(5).
    다리에 'xg'(속한 연장 파동 라벨) 추가, 'k' = 연장 안 라벨."""
    for P in parent:
        if P['live']:
            continue
        motive = P['k'] in '135C' or (P['k'] == 'A' and P['m'] == 5)
        kids = [c for c in mid if c['s'] >= P['s'] and c['e'] <= P['e']]
        n, t = len(kids), (5 if motive else 3)
        if n <= t or kids[0]['s'] != P['s'] or kids[-1]['e'] != P['e']:
            continue
        if not motive and ''.join(c['k'] for c in kids) in ('ABCXABC', 'ABCDE'):
            continue                                         # 복합 조정·삼각형으로 이미 라벨이 붙음
        g = _best_split(kids, motive, P['k'], ext=True)
        if not g:
            continue
        plan = _ext_plan(kids, [x['m'] for x in g], [x['k'] for x in g])
        for sub, ks, gk in plan:
            for c, k in zip(sub, ks):
                c['k'] = k
                if gk:
                    c['xg'] = gk


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


def count_all(H, L, C, th, degs, must=(), bar=False, V=None, rg=True, CH=None, CL=None, ext=False):
    """여러 등급을 아래에서 위로 세고(꺾임 묶기), 라벨은 위에서 아래로 다시 붙임.
    반환: {등급: [{'s','e' 봉 번호, 'k' 라벨키, 'up' 상승 다리, 'm' 하위 수, 'live' 진행 중}]}"""
    P = zigzag(H, L, th)
    rmq = range_ext(H, L)
    CH, CL = CH or C, CL or C                                # 고점·저점 날의 일 종가(주봉 = 고가일·저가일 종가)
    pc = lambda p: (CH if p[1] == 'H' else CL)[p[0]]
    vol = None
    if V and any(V):
        cs = [0.0]
        for x in V:
            cs.append(cs[-1] + (x or 0))
        vol = lambda a, b: (cs[b + 1] - cs[a]) / (b - a + 1) if b >= a else None   # 봉 a~b 평균 거래량
    cutb = set()                                             # 상위(주봉) 경계 봉 → 가장 가까운 지그재그 피벗(3봉 이내)
    for b in must:
        near = min(P, key=lambda p: abs(p[0] - b), default=None)
        if near and abs(near[0] - b) <= 3:
            cutb.add(near[0])
    out = {}
    for deg in degs:
        cut = [i for i, p in enumerate(P) if p[0] in cutb]
        legs = count_level(P, rmq, cut=cut, bar=bar, vol=vol, sh=rg, pc=pc) or count_level(P, rmq, True, cut, bar, vol, sh=rg, pc=pc)
        if len(legs) < 2:
            break
        out[deg] = [{'s': P[a][0], 'e': P[k][0], 'k': POS[pos], 'up': P[a][1] == 'L', 'sz': abs(math.log(P[k][2] / P[a][2])), 'pa': math.log(P[a][2]), 'pb': math.log(P[k][2]), 'ca': math.log(pc(P[a])), 'cb': math.log(pc(P[k])),
                     'm': k - a, 'live': k == len(P) - 1} for a, k, pos, d in legs]
        P = [P[legs[0][0]]] + [P[k] for _, k, _, _ in legs]   # 상위 등급 후보 피벗 = 이번 등급 경계
    names = list(out)
    for j, (hi, lo) in enumerate(zip(names[::-1], names[::-1][1:])):
        if REGROUP and (rg is True or (rg and hi in rg)):
            regroup(out[hi], out[lo], out.get(names[::-1][j + 2]) if j + 2 < len(names) else None)
        relabel(out[hi], out[lo])
        if ext:
            extlabel(out[hi], out[lo])                       # 원칙보다 하위가 많은 상위 파동 = 연장 표기(relabel이 건너뛴 것)
    return out


def weekly(bars):
    """일봉 → 주봉(고가·저가 날짜 보존)."""
    import datetime as dt
    W = []
    for b in bars:
        y, w, _ = dt.date.fromisoformat(b['time']).isocalendar()
        if not W or W[-1]['k'] != (y, w):
            W.append({'k': (y, w), 'high': b['high'], 'low': b['low'], 'close': b['close'], 'hd': b['time'], 'ld': b['time'],
                      'hc': b['close'], 'lc': b['close'], 'volume': b.get('volume') or 0})
        else:
            x = W[-1]
            if b['high'] >= x['high']:
                x['high'], x['hd'], x['hc'] = b['high'], b['time'], b['close']
            if b['low'] <= x['low']:
                x['low'], x['ld'], x['lc'] = b['low'], b['time'], b['close']
            x['close'] = b['close']
            x['volume'] += b.get('volume') or 0
    return W


def weekly_count(H, L, C, V=None, CH=None, CL=None):
    """주봉 등급을 여러 지그재그 문턱(WK_KS)으로 세고, 큰 등급(프라이머리·사이클) 경계가 다른 문턱 결과와
    가장 많이 겹치는 것(합의안)을 고름 — 문턱 하나에 따라 구조가 흔들리지 않게."""
    _, lo, hi = WK_TH
    outs = [count_all(H, L, C, auto_th(H, L, C, k, lo, hi), [WEEK_DEG0] + WEEKLY_DEG, bar=WK_BAR, V=V, rg=WK_RG, CH=CH, CL=CL, ext=WK_EXT) for k in WK_KS]
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
        out = weekly_count(H, L, C, [w['volume'] for w in W], [w['hc'] for w in W], [w['lc'] for w in W])
        for deg, legs in out.items():
            low = ORDER[ORDER.index(deg) + 1]
            rows = [(W[x['e']]['hd' if x['up'] else 'ld'], f"{sym(deg, x['xg'])}의 {sym(low, x['k'])}" if x.get('xg') else sym(deg, x['k']), int(x['live']),
                     W[x['s']]['ld' if x['up'] else 'hd'], int(x['up'])) + ((0, sym(deg, x['xg'])) if x.get('xg') else ()) for x in legs]
            res.append((deg, rows))
            for e, _, live, st, _, *_ in rows:
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
        out = count_all(H, L, C, th, DAILY_DEG[:2] if wint else DAILY_DEG, mi, V=[b.get('volume') or 0 for b in daily])
        lo = DAILY_DEG[1]
        if wint and lo in out:
            tix = {b['time']: i for i, b in enumerate(daily)}
            par = []
            for x, (e, _, live, st, _, *_) in wint:
                ei = n - 1 if live else tix.get(e, -1 if e < daily[0]['time'] else None)
                si = tix.get(st, -1 if st < daily[0]['time'] else None)
                if ei is None or si is None or ei < 0:
                    continue
                par.append(dict(x, s=si, e=ei))
            if REGROUP:
                regroup(par, out[lo], out.get(DAILY_DEG[0]))
            relabel(par, out[lo])                            # 주봉 인터미디에이트 → 일봉 마이너
            if REGROUP:
                regroup(out[lo], out.get(DAILY_DEG[0], []))
            relabel(out[lo], out.get(DAILY_DEG[0], []))      # → 마이뉴트
        for deg, legs in out.items():
            res.append((deg, [(daily[x['e']]['time'], sym(deg, x['k']), int(x['live']), daily[x['s']]['time'], int(x['up'])) + ((1,) if x.get('dup') else ()) for x in legs]))
    res.sort(key=lambda x: ORDER.index(x[0]))
    cur = [[deg, legs[-1][1], legs[-1][3]] for deg, legs in res if legs and legs[-1][2]]
    return {'lv': [[deg, [list(x) for x in legs]] for deg, legs in res], 'cur': cur}
