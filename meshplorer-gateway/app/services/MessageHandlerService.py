import asyncio
import logging
import random
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from app.utils.ConfigUtil import ConfigUtil
from app.utils.MeshSightUtil import MeshSightUtil
from app.utils.MeshtasticUtil import MeshtasticUtil
from app.services.MeshtasticService import MeshtasticService
from app.services.WeatherService import WeatherService
from app.services.EmergencyGuardianService import EmergencyGuardianService


class MessageHandlerService:
    """訊息處理服務，負責處理各種頻道訊息和指令路由"""

    def __init__(self, meshtastic_service: MeshtasticService):
        self.config = ConfigUtil().read_config()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(self.config.get("log", {}).get("level", "INFO").upper())

        # 注入相依服務
        self.meshtastic_service = meshtastic_service
        self.weather_service = WeatherService(meshtastic_service)
        self.emergency_service = EmergencyGuardianService(meshtastic_service)

        # 訊息去重和靜默控制
        self.seen_message_ids = {}  # id: timestamp
        self.seen_message_expire = 600  # 秒，保留 10 分鐘
        self.tested_emoji_silence_until: datetime = datetime.now(timezone.utc)

        # 廣告訊息清單
        self.ad_messages = [
            "🤫～保持頻道乾淨，我只在 SingleTest 頻道工作 ✨",
            "🌦️想知道今天穿什麼？叫我一聲 @nfs.tw weather，馬上報你當地天氣！（記得開定位分享喔 📍）",
            "🤖懶得召喚ARBot？簡單！輸入 @nfs.tw ab，讓我來幫忙 🚀",
            "🤖使用 @nfs.tw help 查看指令！",
            "🗺️找附近節點？快上 MeshSight 探索起來吧 🔍 https://meshsight.nfs.tw/",
            "🧭我是 MeshPlorer，一名穿梭於 Meshtastic 網路中的探索者！",
            "🤖我是 MeshPlorer～每天都在節點間健行，有人要陪我一起走嗎？👣",
            "🎯想挑戰我嗎？看看你能不能找到我巡邏過的最遠節點！",
            "🌌歡迎來到 Meshtastic 宇宙，每個節點都是一顆星✨",
            "📘新手上路？快看看官方文件，掌握 Meshtastic 操作術！ https://meshtastic.org/docs/",
            "🔋記得常檢查電量，訊號不中斷，探索不打烊！",
            "🌐離網不離線，這就是 Meshtastic 最酷的地方！",
            "🛰️你知道嗎？Meshtastic 的節點可以用 LoRa 傳送訊息超過幾公里遠喔！",
            "📡每個節點都是一個小型的中繼站，讓我們的訊息穿越山川河流！",
            "📷發現有趣的節點配置？快分享給社群看看！",
            "📣想和更多臺灣使用者交流？快加入 Meshtastic Taiwan Community《臺灣鏈網》 👉 https://www.facebook.com/groups/413628121046386",
            "📍發現高點或戰略節點？回報給社群一起優化節點佈局吧！",
            "🌟每個節點都是我們 Meshtastic 網路的一部分，讓我們一起連接世界！",
            "🛰️訊號在城市間穿梭，每次連線都是一次未知冒險！",
            "🚩新節點、新希望，一起把台灣鏈網佈好佈滿吧！",
            "🙌今天你幫社群多插一個節點，明天訊號就多一分保障！",
            "🏕️偏遠地區節點稀少？誰願意成為那裡的開拓者？",
            "🚨據點掉線了？看看附近有沒有人能支援！",
            "👻聽說深夜出現神秘節點會發出奇怪訊號...你遇過嗎？",
            "🔧節點設定有問題？社群裡有很多高手可以幫忙！",
            "📡訊號強度不理想？試試調整天線位置或高度！",
            "🌐想了解更多 Meshtastic 技術？歡迎加入我們的討論！",
            "💡有創新的節點應用想法？分享給大家一起實現！",
            "🎯精準定位很重要，記得定期校正你的節點座標！",
            "🔄定期檢查節點狀態，確保網路穩定運行！",
            "🤝遇到問題別擔心，社群夥伴們都很樂意幫忙！",
            "🚀一起打造台灣最強大的 Mesh 網路吧！",
            "💪每個節點都是 Meshtastic 網路的一份子，你的貢獻很重要！",
            "🌍從台灣出發，連接全世界！",
            "📱手機沒訊號？Meshtastic 網路可能是你的救星！",
            "🏔️高山、海邊、城市，哪裡都有我們的節點！",
            "⚡快速、穩定、免費的無線通訊網路！",
            "🔍探索你附近的 Meshtastic 節點，發現新的連線可能！",
            "🎉歡迎加入 Meshtastic 台灣社群！",
            "📈Meshtastic 網路在成長，你的參與讓它更強大！",
            "🛡️備援通訊系統，讓溝通永不中斷！",
            "🌙深夜的 Meshtastic 網路，靜靜地守護著我們！",
            "☀️白天的訊號，照亮每個角落！",
            "🌈多樣化的節點，豐富的網路生態！",
            "🎵訊號在空氣中跳舞，傳遞著訊息與希望！",
            "🔮未來已來，Meshtastic 網路正在改變世界！",
            "💎珍貴的無線資源，需要我們共同維護！",
            "🌟成為 Meshtastic 網路的一份子，連接無限可能！",
        ]

    async def handle_channel_message(self, mp: Any, channel_id: int) -> None:
        """處理頻道訊息路由"""
        try:
            # 檢查重複訊息，避免重複處理
            if not await self._check_duplicate_message(mp):
                return

            self.logger.info(
                f"處理頻道訊息，channel_id: {channel_id}, msg_id: {getattr(mp, 'id', 0)}, "
                f"sender: {getattr(mp, 'from')}，to: {getattr(mp, 'to')}"
            )

            # 取得解碼資料
            decode = getattr(mp, "decoded", None)
            if decode is None:
                self.logger.error(f"訊息 {getattr(mp, 'id', 0)} 沒有解碼資料，無法處理")
                return

            # 處理 emoji 訊息
            if getattr(decode, "emoji", 0) == 1:
                self.logger.info(
                    f"收到來自頻道 {channel_id} 的 emoji 訊息，msg_id: {getattr(mp, 'id', 0)}，"
                    f"sender: {getattr(mp, 'from')}"
                )
                # TODO: 可以在這裡處理 emoji 訊息的邏輯
                return

            # 處理文字訊息
            text = await self._extract_text_from_payload(decode)
            if not text:
                return

            command = await self._extract_command(text)
            if command is not None:  # 使用 is not None 來檢查，因為空字串也是有效的指令
                # 檢查是否為指令訊息
                await self._handle_command_message(mp, channel_id, command)
            elif await self._is_test_message(text):
                # 檢查是否為測試意圖訊息
                await self._handle_test_message(mp, channel_id, text)
            else:
                self._log_ignored_message(text, channel_id, mp)
        except Exception as e:
            self.logger.error(f"處理頻道訊息時發生錯誤: {e}")

    async def _check_duplicate_message(self, mp: Any) -> bool:
        """檢查是否為重複訊息"""
        now = time.time()
        # 清理過期的訊息 ID
        expired = [
            mid
            for mid, ts in self.seen_message_ids.items()
            if now - ts > self.seen_message_expire
        ]
        for mid in expired:
            del self.seen_message_ids[mid]

        message_id = getattr(mp, "id", 0)
        if message_id is not None:
            if message_id in self.seen_message_ids:
                self.logger.info(f"訊息 {message_id} 已處理過，忽略重複處理")
                return False
            self.seen_message_ids[message_id] = now
        return True

    async def _extract_text_from_payload(self, decode: Any) -> Optional[str]:
        """從 payload 中提取文字內容"""
        if (
            hasattr(decode, "payload")
            and isinstance(decode.payload, bytes)
            and decode.payload
        ):
            try:
                text = decode.payload.decode("utf-8")
                return text.strip() if text else None
            except Exception:
                return None
        return None

    async def _is_test_message(self, text: str) -> bool:
        """檢查是否為測試意圖訊息"""
        text_clean = text.strip().lower()

        # 如果訊息太長，可能不是測試意圖
        if len(text_clean) > 10:
            return False

        # 英文測試關鍵字（需要是獨立詞彙，避免誤判）
        english_keywords = ["test", "testing"]
        words = text_clean.split()
        for keyword in english_keywords:
            if text_clean == keyword or (keyword in words and len(words) <= 3):
                return True

        # 中文測試關鍵字（可以直接包含在文字中）
        chinese_keywords = ["測試"]
        for keyword in chinese_keywords:
            if keyword in text_clean:
                return True

        return False

    async def _extract_command(self, text: str) -> Optional[str]:
        """提取指令內容"""
        text_lower = text.lower()
        command_prefixes = ["@nfs.tw", "@nfstw", "@nfs"]

        for prefix in command_prefixes:
            if text_lower.startswith(prefix):
                # 提取指令內容，即使只有 @nfs 也要回傳空字串而不是 None
                command_content = text[len(prefix) :].strip()
                # 回傳指令內容（可能是空字串），讓呼叫方決定如何處理
                return command_content
        return None

    async def _handle_test_message(self, mp: Any, channel_id: int, text: str) -> None:
        """處理測試意圖訊息"""
        # 檢查靜默期間
        if datetime.now(timezone.utc) < self.tested_emoji_silence_until:
            self.logger.info(
                f"尚未到 emoji 靜默截止時間，忽略本次，"
                f"now: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}, "
                f"silence_until: {self.tested_emoji_silence_until.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
            return
        else:
            # 設定 emoji 靜默截止時間
            self.tested_emoji_silence_until = datetime.now(timezone.utc) + timedelta(
                seconds=20
            )

        text_clean = text.replace("\n", " ")
        self.logger.info(
            f"收到測試意圖訊息: {text_clean}，頻道 ID: {channel_id}, "
            f"msg_id: {getattr(mp, 'id', 0)}, sender: {getattr(mp, 'from')}"
        )

        # 發送測試回應 emoji
        packet = self.meshtastic_service.create_emoji_packet(
            channel_id=channel_id, emoji="👌", reply_id=getattr(mp, "id", None)
        )
        await self.meshtastic_service.send_packet(
            mesh_packet=packet, destination_id="^all"
        )

    async def _handle_command_message(
        self, mp: Any, channel_id: int, command: str
    ) -> None:
        """處理指令訊息"""
        self.logger.info(
            f"收到來自頻道 {channel_id} 的指令，msg_id: {getattr(mp, 'id', 0)}，"
            f"sender: {getattr(mp, 'from')}，指令: {command}，"
            f"mp: {mp}"
        )

        # 先發送機器人 emoji 表示收到
        robot_packet = self.meshtastic_service.create_emoji_packet(
            channel_id=channel_id, emoji="🤖", reply_id=getattr(mp, "id", None)
        )
        asyncio.create_task(
            self.meshtastic_service.send_packet(
                mesh_packet=robot_packet, destination_id="^all"
            )
        )

        # 取得發送者標籤
        sender_tag = await self._get_sender_tag(mp)

        # 解析指令和參數
        command_parts = command.strip().split(maxsplit=1)
        command_name = command_parts[0].lower() if command_parts else ""
        command_args = command_parts[1] if len(command_parts) > 1 else ""

        # 根據指令類型分派處理
        if command_name == "help":
            await self._handle_help_command(mp, channel_id, sender_tag, command_args)
        elif command_name == "weather":
            await self.weather_service.handle_weather_request(
                mp, channel_id, sender_tag
            )
        elif command_name == "ab":
            await self._handle_ab_command(mp, channel_id, sender_tag, command_args)
        elif command_name == "":  # 處理只有 @nfs 而沒有其他內容的情況
            await self._handle_general_command(mp, channel_id, "", sender_tag)
        else:
            await self._handle_general_command(mp, channel_id, command, sender_tag)

    async def _get_sender_tag(self, mp: Any) -> str:
        """取得發送者標籤"""
        sender_tag = (
            f"!{MeshtasticUtil.convert_node_id_from_int_to_hex(getattr(mp, 'from'))}"
        )

        try:
            # 併發取得節點資訊和位置資訊
            node_info_task = MeshSightUtil().get_node_info(getattr(mp, "from"))
            node_position_task = MeshSightUtil().get_node_position(getattr(mp, "from"))

            # 等待兩個 API 呼叫完成
            node_info, node_position = await asyncio.gather(
                node_info_task, node_position_task, return_exceptions=True
            )

            # 處理節點資訊
            if isinstance(node_info, Exception):
                self.logger.error(f"取得節點資訊失敗: {node_info}")
            elif node_info:
                short_name = node_info.get("item", {}).get("shortName")
                if short_name:
                    sender_tag = short_name

            # 處理位置資訊
            if isinstance(node_position, Exception):
                self.logger.error(f"取得位置資訊失敗: {node_position}")
            elif node_position and node_position.get("position"):
                taiwan_address = node_position.get("position", {}).get("taiwanAddress")
                if taiwan_address and isinstance(taiwan_address, dict):
                    city = taiwan_address.get("cityOrCounty")
                    district = taiwan_address.get("districtLevel")
                    address_parts = [part for part in [city, district] if part]
                    if address_parts:
                        sender_tag += f" ({''.join(address_parts)})"

        except Exception as e:
            self.logger.error(f"取得發送者資訊時發生錯誤: {e}")

        return sender_tag

    async def _handle_ab_command(
        self, mp: Any, channel_id: int, sender_tag: str, args: str = ""
    ) -> None:
        """處理 ARBot 呼叫指令"""
        # 如果沒有提供參數，使用預設值
        ab_command = args.strip() if args.strip() else "test"

        self.logger.info(
            f"發送 ab 指令給 ARBot，msg_id: {getattr(mp, 'id', 0)}, "
            f"sender: {sender_tag}, 參數: {ab_command}"
        )

        # 發送處理中訊息
        processing_packet = self.meshtastic_service.create_text_packet(
            channel_id=channel_id,
            text=f"嗨！{sender_tag}，正在為您呼叫 ARBot 機器人，若未收到回應，請稍後再試。",
            reply_id=getattr(mp, "id", None),
        )
        response_packet = await self.meshtastic_service.send_packet(
            mesh_packet=processing_packet, destination_id="^all", want_ack=True
        )

        await asyncio.sleep(random.uniform(0.5, 1))

        # 發送 ARBot 指令（包含參數）
        ab_packet = self.meshtastic_service.create_text_packet(
            channel_id=channel_id,
            text=f"@ab {ab_command}",
            reply_id=getattr(response_packet, "id", None),
        )
        await self.meshtastic_service.send_packet(
            mesh_packet=ab_packet, destination_id="^all", want_ack=True
        )

    async def _handle_help_command(
        self, mp: Any, channel_id: int, sender_tag: str, args: str = ""
    ) -> None:
        """處理幫助指令，支援分頁顯示"""

        # 定義所有可用的指令和說明
        commands_info = [
            {
                "name": "help",
                "description": "顯示所有可用指令的詳細說明",
                "usage": "help [頁碼]",
            },
            {
                "name": "ab",
                "description": "由我協助您呼叫 ARBot 機器人",
                "usage": "ab [指令]",
            },
            {
                "name": "weather",
                "description": "查詢您所在位置的天氣狀況（需開啟定位分享，每分鐘限用一次）",
                "usage": "weather",
            },
        ]

        # 先把指令內容組合起來（不包含標題和結尾）
        commands_text = ""
        for cmd in commands_info:
            commands_text += f"• {cmd['name']}: {cmd['description']}\n"
            commands_text += f"  用法: {cmd['usage']}\n"

        # 按照 80 字限制來分頁（只分指令內容）
        max_chars_per_page = 80
        pages = self._split_text_into_pages(commands_text, max_chars_per_page)
        total_pages = len(pages)

        # 解析頁碼參數
        try:
            page_num = int(args.strip()) if args.strip() else 1
            if page_num < 1:
                page_num = 1
            elif page_num > total_pages:
                page_num = total_pages
        except ValueError:
            # 如果頁碼無效，不處理
            return

        # 組合當前頁的完整內容
        current_page_text = f"MeshPlorer 說明 第{page_num}/{total_pages}頁；使用 @nfs.tw 前綴\n{pages[page_num - 1]}"

        # 發送幫助訊息
        help_packet = self.meshtastic_service.create_text_packet(
            channel_id=channel_id,
            text=current_page_text,
            reply_id=getattr(mp, "id", None),
        )
        await self.meshtastic_service.send_packet(
            mesh_packet=help_packet, destination_id="^all", want_ack=True
        )

    def _split_text_into_pages(self, text: str, max_chars: int) -> list[str]:
        """把文字聰明地分割成好幾頁，每頁都不會超過指定的字數"""
        if len(text) <= max_chars:
            return [text]

        pages = []
        lines = text.split("\n")
        current_page = ""

        for line in lines:
            # 檢查一下加入這行會不會超過限制
            test_page = current_page + line + "\n" if current_page else line + "\n"

            if len(test_page) <= max_chars:
                current_page = test_page
            else:
                # 如果目前這頁有內容的話，先存起來
                if current_page:
                    pages.append(current_page.rstrip())
                    current_page = line + "\n"
                else:
                    # 如果單獨一行就超過限制的話，強制分割
                    if len(line) > max_chars:
                        # 在字元限制的地方分割
                        pages.append(line[:max_chars])
                        current_page = line[max_chars:] + "\n"
                    else:
                        current_page = line + "\n"

        # 把最後一頁加進去
        if current_page:
            pages.append(current_page.rstrip())

        return pages

    async def _handle_general_command(
        self, mp: Any, channel_id: int, command: str, sender_tag: str
    ) -> None:
        """處理一般指令（顯示廣告訊息）"""
        # 清理並限制指令長度
        command_clean = command.replace("\n", " ").strip()
        if len(command_clean) > 50:
            command_clean = command_clean[:50] + "..."

        # 組合回覆訊息
        reply = "已收到：\n"
        if command_clean:
            reply += f"{command_clean}\n\n"
        reply += random.choice(self.ad_messages)
        reply = f"嗨！{sender_tag}，{reply}"

        # 發送回覆
        reply_packet = self.meshtastic_service.create_text_packet(
            channel_id=channel_id, text=reply, reply_id=getattr(mp, "id", None)
        )
        await self.meshtastic_service.send_packet(
            mesh_packet=reply_packet, destination_id="^all", want_ack=True
        )

    def _log_ignored_message(self, text: str, channel_id: int, mp: Any) -> None:
        """記錄被忽略的訊息"""
        text_clean = text.replace("\n", " ")
        self.logger.debug(
            f"訊息不以指令開頭，忽略: {text_clean}，頻道 ID: {channel_id}, "
            f"msg_id: {getattr(mp, 'id', 0)}, sender: {getattr(mp, 'from')}"
        )
