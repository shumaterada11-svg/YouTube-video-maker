# youtube-video-maker

「神ショートカット」解説のショート動画（YouTube Shorts / X 向け 1080x1920）を自動生成するツールです。

- 台本: JSON で用意するか、テーマを渡して Claude に書かせる
- 映像: キーキャップが押し込まれるアニメーション、焼き込み字幕、進捗バー
- 音声: AI ナレーション（edge-tts、使えない環境では pyopenjtalk に自動で切り替え）＋自作 BGM・効果音
- 出力: `video.mp4`・`thumbnail.png`・`youtube.txt`（タイトル・説明文・タグ）

## セットアップ

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# FFmpeg と日本語フォントが必要（Mac: brew install ffmpeg ／ Ubuntu: apt install ffmpeg fonts-noto-cjk）
```

オフラインで音声を作りたい場合は `pip install pyopenjtalk` も入れてください（ビルドに cmake が必要です）。

## 使い方

```bash
# 台本 JSON から作る
python video_maker.py --script video_scripts/chrome_shortcuts.json

# テーマから Claude が台本を書いて作る（ANTHROPIC_API_KEY が必要）
python video_maker.py --topic "Excelが3倍速くなる神ショートカット5選"
```

| オプション | 内容 |
| --- | --- |
| `--out DIR` | 出力先（既定: `output/`） |
| `--tts auto\|edge\|openjtalk` | 音声合成エンジン |
| `--voice ja-JP-KeitaNeural` | edge-tts の声（既定は女性の `ja-JP-NanamiNeural`） |
| `--bgm FILE` / `--no-bgm` | BGM を差し替える／付けない |
| `--handle @account` | 画面下部にアカウント名を表示 |

API キーは環境変数 `ANTHROPIC_API_KEY`、または `config.json` の `"ANTHROPIC_API_KEY"` から読み込みます。

## 台本 JSON の形式

`video_scripts/chrome_shortcuts.json` を参照してください。`hook`（冒頭）・`items`（ショートカット 4〜5 個）・`outro`（締め）の 3 部構成で、
見出しの `**語**` は強調色になります。`narration` は読み上げ用なので、英字のキー名はカタカナで書きます（Cmd → コマンド）。
