import logging
import os
import traceback
import uuid
import yaml
from datetime import datetime
from filelock import FileLock

logger = logging.getLogger(__name__)


class ConfigUtil:
    """設定檔工具類別，負責處理設定檔的讀取和管理"""

    def __init__(self, check_and_merge: bool = False) -> None:
        self.logger = logging.getLogger(__name__)
        self.config_dir = os.path.join(os.getcwd(), "configs")
        self.default_config_path = os.path.join(
            os.getcwd(), "app/configs/default/config.yml"
        )
        self.config_path = os.path.join(self.config_dir, "config.yml")
        self.lock = FileLock(self.config_path + ".lock")
        self.ensure_config_exists(check_and_merge)

    def ensure_config_exists(self, check_and_merge: bool = False) -> None:
        """確保設定檔存在，如果不存在則從預設設定複製一份，並同步比較差異"""
        if not os.path.exists(self.config_path):
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self.default_config_path, "r", encoding="utf-8") as default_file:
                with open(self.config_path, "w", encoding="utf-8") as config_file:
                    config_file.write(default_file.read())
        else:
            if check_and_merge:
                # 如果 config.yml 存在，檢查並補充/刪除設定項
                try:
                    # 使用鎖確保單一進程訪問
                    with self.lock:
                        # 先備份原始設定檔
                        backup_path = (
                            self.config_path
                            + f".bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        )
                        with open(
                            self.config_path, "r", encoding="utf-8"
                        ) as original_file:
                            with open(
                                backup_path, "w", encoding="utf-8"
                            ) as backup_file:
                                backup_file.write(original_file.read())

                        with open(
                            self.default_config_path, "r", encoding="utf-8"
                        ) as default_file:
                            default_config = yaml.safe_load(default_file)

                        current_config = self.read_config()

                        # 檢查並補充缺失的設定項
                        self.merge_configs(current_config, default_config)

                        # 檢查並刪除多餘的設定項
                        self.remove_extra_configs(current_config, default_config)

                        # 最後將更新後的設定寫回檔案
                        with open(
                            self.config_path, "w", encoding="utf-8"
                        ) as config_file:
                            yaml.dump(
                                current_config,
                                config_file,
                                allow_unicode=True,
                            )
                    # 完成後刪除備份檔案
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    self.logger.info("設定已檢查並更新。")
                except Exception as e:
                    self.logger.error(
                        "檢查和更新設定時發生錯誤: %s",
                        traceback.format_exc(),
                    )
                    # 如果發生異常，嘗試從備份恢復
                    if os.path.exists(backup_path):
                        try:
                            with open(
                                backup_path, "r", encoding="utf-8"
                            ) as backup_file:
                                with open(
                                    self.config_path, "w", encoding="utf-8"
                                ) as config_file:
                                    config_file.write(backup_file.read())
                            self.logger.warning("設定已從備份恢復。")
                        except Exception as restore_e:
                            self.logger.error(f"從備份恢復失敗: {str(restore_e)}")
                    raise e

    def merge_configs(self, current_config: dict, default_config: dict) -> None:
        """補充缺失的設定項"""
        if current_config is None:
            current_config = {}

        for key, value in default_config.items():
            if key not in current_config:
                current_config[key] = value
            elif isinstance(value, dict) and isinstance(current_config.get(key), dict):
                self.merge_configs(current_config[key], value)  # 遞迴合併

    def remove_extra_configs(self, current_config, default_config):
        """刪除多餘的設定項"""
        keys_to_delete = []
        for key in current_config:
            if key not in default_config:
                keys_to_delete.append(key)
            elif isinstance(current_config[key], dict) and isinstance(
                default_config.get(key), dict
            ):
                self.remove_extra_configs(
                    current_config[key], default_config[key]
                )  # 遞迴處理

        for key in keys_to_delete:
            del current_config[key]

    def read_config(self):
        """讀取設定檔"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as file:
                return yaml.safe_load(file)
        except Exception as e:
            self.logger.error("讀取設定檔時發生錯誤: %s", traceback.format_exc())
            raise e

    # 取得某個 key 的值
    def get_config(self, key, default=None):
        """取得某個設定項的值"""
        try:
            config = self.read_config()
            keys = key.split(".")
            value = config
            for k in keys:
                if k not in value:
                    return default
                value = value[k]
            return value
        except Exception as e:
            self.logger.error("取得設定值時發生錯誤: %s", traceback.format_exc())
            raise e

    def edit_config(self, key, value):
        """編輯某個設定項的值"""
        try:
            with self.lock:
                config = self.read_config()
                keys = key.split(".")
                d = config
                for k in keys[:-1]:
                    if k not in d:
                        d[k] = {}
                    d = d[k]
                d[keys[-1]] = value
                with open(self.config_path, "w", encoding="utf-8") as file:
                    yaml.dump(
                        config,
                        file,
                        allow_unicode=True,
                    )
        except Exception as e:
            self.logger.error("編輯設定值時發生錯誤: %s", traceback.format_exc())
            raise e
