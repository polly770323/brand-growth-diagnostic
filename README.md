# Brand Growth Diagnostic v1.1 — 多品牌通路情報測試版

## 功能
- 任意輸入品牌名稱（台灣、日本、新加坡、香港、馬來西亞、美國）
- 多品牌測試：同一瀏覽器工作階段可切換已分析結果
- 通路相關公開頁面及可點擊網址（每通路最多 3 個）
- 候選競品與 Google Trends（可能受公開來源限制）
- 商品價格線索（**不當作驗證價格**）
- 可下載來源清單 CSV、通路證據 CSV、摘要 HTML
- 明確標示資料缺口，不把搜尋命中當作實際上架

## Streamlit Cloud 更新法（請先備份現有 app.py）
1. GitHub 開原本 `polly770323/brand-growth-diagnostic`。
2. 建議先用新分支 `v1.1-test`，不要直接覆蓋 `main`。在 GitHub 的分支下拉選單輸入分支名並建立。
3. 在該分支 `Add file` → `Upload files`，上傳這個 ZIP **解壓縮後**的 `app.py`、`requirements.txt`、`README.md`，確認允許取代舊檔並提交。
4. 打開 https://share.streamlit.io/ ，新增測試 app：Repository `polly770323/brand-growth-diagnostic`，Branch `v1.1-test`，Main file path `app.py`，App URL 取一個新名稱。
5. 測試正常後再把分支合併到 `main`；舊版網站會依部署狀態更新。

## 本機執行
`pip install -r requirements.txt`
`streamlit run app.py`

## 注意事項
- 不使用 API Key；公開搜尋可能被限流，導致部分品牌結果不完整。
- 對海外品牌的通路查詢仍以台灣網站為主；跨國平台覆蓋是待開發功能。
- 此版通路資訊是搜尋證據，不保證供貨、庫存、成交或門市鋪貨。
- Google Trends 是相對搜尋指數，不能代表銷售額。
- 現階段只做搜尋摘要中的價格線索，尚未做 SKU 標準化和跨平台同品比價。
- 分析結果只暫存於 Streamlit session，重新整理/伺服器重啟可能消失；尚未導入資料庫。
- 公開儲存庫不可放密碼、私密資料、公司非公開資訊。
