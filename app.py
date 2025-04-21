import streamlit as st
import srt
import os
from openai import OpenAI
from typing import List, Dict, Any
import yaml
import tempfile
from datetime import datetime
import zipfile
import io

from config import (
    OPENAI_API_KEY,
    TEMP_DIR,
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    ERROR_MESSAGES
)
from utils import (
    combine_subtitles,
    analyze_content,
    check_and_split_yaml,
    format_yaml_for_preview
)

# ページ設定
st.set_page_config(
    page_title="字幕からスライド用YAMLジェネレーター",
    page_icon="📚",
    layout="wide"
)

# サイドバーの設定
st.sidebar.title("📚 字幕→YAML変換")
st.sidebar.write("""
### 使い方
1. SRTファイルまたはテキストファイルをアップロード
2. 自動的に内容を解析
3. プレビューを確認
4. YAMLファイルを個別または一括でダウンロード
""")

# OpenAI クライアントの初期化
client = OpenAI(api_key=OPENAI_API_KEY)

# セッションステートの初期化
if 'yaml_files' not in st.session_state:
    st.session_state.yaml_files = None
if 'last_processed_file' not in st.session_state:
    st.session_state.last_processed_file = None

def create_zip_file(yaml_files: List[Dict[str, Any]], base_filename: str) -> tuple[bytes, str]:
    """
    YAMLファイルをZIPファイルにまとめる
    
    Args:
        yaml_files (List[Dict[str, Any]]): YAMLファイルのリスト
        base_filename (str): 基本となるファイル名
    
    Returns:
        tuple[bytes, str]: ZIPファイルのバイトデータとファイル名
    """
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for i, yaml_data in enumerate(yaml_files, 1):
            # 個別のYAMLファイル名を生成
            yaml_filename = f"{base_filename}_{i}.yaml"
            # YAMLデータを文字列に変換
            yaml_content = format_yaml_for_preview(yaml_data)
            # ZIPファイルに追加
            zip_file.writestr(yaml_filename, yaml_content)
    
    return zip_buffer.getvalue(), f"{base_filename}.zip"

def process_text_content(content: str) -> List[Dict[str, Any]]:
    """テキストコンテンツを処理してYAMLデータのリストを返す"""
    try:
        print("\n=== テキスト処理開始 ===")
        print(f"入力テキスト長: {len(content)}")
        # OpenAI APIで内容を解析
        yaml_data = analyze_content(client, content)
        print("OpenAI APIでの解析が完了")
        # YAMLデータを分割
        yaml_files = check_and_split_yaml(yaml_data)
        print(f"YAMLファイル数: {len(yaml_files)}")
        return yaml_files
    except Exception as e:
        import traceback
        print("\n=== テキスト処理エラー ===")
        print(f"エラーの種類: {type(e).__name__}")
        print(f"エラーメッセージ: {str(e)}")
        print("スタックトレース:")
        traceback.print_exc()
        st.error(f"エラーが発生しました: {str(e)}")
        return []

def process_srt_file(uploaded_file) -> List[Dict[str, Any]]:
    """SRTファイルを処理してYAMLデータのリストを返す"""
    # ファイルを一時ディレクトリに保存
    temp_path = os.path.join(TEMP_DIR, uploaded_file.name)
    with open(temp_path, 'wb') as f:
        f.write(uploaded_file.getbuffer())

    try:
        # ファイル拡張子の確認
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        
        # ファイルの読み込み
        with open(temp_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if file_ext == '.srt':
            # SRTファイルの場合
            print(f"SRTファイルの処理を開始: {uploaded_file.name}")
            subtitles = list(srt.parse(content))
            print(f"字幕数: {len(subtitles)}")
            combined_text = combine_subtitles(subtitles)
            print(f"結合後のテキスト長: {len(combined_text)}")
            return process_text_content(combined_text)
        else:
            # テキストファイルの場合
            print(f"テキストファイルの処理を開始: {uploaded_file.name}")
            print(f"テキスト長: {len(content)}")
            return process_text_content(content)
    
    except Exception as e:
        import traceback
        print("\n=== エラーの詳細 ===")
        print(f"エラーの種類: {type(e).__name__}")
        print(f"エラーメッセージ: {str(e)}")
        print("スタックトレース:")
        traceback.print_exc()
        st.error(f"エラーが発生しました: {str(e)}")
        return []
    finally:
        # 一時ファイルの削除
        if os.path.exists(temp_path):
            os.remove(temp_path)

def main():
    # ファイルアップロード
    uploaded_file = st.file_uploader(
        "ファイルをアップロード",
        type=["srt", "txt"],
        help="字幕ファイル（.srt）またはテキストファイル（.txt）をアップロードしてください"
    )

    if uploaded_file is not None:
        # ファイルサイズのチェック
        if uploaded_file.size > MAX_FILE_SIZE:
            st.error(ERROR_MESSAGES["file_too_large"])
            return

        # ファイル拡張子のチェック
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            st.error(ERROR_MESSAGES["invalid_extension"])
            return

        # 新しいファイルがアップロードされた場合のみ処理を実行
        if (st.session_state.last_processed_file != uploaded_file.name or 
            st.session_state.yaml_files is None):
            
            with st.spinner("ファイルを処理中..."):
                try:
                    # ファイルの処理
                    st.session_state.yaml_files = process_srt_file(uploaded_file)
                    st.session_state.last_processed_file = uploaded_file.name
                    
                except Exception as e:
                    st.error(ERROR_MESSAGES["processing_error"])
                    st.error(f"詳細: {str(e)}")
                    return

        # 解析結果の表示と処理
        if st.session_state.yaml_files:
            # 一括ダウンロードボタンを表示
            st.subheader("一括ダウンロード")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"lecture_content_{timestamp}"
            zip_data, zip_filename = create_zip_file(st.session_state.yaml_files, base_filename)
            
            st.download_button(
                label="全てのYAMLファイルをZIPでダウンロード",
                data=zip_data,
                file_name=zip_filename,
                mime="application/zip"
            )
            
            st.markdown("---")
            
            # タブでYAMLファイルを個別に表示
            st.subheader("個別のファイル")
            tabs = st.tabs([f"ファイル {i+1}" for i in range(len(st.session_state.yaml_files))])
            
            for i, (tab, yaml_data) in enumerate(zip(tabs, st.session_state.yaml_files)):
                with tab:
                    # プレビューの表示
                    st.subheader(f"プレビュー - ファイル {i+1}")
                    
                    # 講義名の表示
                    if "lecture_name" in yaml_data:
                        st.write(f"**講義名**: {yaml_data['lecture_name']}")
                    
                    # セクションの表示
                    if "sections" in yaml_data:
                        for section in yaml_data["sections"]:
                            with st.expander(f"セクション {section['number']}: {section['name']}", expanded=True):
                                # スライドの表示
                                for slide in section.get("slides", []):
                                    st.markdown(f"#### スライド {slide['number']}: {slide['title']}")
                                    
                                    # 内容の表示
                                    if "content" in slide:
                                        st.markdown("**内容:**")
                                        for point in slide["content"]:
                                            st.markdown(f"- {point}")
                                    
                                    # 教授内容の表示
                                    if "teaching_points" in slide:
                                        st.markdown("**教授内容:**")
                                        st.markdown(slide["teaching_points"])
                                    
                                    st.markdown("---")
                    
                    # YAMLデータの表示（折りたたみ可能）
                    with st.expander("YAMLデータを表示"):
                        preview_text = format_yaml_for_preview(yaml_data)
                        st.code(preview_text, language="yaml")
                    
                    # 個別ダウンロードボタン
                    filename = f"{base_filename}_{i+1}.yaml"
                    st.download_button(
                        label=f"このYAMLファイルをダウンロード",
                        data=preview_text,
                        file_name=filename,
                        mime="text/yaml"
                    )

if __name__ == "__main__":
    # 一時ディレクトリの作成
    os.makedirs(TEMP_DIR, exist_ok=True)
    main() 