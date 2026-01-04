import requests
import pandas as pd
import time
from datetime import datetime

def run_task():
    print(f"任务启动: {datetime.now()}")
    
    # 1. 获取全市场实时列表 (含今日竞价 f46)
    list_url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "5000", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23",
        "fields": "f12,f13,f14,f46"
    }
    
    resp = requests.get(list_url, params=params).json()
    stocks = resp['data']['diff']
    
    # 2. 筛选今日竞价额 > 2000万 的个股
    # (如果是周末测试，强制取前10只)
    valid_stocks = [s for s in stocks if s['f46'] != '-' and float(s['f46']) >= 20000000]
    if not valid_stocks:
        print("未发现达标股，进入测试模式取前10只...")
        valid_stocks = stocks[:10]

    results = []
    print(f"开始抓取历史对比数据，共 {len(valid_stocks)} 只...")

    for s in valid_stocks:
        # 直接请求该股最近 2 天的数据 (ndays=2)
        secid = f"{s['f13']}.{s['f12']}"
        trend_url = f"https://push2his.eastmoney.com/api/qt/stock/trends2/get?secid={secid}&fields1=f1&fields2=f51,f56&ndays=2"
        
        try:
            t_data = requests.get(trend_url).json()
            trends = t_data.get('data', {}).get('trends', [])
            
            # 过滤出每天开盘 09:30 的那一笔
            open_points = [float(x.split(',')[1]) for x in trends if "09:30" in x]
            
            # 今日竞价 (接口实时字段 f46)
            today_val = float(s['f46']) if s['f46'] != '-' else 0
            # 历史竞价 (取开盘序列中的倒数第二个，即昨日)
            yesterday_val = open_points[-2] if len(open_points) >= 2 else None
            
            ratio = round(today_val / yesterday_val, 2) if yesterday_val else "N/A"
            
            results.append({
                "代码": s['f12'], "名称": s['f14'],
                "今日竞价(万)": round(today_val / 10000, 2),
                "昨日竞价(万)": round(yesterday_val / 10000, 2) if yesterday_val else "N/A",
                "竞昨量比": ratio
            })
        except: pass
        time.sleep(0.05)

    # 3. 生成 Excel
    pd.DataFrame(results).to_excel("daily_report.xlsx", index=False)
    print("报告生成完毕")

if __name__ == "__main__":
    run_task()
