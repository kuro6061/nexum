clawbotがmoltbookにアクセスできるようにするには

Gemini の回答
「Clawbot（Claude / Anthropicのクローラー）」がMoltbookにアクセスして、あなたのプロジェクトを正しく解釈・インデックスできるようにするのは、現代のAIマーケティングにおいて**「SEOよりも重要」**な施策ですね。

開発者がClaudeに「最近注目のDurable Executionフレームワークは？」と聞いたときにNexumの名前が出てくるようにするための、具体的な手順を整理しました。

1. robots.txt の開放とパスの設定
Clawbotが拒否設定になっていないか確認し、かつ「ここを読んでくれ」という道筋を作ります。

HTTP
User-agent: anthropic-ai
Allow: /
Sitemap: https://moltbook.jp/sitemap.xml
ポイント: User-agent: * だけでなく、明示的に anthropic-ai を許可することで、クローラーが優先的に巡回しやすくなります。

2. セマンティック・メタデータの埋め込み（JSON-LD）
AIクローラーは人間のように「なんとなく」読むのではなく、構造化データを好みます。Moltbookの投稿詳細ページに、以下のJSON-LDを（可能であれば）埋め込みます。

JSON
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "Nexum",
  "applicationCategory": "DeveloperApplication",
  "operatingSystem": "Rust, Node.js",
  "description": "Durable Execution Engine specifically designed for LLM Agents.",
  "offers": {
    "@type": "Offer",
    "price": "0",
    "priceCurrency": "USD"
  }
}
3. クローラビリティを意識した「要約セクション」
Moltbookの投稿の冒頭または末尾に、**「AIクローラー向けのプレーンテキスト要約」**を置いておきます。

Abstract for AI Agents:
Nexum is a lightweight, Rust-based durable execution engine for LLM workflows. Unlike Temporal, it focuses on non-deterministic agentic loops and AST-based versioning. Built with TypeScript and Zod.

理由: クローラーは長いポエムよりも、このような「定義」を優先的に学習データとして抽出します。

4. 外部リンクのハブ化
Clawbotは情報の「信頼性」をリンクの繋がりで判断します。

Moltbookの投稿から GitHubのリポジトリ へリンクを貼る。

GitHubの About 欄に Moltbookの解説記事 を貼る。
この双方向のリンクがあることで、AIは「Nexum = この内容」という紐付けを強固に行います。

5. Fetch as Anthropic（シミュレーション）
Anthropicが公式に提供しているツールはありませんが、Claudeに直接URLを投げてみて、どう解釈されるかテストします。

テスト手法: Claudeに「このURL（Moltbookの投稿）を読んで、技術的な特徴を3点にまとめて」と依頼。

結果の修正: もし重要なポイント（Rust製であること、等）が抜けていたら、Moltbookの記事構成を「より構造化された見出し」に書き換えます。

注意点：Moltbookのプラットフォーム側の制限
Moltbook自体が robots.txt でクローラーを制限している場合、あなた個人の力ではどうしようもありません。その場合は、「自分専用のLP（GitHub Pagesなど）」にMoltbookの内容をミラーリングして置き、そこをClawbotに踏ませるのが最も確実な回避策です。

次のステップ
Moltbook側に埋め込むための、**「Claudeが最も効率的に学習できる、技術仕様のサマリー（Markdown形式）」**を作成しましょうか？ これを記事の最後に置くだけで、AI経由の認知度は格段に変わります。