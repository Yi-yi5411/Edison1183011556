# -*- coding: utf-8 -*-
"""第8步：把匹配到的检测项目数据上传到服务器（可配置接口）。

服务器地址/鉴权/字段映射均可在配置文件中配置或留空。默认 ``dry_run``
模式只打印载荷、不发送真实请求，便于先联调再落地。真实上传请在配置中
填写 base_url / api_key 并把 dry_run 置 false。
"""
import json

import requests

from report_generator.scan_recognition.config import Config


class ServerUploader:
    """可配置的服务器上传器。"""

    def __init__(self, cfg: Config = None):
        cfg = cfg or Config.load()
        s = cfg.server
        self.base_url = (s.get("base_url") or "").rstrip("/")
        self.api_key = s.get("api_key", "")
        self.auth_header = s.get("auth_header", "Authorization")
        self.auth_prefix = s.get("auth_prefix", "Bearer ")
        self.endpoint = s.get("upload_endpoint", "/scan_records/upload")
        self.field_mapping = s.get("field_mapping", {}) or {}
        self.timeout = s.get("timeout", 30)
        self.dry_run = s.get("dry_run", False)
        self.enabled = s.get("enabled", False)

    def _map_payload(self, record):
        if not self.field_mapping:
            return record
        out = {}
        for server_field, local_field in self.field_mapping.items():
            out[server_field] = record.get(local_field, "")
        return out

    def build_payload(self, detection_item, sub_item, rows, matched_columns=None):
        """把对齐行转成服务器期望的 JSON 载荷。"""
        records = []
        for i, row in enumerate(rows):
            rec = dict(row) if isinstance(row, dict) else {
                str(j): (row[j] if j < len(row) else "") for j in range(len(row))
            }
            records.append(self._map_payload(rec))
        return {
            "detection_item": detection_item,
            "sub_item": sub_item,
            "rows": records,
            "matched_columns": matched_columns or [],
        }

    def upload(self, detection_item, sub_item, rows, matched_columns=None):
        """上传数据。dry_run 或未配置时仅返回模拟响应。"""
        payload = self.build_payload(detection_item, sub_item, rows, matched_columns)
        if self.dry_run or not self.enabled or not self.base_url:
            return {
                "ok": True,
                "dry_run": True,
                "payload": payload,
                "message": "dry_run/未配置：未发送真实请求，请检查配置文件后开启。",
            }
        url = self.base_url + self.endpoint
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers[self.auth_header] = self.auth_prefix + self.api_key
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return {"ok": True, "status_code": resp.status_code, "response": resp.json()}