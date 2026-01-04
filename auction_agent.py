import requests
import pandas as pd
import time
from datetime import datetime

def run_task():
    # 1. 抓取今日竞价额 > 2000万的股票
    list_url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "5000", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fid": "f46", 
        "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23",
        "fields": "f12,f13,f14,f46"
    }
    
    resp = requests.get(list_url, params=params).json()
    df = pd.DataFrame(resp['data']['diff'])
    df['f46'] = pd.to_numeric(df['f46'], errors='coerce').fillna(0)
    df = df[df['f46'] >= 20000000].copy()
    
    if df.empty: return

    # 2. 计算量比
    results = []
    for _, row in df.iterrows():
        trend_url = f"https://push2.eastmoney.com/api/qt/stock/trends2/get?secid={row['f13']}.{row['f12']}&fields1=f1&fields2=f51,f56"
        trends = requests.get(trend_url).json()['data']['trends']
        auction_vals = [float(x.split(',')[1]) for x in trends if "09:30" in x]
        
        yesterday_val = auction_vals[-2] if len(auction_vals) >= 2 else None
        ratio = round(row['f46'] / yesterday_val, 2) if yesterday_val else "N/A"
        
        results.append({
            "代码": row['f12'], "名称": row['f14'],
            "今日竞价(万)": round(row['f46'] / 10000, 2),
            "昨日竞价(万)": round(yesterday_val / 10000, 2) if yesterday_val else "N/A",
            "竞昨量比": ratio
        })
        time.sleep(0.1)

    # 3. 保存结果
    result_df = pd.DataFrame(results).sort_values(by="竞昨量比", ascending=False, key=lambda x: pd.to_numeric(x, errors='coerce'))
    result_df.to_excel("daily_report.xlsx", index=False)
    print("Excel 报告已生成")

if __name__ == "__main__":
    run_task()
