import yaml
from typing import List, Dict, Any
import srt
from openai import OpenAI
import json
from prompts import SYSTEM_PROMPT
import math
import asyncio
from openai import AsyncOpenAI
from concurrent.futures import ThreadPoolExecutor

def split_text(text: str, num_parts: int = 8) -> List[str]:
    """
    テキストを指定された数に分割する
    
    Args:
        text (str): 分割するテキスト
        num_parts (int): 分割数（デフォルト: 8）
    
    Returns:
        List[str]: 分割されたテキストのリスト
    """
    # 段落で分割
    paragraphs = [p for p in text.split('\n\n') if p.strip()]
    
    if len(paragraphs) <= num_parts:
        return paragraphs
    
    # 段落数をnum_partsで割って、各部分の段落数を計算
    paragraphs_per_part = math.ceil(len(paragraphs) / num_parts)
    
    # テキストを分割
    parts = []
    for i in range(0, len(paragraphs), paragraphs_per_part):
        part = '\n\n'.join(paragraphs[i:i + paragraphs_per_part])
        if part.strip():  # 空の部分は除外
            parts.append(part)
    
    return parts

def combine_subtitles(subtitles: List[srt.Subtitle]) -> str:
    """
    字幕を結合してテキストにする
    """
    combined_text = ""
    current_speaker = None
    current_text = []
    
    for subtitle in subtitles:
        # 話者の抽出（字幕の2行目を話者として扱う）
        lines = subtitle.content.split('\n')
        if len(lines) > 1:
            speaker = lines[1]
            text = '\n'.join(lines[2:]) if len(lines) > 2 else lines[0]
        else:
            speaker = "不明"
            text = lines[0]
            
        # 同じ話者の発話をまとめる
        if speaker == current_speaker:
            current_text.append(text)
        else:
            if current_speaker is not None:
                combined_text += f"{current_speaker}：{''.join(current_text)}\n\n"
            current_speaker = speaker
            current_text = [text]
    
    # 最後の話者の発話を追加
    if current_speaker is not None:
        combined_text += f"{current_speaker}：{''.join(current_text)}\n\n"
    
    return combined_text

def truncate_content(content: str, max_length: int = 100) -> str:
    """
    コンテンツを指定された長さに制限する
    
    Args:
        content (str): 制限するテキスト
        max_length (int): 最大文字数
    
    Returns:
        str: 制限されたテキスト
    """
    if len(content) <= max_length:
        return content
    return content[:max_length-3] + "..."

async def analyze_content_part(client: AsyncOpenAI, part: str, part_num: int, total_parts: int = 8) -> Dict[str, Any]:
    """
    テキストの一部を非同期で解析する
    
    Args:
        client (AsyncOpenAI): 非同期OpenAIクライアント
        part (str): 解析するテキスト
        part_num (int): パート番号
        total_parts (int): 全パート数
    
    Returns:
        Dict[str, Any]: 解析結果
    """
    print(f"\n=== パート {part_num+1}/{total_parts} の解析を開始 ===")
    print(f"テキストの長さ: {len(part)} 文字")
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4.1-2025-04-14",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"これは講義の{part_num+1}/{total_parts}部分です。全体の文脈を考慮して解析してください。\n\n{part}"}
            ],
            temperature=0.7
        )
        
        yaml_text = response.choices[0].message.content
        print("\n=== APIレスポンス受信 ===")
        
        # マークダウンのコードブロック記法を削除
        yaml_text = yaml_text.replace('```yaml', '').replace('```', '').strip()
        
        # YAMLとして解析
        try:
            yaml_data = yaml.safe_load(yaml_text)
            print(f"パート {part_num+1} のYAML解析に成功")
            return yaml_data
        except yaml.YAMLError as e:
            print(f"パート {part_num+1} のYAML解析に失敗: {str(e)}")
            raise
            
    except Exception as e:
        print(f"パート {part_num+1} の処理中にエラー: {str(e)}")
        raise

async def summarize_with_openai_async(client: AsyncOpenAI, content: str, max_tokens: int = 100) -> str:
    """
    OpenAI APIを使用してコンテンツを非同期で要約する
    """
    try:
        response = await client.chat.completions.create(
            model="gpt-4.1-2025-04-14",
            messages=[
                {"role": "system", "content": "与えられたテキストを自然な形で要約してください。重要なポイントを保持しながら、簡潔に表現してください。"},
                {"role": "user", "content": f"以下のテキストを{max_tokens}トークン程度に要約してください：\n\n{content}"}
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"要約中にエラーが発生しました: {str(e)}")
        return truncate_content(content, max_tokens)

async def adjust_yaml_size_async(yaml_data: Dict[str, Any], client: AsyncOpenAI, max_chars: int = 10000) -> Dict[str, Any]:
    """
    YAMLデータのサイズを非同期で調整する
    """
    current_size = len(yaml.dump(yaml_data, allow_unicode=True))
    
    # 文字数が少なすぎる場合（8000文字未満）は内容を拡充
    if current_size < 8000:
        adjusted_data = yaml_data.copy()
        
        # 各セクションのスライドの内容を拡充
        for section in adjusted_data.get("sections", []):
            for slide in section.get("slides", []):
                # コンテンツの拡充
                if "content" in slide and isinstance(slide["content"], list):
                    content_text = "\n".join(slide["content"])
                    expansion_prompt = f"""
                    以下の内容をより詳細に展開してください：
                    - 各ポイントに具体例を追加
                    - 関連する補足情報を含める
                    - 実践的な応用例を追加
                    
                    元の内容：
                    {content_text}
                    """
                    expanded_content = await summarize_with_openai_async(client, expansion_prompt, 300)
                    slide["content"] = [point.strip() for point in expanded_content.split("\n") if point.strip()]
                
                # 指導ポイントの拡充
                if "teaching_points" in slide:
                    points_text = slide["teaching_points"] if isinstance(slide["teaching_points"], str) else "\n".join(slide["teaching_points"])
                    points_prompt = f"""
                    以下の指導ポイントをより詳細に展開してください：
                    - 具体的な指導方法を追加
                    - 予想される質問や疑問点への対応
                    - 実践的なアドバイスを含める
                    
                    元のポイント：
                    {points_text}
                    """
                    expanded_points = await summarize_with_openai_async(client, points_prompt, 200)
                    slide["teaching_points"] = [point.strip() for point in expanded_points.split("\n") if point.strip()]
        
        return adjusted_data
    
    # 文字数が多すぎる場合は既存の縮小ロジックを実行
    if current_size <= max_chars:
        return yaml_data
    
    adjusted_data = yaml_data.copy()
    
    # 並列で処理するタスクのリスト
    tasks = []
    
    # 各セクションのスライドの内容を制限
    for section in adjusted_data.get("sections", []):
        for slide in section.get("slides", []):
            if "content" in slide:
                if isinstance(slide["content"], list):
                    combined_content = "\n".join(slide["content"])
                    tasks.append(("content", slide, await summarize_with_openai_async(client, combined_content, 150)))
                    
                    if len(slide["content"]) > 5:
                        combined_points = "\n".join(slide["content"])
                        tasks.append(("content_limit", slide, await summarize_with_openai_async(client, 
                            f"以下の内容を5つの重要なポイントにまとめてください：\n{combined_points}", 200)))
                else:
                    tasks.append(("content", slide, await summarize_with_openai_async(client, str(slide["content"]), 100)))
            
            if "teaching_points" in slide:
                tasks.append(("teaching_points", slide, await summarize_with_openai_async(client, str(slide["teaching_points"]), 200)))
    
    # 並列処理の結果を適用
    for task_type, slide, result in tasks:
        if task_type == "content":
            if isinstance(slide["content"], list):
                slide["content"] = [point.strip() for point in result.split("\n") if point.strip()]
            else:
                slide["content"] = result
        elif task_type == "content_limit":
            slide["content"] = [point.strip() for point in result.split("\n") if point.strip()][:5]
        elif task_type == "teaching_points":
            slide["teaching_points"] = result
    
    # 再度サイズを確認
    final_size = len(yaml.dump(adjusted_data, allow_unicode=True))
    if final_size > max_chars:
        for section in adjusted_data.get("sections", []):
            slides = section.get("slides", [])
            if len(slides) > 10:
                combined_slides = "\n\n".join([
                    f"スライド {slide['number']}: {slide['title']}\n{slide.get('content', '')}\n{slide.get('teaching_points', '')}"
                    for slide in slides
                ])
                summary_prompt = f"""
                以下のスライド群を10個の重要なスライドに要約してください。
                各スライドには以下の情報を含めてください：
                - タイトル
                - 内容（箇条書き）
                - 教授内容
                
                元のスライド内容：
                {combined_slides}
                """
                summarized_slides = await summarize_with_openai_async(client, summary_prompt, 1000)
                try:
                    summarized_data = yaml.safe_load(summarized_slides)
                    print(f"要約データの型: {type(summarized_data)}")
                    print(f"要約データの内容: {summarized_data}")
                    
                    def create_slide_dict(slide_data, index):
                        if isinstance(slide_data, dict):
                            return {
                                "number": str(index + 1),
                                "title": slide_data.get("title", ""),
                                "content": slide_data.get("content", []),
                                "teaching_points": slide_data.get("teaching_points", "")
                            }
                        elif isinstance(slide_data, str):
                            return {
                                "number": str(index + 1),
                                "title": slide_data,
                                "content": [],
                                "teaching_points": ""
                            }
                        else:
                            return {
                                "number": str(index + 1),
                                "title": "スライド " + str(index + 1),
                                "content": [],
                                "teaching_points": ""
                            }

                    if isinstance(summarized_data, dict):
                        print("辞書型のデータを処理中...")
                        if "slides" in summarized_data:
                            slides_data = summarized_data["slides"]
                        else:
                            slides_data = [summarized_data]
                    elif isinstance(summarized_data, list):
                        print("リスト型のデータを処理中...")
                        slides_data = summarized_data
                    else:
                        print("未知の型のデータを処理中...")
                        slides_data = [str(summarized_data)]

                    section["slides"] = [create_slide_dict(slide, i) for i, slide in enumerate(slides_data)]

                except Exception as e:
                    print(f"\n=== スライドの要約処理中にエラー ===")
                    print(f"エラーの種類: {type(e).__name__}")
                    print(f"エラーの詳細: {str(e)}")
                    print(f"summarized_slides の内容: {summarized_slides}")
                    print(f"現在の section の内容: {section}")
                    section["slides"] = [
                        {
                            "number": str(i+1),
                            "title": str(slide),
                            "content": [],
                            "teaching_points": ""
                        }
                        for i, slide in enumerate(slides[:10])
                    ]
    
    return adjusted_data

def analyze_content(client: OpenAI, text: str) -> Dict[str, Any]:
    """
    OpenAI APIを使用してテキストを解析し、構造化する
    """
    try:
        # 非同期クライアントの作成
        async_client = AsyncOpenAI(api_key=client.api_key)
        
        # テキストを8部分に分割
        text_parts = split_text(text, num_parts=8)
        print(f"テキストを8部分に分割しました。")
        
        # 非同期処理を実行
        async def process_all_parts():
            try:
                print("\n=== 全パートの並列処理を開始 ===")
                # 全パートを並列で解析
                tasks = [
                    analyze_content_part(async_client, part, i, len(text_parts))
                    for i, part in enumerate(text_parts)
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # エラーチェック
                errors = [r for r in results if isinstance(r, Exception)]
                if errors:
                    print("\n=== パート処理中にエラーが発生 ===")
                    for i, error in enumerate(errors):
                        print(f"エラー {i+1}:")
                        print(f"種類: {type(error).__name__}")
                        print(f"詳細: {str(error)}")
                    raise Exception(f"パート処理中に{len(errors)}件のエラーが発生しました")
                
                return results
            except Exception as e:
                import traceback
                print("\n=== process_all_parts でエラー発生 ===")
                print(f"エラーの種類: {type(e).__name__}")
                print(f"エラーの詳細: {str(e)}")
                print("スタックトレース:")
                traceback.print_exc()
                raise
        
        # 非同期処理を実行
        yaml_parts = asyncio.run(process_all_parts())
        
        print("\n=== 全パートの解析が完了しました ===")
        print(f"解析されたパート数: {len(yaml_parts)}")
        print(f"戻り値の型: {type(yaml_parts)}")
        print(f"最初のパートの型: {type(yaml_parts[0]) if yaml_parts else 'なし'}")
        
        if not yaml_parts:
            raise ValueError("解析されたパートが存在しません。")
        
        # 講義名を取得
        lecture_name = yaml_parts[0].get("lecture_name")
        if lecture_name is None:
            raise ValueError(f"lecture_nameが見つかりません。")
        
        # セクションごとにスライドをグループ化
        sections_dict = {}
        section_order = []
        
        for part_num, part in enumerate(yaml_parts, 1):
            print(f"\n=== パート{part_num}の処理 ===")
            
            sections = part.get("sections", [])
            print(f"セクション数: {len(sections)}")
            
            for section in sections:
                section_name = section.get("name")
                if not section_name:
                    continue
                
                if section_name not in sections_dict:
                    sections_dict[section_name] = []
                    section_order.append(section_name)
                
                for slide_num, slide in enumerate(section.get("slides", []), 1):
                    slide_data = {
                        "number": str(slide_num),
                        "title": slide["title"],
                        "content": slide["content"],
                        "teaching_points": "\n".join(slide.get("teaching_points", []))
                    }
                    sections_dict[section_name].append(slide_data)
        
        # 最終的なYAML構造を作成（8ファイルに分割）
        final_yaml = []
        sections_per_file = max(1, len(section_order) // 8)
        
        async def process_all_files():
            try:
                print("\n=== ファイル処理を開始 ===")
                tasks = []
                for i in range(8):
                    start_idx = i * sections_per_file
                    end_idx = (i + 1) * sections_per_file if i < 7 else len(section_order)
                    
                    file_sections = []
                    for section_num, section_name in enumerate(section_order[start_idx:end_idx], 1):
                        section_data = {
                            "number": str(section_num),
                            "name": section_name,
                            "slides": sections_dict[section_name]
                        }
                        file_sections.append(section_data)
                    
                    if file_sections:
                        yaml_file = {
                            "lecture_name": lecture_name,
                            "sections": file_sections
                        }
                        tasks.append(adjust_yaml_size_async(yaml_file, async_client))
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # エラーチェック
                errors = [r for r in results if isinstance(r, Exception)]
                if errors:
                    print("\n=== ファイル処理中にエラーが発生 ===")
                    for i, error in enumerate(errors):
                        print(f"エラー {i+1}:")
                        print(f"種類: {type(error).__name__}")
                        print(f"詳細: {str(error)}")
                    raise Exception(f"ファイル処理中に{len(errors)}件のエラーが発生しました")
                
                return results
            except Exception as e:
                import traceback
                print("\n=== process_all_files でエラー発生 ===")
                print(f"エラーの種類: {type(e).__name__}")
                print(f"エラーの詳細: {str(e)}")
                print("スタックトレース:")
                traceback.print_exc()
                raise
        
        # 非同期でファイルサイズの調整を実行
        final_yaml = asyncio.run(process_all_files())
        
        print("\n=== 最終的なYAMLデータの情報 ===")
        print(f"ファイル数: {len(final_yaml)}")
        print(f"データ型: {type(final_yaml)}")
        
        return final_yaml
        
    except Exception as e:
        print(f"\n=== エラーが発生しました ===")
        print(f"エラーの種類: {type(e).__name__}")
        print(f"エラーの詳細: {str(e)}")
        raise Exception(f"OpenAI APIでの解析中にエラーが発生しました: {str(e)}")

def check_and_split_yaml(yaml_data: Dict[str, Any], num_parts: int = 8) -> List[Dict[str, Any]]:
    """
    YAMLデータを指定された数に分割する

    Args:
        yaml_data (Dict[str, Any]): 分割するYAMLデータ
        num_parts (int): 分割数（デフォルト: 8）

    Returns:
        List[Dict[str, Any]]: 分割されたYAMLデータのリスト
    """
    # リストの場合は、そのまま返す
    if isinstance(yaml_data, list):
        return yaml_data

    # 辞書の場合
    if isinstance(yaml_data, dict):
        if not yaml_data.get("file"):
            return [yaml_data]

        # ファイルエントリの総数を取得
        total_files = len(yaml_data["file"])
        
        # 1パートあたりのファイル数を計算
        files_per_part = math.ceil(total_files / num_parts)
        
        # YAMLデータを分割
        yaml_files = []
        for i in range(0, total_files, files_per_part):
            part_files = yaml_data["file"][i:i + files_per_part]
            if part_files:  # 空のパートは除外
                part_yaml = {
                    "lecture_name": yaml_data["lecture_name"],
                    "file": part_files
                }
                yaml_files.append(part_yaml)
        
        return yaml_files

    # その他の型の場合は、単一要素のリストとして返す
    return [{"lecture_name": "Unknown", "sections": []}]

def format_yaml_for_preview(yaml_data: Dict[str, Any]) -> str:
    """
    YAMLデータをプレビュー用に整形する
    """
    return yaml.dump(yaml_data, allow_unicode=True, sort_keys=False, indent=2) 