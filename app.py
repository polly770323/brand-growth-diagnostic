
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pytrends.request import TrendReq
from ddgs import DDGS
from urllib.parse import urlparse
import re, time, html, io

st.set_page_config(page_title="Brand Growth Diagnostic", page_icon="📊", layout="wide")

# ---------------------------
# UI
# ---------------------------
st.title("Brand Growth Diagnostic · v1.1")
st.caption("多品牌商業情報測試版｜公開來源・通路訊號・競品線索・可匯出資料")
st.info("研究用途：搜尋結果不等於實際上架；從網頁摘要擷取的數字不等於驗證售價。所有結論需回到原始來源覆核。")

brand = st.text_input("品牌名稱", placeholder="例如：老協珍、瓦城、雙月食品社").strip()
country = st.selectbox("主要市場", ["台灣", "日本", "新加坡", "香港", "馬來西亞", "美國"], index=0)
run = st.button("開始品牌診斷", type="primary", disabled=not brand)

GEO = {"台灣":"TW","日本":"JP","新加坡":"SG","香港":"HK","馬來西亞":"MY","美國":"US"}

# ---------------------------
# Helpers
# ---------------------------
def clamp(x, lo=0, hi=100):
    try:
        return max(lo, min(hi, float(x)))
    except:
        return 0.0

def normalize(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

@st.cache_data(ttl=3600, show_spinner=False)
def search_web(query, max_results=8):
    out=[]
    err=None
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                out.append({
                    "title": normalize(r.get("title","")),
                    "href": r.get("href",""),
                    "body": normalize(r.get("body",""))
                })
    except Exception as e:
        err=str(e)
    return out, err

def hostname(url):
    try:
        return urlparse(url).netloc.lower().replace("www.","")
    except:
        return ""

def likely_official_urls(results, brand):
    b = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+","",brand.lower())
    candidates=[]
    social_domains=("facebook.com","instagram.com","linkedin.com","youtube.com","wikipedia.org")
    for r in results:
        d=hostname(r["href"])
        if not d or any(x in d for x in social_domains):
            continue
        score=0
        dd=re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+","",d)
        if b and b[:4] in dd:
            score += 4
        if any(k in r["title"].lower() for k in ["官方","official","官網"]):
            score += 2
        if score:
            candidates.append((score,r["href"],r["title"]))
    candidates.sort(reverse=True)
    return candidates[:3]

def extract_brand_candidates(results, target):
    # MVP heuristic: infer possible competitor brand names from result titles/snippets.
    stop = {
        target, "台灣","品牌","推薦","評價","十大","排名","比較","開箱","官網","官方",
        "Facebook","Instagram","YouTube","PChome","momo","蝦皮","Costco","全家","7-ELEVEN",
        "博客來","Dcard","PTT","Threads","Yahoo","Mobile01"
    }
    text=" ".join([r["title"]+" "+r["body"] for r in results])
    chunks=re.split(r"[｜|、,，／/：:\-\(\)（）\[\]【】]", text)
    scores={}
    for c in chunks:
        c=normalize(c)
        if not (2 <= len(c) <= 16):
            continue
        if c in stop or target in c:
            continue
        if re.search(r"https?://|\d{4}|推薦|評價|品牌|比較|開箱|官網|文章|新聞|優惠|價格", c):
            continue
        if re.search(r"[A-Za-z\u4e00-\u9fff]", c):
            scores[c]=scores.get(c,0)+1
    # remove sentence-like candidates
    ranked=[k for k,v in sorted(scores.items(), key=lambda kv:(-kv[1], len(kv[0]))) if v>=1]
    dedup=[]
    for x in ranked:
        if any(x in y or y in x for y in dedup):
            continue
        dedup.append(x)
        if len(dedup)>=4:
            break
    return dedup

def discover_competitors(brand, country):
    queries = [
        f'"{brand}" 競品 同類 品牌 {country}',
        f'"{brand}" 比較 推薦 品牌 {country}',
        f'"{brand}" vs 品牌 {country}'
    ]
    merged=[]
    for q in queries:
        rs,_=search_web(q,10)
        merged += rs
    cands = extract_brand_candidates(merged, brand)
    return cands, merged[:20]

@st.cache_data(ttl=3600, show_spinner=False)
def trends_data(keywords, geo):
    try:
        pt=TrendReq(hl="zh-TW", tz=480, timeout=(10,30), retries=1, backoff_factor=0.4)
        pt.build_payload(keywords[:5], timeframe="today 12-m", geo=geo)
        df=pt.interest_over_time()
        if df is None or df.empty:
            return None, "無 Google Trends 資料"
        if "isPartial" in df.columns:
            df=df.drop(columns=["isPartial"])
        return df, None
    except Exception as e:
        return None, str(e)

def trend_metrics(df, brand, keys):
    if df is None or brand not in df.columns:
        return 0, 0, 50
    s=df[brand].astype(float)
    n=len(s)
    recent=s.tail(min(13,n)).mean()
    prior=s.iloc[max(0,n-26):max(0,n-13)].mean() if n>=14 else s.head(max(1,n//2)).mean()
    growth=0 if prior==0 else (recent-prior)/prior*100
    denom=sum(float(df[k].mean()) for k in keys if k in df.columns)
    sos=0 if denom==0 else float(df[brand].mean())/denom*100
    score=clamp(50 + growth*1.4 + sos*0.35)
    return growth, sos, score

def channel_check(brand, country):
    channels = {
        "品牌官網": f'"{brand}" 官方 官網',
        "蝦皮": f'site:shopee.tw "{brand}"',
        "momo": f'site:momoshop.com.tw "{brand}"',
        "PChome": f'site:pchome.com.tw "{brand}"',
        "7-ELEVEN": f'"{brand}" 7-ELEVEN 台灣',
        "全家": f'"{brand}" 全家 FamilyMart',
        "Costco": f'"{brand}" Costco 台灣',
        "百貨 / 商場": f'"{brand}" 百貨 專櫃',
        "機場 / Travel Retail": f'"{brand}" 機場 免稅 昇恆昌',
        "海外市場": f'"{brand}" overseas distributor export {country}',
    }
    rows=[]
    for name,q in channels.items():
        rs,_=search_web(q,4)
        found=len(rs)>0
        rows.append({
            "Channel":name,
            "Signal":found,
            "Evidence": rs[0]["title"] if found else "",
            "URL": rs[0]["href"] if found else ""
        })
        time.sleep(.08)
    return pd.DataFrame(rows)

def product_price_signals(brand):
    queries=[
        f'"{brand}" 商品 價格',
        f'"{brand}" 禮盒 價格',
        f'"{brand}" momo 蝦皮 價格',
    ]
    merged=[]
    for q in queries:
        rs,_=search_web(q,10)
        merged += rs
    # Extract NTD-like numbers from snippets/titles.
    vals=[]
    evidence=[]
    for r in merged:
        txt=r["title"]+" "+r["body"]
        nums=re.findall(r'(?:NT\$|NTD|\$|售價|價格|優惠價)?\s*([1-9]\d{1,4})(?:\s*元)?', txt, re.I)
        local=[]
        for n in nums:
            try:
                v=int(n)
                if 30 <= v <= 20000:
                    vals.append(v); local.append(v)
            except: pass
        if local:
            evidence.append({"Title":r["title"],"URL":r["href"],"Prices":", ".join(map(str,local[:4]))})
    vals=sorted(vals)
    stats={}
    if vals:
        stats={
            "min":min(vals),
            "median":int(np.median(vals)),
            "max":max(vals),
            "count":len(vals)
        }
    return stats, pd.DataFrame(evidence[:12]), merged

def marketing_signals(brand):
    qs=[
        f'"{brand}" 新品',
        f'"{brand}" 聯名',
        f'"{brand}" 優惠 活動',
        f'"{brand}" KOL 開箱',
        f'"{brand}" 廣告',
    ]
    merged=[]
    for q in qs:
        rs,_=search_web(q,6)
        merged+=rs
    blob=" ".join(r["title"]+" "+r["body"] for r in merged)
    taxonomy = {
        "新品": ["新品","推出","上市","新口味"],
        "聯名": ["聯名","合作"],
        "促銷": ["優惠","折扣","買一送一","滿額","特價"],
        "KOL / UGC": ["KOL","網紅","開箱","實測","推薦"],
        "品牌形象": ["品牌","故事","理念","永續"],
        "通路": ["全家","7-ELEVEN","Costco","momo","蝦皮","百貨"]
    }
    counts={}
    for label,words in taxonomy.items():
        counts[label]=sum(blob.count(w) for w in words)
    score=clamp(35 + min(len(merged),20)*2 + min(sum(counts.values()),30))
    return counts, score, merged[:15]

def consumer_voice(brand):
    qs=[
        f'"{brand}" 評價',
        f'"{brand}" 推薦 回購',
        f'"{brand}" 負評 問題',
        f'"{brand}" Dcard OR PTT OR Threads',
    ]
    merged=[]
    for q in qs:
        rs,_=search_web(q,10)
        merged += rs
    blob=" ".join(r["title"]+" "+r["body"] for r in merged)
    positive=["推薦","回購","好吃","好喝","方便","喜歡","值得","質感","滿意","好用"]
    negative=["太貴","失望","難吃","不好","客訴","破損","等很久","負評","問題","雷"]
    pc={w:blob.count(w) for w in positive}
    nc={w:blob.count(w) for w in negative}
    p=sum(pc.values()); n=sum(nc.values())
    total=p+n
    score=50 if total==0 else clamp(50+(p-n)/max(total,1)*35)
    return score, pc, nc, merged[:15]

def score_product(price_stats, product_results):
    base=40
    if price_stats:
        base += 18
        spread=price_stats["max"]-price_stats["min"]
        if spread>500: base += 10
    base += min(len(product_results),15)*2
    return clamp(base)

def score_digital(general, official):
    return clamp(35 + min(len(general),10)*3 + (20 if official else 0))

def diagnosis(scores, growth):
    hs=[]; tests=[]
    if scores["Demand"]>=60 and scores["Channel"]<55:
        hs.append(("Distribution", "需求訊號不弱，但公開通路覆蓋相對有限；成長瓶頸可能更接近 Distribution，而非 Awareness。"))
        tests.append("選 1 個新通路做 6–8 週測試，追蹤 sell-through、毛利、回購與新客占比。")
    if scores["Demand"]<45:
        hs.append(("Awareness", "搜尋動能偏弱，可能需要先建立品牌需求或品類教育。"))
        tests.append("用 2–3 種訴求做小額 campaign，觀察品牌字搜尋與直接流量是否提升。")
    if scores["Marketing"]>=65 and growth<0:
        hs.append(("Marketing Efficiency", "公開行銷活動不低，但搜尋動能沒有同步成長，需檢查訊息是否帶來增量需求。"))
        tests.append("把素材拆成品牌／功能／促銷／UGC，對照各波段的搜尋與導流變化。")
    if scores["Consumer Voice"]<50:
        hs.append(("Experience / Retention", "公開口碑訊號偏弱；產品、價格、服務或物流可能影響推薦與重購。"))
        tests.append("將負向評論分群並計數，先修正『高頻×高影響』問題。")
    if scores["Product"]<50:
        hs.append(("Product Architecture", "公開商品與價格訊號不足，可能存在 Hero SKU、價格階梯或商品角色不清楚的問題。"))
        tests.append("整理 Entry / Core / Premium 商品階梯，確認每一層的客群與任務。")
    if not hs:
        weakest=min(scores, key=scores.get)
        hs.append(("Opportunity", f"目前沒有單一明顯短板；相對弱項是 {weakest}，適合從競品差距與成長白地切入。"))
        tests.append(f"針對 {weakest} 設計一個 30 天可量化實驗，先驗證再擴大投資。")
    return hs, tests

def radar(scores):
    labels=list(scores.keys()); vals=list(scores.values())
    angles=np.linspace(0,2*np.pi,len(labels),endpoint=False).tolist()
    vals2=vals+vals[:1]; angles2=angles+angles[:1]
    fig=plt.figure(figsize=(5.8,5.8))
    ax=plt.subplot(111,polar=True)
    ax.plot(angles2,vals2,linewidth=2)
    ax.fill(angles2,vals2,alpha=.15)
    ax.set_xticks(angles); ax.set_xticklabels(labels)
    ax.set_yticks([20,40,60,80,100]); ax.set_ylim(0,100)
    return fig

def build_html_report(brand, country, competitors, scores, growth, sos, hypotheses, tests, channels, price_stats, marketing_counts, pos, neg, source_rows):
    def li(items):
        return "".join(f"<li>{html.escape(str(x))}</li>" for x in items)
    score_rows="".join(f"<tr><td>{html.escape(k)}</td><td>{v:.1f}/100</td></tr>" for k,v in scores.items())
    hyp_rows="".join(f"<li><b>{html.escape(t)}</b> — {html.escape(d)}</li>" for t,d in hypotheses)
    ch_rows="".join(
        f"<tr><td>{html.escape(str(r.Channel))}</td><td>{'Yes' if r.Signal else 'No'}</td><td>{html.escape(str(r.Evidence))}</td></tr>"
        for _,r in channels.iterrows()
    )
    src_rows="".join(f"<li>{html.escape(x['title'])} — {html.escape(x['url'])}</li>" for x in source_rows[:15])
    return f"""<!doctype html><html><head><meta charset="utf-8">
    <title>{html.escape(brand)} Brand Growth Diagnostic</title>
    <style>
    body{{font-family:Arial,'Noto Sans TC',sans-serif;max-width:980px;margin:40px auto;padding:0 24px;color:#222;line-height:1.6}}
    h1,h2{{margin-top:30px}} table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #ddd;padding:8px;text-align:left}}
    .note{{background:#f5f5f5;padding:14px;border-radius:8px}} .metric{{font-size:20px;font-weight:700}}
    </style></head><body>
    <h1>{html.escape(brand)} — Brand Growth Diagnostic</h1>
    <p>Market: {html.escape(country)} | Auto-discovered competitors: {html.escape(", ".join(competitors) if competitors else "None")}</p>
    <div class="note">公開資料只能作為方向訊號；正式策略仍需品牌內部營收、毛利、轉換、媒體投入與 sell-through 驗證。</div>
    <h2>Key Metrics</h2>
    <p class="metric">Search Momentum: {growth:+.1f}%　|　Share of Search: {sos:.1f}%</p>
    <table><tr><th>Dimension</th><th>Score</th></tr>{score_rows}</table>
    <h2>Growth Hypotheses</h2><ul>{hyp_rows}</ul>
    <h2>Recommended Tests</h2><ul>{li(tests)}</ul>
    <h2>Channel Signals</h2><table><tr><th>Channel</th><th>Signal</th><th>Evidence</th></tr>{ch_rows}</table>
    <h2>Price Signals</h2><p>{html.escape(str(price_stats) if price_stats else "No reliable price sample detected.")}</p>
    <h2>Marketing Signals</h2><p>{html.escape(str(marketing_counts))}</p>
    <h2>Consumer Voice Keywords</h2>
    <p>Positive: {html.escape(str(pos))}</p><p>Negative: {html.escape(str(neg))}</p>
    <h2>Source Samples</h2><ul>{src_rows}</ul>
    </body></html>"""

# ---------------------------
# v1.1: record multiple brand runs in session memory
# ---------------------------
from datetime import datetime, timezone, timedelta

if "diagnostic_records" not in st.session_state:
    st.session_state.diagnostic_records = {}

# Channels: signals only; never treat an unvalidated search hit as confirmed listing.
def channel_evidence_v11(brand, country):
    channels = {
        "品牌官網": f'"{brand}" 官方 官網',
        "蝦皮": f'site:shopee.tw "{brand}" 商品',
        "momo": f'site:momoshop.com.tw "{brand}" 商品',
        "PChome": f'site:pchome.com.tw "{brand}" 商品',
        "家樂福線上": f'site:carrefour.com.tw "{brand}"',
        "7-ELEVEN": f'"{brand}" 7-ELEVEN 商品',
        "全家": f'"{brand}" 全家 便利商店 商品',
        "Costco": f'"{brand}" Costco 台灣',
        "百貨 / 商場": f'"{brand}" 百貨 專櫃',
        "機場 / Travel Retail": f'"{brand}" 機場 免稅',
    }
    # Stronger topical filtering to reduce false-positive matched sites.
    expected_domains = {
        "蝦皮": ["shopee.tw"], "momo": ["momoshop.com.tw"],
        "PChome": ["pchome.com.tw"], "家樂福線上": ["carrefour.com.tw"],
        "Costco": ["costco.com.tw"],
    }
    result = []
    for channel, query in channels.items():
        hits, err = search_web(query, 6)
        valid=[]
        for h in hits:
            combined = (h.get("title", "") + " " + h.get("body", "")).lower()
            has_brand = brand.lower() in combined
            domains = expected_domains.get(channel)
            on_expected_site = (not domains) or any(d in hostname(h.get("href", "")) for d in domains)
            if has_brand and on_expected_site and h.get("href", "").startswith("http"):
                valid.append(h)
        for h in valid[:3]:
            result.append({"通路":channel,"搜尋狀態":"發現相關公開頁面（待覆核）", "標題":h["title"],"來源網址":h["href"],"摘要":h["body"][:200]})
        if not valid:
            result.append({"通路":channel,"搜尋狀態":"未找到可用證據" if not err else "搜尋發生錯誤", "標題":"","來源網址":"","摘要":(err or "")[:160]})
    return pd.DataFrame(result)

if run:
    geo=GEO[country]
    progress=st.progress(0, text="搜尋品牌與公開資料…")
    general, general_err=search_web(f'"{brand}" 品牌 商品 {country}',12)
    official=likely_official_urls(general,brand)
    progress.progress(15, text="尋找候選競品…")
    competitors, competitor_sources=discover_competitors(brand,country)
    progress.progress(28, text="讀取公開搜尋趨勢…")
    trend_keys=[brand]+competitors[:4]
    trend_df,trend_err=trends_data(trend_keys,geo)
    growth,sos,demand_score=trend_metrics(trend_df,brand,trend_keys)
    progress.progress(45, text="蒐集通路來源…")
    evidence=channel_evidence_v11(brand,country)
    signals=evidence.groupby("通路")["來源網址"].apply(lambda c:any(bool(x) for x in c)).to_dict()
    # For compatibility with old report, do NOT interpret this as channel coverage.
    channels=pd.DataFrame([{"Channel":k,"Signal":v,"Evidence":"需人工確認","URL":""} for k,v in signals.items()])
    progress.progress(62, text="蒐集商品與市場訊號…")
    price_stats,price_evidence,product_results=product_price_signals(brand)
    marketing_counts,marketing_score,marketing_sources=marketing_signals(brand)
    progress.progress(80, text="蒐集口碑訊號…")
    voice_score,pos_kw,neg_kw,voice_sources=consumer_voice(brand)
    scores={"Demand":round(demand_score,1),"Digital":round(score_digital(general,official),1),
            "Marketing":round(marketing_score,1),"Product":round(score_product(price_stats,product_results),1),
            "Consumer Voice":round(voice_score,1)}
    hypotheses,tests=diagnosis(scores,growth)
    sources=[]; seen=set()
    for r in general+competitor_sources+marketing_sources+voice_sources+product_results:
        u=r.get("href","")
        if u.startswith("http") and u not in seen:
            seen.add(u); sources.append({"標題":r["title"],"來源網址":u,"摘要":r["body"][:220]})
    for u in evidence["來源網址"].dropna().tolist():
        if u and u not in seen:
            seen.add(u); sources.append({"標題":"通路搜尋來源","來源網址":u,"摘要":""})
    record={"brand":brand,"country":country,"time":datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M +08:00"),
            "general_err":general_err,"trend_df":trend_df,"trend_err":trend_err,"growth":growth,"sos":sos,
            "competitors":competitors,"evidence":evidence,"price_stats":price_stats,"price_evidence":price_evidence,
            "marketing_counts":marketing_counts,"scores":scores,"hypotheses":hypotheses,"tests":tests,
            "pos_kw":pos_kw,"neg_kw":neg_kw,"sources":sources,"channels":channels}
    st.session_state.diagnostic_records[f"{brand}｜{country}"]=record
    st.session_state.selected_diagnostic=f"{brand}｜{country}"
    progress.progress(100, text="分析完成")
    progress.empty()

records=st.session_state.diagnostic_records
if records:
    st.divider()
    st.subheader("品牌情報工作台")
    keys=list(records.keys())
    selected=st.selectbox("選擇本次工作階段的品牌結果",keys,index=keys.index(st.session_state.get("selected_diagnostic",keys[-1])) if st.session_state.get("selected_diagnostic") in keys else len(keys)-1)
    r=records[selected]
    st.caption(f"分析時間：{r['time']}｜市場：{r['country']}｜同一工作階段已分析 {len(records)} 個品牌（伺服器重啟後不保留）")
    status_count=r["evidence"].groupby("通路")["來源網址"].apply(lambda x:any(bool(u) for u in x)).sum()
    m1,m2,m3=st.columns(3)
    m1.metric("有相關網頁的通路類別",int(status_count))
    m2.metric("蒐集到的引用來源",len(r["sources"]))
    m3.metric("候選競品（未確認）",len(r["competitors"]))
    st.caption("上述為本次搜尋樣本數量，不代表實際上架通路總數、銷售據點數或市場占有率。")

    t1,t2,t3,t4,t5=st.tabs(["通路情報","競品與趨勢","商品價格線索","策略與口碑","來源與下載"])
    with t1:
        st.markdown("#### 通路搜尋證據")
        st.dataframe(r["evidence"],hide_index=True,use_container_width=True,
          column_config={"來源網址":st.column_config.LinkColumn("來源網址")})
        st.caption("搜尋到頁面只表示有品牌相關內容，必須點入確認是否為該通路實際販售、是否仍有效。『未找到』不等於未上架。")
        st.download_button("下載通路情報 CSV",r["evidence"].to_csv(index=False).encode("utf-8-sig"),
                           file_name="channel_evidence.csv",mime="text/csv")
    with t2:
        st.markdown("#### 自動抽取的候選競品")
        st.write("、".join(r["competitors"]) if r["competitors"] else "未找到足夠候選競品")
        st.warning("候選競品是關鍵字抽取結果，可能包含非品牌詞，正式比較前必須人工覆核。")
        if r["trend_df"] is not None:
            st.line_chart(r["trend_df"])
            st.caption("Google Trends 為相對搜尋熱度，不代表銷售額或絕對市場規模。")
        else:
            st.info("Google Trends 本次無法取得；不以缺失資料推估趨勢。")
    with t3:
        st.markdown("#### 商品與價格線索（非已驗證比價）")
        st.warning("搜尋摘要中的數字可能是規格、數量、年份或活動價格。沒有 SKU 核對前，不提供跨通路價差結論。")
        if not r["price_evidence"].empty:
            st.dataframe(r["price_evidence"],hide_index=True,use_container_width=True,column_config={"URL":st.column_config.LinkColumn("URL")})
        else:
            st.info("本次沒有足夠價格線索。")
    with t4:
        st.markdown("#### 探索性策略假設")
        for title,desc in r["hypotheses"]:
            st.markdown(f"**{title}** — {desc}")
        st.markdown("#### 建議驗證方式")
        for t in r["tests"]:st.write("• "+t)
        st.caption("所有建議都是待測試假設；需再補毛利、物流、消費者調查與通路條件。")
        c1,c2=st.columns(2)
        with c1:st.write("正向提及詞（搜尋樣本）：",r["pos_kw"])
        with c2:st.write("負向提及詞（搜尋樣本）：",r["neg_kw"])
    with t5:
        st.markdown("#### 可追溯資料來源")
        df=pd.DataFrame(r["sources"])
        if not df.empty:st.dataframe(df,hide_index=True,use_container_width=True,column_config={"來源網址":st.column_config.LinkColumn("來源網址")})
        else:st.warning("未取得來源。請檢查網路、搜尋限制或品牌關鍵字。")
        st.download_button("下載來源清單 CSV",df.to_csv(index=False).encode("utf-8-sig"),file_name="sources.csv",mime="text/csv")
        safe_name=re.sub(r'[^A-Za-z0-9\u4e00-\u9fff]+','_',r['brand'])
        report=build_html_report(r["brand"],r["country"],r["competitors"],r["scores"],r["growth"],r["sos"],
                   r["hypotheses"],r["tests"],r["channels"],{},r["marketing_counts"],r["pos_kw"],r["neg_kw"],
                   [{"title":s["標題"],"url":s["來源網址"]} for s in r["sources"]])
        st.download_button("下載診斷摘要 HTML",report,file_name=f"{safe_name}_diagnostic.html",mime="text/html")
    if len(records)>1:
        st.markdown("#### 本次多品牌對照（僅供搜尋覆蓋度比較）")
        summary=[]
        for x in records.values():
            count=x["evidence"].groupby("通路")["來源網址"].apply(lambda y:any(bool(u) for u in y)).sum()
            summary.append({"品牌":x["brand"],"市場":x["country"],"相關通路類別數":int(count),"引用來源數":len(x["sources"]),"候選競品數":len(x["competitors"])})
        st.dataframe(pd.DataFrame(summary),hide_index=True,use_container_width=True)
        st.caption("不同品牌有不同搜尋熱度與來源可見性，數字不能直接當作商業實力排名。")
