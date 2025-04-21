import os
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

# OpenAI API設定
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4.1-2025-04-14"


# YAMLファイル設定
MAX_YAML_LENGTH = 50000  # 1ファイルあたりの最大文字数
MAX_FILE_SIZE = 10 * 1024 * 1024  # 最大ファイルサイズ（10MB）

# アプリケーション設定
TEMP_DIR = "temp"
ALLOWED_EXTENSIONS = {".srt", ".txt"}  # 許可する拡張子

# エラーメッセージ
ERROR_MESSAGES = {
    "file_too_large": "ファイルサイズが大きすぎます（最大10MB）",
    "invalid_extension": "SRTファイルまたはテキストファイルのみアップロード可能です",
    "api_error": "OpenAI APIでエラーが発生しました",
    "processing_error": "処理中にエラーが発生しました",
}

# 一時ファイルの設定
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR) 