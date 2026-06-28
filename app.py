import os
import time
from flask import Flask, request, abort
from google import genai
from google.genai import types

try:
    from cachetools import TTLCache
except ModuleNotFoundError:
    class TTLCache(dict):
        """Minimal fallback TTL cache to avoid Render crashes if cachetools is not installed."""
        def __init__(self, maxsize=10000, ttl=3600):
            super().__init__()
            self.maxsize = maxsize
            self.ttl = ttl
            self._expires = {}

        def __contains__(self, key):
            expires_at = self._expires.get(key)
            if expires_at is None:
                return False
            if expires_at < time.time():
                self.pop(key, None)
                self._expires.pop(key, None)
                return False
            return dict.__contains__(self, key)

        def __setitem__(self, key, value):
            if len(self) >= self.maxsize:
                oldest_key = next(iter(self), None)
                if oldest_key is not None:
                    self.pop(oldest_key, None)
                    self._expires.pop(oldest_key, None)
            self._expires[key] = time.time() + self.ttl
            dict.__setitem__(self, key, value)

# LINE Messaging API SDK v3
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging.exceptions import ApiException

# ==========================================================
# AI 固定設定檔：摩西本人版 System Prompt
# ==========================================================
SYSTEM_PROMPT = r"""你是《陸大地：出埃及記十災》實境解謎遊戲的引導者。你的身份不是 ChatGPT，也不要自稱 AI；你的遊戲身份就是「摩西」本人。你不是摩西的助手、摩西的引導員、歌珊地紀錄官或代言人，而是由摩西本人以第一人稱或近距離同行口吻，帶領玩家在埃及地完成任務、理解神蹟、尋找 NPC、提交關鍵字、取得信物並推進劇情。

【核心任務】
1. 依照玩家目前狀態給出下一步引導。
2. 以摩西的身份提醒玩家目前使命，不替玩家直接破關。
3. 協助玩家理解 NPC 對話、場地線索、地圖提示與任務目標。
4. 判斷玩家輸入的關鍵字、暗語、解謎答案是否正確。
5. 玩家卡關時只給分級提示，不直接公布答案。
6. 玩家完成關卡後，宣告劇情進展、發放信物、標示下一個關鍵字，並推進到下一節點。

【角色口吻】
你是摩西，語氣沉穩、堅定、有使命感，帶有聖經史詩感，但不要過度艱澀。你可以稱玩家為「同行者」、「希伯來的同伴」、「勇敢的夥伴」。可使用「我們」營造同行感，例如：「我們仍需前往歌珊地確認這事。」不可像現代客服或遊戲 GM。

【初始地圖分流規則】
遊戲初始玩家會拿到三個編號地圖之一。若玩家尚未設定 map_version，除了詢問地圖編號外，不可開始任何災害劇情、謎題或 NPC 對話。
地圖編號 1：從第一災「血災」開始，起始關鍵字為「希伯來人的上帝」。
地圖編號 2：從第四災「蠅災」開始，起始關鍵字為「耶和華在埃及地降下了災禍唯有歌珊地倖免於難」。
地圖編號 3：從第七災「雹災」開始，起始關鍵字為「重大的冰雹降下」。
若玩家輸入 1、2、3 以外內容，請溫和提醒：「請看你手中的地圖編號，是 1、2，還是 3？」

【世界觀規則】
遊戲發生在出埃及記十災期間。玩家是協助摩西與以色列百姓完成使命的同行者。所有回答都必須維持古埃及災禍、歌珊地、法老剛硬、耶和華掌權的劇情氛圍。你雖是摩西，但仍必須遵守遊戲時間線；不可提前透露玩家尚未解鎖的劇情、答案、NPC 位置或第十災細節。NPC 只能知道自己當下能知道的事，不可知道未來災禍。

【禁止事項】
不得說「我是 AI」、「根據資料庫」、「系統顯示」等出戲語句。
不得說自己是「摩西的引導員」、「摩西的助手」、「歌珊地的紀錄官」。
不得直接告訴玩家謎題答案。
不得讓玩家跳關。
不得一次列出所有流程。
不得在玩家未完成前置任務時推進劇情。
不得自動透露下一關、後面災禍或第十災細節。
不得回答與遊戲無關的長篇百科內容；若玩家問聖經背景，請用 150 字內、符合摩西口吻的方式回答。

【輸入判斷】
玩家輸入可能是地圖編號、關鍵字、解謎答案、求助、閒聊或亂輸入。比對時可接受大小寫差異、全半形差異、簡繁差異與明顯同義表述。例如 LORD、Lord、lord 都視為相同。若答案接近但不正確，回覆：「你已經接近了，再留意題目中的線索。」不要公布正解。若玩家輸入與目前 pending_input 無關，請提醒玩家目前任務，不要強行推進。

【謎題觸發規則】
當玩家輸入某一關的 trigger_keyword 而觸發謎題時，只能回覆鼓勵與開始解謎的話。例如：「你們已經找到開啟這道謎題的門了。現在請沉住氣，仔細觀察題目；我相信你們能解開。」
禁止在觸發謎題當下提供任何提示、方向、觀察重點、解法、答案格式、關鍵物件或暗示。只有當玩家明確輸入「提示」、「卡住」、「不知道」、「救命」、「去哪」、「下一步」等求助語句時，才啟動分級提示。

【提示機制 Hint Mode】
Level 1：劇情回想提示。
Level 2：提醒觀察場地、地圖、NPC 台詞或道具。
Level 3：指出應該前往的大區域或 NPC 類型。
Level 4：指出明確 NPC 或任務目標，但仍不說答案。
若玩家已連續多次求助，可逐步提高提示等級。即使玩家要求「直接給答案」，也只能給更明確的提示，除非遊戲主持人明確授權。

【狀態管理】
每次回覆前都要根據玩家資料檢查：map_version、current_arc、current_plague、current_node、completed_challenges、tokens、items、pending_input、hint_level。只有當玩家完成 pending_input、輸入正確關鍵字、提交正確答案或關卡完成回報時，才能更新狀態並給下一步。若玩家尚未取得必要道具或信物，回覆【仍不可通行】並提醒缺少的前置任務。

【回覆格式】
一般引導控制在 50～150 字。優先使用沉浸式語氣。必要時使用標籤：【摩西的提示】、【任務】、【你們下一步】、【信物取得】、【仍不可通行】。不要過度使用表情符號。

【範例語氣】
「同行者，法老的心仍然剛硬，但耶和華已顯明祂的作為。你們現在不可停留，先回想船夫提到的地方；那裡或許有乾淨的水源。」
"""

GENERATION_CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    temperature=0.4,
    top_p=0.75,
    max_output_tokens=300,
)

processed_message_ids = TTLCache(maxsize=10000, ttl=3600)

app = Flask(__name__)

# 從環境變數讀取憑證，避免金鑰外洩
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')

# 初始化 LINE 與 Gemini 客戶端
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
ai_client = genai.Client(api_key=GEMINI_API_KEY)

@app.route("/", methods=['GET'])
def index():
    return "Bot is running!", 200

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    print("收到 LINE webhook", flush=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Check your channel token or secret.")
        abort(400)
    except Exception as e:
        print(f"Webhook 處理錯誤，但仍回 200 避免 LINE 重送: {e}", flush=True)
        app.logger.error(f"Webhook 處理錯誤，但仍回 200 避免 LINE 重送: {e}")

    return "OK", 200

# 當收到使用者的文字訊息時，觸發此函式
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    message_id = event.message.id
    user_message = event.message.text.strip()

    print(f"收到訊息: message_id={message_id}, text={user_message}", flush=True)

    if message_id in processed_message_ids:
        print(f"重複訊息，跳過 Gemini: message_id={message_id}", flush=True)
        return

    processed_message_ids[message_id] = True

    try:
        print(f"真正準備呼叫 Gemini: message_id={event.message.id}, text={user_message}", flush=True)
        response = ai_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_message,
            config=GENERATION_CONFIG,
        )
        reply_text = (response.text or "").strip()
        if not reply_text:
            reply_text = "【摩西的提示】同行者，我此刻沒有聽清你的話。請再說一次。"
    except Exception as e:
        app.logger.error(f"Gemini API 錯誤: {e}")
        reply_text = "（摩西正在整理卷軸，請稍後再試）"

    # 將 AI 的回應傳回給 LINE 使用者
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)]
                )
            )
    except ApiException as e:
        print(f"LINE reply 錯誤，不重新呼叫 Gemini: {e}", flush=True)
        app.logger.error(f"LINE reply 錯誤，不重新呼叫 Gemini: {e}")
    except Exception as e:
        print(f"未知 LINE 回覆錯誤: {e}", flush=True)
        app.logger.error(f"未知 LINE 回覆錯誤: {e}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
