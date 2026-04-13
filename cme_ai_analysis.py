import os
import yfinance as yf
from datetime import datetime, timedelta
import requests
from google import genai
from google.genai import types

# --- 环境变量配置 ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}", 
    "Content-Type": "application/json", 
    "Notion-Version": "2022-06-28"
}

def call_gemini_sdk_consolidated(full_prompt):
    """使用最新的 Google GenAI SDK 一次性发送请求"""
    
    # 1. 初始化官方 Client
    client = genai.Client(api_key=GOOGLE_API_KEY)
    
    # 2. 填入你刚才查到的准确模型代号
    model_id = "gemini-3-flash-preview" 
    
    try:
        print(f"🚀 正在调用官方 SDK 发送请求至 {model_id}...")
        
        # 3. 发起请求 (官方 SDK 内部对网络波动有更好的容错处理)
        response = client.models.generate_content(
            model=model_id,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                temperature=0.2, # 宏观数据研判，温度设低一点，让结论更严谨客观
                # thinking_config=types.ThinkingConfig(thinking_level="HIGH") # 可选：开启深度思考以获得更深度的博弈推演
            )
        )
        return response.text
        
    except Exception as e:
        print(f"❌ AI 模型请求彻底失败: {e}")
        return None

def run_analysis():
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Copper": "HG=F"}
    
    market_context = []
    notion_pages = {}

    # 1. 预先收集所有行情和事实数据
    for metal, sym in tickers.items():
        try:
            hist = yf.download(sym, period="5d", progress=False)
            if hist.empty: continue
            price = hist['Close'].iloc[-1].item()
            change = (price - hist['Close'].iloc[-2].item()) / hist['Close'].iloc[-2].item() * 100
            
            res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS,
                json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                       {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
            
            if res.get("results"):
                page = res["results"][0]
                notion_pages[metal] = page["id"]
                
                props = page["properties"]
                dealer_rich_text = props.get("JPM/Asahi etc Stock change", {}).get("rich_text", [])
                dealer_info = dealer_rich_text[0]["plain_text"] if dealer_rich_text else "暂无异动数据"
                
                market_context.append(f"--- {metal} ---\nPrice: {price:.2f} ({change:+.2f}%)\nDealer Facts: {dealer_info}")
        except Exception as e: 
            print(f"❌ {metal} 数据收集失败: {e}")

    if not market_context: 
        print("⚠️ 未收集到任何行情数据，中止研判。")
        return

    # 2. 构造合并 Prompt
    full_prompt = f"你是顶尖宏观交易员。以下是 {date_str} 的贵金属数据：\n\n" + "\n".join(market_context) + \
                  "\n\n请分别为每个品种提供 2 句硬核研判。格式严格如下：\n[Gold] 结论...\n[Silver] 结论...\n[Platinum] 结论...\n[Copper] 结论..."

    # 3. 获取 AI 研判
    all_analysis = call_gemini_sdk_consolidated(full_prompt)
    
    if all_analysis:
        print("\n--- AI 原始返回内容 ---")
        print(all_analysis)
        print("-----------------------\n")
        
        # 4. 解析并填入 Notion
        for metal, page_id in notion_pages.items():
            try:
                start_marker = f"[{metal}]"
                if start_marker in all_analysis:
                    part = all_analysis.split(start_marker)[1].split("[")[0].strip()
                    requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=HEADERS,
                        json={"properties": {"Activity Note": {"rich_text": [{"text": {"content": part}}]}}})
                    print(f"✅ {metal} 深度研判同步成功")
            except Exception as e: 
                print(f"❌ {metal} 写入失败: {e}")

if __name__ == "__main__": 
    run_analysis()
