"""매일 데이터 빌드: 주요 지수 + 국내(KOSPI·KOSDAQ 보통주) + 미국(S&P500 + 나스닥 유동성 상위 + 주요 ETF) → 정적 JSON.

사용: python3 build.py [--out site] [--limit N] [--markets KR,US] [--days 730]
출력:
  site/                      web/ 의 앱 파일 복사본
  site/data/universe.json    검색·홈·섹터 목록용 (종목별 마지막 날 지표 요약)
  site/data/validation.json  일일 검증: 데이터 품질 + 신호·국면별 이후 수익률·적중률
  site/data/p/<IX|KR|US|SEC>/<id>.json   일봉 (t,o,h,l,c,v[,sr=공매도 비중%])
키·로그인 불필요(FinanceDataReader·yfinance·FINRA 무료 소스).
국내 공매도는 KRX 로그인이 필요 → 환경변수 KRX_ID·KRX_PW(GitHub Secrets)가 있을 때만 pykrx 로 수집.
"""
import argparse, datetime as dt, json, math, os, re, shutil, sys, time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import FinanceDataReader as fdr
import yfinance as yf

from indicators import summary, forward_stats, BULL, BEAR
import elliott

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------- 주요 지표 (홈 화면) ----------
# (키, 소스, 심볼, 이름, 그룹)  소스: fdr = FinanceDataReader, yf = yfinance
INDICES = [
    ('KS11', 'fdr', 'KS11', 'KOSPI', '한국'), ('KQ11', 'fdr', 'KQ11', 'KOSDAQ', '한국'), ('KS200', 'fdr', 'KS200', 'KOSPI200', '한국'),
    ('USDKRW', 'yf', 'KRW=X', '원/달러 환율', '한국'),
    ('GSPC', 'yf', '^GSPC', 'S&P500', '미국'), ('IXIC', 'yf', '^IXIC', '나스닥 종합', '미국'), ('DJI', 'yf', '^DJI', '다우존스', '미국'),
    ('RUT', 'yf', '^RUT', '러셀2000', '미국'), ('SOX', 'yf', '^SOX', '필라델피아 반도체', '미국'),
    ('N225', 'yf', '^N225', '닛케이225', '일본'), ('TOPIX', 'yf', '1306.T', 'TOPIX (ETF 1306)', '일본'), ('USDJPY', 'yf', 'JPY=X', '엔/달러 환율', '일본'),
    ('SSE', 'yf', '000001.SS', '상해종합', '중국'), ('SZSE', 'yf', '399001.SZ', '심천성분', '중국'), ('HSI', 'yf', '^HSI', '항셍', '중국'),
    ('HSCE', 'yf', '^HSCE', '항셍 H주(HSCEI)', '중국'),
    ('ACWI', 'yf', 'ACWI', 'MSCI 전세계(ACWI ETF)', '글로벌'), ('SX5E', 'yf', '^STOXX50E', '유로스톡스50', '글로벌'),
    ('DAX', 'yf', '^GDAXI', '독일 DAX', '글로벌'), ('VIX', 'yf', '^VIX', 'VIX 변동성', '글로벌'), ('DXY', 'yf', 'DX-Y.NYB', '달러인덱스', '글로벌'),
    ('TNX', 'yf', '^TNX', '미국 10년 금리', '글로벌'), ('GOLD', 'yf', 'GC=F', '금 선물', '글로벌'), ('GLD', 'yf', 'GLD', '금 현물(GLD ETF)', '글로벌'),
    ('WTI', 'yf', 'CL=F', 'WTI 원유', '글로벌'),
    ('BTC', 'yf', 'BTC-USD', '비트코인', '글로벌'),
]

# ---------- 국내 업종(KSIC 158개) → 대표 섹터 ----------
KR_SECTOR_RULES = [
    ('반도체', ['반도체']),
    ('2차전지', ['이차전지']),
    ('방산·항공우주', ['무기 및 총포탄', '항공기']),
    ('조선', ['선박']),
    ('자동차', ['자동차']),
    ('IT하드웨어·부품', ['전자부품', '컴퓨터 및 주변장치', '통신 및 방송 장비', '영상 및 음향기기', '마그네틱', '측정, 시험', '사진장비', '전구 및 조명']),
    ('소프트웨어·인터넷', ['소프트웨어', '컴퓨터 프로그래밍', '자료처리', '기타 정보 서비스']),
    ('통신', ['전기 통신업']),
    ('미디어·엔터', ['영화', '방송', '오디오물', '영상·오디오', '창작 및 예술', '광고업', '서적', '기록매체', '유원지', '스포츠 서비스']),
    ('바이오·제약', ['의약품', '기초 의약물질', '자연과학 및 공학 연구개발업']),
    ('의료기기', ['의료용 기기', '의료용품']),
    ('금융', ['은행', '보험', '금융', '신탁업']),
    ('건설·건자재', ['건설업', '공사업', '건축기술', '시멘트', '유리', '내화', '기타 비금속', '건축자재', '나무제품', '제재', '가구 제조']),
    ('유틸리티', ['전기업', '연료용 가스', '증기, 냉']),
    ('전력기기·전기장비', ['전동기', '절연선', '기타 전기장비']),
    ('기계', ['기계 제조업', '기계장비', '산업용 기계 및 장비 임대', '구조용 금속', '그외 기타 운송장비']),
    ('정유·에너지', ['석유 정제', '연료 소매']),
    ('화학', ['화학', '합성고무', '플라스틱', '고무제품', '비료']),
    ('철강·금속', ['철강', '비철금속', '금속 주조', '금속 가공', '해체, 선별']),
    ('음식료', ['식품', '음료', '곡물', '과실', '도축', '수산물', '떡, 빵', '도시락', '동·식물성', '사료', '담배 제조', '어로', '작물', '음·식료품']),
    ('섬유·의류', ['섬유', '의복', '봉제', '편조', '방적', '직물', '신발', '가죽']),
    ('운송·물류', ['운송업', '운송관련', '운송장비 임대', '항공 여객', '해상 운송', '도로 화물']),
    ('유통·소비재', ['소매업', '도매업', '상품 중개', '숙박', '여행사', '가정용 기기', '악기', '운동 및 경기용구', '귀금속', '개인 및 가정용품', '그외 기타 개인']),
    ('교육', ['교육', '학원', '교습']),
]


# 업종 코드(KSIC)가 실제 사업과 다르게 잡히는 대표 종목 보정 (지주사·장비·소재 등). 코드→이름은 2026-11-24 확인
KR_SECTOR_OVERRIDE = {
    '005930': '반도체', '042700': '반도체', '403870': '반도체', '039030': '반도체', '240810': '반도체', '036930': '반도체',
    '058470': '반도체', '095340': '반도체', '357780': '반도체', '005290': '반도체', '084370': '반도체', '319660': '반도체',
    '086520': '2차전지', '009540': '조선', '034020': '전력기기·전기장비', '064350': '방산·항공우주', '028260': '건설·건자재',
}


def kr_sector(ind):
    if not isinstance(ind, str):
        return '기타'
    for name, kws in KR_SECTOR_RULES:
        if any(k in ind for k in kws):
            return name
    return '기타'


US_SECTOR_KO = {
    'Information Technology': '정보기술', 'Health Care': '헬스케어', 'Financials': '금융',
    'Consumer Discretionary': '경기소비재', 'Communication Services': '커뮤니케이션', 'Industrials': '산업재',
    'Consumer Staples': '필수소비재', 'Energy': '에너지', 'Utilities': '유틸리티', 'Real Estate': '부동산',
    'Materials': '소재',
}
# 나스닥 목록(한글 업종) → GICS 한글 섹터 (순서대로 첫 일치)
NQ_RULES = [
    ('유틸리티', ['유틸리티', '민자 발전']),
    ('필수소비재', ['식품', '음료', '담배', '개인 생활', '증류주', '할인점', '가정용 제품', '농업']),
    ('부동산', ['REIT', '부동산']),
    ('헬스케어', ['생명 공학', '제약', '의료', '의약품']),
    ('정보기술', ['반도체', '소프트웨어', 'IT 서비스', '전자 장비', '통신 및 네트워킹', '컴퓨터 하드웨어', '통합 하드웨어', '전화 및 소형', '사무기기']),
    ('커뮤니케이션', ['온라인 서비스', '광고', '방송', '엔터테인먼트', '통신 서비스', '출판']),
    ('에너지', ['오일', '석탄', '우라늄', '재생 가능']),
    ('소재', ['화학', '금속', '채굴', '알루미늄', '철 및 강철', '종이', '포장', '용기', '임업', '건설 자재', '농화학']),
    ('금융', ['은행', '보험', '투자', '금융', '대출', '핀테크', '블록 체인', '중개']),
    ('산업재', ['기계', '항공우주', '건설 및 엔지니어링', '경영 지원', '물류', '운송', '항공사', '항만', '공항', '고용', '전기 부품',
              '중전기', '중장비', '환경 서비스', '비즈니스 지원', '상업 인쇄', '전문 정보', '다각적 산업']),
    ('경기소비재', ['레스토랑', '소매', '자동차', '의류', '호텔', '여가', '오락', '카지노', '가정용', '가전', '장난감', '주택', '제화',
                '직물', '교육', '개인 서비스', '백화점', '타이어', '소비재 대기업']),
]
NQ_EXCLUDE = {'투자 지주 회사', '폐쇄형 펀드', '영국 투자 신탁'}
NQ_MIN_TV, NQ_MIN_PX = 30e6, 5  # 나스닥 추가 종목: 20일 평균 거래대금 3천만 달러 이상, 주가 5달러 이상

US_ETF = {
    'SPY': 'S&P500 ETF', 'QQQ': '나스닥100 ETF', 'DIA': '다우30 ETF', 'IWM': '러셀2000 ETF',
    'SOXX': '반도체 ETF(SOXX)', 'SMH': '반도체 ETF(SMH)', 'TLT': '미국 장기국채 ETF', 'GLD': '금 ETF',
    'XLK': '정보기술 섹터 ETF', 'XLV': '헬스케어 섹터 ETF', 'XLF': '금융 섹터 ETF', 'XLY': '경기소비재 섹터 ETF',
    'XLC': '커뮤니케이션 섹터 ETF', 'XLI': '산업재 섹터 ETF', 'XLP': '필수소비재 섹터 ETF', 'XLE': '에너지 섹터 ETF',
    'XLU': '유틸리티 섹터 ETF', 'XLRE': '부동산 섹터 ETF', 'XLB': '소재 섹터 ETF',
}


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def to_bars(df):
    """DataFrame(Open,High,Low,Close,Volume) → bars, 결측·0 가격 보정."""
    out = []
    for idx, r in df.iterrows():
        g = lambda k: r[k] if k in r.index else None
        o, h, l, c, v = g('Open'), g('High'), g('Low'), g('Close'), g('Volume')
        bad = lambda x: x is None or (isinstance(x, float) and math.isnan(x))
        if bad(c) or c <= 0:
            continue
        o = c if bad(o) or o <= 0 else o
        h = max(o, c) if bad(h) or h <= 0 else h
        l = min(o, c) if bad(l) or l <= 0 else l
        v = 0 if bad(v) else v
        out.append({'time': idx.strftime('%Y-%m-%d'), 'open': float(o), 'high': float(max(h, o, c)),
                    'low': float(min(l, o, c)), 'close': float(c), 'volume': float(v)})
    return out


# ---------- 종목 목록 ----------
def kr_universe():
    d = fdr.StockListing('KRX-DESC')
    d = d[d['Market'].isin(['KOSPI', 'KOSDAQ', 'KOSDAQ GLOBAL'])]
    d = d[(d['Code'].str[-1] == '0') & ~d['Name'].str.contains('스팩')]  # 보통주, 스팩 제외
    try:
        mc = dict(zip(*fdr.StockListing('KRX')[['Code', 'Marcap']].values.T))
    except Exception as e:
        log('시가총액 실패', e); mc = {}
    return [{'id': f"KR:{r.Code}", 'n': r.Name, 'm': 'KOSPI' if r.Market == 'KOSPI' else 'KOSDAQ',
             's': KR_SECTOR_OVERRIDE.get(r.Code) or kr_sector(r.Industry), 'ind': r.Industry if isinstance(r.Industry, str) else '',
             'mc': int(v) // 100_000_000 if (v := mc.get(r.Code)) and v == v else 0} for r in d.itertuples()]  # 시가총액(억원)


def us_universe():
    u = fdr.StockListing('S&P500')
    fix = {'BRKB': 'BRK.B', 'BFB': 'BF.B'}  # FDR 목록은 점(.)이 빠진 표기
    items = [{'id': f"US:{fix.get(r.Symbol, r.Symbol)}", 'n': r.Name, 'm': 'S&P500',
              's': US_SECTOR_KO.get(r.Sector, r.Sector), 'ind': r.Industry} for r in u.itertuples()]
    have = {it['id'] for it in items}
    try:
        nq = fdr.StockListing('NASDAQ')
        for r in nq.itertuples():
            sym, ind = str(r.Symbol), r.Industry if isinstance(r.Industry, str) else ''
            if f'US:{sym}' in have or ind in NQ_EXCLUDE or not ind or not re.fullmatch(r'[A-Z]{1,5}', sym):
                continue
            sec = next((n for n, kws in NQ_RULES if any(k in ind for k in kws)), '기타')
            items.append({'id': f'US:{sym}', 'n': r.Name, 'm': 'NASDAQ', 's': sec, 'ind': ind, 'nq': 1})
    except Exception as e:
        log('나스닥 목록 실패', e)
    items += [{'id': f"US:{k}", 'n': v, 'm': 'ETF', 's': 'ETF'} for k, v in US_ETF.items()]
    return items


# ---------- 시세 ----------
EW = {}      # id → 엘리엇 다층 파동(elliott.analyze)
LSTART = None  # 장기(주봉 등급용) 시작일 — main 에서 설정


def keep(k, b, start):
    """장기 일봉 b 로 엘리엇(일봉 2년 + 주봉 10년 등급)을 계산하고, 화면용 기간(start~)만 돌려줌."""
    d = [x for x in b if x['time'] >= start]
    try:
        EW[k] = elliott.analyze(d, b)
    except Exception as e:
        log('엘리엇 실패', k, e)
    return d


def fetch_fdr(pairs, start, label):
    """pairs: [(id, fdr심볼)]"""
    res = {}

    def one(p):
        err = None
        for k in range(3):
            try:
                return p[0], to_bars(fdr.DataReader(p[1], LSTART or start))
            except Exception as e:
                err = e; time.sleep(1 + k * 2)
        log(label, '실패', p[1], err)
        return p[0], []

    with ThreadPoolExecutor(8) as ex:
        for n, f in enumerate(as_completed([ex.submit(one, p) for p in pairs]), 1):
            k, b = f.result(); res[k] = keep(k, b, start)
            if n % 500 == 0:
                log(f'{label} {n}/{len(pairs)}')
    return res


def fetch_yf(pairs, start, label, chunk=100):
    """pairs: [(id, 야후심볼)]"""
    res = {}
    for k in range(0, len(pairs), chunk):
        part = pairs[k:k + chunk]
        syms = [s for _, s in part]
        try:
            df = yf.download(syms, start=LSTART or start, group_by='ticker', auto_adjust=True, threads=True, progress=False)
        except Exception as e:
            log(label, '묶음 실패', e); continue
        for i, s in part:
            try:
                res[i] = keep(i, to_bars(df[s].dropna(how='all')) if len(syms) > 1 else to_bars(df.dropna(how='all')), start)
            except Exception:
                res[i] = []
        log(f'{label} {min(k + chunk, len(pairs))}/{len(pairs)}')
    return res


SHORT_DAYS = 130  # 공매도 비중 수집 기간(거래일, 약 6개월)


def short_days(n):
    d, out = dt.date.today(), []
    while len(out) < n + 15:          # 휴일 여유
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return out


def fetch_finra_short(symbols):
    """미국: FINRA Reg SHO 일별 공매도 거래량(CNMS) → {심볼: {날짜: 비중%}}. 심볼 BRK.B → BRK/B."""
    want = {s.replace('.', '/'): s for s in symbols}
    res = defaultdict(dict)

    def one(d):
        url = f'https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d:%Y%m%d}.txt'
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30) as r:
                return d, r.read().decode()
        except Exception:
            return d, ''                 # 휴일·미게시

    with ThreadPoolExecutor(8) as ex:
        ok = 0
        for d, txt in ex.map(one, short_days(SHORT_DAYS)):
            if not txt:
                continue
            ok += 1
            day = d.isoformat()
            for ln in txt.splitlines()[1:]:
                p = ln.split('|')
                if len(p) >= 5 and p[1] in want:
                    try:
                        tot = float(p[4])
                        if tot > 0:
                            res[want[p[1]]][day] = round(float(p[2]) / tot * 100, 1)
                    except ValueError:
                        pass
    log('공매도(FINRA)', ok, '일 ·', len(res), '종목')
    return res


def fetch_krx_short(codes):
    """국내: KRX 공매도 거래량 비중(pykrx, KRX 로그인 필요). 자격 없으면 빈 결과."""
    if not (os.environ.get('KRX_ID') and os.environ.get('KRX_PW')):
        log('공매도(KRX) 건너뜀: KRX_ID·KRX_PW 없음')
        return {}
    try:
        from pykrx import stock
    except Exception as e:
        log('공매도(KRX) 건너뜀: pykrx 없음', e); return {}
    want, res, ok = set(codes), defaultdict(dict), 0
    t0, fails = time.time(), 0

    def get(ds, mkt):
        # KRX 가 연속 요청을 거부하면 pykrx 가 빈 표를 돌려줌 → 쉬었다가 최대 3번 시도(휴장일도 빈 표라 몇 초 낭비는 감수)
        nonlocal fails
        for k in range(3):
            try:
                df = stock.get_shorting_volume_by_ticker(ds, mkt)
                if df is not None and not df.empty and '비중' in df.columns:
                    fails = 0
                    return df
            except Exception:
                pass
            fails += 1
            time.sleep(20 if fails >= 5 else 2 * (k + 1))
        return None

    for d in short_days(SHORT_DAYS):
        if time.time() - t0 > 900:           # 최대 15분: 넘으면 받은 만큼만 사용
            log('공매도(KRX) 시간 제한으로 중단'); break
        got = False
        for mkt in ('KOSPI', 'KOSDAQ'):
            df = get(d.strftime('%Y%m%d'), mkt)
            time.sleep(.4)                   # 요청 간격
            if df is None:
                continue
            got = True
            for code, v in df['비중'].items():
                if code in want and v == v:
                    res[code][d.isoformat()] = round(float(v), 1)
        ok += got
    log('공매도(KRX)', ok, '일 ·', len(res), '종목')
    return res


def sector_index(member_bars):
    """동일가중 섹터지수: 종목별 일간 변화율(시·고·저·종 / 전일 종가)의 평균을 누적. 거래량 = 거래대금 합."""
    by = {}
    for bars in member_bars:
        for p, b in zip(bars, bars[1:]):
            pc = p['close']
            if abs(b['close'] / pc - 1) > .5:  # 액면분할·데이터 오류 제외
                continue
            e = by.setdefault(b['time'], [0, 0, 0, 0, 0, 0])
            e[0] += b['open'] / pc; e[1] += b['high'] / pc; e[2] += b['low'] / pc; e[3] += b['close'] / pc
            e[4] += b['close'] * b['volume']; e[5] += 1
    out, lv = [], 1000.0
    for t in sorted(by):
        o, h, l, c, val, n = by[t]
        b = {'time': t, 'open': lv * o / n, 'high': lv * h / n, 'low': lv * l / n, 'close': lv * c / n, 'volume': val}
        b['high'] = max(b['high'], b['open'], b['close']); b['low'] = min(b['low'], b['open'], b['close'])
        out.append(b); lv = b['close']
    return out


def write_bars(path, bars, digits, ew=None):
    r = (lambda x: round(x, digits)) if digits else (lambda x: int(round(x)))
    obj = {'t': [b['time'] for b in bars], 'o': [r(b['open']) for b in bars], 'h': [r(b['high']) for b in bars],
           'l': [r(b['low']) for b in bars], 'c': [r(b['close']) for b in bars], 'v': [int(b['volume']) for b in bars]}
    if any('sr' in b for b in bars):
        obj['sr'] = [b.get('sr') for b in bars]
    if ew:
        obj['ew'] = ew
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(obj, f, separators=(',', ':'), ensure_ascii=False)


def agg(samples):
    """일일 검증 집계. 표본 [(구분,키,최근,f5,f20,날짜)] →
    {구분: {키: {all, rec, h1, h2, v}}}  v = 판정(유효/약함/역효과/보류):
    기간을 앞·뒤 절반으로 나눠 둘 다 기준 대비 20일 초과수익 +0.5%p 이상·적중률 +2%p 이상(표본 100 이상)이면 '유효',
    둘 다 반대 방향이면 '역효과', 그 외 '약함'. 매일 다시 계산 → 신호 표시(색)가 자동 조정됨."""
    if not samples:
        return {}
    dates = sorted({x[5] for x in samples})
    cut = dates[len(dates) // 2]
    acc = defaultdict(lambda: {'all': [], 'rec': [], 'h1': [], 'h2': []})
    for kind, key, rec, f5, f20, t in samples:
        d = acc[(kind, key)]
        d['all'].append((f5, f20)); d['h1' if t < cut else 'h2'].append((f5, f20))
        if rec:
            d['rec'].append((f5, f20))

    def st(v, key):
        if not v:
            return None
        n = len(v)
        bear = key in BEAR or key == '약세'
        hit = lambda i: sum(1 for x in v if (x[i] < 0 if bear else x[i] > 0)) / n * 100
        return {'n': n, 'f5': round(sum(x[0] for x in v) / n * 100, 2), 'f20': round(sum(x[1] for x in v) / n * 100, 2),
                'h5': round(hit(0), 1), 'h20': round(hit(1), 1)}
    out = defaultdict(dict)
    for (kind, key), d in acc.items():
        out[kind][key] = {k: st(d[k], key) for k in ('all', 'rec', 'h1', 'h2')}
    base = out.get('rg', {}).get('전체(기준)')
    for kind in out:
        for key, x in out[kind].items():
            if key == '전체(기준)' or not base:
                continue
            bear = key in BEAR or key == '약세'
            res = []
            for h in ('h1', 'h2'):
                s_, b_ = x[h], base[h]
                if not s_ or not b_ or s_['n'] < 100:
                    res.append(None); continue
                ex = (b_['f20'] - s_['f20']) if bear else (s_['f20'] - b_['f20'])
                hb = (100 - b_['h20']) if bear else b_['h20']
                res.append((ex, s_['h20'] - hb))
                x[h]['ex'], x[h]['hd'] = round(ex, 2), round(s_['h20'] - hb, 1)
            if None in res:
                x['v'] = '보류'
            elif all(e > .5 and h > 2 for e, h in res):
                x['v'] = '유효'
            elif all(e < -.5 and h < -2 for e, h in res):
                x['v'] = '역효과'
            else:
                x['v'] = '약함'
    out['cut'] = cut
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(HERE, 'site'))
    ap.add_argument('--limit', type=int, default=0, help='시험용: 시장별 종목 수 제한')
    ap.add_argument('--markets', default='KR,US')
    ap.add_argument('--days', type=int, default=730)
    ap.add_argument('--lstart', default='2000-01-01', help='엘리엇 주봉 등급(프라이머리·사이클)용 장기 시작일(고정 — 시작점에 따라 큰 등급 라벨이 바뀌지 않게, 국내는 자료원 한도 약 12년)')
    a = ap.parse_args()
    start = (dt.date.today() - dt.timedelta(days=a.days)).isoformat()
    global LSTART
    LSTART = a.lstart
    out = a.out
    if os.path.isdir(out):
        shutil.rmtree(out)
    shutil.copytree(os.path.join(HERE, 'web'), out)

    # 1) 주요 지표
    items = [{'id': f'IX:{k}', 'n': n, 'm': '지표', 's': g, 'g': g} for k, _, _, n, g in INDICES]
    bars = fetch_fdr([(f'IX:{k}', s) for k, src, s, _, _ in INDICES if src == 'fdr'], start, '지표(FDR)')
    bars.update(fetch_yf([(f'IX:{k}', s) for k, src, s, _, _ in INDICES if src == 'yf'], start, '지표(yf)', chunk=50))

    # 2) 종목
    for mk in a.markets.split(','):
        uni = kr_universe() if mk == 'KR' else us_universe()
        if a.limit:
            uni = uni[:a.limit] + [x for x in uni if x['m'] == 'ETF' or (x.get('nq') and x['n'][:1] in 'AB')][:a.limit]
        log(mk, '종목', len(uni))
        if mk == 'KR':
            bars.update(fetch_fdr([(it['id'], it['id'][3:]) for it in uni], start, 'KR'))
        else:
            bars.update(fetch_yf([(it['id'], it['id'][3:].replace('.', '-')) for it in uni], start, 'US', chunk=200))
            # 나스닥 추가분은 유동성 필터
            keep = []
            for it in uni:
                b = bars.get(it['id']) or []
                if it.get('nq'):
                    tv = sum(x['close'] * x['volume'] for x in b[-20:]) / 20 if len(b) >= 20 else 0
                    if tv < NQ_MIN_TV or not b or b[-1]['close'] < NQ_MIN_PX:
                        bars.pop(it['id'], None); continue
                keep.append(it)
            log('나스닥 유동성 필터 후', sum(1 for x in keep if x.get('nq')), '종목 추가')
            uni = keep
        items += uni

    # 2-1) 공매도 비중 → 일봉에 sr(%) 붙임 (미국 FINRA, 국내 KRX 자격 있을 때)
    shorts = {}
    us_ids = [it['id'] for it in items if it['id'].startswith('US:')]
    kr_ids = [it['id'] for it in items if it['id'].startswith('KR:')]
    if us_ids:
        shorts.update({'US:' + k: v for k, v in fetch_finra_short([i[3:] for i in us_ids]).items()})
    if kr_ids:
        shorts.update({'KR:' + k: v for k, v in fetch_krx_short([i[3:] for i in kr_ids]).items()})
    for i, m in shorts.items():
        for b in bars.get(i) or []:
            if b['time'] in m:
                b['sr'] = m[b['time']]

    # 3) 섹터지수 (ETF·지표 제외, 종목 2개 이상)
    groups = defaultdict(list)
    for it in items:
        if it['m'] not in ('ETF', '지표') and len(bars.get(it['id'], [])) > 60:
            groups[(it['id'][:2], it['s'])].append(it['id'])
    for n, ((mk, sname), ids) in enumerate(sorted(groups.items())):
        if len(ids) < 2:
            continue
        sid = f'SEC:{mk}{n}'
        bars[sid] = sector_index([bars[i] for i in ids])
        EW[sid] = elliott.analyze(bars[sid])
        items.append({'id': sid, 'n': f'[섹터지수] {sname}', 'm': f'{mk} 섹터', 's': sname, 'k': len(ids)})

    # 4) 요약·검증·쓰기
    kept, samples, quality = [], {'KR': [], 'US': []}, defaultdict(list)
    last_day = {}
    for it in items:
        b = bars.get(it['id']) or []
        mk, code = it['id'].split(':')
        sm, r = summary(b, 'KR' if mk == 'KR' else 'US') if b else (None, None)
        if not sm:
            if mk in ('KR', 'US'):
                quality['누락'].append(it['id'])
            continue
        fn = re.sub(r'[^A-Za-z0-9.\-]', '_', code)
        it['f'] = f'{mk}/{fn}'
        write_bars(os.path.join(out, 'data', 'p', mk, fn + '.json'), b, 0 if mk == 'KR' else 2, EW.get(it['id']))
        it.update(sm)
        it['wv'] = EW[it['id']]['cur'] if it['id'] in EW else []
        if mk == 'SEC':          # 섹터 순위 변동용: 1·5·20거래일 전 부호ADX (오늘 sa 와 같은 계산)
            L = len(b) - 1
            it['sah'] = [round(r['sgn'](L - k), 1) if L - k >= 0 and r['adx'][L - k] is not None else None for k in (1, 5, 20)]   # 등급별 현재 파동 [[등급, 표기, 시작일]] (큰 등급 먼저)
        if mk == 'IX':
            it['sp'] = [round(x['close'], 4) for x in b[-60:]]  # 홈 미니 차트
        if mk in ('KR', 'US') and it['m'] != 'ETF':
            samples[mk] += forward_stats(b, r)
            last_day[mk] = max(last_day.get(mk, ''), sm['d'])
        for f in sm['fl']:
            quality[f].append(it['id'])
        kept.append(it)
    # 기준일보다 오래된 종목(거래정지·데이터 지연)
    for it in kept:
        mk = it['id'][:2]
        if mk in last_day and it['d'] < last_day[mk]:
            it['fl'].append('지연'); quality['지연'].append(it['id'])

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes')
    with open(os.path.join(out, 'data', 'universe.json'), 'w') as f:
        json.dump({'updated': now, 'items': kept}, f, separators=(',', ':'), ensure_ascii=False)
    stock_n = {mk: sum(1 for it in items if it['id'].startswith(mk + ':')) for mk in ('KR', 'US')}
    val = {'updated': now, 'base': last_day,
           'quality': {k: {'n': len(v), 'ids': v[:40]} for k, v in quality.items()},
           'coverage': {mk: {'ok': sum(1 for it in kept if it['id'].startswith(mk + ':')), 'all': stock_n[mk]} for mk in stock_n},
           'stats': {mk: agg(s) for mk, s in samples.items()}}
    with open(os.path.join(out, 'data', 'validation.json'), 'w') as f:
        json.dump(val, f, separators=(',', ':'), ensure_ascii=False)
    log('완료', len(kept), '/', len(items), '→', out, '| 품질', {k: len(v) for k, v in quality.items()})
    miss = sum(stock_n.values()) - sum(v['ok'] for v in val['coverage'].values())
    if sum(stock_n.values()) and miss > sum(stock_n.values()) * .2:
        sys.exit('데이터 누락이 20%를 넘음 — 배포 중단')


if __name__ == '__main__':
    main()
