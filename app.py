
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
st.title("Brand Growth Diagnostic")
st.caption("輸入一個品牌名稱，自動整理公開訊號、競品、搜尋趨勢、通路、價格、口碑與成長假設。")
st.info("這是一套『公開訊號決策輔助工具』，不把外部估算當成品牌內部真實營收或轉換資料。")

brand = st.text_input("品牌名稱", placeholder="例如：雙月食品社")
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
# Main run
# ---------------------------
if run:
    geo=GEO[country]
    progress=st.progress(0, text="建立品牌基本輪廓…")

    general, general_err=search_web(f'"{brand}" 品牌 商品 {country}',12)
    official=likely_official_urls(general,brand)
    progress.progress(12, text="自動尋找競品…")

    competitors, competitor_sources=discover_competitors(brand,country)
    if not competitors:
        st.warning("自動競品辨識不足，本次仍會完成單品牌診斷；之後可加入人工校正功能。")
    progress.progress(24, text="讀取 Google Trends…")

    trend_keys=[brand]+competitors[:4]
    trend_df,trend_err=trends_data(trend_keys,geo)
    growth,sos,demand_score=trend_metrics(trend_df,brand,trend_keys)
    progress.progress(40, text="掃描公開通路…")

    channels=channel_check(brand,country)
    channel_score=clamp(channels["Signal"].mean()*100 if len(channels) else 0)
    progress.progress(55, text="整理商品與價格訊號…")

    price_stats,price_evidence,product_results=product_price_signals(brand)
    product_score=score_product(price_stats,product_results)
    progress.progress(68, text="分析近期行銷活動…")

    marketing_counts,marketing_score,marketing_sources=marketing_signals(brand)
    progress.progress(80, text="整理消費者口碑訊號…")

    voice_score,pos_kw,neg_kw,voice_sources=consumer_voice(brand)
    digital_score=score_digital(general,official)
    progress.progress(92, text="建立成長假設與建議…")

    scores={
        "Demand":round(demand_score,1),
        "Digital":round(digital_score,1),
        "Marketing":round(marketing_score,1),
        "Product":round(product_score,1),
        "Channel":round(channel_score,1),
        "Consumer Voice":round(voice_score,1),
    }
    hypotheses,tests=diagnosis(scores,growth)

    all_sources=[]
    seen=set()
    for r in general+competitor_sources+marketing_sources+voice_sources+product_results:
        if r["href"] and r["href"] not in seen:
            seen.add(r["href"])
            all_sources.append({"title":r["title"],"url":r["href"],"snippet":r["body"][:220]})
    progress.progress(100, text="完成")
    time.sleep(.2)
    progress.empty()

    st.success(f"{brand} 診斷完成")

    # Header metrics
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Search Momentum", f"{growth:+.1f}%")
    c2.metric("Share of Search", f"{sos:.1f}%")
    c3.metric("Channel Coverage", f"{channel_score:.0f}%")
    c4.metric("Consumer Voice", f"{voice_score:.0f}/100")

    st.markdown("### 自動辨識競品")
    st.write("、".join(competitors) if competitors else "本次未可靠辨識競品")

    left,right=st.columns([1,1])
    with left:
        st.pyplot(radar(scores))
    with right:
        st.markdown("### Brand Growth Radar")
        st.dataframe(pd.DataFrame({"Dimension":scores.keys(),"Score":scores.values()}),
                     hide_index=True,use_container_width=True)

    if trend_df is not None:
        st.markdown("### Demand / Search Trend")
        st.line_chart(trend_df)
    elif trend_err:
        st.info("Google Trends 暫時無法取得；其他模組仍可使用。")

    st.markdown("### Growth Hypotheses")
    for title,desc in hypotheses:
        st.write(f"**{title}** — {desc}")

    st.markdown("### Recommended Tests")
    for x in tests:
        st.write("• "+x)

    tab1,tab2,tab3,tab4,tab5=st.tabs(["Channel","Product & Price","Marketing","Consumer Voice","Sources"])

    with tab1:
        show=channels.copy()
        show["Signal"]=show["Signal"].map({True:"有公開訊號",False:"未找到明顯訊號"})
        st.dataframe(show[["Channel","Signal","Evidence","URL"]],hide_index=True,use_container_width=True)

    with tab2:
        if price_stats:
            p1,p2,p3=st.columns(3)
            p1.metric("Detected Min", f"NT${price_stats['min']:,}")
            p2.metric("Detected Median", f"NT${price_stats['median']:,}")
            p3.metric("Detected Max", f"NT${price_stats['max']:,}")
            st.caption("價格由公開搜尋片段自動抽取，可能含組合價、促銷價或非商品數字，應人工覆核。")
        else:
            st.write("本次未取得足夠價格樣本。")
        if not price_evidence.empty:
            st.dataframe(price_evidence,hide_index=True,use_container_width=True)

    with tab3:
        st.dataframe(pd.DataFrame({"Signal":marketing_counts.keys(),"Mentions":marketing_counts.values()}),
                     hide_index=True,use_container_width=True)

    with tab4:
        pcols=[(k,v) for k,v in pos_kw.items() if v>0]
        ncols=[(k,v) for k,v in neg_kw.items() if v>0]
        st.write("**正向詞：** "+("、".join(f"{k}({v})" for k,v in pcols) if pcols else "未辨識"))
        st.write("**負向詞：** "+("、".join(f"{k}({v})" for k,v in ncols) if ncols else "未辨識"))

    with tab5:
        st.dataframe(pd.DataFrame(all_sources[:30]),hide_index=True,use_container_width=True)

    report=build_html_report(
        brand,country,competitors,scores,growth,sos,hypotheses,tests,
        channels,price_stats,marketing_counts,pos_kw,neg_kw,all_sources
    )
    st.download_button(
        "下載品牌診斷報告（HTML）",
        data=report,
        file_name=f"{re.sub(r'[^A-Za-z0-9\u4e00-\u9fff]+','_',brand)}_brand_diagnostic.html",
        mime="text/html"
    )

    st.caption("下一階段可加入：登入 / 專案儲存、品牌資料庫、人工校正競品、正式 Similarweb API、Meta/TikTok 合規資料接口、PDF 顧問版型。")
