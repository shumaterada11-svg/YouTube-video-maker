# youtube-video-maker

YouTube Shorts / X 向けの縦型動画（1080x1920）を自動生成するツールです。

- `story_maker.py`: 犬キャラのショートアニメ（ワン高物語）
- `video_maker.py`: 「神ショートカット」解説動画

## 犬キャラのショートアニメ（story_maker.py）

```bash
python story_maker.py --story stories/wan_high_ep1.json
```

キャラクター・背景はすべてプログラムで描画します（`toon.py`）。台本 JSON は「ショット」の並びで、
各ショットに背景（`bg`）、登場キャラ（`cast`：位置・表情・ポーズ・動き）、セリフ（`lines`）を書きます。
セリフごとに `set` で表情やポーズを変えたり、`fx` で演出（`focus` 集中線、`shake` 揺れ、`flash`、`impact:文字`、`confetti` 紙吹雪）を入れられます。

| 種類 | 使える値 |
| --- | --- |
| キャラ | kotaro（ダックス）, leon（プードル）, gou（ピットブル）, pom1〜3（ポメのチア部）, yanki1〜2（不良） |
| 背景 | school_gate, hallway, sunset, stage, results |
| 表情 | normal, happy, shy, sad, shocked, determined, cool, soft, wink, moved |
| ポーズ | stand, shy, point, crossed, notebook, flyer, trash, fist, bump, cheer_a/b, wave_a/b, banzai |
| 動き | idle, walk, jump, tremble, cheer, wave |
| BGM | normal, tense, happy |

### Gemini で作った絵・動画を使う

ブラウザ版 Gemini などで作った絵や動画を、場面ごとに差し替えられます。
出力先の `素材` フォルダ（Mac なら `デスクトップ/YouTube動画/<slug>/素材/`）に `shot01.png`、`shot07.mp4` のような名前で置くと、自動で使われます（`--assets` で別のフォルダも指定可）。

- 番号は台本の場面の順番（1から）。同じ番号なら動画を優先します。
- `shot11_2.png` のように `_番号` を付けると、その場面の何番目のセリフから切り替えるかを指定できます。
- 素材がない場面は、これまで通りプログラムの絵で描きます。字幕・声・BGM・演出はどちらでも付きます。
- `thumbnail.png` を置くと、サムネイルの背景に使います。

第1話の素材づくりの手順とプロンプトは `gemini_prompts/wan_high_ep1.md` にあります。

### 声の設定

声は次の順で自動的に選ばれます（`--tts` で固定も可能）。

1. **VOICEVOX**（無料・キャラ声が数十種類）: アプリが起動していれば自動で使います
2. **edge-tts**（無料・男女1種類ずつ）: インターネット接続が必要
3. **pyopenjtalk**（オフライン・機械的な声）

VOICEVOX を使う手順:

1. https://voicevox.hiroshiba.jp/ から VOICEVOX をインストールして起動する（起動したままにする）
2. `python story_maker.py --list-voices` で使える声を確認する
3. `python story_maker.py --story stories/wan_high_ep1.json` を実行する

キャラごとの声は `story_maker.py` の `VOICES` が初期値です。台本 JSON に `voices` を書くと、その話だけ上書きできます。

```json
"voices": {
  "gou": {"voicevox": "青山龍星/ノーマル", "vv_speed": 0.9, "vv_pitch": -0.05},
  "kotaro": {"voicevox": "白上虎太郎/びくびく"}
}
```

| 項目 | 内容 |
| --- | --- |
| `voicevox` | 「キャラ名/スタイル」（スタイル名を省略すると最初のスタイル） |
| `vv_speed` / `vv_pitch` / `vv_intonation` | 話速（1.0 が標準）／高さ（-0.15〜0.15）／抑揚（1.0 が標準） |
| `voice` / `pitch` / `rate` | edge-tts の声（`ja-JP-KeitaNeural` など）／高さ（`"+10Hz"`）／速さ（`"+10%"`） |
| `half_tone` / `speed` | pyopenjtalk の高さ（半音）／速さ |

VOICEVOX の声を使った動画は、説明文に「VOICEVOX:キャラ名」のクレジットが必要です。`youtube.txt` に自動で追記されます。

## ショートカット解説動画（video_maker.py）

- 台本: JSON で用意するか、テーマを渡して Claude に書かせる
- 映像: キーキャップが押し込まれるアニメーション、焼き込み字幕、進捗バー
- 音声: AI ナレーション（edge-tts、使えない環境では pyopenjtalk に自動で切り替え）＋自作 BGM・効果音
- 出力: `video.mp4`・`thumbnail.png`・`youtube.txt`（タイトル・説明文・タグ）

## セットアップ

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# ffmpeg は imageio-ffmpeg に同梱のものを自動で使う（Linux では日本語フォント fonts-noto-cjk が必要）
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
| `--out DIR` | 出力先（既定: Mac はデスクトップの「YouTube動画」、それ以外は `output/`） |
| `--tts auto\|edge\|openjtalk` | 音声合成エンジン |
| `--voice ja-JP-KeitaNeural` | edge-tts の声（既定は女性の `ja-JP-NanamiNeural`） |
| `--bgm FILE` / `--no-bgm` | BGM を差し替える／付けない |
| `--handle @account` | 画面下部にアカウント名を表示 |

API キーは環境変数 `ANTHROPIC_API_KEY`、または `config.json` の `"ANTHROPIC_API_KEY"` から読み込みます。

## 台本 JSON の形式

`video_scripts/chrome_shortcuts.json` を参照してください。`hook`（冒頭）・`items`（ショートカット 4〜5 個）・`outro`（締め）の 3 部構成で、
見出しの `**語**` は強調色になります。`narration` は読み上げ用なので、英字のキー名はカタカナで書きます（Cmd → コマンド）。
