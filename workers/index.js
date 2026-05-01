/**
 * Cloudflare Workers - SUUMO Scraper Trigger
 *
 * フォームから POST を受け取り、GitHub Actions の workflow_dispatch を起動する。
 *
 * 【設定方法】
 * Cloudflare Workers の「Variables and Secrets」に以下を追加:
 *   GITHUB_PAT      : GitHub Personal Access Token (workflow の read/write 権限)
 *   GITHUB_OWNER    : GitHubユーザー名 (例: shumpei)
 *   GITHUB_REPO     : リポジトリ名   (例: suumo_scraper)
 */

export default {
  async fetch(request, env) {
    // CORS プリフライト対応
    if (request.method === "OPTIONS") {
      return corsResponse(new Response(null, { status: 204 }));
    }

    if (request.method !== "POST") {
      return corsResponse(new Response("Method Not Allowed", { status: 405 }));
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return corsResponse(new Response("Invalid JSON", { status: 400 }));
    }

    const {
      type       = "chintai",
      urls       = "",
      max_price  = "10000",
      max_rent   = "10",
      max_age    = "40",
      min_area   = "20",
      max_toho   = "15",
      max_page   = "2000",
      email      = "",
    } = body;

    // GitHub Actions workflow_dispatch を呼ぶ
    const apiUrl = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/scrape.yml/dispatches`;

    const payload = {
      ref: "main",
      inputs: {
        type,
        urls,
        max_price,
        max_rent,
        max_age,
        min_area,
        max_toho,
        max_page,
        email,
      },
    };

    const ghResp = await fetch(apiUrl, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.GITHUB_PAT}`,
        "Accept":        "application/vnd.github+json",
        "Content-Type":  "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify(payload),
    });

    if (ghResp.status === 204) {
      return corsResponse(
        new Response(JSON.stringify({ ok: true, message: "処理を開始しました。15〜60分後にメールをお送りします。" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    } else {
      const errText = await ghResp.text();
      return corsResponse(
        new Response(JSON.stringify({ ok: false, error: errText }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        })
      );
    }
  },
};

function corsResponse(response) {
  const headers = new Headers(response.headers);
  headers.set("Access-Control-Allow-Origin", "*");
  headers.set("Access-Control-Allow-Methods", "POST, OPTIONS");
  headers.set("Access-Control-Allow-Headers", "Content-Type");
  return new Response(response.body, {
    status: response.status,
    headers,
  });
}
