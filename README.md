
# Brand Growth Diagnostic — v0.3

## 目標
真正做到：
**輸入品牌名稱 → 自動抓公開訊號 → 自動找競品 → 產出診斷與建議**

## v0.3 已完成
- 單一品牌名稱輸入
- 自動競品候選辨識
- Google Trends 12 個月趨勢
- Search Momentum
- Share of Search
- 通路公開訊號掃描
- 商品 / 價格公開訊號
- 行銷活動分類
- Consumer Voice 關鍵字
- Brand Growth Radar
- Growth Hypothesis
- Recommended Tests
- 可下載 HTML 診斷報告

## 本機執行
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 部署成真正網址
最簡單：Streamlit Community Cloud

1. 建立 GitHub repository，例如 `brand-growth-diagnostic`
2. 上傳本資料夾中的 `app.py` 與 `requirements.txt`
3. 到 Streamlit Community Cloud
4. New app → 選擇 repository → Main file 選 `app.py`
5. Deploy
6. 完成後會得到：
   `https://xxxx.streamlit.app`

## 為什麼目前仍稱 MVP
部分公開來源沒有免費、穩定、合法的正式 API，因此 v0.3 使用公開搜尋訊號與 Google Trends 的非官方 Python 套件。
結果適合：
- 品牌初步診斷
- 顧問研究起點
- 競品假設
- Proposal 前置研究

不應直接當成：
- 真實營收
- 真實媒體花費
- 真實通路 sell-through
- 精準市場份額

## 下一版 v0.4
推薦加入：
- 人工確認 / 修改競品
- 類別 Benchmark Database
- 品牌診斷專案儲存
- 正式 Similarweb API
- 可上傳內部營收 / 毛利 / CRM 資料
- External Signal vs Internal Data 交叉診斷
- PDF 顧問版型
