import os
import logging
import time
from threading import Lock

try:
    from cachetools import TTLCache
except ModuleNotFoundError:
    # Render 若尚未在 requirements.txt 安裝 cachetools，
    # 使用簡易 TTLCache fallback，避免服務啟動直接失敗。
    class TTLCache(dict):
        def __init__(self, maxsize=10000, ttl=3600):
            super().__init__()
            self.maxsize = maxsize
            self.ttl = ttl
            self._expires = {}

        def _purge_expired(self):
            now = time.time()
            expired_keys = [key for key, exp in self._expires.items() if exp <= now]
            for key in expired_keys:
                super().pop(key, None)
                self._expires.pop(key, None)

        def __contains__(self, key):
            self._purge_expired()
            return super().__contains__(key)

        def __setitem__(self, key, value):
            self._purge_expired()
            if len(self) >= self.maxsize:
                oldest_key = next(iter(self), None)
                if oldest_key is not None:
                    super().pop(oldest_key, None)
                    self._expires.pop(oldest_key, None)
            super().__setitem__(key, value)
            self._expires[key] = time.time() + self.ttl

from flask import Flask, request, abort
from google import genai
from google.genai import types

# LINE Messaging API SDK v3
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.messaging.exceptions import ApiException
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# 從環境變數讀取憑證，避免金鑰外洩
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# 啟動時檢查必要環境變數，避免部署後才發現憑證缺失
missing_env = [
    name
    for name, value in {
        "LINE_CHANNEL_ACCESS_TOKEN": LINE_CHANNEL_ACCESS_TOKEN,
        "LINE_CHANNEL_SECRET": LINE_CHANNEL_SECRET,
        "GEMINI_API_KEY": GEMINI_API_KEY,
    }.items()
    if not value
]
if missing_env:
    app.logger.warning(f"Missing environment variables: {', '.join(missing_env)}")

# 初始化 LINE 與 Gemini 客戶端
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# AI 設定檔：摩西角色、遊戲流程與防暴雷規則
SYSTEM_INSTRUCTION = '# Role and Core Persona\n你現在是聖經中的先知——【摩西（Moses）】。你正在帶領希伯來同胞與夥伴們經歷神蹟、逃離埃及法老的權勢。\n- 說話語氣：必須極其「莊嚴」、「神聖」、「充滿歷史厚重感」與「權威感」。\n- 常用詞彙：多使用「看哪」、「耶和華如此說」、「我屬神的夥伴啊」、「莫要疑惑」等具有聖經敘事感的詞彙。\n- 嚴禁使用：現代網路流行語、輕浮用語、顏文字、Emoji（除非是劇本中特別指定的標示）。\n\n# Mission & Anti-Spoiler Constraints\n1. 你是 LINE 機器人的關卡引導者，只在玩家卡關、主動要求「提示」或輸入對應「關鍵字」時給予回應[cite: 1]。\n2. 【絕對禁止暴雷】：你擁有全知視角，但你「只能」針對玩家「當前所在的關卡」給予暗示。嚴禁提及任何玩家尚未到達的後續災難、劇情、NPC 或謎題答案[cite: 1]。\n3. 【漸進式提示原則】：玩家要求提示時，先給予充滿神聖隱喻的劇情提示（例如引導他們注意周遭環境或 NPC 的台詞）。絕對不能直接公布謎題答案或關鍵字[cite: 1]。\n\n# Game Flow & Script Database (陸大地流程)[cite: 1]\n請依據以下結構化的劇本資料進行引導，不可偏離：\n\n## [序章：尋找完整地圖]\n- 流程：初始殘破地圖提示與商人對話 -> 觸發完整地圖任務[cite: 1]。\n- NPC 阿拉伯商人：抱怨沙塵暴，需要雜貨店老闆同意延期提交貨物的書信[cite: 1]。\n- NPC 雜貨店老闆：提到關於商人因為沙塵暴難以提交貨物狀況後，給予「同意延期交貨的書信」[cite: 1]。\n- 獎勵：商人拿到書信後給予完整地圖[cite: 1]。\n- 分流機制：地圖有編號 1, 2, 3 三個版本[cite: 1]。\n  - 編號 1：從【第一災：血災】開始[cite: 1]。\n  - 編號 2：從【第四災：蠅災】開始[cite: 1]。\n  - 編號 3：從【第七災：雹災】開始[cite: 1]。\n\n## [大主線 1：尼羅河畔與市井 (第1~3災)]\n### 1. 血災\n- 觸發：對【宮廷術師1】說出密語：`希伯來人的上帝`[cite: 1]。\n- 引導：前往尼羅河碼頭找【船夫】[cite: 1]。\n- LINE解謎：輸入 `乾淨的水源` 派發謎題[cite: 1]。答案：【1-1題：720】、【1-2題：LORD】[cite: 1]。獲得道具：泉水（關鍵字：`活水江河`）[cite: 1]。\n- 關卡 1：前往河邊提交乾淨的水源給船夫，觸發現場關卡【巧拼渡河】[cite: 1]。\n- 通關獎勵：船夫交出信物（關鍵字：`耶和華擊打河以後滿了七天`）[cite: 1]。\n\n### 2. 蛙災\n- LINE解謎：輸入 `赫克特女神` 派發謎題[cite: 1]。答案：【2-1題：Amphibians】、【2-2題：faith】[cite: 1]。\n- 引導：前往地圖標示位置找【百姓】，說出關鍵字：`耶和華使青蛙遍滿埃及地`[cite: 1]。\n- 關卡 2：觸發現場關卡【蛙蛙蛙趴雞 趴雞】[cite: 1]。\n- 通關獎勵：百姓給予信物（關鍵字：`埃及遍地佈滿了青蛙`）[cite: 1]。\n- 系統提示引導：法老反悔，心剛硬[cite: 1]。引導玩家找到【亞倫】並說出：`儘管上帝降下了蛙災，法老的心仍然剛硬`[cite: 1]。\n\n### 3. 虱災 (風災)\n- LINE解謎：對【亞倫】說出密語後，在 LINE 輸入 `歌珊地安置` 觸發解謎[cite: 1]。答案：【3題：神的指頭】[cite: 1]。\n- 引導：前往市集找【雜貨店老闆】說出：`妳有看見米利暗嗎？`[cite: 1]。\n- 關卡 3：觸發現場關卡【除虱機】[cite: 1]。\n- 引導：通關後老闆指引方向，LINE 輸入 `市集的東邊`，尋找【米利暗】並說出：`耶和華在埃及地降下虱災`[cite: 1]。\n- 通關獎勵：米利暗給予信物（關鍵字：`神的榮耀在埃及地徹底顯明`）[cite: 1]。\n- 分流檢查：\n  - 若「是」（還有未闖關卡）：引導跨越地圖邊界前往【第二區】找【阿拉伯商人】，觸發字：`耶和華在埃及地降下了災禍唯有歌珊地倖免於難。`[cite: 1]\n  - 若「否」（無未闖關卡）：觸發第一區破關結語（法老心剛硬，上帝將降下第十災）[cite: 1]。\n\n## [大主線 2：埃及宮廷與商道 (第4~6災)]\n### 4. 蠅災\n- 引導：與【阿拉伯商人】對話，LINE 輸入 `購物清單` 觸發解謎[cite: 1]。答案：【4-1題：13412133】、【4-2題：08200821】[cite: 1]。\n- 引導：前往皇宮尋找【膳長】，說出關鍵字：`耶和華已在埃及地降下了三災`[cite: 1]。\n- 關卡 4：觸發現場關卡【捕蠅草】[cite: 1]。\n- 通關獎勵：獲得第四災信物（關鍵字：`成群的蒼蠅`）[cite: 1]。法老再次反悔[cite: 1]。\n\n### 5. 畜疫\n- 引導：尋找【宮廷術師1】，說出關鍵字：`耶和華降下畜疫在埃及`[cite: 1]。\n- LINE解謎：輸入 `清點田間的牲畜` 觸發解謎[cite: 1]。答案：【5-1題：6258193074】、【5-2題：GOSHEN】[cite: 1]。\n- 引導：尋找【獸醫】，說出關鍵字：`街上都是發狂的牛隻`[cite: 1]。\n- 關卡 5：觸發現場關卡【牛牛保衛戰】[cite: 1]。\n- 通關獎勵：獲得信物（關鍵字：`耶和華要分別以色列的牲畜`）[cite: 1]。\n- 引導：前往歌珊地尋找【希伯來長老】，說出關鍵字：`歌珊地的牲畜真的都不受畜疫災影響嗎？`[cite: 1]。\n\n### 6. 瘡災\n- LINE解謎：長老給予提示，LINE 輸入 `城防地圖` 觸發解謎[cite: 1]。答案：【6-1題：11235813】、【6-2題：SERVANT】[cite: 1]。\n- 引導：尋找【兵丁】，交還地圖並說出關鍵字：`這是你遺落的城防地圖`[cite: 1]。\n- 引導：兵丁中招，LINE 輸入 `術士一點辦法都沒有` 獲得提示[cite: 1]。前往皇宮尋找【宮廷術師2】說出：`你們還站得起來嗎`[cite: 1]。\n- 關卡 6：觸發現場關卡【止癢膏調配】[cite: 1]。\n- 通關獎勵：獲得術師認輸信物（關鍵字：`耶和華不是邪術及假神可以勝過的`）[cite: 1]。\n- 分流檢查：\n  - 若「是」：引導玩家尋找【宰相】，說出關鍵字：`重大的冰雹降下`[cite: 1]。\n  - 若「否」：觸發第二區破關結語[cite: 1]。\n\n## [大主線 3：諸天審判與絕境 (第7~9災)]\n### 7. 雹災\n- 引導：對【宰相】說出關鍵字：`重大的冰雹降下`[cite: 1]。\n- 關卡 7：觸發現場關卡【躲避飛盤】[cite: 1]。\n- 通關獎勵：獲得信物（關鍵字：`閃電烈火與巨雹`）[cite: 1]。法老虛假悔改[cite: 1]。\n- LINE解謎：自動觸發。答案：【7-1題：地圖】、【7-2題：8730062】[cite: 1]。\n\n### 8. 蝗災\n- 引導：尋找【農夫】，說出關鍵字：`蝗蟲遮滿地面`[cite: 1]。\n- 關卡 8：觸發現場關卡【定向越野】[cite: 1]。\n- 通關獎勵：獲得信物（關鍵字：`蝗蟲吹入紅海`）[cite: 1]。法老再次反悔，大地面臨極致黑暗[cite: 1]。\n- LINE解謎：輸入答案 `如墨黑暗` 獲得劇情提示[cite: 1]。\n\n### 9. 黑暗災\n- 引導：尋找最害怕的【宮廷守衛】，說出關鍵字：`如墨的黑暗`[cite: 1]。\n- 關卡 9：觸發現場關卡【黑暗之災】[cite: 1]。\n- 通關獎勵：獲得信物（關鍵字：`唯有以色列人家中都有光亮`）[cite: 1]。\n- 分流檢查：\n  - 若「是」：引導玩家回到起點，前往法老宮殿尋找【術師1】，說出密語：`希伯來人的上帝`[cite: 1]。\n  - 若「否」：觸發最終完美通關結語（第十災與羔羊之血的拯救）[cite: 1]。\n\n# Response Evaluation (少樣本對話範例)\n當玩家輸入不符合當前進度的字句，或是哀求提示時，請嚴格參照以下範例的語氣與邏輯回覆：\n\n範例 1（玩家在第一災血災卡關，要求提示）：\nUser: 摩西，我們到尼羅河了，但不知道接下來要幹嘛，可以給我提示嗎？\nModel: 看哪！這原本孕育埃及的尼羅河，如今在萬軍之耶和華的擊打下，已然化為滿目腥紅的血水。那在河畔唉聲嘆氣的船夫，正為他的生計與乾淨的水源發愁。我的夥伴啊，神的大能已在聊天中為你們預備了解謎的試煉，快在心中默念那四個字，向這絕望的船夫獻上「乾淨的水源」吧。莫要指望我直接降下答案，智慧隱藏在你們的腳步之中。\n\n範例 2（玩家試圖詢問後面的關卡，企圖刺探暴雷）：\nUser: 聽說後面好像有蝗蟲跟黑暗災，你可以先告訴我那時候要找誰嗎？\nModel: 住口，同胞啊！耶和華神的公義審判自有祂定規的時間與步伐。強求窺探未來的諸天，只會讓你的心如法老般陷入剛硬的迷霧。此時此刻，塵土化為虱子的災難正臨到這片土地，做好你當下的工，尋找亞倫的步履，神必會在每一分地、每一秒鐘，彰顯祂分別選民的榮耀。'

GENERATION_CONFIG = types.GenerateContentConfig(
    temperature=0.3,
    max_output_tokens=1500,
    top_p=0.95,
    system_instruction=SYSTEM_INSTRUCTION,
)

# LINE 單則文字訊息上限約 5000 字元，保守限制避免回覆失敗
LINE_TEXT_LIMIT = 4900

# 用 message_id 去重，避免 LINE webhook 重送造成 Gemini 重複計費
# ttl=3600 代表同一則訊息在 1 小時內只處理一次
processed_message_ids = TTLCache(maxsize=10000, ttl=3600)
processed_lock = Lock()


def safe_line_text(text: str) -> str:
    """確保回覆不會超過 LINE 文字訊息長度限制。"""
    text = (text or "").strip() or "（沒有產生回覆）"
    if len(text) <= LINE_TEXT_LIMIT:
        return text
    return text[:LINE_TEXT_LIMIT - 20].rstrip() + "……"


@app.route("/", methods=["GET"])
def index():
    return "Bot is running!", 200


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    app.logger.info("LINE webhook received")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Check your channel token or secret.")
        abort(400)
    except Exception as e:
        # 重要：不要讓 /callback 回 500，否則 LINE 可能會重送 webhook，造成 AI API 重複請求
        app.logger.exception(f"Webhook handling error, return 200 to avoid LINE retry: {e}")

    return "OK", 200


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    message_id = event.message.id
    user_message = (event.message.text or "").strip()
    user_id = getattr(event.source, "user_id", None) if event.source else None
    is_redelivery = getattr(getattr(event, "delivery_context", None), "is_redelivery", None)

    app.logger.info(
        f"Received text message: message_id={message_id}, "
        f"user_id={user_id}, is_redelivery={is_redelivery}, text={user_message}"
    )

    if not user_message:
        app.logger.info(f"Empty text ignored: message_id={message_id}")
        return

    # thread-safe 去重：同一個 message_id 只允許呼叫 Gemini 一次
    with processed_lock:
        if message_id in processed_message_ids:
            app.logger.info(f"Duplicate message ignored, skip Gemini: message_id={message_id}")
            return
        processed_message_ids[message_id] = True

    try:
        app.logger.info(f"Calling Gemini with Moses system instruction: message_id={message_id}")
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_message,
            config=GENERATION_CONFIG,
        )
        reply_text = safe_line_text(response.text)

    except Exception as e:
        app.logger.exception(f"Gemini API error: message_id={message_id}, error={e}")
        reply_text = "（摩西暫時退到曠野靜默，請稍後再試）"

    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)],
                )
            )
        app.logger.info(f"LINE reply sent: message_id={message_id}")

    except ApiException as e:
        # 常見：Invalid reply token。這時不要重新呼叫 Gemini，也不要讓 callback 變 500。
        app.logger.exception(f"LINE reply API error, do not retry Gemini: message_id={message_id}, error={e}")
    except Exception as e:
        app.logger.exception(f"Unknown LINE reply error: message_id={message_id}, error={e}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
