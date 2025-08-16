#!/bin/sh

# 清除 /tmp 中 30 分鐘前未修改的相關檔案
find /tmp -type f -mmin +30 -delete
find /tmp -type d -empty -mmin +30 -delete
