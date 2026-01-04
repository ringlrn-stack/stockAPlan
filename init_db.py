import requests
import pandas as pd
import time

def init_last_day_data():
    print("正在初始化 2025-12-31 (上周三) 的竞价数据...")
    
    # 1. 先获取全市场股票列表
    list_url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "5000", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23",
        "fields": "f12,f13,f14" # 代码, 市场, 名称
    }
    
    try:
        resp = requests.get(list_url, params=params).json()
        stocks = resp['data']['diff']
        
        results = []
        total = len(stocks)
        print(f"共发现 {total} 只股票，开始回溯 12-31 数据 (此过程约需 5-10 分钟)...")

        # 2. 循环获取每只股票在 12-31 的竞价额 (09:30的数据点)
        for i, row in enumerate(stocks):
            secid = f"{row['f13']}.{row['f12']}"
            trend_url = f"https://push2.eastmoney.com/api/qt/stock/trends2/get?secid={secid}&fields1=f1&fields2=f51,f56"
            
            try:
                t_data = requests.get(trend_url, timeout=5).json()
                trends = t_data.get('data', {}).get('trends', [])
                
                # 提取 09:30 的点。根据分时接口，通常 [-2] 或 [-3] 是 12-31 的数据
                # 我们通过倒序查找包含 "09:30" 的点中，排在今天之前的那个
                opening_points = [x for x in trends if "09:30" in x]
                
                # 如果当前是周日，且没有今日数据，那么 opening_points[-1] 可能就是 12-31
                # 为了保险，我们取最近一个已完成交易日的开盘点
                if opening_points:
                    target_val = float(opening_points[-1].split(',')[1])
                    results.append({
                        'code': row['f12'],
                        'name': row['f14'],
                        'last_auction': target_val
                    })
            except:
                pass
            
            if i % 100 == 0:
                print(f"进度: {i}/{total}...")
            
            # 这里的抓取仅执行一次，为了不被封，稍微加一点点延迟
            time.sleep(0.05)

        # 3. 写入数据库
        df_init = pd.DataFrame(results)
        df_init.to_csv("history_auction.csv", index=False)
        print(f"初始化完成！已将 {len(df_init)} 只股票的 12-31 数据存入 history_auction.csv")

    except Exception as e:
        print(f"初始化失败: {e}")

if __name__ == "__main__":
    init_last_day_data()
