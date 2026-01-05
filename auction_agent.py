import requests
import pandas as pd
import time
from datetime import datetime

def run_task():
    # 1. 获取名单 (依然用东财拿列表，因为它是全市场扫描最方便的)
    list_url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "400", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fid": "f6", "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23",
        "fields": "f12,f13,f14" 
    }
    
    try:
        stocks = requests.get(list_url, params=params).json()['data']['diff']
        results = []

        for s in stocks:
            secid = f"{s['f13']}.{s['f12']}"
            # 获取最近 5 天分时，包含今天
            trend_url = f"https://push2his.eastmoney.com/api/qt/stock/trends2/get?secid={secid}&fields1=f1&fields2=f51,f56&ndays=5"
            
            try:
                t_resp = requests.get(trend_url, timeout=4).json()
                trends = t_resp['data']['trends']
                
                # 核心逻辑：提取所有 09:30 的点
                # 这些点就是每一天的集合竞价额
                auction_data = [x.split(',') for x in trends if "09:30" in x]
                
                if len(auction_data) >= 2:
                    # 今日竞价 (如果是今天 9:30 以后跑，这就是今天的开盘额)
                    today_val = float(auction_data[-1][1])
                    # 昨日竞价 (上一个交易日的开盘额)
                    yesterday_val = float(auction_data[-2][1])
                    
                    if today_val >= 20000000: # 2000万门槛
                        ratio = round(today_val / yesterday_val, 2) if yesterday_val > 0 else 0
                        results.append({
                            "代码": s['f12'], "名称": s['f14'],
                            "今日竞价(万)": round(today_val / 10000, 2),
                            "昨日竞价(万)": round(yesterday_val / 10000, 2),
                            "竞昨量比": ratio
                        })
            except: continue
            time.sleep(0.05)

        # 保存结果
        if results:
            pd.DataFrame(results).sort_values(by="竞昨量比", ascending=False).to_excel("daily_report.xlsx", index=False)
            print(f"精准报告已生成，筛选出 {len(results)} 只。")
        else:
            print("未发现达标股。")

    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    run_task()
