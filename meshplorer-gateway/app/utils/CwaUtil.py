from datetime import datetime
import aiohttp
import inspect
import logging
from typing import Optional, List, Dict
from app.exceptions.BusinessLogicException import BusinessLogicException
from app.utils.ConfigUtil import ConfigUtil


class CwaUtil:
    """中央氣象局工具類別，負責取得天氣預報相關資料"""
    def __init__(self, config: dict = None) -> None:
        self.config = config or ConfigUtil().read_config()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(self.config.get("log", {}).get("level", "INFO").upper())

    def get_location_id_by_name(self, name: str) -> str:
        """根據地點名稱取得對應的 ID 代碼"""
        location_id_map = {
            "宜蘭縣": "F-D0047-001",
            "桃園市": "F-D0047-005",
            "新竹縣": "F-D0047-009",
            "苗栗縣": "F-D0047-013",
            "彰化縣": "F-D0047-017",
            "南投縣": "F-D0047-021",
            "雲林縣": "F-D0047-025",
            "嘉義縣": "F-D0047-029",
            "屏東縣": "F-D0047-033",
            "臺東縣": "F-D0047-037",
            "花蓮縣": "F-D0047-041",
            "澎湖縣": "F-D0047-045",
            "基隆市": "F-D0047-049",
            "新竹市": "F-D0047-053",
            "嘉義市": "F-D0047-057",
            "臺北市": "F-D0047-061",
            "高雄市": "F-D0047-065",
            "新北市": "F-D0047-069",
            "臺中市": "F-D0047-073",
            "臺南市": "F-D0047-077",
            "連江縣": "F-D0047-081",
            "金門縣": "F-D0047-085",
        }
        location_id = location_id_map.get(name)
        if not location_id:
            raise BusinessLogicException(f"找不到對應的地點名稱: {name}")
        return location_id

    async def get_cwa_data_fd0047093(
        self,
        location_name: str,  # 縣市名稱
        location_district: str,  # 鄉鎮名稱
    ) -> Optional[Dict]:
        """取得中央氣象局鄉鎮天氣預報相關資料"""
        location_id = self.get_location_id_by_name(location_name)
        url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-093?Authorization={self.config['cwa']['key']}&limit=1&locationId={location_id}&LocationName={location_district}&ElementName=%E5%A4%A9%E6%B0%A3%E9%A0%90%E5%A0%B1%E7%B6%9C%E5%90%88%E6%8F%8F%E8%BF%B0"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    self.logger.error(f"Failed to fetch CWA data: {response.status}")
                    return None
                data = await response.json()
                locations = data.get("records", {}).get("Locations", []) if data else []
                if not locations:
                    self.logger.warning(
                        f"找不到對應的地點資料: {location_name}({location_id}) {location_district}"
                    )
                    return None

                location_list = locations[0].get("Location", [])
                if not location_list:
                    self.logger.warning(
                        f"在第一個地點項目中找不到地點資料"
                    )
                    return None

                return location_list[0]

    def summarize_weather_descriptions(
        self, data: dict, limit: int = 1, offset: int = 0
    ) -> str:
        """擷取前X筆天氣描述並合併成一句話"""
        self.logger.info(
            f"Summarizing weather descriptions from data: {data} with limit: {limit}, offset: {offset}"
        )
        try:
            time_data = next(
                elem["Time"]
                for elem in data["WeatherElement"]
                if elem["ElementName"] == "天氣預報綜合描述"
            )
        except (KeyError, StopIteration):
            return "找不到相關的天氣描述資料。"

        descriptions = []
        for entry in time_data[offset : offset + limit]:
            start = datetime.fromisoformat(entry["StartTime"]).strftime("%m/%d %H")
            end = datetime.fromisoformat(entry["EndTime"]).strftime("%H")
            desc = entry["ElementValue"][0]["WeatherDescription"]
            # descriptions.append(f"{start}~：{desc}")
            descriptions.append(f"{start}至{end}時：{desc}")

        if not descriptions:
            return "找不到天氣描述資料。"

        # 組合
        message = "；".join(descriptions)
        # 如果超過X字，則截斷
        if len(message) > 100:
            message = message[:100] + "..."
        self.logger.info(f"Summarized weather message: {message}")
        return message
