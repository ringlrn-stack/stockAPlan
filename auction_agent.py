import requests
import pandas as pd
import time
from datetime import datetime

def run_task():
    print(f"任务启动时间: {datetime.now()}")
    
    list_url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "50", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fid": "f6", # 改为按成交额排序，确保非交易日也能拿到数据
        "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23",
        "fields": "f12,f13,f14,f46,f6" 
    }
    
    try:
        resp = requests.get(list_url, params=params).json()
        stocks = resp['data']['diff']
        df = pd.DataFrame(stocks)
        
        # 将字符串转为数字
        df['f46'] = pd.to_numeric(df['f46'], errors='coerce').fillna(0)
        
        # 筛选逻辑：如果今天没开盘（f46全是0），我们就取成交额前5名演示
        df_filtered = df[df['f46'] >= 20000000].copy()
        
        if df_filtered.empty:
            print("注意：未找到竞价额 > 2000万的股票，切换至『演示模式』获取成交额前5名...")
            df_filtered = df.head(5).copy()

        results = []
        for _, row in df_filtered.iterrows():
            # 获取昨日数据逻辑
            trend_url = f"https://push2.eastmoney.com/api/qt/stock/trends2/get?secid={row['f13']}.{row['f12']}&fields1=f1&fields2=f51,f56"
            t_resp = requests.get(trend_url).json()
            
            yesterday_val = None
            if t_resp.get('data') and 'trends' in t_resp['data']:
                trends = t_resp['data']['trends']
                auction_vals = [float(x.split(',')[1]) for x in trends if "09:30" in x]
                if len(auction_vals) >= 2:
                    yesterday_val = auction_vals[-2]

            ratio = round(row['f46'] / yesterday_val, 2) if yesterday_val and yesterday_val > 0 else "N/A"
            
            results.append({
                "代码": row['f12'], 
                "名称": row['f14'],
                "今日竞价(万)": round(row['f46'] / 10000, 2),
                "昨日竞价(万)": round(yesterday_val / 10000, 2) if yesterday_val else "N/A",
                "竞昨量比": ratio
            })
            time.sleep(0.1)

        result_df = pd.DataFrame(results)
        # 强制保存为这个名字，与 .yml 保持一致
        result_df.to_excel("daily_report.xlsx", index=False)
        print(f"成功生成报告，包含 {len(result_df)} 行数据")

    except Exception as e:
        print(f"运行出错: {e}")

if __name__ == "__main__":
    run_task()
