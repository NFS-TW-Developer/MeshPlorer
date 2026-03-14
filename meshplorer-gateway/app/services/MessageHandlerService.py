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
        # 一般指令全體靜默，靜默期內不回覆
        self.general_command_silence_until: datetime = datetime.now(timezone.utc)

        # 廣告訊息清單 - 從配置檔案讀取
        self.ad_messages = self.config.get("adMessages", [])

    async def handle_channel_message(self, mp: Any, channel_id: int) -> None:
        """處理頻道訊息路由"""
        try:
            # 檢查重複訊息，避免重複處理
            if not await self._check_duplicate_message(mp):
                return

            self.logger.info(
                f"處理頻道訊息，channel_id: {channel_id}, msg_id: {getattr(mp, 'id', 0)}, "
                f"sender: {getattr(mp, 'from')}，to: {getattr(mp, 'to')}, "
                f"mp: {str(mp).replace('\n', ' ')}"
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
            f"sender: {getattr(mp, 'from')}，指令: {command}"
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
        elif command_name == "askai" or command_name == "ask" or command_name == "ai":
            await self._handle_askai_command(mp, channel_id, sender_tag, command_args)
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
            {
                "name": "askai",
                "description": "與 AI 互動",
                "usage": "askai [問題]",
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
        now = datetime.now(timezone.utc)
        # 全體靜默期間：只 return 不回覆
        if now < self.general_command_silence_until:
            self.logger.info(
                f"一般指令尚在靜默期，忽略本次，"
                f"now: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}, "
                f"silence_until: {self.general_command_silence_until.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
            return
        self.general_command_silence_until = now + timedelta(minutes=5)

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

    async def _handle_askai_command(
        self, mp: Any, channel_id: int, sender_tag: str, args: str = ""
    ) -> None:
        """處理問 AI 指令"""
        self.logger.info(
            f"收到來自頻道 {channel_id} 的問 AI 指令，msg_id: {getattr(mp, 'id', 0)}，"
            f"sender: {sender_tag}, 參數: {args}"
        )

        # 檢查查詢內容
        if not args.strip():
            reply_text = f"嗨！{sender_tag}，請提供您要與 AI 互動的內容，例如： @nfs.tw askai 說個笑話"
            reply_packet = self.meshtastic_service.create_text_packet(
                channel_id=channel_id, text=reply_text, reply_id=getattr(mp, "id", None)
            )
            await self.meshtastic_service.send_packet(
                mesh_packet=reply_packet, destination_id="^all", want_ack=True
            )
            return

        try:
            # 初始化 DifyUtil
            from app.utils.DifyUtil import DifyUtil

            dify_util = DifyUtil()

            # 檢查設定
            if not dify_util.is_configured():
                reply_text = f"嗨！{sender_tag}，AI 服務還沒設定好。"
                reply_packet = self.meshtastic_service.create_text_packet(
                    channel_id=channel_id,
                    text=reply_text,
                    reply_id=getattr(mp, "id", None),
                )
                await self.meshtastic_service.send_packet(
                    mesh_packet=reply_packet, destination_id="^all", want_ack=True
                )
                return

            # 呼叫 Dify API
            user_id = str(getattr(mp, "from", "unknown"))
            response = await dify_util.send_chat_message_streaming(
                query=args.strip(), user=user_id, conversation_id=""  # 每次都是新的對話
            )

            # 處理回應
            if response:
                response = f"嗨！{sender_tag}，{response}"
                # 發送 AI 回應，自動分段處理
                max_length = 50
                segments = [
                    response[i : i + max_length]
                    for i in range(0, len(response), max_length)
                ]
                previous_packet_id = getattr(mp, "id", None)  # 第一段要回覆原始問題

                for i, segment in enumerate(segments):
                    segment_text = f"{segment}\n⚠️ AI 可能會出錯，請查核重要資訊。[{i+1}/{len(segments)}]"
                    segment_packet = self.meshtastic_service.create_text_packet(
                        channel_id=channel_id,
                        text=segment_text,
                        reply_id=previous_packet_id,
                    )
                    await self.meshtastic_service.send_packet(
                        mesh_packet=segment_packet, destination_id="^all", want_ack=True
                    )
                    previous_packet_id = getattr(
                        segment_packet, "id", None
                    )  # 記錄這一段的封包ID，下一段要回覆這一段
                    await asyncio.sleep(1)  # 避免訊息發送太快

                self.logger.info(f"成功發送 AI 回應，用戶: {user_id}")
            else:
                # 發送錯誤訊息
                error_text = f"嗨！{sender_tag}，AI 服務暫時沒辦法回應。"
                error_packet = self.meshtastic_service.create_text_packet(
                    channel_id=channel_id,
                    text=error_text,
                    reply_id=getattr(mp, "id", None),
                )
                await self.meshtastic_service.send_packet(
                    mesh_packet=error_packet, destination_id="^all", want_ack=True
                )

        except Exception as e:
            self.logger.error(f"處理 AI 查詢時發生錯誤: {e}")
            # 發送錯誤訊息
            error_text = f"嗨！{sender_tag}，處理您的問題時出錯了。"
            error_packet = self.meshtastic_service.create_text_packet(
                channel_id=channel_id, text=error_text, reply_id=getattr(mp, "id", None)
            )
            await self.meshtastic_service.send_packet(
                mesh_packet=error_packet, destination_id="^all", want_ack=True
            )
