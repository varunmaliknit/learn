/**
 * Cloudflare Worker: one-click approve / reject for LinkedIn drafts.
 *
 * Routes:
 *   GET /a?d=<draft_id>&s=<hex_hmac_sha256>   -> approve
 *   GET /r?d=<draft_id>&s=<hex_hmac_sha256>   -> reject
 *
 * The signature is HMAC-SHA256(secret, `${action}|${draft_id}`), hex encoded.
 *
 * On valid signature we fire a `repository_dispatch` event on the configured
 * GitHub repo with event_type `linkedin_approve` or `linkedin_reject` and
 * `client_payload: { draft_id }`. The GitHub Actions workflow handles the rest.
 *
 * Required secrets (set via `wrangler secret put <NAME>`):
 *   APPROVAL_HMAC_SECRET   - shared with the Python agent
 *   GITHUB_TOKEN           - fine-grained PAT with `contents:write` on the repo
 *   GITHUB_OWNER           - e.g. "varunmaliknit"
 *   GITHUB_REPO            - e.g. "learn"
 */

export interface Env {
  APPROVAL_HMAC_SECRET: string;
  GITHUB_TOKEN: string;
  GITHUB_OWNER: string;
  GITHUB_REPO: string;
}

const html = (title: string, message: string, color: string): Response =>
  new Response(
    `<!doctype html><html><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>${title}</title>
<style>
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:#f6f7f9;color:#1f2328;display:flex;min-height:100vh;
       align-items:center;justify-content:center;padding:24px}
  .card{background:#fff;border:1px solid #d0d7de;border-radius:12px;
        padding:32px 36px;max-width:520px;width:100%;text-align:center}
  h1{margin:0 0 8px;font-size:22px;color:${color}}
  p{margin:8px 0;color:#57606a;font-size:15px;line-height:1.5}
</style></head>
<body><div class="card"><h1>${title}</h1><p>${message}</p></div></body></html>`,
    { status: 200, headers: { "content-type": "text/html; charset=utf-8" } }
  );

const errorPage = (msg: string): Response => html("Error", msg, "#cf222e");

async function hmacSha256Hex(secret: string, message: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function timingSafeEqualHex(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

async function dispatchToGitHub(
  env: Env,
  eventType: "linkedin_approve" | "linkedin_reject",
  draftId: string
): Promise<{ ok: boolean; status: number; body: string }> {
  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/dispatches`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "linkedin-agent-approver",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      event_type: eventType,
      client_payload: { draft_id: draftId },
    }),
  });
  const body = res.status === 204 ? "" : await res.text();
  return { ok: res.ok, status: res.status, body };
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const pathname = url.pathname.replace(/\/+$/, "") || "/";

    if (pathname === "/" || pathname === "/health") {
      return new Response("ok", { status: 200, headers: { "content-type": "text/plain" } });
    }

    let action: "approve" | "reject";
    if (pathname === "/a") action = "approve";
    else if (pathname === "/r") action = "reject";
    else return errorPage("Unknown route.");

    const draftId = url.searchParams.get("d") || "";
    const signature = url.searchParams.get("s") || "";
    if (!draftId || !signature) {
      return errorPage("Missing draft id or signature.");
    }
    if (!/^[A-Za-z0-9_\-:.]+$/.test(draftId)) {
      return errorPage("Invalid draft id.");
    }
    if (!/^[a-f0-9]{64}$/.test(signature)) {
      return errorPage("Invalid signature format.");
    }

    const expected = await hmacSha256Hex(env.APPROVAL_HMAC_SECRET, `${action}|${draftId}`);
    if (!timingSafeEqualHex(expected, signature)) {
      return errorPage("Signature did not verify. This link may have been tampered with.");
    }

    const eventType = action === "approve" ? "linkedin_approve" : "linkedin_reject";
    const result = await dispatchToGitHub(env, eventType, draftId);
    if (!result.ok) {
      return errorPage(
        `GitHub dispatch failed (HTTP ${result.status}). ` +
          `Verify the worker's GITHUB_TOKEN has 'contents:write' on the repo.`
      );
    }

    if (action === "approve") {
      return html(
        "Approved",
        "Your LinkedIn post is being published. You'll get a confirmation email with the live link within a minute or two.",
        "#1f883d"
      );
    }
    return html(
      "Rejected",
      "Today's draft was discarded. No LinkedIn post will be made.",
      "#57606a"
    );
  },
};
